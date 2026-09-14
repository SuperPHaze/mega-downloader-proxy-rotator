# Changelog

**English** · [Italiano](CHANGELOG.it.md)

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [2.1.0] — 2026-09-14

### Added
- **Notification area icon, next to the clock.** When you minimize the window the program asks
  where to put it — **notification area** or **taskbar**, the way it used to be — and the question
  has a **"Remember this choice"** checkbox. From the icon: double-click to reopen the window, a
  menu with **"Show window"** and **"Quit"**, and a mouse tooltip with the session status (files
  running, completed, speed). While the app is in the notification area it no longer appears in the
  taskbar, and any open detail windows go with it (they come back, as they were, on restore). New
  **pop-up notices**: on every completed file, on every failed file and when the queue is done.
  The window close button (the X) is unchanged: it closes the application. If the notification area
  is not available, no question and no icon: minimizing behaves exactly as before.
- **Settings menu → "On minimize:"**, with the **"Ask every time"** button: it brings the question
  back after it was silenced with "Remember this choice". The mouse tooltip tells you which choice
  is currently in force.
- **Startup with no terminal window.** `avvia.bat` now launches the program with `pythonw.exe`: no
  black window left open next to the application. The new **`avvia-debug.bat`** does the opposite
  and keeps the terminal visible: it is the backup launcher to use when the app does not start and
  you want to see why. `install.ps1` creates both files.

### Fixed
- **`package.ps1` also notices new untracked `.bat` files**, not just `.py` ones: the two
  launchers are front and centre for whoever receives the package, and a new one would have
  fallen out of the zip with nobody noticing until the double-click that did nothing.
- **`install.ps1` really does set everything up in one pass**: besides `requirements.txt` it now
  also installs `requirements-dev.txt` (needed by `pytest` and `tools/demo/demo_runner.py`, which
  previously had to be installed by hand) and checks/installs **ffmpeg** via winget (needed only by
  the demo runner in video mode; only a warning, never a blocking error, if it is missing or winget
  is unavailable). New `-Minimal` flag for those who want just the base app, with no test/tool
  dependencies and no ffmpeg. The final smoke test now builds the module list from a real inventory
  of the dependencies instead of a fixed list in the code.
- **Application icon loaded explicitly at all of its sizes.** The `assets/icon.ico` file contains
  seven of them (16, 24, 32, 48, 64, 128, 256 pixels): they are now read and registered one by one,
  instead of leaving it to the image reader to decide how many to expose. The `.png` fallback also
  kicks in when the `.ico` exists but cannot be read (the check used to rely on an internal detail
  of the graphics library), and the log warning for "nothing loaded" is now covered by a test.
- **Silent startup with no console: output capture no longer breaks.** With no terminal,
  `sys.stdout`/`sys.stderr` do not exist, and the first log line would have brought the program
  down before the window even appeared. Now `logs/terminal-log.txt` remains the only copy of what
  used to be on screen and keeps being written, and an unhandled exception on the main thread also
  ends up in `logs/crash.log` — where `tools/report.py` reads it — instead of vanishing along with
  the terminal that is not there.

## [2.0.0] — 2026-08-21

### Added
- **Interface in Italian and English.** On startup the program follows the system
  language (Italian if the system is in Italian, English in every other case) and the **Settings**
  menu gains a **Language** row with "Automatic / Italiano / English". The choice applies
  **immediately**, with no restart, and is remembered next time. Translated: the **command bar**,
  the **window title**, the "new version available" bar, the **About**, **Experimental Features**
  and **Paste Mega links** windows, the whole dashboard (**proxy area**, **statistics**,
  **download list** with filters, cards and empty state), the **link panel**, **Mega folder
  reading** and every message of the **main window**: start-up warnings, restoring the previous
  session, delete-from-disk confirmations and the status line at the bottom. Singular and plural
  are correct in both languages ("1 link ready" / "2 links ready", "1 subfolder" /
  "3 subfolders"). Also translated: the **per-download detail window** (summary, IP history,
  attempts log) and the **error messages** of individual files, including the status lines of
  proxy collection; if you switch language while a detail window is open, the log already
  written is rewritten in the new language too. Messages in the log files stay in Italian:
  they are diagnostic and must remain stable.

