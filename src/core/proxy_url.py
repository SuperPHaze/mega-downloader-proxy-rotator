# Helper unico per costruire l'URL di un proxy in base al suo protocollo.
# Solo stdlib: importabile sia da src/proxy che da src/downloader senza
# creare dipendenze incrociate fra i due layer.
from __future__ import annotations


def build_proxy_url(proxy: dict) -> str:
    """Costruisce l'URL del proxy con lo schema giusto in base al protocollo.
    socks5 -> socks5h:// (DNS risolto dal proxy, utile per gli host CDN);
    socks4 -> socks4://; tutto il resto (default) -> http://."""
    proto = (proxy.get("protocol") or "http").lower()
    host, port = proxy["host"], proxy["port"]
    if proto in ("socks5", "socks5h"):
        return f"socks5h://{host}:{port}"
    if proto == "socks4":
        return f"socks4://{host}:{port}"
    return f"http://{host}:{port}"


def build_proxies_dict(proxy: dict) -> dict:
    """Dict `requests`-compatibile (stesso URL per http e https)."""
    url = build_proxy_url(proxy)
    return {"http": url, "https": url}
