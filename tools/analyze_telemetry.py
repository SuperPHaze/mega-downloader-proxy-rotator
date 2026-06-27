#!/usr/bin/env python3
"""Analizzatore telemetria MDPR (Fase 3) — strumento offline, di sola lettura.

Trasforma la "scatola nera" prodotta dalla Fase 1
(`logs/telemetry/<session_id>/` con `manifest.json`, `events.jsonl`,
`samples.jsonl`) in risposte su *dove, come e perché* si perde velocità.

Produce, in `--out`:
  - dataset *tidy* in CSV (chunk_attempts, samples, files, rollup per
    fonte/protocollo/IP/proxy, opzionale intra_samples_long col firehose);
  - un report HTML autonomo (SVG inline, niente CDN) + la versione Markdown;
  - un export AI compatto (distillato + esempi reali) da incollare in un
    modello per generare ipotesi.

Principi: sola lettura (non tocca mai telemetria o app), solo stdlib (parquet/
pandas opzionali e guardati), streaming di `events.jsonl` tollerante a righe
rotte/campi null. Nessun import dell'app a runtime: il tool legge solo file.

Uso:
    python -m tools.analyze_telemetry logs/telemetry/<id>
    python -m tools.analyze_telemetry logs/telemetry/        # unione sessioni
    python -m tools.analyze_telemetry <id> --out OUTDIR --firehose
"""
from __future__ import annotations

import argparse
import collections
import csv
import html
import json
import os
import statistics as st  # noqa: F401  (disponibile per estensioni future)
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterator

# Soglia "corsia idle": un campione 1 Hz sotto questa velocita' (byte/s) indica
# una corsia di fatto ferma. Coincide con PARALLEL_MIN_THROUGHPUT_BPS lato app,
# ma qui e' una costante locale: il tool e' autonomo e non importa la config.
_IDLE_BPS = 200 * 1024


# === Lettura JSONL (streaming, tollerante) =================================

def stream_jsonl(path: str | Path) -> Iterator[dict]:
    """Genera i record JSON di un file riga per riga (no caricamento integrale).
    Le righe vuote/rotte e i record non-dict vengono saltati senza sollevare."""
    if not os.path.exists(path):
        return
    try:
        f = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def _read_json(path: str | Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# === Statistica di base ====================================================

def pct(xs: list, q: float):
    """Percentile q (0..1) con indicizzazione robusta. None su lista vuota."""
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, int(q * len(s)))
    return s[i]


def _num(x):
    return x if isinstance(x, (int, float)) else None


def _ts(x):
    """Parsing ISO tollerante: None su valore mancante/non valido."""
    try:
        return datetime.fromisoformat(x)
    except (TypeError, ValueError):
        return None


# === Caricamento sessioni ==================================================

def discover_sessions(path: Path) -> list[Path]:
    """Una singola sessione (cartella con manifest.json) oppure la cartella
    padre: in tal caso tutte le sottocartelle-sessione, ordinate per nome."""
    if (path / "manifest.json").exists():
        return [path]
    if not path.is_dir():
        return []
    return sorted(
        d for d in path.iterdir()
        if d.is_dir() and (d / "manifest.json").exists()
    )


