# Costanti globali dell'applicazione.
from pathlib import Path

APP_VERSION = "1.12.0"
APP_LICENSE = "MIT"

# Repository GitHub usato dal controllo aggiornamenti (scheda Info).
GITHUB_OWNER = "SuperPHaze"
GITHUB_REPO = "mega-downloader-proxy-rotator"

# Identita' (branding) sovrascrivibile da manifest remoto: nome, acronimo,
# autore, nick, link, logo. TOOL_ID identifica la sezione di questo tool nel
# manifest multi-tool. BRANDING_MANIFEST_URL vuoto = branding remoto
# disattivato, si usano solo i default sotto (vedi core/branding.py per la
# risoluzione a 3 livelli: default -> cache locale -> override remoto).
TOOL_ID = "mdpr"
BRANDING_MANIFEST_URL = "https://raw.githubusercontent.com/SuperPHaze/branding/main/manifest.json"

DEFAULT_APP_NAME = "Mega Downloader Proxy Rotator"
DEFAULT_APP_ACRONYM = "MDPR"
DEFAULT_AUTHOR = "Alese (SuperPietro) Haze"
DEFAULT_NICK = "SuperPHaze"
DEFAULT_LINKS = {"github": "https://github.com/SuperPHaze"}

# Numero di cicli di download eseguiti per ogni link Mega.
# Originariamente 3 per il test di rotazione IP (riscaricare lo stesso file N
# volte da proxy diversi e verificare che Mega non rate-limiti). Test superato
# in data 2026-05-31: ora il tool e' usato per il download reale, ciclo singolo.
DOWNLOAD_CYCLES = 1

# Timeout (secondi) per ogni richiesta HTTP attraverso un proxy.
PROXY_TIMEOUT = 8

# Timeout separati per i download via proxy.
# Connect: TCP handshake fino al proxy. Sotto 10s scartiamo: i free proxy
# che ci mettono di piu' non valgono il tempo di attesa.
# Read: tempo massimo senza ricevere byte una volta connessi. Se un proxy
# trickle-streama o si pianta a meta', kill rapido per recuperare via retry.
PROXY_CONNECT_TIMEOUT = 10
PROXY_READ_TIMEOUT = 30

# Endpoint per il check dell'IP uscente effettivo.
IP_CHECK_URL = "https://api.ipify.org"

# Cartella radice dove vengono salvati i file scaricati.
# Risolta rispetto alla root del progetto (parent di src/), NON alla CWD del
# processo: cosi' i file finiscono sempre nella stessa cartella anche se l'app
# viene lanciata da una directory diversa.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = _PROJECT_ROOT / "downloads"

# Icona dell'applicazione (finestra + barra applicazioni). Preferito il .ico
# multi-dimensione (Windows, contiene 16/24/32/48/64/128/256); fallback al
# .png se l'.ico non e' presente o non si carica. Percorsi relativi alla
# root del progetto, mai assoluti della macchina.
ASSETS_DIR = _PROJECT_ROOT / "assets"
APP_ICON_ICO_PATH = ASSETS_DIR / "icon.ico"
APP_ICON_PNG_PATH = ASSETS_DIR / "icon.png"
APP_ICON_PATH = APP_ICON_ICO_PATH if APP_ICON_ICO_PATH.exists() else APP_ICON_PNG_PATH

# Logo cotto nell'app per la scheda Info, scelto in base al tema (vedi
# preferences.load_dark_theme()) quando non c'e' un logo remoto in cache.
LOGO_LIGHT_PATH = ASSETS_DIR / "logo-light.gif"
LOGO_DARK_PATH = ASSETS_DIR / "logo-dark.gif"

# User-Agent usato per le richieste HTTP (scraping liste proxy e validazione).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Tetto massimo di proxy candidati da validare (i gratuiti sono migliaia,
# validarli tutti significa minuti di attesa anche con 20 worker paralleli).
# 3000 candidati per arrivare a un pool vivo realistico di poche decine (vedi
# VALIDATOR_TARGET_ALIVE): lo stage 2 verso Mega ha una resa molto bassa
# (~30-40 vivi anche partendo da migliaia di candidati), quindi il cap resta
# largo per dare margine, non per inseguire un target a centinaia.
MAX_PROXIES_TO_VALIDATE = 12000

