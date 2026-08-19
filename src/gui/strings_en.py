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

    # ---- "new version available" banner --------------------------------------
    "update_banner.available": "Version {version} is available.",
    "update_banner.download": "Download",

    # ---- About window ---------------------------------------------------------
    "about.title": "About",
    "about.name_line": "<b>{name}</b> ({acronym}) — v{version}",
    "about.author": "Author: {author}",
    "about.license": "License: {license}",
    "about.check_button": "Check for updates",
    "about.check_on_startup": "Check for updates at startup",
    "about.update_not_checked": "Update check not run.",
    "about.updates_not_configured": "Update check not configured.",
    "about.checking": "Checking…",
    "about.update_available": "Version {version} is available.",
    "about.up_to_date": "You are on the latest version.",
    "about.check_failed": "Could not determine whether updates are available.",
    "about.close": "Close",

    # ---- Experimental Features window ------------------------------------------
    "experimental.title": "Experimental Features",
    "experimental.info_tooltip": "Show the extended explanation",
    "experimental.speed_selection": "Selection by speed",
    "experimental.speed_selection_desc_short": (
        "Tests the real speed of the proxies: only the fast enough ones are preferred. "
        "The slow ones stay in reserve."
    ),
    "experimental.speed_selection_desc_long": (
        "Enables an alternative download profile tuned for proxy quality. "
        "It changes several session parameters:\n\n"
        "• Validation candidates: 5000 (instead of 12000)\n"
        "• Third validation stage: every proxy downloads a 1 MB test file and its real "
        "speed is measured\n"
        "• Preference threshold (configurable): proxies above this threshold are served "
        "first; the slower ones stay in reserve\n"
        "• Admission threshold (fixed, 100 KB/s): proxies below this speed are discarded\n"
        "• Connections per file: reduced to 5 (less pressure on the pool, proxies last longer)\n\n"
        "The resulting pool is sorted by speed: the download uses the fast proxies first and "
        "falls back to the slow ones only when needed — without stopping to rebuild the pool.\n\n"
        "Default: off, preference threshold 500 KB/s."
    ),
    "experimental.connections_label": "Connections per file:",
    "experimental.connections_title": "Connections per file",
    "experimental.connections_desc_short": (
        "Parts of the file downloaded in parallel, one per proxy. Default 10."
    ),
    "experimental.connections_desc_long": (
        "How many parts of the file are downloaded at the same time, each through a "
        "different proxy. More connections increase speed but burn through more proxies "
        "at once; with few good proxies it can backfire. Range 2–16, default 10."
    ),
    "experimental.budget_label": "Chunk budget (s):",
    "experimental.budget_title": "Chunk budget",
    "experimental.budget_desc_short": (
        "Maximum time to download one chunk from a proxy, then it switches. Default 180 s."
    ),
    "experimental.budget_desc_long": (
        "Maximum time granted to a proxy to complete a single chunk. Past the budget the "
        "attempt is aborted and the chunk retried on another proxy, even if the speed was "
        "acceptable. Raise it if you use large chunks (128/256 MB) on proxies that are not "
        "very fast, otherwise they would be aborted before finishing. Default 180 s."
    ),
    "experimental.feedback": (
        "Got an idea or a problem? Open an issue on GitHub: "
        '<a href="{url}">{url}</a>'
    ),
    "experimental.close": "Close",

    # ---- "Paste Mega links" window ----------------------------------------------
    "paste.title": "Paste Mega links",
    "paste.instructions": "Paste Mega links (one per line):",
    "paste.valid": "Valid: {n}",
    "paste.folders": "Folders: {n}",
    "paste.invalid": "Invalid: {n}",
    "paste.duplicates": "Duplicates: {n}",
    "paste.folders_tooltip": (
        "Mega folder links: on start they are expanded into the files they contain."
    ),
    "paste.cancel": "Cancel",
    "paste.add_button": "Add {n}",
}
