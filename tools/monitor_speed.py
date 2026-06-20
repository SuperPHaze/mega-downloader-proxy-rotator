# Monitor di velocita' di download per Mega Proxy Downloader.
#
# Standalone: non importa nulla dall'app, non interferisce con la GUI in esecuzione.
# Polla la cartella ./downloads/ a intervalli regolari e calcola la velocita'
# come delta di byte (somma ricorsiva delle dimensioni dei file) / delta tempo.
#
# Uso (dalla root del progetto, con il venv attivo):
#   .\venv\Scripts\python.exe -m tools.monitor_speed
#   .\venv\Scripts\python.exe -m tools.monitor_speed --interval 0.5 --dir ./downloads
#
# Mostra per ogni intervallo:
#   - velocita' istantanea totale (somma di tutti i cicli/file)
#   - velocita' per ciclo attivo (ogni cartella ciclo_N che cresce)
#   - totale scaricato dall'avvio del monitor
from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def human_bytes(n: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.2f} {units[i]}"


def human_speed(bytes_per_sec: float) -> str:
    return f"{human_bytes(bytes_per_sec)}/s"


def scan_mega_temp(temp_dir: Path, max_age_seconds: float = 30.0) -> dict[Path, dict]:
    # mega.py 1.0.8 scrive il file in download in `tempfile.NamedTemporaryFile`
    # con prefix `megapy_`, che finisce in %TEMP% (NON in output_dir).
    # Solo a fine download fa shutil.move verso downloads/... .
    # Quindi durante il download i byte crescono qui, non nella cartella ciclo.
    # Filtriamo per mtime recente per ignorare i leftover di run vecchie.
    out: dict[Path, dict] = {}
    if not temp_dir.is_dir():
        return out
    now = time.time()
    try:
        for p in temp_dir.glob("megapy_*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            age = now - st.st_mtime
            out[p] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
                "age_s": age,
                "recent": age <= max_age_seconds,
            }
    except OSError:
        pass
    return out


def scan_detailed(root: Path) -> dict[Path, dict]:
    # Mappa "cartella ciclo_N" -> dict con:
    #   total: byte totali nella cartella
    #   files: { nome_file: { size, mtime, is_temp } }
    # Cosi' il log puo' tracciare l'evoluzione di ogni singolo file.
    out: dict[Path, dict] = {}
    if not root.is_dir():
        return out
    for file_dir in root.iterdir():
        if not file_dir.is_dir():
            continue
        for cycle_dir in file_dir.iterdir():
            if not cycle_dir.is_dir():
                continue
            files: dict[str, dict] = {}
            total = 0
            try:
                for p in cycle_dir.iterdir():
                    if p.is_file():
                        try:
                            st = p.stat()
                            files[p.name] = {
                                "size": st.st_size,
                                "mtime": st.st_mtime,
                                "is_temp": p.name.startswith("megapy_"),
                            }
                            total += st.st_size
                        except OSError as exc:
                            files[p.name] = {"size": 0, "mtime": 0, "is_temp": False, "error": str(exc)}
            except OSError as exc:
                out[cycle_dir] = {"total": 0, "files": {}, "scan_error": str(exc)}
                continue
            out[cycle_dir] = {"total": total, "files": files}
    return out


def scan_sizes_from_detailed(detailed: dict[Path, dict]) -> dict[Path, int]:
    return {k: v.get("total", 0) for k, v in detailed.items()}


