# Test per MegaPublicClient._api_request: retry su -3 (EAGAIN), cancellazione
# cooperativa (should_abort) durante il backoff, codici errore. Nessuna rete:
# la sessione requests è sostituita da una fake; time.sleep è neutralizzato.
import pytest

from src.downloader import mega_api
from src.downloader.mega_api import MegaApiError, MegaPublicClient


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # Il backoff non deve dormire davvero nei test.
    monkeypatch.setattr(mega_api.time, "sleep", lambda _s: None)


def _client(responses, should_abort=None):
    client = MegaPublicClient(should_abort=should_abort)
    seq = list(responses)
    state = {"i": 0}

    def fake_post(*_a, **_k):
        r = seq[min(state["i"], len(seq) - 1)]
        state["i"] += 1
        return r

    client._session.post = fake_post
    return client, state


def test_success_returns_dict():
    client, _ = _client([_FakeResp('[{"g": "http://x", "s": "10"}]')])
    assert client._api_request({"a": "g"}) == {"g": "http://x", "s": "10"}


def test_code_zero_returns_empty_dict():
    client, _ = _client([_FakeResp("[0]")])
    assert client._api_request({"a": "x"}) == {}


def test_eagain_minus3_retries_then_succeeds():
    client, state = _client([_FakeResp("[-3]"), _FakeResp('[{"ok": 1}]')])
    assert client._api_request({"a": "g"}) == {"ok": 1}
    assert state["i"] == 2  # ha davvero ritentato


def test_error_code_raises_with_code():
    client, _ = _client([_FakeResp("[-9]")])
    with pytest.raises(MegaApiError) as exc:
        client._api_request({"a": "g"})
    assert exc.value.code == -9


def test_should_abort_interrupts_backoff_on_minus3():
    # should_abort=True: il backoff dopo un -3 esce subito con errore, senza
    # esaurire i 5 tentativi.
    client, state = _client([_FakeResp("[-3]")], should_abort=lambda: True)
    with pytest.raises(MegaApiError, match="annullato"):
        client._api_request({"a": "g"})
    assert state["i"] == 1  # un solo POST, poi abort nel backoff


def test_retries_exhausted_raises():
    client, state = _client([_FakeResp("[-3]")])  # sempre -3
    with pytest.raises(MegaApiError, match="tentativi esauriti"):
        client._api_request({"a": "g"})
    assert state["i"] == 5  # bounded a 5 tentativi