def load_sessions(session_dirs: list[Path]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Carica e unisce piu' sessioni. Ritorna (manifests, chunk_attempts,
    other_events, samples). Ogni record e' taggato con session_id (gia'
    presente nel JSONL, qui garantito anche per i piu' vecchi). Gli array
    `intra_samples` vengono RIMOSSI dai chunk_attempt e sostituiti da `intra_n`
    per non tenere il firehose in RAM (l'export long si fa in streaming a parte).
    """
    manifests: list[dict] = []
    chunk_attempts: list[dict] = []
    other_events: list[dict] = []
    samples: list[dict] = []
    for d in session_dirs:
        man = _read_json(d / "manifest.json")
        sid = man.get("session_id") or d.name
        man.setdefault("session_id", sid)
        manifests.append(man)
        for rec in stream_jsonl(d / "events.jsonl"):
            rec.setdefault("session_id", sid)
            if rec.get("event_type") == "chunk_attempt":
                intra = rec.pop("intra_samples", None)
                rec["intra_n"] = len(intra) if isinstance(intra, list) else 0
                tp = _num(rec.get("throughput_bps"))
                rec["throughput_kbs"] = round(tp / 1024, 1) if tp else None
                chunk_attempts.append(rec)
            else:
                other_events.append(rec)
        for rec in stream_jsonl(d / "samples.jsonl"):
            rec.setdefault("session_id", sid)
            samples.append(rec)
    return manifests, chunk_attempts, other_events, samples


# === Rollup per dimensione =================================================

def rollup(ca: list[dict], keyfn) -> list[dict]:
    """Aggrega i tentativi-chunk per chiave: tentativi, ok, ok_rate e
    percentili p50/p90/p99 del throughput (KB/s) sui soli OK."""
    d: dict = collections.defaultdict(lambda: {"att": 0, "ok": 0, "tp": []})
    for r in ca:
        k = keyfn(r)
        d[k]["att"] += 1
        if r.get("outcome") == "ok":
            d[k]["ok"] += 1
            tp = _num(r.get("throughput_bps"))
            if tp:
                d[k]["tp"].append(tp / 1024)
    out = []
    for k, v in d.items():
        out.append({
            "key": k, "attempts": v["att"], "ok": v["ok"],
            "ok_rate": round(100 * v["ok"] / v["att"]) if v["att"] else 0,
            "thr_kbs_p50": round(pct(v["tp"], .5) or 0),
            "thr_kbs_p90": round(pct(v["tp"], .9) or 0),
            "thr_kbs_p99": round(pct(v["tp"], .99) or 0),
        })
    return sorted(out, key=lambda x: -x["attempts"])


# === Banda, concorrenza e classificatore del vincolo =======================

def _bandwidth_analysis(sm: list[dict], ca: list[dict],
                        link_capacity_bps: int | None, connections: int | None) -> dict:
    """Utilizzo della linea, timeline delle corsie attive e classificatore del
    vincolo per secondo. Tollerante a capacita' assente (salta i rami che la
    richiedono). Ritorna {"available": False} se non ci sono campioni."""
    out: dict = {"available": False, "link_capacity_bps": link_capacity_bps,
                 "nominal_lanes": connections}

    # Bucket per-secondo dei campioni: aggrega instant_bps tra file concorrenti
    # (la utilizzo della LINEA e' la somma dei throughput dei file attivi nello
    # stesso istante); pool_alive/cooldown sono globali (uso il max nel secondo).
    buckets: dict[int, dict] = {}
    for s in sm:
        t = _ts(s.get("ts"))
        if t is None:
            continue
        sec = int(t.timestamp())
        b = buckets.setdefault(sec, {"bps": 0.0, "pa": 0, "pc": 0})
        b["bps"] += _num(s.get("instant_bps")) or 0
        b["pa"] = max(b["pa"], _num(s.get("pool_alive")) or 0)
        b["pc"] = max(b["pc"], _num(s.get("pool_cooldown")) or 0)
    if not buckets:
        return out

    # Corsie attive nel tempo: ogni tentativo occupa [ts_start, ts_start+t_total].
    # Sweep a delta per-secondo, poi somma cumulativa -> active_lanes(sec).
    delta: dict[int, int] = collections.defaultdict(int)
    for r in ca:
        t = _ts(r.get("ts_start"))
        if t is None:
            continue
        start = int(t.timestamp())
        dur = (_num(r.get("t_total_ms")) or 0) / 1000
        end = int(start + dur)
        delta[start] += 1
        delta[end + 1] -= 1
    active_at: dict[int, int] = {}
    if delta:
        run = 0
        for sec in range(min(delta), max(delta) + 1):
            run += delta.get(sec, 0)
            active_at[sec] = run

    lanes_series = [active_at[sec] for sec in buckets if sec in active_at]
    if not lanes_series and active_at:
        lanes_series = list(active_at.values())
    out["active_lanes_p50"] = round(pct(lanes_series, .5) or 0)
    out["active_lanes_p90"] = round(pct(lanes_series, .9) or 0)

    # Utilizzo della linea (solo se la capacita' e' nota).
    if link_capacity_bps:
        utils = [b["bps"] / link_capacity_bps for b in buckets.values()]
        over = sum(1 for u in utils if u >= 0.85)
        out["util_p50"] = round(pct(utils, .5) or 0, 3)
        out["util_p90"] = round(pct(utils, .9) or 0, 3)
        out["util_max"] = round(max(utils) if utils else 0, 3)
        out["pct_time_over_85"] = round(100 * over / len(utils)) if utils else 0

    # Classificatore del vincolo per secondo. Senza capacita' i rami che
    # dipendono da u vengono saltati (il resto resta informativo).
    conns = connections or 1
    states: collections.Counter = collections.Counter()
    for sec in buckets:
        b = buckets[sec]
        pa, pc = b["pa"], b["pc"]
        al = active_at.get(sec, 0)
        u = (b["bps"] / link_capacity_bps) if link_capacity_bps else None
        if u is not None and u >= 0.85:
            state = "line_bound"
        elif (pa + pc) > 0 and pc >= 0.5 * (pa + pc):
            state = "rate_limit_bound"
        elif pa < conns:
            state = "pool_bound"
        elif al < 0.7 * conns:
            state = "lane_supply_bound"
        else:
            state = "proxy_speed_bound"
        states[state] += 1
    total = sum(states.values())
    out["binding_states_pct"] = (
        {k: round(100 * v / total) for k, v in states.most_common()} if total else {}
    )
    out["dominant_binding"] = states.most_common(1)[0][0] if states else None
    out["available"] = True
    return out


# === Analisi principale ====================================================

def analyze(manifests: list[dict], ca: list[dict], ev: list[dict], sm: list[dict],
            link_capacity_bps: int | None = None) -> dict:
    man = manifests[0] if manifests else {}
    plans = [r for r in ev if r.get("event_type") == "file_plan"]
    resolves = [r for r in ev if r.get("event_type") == "file_resolved"]
    re_resolves = [r for r in ev if r.get("event_type") == "re_resolve"]
    pool_empties = [r for r in ev if r.get("event_type") == "pool_empty"]

    # Capacita' linea: priorita' all'override CLI, poi al manifest. Sessioni
    # vecchie senza il dato -> None (metriche di utilizzo saltate, niente crash).
    if link_capacity_bps is None:
        link_capacity_bps = man.get("link_capacity_bps")
    link_capacity_bps = link_capacity_bps if (link_capacity_bps and link_capacity_bps > 0) else None

    R: dict = {
        "session_ids": [m.get("session_id") for m in manifests],
        "n_sessions": len(manifests),
        "app_version": man.get("app_version"),
        "chunk_size_mb": round(man.get("chunk_size_bytes", 0) / 1048576, 2),
        "connections": man.get("connections_per_file"),
        "selection_mode": man.get("selection_mode"),
        "speed_selection_enabled": man.get("speed_selection_enabled"),
        "n_links": man.get("n_links"),
        "link_capacity_bps": link_capacity_bps,
        "link_capacity_mbit": (round(link_capacity_bps * 8 / 1_000_000, 1)
                               if link_capacity_bps else None),
        "config": man.get("config", {}),
        "totals": {}, "outcomes": {}, "by_source": [], "by_protocol": [],
        "by_proxy_top": [], "by_ip_top": [], "per_file": [],
        "decomposition": {}, "parallelism": {}, "rate_limit": {},
        "waste_by_category": [], "re_resolve": {}, "pool_empty": {},
        "resume_check": [], "bandwidth": {}, "recommendations": [],
    }

    # --- Esiti e throughput globale ---
    R["outcomes"] = dict(collections.Counter(r.get("outcome") for r in ca))
    ok = [r for r in ca if r.get("outcome") == "ok"]
    tp_ok = [r["throughput_bps"] / 1024 for r in ok if _num(r.get("throughput_bps"))]
    R["totals"] = {
        "chunk_attempts": len(ca), "ok": len(ok),
        "ok_rate": round(100 * len(ok) / len(ca), 1) if ca else 0,
        "thr_kbs_p10": round(pct(tp_ok, .1) or 0),
        "thr_kbs_p50": round(pct(tp_ok, .5) or 0),
        "thr_kbs_p90": round(pct(tp_ok, .9) or 0),
        "thr_kbs_p99": round(pct(tp_ok, .99) or 0),
    }

    # --- Rollup per dimensione ---
    R["by_source"] = rollup(ca, lambda r: r.get("proxy_source") or "?")
    R["by_protocol"] = rollup(ca, lambda r: r.get("proxy_protocol") or "?")
    R["by_proxy_top"] = rollup(ca, lambda r: f"{r.get('proxy_host')}:{r.get('proxy_port')}")[:15]
    R["by_ip_top"] = rollup(ca, lambda r: r.get("egress_ip") or "?")[:15]

    # --- Decomposizione wall-clock del tempo dei tentativi ---
    tot = sum((_num(r.get("t_total_ms")) or 0) for r in ca) / 1000
    prod = sum((_num(r.get("t_transfer_ms")) or 0) for r in ok) / 1000
    waste = sum((_num(r.get("t_total_ms")) or 0) for r in ca if r.get("outcome") != "ok") / 1000
    R["decomposition"] = {
        "attempt_time_s": round(tot),
        "productive_transfer_s": round(prod),
        "productive_pct": round(100 * prod / tot, 1) if tot else 0,
        "failed_attempt_s": round(waste),
        "failed_pct": round(100 * waste / tot, 1) if tot else 0,
        "backoff_declared_s": round(sum((_num(r.get("backoff_s")) or 0) for r in ca)),
    }

    # --- Spreco per categoria di esito (dove va il tempo perso) ---
    waste_cat: dict = collections.defaultdict(lambda: {"n": 0, "s": 0.0})
    for r in ca:
        oc = r.get("outcome")
        if oc == "ok":
            continue
        waste_cat[oc]["n"] += 1
        waste_cat[oc]["s"] += (_num(r.get("t_total_ms")) or 0) / 1000
    R["waste_by_category"] = sorted(
        [{"outcome": k, "attempts": v["n"], "wasted_s": round(v["s"])}
         for k, v in waste_cat.items()],
        key=lambda x: -x["wasted_s"],
    )

    # --- Parallelismo effettivo (corsie davvero piene) ---
    inst = [s["instant_bps"] for s in sm if _num(s.get("instant_bps")) and s["instant_bps"] > 0]
    agg_p50 = pct(inst, .5) or 0
    chunk_bps_p50 = (pct(tp_ok, .5) or 0) * 1024  # tp_ok e' in KB/s
    R["parallelism"] = {
        "aggregate_bps_p50_kbs": round(agg_p50 / 1024),
        "per_chunk_bps_p50_kbs": round(chunk_bps_p50 / 1024),
        "effective_lanes": round(agg_p50 / chunk_bps_p50, 2) if chunk_bps_p50 else None,
        "nominal_lanes": man.get("connections_per_file"),
    }

    # --- Attribuzione rate-limit (403/509) ---
    rl = [r for r in ca if r.get("outcome") in ("http_403", "http_509")]
    rl_by_ip = collections.Counter(r.get("egress_ip") or "?" for r in rl)
    rl_by_src = collections.Counter(r.get("proxy_source") or "?" for r in rl)
    R["rate_limit"] = {
        "total": len(rl),
        "by_ip_top": [{"key": k, "count": c} for k, c in rl_by_ip.most_common(15)],
        "by_source_top": [{"key": k, "count": c} for k, c in rl_by_src.most_common(15)],
    }

    # --- re_resolve e pool_empty ---
    R["re_resolve"] = {
        "total": len(re_resolves),
        "by_outcome": dict(collections.Counter(r.get("outcome") for r in re_resolves)),
    }
    R["pool_empty"] = {
        "total": len(pool_empties),
        "added_total": sum((_num(r.get("added")) or 0) for r in pool_empties),
    }

    # --- Per-file: wall-clock, efficienza, idle, stragglers (dai samples) ---
    by_file_sm: dict = collections.defaultdict(list)
    for s in sm:
        by_file_sm[(s.get("session_id"), s.get("file_id"))].append(s)
    plan_by_file = {(p.get("session_id"), p.get("file_id")): p for p in plans}
    nominal_lanes = man.get("connections_per_file") or 1

    for (sid, fid), ss in sorted(
        by_file_sm.items(), key=lambda x: (x[0][0] or "", x[0][1] is None, x[0][1])
    ):
        ss = [s for s in ss if s.get("ts")]
        ts = [_ts(s["ts"]) for s in ss]
        ts = [t for t in ts if t is not None]
        if not ts:
            continue
        wall = (max(ts) - min(ts)).total_seconds()
        plan = plan_by_file.get((sid, fid), {})
        size = plan.get("file_size") or (ss[-1].get("total_size") or 0)
        eff = size / wall / 1048576 if wall > 0 else 0
        idle = sum(1 for s in ss if (_num(s.get("instant_bps")) or 0) < _IDLE_BPS)
        # Completamenti dei chunk OK per questo file (rel. all'inizio file).
        f0 = min(ts).timestamp()
        f1 = max(ts).timestamp()
        ends = []
        tail_proxies: collections.Counter = collections.Counter()
        tail_sources: collections.Counter = collections.Counter()
        for r in ca:
            if (r.get("session_id") != sid or r.get("file_id") != fid
                    or r.get("outcome") != "ok" or not r.get("ts_start")):
                continue
            t = _ts(r["ts_start"])
            if t is None:
                continue
            end = t.timestamp() + (_num(r.get("t_total_ms")) or 0) / 1000
            ends.append((end, r))
        ends.sort(key=lambda x: x[0])
        straggler_n = 0
        straggler_wall_pct = 0
        if ends:
            # La "coda" inizia quando restano <= nominal_lanes chunk da finire:
            # da li' le corsie si svuotano e il wall e' dominato dai lenti.
            tail_idx = max(0, len(ends) - nominal_lanes)
            tail_start = ends[tail_idx][0]
            straggler_n = len(ends) - tail_idx
            if wall > 0:
                straggler_wall_pct = round(100 * max(0.0, f1 - tail_start) / wall)
            for end, r in ends[tail_idx:]:
                tail_proxies[f"{r.get('proxy_host')}:{r.get('proxy_port')}"] += 1
                tail_sources[r.get("proxy_source") or "?"] += 1
        R["per_file"].append({
            "session_id": sid, "file_id": fid,
            "size_mb": round(size / 1048576), "wall_s": round(wall),
            "eff_mbs": round(eff, 2),
            "idle_samples_pct": round(100 * idle / len(ss)) if ss else 0,
            "straggler_chunks": straggler_n,
            "straggler_wall_pct": straggler_wall_pct,
            "tail_sources": [k for k, _ in tail_sources.most_common(3)],
        })

    # --- Resume check: download() ripetuti senza chunk ripresi ---
    plans_by_file: dict = collections.defaultdict(list)
    for p in plans:
        plans_by_file[(p.get("session_id"), p.get("file_id"))].append(p)
    for (sid, fid), ps in plans_by_file.items():
        n_dl = len(ps)
        resumed_total = sum((_num(p.get("resumed_chunks")) or 0) for p in ps)
        zero_resume = sum(1 for p in ps if (_num(p.get("resumed_chunks")) or 0) == 0)
        suspect = n_dl > 1 and zero_resume > 1
        if n_dl > 1 or suspect:
            R["resume_check"].append({
                "session_id": sid, "file_id": fid, "downloads": n_dl,
                "resumed_chunks_total": resumed_total,
                "zero_resume_downloads": zero_resume, "suspect": suspect,
            })

    R["bandwidth"] = _bandwidth_analysis(
        sm, ca, link_capacity_bps, man.get("connections_per_file"),
    )

    R["recommendations"] = _recommendations(R)
    return R


def _recommendations(R: dict) -> list[str]:
    recs: list[str] = []
    # Fonti a bassa resa (molti tentativi, ok_rate basso): candidate alla potatura.
    for s in R["by_source"]:
        if s["attempts"] >= 20 and s["ok_rate"] < 50:
            recs.append(
                f"Fonte '{s['key']}' a bassa resa: {s['ok_rate']}% ok su "
                f"{s['attempts']} tentativi — valutare la potatura."
            )
    # Hotspot di rate-limit.
    rl = R["rate_limit"]
    if rl["total"] > 0 and rl["by_ip_top"]:
        top = rl["by_ip_top"][0]
        recs.append(
            f"Rate-limit (403/509): {rl['total']} totali, hotspot {top['key']} "
            f"({top['count']} colpi)."
        )
    # Verso la banda massima: vincolo dominante + utilizzo della linea.
    bw = R.get("bandwidth", {})
    if bw.get("available"):
        pct_states = bw.get("binding_states_pct", {})
        dom = bw.get("dominant_binding")
        dom_pct = pct_states.get(dom, 0) if dom else 0
        advice = {
            "line_bound": "linea satura: e' il limite fisico, non c'e' molto da spremere.",
            "rate_limit_bound": "N troppo alto per il pool, riduci le connessioni o ruota piu' proxy.",
            "pool_bound": "pochi proxy vivi: aumenta il pool (fonti/validazione) o abbassa N.",
            "lane_supply_bound": "corsie idle: alza N o migliora la selezione (get_next a secco).",
            "proxy_speed_bound": "corsie piene ma proxy lenti: serve selezione per velocita'.",
        }.get(dom, "")
        if dom and advice:
            recs.append(f"Vincolo dominante '{dom}' ({dom_pct}% del tempo) → {advice}")
        if bw.get("util_p50") is not None:
            recs.append(
                f"Utilizzo linea mediano {round(bw['util_p50'] * 100)}% "
                f"(picco {round(bw['util_max'] * 100)}%, "
                f"sopra l'85% nel {bw.get('pct_time_over_85', 0)}% del tempo)."
            )
    # Parallelismo sotto il nominale.
    p = R["parallelism"]
    if p.get("effective_lanes") and p.get("nominal_lanes"):
        if p["effective_lanes"] < 0.6 * p["nominal_lanes"]:
            recs.append(
                f"Parallelismo effettivo {p['effective_lanes']} corsie su "
                f"{p['nominal_lanes']} nominali: le corsie non sono piene "
                f"(proxy lenti o pool sotto fabbisogno)."
            )
    # Quota stragglers.
    for f in R["per_file"]:
        if f["straggler_wall_pct"] >= 25:
            recs.append(
                f"File {f['file_id']} (sess {f['session_id']}): la coda di "
                f"chunk lenti occupa il {f['straggler_wall_pct']}% del wall-clock."
            )
    # Resume sospetto.
    for rc in R["resume_check"]:
        if rc["suspect"]:
            recs.append(
                f"File {rc['file_id']} (sess {rc['session_id']}): "
                f"{rc['downloads']} download con {rc['zero_resume_downloads']} "
                f"senza chunk ripresi — possibile re-download di chunk gia' fatti."
            )
    # Spreco dominante.
    if R["waste_by_category"]:
        w = R["waste_by_category"][0]
        if w["wasted_s"] > 0:
            recs.append(
                f"Tempo perso dominato da '{w['outcome']}': ~{w['wasted_s']}s su "
                f"{w['attempts']} tentativi falliti."
            )
    if not recs:
        recs.append("Nessuna anomalia di rilievo: la sessione appare sana.")
    return recs


# === Scrittura CSV =========================================================

_CA_COLS = [
    "session_id", "ts", "file_id", "url_hash", "chunk_idx", "attempt",
    "attempt_of", "chunk_start", "chunk_end", "chunk_bytes", "ts_start",
    "proxy_host", "proxy_port", "proxy_protocol", "proxy_source",
    "proxy_score_before", "proxy_latency_ms", "proxy_uptime_pct",
    "proxy_anonymity", "pool_alive", "pool_cooldown", "egress_ip",
    "http_status", "t_headers_ms", "t_firstbyte_ms", "t_transfer_ms",
    "t_total_ms", "bytes_downloaded", "throughput_bps", "throughput_kbs",
    "intra_n", "outcome", "pool_action", "error", "backoff_s",
]


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _union_cols(rows: list[dict], preferred: list[str]) -> list[str]:
    seen = list(preferred)
    sset = set(preferred)
    for r in rows:
        for k in r:
            if k not in sset:
                sset.add(k)
                seen.append(k)
    return seen


def write_datasets(out: Path, R: dict, ca: list[dict], sm: list[dict]) -> None:
    _write_csv(out / "chunk_attempts.csv", ca, _union_cols(ca, _CA_COLS))
    sm_cols = _union_cols(sm, [
        "session_id", "ts", "file_id", "url_hash", "bytes_done", "total_size",
        "instant_bps", "pool_alive", "pool_cooldown", "pool_discarded",
        "refill_count",
    ])
    _write_csv(out / "samples.csv", sm, sm_cols)
    _write_csv(out / "files.csv", R["per_file"], [
        "session_id", "file_id", "size_mb", "wall_s", "eff_mbs",
        "idle_samples_pct", "straggler_chunks", "straggler_wall_pct",
        "tail_sources",
    ])
    rollup_cols = ["key", "attempts", "ok", "ok_rate",
                   "thr_kbs_p50", "thr_kbs_p90", "thr_kbs_p99"]
    _write_csv(out / "sources.csv", R["by_source"], rollup_cols)
    _write_csv(out / "protocols.csv", R["by_protocol"], rollup_cols)
    _write_csv(out / "proxies.csv", R["by_proxy_top"], rollup_cols)
    _write_csv(out / "ips.csv", R["by_ip_top"], rollup_cols)


def write_firehose(out: Path, session_dirs: list[Path]) -> int:
    """Esplode gli array intra_samples in formato long (una riga per campione
    64 KB). Streaming: non carica gli array in RAM tutti insieme. Ritorna il
    numero di righe scritte."""
    path = out / "intra_samples_long.csv"
    n = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_id", "file_id", "chunk_idx", "attempt",
                    "t_offset_ms", "cum_bytes"])
        for d in session_dirs:
            man = _read_json(d / "manifest.json")
            sid = man.get("session_id") or d.name
            for rec in stream_jsonl(d / "events.jsonl"):
                if rec.get("event_type") != "chunk_attempt":
                    continue
                intra = rec.get("intra_samples")
                if not isinstance(intra, list):
                    continue
                fid = rec.get("file_id")
                cidx = rec.get("chunk_idx")
                att = rec.get("attempt")
                for s in intra:
                    if isinstance(s, (list, tuple)) and len(s) >= 2:
                        w.writerow([sid, fid, cidx, att, s[0], s[1]])
                        n += 1
    return n


# === Grafici SVG inline (stdlib) ===========================================

_COLORS = ["#4f8cff", "#3ecf8e", "#f5a623", "#f25767", "#a78bfa",
           "#22d3ee", "#fb7185", "#84cc16"]


def _svg_line_throughput(sm: list[dict], link_capacity_bps: int | None = None) -> str:
    """Throughput aggregato nel tempo, una linea per file (indice campione su x,
    instant_bps in MB/s su y). Punti ricampionati a max ~300 per linea. Se nota,
    la capacita' della linea e' disegnata come banda orizzontale di riferimento."""
    by_file: dict = collections.defaultdict(list)
    for s in sm:
        by_file[(s.get("session_id"), s.get("file_id"))].append(s)
    series = []
    ymax = 1.0
    for key, ss in by_file.items():
        vals = [(_num(s.get("instant_bps")) or 0) / 1048576 for s in ss]
        if len(vals) > 300:
            step = len(vals) / 300
            vals = [vals[int(i * step)] for i in range(300)]
        if vals:
            ymax = max(ymax, max(vals))
            series.append((key, vals))
    if not series:
        return '<div class="empty">Nessun campione per il grafico throughput.</div>'
    cap_mbs = link_capacity_bps / 1048576 if link_capacity_bps else None
    if cap_mbs:
        ymax = max(ymax, cap_mbs)
    W, H, pad = 760, 240, 30
    lines = []
    if cap_mbs:
        ycap = H - pad - (H - 2 * pad) * (cap_mbs / ymax)
        lines.append(
            f'<line x1="{pad}" y1="{ycap:.1f}" x2="{W - pad}" y2="{ycap:.1f}" '
            f'stroke="#f25767" stroke-width="1" stroke-dasharray="5 4"/>'
            f'<text x="{pad + 4}" y="{ycap - 4:.1f}" fill="#f25767" font-size="11">'
            f'linea {cap_mbs:.1f} MB/s</text>'
        )
    for idx, (key, vals) in enumerate(series):
        n = len(vals)
        pts = []
        for i, v in enumerate(vals):
            x = pad + (W - 2 * pad) * (i / max(1, n - 1))
            y = H - pad - (H - 2 * pad) * (v / ymax)
            pts.append(f"{x:.1f},{y:.1f}")
        color = _COLORS[idx % len(_COLORS)]
        lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.3" '
            f'points="{" ".join(pts)}"/>'
        )
        lines.append(
            f'<text x="{W - pad - 90}" y="{pad + 14 * idx + 4}" fill="{color}" '
            f'font-size="11">file {key[1]}</text>'
        )
    axes = (
        f'<line x1="{pad}" y1="{H - pad}" x2="{W - pad}" y2="{H - pad}" stroke="#2a2e38"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H - pad}" stroke="#2a2e38"/>'
        f'<text x="{pad}" y="{pad - 8}" fill="#9aa1ad" font-size="11">MB/s (picco {ymax:.1f})</text>'
        f'<text x="{W - pad - 40}" y="{H - pad + 18}" fill="#9aa1ad" font-size="11">tempo →</text>'
    )
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" '
            f'style="max-width:{W}px">{axes}{"".join(lines)}</svg>')


def _svg_hist_proxy_throughput(by_proxy: list[dict]) -> str:
    """Istogramma del throughput p50 per proxy (KB/s) in bucket."""
    vals = [p["thr_kbs_p50"] for p in by_proxy if p.get("thr_kbs_p50")]
    if not vals:
        return '<div class="empty">Nessun dato throughput per proxy.</div>'
    buckets = [0, 200, 500, 1000, 2000, 5000, 10 ** 9]
    labels = ["<200", "200-500", "500-1k", "1k-2k", "2k-5k", ">5k"]
    counts = [0] * (len(buckets) - 1)
    for v in vals:
        for i in range(len(buckets) - 1):
            if buckets[i] <= v < buckets[i + 1]:
                counts[i] += 1
                break
    cmax = max(counts) or 1
    W, H, pad = 760, 220, 36
    bw = (W - 2 * pad) / len(counts)
    bars = []
    for i, c in enumerate(counts):
        h = (H - 2 * pad) * (c / cmax)
        x = pad + i * bw
        y = H - pad - h
        bars.append(
            f'<rect x="{x + 6:.1f}" y="{y:.1f}" width="{bw - 12:.1f}" height="{h:.1f}" fill="#4f8cff"/>'
            f'<text x="{x + bw / 2:.1f}" y="{H - pad + 16}" fill="#9aa1ad" font-size="11" '
            f'text-anchor="middle">{labels[i]}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{y - 4:.1f}" fill="#e6e8ec" font-size="11" '
            f'text-anchor="middle">{c}</text>'
        )
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">'
            f'<text x="{pad}" y="{pad - 12}" fill="#9aa1ad" font-size="11">'
            f'Proxy per fascia di throughput p50 (KB/s)</text>{"".join(bars)}</svg>')


def _svg_outcomes(outcomes: dict) -> str:
    items = sorted(outcomes.items(), key=lambda x: -(x[1] or 0))
    if not items:
        return '<div class="empty">Nessun esito.</div>'
    total = sum(v for _, v in items) or 1
    W, rowh, pad = 760, 26, 8
    H = pad * 2 + rowh * len(items)
    rows = []
    for i, (k, v) in enumerate(items):
        y = pad + i * rowh
        w = (W - 220) * (v / total)
        color = "#3ecf8e" if k == "ok" else "#f25767"
        rows.append(
            f'<text x="0" y="{y + 16}" fill="#e6e8ec" font-size="12">{html.escape(str(k))}</text>'
            f'<rect x="150" y="{y + 4}" width="{w:.1f}" height="16" fill="{color}"/>'
            f'<text x="{150 + w + 6:.1f}" y="{y + 16}" fill="#9aa1ad" font-size="11">'
            f'{v} ({100 * v / total:.1f}%)</text>'
        )
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">'
            f'{"".join(rows)}</svg>')


# === Report HTML ============================================================

_CSS = """
:root { --bg:#0f1115; --panel:#171a21; --border:#2a2e38; --text:#e6e8ec;
  --muted:#9aa1ad; --ok:#3ecf8e; --bad:#f25767; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--text); margin:0; padding:24px;
  font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif; line-height:1.5; }