def relpath(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor velocita' download Mega Proxy Downloader")
    parser.add_argument("--dir", default="./downloads", help="Cartella radice dei download (default: ./downloads)")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervallo di campionamento in secondi (default: 1.0)")
    parser.add_argument("--quiet-idle", action="store_true", help="Non stampare righe quando nessun ciclo sta crescendo")
    parser.add_argument("--log-file", default="./monitor_speed.log", help="File di log dettagliato (default: ./monitor_speed.log)")
    parser.add_argument("--jsonl", default="./monitor_speed.jsonl", help="File JSONL con uno snapshot per riga (default: ./monitor_speed.jsonl)")
    parser.add_argument("--duration", type=float, default=0.0, help="Esce automaticamente dopo N secondi (0 = mai)")
    parser.add_argument("--temp-dir", default=tempfile.gettempdir(), help="Cartella temp di mega.py (default: %%TEMP%% del sistema)")
    parser.add_argument("--temp-max-age", type=float, default=30.0, help="Eta' massima (s) dei file megapy_* per considerarli 'attivi' (default: 30)")
    args = parser.parse_args()

    temp_dir = Path(args.temp_dir).resolve()

    log_path = Path(args.log_file).resolve()
    jsonl_path = Path(args.jsonl).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger("monitor_speed")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)
    jsonl_fp = open(jsonl_path, "a", encoding="utf-8")

    root = Path(args.dir).resolve()
    interval = max(0.1, float(args.interval))

    print(f"[monitor] watching {root}  +  mega-temp in {temp_dir}  interval={interval}s")
    print(f"[monitor] log={log_path}  jsonl={jsonl_path}")
    if args.duration > 0:
        print(f"[monitor] auto-stop fra {args.duration}s")
    else:
        print("[monitor] Ctrl+C per uscire")
    if not root.exists():
        print(f"[monitor] attenzione: {root} non esiste ancora — verra' creata quando partira' il primo download.")

    log.info("=" * 70)
    log.info("monitor avviato pid=%d root=%s temp=%s interval=%.3fs duration=%.1fs",
             os.getpid(), root, temp_dir, interval, args.duration)
    log.info("root_exists=%s temp_exists=%s cwd=%s", root.exists(), temp_dir.exists(), os.getcwd())

    prev_detailed = scan_detailed(root)
    prev = scan_sizes_from_detailed(prev_detailed)
    prev_temp = scan_mega_temp(temp_dir, args.temp_max_age)
    baseline_total = sum(prev.values())
    log.info("snapshot temp iniziale: %d file megapy_* trovati, %d recenti (<= %.0fs)",
             len(prev_temp), sum(1 for v in prev_temp.values() if v["recent"]), args.temp_max_age)
    for p, meta in prev_temp.items():
        if meta["recent"]:
            log.info("  TEMP attivo init: %s size=%dB age=%.1fs", p.name, meta["size"], meta["age_s"])
    log.info("snapshot iniziale: cicli=%d baseline_bytes=%d", len(prev), baseline_total)
    for cycle_dir, info in prev_detailed.items():
        log.debug("  init cycle=%s total=%d files=%d", cycle_dir, info["total"], len(info.get("files", {})))
        for fname, fmeta in info.get("files", {}).items():
            log.debug("    file=%s size=%d temp=%s", fname, fmeta.get("size", 0), fmeta.get("is_temp"))

    start_time = time.monotonic()
    last_time = start_time
    tick = 0
    peak_inst = 0.0
    sum_inst = 0.0
    n_inst = 0

    stop_reason = "ctrl-c"
    try:
        while True:
            if args.duration > 0 and (time.monotonic() - start_time) >= args.duration:
                stop_reason = "duration-reached"
                break
            time.sleep(interval)
            now = time.monotonic()
            dt = now - last_time
            last_time = now
            tick += 1

            curr_detailed = scan_detailed(root)
            curr = scan_sizes_from_detailed(curr_detailed)
            curr_total = sum(curr.values())
            curr_temp = scan_mega_temp(temp_dir, args.temp_max_age)

            # Delta per ciclo: somma solo gli incrementi positivi.
            per_cycle_delta: list[tuple[Path, int]] = []
            for cycle_dir, size in curr.items():
                old = prev.get(cycle_dir, 0)
                delta = size - old
                if delta > 0:
                    per_cycle_delta.append((cycle_dir, delta))

            # Delta dei file megapy_* in %TEMP%: e' qui che mega.py scrive
            # durante il download (poi shutil.move verso downloads/...).
            per_temp_delta: list[tuple[Path, int, int]] = []  # (path, delta, size)
            for p, meta in curr_temp.items():
                old_size = prev_temp.get(p, {}).get("size", 0) if p in prev_temp else 0
                delta = meta["size"] - old_size
                if delta > 0:
                    per_temp_delta.append((p, delta, meta["size"]))
            temp_delta_sum = sum(d for _, d, _ in per_temp_delta)

            # Cicli scomparsi (cleanup di temp) e nuovi (primo file appena creato).
            removed = [c for c in prev if c not in curr]
            added = [c for c in curr if c not in prev]

            # La velocita' "reale" e' la somma: cresce il temp durante il
            # download, poi al move sparisce dal temp e appare in ciclo (delta
            # nullo netto). Sommarli evita doppio conteggio nel singolo tick:
            # NON sommiamo il delta della cartella ciclo se nello stesso istante
            # un temp ha appena perso quei byte. Approssimazione semplice:
            # usiamo max(cycle_delta, temp_delta) per ciascun "stream".
            total_delta = sum(d for _, d in per_cycle_delta) + temp_delta_sum
            inst_speed = total_delta / dt if dt > 0 else 0.0

            cumulative = curr_total - baseline_total
            elapsed = now - start_time
            avg_speed = cumulative / elapsed if elapsed > 0 else 0.0

            if inst_speed > peak_inst:
                peak_inst = inst_speed
            if inst_speed > 0:
                sum_inst += inst_speed
                n_inst += 1

            # Log dettagliato (sempre, anche se idle).
            n_temp_recent = sum(1 for v in curr_temp.values() if v["recent"])
            log.info(
                "tick=%d dt=%.3fs inst=%.1fB/s avg=%.1fB/s cumulative=%dB on_disk=%dB cicli_attivi=%d temp_attivi=%d/%d temp_delta=%dB",
                tick, dt, inst_speed, avg_speed, cumulative, curr_total,
                len(per_cycle_delta), n_temp_recent, len(curr_temp), temp_delta_sum,
            )
            for p, delta, size in sorted(per_temp_delta, key=lambda x: -x[1]):
                speed = delta / dt if dt > 0 else 0.0
                log.info("  ~TEMP=%s delta=%dB speed=%.1fB/s size=%dB", p.name, delta, speed, size)
            for cycle_dir, delta in sorted(per_cycle_delta, key=lambda x: -x[1]):
                speed = delta / dt if dt > 0 else 0.0
                log.info(
                    "  +cycle=%s delta=%dB speed=%.1fB/s size=%dB",
                    relpath(cycle_dir, root), delta, speed, curr.get(cycle_dir, 0),
                )
                # Per-file delta dentro il ciclo.
                old_files = prev_detailed.get(cycle_dir, {}).get("files", {})
                new_files = curr_detailed.get(cycle_dir, {}).get("files", {})
                for fname, fmeta in new_files.items():
                    old_size = old_files.get(fname, {}).get("size", 0)
                    new_size = fmeta.get("size", 0)
                    fdelta = new_size - old_size
                    if fdelta > 0 or fname not in old_files:
                        log.debug(
                            "      file=%s size=%dB delta=%dB temp=%s mtime=%s",
                            fname, new_size, fdelta, fmeta.get("is_temp"),
                            datetime.fromtimestamp(fmeta.get("mtime", 0)).isoformat(timespec="milliseconds")
                            if fmeta.get("mtime") else "n/a",
                        )
                for fname in old_files:
                    if fname not in new_files:
                        log.debug("      file=%s RIMOSSO (era %dB)", fname, old_files[fname].get("size", 0))
            for cycle_dir in added:
                log.info("  *new cycle apparso=%s size=%dB files=%d",
                         relpath(cycle_dir, root), curr.get(cycle_dir, 0),
                         len(curr_detailed.get(cycle_dir, {}).get("files", {})))
            for cycle_dir in removed:
                log.info("  -cycle scomparso=%s (era %dB)", relpath(cycle_dir, root), prev.get(cycle_dir, 0))

            # JSONL: uno snapshot per riga, parseable.
            snapshot = {
                "tick": tick,
                "ts": datetime.now().isoformat(timespec="milliseconds"),
                "elapsed_s": round(elapsed, 3),
                "dt_s": round(dt, 3),
                "inst_bps": round(inst_speed, 2),
                "avg_bps": round(avg_speed, 2),
                "cumulative_bytes": cumulative,
                "on_disk_bytes": curr_total,
                "active_cycles": len(per_cycle_delta),
                "total_cycles": len(curr),
                "cycles": {
                    relpath(c, root): {
                        "total": info.get("total", 0),
                        "files": {fn: fm.get("size", 0) for fn, fm in info.get("files", {}).items()},
                    } for c, info in curr_detailed.items()
                },
                "added_cycles": [relpath(c, root) for c in added],
                "removed_cycles": [relpath(c, root) for c in removed],
                "temp_delta_bytes": temp_delta_sum,
                "temp_active": [
                    {"name": p.name, "size": meta["size"], "age_s": round(meta["age_s"], 2)}
                    for p, meta in curr_temp.items() if meta["recent"]
                ],
            }
            jsonl_fp.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
            jsonl_fp.flush()

            if not per_cycle_delta and not per_temp_delta and args.quiet_idle:
                prev = curr
                prev_detailed = curr_detailed
                prev_temp = curr_temp
                continue

            ts = time.strftime("%H:%M:%S")
            print(
                f"[{ts}] tot={human_speed(inst_speed):>12}  "
                f"avg={human_speed(avg_speed):>12}  "
                f"sessione={human_bytes(cumulative):>10}  "
                f"cicli={len(per_cycle_delta)}  temp={len(per_temp_delta)}/{n_temp_recent}"
            )
            for cycle_dir, delta in sorted(per_cycle_delta, key=lambda x: -x[1]):
                speed = delta / dt if dt > 0 else 0.0
                print(
                    f"           [ciclo] {relpath(cycle_dir, root):<34} "
                    f"{human_speed(speed):>12}  size={human_bytes(curr.get(cycle_dir, 0))}"
                )
            for p, delta, size in sorted(per_temp_delta, key=lambda x: -x[1]):
                speed = delta / dt if dt > 0 else 0.0
                print(
                    f"           [temp]  {p.name:<34} "
                    f"{human_speed(speed):>12}  size={human_bytes(size)}"
                )

            prev = curr
            prev_detailed = curr_detailed
            prev_temp = curr_temp
    except KeyboardInterrupt:
        stop_reason = "ctrl-c"

    elapsed = time.monotonic() - start_time
    final_detailed = scan_detailed(root)
    final_total_on_disk = sum(scan_sizes_from_detailed(final_detailed).values())
    total = final_total_on_disk - baseline_total
    avg = total / elapsed if elapsed > 0 else 0.0
    mean_active_inst = (sum_inst / n_inst) if n_inst else 0.0
    summary = (
        f"durata={elapsed:.2f}s tick={tick} stop={stop_reason} "
        f"scaricato_sessione={total}B media={avg:.1f}B/s "
        f"peak_inst={peak_inst:.1f}B/s media_solo_attivi={mean_active_inst:.1f}B/s "
        f"cicli_finali={len(final_detailed)}"
    )
    log.info("FINE: %s", summary)
    jsonl_fp.write(json.dumps({"event": "stop", "summary": summary}) + "\n")
    jsonl_fp.close()
    print()
    print(f"[monitor] stop ({stop_reason}). durata={elapsed:.1f}s  scaricato={human_bytes(total)}  media={human_speed(avg)}  peak={human_speed(peak_inst)}")
    print(f"[monitor] log: {log_path}")
    print(f"[monitor] jsonl: {jsonl_path}")


if __name__ == "__main__":
    main()
