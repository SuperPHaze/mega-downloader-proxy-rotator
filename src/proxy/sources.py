# Elenco delle fonti di proxy gratuiti supportate.
# Per aggiungere una fonte: estendere PROXY_SOURCES e (se serve) un parser in scraper.py.
# Oggi sono 52 fonti (4 html, 45 plain, 3 json/jsonl).
#
# Tipi (`kind`) supportati:
#   - "html_table" : pagina HTML con tabella standard host/porta nelle prime due colonne.
#   - "plain_text" : righe "host:port" (eventuali blank/commenti ignorati).
#   - "geonode_json": API JSON di proxylist.geonode.com (chiavi `ip` / `port` in `data[]`).
#   - "jsonl"      : una riga = un JSON object (es. fate0/proxylist) con chiavi host/port/type.
#   - "databay_json": API JSON di databay.com con filtro Strict-SSL upstream
#                     (esclude proxy MITM-suspect). Array di {ip, port, ...}.
#
# Campo opzionale `"protocol"`: "http" (default se assente), "socks4", "socks5".
# Etichetta TUTTI i proxy di quella fonte con questo protocollo (vedi
# ProxyScraper._fetch_source in scraper.py: e' la fonte di verita', i parser
# scrivono sempre "http" e vengono sovrascritti qui). Determina lo schema
# dell'URL costruito da src/core/proxy_url.py (socks5 -> socks5h://, ecc.).

PROXY_SOURCES = [
    # --- HTML scraping ---
    {
        "name": "free-proxy-list",
        "url": "https://free-proxy-list.net/",
        "kind": "html_table",
    },
    {
        "name": "sslproxies",
        "url": "https://www.sslproxies.org/",
        "kind": "html_table",
    },
    {
        "name": "us-proxy",
        "url": "https://www.us-proxy.org/",
        "kind": "html_table",
    },
    {
        "name": "free-proxy-list-anonymous",
        "url": "https://free-proxy-list.net/anonymous-proxy.html",
        "kind": "html_table",
    },

    # --- API plain text storiche ---
    {
        "name": "proxyscrape-http",
        "url": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all",
        "kind": "plain_text",
    },
    {
        "name": "proxy-list-download-http",
        "url": "https://www.proxy-list.download/api/v1/get?type=http",
        "kind": "plain_text",
    },
    {
        "name": "openproxylist-http",
        "url": "https://api.openproxylist.xyz/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "proxyspace-http",
        "url": "https://proxyspace.pro/http.txt",
        "kind": "plain_text",
    },

    # --- Liste GitHub mantenute (refresh continuo) ---
    {
        "name": "thespeedx-http",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "monosans-http",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "clarketm-proxy-list",
        "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "kind": "plain_text",
    },
    {
        "name": "jetkai-http",
        "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "kind": "plain_text",
    },
    {
        "name": "mmpx12-http",
        "url": "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "proxifly-http",
        "url": "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
        "kind": "plain_text",
    },
    {
        "name": "hookzof-socks5",
        "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "kind": "plain_text",
        "protocol": "socks5",
    },

    # --- API JSON ---
    {
        "name": "geonode-http",
        "url": (
            "https://proxylist.geonode.com/api/proxy-list"
            "?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps"
        ),
        "kind": "geonode_json",
    },

    # --- Liste GitHub aggiuntive (refresh periodico) ---
    {
        "name": "gfpcom-http",
        "url": "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "vakhov-http",
        "url": "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "proxygenerator1-http",
        "url": "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/http_proxies.txt",
        "kind": "plain_text",
    },
    {
        "name": "shiftytr-http",
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "roosterkid-https",
        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "kind": "plain_text",
    },
    {
        "name": "murongpig-http",
        "url": "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "zloi-user-http",
        "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "b4rc0de-http",
        "url": "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
        "kind": "plain_text",
    },
    {
        "name": "proxy4parsing-http",
        "url": "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "almroot-http",
        "url": "https://raw.githubusercontent.com/almroot/proxylist/master/list.txt",
        "kind": "plain_text",
    },

    # --- API/siti pubblici aggiuntivi ---
    {
        "name": "proxyscrape-v4-http",
        "url": (
            "https://api.proxyscrape.com/v4/free-proxy-list/get"
            "?request=display_proxies&proxy_format=protocolipport&format=text&protocol=http"
        ),
        "kind": "plain_text",
    },
    {
        # Formato "host:port CC-A-S": il regex _PLAIN_LINE_RE cattura host:port a inizio riga.
        "name": "spys-me-http",
        "url": "https://spys.me/proxy.txt",
        "kind": "plain_text",
    },
    {
        # Probabilmente HTML: se il parser plain non estrae nulla, l'entry diventa
        # innocua (0 proxy) ma la fonte resta registrata per futuri parser dedicati.
        "name": "openproxy-space-http",
        "url": "https://openproxy.space/list/http",
        "kind": "plain_text",
    },

    # --- API JSON aggiuntive ---
    {
        "name": "databay-strict-ssl",
        "url": (
            "https://databay.com/api/v1/proxy-list"
            "?protocol=http&ssl=strict&format=json&limit=1000"
        ),
        "kind": "databay_json",
    },
    {
        "name": "pubproxy-fresh",
        "url": (
            "http://pubproxy.com/api/proxy"
            "?limit=20&format=txt&type=http&https=true&last_check=15"
        ),
        "kind": "plain_text",
    },

    # --- JSONL ---
    {
        "name": "fate0-proxylist",
        "url": "https://raw.githubusercontent.com/fate0/proxylist/master/proxy.list",
        "kind": "jsonl",
    },

    # --- Liste GitHub HTTP/HTTPS aggiuntive (ingrandimento pool 2026-06) ---
    {
        "name": "jetkai-https",
        "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
        "kind": "plain_text",
    },
    {
        "name": "shiftytr-https",
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "mmpx12-https",
        "url": "https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "vakhov-https",
        "url": "https://vakhov.github.io/fresh-proxy-list/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "vpslab-http-all",
        "url": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/http_all.txt",
        "kind": "plain_text",
    },
    {
        "name": "vpslab-http-ssl",
        "url": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/http_ssl.txt",
        "kind": "plain_text",
    },
    {
        "name": "vpslab-http-elite",
        "url": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/http_elite.txt",
        "kind": "plain_text",
    },
    {
        "name": "vmheaven-http",
        "url": "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/main/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "vmheaven-https",
        "url": "https://raw.githubusercontent.com/vmheaven/VMHeaven-Free-Proxy-Updated/main/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "komutan234-http",
        "url": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "rdavydov-http",
        "url": "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "zevtyardt-http",
        "url": "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "kangproxy-http",
        "url": "https://raw.githubusercontent.com/officialputuid/KangProxy/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "thordata-http",
        "url": "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "thordata-https",
        "url": "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "zaeem20-http",
        "url": "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "zaeem20-https",
        "url": "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
        "kind": "plain_text",
    },
    {
        "name": "ercindedeoglu-http",
        "url": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "yemixzy-http",
        "url": "https://raw.githubusercontent.com/yemixzy/proxy-list/main/proxies/http.txt",
        "kind": "plain_text",
    },
    {
        "name": "proxygenerator1-stable-http",
        "url": "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/Stable/http.txt",
        "kind": "plain_text",
    },
]
