"""One-shot CLI: scarica un link Mega tramite proxy, una volta sola.

Scopo: bypassare la GUI per ottenere il file richiesto.
Uso: python -m scripts.download_once <mega_url> [output_dir]
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.core.config import OUTPUT_DIR
from src.downloader.mega_client import MegaClient, MegaCryptoDependencyError
from src.proxy.scraper import ProxyScraper
from src.proxy.validator import ProxyValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("download_once")


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.download_once <mega_url> [output_dir]", file=sys.stderr)
        return 2
    url = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else OUTPUT_DIR / "oneshot"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Scrape proxy...")
    candidates = ProxyScraper().fetch_all()
    log.info("Candidati: %d", len(candidates))
    if not candidates:
        log.error("Nessun proxy raccolto")
        return 1

    log.info("Validazione contro Mega (cap 200)...")
    alive = ProxyValidator().validate_against_mega(
        candidates[:200],
        progress_callback=lambda d, t, a: log.info("validati %d/%d (vivi %d)", d, t, a)
        if d % 25 == 0 else None,
    )
    log.info("Proxy vivi: %d", len(alive))
    if not alive:
        log.error("Nessun proxy valido")
        return 1

    for i, proxy in enumerate(alive, 1):
        log.info("[%d/%d] tento con %s:%s", i, len(alive), proxy["host"], proxy["port"])
        client = MegaClient(proxy)
        try:
            ip = client.get_egress_ip()
            log.info("  IP uscente: %s", ip)
        except Exception as exc:
            log.warning("  IP check ko: %s", exc)
            continue
        try:
            result = client.download(url, out_dir)
            log.info("OK: file salvato in %s", result)
            return 0
        except MegaCryptoDependencyError as exc:
            log.error("Errore di configurazione: %s", exc)
            return 1
        except Exception as exc:
            log.warning("  download ko: %s", exc)
            continue

    log.error("Tutti i proxy hanno fallito")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