h1 { font-size:1.5rem; margin:0 0 4px; }
h2 { font-size:1.1rem; margin:32px 0 12px; border-bottom:1px solid var(--border); padding-bottom:6px; }
.subtitle { color:var(--muted); margin-bottom:24px; font-size:.9rem; }
.cards { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:10px;
  padding:14px 18px; min-width:150px; flex:1; }
.card .label { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.03em; }
.card .value { font-size:1.6rem; font-weight:600; margin-top:4px; }
table { width:100%; border-collapse:collapse; background:var(--panel); border-radius:10px; overflow:hidden; margin-bottom:16px; }
th,td { text-align:left; padding:8px 12px; border-bottom:1px solid var(--border); font-size:.88rem; }
th { color:var(--muted); font-weight:600; font-size:.78rem; text-transform:uppercase; }
tr:last-child td { border-bottom:none; }
.chart-wrap { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:16px; }
.empty { color:var(--muted); font-style:italic; padding:8px 0; }
.recs li { margin:4px 0; }
footer { color:var(--muted); font-size:.78rem; margin-top:32px; text-align:center; }
"""


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return '<div class="empty">Nessun dato.</div>'
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def render_html(R: dict, generated_at: str, sm: list[dict]) -> str:
    t = R["totals"]
    dec = R["decomposition"]
    par = R["parallelism"]
    cards = f"""
    <div class="cards">
      <div class="card"><div class="label">Tentativi-chunk</div><div class="value">{t['chunk_attempts']}</div></div>
      <div class="card"><div class="label">OK-rate</div><div class="value">{t['ok_rate']}%</div></div>
      <div class="card"><div class="label">Throughput p50</div><div class="value">{t['thr_kbs_p50']} KB/s</div></div>
      <div class="card"><div class="label">Tempo produttivo</div><div class="value">{dec['productive_pct']}%</div></div>
      <div class="card"><div class="label">Corsie effettive</div><div class="value">{par.get('effective_lanes') if par.get('effective_lanes') is not None else 'n/d'} / {par.get('nominal_lanes')}</div></div>
      <div class="card"><div class="label">Sessioni</div><div class="value">{R['n_sessions']}</div></div>
    </div>
    """

    cfg_rows = [
        ["Versione app", R.get("app_version")],
        ["Sessioni", ", ".join(str(s) for s in R["session_ids"])],
        ["Chunk size", f"{R['chunk_size_mb']} MB"],
        ["Connessioni/file", R.get("connections")],
        ["Selezione", R.get("selection_mode")],
        ["Link", R.get("n_links")],
    ]

    dec_rows = [
        ["Tempo totale tentativi", f"{dec['attempt_time_s']} s"],
        ["Trasferimento produttivo", f"{dec['productive_transfer_s']} s ({dec['productive_pct']}%)"],
        ["Tentativi falliti", f"{dec['failed_attempt_s']} s ({dec['failed_pct']}%)"],
        ["Backoff dichiarato", f"{dec['backoff_declared_s']} s"],
    ]

    par_rows = [
        ["Aggregato p50", f"{par['aggregate_bps_p50_kbs']} KB/s"],
        ["Per-chunk p50", f"{par['per_chunk_bps_p50_kbs']} KB/s"],
        ["Corsie effettive", par.get("effective_lanes")],
        ["Corsie nominali", par.get("nominal_lanes")],
    ]

    def _roll_rows(rs):
        return [[r["key"], r["attempts"], r["ok"], f"{r['ok_rate']}%",
                 r["thr_kbs_p50"], r["thr_kbs_p90"], r["thr_kbs_p99"]] for r in rs]

    roll_head = ["Chiave", "Tent.", "OK", "OK-rate", "p50 KB/s", "p90", "p99"]

    fast = sorted([p for p in R["by_proxy_top"] if p["ok"] > 0],
                  key=lambda x: -x["thr_kbs_p50"])[:10]
    slow = sorted([p for p in R["by_proxy_top"] if p["ok"] > 0],
                  key=lambda x: x["thr_kbs_p50"])[:10]

    file_rows = [[f["session_id"], f["file_id"], f["size_mb"], f["wall_s"],
                  f["eff_mbs"], f["idle_samples_pct"], f["straggler_chunks"],
                  f["straggler_wall_pct"], ", ".join(f["tail_sources"])]
                 for f in R["per_file"]]

    waste_rows = [[w["outcome"], w["attempts"], w["wasted_s"]] for w in R["waste_by_category"]]
    rl = R["rate_limit"]
    rl_rows = [[x["key"], x["count"]] for x in rl["by_ip_top"]]

    recs = "".join(f"<li>{html.escape(r)}</li>" for r in R["recommendations"])

    # Sezione "Verso la banda massima": utilizzo linea, corsie attive, vincolo.
    bw = R.get("bandwidth", {})
    if bw.get("available"):
        band_rows = []
        if R.get("link_capacity_mbit"):
            band_rows.append(["Capacita' linea", f"{R['link_capacity_mbit']} Mbit/s"])
        if bw.get("util_p50") is not None:
            band_rows += [
                ["Utilizzo mediano", f"{round(bw['util_p50'] * 100)}%"],
                ["Utilizzo p90", f"{round(bw['util_p90'] * 100)}%"],
                ["Utilizzo massimo", f"{round(bw['util_max'] * 100)}%"],
                ["Headroom alla linea", f"{round((1 - bw['util_p50']) * 100)}% (mediano)"],
                ["Tempo sopra l'85%", f"{bw.get('pct_time_over_85', 0)}%"],
            ]
        else:
            band_rows.append(["Utilizzo linea", "n/d (capacita' non misurata) — usa --link-mbit"])
        band_rows += [
            ["Corsie attive p50", f"{bw.get('active_lanes_p50')} / {bw.get('nominal_lanes')}"],
            ["Corsie attive p90", f"{bw.get('active_lanes_p90')} / {bw.get('nominal_lanes')}"],
            ["Vincolo dominante", bw.get("dominant_binding") or "n/d"],
        ]
        states = bw.get("binding_states_pct", {})
        binding_rows = [[k, f"{v}%"] for k, v in states.items()]
        band_section = (
            "<h2>Verso la banda massima</h2>"
            + _table(["Metrica", "Valore"], band_rows)
            + "<h3 style='color:#9aa1ad;font-size:.95rem'>Ripartizione del vincolo (per secondo)</h3>"
            + _table(["Stato", "% tempo"], binding_rows)
        )
    else:
        band_section = (
            "<h2>Verso la banda massima</h2>"
            '<div class="empty">Nessun campione: sezione non disponibile.</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Analisi telemetria — Mega Downloader Proxy Rotator</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Analisi telemetria</h1>
<div class="subtitle">Generato il {html.escape(generated_at)} da tools/analyze_telemetry.py — sola lettura.</div>

{cards}

<h2>Configurazione della run</h2>
{_table(["Parametro", "Valore"], cfg_rows)}

<h2>Raccomandazioni</h2>
<ul class="recs">{recs}</ul>

{band_section}

<h2>Decomposizione del tempo</h2>
{_table(["Voce", "Valore"], dec_rows)}

<h2>Parallelismo effettivo</h2>
{_table(["Metrica", "Valore"], par_rows)}

<h2>Throughput nel tempo</h2>
<div class="chart-wrap">{_svg_line_throughput(sm, R.get("link_capacity_bps"))}</div>

<h2>Distribuzione esiti</h2>
<div class="chart-wrap">{_svg_outcomes(R['outcomes'])}</div>

<h2>Throughput per proxy</h2>
<div class="chart-wrap">{_svg_hist_proxy_throughput(R['by_proxy_top'])}</div>

<h2>Per fonte</h2>
{_table(roll_head, _roll_rows(R['by_source']))}

<h2>Per protocollo</h2>
{_table(roll_head, _roll_rows(R['by_protocol']))}

<h2>Proxy piu' veloci</h2>
{_table(roll_head, _roll_rows(fast))}

<h2>Proxy piu' lenti</h2>
{_table(roll_head, _roll_rows(slow))}

<h2>IP uscenti (top per tentativi)</h2>
{_table(roll_head, _roll_rows(R['by_ip_top']))}

<h2>Spreco per categoria</h2>
{_table(["Esito", "Tentativi", "Secondi persi"], waste_rows)}

<h2>Rate-limit per IP</h2>
{_table(["IP uscente", "403/509"], rl_rows)}

<h2>Per file (wall-clock e stragglers)</h2>
{_table(["Sessione", "File", "MB", "Wall s", "Eff MB/s", "Idle %", "Stragglers", "Coda %wall", "Fonti coda"], file_rows)}

<footer>MDPR — analisi telemetria generata localmente, sola lettura.</footer>
</body>
</html>
"""


