# Catalogo dei testi ITALIANI degli errori che l'utente legge.
#
# Perche' vive in `core/` e non nei dizionari della GUI: il testo italiano non
# serve solo a video, serve ai LOG (`app.log`, `events.jsonl`,
# `failed_links.log`, telemetria), che restano in italiano anche con
# l'interfaccia in inglese. Il motore deve poterlo produrre senza sapere che
# esiste un'interfaccia — la separazione dei layer vieta `core -> gui`, non il
# contrario: sara' `gui/strings_it.py` a innestare queste voci come `err.*`
# (fase E2).
#
# Regola: il testo NON si scrive piu' al punto di `raise`, si scrive qui. Al
# `raise` si passano codice e parametri. Cosi' un messaggio ha un identificatore
# stabile che sopravvive alla riscrittura del testo, ed e' quello che la GUI
# traduce.
#
# I segnaposto sono NOMINATI e possono portare uno specificatore di formato
# (`{required:,}`, `{kbps:.1f}`): fa parte del testo, riprodurlo e' necessario
# perche' il messaggio resti identico a prima della migrazione.
from __future__ import annotations

# Codice di ripiego per tutto cio' che non nasce da un nostro `raise`:
# eccezioni delle librerie (`requests`, `OSError`) e violazioni di contratto
# interno. Il testo originale viaggia come parametro.
UNEXPECTED = "unexpected"

ERROR_TEXTS_IT: dict[str, str] = {
    # ---- ripiego -----------------------------------------------------------
    UNEXPECTED: "{error}",

    # ---- core/disk.py ------------------------------------------------------
    "disk_full": (
        "spazio su disco insufficiente in '{path}': "
        "servono {required:,} B (file {needed_bytes:,} + margine {margin_bytes:,}), "
        "liberi {free:,} B"
    ),

    # ---- downloader/mega_api.py -------------------------------------------
    "resolve_cancelled": "resolve annullato durante il backoff",
    # `api_code` e non `code`: `code` e' il primo parametro posizionale di
    # UserFacingError, usarlo come nome darebbe "multiple values for 'code'".
    "api_error_code": "API Mega ha risposto codice {api_code}",
    "api_unexpected_response": "API Mega: risposta inattesa {response}",
    # Il "5" resta letterale: e' il bound del `for attempt in range(1, 6)` e
    # non e' una costante nominata. Parametrizzarlo qui vorrebbe dire
    # duplicarne il valore in un secondo posto.
    "api_retries_exhausted": "API Mega: 5 tentativi esauriti ({error})",
    "folder_link_not_downloadable": (
        "link a cartella Mega: va espanso in singoli file prima del download ({url})"
    ),
    "url_not_parsable": "URL Mega non parsabile: {url}",
    "file_not_accessible": "File non accessibile (API senza 'g'): {response}",
    "size_missing": "size mancante o invalida: {error}",
    "node_key_too_short": "chiave del nodo troppo corta ({words} word): {node}",
    "folder_file_not_accessible": (
        "File non accessibile nella cartella (API senza 'g'): {response}"
    ),
    "folder_listing_unavailable": (
        "elenco della cartella non disponibile (risposta: {response})"
    ),

    # ---- downloader/mega_client.py ----------------------------------------
    "download_incomplete": "download incompleto: {downloaded}/{expected} byte",
    # Due testi diversi per la stessa causa (mega_client e parallel_client):
    # restano due codici finche' non si decide di unificarli, che sarebbe un
    # cambio di testo.
    "crypto_not_importable": (
        "pycryptodome non importabile ({error}). "
        "Verifica le dipendenze (pip install -r requirements.txt)."
    ),
    "crypto_missing": "pycryptodome mancante ({error})",

    # ---- downloader/mega_crypto.py ----------------------------------------
    "crypto_bad_key_length": "chiave cifrata di lunghezza non valida: {words} word",
    "crypto_bad_master_key": "master key della cartella non a 4 word: {words}",
    "crypto_file_key_short": "file_key troppo corta: {words} word",

    # ---- downloader/mega_folder.py ----------------------------------------
    "folder_key_invalid": "chiave della cartella non valida ({words} word invece di 4)",
    "folder_no_nodes": "la cartella non ha restituito alcun nodo",
    "folder_root_not_found": "nodo radice della cartella non individuabile",
    "folder_node_not_in_folder": (
        "il nodo selezionato dal link ({node}) non e' nella cartella"
    ),
    "not_a_folder_link": "non e' un link a cartella Mega: {url}",
    "folder_key_unreadable": "chiave della cartella illeggibile: {error}",
    "folder_key_too_short": "chiave della cartella troppo corta ({words} word)",

    # ---- downloader/parallel_client.py ------------------------------------
    # `detail` e' la concatenazione dei primi tre errori di chunk, come oggi.
    # Gli stessi tre viaggiano anche come dato strutturato nel parametro
    # `children`, che E2 rendera' al posto di `detail`.
    "chunks_failed": "{failed}/{total} chunk falliti: {detail}",
    "chunk_local_abort": (
        "chunk {chunk}: abort locale (altri chunk hanno esaurito i retry)"
    ),
    "chunk_cancelled": "chunk {chunk}: cancellato dall'utente",
    "chunk_abort_pool_wait": "chunk {chunk}: abort durante attesa pool",
    "chunk_abort_backoff": "chunk {chunk}: abort durante backoff",
    "chunk_abort_backoff_429": "chunk {chunk}: abort durante backoff 429",
    "chunk_range_ignored": "chunk {chunk}: server ignora Range (status={status})",
    "chunk_local_abort_mid": "chunk {chunk}: abort locale mid-download",
    "chunk_cancelled_mid": "chunk {chunk}: cancellato mid-download",
    "chunk_time_budget": (
        "chunk {chunk}: superato budget temporale di {budget_s}s "
        "(scaricati {downloaded}/{expected} B)"
    ),
    "chunk_too_slow": (
        "chunk {chunk}: proxy troppo lento "
        "({kbps:.1f} KB/s < {min_kbps:.0f} KB/s per {window_s:.0f}s)"
    ),
    "chunk_short_read": "chunk {chunk}: ricevuti {received}B su {expected}B attesi",
    "chunk_retries_exhausted": "chunk {chunk}: esauriti {attempts} tentativi ({error})",

    # ---- downloader/worker.py: le cornici --------------------------------
    # Non nascono da un `raise` ma sono testo che l'utente legge, quindi stanno
    # nello stesso catalogo.
    #
    # Le coppie `*_paren` / senza suffisso non sono un doppione: il worker usa
    # DUE formulazioni diverse per la stessa causa — una per il segnale
    # `failed` (fra parentesi, dopo "Tentativo N: ") e una per
    # `_last_error_msg`, che finisce in `failed_links.log` (con i due punti).
    # Sono tenute distinte perche' il testo dei due canali oggi differisce e
    # questa fase non lo cambia.
    "attempt_frame": "Tentativo {n}: {reason}",
    "pool_empty_short": "pool vuoto, attendo refill",
    "pool_empty": "pool proxy vuoto, refill in attesa",
    "ip_check_failed_paren": "IP check fallito ({error})",
    "ip_check_failed": "IP check fallito: {error}",
    "download_failed_paren": "download fallito ({error})",
    "download_failed": "download fallito: {error}",
    "config_error": "Errore di configurazione: {error}",
    "disk_full_short": "spazio su disco insufficiente ({error})",
    "time_limit_exceeded": "superato il limite di {minutes} minuti",
    "unknown_reason": "motivo sconosciuto",
}