# Validazione a due stadi.
# Stage 1: "il proxy funziona?" — pre-filtro veloce su un endpoint di
# connectivity-check affidabile e ad alto volume (NON giudica Mega, solo
# se il proxy regge un round-trip HTTP). generate_204 di Google e' pensato
# esattamente per questo: risposta 204 vuota, infrastruttura enorme, niente
# dei falsi negativi che httpbin.org/ip produceva quando era sotto carico.
# Alta concorrenza, timeout aggressivi: scarta i proxy morti senza
# sprecare un round-trip sulla capacita' limitata del test Mega (stage 2).
VALIDATOR_STAGE1_WORKERS = 200
VALIDATOR_STAGE1_TIMEOUT = 4                                # connect+read combinati
VALIDATOR_STAGE1_URL = "http://www.gstatic.com/generate_204"

# Stage 2: "il proxy raggiunge l'infrastruttura di DOWNLOAD Mega?" — punta
# all'host dell'API Mega (lo stesso usato dal resolve reale, vedi
# downloader/mega_api.py:API_URL), non alla homepage: i download veri non
# passano dalla vetrina, e un proxy che non risolve un link e' inutile a
# prescindere da come risponde mega.nz/. Criterio di successo: QUALSIASI
# risposta HTTP ricevuta dall'host, anche un errore applicativo (es. "-2"
# su una GET senza payload valido) — significa che il roundtrip e' arrivato
# a destinazione. Non richiediamo 200: un criterio troppo severo qui
# scarterebbe proxy che funzionano benissimo per il download (falso
# negativo), esattamente il difetto che questo stage deve evitare.
# Concorrenza moderata (Mega rate-limita) e stop anticipato al target,
# invariati rispetto a prima.
VALIDATOR_STAGE2_WORKERS = 120
VALIDATOR_STAGE2_TIMEOUT = PROXY_TIMEOUT                    # resta 8s
VALIDATOR_STAGE2_URL = "https://g.api.mega.co.nz/cs"

# Target proxy vivi: se raggiunto, la validazione si ferma in anticipo
# (cancellando i future rimanenti). None = valida tutto.
# La resa reale dello stage 2 (raggiungibilita' Mega) e' bassa: anche con
# migliaia di candidati si arriva tipicamente a ~30-40 proxy vivi. Un target
# di 200 era irraggiungibile e teneva il pool sempre "sotto soglia" agli
# occhi del refresher; 60 e' un tetto realistico che lascia comunque scattare
# l'early-stop nelle sessioni piu' fortunate, senza inseguire un numero che
# non si raggiunge mai.
VALIDATOR_TARGET_ALIVE = 300

# DEPRECATO: alias retro-compatibile per VALIDATOR_STAGE2_WORKERS.
# Codice nuovo deve usare VALIDATOR_STAGE2_WORKERS direttamente.
VALIDATOR_WORKERS = VALIDATOR_STAGE2_WORKERS

# Numero di download contemporanei (DEFAULT INIZIALE).
# Era 3. Default ora sequenziale: con tanti link e proxy gratuiti,
# parallelizzare i file moltiplica la pressione sul pool e degrada
# tutti i download. L'utente puo' alzarlo dalla GUI tramite lo spinbox
# "Download paralleli". Range consigliato: 1-5.
MAX_CONCURRENT_DOWNLOADS = 1

# Numero di connessioni HTTP Range parallele PER SINGOLO file.
# Mega.py nativo scarica seriale: aggiriamo risolvendo la URL CDN via mega.py
# e poi facendo N richieste con Range: bytes=..., ognuna con un proxy diverso.
# 1 = comportamento legacy (mega.py monolitico). >1 = parallel client.
PARALLEL_CONNECTIONS_PER_FILE = 10

# Limiti residui del motore (non piu' esposti in GUI dalla 1.9.0: la scheda
# Funzioni Sperimentali e' stata svuotata). PARALLEL_CONNECTIONS_PER_FILE
# resta il DEFAULT; il range [MIN, MAX] e' mantenuto per riuso futuro.
PARALLEL_CONNECTIONS_MIN = 2
# Alzato da 16 a 64 per consentire lo sweep di N della campagna telemetria
# (15 -> 25 -> 40): con linee larghe servono molte piu' corsie per saturare la
# banda. Lo spinbox in experimental_dialog.py usa questa costante come massimo.
PARALLEL_CONNECTIONS_MAX = 64

