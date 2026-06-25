# Test puri per l'helper schema-aware dell'URL proxy. Nessuna rete.
from src.core.proxy_url import build_proxies_dict, build_proxy_url


def test_http_protocol_uses_http_scheme():
    assert build_proxy_url({"host": "1.2.3.4", "port": "8080", "protocol": "http"}) == "http://1.2.3.4:8080"


def test_socks5_protocol_uses_socks5h_scheme():
    assert build_proxy_url({"host": "1.2.3.4", "port": "1080", "protocol": "socks5"}) == "socks5h://1.2.3.4:1080"


def test_socks4_protocol_uses_socks4_scheme():
    assert build_proxy_url({"host": "1.2.3.4", "port": "1080", "protocol": "socks4"}) == "socks4://1.2.3.4:1080"


def test_missing_protocol_defaults_to_http():
    assert build_proxy_url({"host": "1.2.3.4", "port": "8080"}) == "http://1.2.3.4:8080"


def test_build_proxies_dict_same_url_for_http_and_https():
    proxies = build_proxies_dict({"host": "1.2.3.4", "port": "1080", "protocol": "socks5"})
    assert proxies == {"http": "socks5h://1.2.3.4:1080", "https": "socks5h://1.2.3.4:1080"}
