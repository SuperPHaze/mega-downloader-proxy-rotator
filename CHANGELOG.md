# Changelog

**English** · [Italiano](CHANGELOG.it.md)

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [1.13.3] — 2026-06-29

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