# Dimensione minima di un segmento parallelo. File piu' piccoli vanno
# direttamente in seriale (non vale la pena di splittarli).
PARALLEL_MIN_SEGMENT_BYTES = 1 * 1024 * 1024  # 1 MiB

# Tentativi per singolo segmento prima di considerare il download fallito.
# Alzato perche' i free proxy hanno mortalita' alta e ora i timeout sono brevi,
# quindi anche 8 tentativi finiscono in pochi minuti nel caso peggiore.
PARALLEL_SEGMENT_RETRIES = 8

# Backoff massimo (s) tra tentativi consecutivi per lo stesso segmento.
PARALLEL_SEGMENT_BACKOFF_MAX = 8

# Refresh proxy in background: il refresher controlla la dimensione del pool
# a intervalli regolari e, se scende sotto la soglia, lancia uno scrape+validate
# senza bloccare i worker (che intanto continuano a usare i proxy gia' presenti).
POOL_REFRESH_INTERVAL = 30          # secondi tra check

# Isteresi armato/disarmato (vedi proxy/refresher.py): senza isteresi, un pool
# che oscilla intorno a una soglia singola scatena refill ripetuti a raffica
# (osservato: 66 refill in una sessione, ~200 thread di picco -> access
# violation nei thread di validazione). Con isteresi il refresher si "disarma"
# dopo un refill e si riarma solo quando il pool torna sano (>= HIGH).
# Soglie dimensionate sulla resa reale dello stage 2 (~30-40 vivi tipici, vedi
# VALIDATOR_TARGET_ALIVE): LOW < HIGH < resa tipica, altrimenti il refresher
# non si riarmerebbe mai (HIGH >= resa reale = disarmato per sempre) oppure
# scatenerebbe un refill quasi a ogni ciclo (LOW troppo vicino alla resa).
POOL_REFRESH_THRESHOLD_LOW = 80     # armato + vivi < LOW -> refill, poi disarma
POOL_REFRESH_THRESHOLD_HIGH = 160   # disarmato + vivi >= HIGH -> riarma
POOL_REFRESH_MIN_INTERVAL_S = 45    # mai due refill a meno di N secondi l'uno dall'altro

# DEPRECATO: alias retro-compatibile pre-isteresi. Codice nuovo deve usare
# POOL_REFRESH_THRESHOLD_LOW / _HIGH.
POOL_REFRESH_THRESHOLD = POOL_REFRESH_THRESHOLD_LOW

# Dimensione di ogni chunk nella coda parallela (MB). Deve essere multiplo di
# 16 byte (block AES — i MB lo sono sempre). Pezzi più piccoli = più resistenza
# al cambio proxy, più richieste HTTP al CDN. Default GUI configurabile.
PARALLEL_CHUNK_SIZE_MB = 32

# Abort soft della coda chunk: se questo numero di chunk ha esaurito TUTTI i
# retry, il download viene interrotto (i chunk completati restano nel sidecar).
# Il worker rilancia e riprende dal punto lasciato. Con N=3 si tollera
# un'instabilità momentanea senza sprecare i byte già scaricati.
PARALLEL_MAX_FAILED_CHUNKS = 3

# Watchdog throughput per segmento: se la velocita' media negli ultimi
# WINDOW secondi scende sotto MIN_BPS, abortiamo il tentativo e cambiamo
# proxy. NOTA: l'esperimento "slow-kill aggressivo" (400 KB/s, window 12,
# grace 10) ha REGREDITO — run 20260627-194714: corsie attive 14->6, util
# 18%->5%, vincolo lane_supply_bound (il pool non regge le corsie quando si
# scartano troppi proxy troppo presto). Ripristinati i valori baseline.
PARALLEL_MIN_THROUGHPUT_BPS = 200 * 1024  # 200 KB/s minimi (baseline)
PARALLEL_THROUGHPUT_WINDOW = 20           # finestra di misura (s) (baseline)
# Grace period iniziale: i primi N secondi non valutiamo throughput,
# diamo tempo al TCP slow-start e al primo buffer.
PARALLEL_THROUGHPUT_GRACE = 15            # (baseline)

