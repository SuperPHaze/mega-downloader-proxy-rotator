"""Runner CLI per scaricare N link Mega senza GUI.

Usa lo stesso DownloadOrchestrator dell'app desktop ma con QCoreApplication
(no widget). I segnali vengono stampati a stdout. Termina quando tutti i
worker hanno emesso all_done o fatal_error.

Uso:
    python -m tools.cli_download <url1> [<url2> ...]

Per scaricare lo stesso link in due cartelle distinte:
    python -m tools.cli_download <url> <url>

(due voci uguali in input → due worker con file_id diversi → due cartelle).
"""
from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtCore import QCoreApplication, QTimer

from src.core.logging_setup import setup_logging
from src.core.state import SessionState
from src.downloader.orchestrator import DownloadOrchestrator

log = logging.getLogger("cli_download")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="cli_download",
        description="Runner CLI headless (riusa DownloadOrchestrator, senza GUI).",
    )
    parser.add_argument("links", nargs="*", help="URL Mega da scaricare (1+).")
    parser.add_argument(
        "--selection-mode", choices=("score", "throughput"), default="score",
        help="Modalita' di selezione proxy del pool (default: score).",
    )
    parser.add_argument(
        "--connections", type=int, default=None,
        help="Connessioni HTTP Range parallele per file (default: config).",
    )
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help="File scaricati in parallelo (default: config).",
    )
    args = parser.parse_args(argv)
    links = args.links
    if not links:
        print("Uso: python -m tools.cli_download [--selection-mode score|throughput] "
              "[--connections N] [--concurrency N] <url1> [<url2> ...]")
        return 2

    setup_logging()
    app = QCoreApplication(sys.argv[:1])
    state = SessionState()
    orch = DownloadOrchestrator(state)

    pending = set(range(len(links)))
    exit_code = {"value": 0}

    def on_setup_status(msg: str) -> None:
        log.info("[setup] %s", msg)

    def on_setup_progress(done: int, total: int, alive: int) -> None:
        if done % 50 == 0 or done == total:
            log.info("[setup] validati %d/%d (vivi: %d)", done, total, alive)

    def on_pool_ready(n: int) -> None:
        log.info("[setup] pool pronto: %d proxy vivi", n)

    def on_pool_failed(msg: str) -> None:
        log.error("[setup] FALLITO: %s", msg)
        exit_code["value"] = 1
        QCoreApplication.quit()

    def on_progress(fid: int, cycle: int, pct: int) -> None:
        if pct % 10 == 0:
            log.info("[file %d] ciclo %d: %d%%", fid, cycle, pct)

    def on_cycle_completed(fid: int, cycle: int) -> None:
        log.info("[file %d] ciclo %d COMPLETATO", fid, cycle)

    def on_all_done(fid: int) -> None:
        log.info("[file %d] TUTTI I CICLI COMPLETATI", fid)
        pending.discard(fid)
        if not pending:
            log.info("[done] tutti i download conclusi, esco")
            QCoreApplication.quit()

    def on_fatal_error(fid: int, msg: str) -> None:
        log.error("[file %d] FATAL: %s", fid, msg)
        pending.discard(fid)
        if not pending:
            exit_code["value"] = 1
            QCoreApplication.quit()

    def on_failed(fid: int, cycle: int, reason: str) -> None:
        log.warning("[file %d] ciclo %d tentativo fallito: %s", fid, cycle, reason)

    orch.setup_status.connect(on_setup_status)
    orch.setup_progress.connect(on_setup_progress)
    orch.pool_ready.connect(on_pool_ready)
    orch.pool_failed.connect(on_pool_failed)
    orch.progress.connect(on_progress)
    orch.cycle_completed.connect(on_cycle_completed)
    orch.all_done.connect(on_all_done)
    orch.fatal_error.connect(on_fatal_error)
    orch.failed.connect(on_failed)

    QTimer.singleShot(0, lambda: orch.start(
        links,
        concurrency=args.concurrency,
        connections_per_file=args.connections,
        selection_mode=args.selection_mode,
    ))
    log.info(
        "CLI: avvio con %d link (selezione=%s, connessioni=%s, concorrenza=%s)",
        len(links), args.selection_mode, args.connections, args.concurrency,
    )
    app.exec()
    # Teardown esplicito: ferma worker/refresher/timer e chiude la telemetria
    # (telemetry.close() drena la coda e chiude i file). Senza questo, l'ultimo
    # batch entro TELEMETRY_FLUSH_INTERVAL_S puo' restare non scritto.
    try:
        orch.shutdown()
    except Exception:  # noqa: BLE001 — il teardown non deve mascherare l'esito
        log.exception("CLI: errore durante shutdown()")
    log.info("CLI: terminato con exit_code=%d", exit_code["value"])
    return exit_code["value"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

