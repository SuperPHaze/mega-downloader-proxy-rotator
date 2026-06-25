# Changelog

**English** · [Italiano](CHANGELOG.it.md)

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- **Larger proxy pool**: target alive proxies 80→200, validated candidates 1000→3000, refill thresholds 40/80→100/180 (consistent with the new target); added ~20 new HTTP/HTTPS sources. Initial/refill validation takes longer but runs in the background; the goal is to sustain long sessions with many connections without draining the pool.

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
