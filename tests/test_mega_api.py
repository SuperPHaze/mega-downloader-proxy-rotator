# Test per MegaPublicClient._api_request: retry su -3 (EAGAIN), cancellazione
# cooperativa (should_abort) durante il backoff, codici errore. Nessuna rete:
# la sessione requests è sostituita da una fake; time.sleep è neutralizzato.
import base64
import json
import struct

import pytest

from src.core.mega_links import build_folder_job_url
from src.downloader import mega_api
from src.downloader.mega_api import MegaApiError, MegaPublicClient


def _b64_key(words):
    """a32 -> base64url senza padding, come nei job-cartella."""
    raw = struct.pack(">%dI" % len(words), *words)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


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
    # Il codice numerico dell'API Mega non e' piu' un attributo a parte:
    # sta fra i parametri del messaggio, insieme a tutto il resto.
    client, _ = _client([_FakeResp("[-9]")])
    with pytest.raises(MegaApiError) as exc:
        client._api_request({"a": "g"})
    assert exc.value.error_code == "api_error_code"
    assert exc.value.params["api_code"] == -9
    assert str(exc.value) == "API Mega ha risposto codice -9"


def test_should_abort_interrupts_backoff_on_minus3():
    # should_abort=True: il backoff dopo un -3 esce subito con errore, senza
    # esaurire i 5 tentativi.
    client, state = _client([_FakeResp("[-3]")], should_abort=lambda: True)
    with pytest.raises(MegaApiError, match="annullato") as exc:
        client._api_request({"a": "g"})
    assert exc.value.error_code == "resolve_cancelled"
    assert state["i"] == 1  # un solo POST, poi abort nel backoff


def test_retries_exhausted_raises():
    client, state = _client([_FakeResp("[-3]")])  # sempre -3
    with pytest.raises(MegaApiError, match="tentativi esauriti") as exc:
        client._api_request({"a": "g"})
    assert exc.value.error_code == "api_retries_exhausted"
    assert state["i"] == 5  # bounded a 5 tentativi


# ---- parametri di query extra (cartelle condivise) -------------------------

def _client_capturing():
    """Client la cui POST registra params/data invece di andare in rete."""
    client = MegaPublicClient()
    seen = {}

    def fake_post(url, params=None, data=None, timeout=None):
        seen["url"] = url
        seen["params"] = params
        seen["data"] = data
        return _FakeResp('[{"g": "http://cdn/x", "s": "42", "at": ""}]')

    client._session.post = fake_post
    return client, seen


def test_extra_params_land_in_the_query_string():
    client, seen = _client_capturing()
    client._api_request({"a": "f", "c": 1, "r": 1}, extra_params={"n": "FOLDERID"})
    assert seen["params"]["n"] == "FOLDERID"
    assert "id" in seen["params"]        # il seq number resta


def test_without_extra_params_only_id_is_sent():
    client, seen = _client_capturing()
    client._api_request({"a": "g"})
    assert list(seen["params"]) == ["id"]


def test_list_folder_sends_recursive_listing_request():
    client = MegaPublicClient()
    seen = {}

    def fake_post(url, params=None, data=None, timeout=None):
        seen["params"] = params
        seen["data"] = data
        return _FakeResp('[{"f": [{"h": "A", "t": 2}, "non-dict"]}]')

    client._session.post = fake_post
    nodes = client.list_folder("FOLDERID")
    assert json.loads(seen["data"]) == [{"a": "f", "c": 1, "r": 1, "ca": 1}]
    assert seen["params"]["n"] == "FOLDERID"
    # I nodi non-dict della risposta vengono scartati, non fanno esplodere.
    assert nodes == [{"h": "A", "t": 2}]


def test_list_folder_without_f_raises():
    client, _ = _client_capturing()   # risponde con 'g', non con 'f'
    with pytest.raises(MegaApiError, match="elenco della cartella") as exc:
        client.list_folder("FOLDERID")
    assert exc.value.error_code == "folder_listing_unavailable"


# ---- resolve di un nodo dentro una cartella --------------------------------