# 429 "Too Many Concurrent IP Addresses": e' un limite PER-FILE di Mega sul
# numero di IP DISTINTI che scaricano lo stesso file contemporaneamente (NON un
# problema del singolo proxy). Cambiare proxy su un 429 AGGIUNGE un IP nuovo e
# PEGGIORA il limite (spirale di 429 -> abbandono). La risposta corretta e'
# ri-provare lo STESSO proxy (stesso IP) dopo un backoff, lasciando decadere il
# conteggio IP concorrenti lato Mega. Questo backoff base (s) viene scalato per
# tentativo. Il proxy NON viene penalizzato (non e' colpa sua).
PARALLEL_HTTP_429_BACKOFF_S = 6
PARALLEL_HTTP_429_BACKOFF_MAX_S = 20

# Budget temporale ASSOLUTO per singolo tentativo di segmento. A prescindere
# dal throughput istantaneo, se un tentativo dura piu' di N secondi viene
# abortito e il proxy marcato dead. Difesa contro proxy che si mantengono
# appena sopra la soglia throughput ma non finiscono mai in tempi sensati.
PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S = 180

# Tetto di sicurezza anti-spike per i campioni di velocita' di sessione
# (SessionSpeedStats, sparkline GUI). Puramente difensivo: un campione sopra
# questo valore e' impossibile per questo downloader e viene scartato senza
# avvelenare il picco. Non deve mai scartare velocita' reali raggiungibili.
SPEED_SAMPLE_CEILING_BPS = 1_073_741_824  # 1 GiB/s

# Refresh forzato del pool a intervalli regolari: se l'ultimo refill e' avvenuto
# piu' di N secondi fa, rinfresca a prescindere dalla soglia. Serve quando il
# pool oscilla appena sopra POOL_REFRESH_THRESHOLD ma i proxy si degradano
# silenziosamente (rate-limit progressivo, scadenze, captive portal).
POOL_REFRESH_MAX_INTERVAL_S = 300

# Limite di durata wall-clock per singolo file (minuti). Superato, il file
# viene abbandonato e lo slot passa al successivo. Configurabile dalla GUI.
# Il limite include il tempo di pausa (wall-clock, non CPU time).
MAX_FILE_DURATION_MINUTES = 60

# Numero massimo di tentativi consecutivi falliti per un singolo link
# prima di abbandonarlo. Evita loop infiniti su link irraggiungibili
# (file rimosso, hash invalido, regione bloccata, ecc.).
# Il conteggio NON si resetta tra cicli diversi dello stesso link.
MAX_ATTEMPTS_PER_FILE = 15

# Cartella unica per log diagnostici/operativi e report generati.
LOGS_DIR = _PROJECT_ROOT / "logs"
REPORTS_DIR = LOGS_DIR / "reports"

# Log strutturato universale (JSON Lines, un record per riga, livello DEBUG:
# massimo dettaglio). Sorgente primaria per tools/report.py.
EVENTS_LOG = "events.jsonl"
EVENTS_LOG_MAX_BYTES = 20_000_000   # 20 MB: il JSONL a DEBUG cresce più di app.log
EVENTS_LOG_BACKUPS = 5

# ---------------------------------------------------------------------------
# Telemetria "scatola nera" (Fase 1 — cattura grezza per analisi offline)
# ---------------------------------------------------------------------------
# Recorder strutturato asincrono: un record per tentativo-chunk + campioni a
# 1 Hz, su file separati per sessione in logs/telemetry/<session_id>/. Il
# thread di download fa solo enqueue O(1); un writer daemon scrive a batch.
# Disattivabile a costo zero (ogni hook diventa un no-op).
TELEMETRY_ENABLED = True
TELEMETRY_DIR = LOGS_DIR / "telemetry"
# Intervallo (s) di flush del writer asincrono. Più basso = meno backlog in RAM,
# più write; più alto = batch più grandi. 0.25s è un buon compromesso.
TELEMETRY_FLUSH_INTERVAL_S = 0.25
# Campionamento aggregato del download (s). 1 Hz è sufficiente per la curva di
# throughput nel tempo senza gonfiare samples.jsonl.
TELEMETRY_SAMPLE_INTERVAL_S = 1.0
# Firehose intra-chunk: tieni il delta di ogni lettura da 64 KB dentro il record
# del tentativo-chunk (array compatto [t_offset_ms, cum_bytes]). 0 = illimitato
# (firehose pieno). >0 = tetto di sicurezza sul numero di campioni per chunk
# (downsampling oltre il tetto) per evitare record patologici su chunk enormi.
TELEMETRY_INTRA_CHUNK_MAX_SAMPLES = 0

