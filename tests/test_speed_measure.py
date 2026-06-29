# Test della misura di throughput pura (sustained_throughput_bps) e del
# cache-buster. Niente rete, niente Qt: matematica deterministica.
#
# Regressione del bug "banda non possibile" (fix 1.13.1): il cronometro partiva
# al primo chunk del corpo, ma con i proxy che bufferizzano l'intero file e poi
# lo riversano in burst la finestra del corpo collassava verso 0 e, col floor a
# 0.001s, il throughput diventava astronomico (migliaia di Mbit/s).
from urllib.parse import urlparse, parse_qs

from src.core.proxy_url import cache_bust_url, sustained_throughput_bps

MB = 1024 * 1024


def test_normal_streaming_uses_body_window():
    # Corpo che scorre regolarmente: 1 MB in 2s di finestra corpo -> 0.5 MB/s.
    # t_request=0, t_first=1 (TTFB di 1s escluso), t_last=3.
    bps = sustained_throughput_bps(MB, t_request=0.0, t_first_byte=1.0, t_last_byte=3.0)
    assert abs(bps - MB / 2.0) < 1.0


def test_ttfb_is_excluded():
    # Stessa finestra corpo (2s) ma TTFB enorme (10s): il throughput NON deve
    # crollare per colpa del setup -> resta 0.5 MB/s, non 1MB/12s.
    bps = sustained_throughput_bps(MB, t_request=0.0, t_first_byte=10.0, t_last_byte=12.0)
    assert abs(bps - MB / 2.0) < 1.0


def test_buffered_burst_does_not_explode():
    # IL BUG: dopo un lungo TTFB (8s) il corpo arriva tutto in 0.5 ms.
    # Finestra corpo degenere -> si ricade sulla finestra completa (8.0005s),
    # ottenendo un valore plausibile, NON migliaia di Mbit/s.
    bps = sustained_throughput_bps(
        MB, t_request=0.0, t_first_byte=8.0, t_last_byte=8.0005
    )
    mbit = bps * 8 / 1_000_000
    assert mbit < 50.0, f"throughput impossibile non contenuto: {mbit:.0f} Mbit/s"
    # Coerente con la finestra completa: 1 MB / 8.0005s.
    assert abs(bps - MB / 8.0005) < 1000.0


def test_instant_transfer_capped_by_min_window():
    # Caso estremo: anche la finestra completa e' ~0 (tutto bufferizzato e
    # connessione gia' calda). Il divisore min_window evita la divisione per
    # ~zero: throughput limitato, mai infinito/impossibile.
    bps = sustained_throughput_bps(
        MB, t_request=0.0, t_first_byte=0.0001, t_last_byte=0.0002,
        min_window_s=0.05,
    )
    assert bps == MB / 0.05


def test_zero_bytes_is_zero():
    assert sustained_throughput_bps(0, 0.0, 1.0, 2.0) == 0.0


def test_cache_bust_appends_unique_param():
    u1 = cache_bust_url("http://speedtest.tele2.net/10MB.zip")
    u2 = cache_bust_url("http://speedtest.tele2.net/10MB.zip")
    assert u1 != u2  # univoco a ogni chiamata
    q = parse_qs(urlparse(u1).query)
    assert "nc" in q
    assert urlparse(u1).path == "/10MB.zip"


def test_cache_bust_respects_existing_query():
    u = cache_bust_url("http://host/file?foo=bar")
    q = parse_qs(urlparse(u).query)
    assert q["foo"] == ["bar"]
    assert "nc" in q