JOB_URL = build_folder_job_url(
    "FOLDERID", "NODE1", _b64_key((1, 2, 3, 4, 5, 6, 7, 8)), ("Cart", "sub", "f.bin"),
)


def test_folder_job_resolve_uses_node_in_payload_and_folder_in_query():
    client, seen = _client_capturing()
    info = client.resolve_public_url(JOB_URL)
    # Doppio uso di 'n': handle del NODO nel payload, id della CARTELLA in query.
    assert json.loads(seen["data"]) == [{"a": "g", "g": 1, "n": "NODE1"}]
    assert seen["params"]["n"] == "FOLDERID"
    assert info["handle"] == "NODE1"
    assert info["cdn_url"] == "http://cdn/x"
    assert info["file_size"] == 42


def test_folder_job_file_name_comes_from_the_job_not_from_the_attributes():
    # Il nome e' gia' stato deciso (sanificato e de-collisionato) in fase di
    # espansione: il path su disco deve restare stabile fra i retry.
    client, _ = _client_capturing()
    assert client.resolve_public_url(JOB_URL)["file_name"] == "f.bin"


def test_folder_job_key_is_the_already_decrypted_eight_word_key():
    client, _ = _client_capturing()
    info = client.resolve_public_url(JOB_URL)
    assert info["k"], info["iv"]
    assert info["iv"] == (5, 6, 0, 0)     # iv = (raw[4], raw[5], 0, 0)


def test_folder_job_with_short_key_raises():
    bad = build_folder_job_url("F", "N", _b64_key((1, 2, 3, 4)), ("a", "b.bin"))
    client, _ = _client_capturing()
    with pytest.raises(MegaApiError, match="troppo corta") as exc:
        client.resolve_public_url(bad)
    assert exc.value.error_code == "node_key_too_short"


def test_plain_folder_link_is_refused_with_a_clear_message():
    client, _ = _client_capturing()
    with pytest.raises(MegaApiError, match="va espanso") as exc:
        client.resolve_public_url("https://mega.nz/folder/AAA#KEYKEY")
    assert exc.value.error_code == "folder_link_not_downloadable"


def test_unparsable_url_still_raises():
    client, _ = _client_capturing()
    with pytest.raises(MegaApiError, match="non parsabile") as exc:
        client.resolve_public_url("https://example.com/nope")
    assert exc.value.error_code == "url_not_parsable"


# ---- resolve di un file singolo: nome vero, non il ripiego -----------------

def test_single_file_resolve_reads_the_real_name_from_attribs():
    # Caso reale (handle jR0jjSZK): il blob "at" catturato dal vivo ha residuo
    # non-zero dopo la '}' di chiusura (file rinominato lato Mega). Prima del
    # fix, resolve_public_url ripiegava su "mega_<handle>" pur con chiave e
    # contenuto giusti (leggibile in VLC): decrypt_attr falliva su "Extra
    # data". Qui si passa dall'URL pubblico fino al file_name finale.
    url = "https://mega.nz/file/jR0jjSZK#DwH38x_DYgk-mVttQloBGEYJ4Xv4DZ5sKhgE3-ae048"
    at = (
        "xP7WBM5hdFrJLk9ZIJicefmGITGmNbhJmKXk69KVsVhp-tjW8z0P1e-0Koi6XDBM6"
        "Uzx8uJvMy31PwU3ZHvKYtrTNLwgBeGa6ju6Wbq8Chwow3RuLp6zZl-QJo6RULEk"
    )
    client = MegaPublicClient()

    def fake_post(url_, params=None, data=None, timeout=None):
        return _FakeResp(json.dumps([{"g": "http://cdn/x", "s": "2481328318", "at": at}]))

    client._session.post = fake_post
    info = client.resolve_public_url(url)
    assert info["file_name"] == (
        "We.Were.Soldiers.Fino.All.Ultimo.Uomo.2002.ITA-ENG.BRRip.720p.x264-P92.mkv"
    )
    assert info["file_name"] != "mega_jR0jjSZK"
