# Test puri per l'etichettatura del protocollo per fonte in _fetch_source.
# Nessuna rete: requests.get e' monkeypatchato con una risposta finta.
from src.proxy.scraper import ProxyScraper


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


def test_fetch_source_labels_proxies_with_source_protocol(monkeypatch):
    monkeypatch.setattr(
        "src.proxy.scraper.requests.get",
        lambda *a, **k: _FakeResponse("1.2.3.4:1080\n5.6.7.8:1080\n"),
    )
    source = {"name": "fake-socks5", "url": "http://example.invalid", "kind": "plain_text", "protocol": "socks5"}
    proxies = ProxyScraper()._fetch_source(source)
    assert len(proxies) == 2
    assert all(p["protocol"] == "socks5" for p in proxies)


def test_fetch_source_defaults_to_http_protocol(monkeypatch):
    monkeypatch.setattr(
        "src.proxy.scraper.requests.get",
        lambda *a, **k: _FakeResponse("1.2.3.4:8080\n"),
    )
    source = {"name": "fake-http", "url": "http://example.invalid", "kind": "plain_text"}
    proxies = ProxyScraper()._fetch_source(source)
    assert len(proxies) == 1
    assert proxies[0]["protocol"] == "http"