# === Report Markdown =======================================================

def render_md(R: dict) -> str:
    t = R["totals"]
    dec = R["decomposition"]
    par = R["parallelism"]
    lines = [
        f"# Analisi telemetria MDPR",
        "",
        f"- Sessioni: {', '.join(str(s) for s in R['session_ids'])}",
        f"- Versione app: {R.get('app_version')}",
        f"- Chunk {R['chunk_size_mb']} MB · {R.get('connections')} connessioni · "
        f"selezione {R.get('selection_mode')} · {R.get('n_links')} link",
        "",
        "## Totali",
        f"- Tentativi-chunk: {t['chunk_attempts']} (OK {t['ok']}, ok-rate {t['ok_rate']}%)",
        f"- Throughput KB/s: p10 {t['thr_kbs_p10']} · p50 {t['thr_kbs_p50']} · "
        f"p90 {t['thr_kbs_p90']} · p99 {t['thr_kbs_p99']}",
        "",
        "## Decomposizione del tempo",
        f"- Tempo tentativi: {dec['attempt_time_s']}s",
        f"- Produttivo: {dec['productive_transfer_s']}s ({dec['productive_pct']}%)",
        f"- Falliti: {dec['failed_attempt_s']}s ({dec['failed_pct']}%)",
        f"- Backoff dichiarato: {dec['backoff_declared_s']}s",
        "",
        "## Parallelismo effettivo",
        f"- Aggregato p50: {par['aggregate_bps_p50_kbs']} KB/s",
        f"- Per-chunk p50: {par['per_chunk_bps_p50_kbs']} KB/s",
        f"- Corsie effettive: {par.get('effective_lanes')} / {par.get('nominal_lanes')} nominali",
        "",
    ]
    bw = R.get("bandwidth", {})
    if bw.get("available"):
        lines.append("## Verso la banda massima")
        if R.get("link_capacity_mbit"):
            lines.append(f"- Capacita' linea: {R['link_capacity_mbit']} Mbit/s")
        if bw.get("util_p50") is not None:
            lines.append(
                f"- Utilizzo linea: mediano {round(bw['util_p50'] * 100)}% · "
                f"p90 {round(bw['util_p90'] * 100)}% · max {round(bw['util_max'] * 100)}% · "
                f"sopra 85% nel {bw.get('pct_time_over_85', 0)}% del tempo"
            )
        lines.append(
            f"- Corsie attive: p50 {bw.get('active_lanes_p50')} / "
            f"{bw.get('nominal_lanes')} nominali"
        )
        lines.append(f"- Vincolo dominante: {bw.get('dominant_binding')}")
        for k, v in bw.get("binding_states_pct", {}).items():
            lines.append(f"  - {k}: {v}%")
        lines.append("")
    lines.append("## Esiti")
    for k, v in sorted(R["outcomes"].items(), key=lambda x: -(x[1] or 0)):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Raccomandazioni"]
    for r in R["recommendations"]:
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


