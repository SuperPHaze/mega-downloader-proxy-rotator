# Downloader Mega multi-connessione con coda di chunk HTTP Range parallele.
#
# Perche' esiste: mega.py 1.0.8 scarica un file in modo monolitico e seriale,
# il throughput e' limitato dalla velocita' del singolo proxy in uso. Qui
# usiamo mega.py SOLO per risolvere il link pubblico (parse URL + chiave AES
# + API request `g=1` -> URL CDN + size + filename cifrato), poi eseguiamo N
# download paralleli di chunk a dimensione FISSA (default 8 MB ciascuno),
# ognuno instradato su un proxy diverso. Un cambio proxy fa perdere al
# massimo un chunk, non N/4 di file come con i segmenti grandi.
#
# Limiti noti:
# - I chunk vanno allineati a 16 byte (block size AES). Forzato in _split_chunks.
# - La verifica MAC del file non viene fatta (richiederebbe un pass seriale
#   sull'intero file). Confidiamo nella correttezza dei chunk CDN.
# - Se mega.py cambia API privata (_parse_url, _api_request, crypto helpers)
#   il client si rompe in modo esplicito.
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

import requests

from src.core import telemetry
from src.core.config import (
    PARALLEL_CHUNK_SIZE_MB,
    PARALLEL_HTTP_429_BACKOFF_MAX_S,
    PARALLEL_HTTP_429_BACKOFF_S,
    PARALLEL_MAX_FAILED_CHUNKS,
    PARALLEL_MIN_SEGMENT_BYTES,
    PARALLEL_MIN_THROUGHPUT_BPS,
    PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S,
    PARALLEL_SEGMENT_BACKOFF_MAX,
    PARALLEL_SEGMENT_RETRIES,
    PARALLEL_THROUGHPUT_GRACE,
    PARALLEL_THROUGHPUT_WINDOW,
    PROXY_CONNECT_TIMEOUT,
    PROXY_READ_TIMEOUT,
    PROXY_TIMEOUT,
    TELEMETRY_INTRA_CHUNK_MAX_SAMPLES,
    TELEMETRY_SAMPLE_INTERVAL_S,
    USER_AGENT,
)
from src.core.proxy_url import build_proxies_dict as _proxies_dict
from src.core.state import SessionState
from src.downloader.mega_api import MegaPublicClient
from src.downloader.mega_crypto import a32_to_str
from src.downloader.mega_client import MegaCryptoDependencyError
from src.proxy.pool import ProxyPool

log = logging.getLogger(__name__)


def _progress_path(target_path: Path) -> Path:
    # Sidecar accanto al file a cui si riferisce (nello schema corrente: il .part).
    return target_path.with_name(target_path.name + ".progress.json")