### Changed
- **English interface wording polished**: "Selection by speed" became "Speed-based selection"
  (the same term the guide uses), "Limit min/file:" became "Time limit (min/file):", and the
  button that opens the information window is now called "About", like the window itself.

### Fixed
- **Single-file name now read correctly** (it fell back to `mega_<handle>` instead of the real
  name). Some Mega files have an attribute blob with non-zero leftover bytes after the name
  (e.g. files renamed on Mega's side): the reader expected the whole decrypted string to be
  valid JSON and failed, falling back to the placeholder even with the right key and content.
  Now only the valid JSON object is extracted, ignoring the leftover bytes. While at it, the
  blob decoding moved from latin-1 to UTF-8: accented names no longer risk mojibake.
- In a download's history the line for a failed attempt repeated "Attempt N:" twice
  ("Attempt 1: Attempt 1: download failed…"). It now appears once.
- **Ungrammatical Italian singulars.** When the count was 1, some Italian messages stayed in
  the plural: "1 sottocartelle", "1 file pronti al download", "1 file duplicati … sono stati
  rimossi", "1 file NON verranno scaricati", "dopo 1 tentativi", "chiusa con 1 link non
  completati", "Ripristinati 1 link", "Riavviati 1 download". The sentence is now singular.
- **A download's status is no longer shown in raw form.** The detail window read "in_corso",
  "abbandonato" — the program's internal value — instead of "Running", "Abandoned". It now uses
  the same labels as the download list, in both languages.
- **The status label is no longer clipped**: the longest one (the Italian "Abbandonato") did not
  fit inside the badge and was cut off halfway.

## [1.21.0] — 2026-08-18

### Added
- **Support for Mega folder links (`/folder/`).** You can now paste the link of a shared folder
  directly: on Start the program reads its listing and **expands it into the individual files**,
  which are then downloaded by the usual engine (proxy rotation, parallel chunks, resume of
  interrupted downloads, history). Every format is recognised: the whole folder
  (`/folder/<id>#<key>`), the legacy format (`#F!<id>!<key>`), and links pointing to a single file
  or to a subfolder inside the shared folder. Folder links and single-file links can be mixed
  freely in the same paste.
- **Files from a folder are saved as a tree**, under a single folder named after the Mega folder
  and with the original subfolders preserved
  (`<download folder>/<Mega folder name>/<subfolder>/<file>`). Names that are invalid on Windows
  are fixed and duplicates get a numeric suffix, never overwriting anything. If you paste **two
  different folders with the same name**, the second one goes to "Name (2)": the two trees stay
  separate instead of mixing.
- **Targeted deletion of a folder's files.** Cancelling or deleting a file that came from a folder
  removes **only that file** (along with its temporary files); the other files of the same folder
  stay where they are.
- In the "Incolla link Mega" (Paste Mega links) window a **"Cartelle"** (Folders) counter tells
  folder links apart from single-file links.

## [1.20.1] — 2026-07-02

### Changed
- **More compact proxy area.** The "↻ Banda", "↻ Banda proxy" and "Reset cache" buttons are now
  stacked vertically to the right of the pool stats, taking up less horizontal space.
- **Proxy-area stats laid out on two rows.** The seven cards (Vivi, Validazione, Scartati,
  Ricariche, Ultimo refill, Banda, Banda proxy) are now arranged on two rows (a 4+3 grid) instead
  of a single row: each card has room for its own label without clipping, even when the window is
  resized.

## [1.20.0] — 2026-07-02

### Added
- **Choosable download folder from the GUI.** Under **Settings → "Cartella download:"** you can
  pick where files are saved; the choice is remembered across sessions. If you pick nothing, the
  default folder is used (the program's `downloads/`). If the chosen folder isn't writable, the
  program warns you and reverts to the default.
- **Session restore on startup.** If the program closes (or crashes) with unfinished downloads, on
  the next launch it offers to **reload the remaining links**. Already-downloaded pieces resume
  automatically: just press Start.
- **Disk-space check before starting.** If there isn't enough room for the file (plus a safety
  margin), the download is abandoned right away with a clear message, instead of failing cryptically
  halfway through on a full disk.
- **Honoring the Mega CDN `Retry-After` header.** On rate-limits (403/509) and the concurrent-IP
  limit (429), if the server states how long to wait, the wait follows that value (up to a cap)
  instead of a blind backoff.
- **Continuous Integration (CI).** A GitHub Actions workflow runs the test suite automatically on
  Windows (Python 3.11 and 3.13) on every push and pull request.
- **Authenticated proxy support** (`user:password`) in the proxy URL builder. Free lists don't need
  it: it's groundwork for any authenticated lists.

### Changed
- **Prudent restore of proxy reputation from cache.** On a warm start, proxies that had a good
  reputation in a previous session start with an advantage but with their score **halved toward
  neutral** (free proxies change quality constantly); neutral or penalized proxies start from
  scratch, inheriting neither penalties nor an inflated "resurrection".
- **More robust filenames on Windows.** The downloaded file's name is cleaned of forbidden
  characters (`: ? * " < > |`) and reserved device names (`CON`, `NUL`, …), preserving the
  extension. Previously such a name made saving fail and wasted every attempt, with a misleading
  error that looked like a proxy problem.
- **More responsive cancel during link resolution.** A "Cancel" that arrives while the program is
  resolving a Mega link (with its retries) is now honored immediately, instead of hanging for up to
  tens of seconds.

### Fixed
- **Zero-byte files are no longer abandoned.** An empty file on Mega was requested with an invalid
  byte range and failed repeatedly until abandoned; it is now correctly created as an empty file.

## [1.14.0] — 2026-07-01

### Changed
- **The download-list filter buttons now show the file count per state.**
  Each button reports in parentheses how many files fall into its category —
  "In corso (N)" (queued + running), "Completati (N)" (completed) and
  "Non completati (N)" (failed + cancelled + abandoned). The counts update in
  real time on every download status change, so the makeup of the session is
  visible at a glance without switching between filters.

### Fixed
- **Speed test reporting impossible bandwidth values.** Throughput could "explode"
  to thousands of Mbit/s in two cases: when a proxy downloaded the whole file
  during the TTFB and then burst it from the local buffer (the timed window
  collapsed toward zero, against a floor of just 0.001 s), and when the test file
  was served from an ISP/router/proxy cache at local-network speed. Throughput is
  now computed over a robust window (it excludes connect+TTFB but falls back to
  the full window when the body arrives in a burst, with a minimum that avoids
  dividing by ~zero), and all speed tests (line, proxy and validation) use a URL
  with a cache-busting parameter, so the reported bandwidth stays realistic.

## [1.13.2] — 2026-06-29

### Added
- **Proxy speed test in the proxy zone**, distinct from the direct line speed test. There are now two
  side-by-side measurements, differentiated at a glance (different colors):
  - **Banda** (green): line bandwidth, direct download **without proxy** (the pre-existing measure).
  - **Banda proxy** (blue): real aggregate bandwidth the **live proxy pool** can deliver, measured by
    sampling the best proxies and downloading through them in parallel.
  The **↻ Banda proxy** button is enabled only during a session (at rest there are no proxies to
  test). The measurement is resilient: a slow or dead proxy contributes only the bytes actually
  downloaded, without failing the whole test. Comparing the two figures shows how close the proxy pool
  gets to your own line capacity.

## [1.13.1] — 2026-06-29

### Fixed
- **Speed test (Speed-based selection) reporting unrealistic values**: the timer started before the
  request, so the measured time included the connection phase (connect + TLS + time-to-first-byte)
  through the proxy. With free proxies this latency is often several seconds and, on a download of just
  1 MB, *dominates* the calculation: a proxy that actually runs at ~1 MB/s was measured at ~260 KB/s
  (−75%). Now only the **body transfer** is timed (the clock starts at the first byte received,
  excluding the connection), yielding the real sustained throughput (residual error ≈ 1%). Fast proxies
  with high latency are no longer discarded or ranked incorrectly.

## [1.13.0] — 2026-06-28

### Changed
- **Markedly improved download throughput** (≈ +148% on average in tests on large files, from ~5.8 to
  ~14.3 MB/s): the pool of validated proxies is much larger. Target alive proxies **60 → 300**, maximum
  validation candidates **3000 → 12000**, validation workers **100 → 200** (stage 1) and **60 → 120**
  (stage 2), background resupplier thresholds **15/30 → 80/160**. More alive proxies means fuller lanes
  and, above all, fewer speed drops over long sessions (the pool doesn't "burn out" because it resupplies
  faster).
- Throughput watchdog reverted to baseline values (minimum **200 KB/s** over a **20 s** window, **15 s**
  grace) after a more aggressive experiment that had regressed (it dropped too many proxies too early,
  leaving lanes empty).

### Added
- **"Black-box" telemetry**: structured, asynchronous capture of every chunk attempt and 1 Hz samples,
  in per-session files under `logs/telemetry/`, at negligible cost to the download. A command-line tool
  `tools/analyze_telemetry.py` turns it into an HTML/Markdown report + CSV datasets + a compact AI export
  — useful to understand *where* speed is lost (per-source quality, stragglers, line utilization,
  dominant constraint).
- **Speed-admission** (experimental, command-line `--speed-admission KB/s`): admits into the pool only
  proxies that pass a real speed test at the given threshold, while keeping score-based selection and the
  normal connection count. Useful to favor proxy quality.
- Headless runner flags for `tools/cli_download.py`: `--selection-mode`, `--connections`,
  `--concurrency` for controlled, GUI-less tests.

### Fixed
- **Handling of Mega's `429 "Too Many Concurrent IP Addresses"`**: it is a *per-file* limit on the number
  of distinct IPs downloading the same file at once. It was previously treated as a generic error and the
  program switched to another proxy — adding an IP and *worsening* the limit, up to abandoning the file.
  It now **retries the same proxy** (same IP) after a short wait, without penalizing it. More robust
  downloads and fewer abandonments.
- **Headless CLI runner hung on an abandoned link**: it did not handle the `abandoned` signal, so a link
  that exhausted its attempts was never removed and the process stayed waiting. It now terminates
  correctly.

## [1.11.3] — 2026-06-27

### Added
- **"Reset cache" button in the proxy zone**: deletes `proxy_cache.json` on demand so the
  next startup performs a fresh scrape from scratch. Useful for repeated configuration tests.
- **Collapsible Statistics widget** with a summary header always visible (time, volume,
  throughput, job counts). Expanded/collapsed state persisted in preferences.

### Fixed
- **"In progress" filter not updating on job completion**: the card disappeared only after
  manually switching the filter. `JobsPanel` now subscribes to `job_updated` and updates
  the individual card's visibility on status change, with no user action required.
- **Download folders renamed with the file name**: previously `downloads/<hash>_<id>/`.
  On the first successful resolve the folder is renamed to `<sanitised_file_name>_<id>/`,
  making the `downloads/` directory immediately recognisable. Windows-safe sanitisation
  (strips `<>:"/\|?*` and control characters, max 120 chars). If rename is not possible
  (collision, lock, permissions), the old path is kept and a warning is logged — the
  download is not interrupted.

## [1.11.2] — 2026-06-26

### Added
- **ProxyScrape JSON source** (GitHub mirror, ~22k proxies updated every 5 min): 3 separate
  endpoints per protocol (http/socks5/socks4) with pre-calculated metadata (`latency_ms`,
  `uptime_percent`, `anonymity`) propagated to the proxy dict up to the pool. Pre-filter in the
  scraper that discards candidates with `uptime_percent < 50%` or `latency_ms > 3000` before
  validation, saving stage 1/2 time. 30s timeout for these sources (the JSON is several MB).
- **Adaptive refill threshold** (with speed-based selection active only): the static refresher
  threshold (15/30) is replaced by a dynamic threshold calculated on real demand —
  `max(10, active_downloads × connections × 3)` for LOW, double for HIGH. Thresholds are
  updated every time a download starts or ends, avoiding unnecessary refills under low load
  and raising the margin when load grows. With the flag OFF, behavior is identical (static thresholds).
- **Statistics widget** with complete session metrics: total downloaded volume (including
  partial bytes from failed/cancelled jobs), effective throughput (volume / active time),
  arithmetic average per-download, session peak/minimum, active time with auto-freeze at
  session end, per-job detail rows, "Copy summary" button (plain text to clipboard).
- **Final per-download average** shown on job cards at termination (below the status badge):
  frozen average speed, partial volume, and duration.

## [1.11.1] — 2026-06-26

### Added
- **Speed-based selection** (Experimental Features): alternative download profile that activates
  a third validation stage (real 1 MB speed test), dual threshold (fixed admission at 100 KB/s +
  configurable preference, default 500 KB/s), 5 000 candidates (instead of 3 000), connections
  reduced to 5, and throughput-based round-robin selection. Slow proxies remain as fallback: the
  download degrades rather than stopping. Enabled from the Experimental Features panel with a
  checkbox and a threshold spinbox in KB/s.

## [1.11.0] — 2026-06-25

### Added
- Added ~20 SOCKS4/SOCKS5 sources (TheSpeedX, monosans, ShiftyTR, jetkai, roosterkid, mmpx12, vakhov, zloi, rdavydov, Zaeem20, ErcinDedeoglu, Thordata, yemixzy, proxifly): more raw candidates to raise the number of proxies that hold up against Mega.
- SOCKS4/SOCKS5 proxy support in the engine (`socks5h`/`socks4` scheme via PySocks; the scraper labels the protocol per source). SOCKS sources are added separately.
- Capture of the entire terminal output in `logs/terminal-log.txt` (reset on every startup), for quick diagnosis and sharing.
- **Proxy cooldown on Mega rate-limit (403/509)**: put to rest for `PROXY_COOLDOWN_SECONDS` (90s) instead of being discarded, to avoid draining the pool on long sessions.
- Re-exposed the connections-per-file control in the Experimental Features tab (for testing).
- Additional chunk sizes 64 / 128 / 256 MB in the size combo (default unchanged at 32 MB).
- **Configurable per-chunk budget** from the Experimental Features tab (default unchanged at 180s): maximum time given to a proxy to finish a chunk before switching.
- **Short description + "i" icon** on both Experimental Features controls (connections per file, per-chunk budget): the extended explanation opens on click, keeping the dialog compact.

### Changed
- **Larger proxy pool**: increased the number of validated candidates to **3000** (added ~20 new HTTP/HTTPS sources). The target of alive proxies has been set to **60**, and the refill thresholds to **15/30** — realistic values for validation against Mega.
- The default chunk size is **32 MB**, and parallel connections per file are **10**.
- The cooldown for proxies that hit a Mega rate-limit (403/509) is **90 seconds**.

### Fixed
- **Pool starvation**: fixed an issue where a proxy in cooldown (403/509 rate-limit) still counted as "alive", so when almost the whole pool went into cooldown together `size()` stayed > 0 and `refill_blocking()` kept being skipped forever while `get_next()` had nothing left to select, pinning the pool at 1-2 proxies. A proxy in cooldown no longer counts as alive until it expires.
- The `hookzof-socks5` source was treated as http, now correctly SOCKS5.

## [1.10.0] — 2026-06-24

### Added
- **Session speed metrics**: average, peak, and minimum (over samples taken while a download is active) alongside the instantaneous speed, in the dashboard.
- **Segmented bar** for job status (running/queued/completed/failed, proportional).
- **Dedicated proxy zone** (new `ProxyBar` widget), with pool health as compact cards: alive proxies, validation outcome, proxies discarded this session (alive→dead transitions), number of pool refills, and time since the last refill.

### Changed
- **Dashboard reorganized into a single row with 3 zones** (speed · downloads · proxy), compact and separated by inner vertical lines: speed zone with a **radial gauge** (`RadialGauge`, current speed as a % of the session peak, value shown at the ring's center) plus peak/average/minimum/ETA/elapsed time; "Downloads" zone (renamed from "Jobs") with total, segmented bar, and counters; proxy zone as cards.
- **Job list filters changed from a dropdown to buttons**: "Running" / "Completed" / "Not completed" as mutually-exclusive buttons, with no "Show:" label.

### Fixed
- **Session speed peak**: removed the GB-scale spike on resumed downloads (the sampler started from `prev_bytes=0`, counting already-downloaded bytes). Added a guard against implausible samples (non-finite, negative, or above a safety ceiling) on both `SessionSpeedStats` and the dashboard's speed feed.
- **Installer smoke test** (`install.ps1`): now run from a temporary file instead of `python -c`, fixing a `SyntaxError` caused by how PowerShell passed the multi-line script.

## [1.9.0] — 2026-06-22

### Added
- **Universal structured logging** (`logs/events.jsonl`, JSON Lines at DEBUG level): every logging record is also written in structured form, with no upstream filtering. Primary source for the new diagnostics.
- **New `tools/report.py` tool**: reads `logs/events.jsonl` and `logs/crash.log` (read-only, streaming) and generates an HTML report in `logs/reports/` with sessions, heartbeat timeline, errors/anomalies, download events, and native crashes.

### Changed
- **All logs, the crash log, and generated reports are consolidated into the `logs/` folder** (previously scattered in the project root): `app.log`, `crash.log`, `failed_links.log`, `download_history.log`, `proxy_sources_stats.log`, `events.jsonl`, `reports/`.
- **New download defaults**: chunk size 8 → **32 MB**, parallel connections per file 4 → **10**. Parallel files remains 1; speed-based proxy selection remains disabled ("score" mode).

### Removed
- `tools/analyze_crashlog.py`, replaced by `tools/report.py` (primary source events.jsonl instead of app.log/crash.log).
- **Experimental features retired from the interface**: the "connections per file" and "speed-based selection" controls have been removed from the "Experimental Features" panel, which remains present but empty (placeholder). The download engine (`selection_mode` and `connections_per_file` parameters) was not touched: it remains available for future reuse. Any experimental preferences saved by previous versions are now ignored.

## [1.8.3] — 2026-06-22

### Added
- **Experimental Features** — new dedicated panel, all options **disabled by default**:
  - **configurable** parallel connections per file (default 4);
  - **speed-based proxy selection**: the pool measures the real throughput of each proxy and prefers the fastest ones, rotating among the best to avoid getting them rate-limited by Mega.
- **Crash diagnostics suite** (passive, always on): native crash tracebacks (`faulthandler`), multi-thread exception capture, periodic heartbeat with memory usage, session markers (start / clean exit), Qt message routing into the log.
- **Crash log analyzer** with HTML report (`tools/analyze_crashlog.py`).

### Fixed
- Version number reverted to 1.8.3
- **Stabilized proxy validation concurrency**, the cause of a native crash (access violation) under load: Stage 1 worker cap lowered (200 → 100) and an armed/disarmed hysteresis added to the background refresher to eliminate repeated refill bursts (observed up to 66 in a single session, with peaks of ~200 threads). Download connections are untouched: no impact on speed.
- **Fixed the diagnostic heartbeat's memory probe**: the Windows fallback (ctypes/psapi) didn't set `restype`/`argtypes` on the system functions, causing a silent handle error and always reporting `mem_rss=n/d` in the logs. It now reports a real number.
- **Fixed a native crash (access violation) in `SessionState.is_cancelled`** under high concurrency: dozens of download threads (`ThreadPoolExecutor`, not `QThread`) hammering the shared state through Qt primitives (`QMutex`/`QWaitCondition`) could corrupt memory. Migrated to `threading.Lock`/`threading.Condition` (stdlib); API and pause/cancel semantics unchanged.

### Changed
- **Logging discipline**: reclassified from ERROR to WARNING the expected/transient failures of free proxies (chunks failed after exhausting retries, link abandoned after the attempt cap) — these are physiological, not bugs. Added a `CONFIG` line at session start with the active operating parameters (connections, chunk size, speed-based selection, parallel files, validation workers) to correlate configuration with crashes in logs collected from users. Formalized the rule in `.claude/rules/logging.md`.

## [1.8.2] — 2026-06-21

### Added
- **Bilingual EN/IT documentation** with language selector: README and operating guide.
- **Bilingual website** (English by default + Italian) with language toggle.
- **Bilingual** `install.ps1` and `package.ps1` script messages (English by default, `-Lang IT` for Italian).

### Changed
- Official name unified throughout the project and in the window title: **"Mega Downloader Proxy Rotator (MDPR)"**.
- Terminology unified on **"chunk"** across documents and the website.
- Operating guide rewritten with values aligned to the code.

### Notes
- Republished the repository with clean git history.

## [1.8.1]

### Added
- First public release. Engine: fixed-size chunk queue downloaded via parallel HTTP Range connections on different proxies, two-stage validated proxy pool with reputation scoring, cache for "hot" startup, streaming AES decryption, tabbed GUI with light/dark themes, download history with duplicate warnings, CLI mode.
