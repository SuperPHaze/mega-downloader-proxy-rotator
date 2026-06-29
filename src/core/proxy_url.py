# Helper unico per costruire l'URL di un proxy in base al suo protocollo.
# Solo stdlib: importabile sia da src/proxy che da src/downloader senza
# creare dipendenze incrociate fra i due layer.
from __future__ import annotations

import uuid


def cache_bust_url(url: str) -> str:
    """Aggiunge un parametro di query univoco per evitare che la risposta a uno
    speed test venga servita dalla cache (ISP, proxy trasparente, router): un
    file gia' in cache tornerebbe a velocita' di rete locale, falsando in alto
    la banda misurata fino a valori impossibili. Il server statico ignora il
    parametro sconosciuto e serve comunque il file; la cache, invece, vede un
    URL diverso a ogni richiesta."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}nc={uuid.uuid4().hex}"


def sustained_throughput_bps(
    total_bytes: int,
    t_request: float,
    t_first_byte: float,
    t_last_byte: float,
    min_window_s: float = 0.05,
) -> float:
    """Throughput sostenuto (byte/s) di un download a stream singolo.

    Tutti i tempi sono `time.monotonic()`. La misura esclude connect+TLS+TTFB
    cronometrando la sola finestra del corpo `[t_first_byte, t_last_byte]`: con
    i proxy lenti il setup vale secondi e falserebbe in BASSO un download
    piccolo.

    Ma quando il corpo arriva in burst da un buffer (tipico dei proxy che
    pre-scaricano l'intero file dall'origine durante il TTFB e poi lo riversano
    al client), quella finestra collassa verso lo zero e `byte / finestra`
    diventa un valore IMPOSSIBILE (era il bug del floor a 0.001s). In quel caso
    si ricade sulla finestra completa `[t_request, t_last_byte]`, che include il
    tempo reale di consegna end-to-end. Se anche quella e' sotto `min_window_s`,
    il trasferimento e' troppo breve per una misura affidabile e si usa
    `min_window_s` come divisore: cap implicito che evita throughput assurdi.
    """
    if total_bytes <= 0:
        return 0.0
    body_window = t_last_byte - t_first_byte
    if body_window >= min_window_s:
        return total_bytes / body_window
    full_window = t_last_byte - t_request
    return total_bytes / max(full_window, min_window_s)


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
