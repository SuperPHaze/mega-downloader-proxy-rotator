# Dizionario italiano della GUI. L'italiano e' la FONTE: qui si scrive il testo
# originale, `strings_en.py` ne e' la traduzione (stesso insieme di chiavi).
#
# Chiavi: slug stabile "<superficie>.<elemento>" (mai la stringa italiana come
# chiave: cambiare il testo IT non deve invalidare la traduzione EN).
# Parametri: SEMPRE nominati ({name}, {path}), mai posizionali: in inglese
# l'ordine delle parti della frase cambia e con {} non si potrebbe riordinare.
# Plurali: il valore diventa un dict {"one": ..., "other": ...}, letto da `tn()`.
#
# Stato migrazione: F1 copre ControlsBar + titolo finestra. Gli altri pannelli
# hanno ancora il testo hard-coded e vengono migrati in F2.
from __future__ import annotations

STRINGS: dict[str, str | dict[str, str]] = {
    # ---- finestra principale ----------------------------------------------
    "main_window.title": "{name} v{version}",

    # ---- barra comandi: pulsanti ------------------------------------------
    "controls.start": "Avvia",
    "controls.pause": "Pausa",
    "controls.resume": "Riprendi",
    "controls.cancel": "Annulla",
    "controls.settings": "Impostazioni",
    "controls.experimental": "Sperimentale",
    "controls.paste_links": "Aggiungi link",
    "controls.info": "Info",

    # ---- barra comandi: tooltip -------------------------------------------
    "controls.concurrency_tooltip": (
        "Quanti file scaricare contemporaneamente.\n"
        "Default 1 (sequenziale): con proxy gratuiti, parallelizzare\n"
        "degrada tutti i download."
    ),
    "controls.time_limit_tooltip": (
        "Minuti massimi per scaricare un singolo file (wall-clock).\n"
        "Superato il limite, il file viene abbandonato e si passa al successivo.\n"
        "Il tempo in pausa è incluso nel conteggio."
    ),
    "controls.chunk_size_tooltip": (
        "Dimensione di ogni pezzo scaricato da un proxy diverso.\n"
        "Pezzi più piccoli = più resistenza ai proxy instabili,\n"
        "più richieste HTTP al CDN Mega.\n"
        "Tagli grandi (128/256 MB): adatti a file molto grandi su proxy buoni."
    ),
    "controls.settings_tooltip": (
        "Configura download paralleli, limite di durata e dimensione pezzo.\n"
        "Non modificabile durante una sessione di download."
    ),
    "controls.experimental_tooltip": (
        "Funzioni in prova (connessioni per file, selezione proxy per "
        "velocità). Disattivate di default.\n"
        "Non modificabile durante una sessione di download."
    ),
    "controls.theme_tooltip_to_dark": "Passa al tema scuro",
    "controls.theme_tooltip_to_light": "Passa al tema chiaro",

    # ---- barra comandi: cartella di download -------------------------------
    "controls.download_dir_default": "Predefinita",
    "controls.download_dir_tooltip_default": (
        "Cartella dove salvare i file scaricati.\n"
        "Predefinita: sottocartella 'downloads' del programma."
    ),
    "controls.download_dir_tooltip_chosen": "Cartella di download:\n{path}",
    "controls.choose_download_dir_title": "Scegli la cartella di download",

    # ---- barra comandi: righe del menu Impostazioni ------------------------
    "controls.row_concurrency": "Paralleli:",
    "controls.row_time_limit": "Limite min/file:",
    "controls.row_chunk": "Pezzo:",
    "controls.row_download_dir": "Cartella download:",
    "controls.row_language": "Lingua:",

    # ---- barra comandi: selettore di lingua --------------------------------
    # I nomi delle lingue restano nella lingua stessa (convenzione diffusa:
    # resta leggibile a chi ha aperto l'app nella lingua sbagliata), quindi
    # "language_it"/"language_en" hanno lo stesso valore in entrambi i dizionari.
    "controls.language_auto": "Automatica",
    "controls.language_auto_detected": "Automatica ({lang})",
    "controls.language_it": "Italiano",
    "controls.language_en": "English",
    "controls.language_tooltip": (
        "Lingua dell'interfaccia.\n"
        "Automatica: segue la lingua del sistema."
    ),

    # ---- banner "nuova versione disponibile" -------------------------------
    "update_banner.available": "Disponibile la versione {version}.",
    "update_banner.download": "Scarica",

    # ---- finestra Info -----------------------------------------------------
    "about.title": "Info",
    "about.name_line": "<b>{name}</b> ({acronym}) — v{version}",
    "about.author": "Autore: {author}",
    "about.license": "Licenza: {license}",
    "about.check_button": "Controlla aggiornamenti",
    "about.check_on_startup": "Controlla aggiornamenti all'avvio",
    "about.update_not_checked": "Controllo aggiornamenti non eseguito.",
    "about.updates_not_configured": "Controllo aggiornamenti non configurato.",
    "about.checking": "Controllo in corso…",
    "about.update_available": "Disponibile la versione {version}.",
    "about.up_to_date": "Sei aggiornato all'ultima versione.",
    "about.check_failed": "Impossibile determinare se ci sono aggiornamenti.",
    "about.close": "Chiudi",

    # ---- finestra Funzioni Sperimentali ------------------------------------
    "experimental.title": "Funzioni Sperimentali",
    "experimental.info_tooltip": "Mostra la spiegazione estesa",
    "experimental.speed_selection": "Selezione per velocità",
    "experimental.speed_selection_desc_short": (
        "Testa la velocità reale dei proxy: solo quelli abbastanza veloci vengono preferiti. "
        "I lenti restano come riserva."
    ),
    "experimental.speed_selection_desc_long": (
        "Attiva un profilo di download alternativo ottimizzato per la qualità dei proxy. "
        "Cambia diversi parametri della sessione:\n\n"
        "• Candidati alla validazione: 5000 (anziché 12000)\n"
        "• Terzo stadio di validazione: ogni proxy scarica un file di prova da 1 MB e viene "
        "misurato in velocità reale\n"
        "• Soglia preferenza (configurabile): i proxy sopra questa soglia vengono serviti per "
        "primi; quelli più lenti restano come riserva\n"
        "• Soglia ammissione (fissa, 100 KB/s): i proxy sotto questa velocità vengono scartati\n"
        "• Connessioni per file: ridotte a 5 (meno pressione sul pool, i proxy durano di più)\n\n"
        "Il pool risultante è ordinato per velocità: il download usa prima i proxy veloci, e "
        "degrada ai lenti solo se necessario — senza fermarsi per ricostruire il pool.\n\n"
        "Default: disattivato, soglia preferenza 500 KB/s."
    ),
    "experimental.connections_label": "Connessioni per file:",
    "experimental.connections_title": "Connessioni per file",
    "experimental.connections_desc_short": (
        "Parti del file scaricate in parallelo, una per proxy. Default 10."
    ),
    "experimental.connections_desc_long": (
        "Quante parti del file vengono scaricate contemporaneamente, ognuna su un "
        "proxy diverso. Più connessioni aumentano la velocità ma consumano più "
        "proxy nello stesso istante; con pochi proxy buoni può essere "
        "controproducente. Intervallo 2–16, default 10."
    ),
    "experimental.budget_label": "Budget per pezzo (s):",
    "experimental.budget_title": "Budget per pezzo",
    "experimental.budget_desc_short": (
        "Tempo massimo per scaricare un pezzo da un proxy, poi si cambia. Default 180 s."
    ),
    "experimental.budget_desc_long": (
        "Tempo massimo concesso a un proxy per completare un singolo pezzo. "
        "Superato il budget il tentativo viene annullato e il pezzo riprovato su "
        "un altro proxy, anche se la velocità era accettabile. Alzalo se usi "
        "pezzi grandi (128/256 MB) su proxy non velocissimi, altrimenti "
        "verrebbero annullati prima di finire. Default 180 s."
    ),
    "experimental.feedback": (
        "Hai un'idea o un problema? Apri una segnalazione su GitHub: "
        '<a href="{url}">{url}</a>'
    ),
    "experimental.close": "Chiudi",

    # ---- finestra "Incolla link Mega" --------------------------------------
    "paste.title": "Incolla link Mega",
    "paste.instructions": "Incolla link Mega (uno per riga):",
    "paste.valid": "Validi: {n}",
    "paste.folders": "Cartelle: {n}",
    "paste.invalid": "Non validi: {n}",
    "paste.duplicates": "Duplicati: {n}",
    "paste.folders_tooltip": (
        "Link a cartella Mega: all'avvio vengono espansi nei file contenuti."
    ),
    "paste.cancel": "Annulla",
    # Il numero e' un parametro, non un plurale: il testo non cambia forma.
    "paste.add_button": "Aggiungi {n}",

    # ---- helper di formattazione condivisi ---------------------------------
    # Le UNITA' non si traducono (MB/s, GB, KB): qui c'e' solo il testo.
    "format.session_completed": "(completata)",
    "format.header_summary": (
        "{time} · {volume} · {speed} · {total} tot · {ok} ok · {fallen} fall."
    ),

    # ---- cruscotto compatto (StatsBar) -------------------------------------
    "stats_bar.speed": "Velocità",
    "stats_bar.downloads": "Download",
    "stats_bar.total_suffix": "totali",
    "stats_bar.pct_of_peak": "{pct}% del picco",
    "stats_bar.substats": "picco {peak} · media {avg} · min {min}",
    "stats_bar.eta_time": "ETA {eta} · {clock}",
    # {failed} arriva gia' formattato (porta il colore): e' l'ultimo segmento.
    "stats_bar.counts": "{running} corso · {queued} coda · {completed} ok · {failed}",
    "stats_bar.count_failed": "{n} fall.",

    # ---- zona proxy (ProxyBar) ---------------------------------------------
    "proxy_bar.micro": "PROXY",
    # Etichette delle card: il codice le mette in MAIUSCOLO da sé.
    "proxy_bar.card_alive": "Vivi",
    "proxy_bar.card_validation": "Validazione",
    "proxy_bar.card_discarded": "Scartati",
    "proxy_bar.card_refills": "Ricariche",
    "proxy_bar.card_last_refill": "Ultimo refill",
    "proxy_bar.card_band": "Banda",
    "proxy_bar.card_band_proxy": "Banda proxy",
    "proxy_bar.speedtest_button": "Banda",
    "proxy_bar.speedtest_tooltip": (
        "Misura la banda della linea (download diretto, senza proxy)."
    ),
    "proxy_bar.proxy_speedtest_button": "Banda proxy",
    "proxy_bar.proxy_speedtest_tooltip": (
        "Misura la banda reale del pool di proxy (solo durante una sessione)."
    ),
    "proxy_bar.reset_button": "Reset cache",
    "proxy_bar.reset_tooltip": (
        "Cancella proxy_cache.json. Il prossimo avvio rifarà lo scrape da zero."
    ),
    "proxy_bar.reset_confirm_title": "Reset cache proxy",
    "proxy_bar.reset_confirm_body": (
        "Cancellare la cache dei proxy?\n"
        "Il prossimo avvio sarà più lento perché rifarà lo scrape da zero."
    ),
    "proxy_bar.reset_error_title": "Errore",
    "proxy_bar.reset_error_body": "Impossibile cancellare la cache:\n{error}",
    "proxy_bar.cache_title": "Cache proxy",
    "proxy_bar.cache_deleted": "Cache proxy cancellata.",
    "proxy_bar.cache_absent": "Nessuna cache da cancellare.",

    # ---- pannello Statistiche (StatsPanel) ---------------------------------
    "stats_panel.title": "Statistiche",
    "stats_panel.copy_button": "Copia riepilogo",
    "stats_panel.session": "Sessione: {time}  ({status})",
    "stats_panel.session_placeholder": "Sessione: —",
    "stats_panel.session_running": "in corso",
    "stats_panel.session_completed": "completata",
    "stats_panel.volume": "Volume scaricato:  {value}",
    "stats_panel.speed_header": "Velocità di sessione",
    # Le righe seguenti sono allineate a colonna in Consolas: gli spazi prima
    # dei due punti fanno parte dell'impaginazione e vanno ritarati per lingua.
    "stats_panel.throughput": "  Throughput effettivo : {value}",
    "stats_panel.avg_per_download": "  Media per-download   : {value}",
    "stats_panel.peak": "  Picco  : {value}",
    "stats_panel.minimum": "  Minima : {value}",
    "stats_panel.counts": (
        "Job: {total} totali · {ok} ok · {failed} fall. · {abandoned} abb. · "
        "{cancelled} ann. · {running} in corso · {queued} coda"
    ),
    "stats_panel.counts_placeholder": "Job: —",
    "stats_panel.rate": "Tasso completati: {value}",
    "stats_panel.detail_header": "Dettaglio per-download:",
    # Stato del job nel dettaglio: la MAPPA vive in stats_panel, quindi il testo
    # e' suo. La chiave della mappa resta lo stato del modello (dato, non testo).
    "stats_panel.status_completed": "ok",
    "stats_panel.status_failed": "fallito",
    "stats_panel.status_cancelled": "annullato",
    "stats_panel.status_abandoned": "abbandonato",
    "stats_panel.status_running": "in corso",
    "stats_panel.status_queued": "in coda",
    # Riepilogo copiato negli appunti: lo legge l'utente, quindi si traduce.
    "stats_panel.copy_header": "=== Sessione MDPR ===",
    "stats_panel.copy_time": "Tempo:    {time}  ({status})",
    "stats_panel.copy_volume": "Volume:   {value}",
    "stats_panel.copy_speed_header": "Velocita':",
    "stats_panel.copy_throughput": "  - Throughput effettivo: {value}",
    "stats_panel.copy_avg": "  - Media per-download:   {value}",
    "stats_panel.copy_peak_min": "  - Picco / Minima:       {peak} / {min}",
    "stats_panel.copy_counts": (
        "Job: {total} totali  ok={ok}  fall={failed}  abb={abandoned}"
        "  ann={cancelled}  in_corso={running}  in_coda={queued}"
    ),
    "stats_panel.copy_rate": "Tasso completati: {value}",
    "stats_panel.copy_detail_header": "Dettaglio:",
    "stats_panel.copied_title": "Copiato",
    "stats_panel.copied_body": "Riepilogo copiato negli appunti.",

    # ---- elenco job (JobsPanel) --------------------------------------------
    # Solo il CROMO del pannello: i testi che arrivano dal modello (stato grezzo
    # di fallback, ultimo errore, nome file) NON si traducono qui — nascono in
    # jobs_model/core/downloader e sono materia della fase «Errori & Cronologia».
    "jobs_panel.status_queued": "In coda",
    "jobs_panel.status_running": "In corso",
    "jobs_panel.status_completed": "Completato",
    "jobs_panel.status_failed": "Fallito",
    "jobs_panel.status_cancelled": "Annullato",
    "jobs_panel.status_abandoned": "Abbandonato",
    "jobs_panel.action_cancel": "Annulla download",
    "jobs_panel.action_open_folder": "Apri cartella",
    "jobs_panel.action_restart": "Riavvia download",
    "jobs_panel.action_copy_url": "Copia URL",
    "jobs_panel.open_folder_button": "Apri cartella",
    "jobs_panel.terminal_stats": "{speed} · {volume} · {duration}",
    "jobs_panel.avg_speed": "media {value}",
    "jobs_panel.current_ip": "IP corrente: {ip}",
    "jobs_panel.attempts": "Tentativi: {n}",
    "jobs_panel.errors_suffix": "  •  Errori: {n}",
    "jobs_panel.last_error_suffix": "  •  Ultimo errore: {error}",
    "jobs_panel.filter_in_progress": "In corso",
    "jobs_panel.filter_completed": "Completati",
    "jobs_panel.filter_not_completed": "Non completati",
    "jobs_panel.filter_with_count": "{label} ({n})",
    "jobs_panel.restart_all": "Riavvia falliti ({n})",
    "jobs_panel.restart_all_tooltip": (
        "Riavvia tutti i download falliti, abbandonati o annullati.\n"
        "Il download riprende dai segmenti già scaricati (.part)."
    ),
    "jobs_panel.empty_title": "Aggiungi i tuoi link Mega per iniziare",
    # {button} e' il nome del pulsante preso da controls.paste_links: cosi' il
    # suggerimento non puo' sfasarsi dal pulsante che nomina.
    "jobs_panel.empty_hint": (
        "Usa il pulsante «{button}» nella barra comandi\n"
        "oppure clicca qui sotto."
    ),
}
