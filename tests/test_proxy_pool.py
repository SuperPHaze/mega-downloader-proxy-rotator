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


# ---- Funzioni Sperimentali: Leva A/B (additive, default off) -------------

def test_default_selection_mode_is_score():
    # Con i flag ai default il pool deve restare in modalita' storica.
    pool = ProxyPool()
    assert pool.selection_mode == "score"


def test_score_mode_get_next_sequence_unchanged():
    # Regressione: con selection_mode="score" (default) la sequenza prodotta
    # da get_next() e' IDENTICA a quella attuale (score-tier -> tiebreak
    # latenza -> round-robin), a prescindere da record_throughput().
    pool = ProxyPool()
    p1, p2, p3 = _proxy("1.1.1.1"), _proxy("2.2.2.2"), _proxy("3.3.3.3")
    pool.add_many([p1, p2, p3])
    # record_throughput non deve influenzare il ramo "score".
    pool.record_throughput(p3, 999_999.0)
    seq = [pool.get_next() for _ in range(6)]
    expected = [p1, p2, p3, p1, p2, p3]
    assert seq == expected


def test_record_throughput_ema_known_values():
    from src.core.config import POOL_THROUGHPUT_EMA_ALPHA

    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.record_throughput(p, 1000.0)
    assert pool._throughput[(p["host"], p["port"])] == 1000.0
    pool.record_throughput(p, 2000.0)
    expected = POOL_THROUGHPUT_EMA_ALPHA * 2000.0 + (1 - POOL_THROUGHPUT_EMA_ALPHA) * 1000.0
    assert pool._throughput[(p["host"], p["port"])] == expected


def test_record_throughput_never_measured_proxy_has_no_entry():
    pool = ProxyPool()
    p1, p2 = _proxy("1.1.1.1"), _proxy("2.2.2.2")
    pool.add_many([p1, p2])
    pool.record_throughput(p1, 500.0)
    assert (p2["host"], p2["port"]) not in pool._throughput
    # get_next in modalita' throughput non deve sollevare anche se p2 non e'
    # mai stato misurato.
    pool.selection_mode = "throughput"
    pool.n_connections = 1
    for _ in range(4):
        assert pool.get_next() is not None


# ---- Telemetria di sessione: discarded_count / refill_count -------------

def test_discarded_count_increments_once_per_alive_to_dead_transition():
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    assert pool.discarded_count() == 0
    rounds = abs(POOL_SCORE_DEAD_THRESHOLD) // abs(POOL_SCORE_ON_FAILURE) + 2
    for _ in range(rounds):
        pool.record_failure(p)
    # Una sola transizione vivo->morto avvenuta durante il loop.
    assert pool.discarded_count() == 1
    # Ulteriori fallimenti sul proxy gia' morto non incrementano di nuovo.
    pool.record_failure(p)
    assert pool.discarded_count() == 1


def test_discarded_count_not_affected_by_penalize_hard():
    # penalize(hard=True) non passa da record_failure: non e' nello scope
    # dell'istruzione (solo record_failure e' instrumentato).
    pool = ProxyPool()
    p = _proxy()
    pool.add_many([p])
    pool.penalize(p, hard=True)
    assert pool.discarded_count() == 0


def test_refill_count_and_last_refill_via_note_refill():
    pool = ProxyPool()
    assert pool.refill_count() == 0
    assert pool.seconds_since_last_refill() is None
    pool.note_refill()
    assert pool.refill_count() == 1
    elapsed = pool.seconds_since_last_refill()
    assert elapsed is not None and elapsed >= 0
    pool.note_refill()
    assert pool.refill_count() == 2


def test_refill_blocking_calls_note_refill_on_success():
    pool = ProxyPool(refill_fn=lambda: [_proxy()])
    pool.refill_blocking(force=True)
    assert pool.refill_count() == 1
    assert pool.seconds_since_last_refill() is not None


def test_refill_blocking_skip_branch_does_not_call_note_refill():
    pool = ProxyPool(refill_fn=lambda: [_proxy()])
    pool.add_many([_proxy("9.9.9.9")])  # pool non vuoto
    pool.refill_blocking(force=False)  # skip: size() > 0
    assert pool.refill_count() == 0


def test_throughput_mode_prefers_fast_proxies_with_rotation():
    pool = ProxyPool(selection_mode="throughput", n_connections=1)
    fast = _proxy("1.1.1.1")
    slow = _proxy("2.2.2.2")
    very_slow = _proxy("3.3.3.3")
    pool.add_many([fast, slow, very_slow])
    pool.record_throughput(fast, 5_000_000.0)
    pool.record_throughput(slow, 500_000.0)
    pool.record_throughput(very_slow, 1_000.0)
    # K = n_connections(1) * POOL_THROUGHPUT_TOPK_FACTOR(2) = 2 -> top-2 piu'
    # veloci (fast, slow) ruotati; il piu' lento resta fuori dalla rotazione.
    seen = {(pool.get_next() or {}).get("host") for _ in range(10)}
    assert seen == {"1.1.1.1", "2.2.2.2"}
    assert "3.3.3.3" not in seen
