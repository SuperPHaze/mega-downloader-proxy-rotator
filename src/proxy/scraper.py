# Scarica le liste pubbliche di proxy e le normalizza in dict {host, port, protocol}.
from __future__ import annotations

import json
import logging
import re

import requests
from bs4 import BeautifulSoup

from src.core.config import PROXY_TIMEOUT, USER_AGENT
from src.core.sources_stats import log_source_event
from src.proxy.sources import PROXY_SOURCES

log = logging.getLogger(__name__)


class ProxyScraper:
    def __init__(self) -> None:
        self._headers = {"User-Agent": USER_AGENT}

    def fetch_all(self) -> list[dict]:
        # Raccoglie i proxy da tutte le fonti, deduplicando per host:port.
        # Tagga ogni proxy con `_source` = nome della prima fonte che lo ha
        # visto (semantica "first-wins" sul dedup): permette aggregazione
        # post-validazione delle survival stats per fonte.
        seen: set[tuple[str, str]] = set()
        result: list[dict] = []
        for source in PROXY_SOURCES:
            log.info("Scraping fonte '%s' (%s)", source["name"], source["url"])
            try:
                proxies = self._fetch_source(source)
                raw_count = len(proxies)
                log.info("Fonte '%s' -> %d proxy", source["name"], raw_count)
            except Exception as exc:
                outcome = "timeout" if isinstance(
                    exc, (requests.exceptions.Timeout,
                          requests.exceptions.ReadTimeout,
                          requests.exceptions.ConnectTimeout),
                ) else "fail"
                log.warning("Fonte '%s' fallita (%s): %s", source["name"], outcome, exc)
                try:
                    log_source_event(
                        source["name"], outcome=outcome,
                        raw_count=0, dedup_added=0, error=str(exc)[:200],
                    )
                except Exception:
                    log.debug("log_source_event fallita per '%s'", source["name"])
                continue
            dedup_added = 0
            for p in proxies:
                key = (p["host"], p["port"])
                if key in seen:
                    continue
                seen.add(key)
                p["_source"] = source["name"]
                result.append(p)
                dedup_added += 1
            log.debug("Fonte '%s' -> %d nuovi dopo dedup", source["name"], dedup_added)
            try:
                log_source_event(
                    source["name"], outcome="ok",
                    raw_count=raw_count, dedup_added=dedup_added,
                )
            except Exception:
                log.debug("log_source_event fallita per '%s'", source["name"])
        log.info("Totale proxy raccolti (dedup): %d", len(result))
        return result

    def _fetch_source(self, source: dict) -> list[dict]:
        resp = requests.get(source["url"], headers=self._headers, timeout=PROXY_TIMEOUT)
        resp.raise_for_status()
        if source["kind"] == "html_table":
            proxies = self._parse_html_table(resp.text)
        elif source["kind"] == "plain_text":
            proxies = self._parse_plain_text(resp.text)
        elif source["kind"] == "geonode_json":
            proxies = self._parse_geonode_json(resp.text)
        elif source["kind"] == "jsonl":
            proxies = self._parse_jsonl(resp.text)
        elif source["kind"] == "databay_json":
            proxies = self._parse_databay_json(resp.text)
        else:
            proxies = []
        # I parser scrivono sempre "http": il protocollo della fonte (campo
        # opzionale "protocol" in sources.py) e' la fonte di verita' e
        # sovrascrive qui, cosi' tutti i parser ereditano il comportamento
        # senza doverlo gestire uno a uno.
        protocol = source.get("protocol", "http")
        for p in proxies:
            p["protocol"] = protocol
        return proxies

    @classmethod
    def _parse_databay_json(cls, text: str) -> list[dict]:
        # Accetta sia array top-level sia dict con chiave 'data'/'proxies':
        # l'endpoint può cambiare shape, parsing difensivo.
        try:
            payload = json.loads(text)
        except ValueError:
            return []
        if isinstance(payload, dict):
            entries = payload.get("data") or payload.get("proxies") or []
        elif isinstance(payload, list):
            entries = payload
        else:
            return []
        out: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            host = entry.get("ip") or entry.get("host")
            port_raw = entry.get("port")
            if not host:
                continue
            port_str = str(port_raw)
            if not port_str.isdigit():
                continue
            item: dict = {"host": host, "port": port_str, "protocol": "http"}
            latency = entry.get("latency_ms")
            try:
                if latency is not None:
                    item["latency_ms"] = int(latency)
            except (TypeError, ValueError):
                pass
            out.append(item)
        return out

    @staticmethod
    def _parse_html_table(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        out: list[dict] = []
        table = soup.find("table")
        if not table:
            return out
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cells) < 2:
                continue
            host, port = cells[0], cells[1]
            if not host or not port.isdigit():
                continue
            out.append({"host": host, "port": port, "protocol": "http"})
        return out

    # Accetta sia "host:port" semplici sia righe con prefisso protocollo
    # (es. "http://1.2.3.4:8080", "socks5://...") che varie liste GitHub usano.
    _PLAIN_LINE_RE = re.compile(
        r"^(?:[a-zA-Z0-9+]+://)?"
        r"(?P<host>[A-Za-z0-9\.\-]+):(?P<port>\d{2,5})"
        r"(?:[/:?#].*)?$"
    )

    @classmethod
    def _parse_plain_text(cls, text: str) -> list[dict]:
        out: list[dict] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = cls._PLAIN_LINE_RE.match(line)
            if not m:
                continue
            out.append({"host": m.group("host"), "port": m.group("port"), "protocol": "http"})
        return out

    @classmethod
    def _parse_jsonl(cls, text: str) -> list[dict]:
        # Una riga = un JSON object con chiavi host/port/type (es. fate0/proxylist).
        # Righe corrotte vengono saltate silenziosamente: una fonte non deve
        # rompersi per un singolo record malformato.
        out: list[dict] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            ptype = entry.get("type")
            if ptype not in ("http", "https"):
                continue
            host = entry.get("host")
            port = entry.get("port")
            if not host:
                continue
            port_str = str(port)
            if not port_str.isdigit():
                continue
            out.append({"host": host, "port": port_str, "protocol": "http"})
        return out

    @staticmethod
    def _parse_geonode_json(text: str) -> list[dict]:
        # Formato: {"data": [{"ip": "...", "port": "...", "protocols": ["http", ...]}, ...]}
        out: list[dict] = []
        try:
            payload = json.loads(text)
        except ValueError:
            return out
        for entry in payload.get("data", []):
            host = entry.get("ip")
            port = str(entry.get("port", ""))
            if not host or not port.isdigit():
                continue
            out.append({"host": host, "port": port, "protocol": "http"})
        return out
