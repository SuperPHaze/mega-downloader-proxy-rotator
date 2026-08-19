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

    # ---- shared formatting helpers ---------------------------------------------
    "format.session_completed": "(completed)",
    "format.header_summary": (
        "{time} · {volume} · {speed} · {total} tot · {ok} ok · {fallen} fail."
    ),

    # ---- compact dashboard (StatsBar) -------------------------------------------
    "stats_bar.speed": "Speed",
    "stats_bar.downloads": "Downloads",
    "stats_bar.total_suffix": "total",
    "stats_bar.pct_of_peak": "{pct}% of peak",
    "stats_bar.substats": "peak {peak} · avg {avg} · min {min}",
    "stats_bar.eta_time": "ETA {eta} · {clock}",
    "stats_bar.counts": "{running} running · {queued} queued · {completed} ok · {failed}",
    "stats_bar.count_failed": "{n} fail.",

    # ---- proxy area (ProxyBar) ---------------------------------------------------
    # Le etichette delle card stanno in uno spazio di ~100px a 7pt: "Proxy
    # bandwidth" (143px) verrebbe TAGLIATA. "Line speed"/"Proxy speed" dicono
    # la stessa cosa e ci stanno; il tooltip dei pulsanti spiega per esteso.
    "proxy_bar.micro": "PROXY",
    "proxy_bar.card_alive": "Alive",
    "proxy_bar.card_validation": "Validation",
    "proxy_bar.card_discarded": "Discarded",
    "proxy_bar.card_refills": "Refills",
    "proxy_bar.card_last_refill": "Last refill",
    "proxy_bar.card_band": "Line speed",
    "proxy_bar.card_band_proxy": "Proxy speed",
    "proxy_bar.speedtest_button": "Line speed",
    "proxy_bar.speedtest_tooltip": (
        "Measures the line bandwidth (direct download, without proxies)."
    ),
    "proxy_bar.proxy_speedtest_button": "Proxy speed",
    "proxy_bar.proxy_speedtest_tooltip": (
        "Measures the real bandwidth of the proxy pool (only during a session)."
    ),
    "proxy_bar.reset_button": "Reset cache",
    "proxy_bar.reset_tooltip": (
        "Deletes proxy_cache.json. The next run will scrape from scratch."
    ),
    "proxy_bar.reset_confirm_title": "Reset proxy cache",
    "proxy_bar.reset_confirm_body": (
        "Delete the proxy cache?\n"
        "The next run will be slower because it will scrape from scratch."
    ),
    "proxy_bar.reset_error_title": "Error",
    "proxy_bar.reset_error_body": "Could not delete the cache:\n{error}",
    "proxy_bar.cache_title": "Proxy cache",
    "proxy_bar.cache_deleted": "Proxy cache deleted.",
    "proxy_bar.cache_absent": "No cache to delete.",

    # ---- Statistics panel (StatsPanel) ---------------------------------------------
    "stats_panel.title": "Statistics",
    "stats_panel.copy_button": "Copy summary",
    "stats_panel.session": "Session: {time}  ({status})",
    "stats_panel.session_placeholder": "Session: —",
    "stats_panel.session_running": "running",
    "stats_panel.session_completed": "completed",
    "stats_panel.volume": "Downloaded volume:  {value}",
    "stats_panel.speed_header": "Session speed",
    # Colonne allineate in Consolas: la spaziatura e' ritarata sull'inglese
    # ("Effective throughput" e "Per-download average" hanno la stessa lunghezza).
    "stats_panel.throughput": "  Effective throughput : {value}",
    "stats_panel.avg_per_download": "  Per-download average : {value}",
    "stats_panel.peak": "  Peak    : {value}",
    "stats_panel.minimum": "  Minimum : {value}",
    "stats_panel.counts": (
        "Jobs: {total} total · {ok} ok · {failed} fail. · {abandoned} aband. · "
        "{cancelled} canc. · {running} running · {queued} queued"
    ),
    "stats_panel.counts_placeholder": "Jobs: —",
    "stats_panel.rate": "Completion rate: {value}",
    "stats_panel.detail_header": "Per-download detail:",
    "stats_panel.status_completed": "ok",
    "stats_panel.status_failed": "failed",
    "stats_panel.status_cancelled": "cancelled",
    "stats_panel.status_abandoned": "abandoned",
    "stats_panel.status_running": "running",
    "stats_panel.status_queued": "queued",
    "stats_panel.copy_header": "=== MDPR session ===",
    "stats_panel.copy_time": "Time:     {time}  ({status})",
    "stats_panel.copy_volume": "Volume:   {value}",
    "stats_panel.copy_speed_header": "Speed:",
    "stats_panel.copy_throughput": "  - Effective throughput: {value}",
    "stats_panel.copy_avg": "  - Per-download average: {value}",
    "stats_panel.copy_peak_min": "  - Peak / Minimum:       {peak} / {min}",
    "stats_panel.copy_counts": (
        "Jobs: {total} total  ok={ok}  fail={failed}  aband={abandoned}"
        "  canc={cancelled}  running={running}  queued={queued}"
    ),
    "stats_panel.copy_rate": "Completion rate: {value}",
    "stats_panel.copy_detail_header": "Detail:",
    "stats_panel.copied_title": "Copied",
    "stats_panel.copied_body": "Summary copied to the clipboard.",

    # ---- job list (JobsPanel) --------------------------------------------------
    "jobs_panel.status_queued": "Queued",
    "jobs_panel.status_running": "Running",
    "jobs_panel.status_completed": "Completed",
    "jobs_panel.status_failed": "Failed",
    "jobs_panel.status_cancelled": "Cancelled",
    "jobs_panel.status_abandoned": "Abandoned",
    "jobs_panel.action_cancel": "Cancel download",
    "jobs_panel.action_open_folder": "Open folder",
    "jobs_panel.action_restart": "Restart download",
    "jobs_panel.action_copy_url": "Copy URL",
    "jobs_panel.open_folder_button": "Open folder",
    "jobs_panel.terminal_stats": "{speed} · {volume} · {duration}",
    "jobs_panel.avg_speed": "avg {value}",
    "jobs_panel.current_ip": "Current IP: {ip}",
    "jobs_panel.attempts": "Attempts: {n}",
    "jobs_panel.errors_suffix": "  •  Errors: {n}",
    "jobs_panel.last_error_suffix": "  •  Last error: {error}",
    "jobs_panel.filter_in_progress": "In progress",
    "jobs_panel.filter_completed": "Completed",
    "jobs_panel.filter_not_completed": "Not completed",
    "jobs_panel.filter_with_count": "{label} ({n})",
    "jobs_panel.restart_all": "Restart failed ({n})",
    "jobs_panel.restart_all_tooltip": (
        "Restarts every failed, abandoned or cancelled download.\n"
        "The download resumes from the segments already fetched (.part)."
    ),
    "jobs_panel.empty_title": "Add your Mega links to get started",
    "jobs_panel.empty_hint": (
        'Use the "{button}" button in the command bar\n'
        "or click below."
    ),
    # ---- pannello link (LinkPanel) -----------------------------------------
    "link_panel.import": "Import from file",
    "link_panel.add": "Add links",
    "link_panel.clear": "Clear",
    "link_panel.allow_duplicates": "Allow duplicates",
    "link_panel.allow_duplicates_tooltip": (
        "If enabled, the same link can be added more than once. "
        "Each copy is downloaded into a separate folder."
    ),
    "link_panel.counter_empty": "no links",
    "link_panel.counter": {
        "one": "{n} link ready",
        "other": "{n} links ready",
    },

    # ---- pannello link: import da file --------------------------------------
    "link_panel.import_dialog_title": "Import links from file",
    "link_panel.import_dialog_filter": "Text files (*.txt);;All files (*)",
    "link_panel.read_error_title": "File read error",
    "link_panel.read_error_body": "Cannot read the file:\n{error}",
    "link_panel.nothing_imported_title": "No links imported",
    "link_panel.nothing_imported_body": (
        "The file contains no valid Mega links "
        "(invalid: {invalid}, duplicates ignored: {dups})."
    ),
    "link_panel.import_done_title": "Import complete",
    "link_panel.import_done_body": {
        "one": (
            "Import complete.\n"
            "- Added: {n} link\n"
            "- Invalid: {invalid}\n"
            "- Duplicates ignored: {dups}"
        ),
        "other": (
            "Import complete.\n"
            "- Added: {n} links\n"
            "- Invalid: {invalid}\n"
            "- Duplicates ignored: {dups}"
        ),
    },

    # ---- pannello link: avviso "gia' scaricati" -----------------------------
    "link_panel.history_title": "Links already downloaded",
    "link_panel.history_text": {
        "one": "{n} of {total} links was already downloaded before:",
        "other": "{n} of {total} links were already downloaded before:",
    },
    "link_panel.history_entry": "\u2022 {name} (downloaded on {date})",
    "link_panel.history_more": {
        "one": "... and {n} more link",
        "other": "... and {n} more links",
    },
    "link_panel.history_skip": "Skip already downloaded",
    "link_panel.history_anyway": "Download anyway",
    "link_panel.history_cancel": "Cancel",

    # ---- espansione cartelle: righe di report (FolderExpandWorker) ----------
    "folder_expand.cancelled": "Expansion cancelled.",
    "folder_expand.nothing": "No files to download.",
    "folder_expand.error_line": "\u2717 {url}\n    {error}",
    "folder_expand.unexpected_line": "\u2717 {url}\n    unexpected error: {error}",
    "folder_expand.empty_line": (
        "\u2717 \u00ab{folder}\u00bb: the folder is empty "
        "(no files to download)."
    ),
    "folder_expand.ok_line": {
        "one": "\u2713 \u00ab{folder}\u00bb: {n} file",
        "other": "\u2713 \u00ab{folder}\u00bb: {n} files",
    },
    "folder_expand.subfolders_suffix": {
        "one": ", {n} subfolder",
        "other": ", {n} subfolders",
    },
    "folder_expand.truncated_suffix": (
        " \u2014 WARNING: {n} more files left out by the limit of {max}"
    ),
    "folder_expand.skipped_suffix": " \u2014 {n} unreadable nodes skipped",
    "folder_expand.duplicates_removed": {
        "one": (
            "\u2022 {n} duplicate file (the same file pasted more than once) "
            "was removed."
        ),
        "other": (
            "\u2022 {n} duplicate files (the same file pasted more than once) "
            "were removed."
        ),
    },

    # ---- finestra principale: cartella di download --------------------------
    "main_window.dir_not_writable_title": "Folder not writable",
    "main_window.dir_not_writable_body": (
        "Cannot write to:\n{path}\n\n"
        "Falling back to the default folder."
    ),
    "main_window.dir_reset": "Download folder: default.",
    "main_window.dir_set": "Download folder: {path}",
    "main_window.dir_default": "Download folder: default (downloads/).",

    # ---- finestra principale: avvio -----------------------------------------
    "main_window.no_links_title": "No links",
    "main_window.no_links_body": "Add at least one Mega link before starting.",
    "main_window.nothing_to_download": (
        "Nothing to download: every link is already in the history."
    ),
    "main_window.previous_session_closing": (
        "Previous session still shutting down: try again in a few seconds."
    ),
    "main_window.collecting_proxies": "Collecting proxies…",
    "main_window.pool_ready": "Valid proxies: {n}. Download started.",
    "main_window.pool_failed": "Proxy pool error: {error}",
    "main_window.validation_progress": (
        "Validating proxies: {done}/{total} (alive: {alive})"
    ),

    # ---- finestra principale: espansione delle cartelle ---------------------
    "main_window.expand_already_running": "Expansion already running, please wait…",
    "main_window.expand_status": {
        "one": "Expanding {n} Mega folder…",
        "other": "Expanding {n} Mega folders…",
    },
    "main_window.expand_dialog_text": "Reading the Mega folders…",
    "main_window.expand_dialog_cancel": "Cancel",
    "main_window.expand_dialog_title": "Expanding folders",
    "main_window.expand_cancelling": "Cancelling the expansion…",
    "main_window.expand_progress": "Expanding folders: {done}/{total}…",
    "main_window.expand_cancelled": "Expansion cancelled.",
    "main_window.expand_failed_status": "Folder expansion failed.",
    "main_window.expand_failed_title": "Mega folder not expanded",
    "main_window.expand_failed_body": (
        "The files could not be read from the folder:\n\n{details}"
    ),
    "main_window.expand_truncated_title": "Very large folder",
    "main_window.expand_truncated_body": {
        "one": (
            "The folder holds more files than the app limit: "
            "{n} file will NOT be downloaded.\n\n"
            "Do you want to go ahead with the first {kept}?"
        ),
        "other": (
            "The folder holds more files than the app limit: "
            "{n} files will NOT be downloaded.\n\n"
            "Do you want to go ahead with the first {kept}?"
        ),
    },
    "main_window.expand_report_title": "Mega folders expanded",
    "main_window.expand_ready": {
        "one": "{n} file ready to download.",
        "other": "{n} files ready to download.",
    },
    "main_window.start_cancelled": "Start cancelled.",

    # ---- finestra principale: pausa / annullo -------------------------------
    "main_window.paused": "Paused.",
    "main_window.resumed": "Resumed.",
    "main_window.cancelled": "Cancelled.",

    # ---- finestra principale: ripristino sessione ---------------------------
    "main_window.restore_title": "Restore session",
    "main_window.restore_body": {
        "one": (
            "The previous session ended with {n} unfinished link.\n"
            "Do you want to load it back into the list?\n\n"
            "Chunks already downloaded will resume automatically."
        ),
        "other": (
            "The previous session ended with {n} unfinished links.\n"
            "Do you want to load them back into the list?\n\n"
            "Chunks already downloaded will resume automatically."
        ),
    },
    "main_window.restored_status": {
        "one": (
            "Restored {n} link from the previous session. "
            "Press Start to resume."
        ),
        "other": (
            "Restored {n} links from the previous session. "
            "Press Start to resume."
        ),
    },

    # ---- finestra principale: fine dei download -----------------------------
    "main_window.file_done": "File {file} completed ({done}/{total}).",
    "main_window.all_completed": "All downloads completed.",
    "main_window.all_terminated": "All downloads finished.",
    "main_window.fatal_title": "Blocking error",
    "main_window.fatal_body": "File {file}: {error}\n\nThe worker has stopped.",
    "main_window.fatal_status": "Blocking error on file {file}: {error}",
    "main_window.abandoned_status": {
        "one": "File {file} abandoned after {n} attempt: {error}",
        "other": "File {file} abandoned after {n} attempts: {error}",
    },

    # ---- finestra principale: annullo per-job -------------------------------
    "main_window.job_cancelling": "File {file}: cancelling…",
    "main_window.job_cancelled": "File {file} cancelled ({done}/{total}).",

    # ---- finestra principale: eliminazione dal disco ------------------------
    "main_window.delete_title": "Delete from disk?",
    "main_window.delete_folder_job_body": (
        "Delete file {file} from the downloaded folder?\n"
        "The other files of the same Mega folder stay where they are.\n"
        "This cannot be undone."
    ),
    "main_window.delete_folder_body": (
        "Delete the disk folder of file {file}?\n"
        "This cannot be undone."
    ),
    "main_window.delete_missing": "File {file}: folder not found on disk.",
    "main_window.delete_done": "File {file}: folder deleted ({name}).",
    "main_window.delete_failed_title": "Folder deletion failed",
    "main_window.delete_failed_body": "Cannot delete {path}:\n{error}",
    "main_window.delete_nothing": "File {file}: nothing to delete on disk.",
    "main_window.delete_file_done": "File {file}: file deleted ({name}).",

    # ---- finestra principale: riavvio dei job -------------------------------
    "main_window.restart_no_url": (
        "File {file}: URL not found, cannot restart."
    ),
    "main_window.restart_failed": "File {file}: restart failed.",
    "main_window.restart_queued": "File {file}: restart queued.",
    "main_window.restart_all_done": {
        "one": "Restarted {n} download.",
        "other": "Restarted {n} downloads.",
    },

    # ---- finestra principale: banda dei proxy -------------------------------
    "main_window.proxy_speed_no_session": "Proxy speed: no active session.",
    "main_window.proxy_speed_no_proxy": (
        "Proxy speed: no proxy available in the pool."
    ),

}