# === Export AI =============================================================

_SCHEMA_HINT = {
    "chunk_attempt": "un record per TENTATIVO di scaricare un chunk; outcome in "
                     "{ok,http_403,http_509,http_503,timeout_read,timeout_connect,"
                     "slow_killed,budget_exceeded,size_mismatch,range_ignored,"
                     "conn_error,aborted_local,cancelled,retries_exhausted,other}; "
                     "throughput_bps=byte/s sul trasferimento; t_*_ms=tappe di timing.",
    "totals": "percentili throughput in KB/s sui soli OK.",
    "decomposition": "ripartizione del wall-clock dei tentativi: produttivo vs perso.",
    "parallelism": "effective_lanes = aggregato_p50 / per_chunk_p50: corsie davvero piene.",
    "rate_limit": "403/509 = rate-limit per IP del proxy (temporaneo, cooldown).",
    "per_file": "wall-clock reale, efficienza MB/s, % campioni idle, coda di stragglers.",
    "bandwidth": "util_* = frazione della linea usata (instant_bps aggregato / "
                 "link_capacity_bps); active_lanes = tentativi sovrapposti nel tempo; "
                 "binding_states_pct = % tempo per vincolo {line_bound,rate_limit_bound,"
                 "pool_bound,lane_supply_bound,proxy_speed_bound}; e' la leva da tirare.",
}


