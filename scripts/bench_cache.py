"""Bench: cold start (scrape+validate completo) vs hot start (cache revalidate).

Esegue lo stesso path che _SetupThread userebbe, senza GUI, e stampa i tempi.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime

from src.core.config import (
    MAX_PROXIES_TO_VALIDATE,
    PROXY_CACHE_MIN_SCORE_FOR_PERSISTENCE,
    VALIDATOR_STAGE1_WORKERS,
)
from src.proxy import proxy_cache
from src.proxy.pool import ProxyPool
from src.proxy.scraper import ProxyScraper
from src.proxy.validator import ProxyValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bench")


def cold_start() -> list[dict]:
    t0 = time.monotonic()
    scraper = ProxyScraper()
    candidates = scraper.fetch_all()[:MAX_PROXIES_TO_VALIDATE]
    log.info("Cold: %d candidati", len(candidates))
    validator = ProxyValidator()
    breakdown = validator.validate_against_mega(candidates, return_stage_breakdown=True)
    alive = breakdown["stage2_alive"]
    dt = time.monotonic() - t0
    log.info("COLD START: %d proxy vivi in %.1fs", len(alive), dt)
    return alive


def hot_start() -> list[dict]:
    t0 = time.monotonic()
    cached = proxy_cache.load()
    log.info("Hot: %d cached candidati", len(cached))
    if not cached:
        log.warning("nessuna cache, hot start vuoto")
        return []
    validator = ProxyValidator()
    hot = validator._run_stage(
        cached, validator._check_alive, VALIDATOR_STAGE1_WORKERS,
        progress_callback=None, stage_name="cache-revalidate", target_alive=None,
    )
    dt = time.monotonic() - t0
    log.info("HOT START: %d/%d revalidati in %.1fs", len(hot), len(cached), dt)
    return hot


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "cold-then-hot"
    if mode in ("cold", "cold-then-hot"):
        alive = cold_start()
        # Salva cache come farebbe l'orchestrator.
        pool = ProxyPool()
        pool.add_many(alive)
        snap = pool.export_for_cache(min_score=PROXY_CACHE_MIN_SCORE_FOR_PERSISTENCE)
        now = datetime.now().isoformat(timespec="seconds")
        for p in snap:
            p["last_seen"] = now
        proxy_cache.save(snap)
    if mode in ("hot", "cold-then-hot"):
        hot_start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
