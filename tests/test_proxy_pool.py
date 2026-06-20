# Test puri per ProxyPool: scoring, esclusione "morti", dedup. Nessuna rete.
from src.core.config import (
    POOL_SCORE_DEAD_THRESHOLD,
    POOL_SCORE_INITIAL,
    POOL_SCORE_MAX,
    POOL_SCORE_ON_FAILURE,
    POOL_SCORE_ON_SUCCESS,
)
from src.proxy.pool import ProxyPool


def _proxy(host="1.2.3.4", port="8080"):
    return {"host": host, "port": port, "protocol": "http"}


def test_record_success_increases_score():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.record_success(p)
    assert pool._score[(p["host"], p["port"])] == POOL_SCORE_INITIAL + POOL_SCORE_ON_SUCCESS


def test_record_failure_decreases_score():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.record_failure(p)
    assert pool._score[(p["host"], p["port"])] == POOL_SCORE_INITIAL + POOL_SCORE_ON_FAILURE


def test_proxy_below_dead_threshold_excluded_from_get_next():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    # Sufficienti fallimenti per scendere sotto soglia.
    rounds = abs(POOL_SCORE_DEAD_THRESHOLD) // abs(POOL_SCORE_ON_FAILURE) + 2
    for _ in range(rounds):
        pool.record_failure(p)
    assert pool.get_next() is None


def test_penalize_hard_drops_below_threshold_immediately():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.penalize(p, hard=True)
    assert pool._score[(p["host"], p["port"])] < POOL_SCORE_DEAD_THRESHOLD
    assert pool.get_next() is None


def test_penalize_soft_equivalent_to_record_failure():
    pool = ProxyPool()
    p1, p2 = _proxy("1.1.1.1"), _proxy("2.2.2.2")
    pool.add_many([p1, p2])
    pool.penalize(p1, hard=False)
    pool.record_failure(p2)
    assert pool._score[(p1["host"], p1["port"])] == pool._score[(p2["host"], p2["port"])]


def test_add_many_dedup_on_host_port():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.record_success(p)
    score_before = pool._score[(p["host"], p["port"])]
    # Stesso (host, port) ricompare: lo score "buono" non viene resettato.
    pool.add_many([_proxy()])
    assert pool._score[(p["host"], p["port"])] == score_before
    assert pool.size() == 1


def test_record_success_caps_at_max_score():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    for _ in range(100):
        pool.record_success(p)
    assert pool._score[(p["host"], p["port"])] == POOL_SCORE_MAX


def test_size_counts_alive_only():
    pool = ProxyPool()
    alive, dead = _proxy("1.1.1.1"), _proxy("2.2.2.2")
    pool.add_many([alive, dead])
    pool.penalize(dead, hard=True)
    assert pool.size() == 1


def test_get_next_returns_none_on_empty_pool():
    pool = ProxyPool()
    assert pool.get_next() is None