# File log dedicato ai link abbandonati. Una riga per link, formato
# JSON Lines per parsing successivo. Rotante per evitare crescita
# illimitata su sessioni molto lunghe.
FAILED_LINKS_LOG = "failed_links.log"
FAILED_LINKS_LOG_MAX_BYTES = 2_000_000
FAILED_LINKS_LOG_BACKUPS = 3

# Storico persistente dei download completati (JSONL rotante, stesso schema
# di failed_links.log). Usato per avvisare l'utente quando reinserisce un
# link gia' scaricato in una sessione precedente (dedup per handle Mega).
DOWNLOAD_HISTORY_LOG = "download_history.log"
DOWNLOAD_HISTORY_LOG_MAX_BYTES = 2_000_000
DOWNLOAD_HISTORY_LOG_BACKUPS = 3

# Log delle metriche per-fonte (scraping + survival post-validazione).
# Rotante per evitare crescita illimitata su sessioni lunghe.
SOURCES_STATS_LOG = "proxy_sources_stats.log"
SOURCES_STATS_LOG_MAX_BYTES = 2_000_000
SOURCES_STATS_LOG_BACKUPS = 3

# Cattura grezza di tutto l'output del terminale (stdout+stderr) della sessione
# corrente. Riazzerato a ogni avvio (mode "w"): contiene solo l'ultima sessione.
# Diagnostico/condivisibile: NON è il log strutturato (vedi events.jsonl).
TERMINAL_LOG = "terminal-log.txt"

# Pool a punteggio reputazionale.
# Ogni successo alza il punteggio, ogni fallimento lo abbassa. Un proxy
# sotto SCORE_DEAD_THRESHOLD è considerato morto ma viene riabilitato al
# refill successivo se ricompare nelle liste fonti.
# Score=0 al primo ingresso. Stage 1 alive NON chiama record_success: la
# prima reazione utile è il primo successo/fallimento applicativo (download).
POOL_SCORE_INITIAL = 0
POOL_SCORE_ON_SUCCESS = 5
POOL_SCORE_ON_FAILURE = -10
POOL_SCORE_DEAD_THRESHOLD = -20
POOL_SCORE_MAX = 100

# Cooldown (secondi) per un proxy che ha ricevuto un rate-limit dal CDN Mega
# (403/509): viene escluso dalla rotazione per questo tempo e poi torna
# disponibile, invece di essere scartato definitivamente. Evita di svuotare il
# pool su sessioni lunghe (il 403/509 è temporaneo, non un proxy morto).
PROXY_COOLDOWN_SECONDS = 90

# Latency-aware selection.
# Quando due proxy hanno score identico, viene scelto quello con latency_ms minore.
# Se latency_ms è ignota (None), il proxy va in fondo alla coda di pari-score.
# Il valore è popolato dal validator Stage 1 (o upstream da fonti come Databay).
POOL_LATENCY_TIEBREAKER = True

# Selezione per throughput osservato (Leva B della scheda Funzioni
# Sperimentali, default OFF -> selection_mode resta "score"). EMA dei bps
# misurati per proxy: ema = alpha*nuovo + (1-alpha)*vecchio. K = connessioni
# * FACTOR determina quanti dei proxy piu' veloci entrano in rotazione
# round-robin (non si pesca sempre il singolo migliore, altrimenti si
# brucia il proxy top con il rate-limit di Mega sullo stesso IP).
POOL_THROUGHPUT_EMA_ALPHA = 0.3
POOL_THROUGHPUT_TOPK_FACTOR = 2

