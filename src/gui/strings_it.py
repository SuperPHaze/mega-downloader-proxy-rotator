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
}
