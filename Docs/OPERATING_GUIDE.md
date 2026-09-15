# Operating guide — Mega Downloader Proxy Rotator (MDPR)

**English** · [Italiano](GUIDA_OPERATIVA.md)

This guide describes what the program does, how the download is structured, and what behaviors to expect during use. It is aimed at a technical audience: the goal is to explain how the tool actually works and the rationale behind its choices, without showing off jargon but also without watering down the core of the system.

---

## 1. Purpose and scope

MDPR is a desktop application for Windows (Python + PyQt6) that downloads files from Mega.nz by routing traffic through free public HTTP proxies. The problem it addresses is the throttling Mega applies per IP address: downloading from a single IP quickly hits bandwidth and volume limits. MDPR works around the constraint by spreading the transfer across multiple proxies, each with a different egress IP.

The tool is single-user and single-process, with no backend. It started as a testbed for IP rotation (re-downloading the same file multiple times through different proxies to measure Mega's rate-limit behavior) and is now used as a real-world downloader.

The intended use is downloading files you have the right to access. Public proxies are run by unidentified third parties and offer no confidentiality guarantees: they must not be used for sensitive data.

---

## 1-bis. Starting the program: two launchers

The installation (`install.bat`) prepares **two** launcher files in the program folder, doing the same thing in two different ways.

**`avvia.bat` is the normal launcher**: it opens the application **with no terminal window**. That is the one to use. The moment it starts you see a black window flash into view and disappear: that is Windows opening a console for any `.bat` file, not the program. To avoid even that flash you can create a Windows shortcut by hand pointing straight at `venv\Scripts\pythonw.exe` with the argument `-m src.main`.

**`avvia-debug.bat` is the backup launcher**: it starts the application **with the terminal visible** and keeps it open if something goes wrong. Use it when the app does not start and you want to see why with your own eyes.

With no terminal, everything that used to be readable on screen only goes into the files under `logs/`: the technical log (`logs/app.log`), the structured log (`logs/events.jsonl`) and the raw copy of the output (`logs/terminal-log.txt`, reset at every launch). A sudden error is captured too: unhandled exceptions end up both in the technical log and in `logs/crash.log`, alongside low-level crashes. **One case only stays invisible**: a failure happening *before* the logging system is up — an incomplete installation, say, or a corrupted program file. That is exactly what `avvia-debug.bat` is there for.

---

## 2. Three-phase download architecture

Every download session is made up of three phases that operate in parallel once started.

**Pool provisioning.** Before downloading, the program builds a set of working proxies: it collects lists from numerous public sources and runs them through a two-stage validation (three stages with speed-based selection active; section 3). If a cache from a previous session is available, it starts "warm" from that and validates in the background.

**Download.** The file is resolved and split into a queue of fixed-size chunks, downloaded by several parallel HTTP Range connections, each routed through a different proxy, decrypted in streaming fashion, and reassembled (sections 4 and 6).

**Pool maintenance.** For the entire duration of the download, a background component monitors the size and quality of the pool and replenishes it as proxies are exhausted or degrade (section 7).

---

## 3. The proxy pool: collection, validation, scoring

Public proxy lists are large and largely made up of addresses that are no longer operational. Using them unfiltered would produce constant failures. The program therefore applies a **two-stage validation** (three with speed-based selection active), sized to quickly discard useless candidates and spend the more expensive test resources only on the promising ones.

**Pre-filter for sources with metadata (ProxyScrape JSON).** Sources that provide pre-calculated metadata — in particular the three ProxyScrape JSON endpoints — include in their payload fields such as `uptime_percent` and `latency_ms` for each candidate. The scraper uses them as a pre-filter before validation, discarding candidates with `uptime < 50%` or `latency > 3000 ms`. This saves stage 1/2 time without replacing validation: proxies that pass the pre-filter are still validated normally.

**Stage 1 — reachability.** A fast, high-concurrency pre-filter (up to 200 workers, 4 s timeout) against a highly reliable connectivity endpoint (Google's `generate_204`). It only verifies that the proxy can complete an HTTP round trip; it does not judge Mega reachability. It serves to eliminate dead proxies without wasting a test on stage 2's limited capacity.

**Stage 2 — Mega reachability.** Survivors are tested, at moderate concurrency (120 workers) because Mega rate-limits, against the host of Mega's download API — the same one used by real link resolution, not the homepage. The success criterion is any HTTP response received from the host, even an application-level error: it means the round trip reached its destination. A stricter criterion would discard proxies that are perfectly valid for downloading.

Validation stops early once the target number of alive proxies (300) is reached, and in any case never exceeds a candidate cap (12 000, reduced to 5 000 with speed-based selection active), so startup doesn't turn into minutes of waiting.

**Stage 3 — speed test (optional).** If "Speed-based selection" is enabled in the Experimental Features panel, proxies that passed stage 2 are further filtered with a real throughput test: 1 MB is downloaded from an external server (not Mega) with a 15-second timeout and 30 parallel workers. Proxies below the fixed admission threshold (100 KB/s) are discarded; those above the configurable preference threshold (default 500 KB/s) are served first in the pool; those in between remain as fallback and are used when "fast" proxies are exhausted — the download degrades but does not stop. Throughput is measured over the body transfer only (excluding connect and time-to-first-byte), but falls back to the full window when the body arrives in a burst from a buffer, and avoids measuring bandwidth on a cached file (URL with a cache-busting parameter): this way impossible bandwidth values are never reported.

It is expected, and not a flaw, that out of hundreds or thousands of candidates only a few dozen survive: free proxies have a high mortality rate, on the order of 70%.

**Reputation score.** Every proxy in the pool has a score. It starts at 0; a success increases it (+5), a failure penalizes it (−10), and below a threshold of −20 it is considered dead and set aside (but it can rejoin on a later refill if it reappears in the lists). Selection is round-robin by score; ties are broken in favor of the proxy with lower latency.

Penalties distinguish the cause: an explicit rejection from Mega's CDN due to IP saturation (403, 509) does not penalize the score, but rests the proxy for a short period instead (section 14); CDN overload (503) is instead a "hard" penalty; a transient error (timeout, insufficient throughput, network error) is a "soft" penalty. Successes — a completed segment or a successful egress IP check — are recorded and raise the score.

---

## 4. Download: parallel chunks, decryption, atomic write

A direct download from Mega proceeds in a single stream, as fast as the one connection serving it: with a slow free proxy, the download is slow. MDPR works around the limit by splitting the file into **fixed-size chunks** (32 MB by default) and downloading them with **several parallel HTTP Range connections** (10 by default), each routed through a different proxy. Completed chunks are reassembled in the correct order.

Rotation is therefore per-chunk, not per-file: if a proxy drops, at most the chunk in progress is lost, not the entire transfer. Files smaller than the parallelization threshold (1 MiB) are downloaded serially, since splitting would bring no benefit.

The program can also work on **several files at once**: the default is 1, adjustable from the GUI up to 5. Increasing it, however, multiplies the pressure on the proxy pool and can degrade all downloads in progress, which is why the default is sequential.

The payload delivered by Mega is encrypted. The program **decrypts it in streaming fashion** (AES-CTR) as chunks arrive, writing directly to the destination file: RAM usage stays constant even for files of many GB, and what lands on disk is already the final, usable file.

Writing follows the **`.part` + atomic rename** pattern: the transfer always happens on a `<name>.part` file, accompanied by a `.progress.json` sidecar that records completed chunks. Only when the download is complete is the file renamed (an atomic operation) to its final name. The existence of the final name is the only completion marker.

---

## 5. Experimental features

The "Experimental Features" panel exposes three controls, each with a short description and an "i" icon that opens the extended explanation: the number of **connections per file** (how many parts of the same file to download in parallel, each over a different proxy; default 10), the **per-chunk budget** (maximum time given to a proxy to finish a chunk before switching; default 180 s, section 6), and **speed-based selection** (checkbox + threshold spinbox in KB/s).

**Speed-based selection** is an alternative download profile: when active it adds a stage 3 validation (real 1 MB speed test), lowers candidates from 12 000 to 5 000 (the speed test is costly), reduces connections per file to 5, and selects proxies by measured throughput. Fast proxies (above the configurable threshold, default 500 KB/s) are preferred; slow ones but above the fixed admission threshold (100 KB/s) remain as fallback. Off by default.

> **A note on default values.** The program is tested on long sessions with the factory defaults. Changing the parameters (parallel downloads, connections per file, chunk size, per-chunk budget) may help in some scenarios and hurt in others, because the behaviour of free proxies is highly variable. Work is ongoing to improve throughput, proxy quality, and resilience on long sessions. For now it is recommended to keep **1 download at a time** and a **32 MB chunk size**.

---

## 5-bis. Mega folder links

Besides single-file links you can paste the link of a **shared folder**. The whole folder
(`https://mega.nz/folder/<id>#<key>`), the legacy format (`https://mega.nz/#F!<id>!<key>`) and
links selecting a single file or a subfolder inside the shared folder are all recognised. Folder
links and single-file links can be mixed freely in the same paste.

When you press **Start**, before any download begins, the program reads the folder listing
**once** and **expands it into the individual files**: from that moment each file is an
independent download and goes through the usual engine (proxy rotation, parallel chunks, resume of
interrupted downloads, history, per-file cancellation). The operation runs in the background, with
progress shown in the status bar; when it ends, a window summarises what was found. Reading the
listing is the **only** operation that does not go through the proxies: it happens before the pool
is ready, and it is not subject to the per-IP limits that affect the actual downloads.

Files are saved as a **tree** (see section 11): all under a single folder named after the Mega
folder, with the original subfolders preserved. Names that are invalid on Windows are fixed
segment by segment, and two files that would end up with the same name after the fix get a numeric
suffix, never overwriting each other. The same holds in edge cases: if you paste **two different
folders with the same name**, the second one goes to "Name (2)" (the two trees do not mix); if
inside a folder a file and a subfolder share a name, the folder keeps the name and the file takes
the suffix. Cancelling or deleting a file from a folder removes **only that file**: the others stay
where they are, and folders left empty are cleaned up.

Special cases handled: an empty or no longer accessible folder (explicit message, no download
started); a file whose name cannot be decrypted with the link's key (skipped and reported, so that
corrupt data is not downloaded); very large folders, where beyond the file limit the program
**asks for confirmation** stating how many files would be left out, never truncating silently.

---

## 6. Watchdog and failure handling

Free proxies fail often and in different ways; the program is built to absorb them without stopping. Every chunk transfer attempt is watched by two limits.

**Throughput threshold.** If the average speed over the last 20 seconds drops below a useful minimum (200 KB/s), after an initial grace period of 15 seconds (to leave room for TCP slow-start), the attempt is aborted and the chunk retried with another proxy. This is the defense against proxies that trickle data: they send just enough bytes not to trigger a read timeout, but would effectively never finish.

**Absolute time budget.** Regardless of instantaneous throughput, a single attempt cannot last more than the configured budget (default 180 seconds, adjustable from the Experimental Features panel — section 5). This avoids getting stuck on a proxy that stays just above the threshold but doesn't finish in a reasonable time.

When an attempt fails, the program retries the same chunk with a different proxy, up to a maximum number of attempts per segment (8). If too many chunks exhaust all their attempts, the download is stopped softly: chunks already completed remain saved in the sidecar and the file is resumed from where it left off.

There are two file-level safety limits: a maximum wall-clock duration per file (60 minutes, configurable), beyond which the file is abandoned and the slot moves to the next one; and a maximum number of consecutive failed attempts for the same link (15) before abandoning it, to avoid infinite loops on files removed from Mega, invalid hashes, or blocked regions. Abandoned links are recorded in a dedicated log.

The many failed attempts visible during use are therefore expected behavior, not a malfunction: they are the cost of free proxies, and the system is designed to handle them.

---

## 7. Pool maintenance

Free proxies wear out: one that was valid a few minutes ago may no longer be. If the program only used the set collected at startup, it would eventually run dry. A **background resupplier** checks at regular intervals (every 30 seconds) how many proxies are alive and, if it drops below the threshold (80), starts a scrape and validation without interrupting downloads in progress. To avoid bursts of resupplies when the pool oscillates right around the threshold, the resupplier "disarms" itself after each run and only re-arms once alive proxies climb back above a higher threshold (160). To catch silent degradation (proxies progressively slowing down without fully dying), it also forces a resupply if the last one happened more than 5 minutes ago.

With **speed-based selection active**, these thresholds become adaptive: the low threshold is `max(10, active downloads × connections × 3)`, and the high threshold is double that. They update automatically every time a download starts or ends, so the reserve margin grows in proportion to the actual load. With speed-based selection off, behavior is identical to what is described above (static thresholds 80/160).

If the pool empties at a critical moment, it's the download itself that requests an immediate resupply and waits as long as needed: at those times you may see a pause, during which the program is rebuilding the pool before continuing. All of this is automatic and requires no intervention.

---

## 8. Memory between sessions (warm start)

Building the pool for the first time takes a while (roughly half a minute to a couple of minutes). To avoid repeating that on every launch, the program persists the best proxies to disk and reloads them on the next launch, quickly re-validating them: proxies still alive are immediately available (a "warm" start), while a full search still starts in the background. Cache entries past their validity window (6 hours) are discarded on load. From the second session onward, startup is therefore noticeably faster.

The **Reset cache** button in the proxy zone (at the bottom of the interface) deletes `proxy_cache.json` without closing the application: the next startup or session will start from scratch, useful when testing a different configuration without leftovers from the previous session. The deletion does not interrupt any download in progress.

The proxy zone also shows two side-by-side bandwidth measurements, distinguished by color. **Line speed** (green) is your own line bandwidth, measured with a direct download **without proxy**: it is computed automatically at startup and can be re-run with the **↻ Line speed** button. **Proxy speed** (blue) is instead the real aggregate bandwidth the **proxy pool** can deliver, obtained by downloading in parallel through the best proxies available at the moment; it is triggered with the **↻ Proxy speed** button, enabled only during a session (at rest there are no proxies to test). The measurement is robust: a slow or dead proxy contributes only the bytes actually downloaded, without failing the whole test. Comparing the two figures shows how close the proxy pool gets to your line capacity.

---

## 9. Session controls and resume

During a session, the available controls are pause/resume and cancel, both globally and per individual file from the table. Pausing does not lose the proxies: on resume, work continues from where it was suspended. Pausing takes effect **at the boundary of the current piece**: a chunk already in transfer is completed and only then does work suspend (suspending a piece mid-transfer would make the read timeouts expire). Canceling a single file can optionally also remove its already-downloaded data from disk.

**Adding links to a running session.** The **Add links** button stays active while downloading: pasted links join the current session without stopping anything and without redoing the proxy collection, which is the slow part of starting up. Downloads already under way keep going, and the added ones join the **queue**: the number of files downloaded at the same time does not change.

The add window asks **where** to put them: *at the end of the queue* (the default) or *right after the current download*, to jump ahead of the links already waiting. In both cases no download already under way is interrupted.

If any of the links is **already in the session** — queued, downloading or already finished — it is listed with its state and a confirmation is needed to add it anyway. The comparison is by Mega handle, so it recognises the same file even when pasted in a different URL form. It is the same warning, in a distinct form, as the one about files already downloaded in past sessions: both can appear, because they answer two different questions.

If the **queue has already finished** (every download over but the window still open), adding asks first what to do: *Carry on with this session* keeps the list, the statistics, the timer and above all the proxies already validated; *New session* puts the links back in the list and Start begins from scratch, proxy collection included.

A **folder** link added while downloading is listed first, as it is at start-up. In this case the progress window is **not modal** and says so: the downloads under way keep going and pause, cancel and the per-file detail stay reachable.

If the program is closed (or crashes) with downloads not yet completed, on the next launch it offers to **reload the remaining links** with a prompt titled "Restore session" ("The previous session ended with N unfinished links. Do you want to load them back into the list?"). By accepting, the links return to the list and — thanks to the resume described below — restart from the pieces already downloaded: just press Start.

The download list can be filtered with three mutually exclusive buttons — **In progress**, **Completed** and **Not completed** — which together cover every possible state (queued and running jobs fall under "In progress"; failed, cancelled and abandoned ones under "Not completed"). Each button reports in parentheses the number of files in its category, updated in real time, so the makeup of the session is readable at a glance without switching filters.

Resume also covers involuntary interruptions (program closed, blackout, error). Thanks to the `.part` + sidecar scheme, on resume only the missing chunks are re-downloaded; a cycle is considered complete only when the final renamed file exists, so an interrupted file is never mistaken for complete.

---

## 9-bis. Interface language

The interface is **bilingual: Italian and English**. On first launch the program follows the **system language** — Italian if the system is in Italian, English in every other case — and from then on the choice is the user's.

You change it from the **Settings → "Language:"** menu, which offers three entries: **Automatic**, **Italiano**, **English**. "Automatic" is not a language but a rule: it keeps following the system, and shows in brackets which language it is picking at that moment ("Automatic (Italiano)"). Choosing Italiano or English explicitly steps out of the rule; to go back, just set "Automatic" again. The choice is **remembered** and restored on the next launch.

The change is **immediate and needs no restart**: panels, menus, buttons, dialogs and the status line rewrite themselves in place, including windows that are already open — if a download's detail window is open, the attempts history already written is retranslated too.

The translation covers the **whole** interface, including the **error messages** of individual files, which are the part that usually lags behind: errors from the engine travel to the window as a code plus parameters, not as an already-composed sentence, and that is why they can be rendered in either language at drawing time.

**Messages in the log files stay in Italian instead**, whatever the interface language is. That is deliberate: they are diagnostic material and must stay stable over time, otherwise comparing two sessions or looking up an error in an old log would turn into a translation exercise. It applies to `logs/app.log`, `logs/events.jsonl`, `logs/failed_links.log` and to the messages of the CLI mode.

---

## 9-ter. Minimizing: notification area and notices

When you minimize the window the program **asks where to put it**, with a question titled "Minimize": **Notification area** (the icon next to the clock) or **Taskbar** (the way it has always been). The question appears at the moment you minimize and has a **"Remember this choice"** checkbox: tick it and the choice is saved and no longer asked. To go back to being asked every time: **Settings → "On minimize:" → "Ask every time"** menu; the mouse tooltip on that button tells you which choice is in force right now.

**The window close button (the X) does not change: it closes the application**, as it always has and without asking for confirmation. The notification area is a place to *minimize* the window to, not a way to quietly close the program.

While the application is in the notification area it **no longer appears in the taskbar**, and any detail windows left open disappear along with the main window — coming back to their place, just as they were, on restore. From the icon you get back to the window with a **double-click**, or from the right-click menu, which has two entries: **"Show window"** and **"Quit"**. Resting the mouse on the icon shows the session status: how many files are running, how many are completed out of the total, and the overall speed.

The icon also sends **pop-up notices**: on every **completed file**, on every **failed file** (with the reason) and when the **queue is done**. Notices arrive with the window open too, which is why the icon is there from startup and not only while minimized. A failed attempt that will be retried produces no notice at all: you get told when a file is really finished, one way or the other.

An **unrecoverable** error on a file, which with the window open raises a message box, arrives **only** as a pop-up notice while the application is in the notification area: a lone dialog on screen, without even a taskbar entry to get back to it, would be worse than the problem it reports. The error is still written on the file's card and in the status line.

If the notification area is not available — switched off in the Windows settings, or a session without a full graphical shell — **neither the question nor the icon appears**: minimizing behaves exactly as before and a line in the technical log says so.

---

## 10. Statistics dashboard

The **Statistics** panel, visible below the main dashboard, aggregates session metrics in a single place designed for comparing configurations during tests. The panel is **collapsible**: clicking the header shrinks it to a single summary line (active time, volume, throughput and job counts) that remains always visible. The expanded/collapsed state is remembered between sessions.

**What it shows:**

- *Session*: active time since startup. The clock **auto-freezes** when all downloads finish (in any state), keeping the numbers stable for review. Starting a new session resets the clock.
- *Downloaded volume*: cumulative total across all session jobs, including partial bytes from failed, cancelled, or abandoned jobs.
- *Session speed*: two distinct formulas:
  - **Effective throughput** = total volume / active time (measures how many bytes are actually delivered per unit of time);
  - **Average per-download** = arithmetic average of the mean speeds of each finished job (indicates the typical quality of a single download).
  - Session peak and minimum from 1 Hz sampling.
- *Job counts*: totals by status and completion rate.
- *Per-download detail*: one row per job with file name, volume, duration, and final average speed (or current speed for jobs still in progress).

**"Copy summary" button**: produces a plain-text block in the clipboard with all the numbers listed above, ready to paste into a comparison note across tests with different configurations.

Each job card in a terminal state also shows a summary line with the final average speed, downloaded volume, and duration of that individual download.

---

## 11. Output, history, and logs

Downloaded files are saved in dedicated subfolders inside the **download folder**. By default this is the project's `downloads` folder, but it can be changed from the **Settings → "Download folder:"** menu: the choice is remembered across sessions and, if the chosen folder isn't writable, the program warns you and reverts to the default. Before starting, the program checks that the destination disk has enough space for the file (plus a safety margin): if not, the download is abandoned right away with a clear message instead of failing halfway on a full disk. Each download from a **single-file link** occupies a folder named after the downloaded file with a numeric suffix (`<file_name>_<id>/`); inside it, the `ciclo_1/`, `ciclo_2/`, … subfolders hold the files produced by each cycle. The folder name is assigned on the first successful link resolve; until then a temporary name based on a URL hash is used. Files coming from a **folder link** follow a **tree** layout instead: they all end up under a single folder named after the Mega folder, with the original subfolders preserved (`<Mega folder name>/<subfolder>/<file>`), with no numeric suffix and no `ciclo_N` level. All diagnostic/operational logs are collected in the project's `logs/` folder: the history of completed downloads (deduplicated by Mega handle, used to warn when a link already downloaded is re-entered), the log of abandoned links, per-source proxy metrics, a general technical activity log, a universal structured log (`logs/events.jsonl`), and a raw capture of the entire terminal output of the current session (`logs/terminal-log.txt`, reset on every startup). They are not needed for normal use, but are available for diagnostics.

A **passive diagnostics suite**, always on, complements these logs: native crash tracebacks, multi-thread exception capture, a periodic heartbeat with memory usage, and session start/clean-exit markers. In case of a crash, the command-line tool `tools/report.py` reads `logs/events.jsonl` and `logs/crash.log` and produces a readable HTML report in `logs/reports/`, useful for reconstructing what the program was doing shortly before the problem.

---

## 12. Key parameters and defaults

The values below are factory defaults; the configurable ones are noted accordingly.

| Parameter | Default | Notes |
|---|---|---|
| Chunk size | 32 MB | configurable; smaller chunks tolerate proxy changes better but generate more requests |
| Parallel connections per file | 10 | configurable (Experimental Features); simultaneous HTTP Range requests, one per proxy |
| Concurrent downloads | 1 | configurable, recommended range 1–5 |
| Minimum parallelization threshold | 1 MiB | below this size the file is downloaded serially |
| Attempts per segment | 8 | before considering the chunk failed |
| Minimum throughput | 200 KB/s | measured over a 20 s window, after 15 s grace |
| Per-segment attempt budget | 180 s | configurable (Experimental Features); absolute limit, independent of throughput |
| Maximum duration per file | 60 min | configurable; beyond the limit the file is abandoned |
| Failed attempts before abandoning | 15 | per individual link, does not reset between cycles |
| Pool refresh | every 30 s | refill if alive proxies < 80 (re-arms at 160); forced refresh after 5 min |
| **Adaptive refill threshold** (with speed-based selection) | floor 10, ×3 | `LOW = max(10, active × conn × 3)`, `HIGH = 2 × LOW`. With flag OFF: static (80/160). |
| Target alive proxies | 300 | validation stops early once reached; with free proxies it is not always achieved (typical yield ~150-170) |
| Maximum validation candidates | 12000 | cap to limit startup duration; scans stage 1 first, then stage 2 up to the target |
| Validation workers | 200 (stage 1) / 120 (stage 2) | concurrency of the two validation stages |
| **Pre-filter for metadata sources** (ProxyScrape JSON) | uptime ≥ 50%, latency ≤ 3000 ms | applied by the scraper before validation; discards candidates the source flags as unreliable |
| Rate-limit proxy cooldown | 90 s | excluded from rotation and from the "alive" count on 403/509 from the CDN; returns available when it expires |
| Maximum files per Mega folder | 500 | beyond the limit the program asks for confirmation and states how many files would be left out |
| Folder listing read timeout | 60 s | for the single node-listing call |
| Proxy cache validity | 6 hours | older entries discarded at startup |
| Proxy score | 0 / +5 / −10 / dead below −20 | initial / success / failure / threshold |
| **Speed-based selection** (Stage 3) | off | enabled from Experimental Features; adds speed test and throughput-based selection |
| Preference threshold (speed-based selection) | 500 KB/s | configurable from Experimental Features; proxies above threshold served first |
| Admission threshold (speed-based selection) | 100 KB/s | fixed; proxies below discarded at Stage 3 |
| Connections per file (speed-based selection) | 5 | reduced from 10 when speed-based selection is active |
| Maximum candidates (speed-based selection) | 5 000 | reduced from 12 000 when speed-based selection is active |
| Speed test URL (Stage 3) | http://speedtest.tele2.net/1MB.zip | external server, not Mega |
| Bytes downloaded per speed test | 1 MB | measures real proxy throughput |
| Speed test timeout | 15 s | connect+read per proxy during Stage 3 |
| Stage 3 workers | 30 | speed test concurrency |

---

## 13. Expected behaviors

Some behaviors may look like anomalies but are part of normal operation:

- **A wait at startup before the download begins:** this is proxy collection and validation. From the second session on it's faster thanks to the cache.
- **Many failed attempts scrolling by:** this is the cost of free proxies; what matters is the final result, not the individual errors.
- **Variable and often modest speed:** depends on proxy quality, typically a few tens to a few hundred KB/s. The bottleneck is external to the program.
- **Brief pauses during the download:** this is pool resupply in action.
- **Files occasionally abandoned:** this happens with links no longer valid or files removed from Mega; the program flags it and moves on to the others.

---

## 14. Known limitations

- Free proxies have a high mortality rate (~70%): validation physiologically discards most of them.
- Speed is determined by the proxies, not the program.
- Mega can rate-limit the same file even from different IPs (403/509 from the CDN): this is the behavior the tool was originally built to measure. The affected proxy is not discarded but put to rest for 90 seconds, then returns to rotation.
- Mega also enforces a **per-file concurrent-IP limit** (response `429 "Too Many Concurrent IP Addresses"`): too many different proxies downloading the same file at the same moment get rejected. The program handles it by **retrying the same proxy** (same IP) after a short wait, instead of switching to a new one — changing IP would make the limit worse. Practical consequence: beyond a certain point, adding connections or proxies to the same file does not increase bandwidth. The peak speed on a single file is therefore bounded by both proxy quality and this Mega ceiling.
- Two **different Mega folders that share the same name** downloaded in **different sessions** end up in the same folder on disk (within the same session they are separated automatically into "Name" and "Name (2)"). Files are never swapped — before considering a file already downloaded the program also checks its size — but the contents of the two folders get mixed. If that happens, it is best to pick a different download folder for the second one.
- Integrity verification via the downloaded file's MAC is not yet implemented: it is a planned feature.
