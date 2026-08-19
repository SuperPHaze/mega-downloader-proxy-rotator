# English dictionary of the GUI. Traduzione di `strings_it.py`, che resta la
# FONTE: stesso insieme di chiavi e stessi parametri {nome} (due test offline
# lo verificano, vedi tests/test_i18n.py).
#
# Nota: "controls.language_it"/"controls.language_en" NON si traducono — ogni
# lingua compare nel proprio nome anche in inglese.
#
# Stato migrazione: F1 copre ControlsBar + titolo finestra (F2 aggiunge il resto).
from __future__ import annotations

STRINGS: dict[str, str | dict[str, str]] = {
    # ---- main window -------------------------------------------------------
    "main_window.title": "{name} v{version}",

    # ---- controls bar: buttons ---------------------------------------------
    "controls.start": "Start",
    "controls.pause": "Pause",
    "controls.resume": "Resume",
    "controls.cancel": "Cancel",
    "controls.settings": "Settings",
    "controls.experimental": "Experimental",
    "controls.paste_links": "Add links",
    "controls.info": "Info",

    # ---- controls bar: tooltips --------------------------------------------
    "controls.concurrency_tooltip": (
        "How many files to download at the same time.\n"
        "Default 1 (sequential): with free proxies, running them in\n"
        "parallel degrades every download."
    ),
    "controls.time_limit_tooltip": (
        "Maximum minutes to download a single file (wall clock).\n"
        "Past the limit the file is abandoned and the next one starts.\n"
        "Time spent paused counts towards the limit."
    ),
    "controls.chunk_size_tooltip": (
        "Size of each chunk downloaded through a different proxy.\n"
        "Smaller chunks = more resilience to unstable proxies,\n"
        "more HTTP requests to the Mega CDN.\n"
        "Large sizes (128/256 MB): for very large files on good proxies."
    ),
    "controls.settings_tooltip": (
        "Configure parallel downloads, duration limit and chunk size.\n"
        "Cannot be changed during a download session."
    ),
    "controls.experimental_tooltip": (
        "Features under test (connections per file, proxy selection by "
        "speed). Off by default.\n"
        "Cannot be changed during a download session."
    ),
    "controls.theme_tooltip_to_dark": "Switch to the dark theme",
    "controls.theme_tooltip_to_light": "Switch to the light theme",

    # ---- controls bar: download folder --------------------------------------
    "controls.download_dir_default": "Default",
    "controls.download_dir_tooltip_default": (
        "Folder where downloaded files are saved.\n"
        "Default: the program's 'downloads' subfolder."
    ),
    "controls.download_dir_tooltip_chosen": "Download folder:\n{path}",
    "controls.choose_download_dir_title": "Choose the download folder",

    # ---- controls bar: Settings menu rows ------------------------------------
    "controls.row_concurrency": "Parallel files:",
    "controls.row_time_limit": "Limit min/file:",
    "controls.row_chunk": "Chunk:",
    "controls.row_download_dir": "Download folder:",
    "controls.row_language": "Language:",

    # ---- controls bar: language selector -------------------------------------
    "controls.language_auto": "Automatic",
    "controls.language_auto_detected": "Automatic ({lang})",
    "controls.language_it": "Italiano",
    "controls.language_en": "English",
    "controls.language_tooltip": (
        "Interface language.\n"
        "Automatic: follows the system language."
    ),
}
