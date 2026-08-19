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
}