def _pick_examples(ca: list[dict]) -> list[dict]:
    def trim(r):
        r = dict(r)
        r.pop("intra_samples", None)
        if r.get("error"):
            r["error"] = str(r["error"])[:160]
        return r
    ok = [r for r in ca if r.get("outcome") == "ok" and _num(r.get("throughput_bps"))]
    examples = []
    if ok:
        fast = max(ok, key=lambda r: r["throughput_bps"])
        slow = min(ok, key=lambda r: r["throughput_bps"])
        examples += [trim(fast), trim(slow)]
    rl = next((r for r in ca if r.get("outcome") in ("http_403", "http_509")), None)
    if rl:
        examples.append(trim(rl))
    sk = next((r for r in ca if r.get("outcome") == "slow_killed"), None)
    if sk:
        examples.append(trim(sk))
    to = next((r for r in ca if r.get("outcome") in ("timeout_read", "timeout_connect")), None)
    if to and len(examples) < 5:
        examples.append(trim(to))
    return examples[:5]


_AI_BUDGET = 15000


def write_ai_export(out: Path, R: dict, ca: list[dict]) -> int:
    summary = {
        k: R[k] for k in (
            "session_ids", "n_sessions", "app_version", "chunk_size_mb",
            "connections", "selection_mode", "n_links", "link_capacity_mbit",
            "totals", "outcomes", "decomposition", "parallelism", "rate_limit",
            "re_resolve", "pool_empty", "waste_by_category", "bandwidth",
            "by_source", "by_protocol", "per_file", "resume_check",
            "recommendations",
        )
    }
    summary["by_proxy_top"] = list(R["by_proxy_top"])
    summary["by_ip_top"] = list(R["by_ip_top"])

    def build():
        payload = {"schema_hint": _SCHEMA_HINT, "summary": summary,
                   "examples": _pick_examples(ca)}
        return json.dumps(payload, ensure_ascii=False, indent=1, default=str)

    text = build()
    # Sfoltisce progressivamente le liste piu' voluminose finche' non rientra
    # nel budget (l'AI ragiona sul distillato + esempi, non sulle code lunghe).
    caps = [("by_proxy_top", 8), ("by_ip_top", 8), ("by_source", 12),
            ("by_proxy_top", 5), ("by_ip_top", 5), ("per_file", 10),
            ("by_source", 6), ("by_proxy_top", 3), ("by_ip_top", 3)]
    ci = 0
    while len(text.encode("utf-8")) > _AI_BUDGET and ci < len(caps):
        key, n = caps[ci]
        summary[key] = summary[key][:n]
        text = build()
        ci += 1
    path = out / "telemetry_ai_export.json"
    # newline="\n": evita la traduzione CRLF su Windows, cosi' la dimensione su
    # disco coincide col budget contato (e resta < ~15 KB).
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    return path.stat().st_size