# Intervallo (secondi) dell'heartbeat diagnostico: una riga INFO su app.log
# con memoria/thread/job attivi/pool vivi. Serve a vedere l'ora dell'ultimo
# respiro prima di un crash silenzioso (es. di notte su hardware leggero) e
# la curva della memoria nel tempo (diagnosi OOM/leak).
HEARTBEAT_INTERVAL_S = 120

# Cache dei proxy validati: persistita su disco tra sessioni per evitare
# lo scrape iniziale "da zero" (~30-120s) ogni volta. Il file e' relativo
# alla root del progetto (stesso schema di app.log / failed_links.log /
# proxy_sources_stats.log: viene risolto come absolute path nel modulo
# `proxy/proxy_cache.py`).
PROXY_CACHE_PATH = "proxy_cache.json"
PROXY_CACHE_TTL_S = 6 * 3600               # entry oltre TTL = scartate al load
PROXY_CACHE_SAVE_INTERVAL_S = 300          # salvataggio periodico
PROXY_CACHE_SCHEMA_VERSION = 1             # incrementare al cambio formato
PROXY_CACHE_MIN_SCORE_FOR_PERSISTENCE = 0  # solo proxy con score >= soglia

# ---------------------------------------------------------------------------
# Selezione per velocita' (Funzioni Sperimentali)
# ---------------------------------------------------------------------------
# Se abilitata, cambia il profilo di download: piu' candidati (5000 vs 3000),
# validazione a 3 stadi con speed test reale, connessioni ridotte (5 vs 10),
# selezione round-robin basata su throughput EMA (top-K).
SPEED_SELECTION_ENABLED = False                        # default off
SPEED_SELECTION_MIN_BPS = 500 * 1024                   # 500 KB/s soglia preferenza (GUI)
SPEED_SELECTION_ADMISSION_BPS = 100 * 1024             # 100 KB/s soglia ammissione (fissa)
SPEED_SELECTION_DEFAULT_CONNECTIONS = 5                # connessioni per file quando attivo
SPEED_SELECTION_MAX_CANDIDATES = 5000                  # candidati alla validazione quando attivo

# Stage 3: speed test reale (solo quando selezione per velocita' attiva).
# Scarica VALIDATOR_SPEED_TEST_BYTES da un server esterno (NON Mega) per
# misurare il throughput. L'URL deve essere un file statico su un server ad
# alta banda, HTTP puro, nessun redirect.
VALIDATOR_SPEED_TEST_URL = "http://speedtest.tele2.net/1MB.zip"
VALIDATOR_SPEED_TEST_BYTES = 1 * 1024 * 1024           # 1 MB
VALIDATOR_SPEED_TEST_TIMEOUT = 15                      # connect+read per proxy
VALIDATOR_SPEED_TEST_WORKERS = 30                      # concorrenza stage 3

# Soglia refill adattiva (solo con selezione per velocita' attiva).
# La soglia statica (POOL_REFRESH_THRESHOLD_LOW/HIGH) viene sostituita da
# una soglia dinamica calcolata in base al fabbisogno reale:
#   soglia_low = max(FLOOR, download_attivi * connessioni * MOLTIPLICATORE)
#   soglia_high = soglia_low * 2
# Questo evita refill inutili quando il carico e' basso (pochi download,
# poche connessioni) e aumenta la soglia quando il carico cresce.
ADAPTIVE_REFILL_FLOOR = 10           # proxy minimi anche con 0 download attivi
ADAPTIVE_REFILL_MULTIPLIER = 3       # margine per mortalita' naturale dei proxy

# ---------------------------------------------------------------------------
# Speed test della LINEA dell'utente (diretto, FUORI dai proxy)
# ---------------------------------------------------------------------------
# Misura la banda disponibile da mostrare in GUI e usare come denominatore per
# la "% di linea usata" nell'analisi telemetria. Parallelo perche' una singola
# connessione TCP spesso non satura una linea larga (slow-start + limiti
# per-connessione): K stream diretti danno una stima realistica di cio' che il
# downloader multi-connessione puo' sfruttare.
LINE_SPEEDTEST_URL = "http://speedtest.tele2.net/10MB.zip"
LINE_SPEEDTEST_STREAMS = 4          # connessioni dirette parallele
LINE_SPEEDTEST_TIMEOUT = 20         # secondi per stream
