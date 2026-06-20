"""CLI multi-ciclo: scarica un link Mega N volte ruotando i proxy.

Uso: python -m scripts.download_n <mega_url> [cicli] [output_dir]
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
log = logging.getLogger("download_n")


def _validate_pool() -> list[dict]:
    log.info("Scrape proxy...")
    candidates = ProxyScraper().fetch_all()
    log.info("Candidati: %d", len(candidates))
    if not candidates:
        return []
    log.info("Validazione contro Mega (cap 200)...")
    alive = ProxyValidator().validate_against_mega(
        candidates[:200],
        progress_callback=lambda d, t, a: log.info("validati %d/%d (vivi %d)", d, t, a)
        if d % 50 == 0 else None,
    )
    log.info("Proxy vivi: %d", len(alive))
    return alive


def _one_download(pool: list[dict], start_idx: int, used_ips: set[str], dest: Path) -> tuple[bool, int, str | None]:
    """Tenta finche' non riesce; restituisce (ok, next_idx, ip_used)."""
    n = len(pool)
    tried = 0
    idx = start_idx
    while tried < n:
        proxy = pool[idx % n]
        idx += 1
        tried += 1
        log.info("  tentativo con %s:%s", proxy["host"], proxy["port"])
        client = MegaClient(proxy)
        try:
            ip = client.get_egress_ip()
            log.info("    IP uscente: %s", ip)
        except Exception as exc:
            log.warning("    IP check ko: %s", exc)
            continue
        if ip in used_ips:
            log.info("    IP %s gia' usato, salto", ip)
            continue
        try:
            result = client.download("__URL__", dest)  # placeholder, sostituito da caller
            log.info("    OK: %s", result)
            return True, idx, ip
        except MegaCryptoDependencyError as exc:
            log.error("Errore di configurazione: %s", exc)
            raise
        except Exception as exc:
            log.warning("    download ko: %s", exc)
            continue
    return False, idx, None


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python -m scripts.download_n <mega_url> [cicli] [output_dir]", file=sys.stderr)
        return 2
    url = sys.argv[1]
    cycles = int(sys.argv[2]) if len(sys.argv) >= 3 else 5
    out_root = Path(sys.argv[3]) if len(sys.argv) >= 4 else OUTPUT_DIR / "multi"
    start_cycle = int(sys.argv[4]) if len(sys.argv) >= 5 else 1
    out_root.mkdir(parents=True, exist_ok=True)

    pool = _validate_pool()
    if not pool:
        log.error("Pool vuoto, abort")
        return 1

    used_ips: set[str] = set()
    idx = 0
    ok_count = 0
    for cycle in range(start_cycle, start_cycle + cycles):
        log.info("=== Ciclo %d (%d/%d in questo run) ===", cycle, cycle - start_cycle + 1, cycles)
        dest = out_root / f"ciclo_{cycle}"
        dest.mkdir(parents=True, exist_ok=True)
        ok = False
        n = len(pool)
        tried = 0
        while tried < n:
            proxy = pool[idx % n]
            idx += 1
            tried += 1
            log.info("  tentativo con %s:%s", proxy["host"], proxy["port"])
            client = MegaClient(proxy)
            try:
                ip = client.get_egress_ip()
                log.info("    IP uscente: %s", ip)
            except Exception as exc:
                log.warning("    IP check ko: %s", exc)
                continue
            if ip in used_ips:
                log.info("    IP %s gia' usato in un ciclo precedente, salto", ip)
                continue
            try:
                result = client.download(url, dest)
                log.info("    OK ciclo %d: %s", cycle, result)
                used_ips.add(ip)
                ok = True
                ok_count += 1
                break
            except MegaCryptoDependencyError as exc:
                log.error("Errore di configurazione: %s", exc)
                return 1
            except Exception as exc:
                log.warning("    download ko: %s", exc)
                continue
        if not ok:
            log.error("Ciclo %d FALLITO: nessun proxy disponibile ha funzionato", cycle)
    log.info("=== Riepilogo: %d/%d cicli completati ===", ok_count, cycles)
    log.info("IP usati: %s", sorted(used_ips))
    return 0 if ok_count == cycles else 1


if __name__ == "__main__":
    raise SystemExit(main())
