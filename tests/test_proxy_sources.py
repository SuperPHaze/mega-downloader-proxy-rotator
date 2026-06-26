# Test puri per l'elenco fonti: integrita' dei campi e presenza delle
# liste SOCKS curate. Nessuna rete (non scarica gli URL, legge solo il dict).
from src.proxy.sources import PROXY_SOURCES

_VALID_PROTOCOLS = {"http", "socks4", "socks5"}
_VALID_KINDS = {"html_table", "plain_text", "geonode_json", "jsonl", "databay_json", "proxyscrape_json"}


def test_every_source_has_required_fields():
    for source in PROXY_SOURCES:
        assert "name" in source and source["name"]
        assert "url" in source and source["url"]
        assert source["kind"] in _VALID_KINDS


def test_protocol_field_is_valid_when_present():
    for source in PROXY_SOURCES:
        assert source.get("protocol", "http") in _VALID_PROTOCOLS


def test_source_names_are_unique():
    names = [s["name"] for s in PROXY_SOURCES]
    assert len(names) == len(set(names))


def test_socks_sources_are_all_plain_text():
    # Le fonti proxyscrape_json possono avere protocollo socks: escluse dall'asserzione sul kind.
    socks_sources = [
        s for s in PROXY_SOURCES
        if s.get("protocol") in ("socks4", "socks5") and s["kind"] != "proxyscrape_json"
    ]
    assert len(socks_sources) >= 19  # 14 socks5 + 5 socks4 curate + hookzof preesistente
    assert all(s["kind"] == "plain_text" for s in socks_sources)


def test_hookzof_source_is_socks5():
    hookzof = next(s for s in PROXY_SOURCES if s["name"] == "hookzof-socks5")
    assert hookzof["protocol"] == "socks5"


def test_curated_socks5_sources_present():
    names = {s["name"] for s in PROXY_SOURCES}
    expected = {
        "thespeedx-socks5", "monosans-socks5", "shiftytr-socks5", "jetkai-socks5",
        "roosterkid-socks5", "mmpx12-socks5", "vakhov-socks5", "zloi-user-socks5",
        "rdavydov-socks5", "zaeem20-socks5", "ercindedeoglu-socks5", "thordata-socks5",
        "yemixzy-socks5", "proxifly-socks5",
    }
    assert expected <= names
    for name in expected:
        source = next(s for s in PROXY_SOURCES if s["name"] == name)
        assert source["protocol"] == "socks5"


def test_curated_socks4_sources_present():
    names = {s["name"] for s in PROXY_SOURCES}
    expected = {
        "thespeedx-socks4", "monosans-socks4", "shiftytr-socks4",
        "roosterkid-socks4", "jetkai-socks4",
    }
    assert expected <= names
    for name in expected:
        source = next(s for s in PROXY_SOURCES if s["name"] == name)
        assert source["protocol"] == "socks4"
