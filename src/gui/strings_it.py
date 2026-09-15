# Dizionario italiano della GUI. L'italiano e' la FONTE: qui si scrive il testo
# originale, `strings_en.py` ne e' la traduzione (stesso insieme di chiavi).
#
# Chiavi: slug stabile "<superficie>.<elemento>" (mai la stringa italiana come
# chiave: cambiare il testo IT non deve invalidare la traduzione EN).
# Parametri: SEMPRE nominati ({name}, {path}), mai posizionali: in inglese
# l'ordine delle parti della frase cambia e con {} non si potrebbe riordinare.
# Plurali: il valore diventa un dict {"one": ..., "other": ...}, letto da `tn()`.
#
# Stato: traduzione COMPLETA (F1-F2c per l'interfaccia, E1+E2 per errori e
# cronologia). Le chiavi `err.*` non si scrivono qui: sono innestate in fondo
# dal catalogo di `core/error_catalog.py`, che e' la loro unica fonte perche'
# lo stesso testo serve ai log.
from __future__ import annotations

from src.core.error_catalog import ERROR_TEXTS_IT

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
    "controls.row_minimize": "Riduzione a icona:",
    "controls.row_language": "Lingua:",

    # ---- barra comandi: riduzione a icona ----------------------------------
    "controls.minimize_reset": "Chiedi ogni volta",
    "controls.minimize_tooltip_ask": (
        "Riducendo la finestra a icona, il programma chiede ogni volta\n"
        "dove metterla: area di notifica o barra delle applicazioni."
    ),
    "controls.minimize_tooltip_tray": (
        "Ora la finestra ridotta va nell'area di notifica, accanto\n"
        "all'orologio, senza chiedere.\n"
        "Premi per tornare a farti chiedere ogni volta."
    ),
    "controls.minimize_tooltip_taskbar": (
        "Ora la finestra ridotta resta nella barra delle applicazioni,\n"
        "senza chiedere.\n"
        "Premi per tornare a farti chiedere ogni volta."
    ),

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
    # Chiesto solo a sessione in corso: fuori sessione la coda non esiste.
    "paste.position_label": "Dove mettere i link aggiunti:",
    "paste.position_bottom": "In fondo alla coda",
    "paste.position_bottom_tooltip": (
        "Partono dopo tutti i link gia' in attesa."
    ),
    "paste.position_top": "Subito dopo il download in corso",
    "paste.position_top_tooltip": (
        "Passano davanti ai link gia' in attesa. I download gia' avviati "
        "non vengono interrotti."
    ),

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
    # Il CROMO del pannello. Dal modello arrivano DATI, non frasi: l'ultimo
    # errore è un payload (codice + parametri) che la card rende con
    # `error_render`, lo stato grezzo di fallback e il nome file restano tali.
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
    # ---- pannello link (LinkPanel) -----------------------------------------
    "link_panel.import": "Importa da file",
    "link_panel.add": "Aggiungi link",
    "link_panel.clear": "Svuota",
    "link_panel.allow_duplicates": "Consenti duplicati",
    "link_panel.allow_duplicates_tooltip": (
        "Se attivo, lo stesso link puo' essere aggiunto piu' volte. "
        "Ogni copia viene scaricata in una cartella separata."
    ),
    # Contatore: gia' oggi il codice sceglieva la forma con un `if`, qui la
    # scelta passa a `tn()`.
    "link_panel.counter_empty": "nessun link",
    "link_panel.counter": {
        "one": "{n} link pronto",
        "other": "{n} link pronti",
    },

    # ---- pannello link: import da file --------------------------------------
    "link_panel.import_dialog_title": "Importa link da file",
    "link_panel.import_dialog_filter": "File di testo (*.txt);;Tutti i file (*)",
    "link_panel.read_error_title": "Errore lettura file",
    "link_panel.read_error_body": "Impossibile leggere il file:\n{error}",
    "link_panel.nothing_imported_title": "Nessun link importato",
    "link_panel.nothing_imported_body": (
        "Il file non contiene link Mega validi "
        "(non validi: {invalid}, duplicati ignorati: {dups})."
    ),
    "link_panel.import_done_title": "Import completato",
    # Le due forme italiane sono identiche ("link" e' invariabile): la coppia
    # serve all'inglese, che qui distingue link/links.
    "link_panel.import_done_body": {
        "one": (
            "Import completato.\n"
            "- Aggiunti: {n} link\n"
            "- Non validi: {invalid}\n"
            "- Duplicati ignorati: {dups}"
        ),
        "other": (
            "Import completato.\n"
            "- Aggiunti: {n} link\n"
            "- Non validi: {invalid}\n"
            "- Duplicati ignorati: {dups}"
        ),
    },

    # ---- pannello link: avviso "gia' scaricati" -----------------------------
    "link_panel.history_title": "Link gia' scaricati",
    "link_panel.history_text": {
        "one": "{n} link su {total} risulta gia' scaricato in passato:",
        "other": "{n} link su {total} risultano gia' scaricati in passato:",
    },
    "link_panel.history_entry": "\u2022 {name} (scaricato il {date})",
    "link_panel.history_more": {
        "one": "... e altri {n} link",
        "other": "... e altri {n} link",
    },
    "link_panel.history_skip": "Salta gia' scaricati",
    "link_panel.history_anyway": "Scarica comunque",
    "link_panel.history_cancel": "Annulla",

    # ---- pannello link: avviso "gia' nella sessione in corso" --------------
    "link_panel.session_dup_title": "Link gia' in questa sessione",
    "link_panel.session_dup_text": {
        "one": "{n} link su {total} e' gia' in questa sessione:",
        "other": "{n} link su {total} sono gia' in questa sessione:",
    },
    "link_panel.session_dup_entry": "\u2022 {url} ({state})",
    "link_panel.session_dup_skip": "Salta i doppioni",
    "link_panel.session_dup_anyway": "Aggiungi comunque",

    # ---- espansione cartelle: righe di report (FolderExpandWorker) ----------
    # Il report e' una lista di righe mostrate in un QMessageBox. Le voci che
    # finiscono con "_suffix" sono clausole opzionali accodate alla riga di
    # esito: ognuna e' autonoma (separatore incluso), quindi traducibile da
    # sola. L'alternativa - una chiave per ogni combinazione - sarebbero otto
    # varianti della stessa frase.
    "folder_expand.cancelled": "Espansione annullata.",
    "folder_expand.nothing": "Nessun file da scaricare.",
    "folder_expand.error_line": "\u2717 {url}\n    {error}",
    "folder_expand.unexpected_line": "\u2717 {url}\n    errore imprevisto: {error}",
    "folder_expand.empty_line": (
        "\u2717 \u00ab{folder}\u00bb: la cartella è vuota "
        "(nessun file da scaricare)."
    ),
    "folder_expand.ok_line": {
        "one": "\u2713 \u00ab{folder}\u00bb: {n} file",
        "other": "\u2713 \u00ab{folder}\u00bb: {n} file",
    },
    # Le forme "one" italiane sono state corrette in F3: fino ad allora
    # ripetevano il plurale ("1 sottocartelle"), difetto PREESISTENTE che le
    # fasi di traduzione avevano tenuto identico per non cambiare il testo IT.
    "folder_expand.subfolders_suffix": {
        "one": ", {n} sottocartella",
        "other": ", {n} sottocartelle",
    },
    "folder_expand.truncated_suffix": (
        " \u2014 ATTENZIONE: altri {n} file esclusi dal limite di {max}"
    ),
    "folder_expand.skipped_suffix": " \u2014 {n} nodi illeggibili saltati",
    "folder_expand.duplicates_removed": {
        "one": (
            "\u2022 {n} file duplicato (stesso file incollato più volte) "
            "è stato rimosso."
        ),
        "other": (
            "\u2022 {n} file duplicati (stesso file incollato più volte) "
            "sono stati rimossi."
        ),
    },

    # ---- finestra principale: cartella di download --------------------------
    "main_window.dir_not_writable_title": "Cartella non scrivibile",
    "main_window.dir_not_writable_body": (
        "Non è possibile scrivere in:\n{path}\n\n"
        "Torno alla cartella predefinita."
    ),
    "main_window.dir_reset": "Cartella di download: predefinita.",
    "main_window.dir_set": "Cartella di download: {path}",
    "main_window.dir_default": "Cartella di download: predefinita (downloads/).",

    # ---- finestra principale: avvio -----------------------------------------
    "main_window.no_links_title": "Nessun link",
    "main_window.no_links_body": "Aggiungi almeno un link Mega prima di avviare.",
    "main_window.nothing_to_download": (
        "Nessun link da scaricare: tutti già presenti nello storico."
    ),
    "main_window.previous_session_closing": (
        "Sessione precedente ancora in chiusura: riprova tra qualche secondo."
    ),
    "main_window.collecting_proxies": "Raccolta proxy in corso…",
    "main_window.pool_ready": "Proxy validi: {n}. Download avviato.",
    "main_window.pool_failed": "Errore pool proxy: {error}",
    "main_window.validation_progress": (
        "Validazione proxy: {done}/{total} (vivi: {alive})"
    ),

    # ---- finestra principale: espansione delle cartelle ---------------------
    "main_window.expand_already_running": "Espansione gia' in corso, attendi…",
    "main_window.expand_status": {
        "one": "Espansione di {n} cartella Mega in corso…",
        "other": "Espansione di {n} cartelle Mega in corso…",
    },
    "main_window.expand_dialog_text": "Lettura delle cartelle Mega in corso…",
    "main_window.expand_dialog_text_hot": (
        "Lettura delle cartelle Mega in corso… "
        "I download in corso proseguono."
    ),
    "main_window.expand_dialog_cancel": "Annulla",
    "main_window.expand_dialog_title": "Espansione cartelle",
    "main_window.expand_cancelling": "Annullamento dell'espansione…",
    "main_window.expand_progress": "Espansione cartelle: {done}/{total}…",
    "main_window.expand_cancelled": "Espansione annullata.",
    "main_window.expand_failed_status": "Espansione cartella non riuscita.",
    "main_window.expand_failed_title": "Cartella Mega non espansa",
    # Prima era costruita con una concatenazione (" + msg): il frammento finale
    # non era traducibile da solo, ora il dettaglio e' un parametro.
    "main_window.expand_failed_body": (
        "Non è stato possibile ricavare i file dalla cartella:\n\n{details}"
    ),
    "main_window.expand_truncated_title": "Cartella molto grande",
    "main_window.expand_truncated_body": {
        "one": (
            "La cartella contiene più file del limite dell'app: "
            "{n} file NON verrà scaricato.\n\n"
            "Vuoi procedere con i primi {kept}?"
        ),
        "other": (
            "La cartella contiene più file del limite dell'app: "
            "{n} file NON verranno scaricati.\n\n"
            "Vuoi procedere con i primi {kept}?"
        ),
    },
    "main_window.expand_report_title": "Cartelle Mega espanse",
    "main_window.expand_ready": {
        "one": "{n} file pronto al download.",
        "other": "{n} file pronti al download.",
    },
    "main_window.start_cancelled": "Avvio annullato.",

    # ---- finestra principale: pausa / annullo -------------------------------
    "main_window.paused": "In pausa.",
    "main_window.resumed": "Ripreso.",
    "main_window.cancelled": "Annullato.",

    # ---- finestra principale: ripristino sessione ---------------------------
    "main_window.restore_title": "Ripristina sessione",
    "main_window.restore_body": {
        "one": (
            "La sessione precedente si è chiusa con {n} link non "
            "completato.\nVuoi ricaricarlo nella lista?\n\n"
            "I pezzi già scaricati verranno ripresi automaticamente."
        ),
        "other": (
            "La sessione precedente si è chiusa con {n} link non "
            "completati.\nVuoi ricaricarli nella lista?\n\n"
            "I pezzi già scaricati verranno ripresi automaticamente."
        ),
    },
    "main_window.restored_status": {
        "one": (
            "Ripristinato {n} link dalla sessione precedente. "
            "Premi Avvia per riprendere."
        ),
        "other": (
            "Ripristinati {n} link dalla sessione precedente. "
            "Premi Avvia per riprendere."
        ),
    },

    # ---- finestra principale: fine dei download -----------------------------
    # {file} e' il numero del file mostrato all'utente (1-based), {n} resta
    # riservato al conteggio che decide la forma plurale.
    "main_window.file_done": "File {file} completato ({done}/{total}).",
    "main_window.all_completed": "Tutti i download completati.",
    "main_window.all_terminated": "Tutti i download terminati.",
    "main_window.fatal_title": "Errore bloccante",
    "main_window.fatal_body": "File {file}: {error}\n\nIl worker è terminato.",
    "main_window.fatal_status": "Errore bloccante file {file}: {error}",
    "main_window.abandoned_status": {
        "one": "File {file} abbandonato dopo {n} tentativo: {error}",
        "other": "File {file} abbandonato dopo {n} tentativi: {error}",
    },

    # ---- finestra principale: annullo per-job -------------------------------
    "main_window.job_cancelling": "File {file}: cancellazione in corso…",
    "main_window.job_cancelled": "File {file} annullato ({done}/{total}).",

    # ---- finestra principale: eliminazione dal disco ------------------------
    # Le due frasi erano concatenate a pezzi attorno al numero del file: ora
    # sono due chiavi intere, scelte in base al tipo di job.
    "main_window.delete_title": "Eliminare dal disco?",
    "main_window.delete_folder_job_body": (
        "Eliminare il file {file} dalla cartella scaricata?\n"
        "Gli altri file della stessa cartella Mega restano al loro posto.\n"
        "L'operazione è irreversibile."
    ),
    "main_window.delete_folder_body": (
        "Eliminare la cartella su disco del file {file}?\n"
        "L'operazione è irreversibile."
    ),
    "main_window.delete_missing": "File {file}: cartella non presente su disco.",
    "main_window.delete_done": "File {file}: cartella eliminata ({name}).",
    "main_window.delete_failed_title": "Eliminazione cartella fallita",
    "main_window.delete_failed_body": "Impossibile eliminare {path}:\n{error}",
    "main_window.delete_nothing": "File {file}: nessun file da eliminare su disco.",
    "main_window.delete_file_done": "File {file}: file eliminato ({name}).",

    # ---- finestra principale: riavvio dei job -------------------------------
    "main_window.restart_no_url": (
        "File {file}: URL non trovato, impossibile riavviare."
    ),
    "main_window.restart_failed": "File {file}: riavvio non riuscito.",
    "main_window.restart_queued": "File {file}: riavvio in coda.",
    "main_window.restart_all_done": {
        "one": "Riavviato {n} download.",
        "other": "Riavviati {n} download.",
    },

    # ---- finestra principale: aggiunta a una sessione in corso --------------
    "main_window.add_finished_title": "Coda gia' completata",
    "main_window.add_finished_body": (
        "Tutti i download di questa sessione sono terminati. "
        "Vuoi proseguire la stessa sessione?"
    ),
    "main_window.add_finished_hint": (
        "Proseguendo si tengono elenco, statistiche, cronometro e i proxy gia' "
        "validati. Con una sessione nuova si riparte da zero, raccolta proxy "
        "compresa."
    ),
    "main_window.add_finished_continue": "Prosegui questa sessione",
    "main_window.add_finished_fresh": "Nuova sessione",
    "main_window.add_finished_cancel": "Annulla",
    "main_window.add_nothing": "Nessun link da aggiungere.",
    "main_window.add_refused": (
        "Aggiunta non riuscita: la sessione non ha proxy utilizzabili. "
        "Annulla e riavvia."
    ),
    "main_window.add_done": {
        "one": "Aggiunto {n} link alla sessione in corso.",
        "other": "Aggiunti {n} link alla sessione in corso.",
    },

    # ---- finestra principale: banda dei proxy -------------------------------
    "main_window.proxy_speed_no_session": "Banda proxy: nessuna sessione attiva.",
    "main_window.proxy_speed_no_proxy": (
        "Banda proxy: nessun proxy disponibile nel pool."
    ),

    # ---- finestra principale: riavvio rifiutato -----------------------------
    # Nascono nella GUI ma finiscono nel MODELLO come errore del job: viaggiano
    # quindi come codice (chiave intera, col punto) e non come testo gia' reso.
    "main_window.restart_no_orchestrator": "Nessun orchestrator attivo",
    "main_window.restart_refused": "Riavvio rifiutato dall'orchestrator",

    # ---- area di notifica (icona accanto all'orologio) ----------------------
    "main_window.minimize_ask_restored": (
        "Alla prossima riduzione a icona ti verrà chiesto di nuovo dove "
        "mettere la finestra."
    ),
    "tray.menu_show": "Mostra la finestra",
    "tray.menu_quit": "Esci",
    "tray.tooltip_idle": "Nessun download in corso",
    "tray.tooltip_running": "{running} in corso · {done}/{total} completati · {speed}",
    "tray.tooltip_done": "{done}/{total} completati",
    # Domanda al momento della riduzione a icona.
    "tray.ask_title": "Riduzione a icona",
    "tray.ask_body": "Dove vuoi mettere la finestra?",
    "tray.ask_tray": "Area di notifica",
    "tray.ask_taskbar": "Barra delle applicazioni",
    "tray.ask_remember": "Ricorda la scelta",
    # Avvisi a comparsa. `file_fallback` copre i casi in cui il nome del file
    # non e' ancora noto (l'errore puo' arrivare prima del resolve).
    "tray.file_fallback": "File {file}",
    "tray.notify_completed_title": "Download completato",
    "tray.notify_completed_body": "{name}  ({done}/{total})",
    "tray.notify_failed_title": "Download non riuscito",
    "tray.notify_failed_body": "{name}: {error}",
    "tray.notify_queue_done_title": "Coda completata",
    "tray.notify_queue_done_body": "{done}/{total} file scaricati.",

    # ---- setup del pool proxy ----------------------------------------------
    # Le righe di stato nascono nell'orchestrator, fuori dalla GUI: viaggiano
    # come codice + parametri (`setup_status_t`/`pool_failed_t`) e si rendono
    # qui. Il segnale gemello che porta la stringa italiana resta per i log e
    # per la CLI, che non si traducono.
    "setup.cache_candidates": "Cache proxy: {n} candidati...",
    "setup.hot_start": "Hot-start: {n} proxy pronti dalla cache",
    "setup.collecting": "Raccolta proxy dalle fonti pubbliche...",
    "setup.validating": "Validazione di {n} proxy contro Mega...",
    "setup.no_proxy_collected": "Nessun proxy raccolto dalle fonti",
    "setup.no_valid_proxy": "Nessun proxy valido per Mega",
    # Ripiego per le eccezioni impreviste del setup: il testo originale
    # (spesso inglese, di una libreria) viaggia come parametro.
    "setup.unexpected": "{error}",

    # ---- cronologia di un job ----------------------------------------------
    # `jobs_model` non formatta piu' testo: memorizza CHIAVE + parametri e
    # lascia rendere a chi disegna. Le tre voci con un errore dentro ricevono
    # il payload di E1, gia' reso, nel parametro {error}.
    "job_log.started": "Download avviato",
    "job_log.ip": "IP uscente: {ip}",
    "job_log.attempt": "Tentativo {attempt}: {error}",
    "job_log.completed": "Download completato",
    "job_log.fatal": "Errore fatale: {error}",
    "job_log.abandoned": {
        "one": "Link abbandonato dopo {n} tentativo: {error}",
        "other": "Link abbandonato dopo {n} tentativi: {error}",
    },
    "job_log.cancelled": "Cancellato dall'utente",
    "job_log.restart": "----- Riavvio richiesto -----",

    # ---- finestra di dettaglio di un job ------------------------------------
    "job_detail.title": "Dettaglio job #{file}",
    "job_detail.abandoned_title": "Link abbandonato",
    "job_detail.copy": "Copia",
    "job_detail.abandoned_info": (
        "Tentativi falliti: {attempts}  •  Ultimo errore: {error}"
    ),
    "job_detail.not_available": "n/d",
    "job_detail.url_label": "URL:",
    "job_detail.summary": (
        "Stato: <b>{status}</b>  •  Avanzamento: {progress}%  •  "
        "Tentativi: {attempts}  •  Errori: {errors}  •  "
        "Durata: {duration}"
    ),
    "job_detail.summary_last_error": "  •  Ultimo errore: {error}",
    "job_detail.ip_history": "Cronologia IP usati:",
    "job_detail.col_timestamp": "Timestamp",
    "job_detail.col_ip": "IP",
    "job_detail.attempts_log": "Log dei tentativi:",
    "job_detail.close": "Chiudi",

    # ---- errori: il catalogo del motore, innestato ---------------------------
    # L'italiano degli errori ha UNA sola fonte, `core/error_catalog.py`: serve
    # anche ai LOG, che restano italiani con l'interfaccia in inglese. Qui
    # entra come chiavi `err.*` senza essere ricopiato, cosi' i test di parita'
    # IT<->EN lo coprono senza sapere che e' speciale.
    **{f"err.{code}": text for code, text in ERROR_TEXTS_IT.items()},

    # Le voci che l'INGLESE declina al singolare e al plurale («1 minute» /
    # «2 minutes»). L'italiano non cambia — e' lo stesso testo del catalogo in
    # entrambe le forme, com'era prima della traduzione — ma la coppia deve
    # esserci anche qui perche' `tn()` possa scegliere. Il testo si PRENDE dal
    # catalogo, non si ricopia. L'elenco dei codici sta in
    # `gui/error_render._COUNT_PARAM`, ed e' li' che si aggiunge una voce.
    **{
        f"err.{code}": {
            "one": ERROR_TEXTS_IT[code],
            "other": ERROR_TEXTS_IT[code],
        }
        for code in (
            "time_limit_exceeded",
            "node_key_too_short",
            "crypto_bad_key_length",
            "crypto_file_key_short",
            "folder_key_invalid",
            "folder_key_too_short",
            "chunk_retries_exhausted",
        )
    },
}
