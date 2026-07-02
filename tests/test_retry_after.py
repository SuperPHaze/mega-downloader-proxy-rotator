# Test puri per il parsing dell'header Retry-After (2.13). Nessuna rete: si usa
# un finto response con solo .headers.
from email.utils import formatdate

from src.downloader.parallel_client import ParallelMegaDownloader

_parse = ParallelMegaDownloader._retry_after_seconds


class _Resp:
    def __init__(self, headers):
        self.headers = headers


def test_absent_header_returns_none():
    assert _parse(_Resp({}), cap=60) is None


def test_seconds_form_within_cap():
    assert _parse(_Resp({"Retry-After": "5"}), cap=60) == 5.0


def test_seconds_form_capped():
    assert _parse(_Resp({"Retry-After": "9999"}), cap=60) == 60.0


def test_zero_seconds():
    assert _parse(_Resp({"Retry-After": "0"}), cap=60) == 0.0


def test_unparsable_returns_none():
    assert _parse(_Resp({"Retry-After": "domani"}), cap=60) is None


def test_http_date_in_future_is_positive_and_capped():
    future = formatdate(timeval=__import__("time").time() + 20, usegmt=True)
    secs = _parse(_Resp({"Retry-After": future}), cap=60)
    assert secs is not None
    assert 0 < secs <= 60


def test_http_date_in_past_returns_zero():
    past = formatdate(timeval=__import__("time").time() - 100, usegmt=True)
    assert _parse(_Resp({"Retry-After": past}), cap=60) == 0.0