def _load_progress(
    target_path: Path,
    file_handle: str,
    file_size: int,
    chunk_size: int,
) -> set[tuple[int, int]]:
    """Carica i (start, end) gia' scaricati dalla run precedente.

    Invalida il sidecar se file_handle, file_size O chunk_size non corrispondono.
    Con chunk_size fisso il resume e' valido indipendentemente dal numero di
    connessioni N: cambiare N non rende incompatibili i chunk gia' scaricati
    (al contrario dei vecchi segmenti proporzionali a N).
    """
    p = _progress_path(target_path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if (data.get("file_handle") != file_handle
                or data.get("file_size") != file_size
                or data.get("chunk_size") != chunk_size):
            log.info(
                "[parallel] sidecar invalido (handle/size/chunk_size diversi), ignoro"
            )
            return set()
        done = {(int(s), int(e)) for s, e in data.get("done", [])}
        log.info("[parallel] resume: %d chunk gia' scaricati da run precedente", len(done))
        return done
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        log.warning("[parallel] sidecar non leggibile (%s), ignoro", exc)
        return set()


def _save_progress(
    target_path: Path,
    file_handle: str,
    file_size: int,
    done: set[tuple[int, int]],
    chunk_size: int,
) -> None:
    p = _progress_path(target_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    payload = {
        "file_handle": file_handle,
        "file_size": file_size,
        "chunk_size": chunk_size,
        "done": sorted([list(t) for t in done]),
    }
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, p)
    except OSError as exc:
        log.warning("[parallel] non posso salvare progress sidecar: %s", exc)


def _align_down(n: int, block: int = 16) -> int:
    return (n // block) * block


def _split_chunks(file_size: int, chunk_size: int) -> list[tuple[int, int]]:
    """Suddivide file_size in range di dimensione fissa (chunk_size byte ognuno).

    chunk_size viene arrotondato a multiplo di 16 (block AES).
    L'ultimo chunk puo' essere piu' corto. Per file piccoli restituisce un solo chunk.
    Ogni chunk completato viene salvato subito nel sidecar: un cambio proxy fa
    perdere al massimo un chunk, non un quarto di file.
    """
    chunk_size = max(16, _align_down(chunk_size, 16))
    if file_size <= PARALLEL_MIN_SEGMENT_BYTES:
        return [(0, file_size - 1)]
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < file_size:
        end = min(start + chunk_size - 1, file_size - 1)
        chunks.append((start, end))
        start = end + 1
    return chunks


class ParallelMegaDownloader:
    def __init__(
        self,
        proxy_pool: ProxyPool,
        n_connections: int,
        session_state: SessionState | None = None,
        chunk_size: int | None = None,
        segment_max_duration_s: int | None = None,
    ) -> None:
        self.pool = proxy_pool
        self.n_connections = max(1, n_connections)
        self.session_state = session_state
        # Dimensione di ogni chunk in byte (multiplo di 16, block AES).
        # Default dalla costante di configurazione se non specificato dalla GUI.
        self.chunk_size = (
            chunk_size
            if chunk_size is not None
            else PARALLEL_CHUNK_SIZE_MB * 1024 * 1024
        )
        # Budget temporale massimo per un singolo tentativo di chunk.
        # Default dalla costante di configurazione se non specificato dalla GUI.
        self.segment_max_duration_s = (
            segment_max_duration_s
            if segment_max_duration_s is not None
            else PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S
        )
        self._bytes_downloaded = 0
        self._bytes_lock = threading.Lock()
        # Abort LOCALE: settato quando PARALLEL_MAX_FAILED_CHUNKS chunk hanno
        # esaurito TUTTI i retry. NON tocchiamo session_state (globale).
        self._abort = threading.Event()
        # Lock per il re-resolve CDN (thread-safe, solo il primo thread esegue).
        self._cdn_lock = threading.Lock()
        # Contatori chunk per la logica di abort soft.
        self._n_chunks = 0
        self._failed_chunks = 0
        self._failed_lock = threading.Lock()

    def download(
        self,
        mega_url: str,
        output_dir: Path,
        resolver_proxy: dict,
        progress_callback: Callable[[int], None] | None = None,
        ip_callback: Callable[[str, int], None] | None = None,
        speed_callback: Callable[[float, int, int], None] | None = None,
        resolved_callback: Callable[[str, object, "Path"], None] | None = None,
        file_id: int | None = None,
    ) -> Path:
        """Scarica un link Mega in parallelo usando una coda di chunk a dimensione fissa.

        `resolver_proxy` viene usato solo per la fase di resolve URL; i chunk
        useranno proxy prelevati dal pool. Lancia eccezioni se il resolve fallisce
        o se PARALLEL_MAX_FAILED_CHUNKS chunk esauriscono tutti i retry.
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Util import Counter
        except ImportError as exc:
            raise MegaCryptoDependencyError(f"pycryptodome mancante ({exc})") from exc

        output_dir.mkdir(parents=True, exist_ok=True)

        # Salvo URL per poter ri-risolvere la URL CDN su 403/509/503.
        self._mega_url = mega_url

        # === Fase 1: resolve URL via mega.py usando il proxy del worker. ===
        self._url_hash = hashlib.sha1(
            mega_url.encode("utf-8", "replace")
        ).hexdigest()[:12]
        self._file_id = file_id
        _t0 = time.monotonic()
        file_handle, k, iv, cdn_url, file_size, file_name = self._resolve_cdn(
            mega_url, resolver_proxy,
        )
        telemetry.event(
            "file_resolved",
            file_id=file_id, url_hash=self._url_hash,
            resolve_ms=round((time.monotonic() - _t0) * 1000, 1),
            file_size=file_size, file_name=file_name,
            cdn_host=cdn_url.split("/")[2] if "://" in cdn_url else None,
        )
        self._file_handle = file_handle
        self._k_tuple = k
        self._iv = iv

        # Sanitizzo: blocca path traversal con nomi tipo "../x".
        file_name = Path(file_name).name
        final_path = output_dir / file_name
        # Pattern .part + rename atomico: si scrive SEMPRE su `<nome>.part`;
        # il nome finale viene creato solo a download completo e verificato
        # (os.replace). L'esistenza del nome finale e' l'UNICO marker di
        # completamento usato dal check di resume del worker.
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        log.info(
            "[parallel] resolve ok: name=%s size=%d cdn_host=%s",
            file_name, file_size, cdn_url.split("/")[2] if "://" in cdn_url else "?",
        )
        # Notifica immediata al worker: nome file noto appena risolto.
        if resolved_callback is not None:
            try:
                resolved_callback(file_name, file_size, final_path)
            except Exception:
                pass

        # === Fase 2: calcola chunk a dimensione fissa. ===
        eff_conn = self.n_connections
        if file_size < PARALLEL_MIN_SEGMENT_BYTES * 2:
            eff_conn = 1
        chunks = _split_chunks(file_size, self.chunk_size)
        log.info(
            "[parallel] chunk=%d chunk_size=%d B eff_conn=%d",
            len(chunks), self.chunk_size, eff_conn,
        )

        # Compat vecchio schema (pre-.part): il sidecar puntava al nome finale
        # e i byte parziali stavano direttamente in final_path. Se troviamo
        # quella coppia, rinominiamo file e sidecar al nuovo schema .part e
        # il resume prosegue normalmente.
        old_sidecar = _progress_path(final_path)
        if final_path.exists() and old_sidecar.exists() and not part_path.exists():
            try:
                os.replace(final_path, part_path)
                os.replace(old_sidecar, _progress_path(part_path))
                log.info("[parallel] migrato file+sidecar dal vecchio schema a .part")
            except OSError as exc:
                log.warning("[parallel] migrazione vecchio schema fallita: %s", exc)
        elif final_path.exists() and not part_path.exists():
            log.warning("[parallel] file esistente senza sidecar, provenienza "
                        "incerta: riparto da zero su .part")

        # Resume: carica i chunk gia' completati da una run precedente.
        # Il sidecar include chunk_size: se cambia, i range salvati sono
        # incompatibili e si reinizia. Con chunk_size fisso il resume e' valido
        # indipendentemente da N connessioni (al contrario dei vecchi segmenti).
        already_done = _load_progress(part_path, file_handle, file_size, self.chunk_size)
        already_done = already_done & set(chunks)

        telemetry.event(
            "file_plan", file_id=file_id, url_hash=self._url_hash,
            n_chunks=len(chunks), chunk_size=self.chunk_size,
            eff_conn=eff_conn, file_size=file_size,
            resumed_chunks=len(already_done),
        )

        # === Fase 3: scarica chunk in parallelo. ===
        k_str = a32_to_str(k)
        base_counter = ((iv[0] << 32) + iv[1]) << 64  # counter iniziale per offset 0
        self._bytes_downloaded = sum((e - s + 1) for (s, e) in already_done)
        self._cdn_url = cdn_url
        self._n_chunks = len(chunks)
        self._failed_chunks = 0
        self._abort.clear()
        self._done_segments = set(already_done)
        self._done_lock = threading.Lock()
        self._part_path = part_path
        self._file_handle_str = file_handle
        self._file_size = file_size
        self._chunk_size = self.chunk_size  # snapshot per _download_chunk

        # Pre-alloca il .part (sparse) SOLO se non esiste gia' (resume).
        if not part_path.exists():
            with open(part_path, "wb") as fp:
                if file_size > 0:
                    fp.seek(file_size - 1)
                    fp.write(b"\0")
        elif part_path.stat().st_size != file_size:
            # .part esiste ma dimensione errata: rigenera (sidecar invalidato sopra).
            log.warning("[parallel] .part esistente con size errato, rialloco")
            with open(part_path, "wb") as fp:
                if file_size > 0:
                    fp.seek(file_size - 1)
                    fp.write(b"\0")
        # Niente write_lock globale: ogni segmento apre un proprio file handle
        # sul .part e scrive su un range disgiunto dagli altri; seek+write su
        # offset non sovrapposti con handle separati non hanno race.

        progress_stop = threading.Event()
        progress_thread: threading.Thread | None = None
        if progress_callback:
            progress_thread = threading.Thread(
                target=self._progress_poller,
                args=(file_size, progress_callback, progress_stop, speed_callback),
                daemon=True,
                name="ParallelProgressPoller",
            )
            progress_thread.start()

        chunk_errors: list[str] = []
        try:
            with ThreadPoolExecutor(
                max_workers=eff_conn, thread_name_prefix="ParallelChunk"
            ) as pool:
                futures = []
                for chunk_idx, (start, end) in enumerate(chunks):
                    if (start, end) in already_done:
                        log.info(
                            "[parallel] chunk=%d gia' completo (resume), skip range=%d-%d",
                            chunk_idx, start, end,
                        )
                        continue
                    futures.append(pool.submit(
                        self._download_chunk,
                        chunk_idx,
                        start,
                        end,
                        cdn_url,
                        k_str,
                        base_counter,
                        part_path,
                        AES,
                        Counter,
                        ip_callback,
                    ))
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as exc:
                        chunk_errors.append(str(exc))
                        # WARNING, non ERROR: copre abort locale/cancellazione,
                        # retry esauriti e rate-limit CDN — fisiologico coi
                        # proxy gratuiti, non un bug. Vedi rules/logging.md.
                        log.warning("[parallel] chunk fallito: %s", exc)
                        # Abort soft: conta solo i fallimenti reali (chunk che
                        # hanno esaurito TUTTI i retry). Ignora eccezioni da
                        # abort/cancellazione gia' gestite dai checkpoint interni.
                        if not self._abort.is_set() and (
                            self.session_state is None
                            or not self.session_state.is_cancelled()
                        ):
                            with self._failed_lock:
                                self._failed_chunks += 1
                                f = self._failed_chunks
                            if f >= PARALLEL_MAX_FAILED_CHUNKS:
                                if not self._abort.is_set():
                                    log.warning(
                                        "[parallel] %d chunk hanno esaurito tutti "
                                        "i retry -> abort soft",
                                        f,
                                    )
                                    self._abort.set()
        finally:
            progress_stop.set()
            if progress_thread is not None:
                progress_thread.join(timeout=2)

        if chunk_errors:
            # NON cancellare il .part ne' il sidecar: i chunk completati restano
            # su disco. Al prossimo retry del worker il sidecar viene riletto e
            # solo i chunk mancanti vengono riscaricati.
            raise RuntimeError(
                f"{len(chunk_errors)}/{len(chunks)} chunk falliti: "
                + "; ".join(chunk_errors[:3])
            )

        # Successo totale: rimuovi il sidecar, poi promuovi il .part al nome
        # finale con rename atomico. Solo da qui il file "esiste" davvero.
        try:
            _progress_path(part_path).unlink(missing_ok=True)
        except OSError:
            pass
        os.replace(part_path, final_path)
        if progress_callback:
            progress_callback(100)
        log.info("[parallel] download completato: %s (%d B)", final_path, file_size)
        telemetry.event(
            "file_completed", file_id=file_id, url_hash=self._url_hash,
            file_size=file_size,
        )
        return final_path

    def _emit_attempt(self, rec, outcome, pool_action, _t0, error=None, backoff=None):
        # Chiude e accoda il record del tentativo-chunk una sola volta per
        # tentativo. Telemetria pura: nessun effetto sul flusso.
        rec["outcome"] = outcome
        rec["pool_action"] = pool_action
        if error is not None:
            rec["error"] = str(error)[:300]
        if backoff is not None:
            rec["backoff_s"] = backoff
        rec["t_total_ms"] = round((time.monotonic() - _t0) * 1000, 1)
        telemetry.chunk_attempt(rec)

    @staticmethod
    def _classify(exc: Exception) -> str:
        """Classifica un'eccezione di tentativo per il campo outcome della
        telemetria. Sola lettura del messaggio: non cambia il flusso."""
        msg = str(exc).lower()
        if "cancellato" in msg:
            return "cancelled"
        if "abort locale" in msg or "abort durante" in msg:
            return "aborted_local"
        if "budget temporale" in msg:
            return "budget_exceeded"
        if "troppo lento" in msg:
            return "slow_killed"
        if "ignora range" in msg:
            return "range_ignored"
        if "ricevuti" in msg and "attesi" in msg:
            return "size_mismatch"
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return "timeout_connect"
        if isinstance(exc, requests.exceptions.ReadTimeout):
            return "timeout_read"
        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout_read"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "conn_error"
        return "other"

    def _download_chunk(
        self,
        chunk_idx: int,
        start: int,
        end: int,
        cdn_url: str,
        k_str: bytes,
        base_counter: int,
        part_path: Path,
        AES,
        Counter,
        ip_callback: Callable[[str, int], None] | None,
    ) -> None:
        chunk_size_actual = end - start + 1
        attempt = 0
        last_exc: Exception | None = None
        # Proxy "appiccicoso" per il 429 (too many concurrent IPs): quando il
        # CDN risponde 429, si RI-PROVA LO STESSO proxy (stesso IP) invece di
        # pescarne uno nuovo, per non aumentare il numero di IP concorrenti sul
        # file. Settato nel branch 429, consumato qui alla selezione successiva.
        sticky_proxy: dict | None = None
        while attempt < PARALLEL_SEGMENT_RETRIES:
            if self._abort.is_set():
                raise RuntimeError(
                    f"chunk {chunk_idx}: abort locale (altri chunk hanno esaurito i retry)"
                )
            if self.session_state is not None and self.session_state.is_cancelled():
                raise RuntimeError(f"chunk {chunk_idx}: cancellato dall'utente")
            if self.session_state is not None:
                self.session_state.wait_if_paused()
            attempt += 1
            if sticky_proxy is not None:
                # Ri-uso lo stesso IP dopo un 429 (vedi branch 429): non aggiungo
                # un IP nuovo al conteggio concorrente del file.
                proxy = sticky_proxy
                sticky_proxy = None
            else:
                proxy = self.pool.get_next()
            if proxy is None:
                added = self.pool.refill_blocking()
                telemetry.event(
                    "pool_empty",
                    file_id=getattr(self, "_file_id", None),
                    url_hash=getattr(self, "_url_hash", None),
                    chunk_idx=chunk_idx, added=added,
                )
                proxy = self.pool.get_next()
            if proxy is None:
                last_exc = RuntimeError("pool proxy vuoto")
                if self._sleep_interruptible(5):
                    raise RuntimeError(f"chunk {chunk_idx}: abort durante attesa pool")
                continue
            proxies = _proxies_dict(proxy)
            current_url = self._cdn_url or cdn_url
            rec = {
                "file_id": getattr(self, "_file_id", None),
                "url_hash": getattr(self, "_url_hash", None),
                "chunk_idx": chunk_idx, "attempt": attempt,
                "attempt_of": PARALLEL_SEGMENT_RETRIES,
                "chunk_start": start, "chunk_end": end,
                "chunk_bytes": chunk_size_actual,
                "ts_start": datetime.now().isoformat(timespec="milliseconds"),
                "proxy_host": proxy["host"], "proxy_port": proxy["port"],
                "proxy_protocol": proxy.get("protocol", "http"),
                "proxy_source": proxy.get("_source", "cache"),
                "proxy_score_before": self.pool.score_of(proxy),
                "proxy_latency_ms": proxy.get("latency_ms"),
                "proxy_uptime_pct": proxy.get("uptime_percent"),
                "proxy_anonymity": proxy.get("anonymity"),
                "pool_alive": self.pool.size(),
                "pool_cooldown": self.pool.cooldown_count(),
                "egress_ip": None, "http_status": None,
                "t_headers_ms": None, "t_firstbyte_ms": None,
                "t_transfer_ms": None, "t_total_ms": None,
                "bytes_downloaded": 0, "throughput_bps": None,
                "intra_samples": [], "outcome": None, "pool_action": None,
                "error": None, "backoff_s": None,
            }
            _attempt_t0 = time.monotonic()
            log.info(
                "[parallel] chunk=%d tentativo=%d/%d range=%d-%d (%d B) via %s:%s",
                chunk_idx, attempt, PARALLEL_SEGMENT_RETRIES,
                start, end, chunk_size_actual, proxy["host"], proxy["port"],
            )
            cdn_error = False
            try:
                rec["egress_ip"] = f"{proxy['host']}:{proxy['port']}"
                if ip_callback:
                    try:
                        ip_callback(f"{proxy['host']}:{proxy['port']}", chunk_idx)
                    except Exception:
                        pass
                headers = {
                    "User-Agent": USER_AGENT,
                    "Range": f"bytes={start}-{end}",
                    "Accept-Encoding": "identity",
                }
                resp = requests.get(
                    current_url,
                    headers=headers,
                    proxies=proxies,
                    timeout=(PROXY_CONNECT_TIMEOUT, PROXY_READ_TIMEOUT),
                    stream=True,
                )
                rec["t_headers_ms"] = round((time.monotonic() - _attempt_t0) * 1000, 1)
                with resp:
                    rec["http_status"] = resp.status_code
                    if resp.status_code in (403, 509):
                        last_exc = RuntimeError(
                            f"CDN {resp.status_code} (rate-limit proxy)"
                        )
                        log.warning(
                            "[parallel] chunk=%d 403/509 dal CDN -> proxy %s:%s "
                            "in cooldown (rate-limit)",
                            chunk_idx, proxy["host"], proxy["port"],
                        )
                        self.pool.cooldown(proxy)
                        cdn_error = True
                        backoff = min(PARALLEL_SEGMENT_BACKOFF_MAX, 2 ** min(attempt, 6))
                        self._emit_attempt(
                            rec, "http_%d" % resp.status_code, "cooldown",
                            _attempt_t0, error=last_exc, backoff=backoff,
                        )
                        if self._sleep_interruptible(backoff):
                            raise RuntimeError(f"chunk {chunk_idx}: abort durante backoff")
                        continue
                    if resp.status_code == 503:
                        last_exc = RuntimeError("CDN 503 (overload o URL scaduta)")
                        log.warning(
                            "[parallel] chunk=%d 503 dal CDN -> proxy %s:%s marcato "
                            "dead + tentativo re-resolve URL",
                            chunk_idx, proxy["host"], proxy["port"],
                        )
                        self.pool.penalize(proxy, hard=True)
                        cdn_error = True
                        self._refresh_cdn_url(current_url)
                        backoff = min(PARALLEL_SEGMENT_BACKOFF_MAX, 2 ** min(attempt, 6))
                        self._emit_attempt(
                            rec, "http_503", "penalize_hard",
                            _attempt_t0, error=last_exc, backoff=backoff,
                        )
                        if self._sleep_interruptible(backoff):
                            raise RuntimeError(f"chunk {chunk_idx}: abort durante backoff")
                        continue
                    if resp.status_code == 429:
                        # Limite PER-FILE di Mega (troppi IP concorrenti sullo
                        # stesso file): NON e' colpa del proxy. Cambiare proxy
                        # aggiungerebbe un IP e peggiorerebbe il 429 -> ri-provo
                        # lo STESSO proxy dopo un backoff (sticky), senza
                        # penalizzare ne' mettere in cooldown. cdn_error=True per
                        # non penalizzare nel cleanup finale del loop.
                        last_exc = RuntimeError("CDN 429 (too many concurrent IPs)")
                        log.warning(
                            "[parallel] chunk=%d 429 (troppi IP concorrenti sul "
                            "file) -> ri-provo lo stesso IP %s:%s dopo backoff",
                            chunk_idx, proxy["host"], proxy["port"],
                        )
                        sticky_proxy = proxy
                        cdn_error = True
                        backoff = min(
                            PARALLEL_HTTP_429_BACKOFF_MAX_S,
                            PARALLEL_HTTP_429_BACKOFF_S * attempt,
                        )
                        self._emit_attempt(
                            rec, "http_429", "sticky_retry",
                            _attempt_t0, error=last_exc, backoff=backoff,
                        )
                        if self._sleep_interruptible(backoff):
                            raise RuntimeError(f"chunk {chunk_idx}: abort durante backoff 429")
                        continue
                    resp.raise_for_status()
                    if resp.status_code != 206 and chunk_size_actual != self._content_length(resp):
                        raise RuntimeError(
                            f"chunk {chunk_idx}: server ignora Range "
                            f"(status={resp.status_code})"
                        )

                    initial_counter = base_counter + (start // 16)
                    counter = Counter.new(128, initial_value=initial_counter)
                    aes = AES.new(k_str, AES.MODE_CTR, counter=counter)

                    downloaded = 0
                    # Watchdog throughput e budget temporale: ora per-chunk.
                    # Con chunk da 8 MB a 200 KB/s il download dura ~40s,
                    # ben dentro il budget assoluto di 180s.
                    attempt_start = time.monotonic()
                    window_start = attempt_start
                    window_bytes = 0
                    with open(part_path, "r+b") as fp:
                        fp.seek(start)
                        for net_chunk in resp.iter_content(chunk_size=64 * 1024):
                            if self._abort.is_set():
                                raise RuntimeError(
                                    f"chunk {chunk_idx}: abort locale mid-download"
                                )
                            if (self.session_state is not None
                                    and self.session_state.is_cancelled()):
                                raise RuntimeError(
                                    f"chunk {chunk_idx}: cancellato mid-download"
                                )
                            if not net_chunk:
                                continue
                            if rec["t_firstbyte_ms"] is None:
                                rec["t_firstbyte_ms"] = round(
                                    (time.monotonic() - _attempt_t0) * 1000, 1
                                )
                            fp.write(aes.decrypt(net_chunk))
                            downloaded += len(net_chunk)
                            with self._bytes_lock:
                                self._bytes_downloaded += len(net_chunk)
                            window_bytes += len(net_chunk)
                            now = time.monotonic()
                            samples = rec["intra_samples"]
                            samples.append(
                                [round((now - _attempt_t0) * 1000), downloaded]
                            )
                            if (TELEMETRY_INTRA_CHUNK_MAX_SAMPLES > 0
                                    and len(samples) > TELEMETRY_INTRA_CHUNK_MAX_SAMPLES):
                                rec["intra_samples"] = samples[::2]
                            elapsed_attempt = now - attempt_start
                            if elapsed_attempt > self.segment_max_duration_s:
                                raise RuntimeError(
                                    f"chunk {chunk_idx}: superato budget temporale di "
                                    f"{self.segment_max_duration_s}s "
                                    f"(scaricati {downloaded}/{chunk_size_actual} B)"
                                )
                            window_elapsed = now - window_start
                            if (
                                elapsed_attempt >= PARALLEL_THROUGHPUT_GRACE
                                and window_elapsed >= PARALLEL_THROUGHPUT_WINDOW
                            ):
                                bps = window_bytes / window_elapsed
                                if bps < PARALLEL_MIN_THROUGHPUT_BPS:
                                    raise RuntimeError(
                                        f"chunk {chunk_idx}: proxy troppo lento "
                                        f"({bps / 1024:.1f} KB/s < "
                                        f"{PARALLEL_MIN_THROUGHPUT_BPS / 1024:.0f} KB/s "
                                        f"per {window_elapsed:.0f}s)"
                                    )
                                window_start = now
                                window_bytes = 0
                    if downloaded != chunk_size_actual:
                        raise RuntimeError(
                            f"chunk {chunk_idx}: ricevuti {downloaded}B "
                            f"su {chunk_size_actual}B attesi"
                        )

                # Persisti il chunk nel sidecar prima di tornare.
                with self._done_lock:
                    self._done_segments.add((start, end))
                    done_snapshot = set(self._done_segments)
                _save_progress(
                    self._part_path,
                    self._file_handle_str,
                    self._file_size,
                    done_snapshot,
                    self._chunk_size,
                )
                self.pool.record_success(proxy)
                # Leva B (sperimentale): segnale a costo zero, gia' disponibile
                # al watchdog. Non influisce sulla modalita' "score" (default).
                chunk_elapsed = time.monotonic() - attempt_start
                if chunk_elapsed > 0:
                    self.pool.record_throughput(proxy, downloaded / chunk_elapsed)
                log.info(
                    "[parallel] chunk=%d OK (%d B in %d tentativi)",
                    chunk_idx, chunk_size_actual, attempt,
                )
                rec["bytes_downloaded"] = downloaded
                rec["t_transfer_ms"] = round(chunk_elapsed * 1000, 1)
                rec["throughput_bps"] = (
                    downloaded / chunk_elapsed if chunk_elapsed > 0 else None
                )
                self._emit_attempt(rec, "ok", "record_success", _attempt_t0)
                return
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                code = exc.response.status_code if exc.response is not None else 0
                if code in (403, 509):
                    log.warning(
                        "[parallel] chunk=%d HTTP %d -> proxy %s:%s in cooldown",
                        chunk_idx, code, proxy["host"], proxy["port"],
                    )
                    self.pool.cooldown(proxy)
                    cdn_error = True
                    rec_outcome, rec_action = "http_%d" % code, "cooldown"
                elif code == 503:
                    log.warning(
                        "[parallel] chunk=%d HTTP 503 -> proxy %s:%s marcato "
                        "dead + re-resolve URL",
                        chunk_idx, proxy["host"], proxy["port"],
                    )
                    self.pool.penalize(proxy, hard=True)
                    cdn_error = True
                    self._refresh_cdn_url(current_url)
                    rec_outcome, rec_action = "http_503", "penalize_hard"
                else:
                    log.warning(
                        "[parallel] chunk=%d tentativo=%d fallito: HTTP %d",
                        chunk_idx, attempt, code,
                    )
                    rec_outcome, rec_action = "http_other", "penalize_soft"
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "[parallel] chunk=%d tentativo=%d fallito: %s",
                    chunk_idx, attempt, exc,
                )
                rec_outcome = self._classify(exc)
                rec_action = None if cdn_error else "penalize_soft"
            if not cdn_error:
                self.pool.penalize(proxy, hard=False)
            backoff = min(PARALLEL_SEGMENT_BACKOFF_MAX, 2 ** min(attempt, 6))
            self._emit_attempt(
                rec, rec_outcome, rec_action, _attempt_t0,
                error=last_exc, backoff=backoff,
            )
            if self._sleep_interruptible(backoff):
                raise RuntimeError(f"chunk {chunk_idx}: abort durante backoff")
        rec_final = {
            "file_id": getattr(self, "_file_id", None),
            "url_hash": getattr(self, "_url_hash", None),
            "chunk_idx": chunk_idx, "attempt": attempt,
            "attempt_of": PARALLEL_SEGMENT_RETRIES,
            "chunk_start": start, "chunk_end": end,
            "chunk_bytes": chunk_size_actual,
            "ts_start": datetime.now().isoformat(timespec="milliseconds"),
        }
        self._emit_attempt(
            rec_final, "retries_exhausted", None, time.monotonic(), error=last_exc,
        )
        raise RuntimeError(
            f"chunk {chunk_idx}: esauriti {PARALLEL_SEGMENT_RETRIES} tentativi ({last_exc})"
        )

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep che ritorna True se nel mezzo arriva abort o cancellazione."""
        step = 0.5
        elapsed = 0.0
        while elapsed < seconds:
            if self._abort.is_set():
                return True
            if self.session_state is not None and self.session_state.is_cancelled():
                return True
            time.sleep(step)
            elapsed += step
        return False

    def _resolve_cdn(self, mega_url: str, resolver_proxy: dict):
        """Risolve un link Mega pubblico ritornando (file_handle, k, iv,
        cdn_url, file_size, file_name). Usato sia al primo download che ai
        re-resolve quando la URL CDN scade (403/509/503).

        Usa il `resolver_proxy` passato per la chiamata API; se fallisce, il
        chiamante deve scegliere un proxy diverso e ritentare.
        """
        client = MegaPublicClient(resolver_proxy, timeout=max(PROXY_TIMEOUT * 4, 30))
        info = client.resolve_public_url(mega_url)
        return (
            info["handle"], info["k"], info["iv"],
            info["cdn_url"], info["file_size"], info["file_name"],
        )

    def _refresh_cdn_url(self, current_url: str) -> str | None:
        """Ri-risolve la URL CDN se quella corrente e' scaduta/throttled.
        Thread-safe: il primo segmento che entra fa il refresh, gli altri
        riusano il risultato senza ri-chiamare l'API Mega.
        """
        with self._cdn_lock:
            # Se qualcun altro ha gia' fatto refresh dopo la nostra ultima
            # lettura, salta.
            if getattr(self, "_cdn_url", None) and self._cdn_url != current_url:
                return self._cdn_url
            log.info("[parallel] re-resolve CDN URL (la precedente sembra scaduta)")
            _rr_t0 = time.monotonic()
            _rr_tried = 0
            # Provo fino a 3 proxy diversi per il re-resolve.
            for _ in range(3):
                if self._abort.is_set():
                    telemetry.event(
                        "re_resolve",
                        file_id=getattr(self, "_file_id", None),
                        url_hash=getattr(self, "_url_hash", None),
                        outcome="aborted", proxies_tried=_rr_tried, cdn_host=None,
                        elapsed_ms=round((time.monotonic() - _rr_t0) * 1000, 1),
                    )
                    return None
                proxy = self.pool.get_next()
                if proxy is None:
                    self.pool.refill_blocking()
                    proxy = self.pool.get_next()
                if proxy is None:
                    log.warning("[parallel] re-resolve: pool vuoto, abort")
                    telemetry.event(
                        "re_resolve",
                        file_id=getattr(self, "_file_id", None),
                        url_hash=getattr(self, "_url_hash", None),
                        outcome="pool_empty", proxies_tried=_rr_tried, cdn_host=None,
                        elapsed_ms=round((time.monotonic() - _rr_t0) * 1000, 1),
                    )
                    return None
                _rr_tried += 1
                try:
                    _, _, _, new_url, _, _ = self._resolve_cdn(self._mega_url, proxy)
                    self._cdn_url = new_url
                    log.info("[parallel] nuova CDN URL ottenuta: %s",
                             new_url.split("/")[2] if "://" in new_url else "?")
                    telemetry.event(
                        "re_resolve",
                        file_id=getattr(self, "_file_id", None),
                        url_hash=getattr(self, "_url_hash", None),
                        outcome="ok", proxies_tried=_rr_tried,
                        cdn_host=new_url.split("/")[2] if "://" in new_url else None,
                        elapsed_ms=round((time.monotonic() - _rr_t0) * 1000, 1),
                    )
                    return new_url
                except Exception as exc:
                    log.warning("[parallel] re-resolve fallito via %s:%s: %s",
                                proxy["host"], proxy["port"], exc)
                    # Resolve fallito = errore transitorio: penalita' soft.
                    self.pool.penalize(proxy, hard=False)
            telemetry.event(
                "re_resolve",
                file_id=getattr(self, "_file_id", None),
                url_hash=getattr(self, "_url_hash", None),
                outcome="failed", proxies_tried=_rr_tried, cdn_host=None,
                elapsed_ms=round((time.monotonic() - _rr_t0) * 1000, 1),
            )
            return None

    @staticmethod
    def _content_length(resp) -> int:
        try:
            return int(resp.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return 0

    def _progress_poller(
        self,
        total_size: int,
        cb: Callable[[int], None],
        stop: threading.Event,
        speed_cb: Callable[[float, int, int], None] | None = None,
    ) -> None:
        last_pct = -1
        # Inizializzo dai byte GIA' scaricati (resume incluso): il primo
        # delta deve misurare solo i byte scaricati DOPO l'avvio del monitor,
        # non quelli ripresi da run precedenti (altrimenti il primo bps e'
        # spurio: conta in mezzo secondo byte accumulati su run multiple).
        with self._bytes_lock:
            prev_bytes = self._bytes_downloaded
        prev_time = time.monotonic()
        last_bps = 0.0
        last_sample_t = 0.0
        while not stop.is_set():
            with self._bytes_lock:
                done = self._bytes_downloaded
            pct = min(99, int(done * 100 / total_size)) if total_size else 0
            if pct != last_pct:
                try:
                    cb(pct)
                except Exception:
                    pass
                last_pct = pct
            # Un solo time.monotonic() per giro, riusato da speed_cb e dal
            # campione di telemetria (evita di alterare il timing del poller).
            now = time.monotonic()
            if speed_cb and total_size > 0:
                dt = now - prev_time
                if dt >= 0.5:
                    bps = (done - prev_bytes) / dt
                    last_bps = max(0.0, bps)
                    prev_bytes = done
                    prev_time = now
                    try:
                        speed_cb(last_bps, done, total_size)
                    except Exception:
                        pass
            # Campione aggregato a 1 Hz (telemetria scatola nera). Il guard
            # is_active() evita di toccare self.pool quando la cattura e' OFF
            # (o il pool e' None, es. nei test del poller in isolamento).
            if (telemetry.is_active()
                    and now - last_sample_t >= TELEMETRY_SAMPLE_INTERVAL_S):
                last_sample_t = now
                telemetry.sample({
                    "file_id": getattr(self, "_file_id", None),
                    "url_hash": getattr(self, "_url_hash", None),
                    "bytes_done": done, "total_size": total_size,
                    "instant_bps": last_bps,
                    "pool_alive": self.pool.size(),
                    "pool_cooldown": self.pool.cooldown_count(),
                    "pool_discarded": self.pool.discarded_count(),
                    "refill_count": self.pool.refill_count(),
                })
            stop.wait(0.5)