# === CLI ===================================================================

def _default_out() -> Path:
    root = Path(__file__).resolve().parents[1]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root / "logs" / "reports" / "telemetry" / ts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_telemetry",
        description="Analizza la telemetria scatola nera (sola lettura): CSV + report HTML + export AI.",
    )
    parser.add_argument(
        "path", type=Path,
        help="Cartella sessione (logs/telemetry/<id>) o cartella padre (logs/telemetry/).",
    )
    parser.add_argument("--out", type=Path, default=None,
                        help="Cartella di output (default: logs/reports/telemetry/<timestamp>/).")
    parser.add_argument("--firehose", action="store_true",
                        help="Esplode anche intra_samples in intra_samples_long.csv (grande).")
    parser.add_argument("--link-mbit", type=float, default=None,
                        help="Capacita' linea (Mbit/s) come override/fallback se assente nel manifest.")
    args = parser.parse_args(argv)

    session_dirs = discover_sessions(args.path)
    if not session_dirs:
        print(f"Nessuna sessione di telemetria trovata in: {args.path}", file=sys.stderr)
        return 1

    manifests, ca, ev, sm = load_sessions(session_dirs)
    if not ca and not sm:
        print(f"Sessione(i) trovate ma senza dati (events/samples vuoti): {args.path}",
              file=sys.stderr)
        # Non e' un errore fatale: scrivo comunque output minimo.

    link_bps = int(args.link_mbit * 1_000_000 / 8) if args.link_mbit else None
    R = analyze(manifests, ca, ev, sm, link_capacity_bps=link_bps)

    out: Path = args.out if args.out is not None else _default_out()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Errore: impossibile creare {out}: {exc}", file=sys.stderr)
        return 1

    write_datasets(out, R, ca, sm)
    generated_at = datetime.now().isoformat(timespec="seconds")
    (out / "telemetry_report.html").write_text(
        render_html(R, generated_at, sm), encoding="utf-8")
    (out / "telemetry_report.md").write_text(render_md(R), encoding="utf-8")
    ai_bytes = write_ai_export(out, R, ca)
    firehose_rows = write_firehose(out, session_dirs) if args.firehose else 0

    print(f"Output scritto in: {out}")
    print(f"Sessioni: {R['n_sessions']} | tentativi-chunk: {R['totals']['chunk_attempts']} "
          f"| ok-rate: {R['totals']['ok_rate']}% | campioni: {len(sm)}")
    print(f"Throughput p50: {R['totals']['thr_kbs_p50']} KB/s | "
          f"produttivo: {R['decomposition']['productive_pct']}% | "
          f"corsie effettive: {R['parallelism'].get('effective_lanes')}/{R['parallelism'].get('nominal_lanes')}")
    bw = R.get("bandwidth", {})
    if bw.get("available"):
        util = (f"util p50 {round(bw['util_p50'] * 100)}%"
                if bw.get("util_p50") is not None else "util n/d (usa --link-mbit)")
        print(f"Banda: {util} | corsie attive p50 {bw.get('active_lanes_p50')}"
              f"/{bw.get('nominal_lanes')} | vincolo {bw.get('dominant_binding')}")
    print(f"AI export: {ai_bytes} byte" + (f" | firehose: {firehose_rows} righe" if args.firehose else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
