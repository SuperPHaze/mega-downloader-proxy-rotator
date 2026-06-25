# Operating guide — Mega Downloader Proxy Rotator (MDPR)

**English** · [Italiano](GUIDA_OPERATIVA.md)

This guide describes what the program does, how the download is structured, and what behaviors to expect during use. It is aimed at a technical audience: the goal is to explain how the tool actually works and the rationale behind its choices, without showing off jargon but also without watering down the core of the system.

---

## 1. Purpose and scope

MDPR is a desktop application for Windows (Python + PyQt6) that downloads files from Mega.nz by routing traffic through free public HTTP proxies. The problem it addresses is the throttling Mega applies per IP address: downloading from a single IP quickly hits bandwidth and volume limits. MDPR works around the constraint by spreading the transfer across multiple proxies, each with a different egress IP.

The tool is single-user and single-process, with no backend. It started as a testbed for IP rotation (re-downloading the same file multiple times through different proxies to measure Mega's rate-limit behavior) and is now used as a real-world downloader.

The intended use is downloading files you have the right to access. Public proxies are run by unidentified third parties and offer no confidentiality guarantees: they must not be used for sensitive data.

---

## 2. Three-phase download architecture

Every download session is made up of three phases that operate in parallel once started.

**Pool provisioning.** Before downloading, the program builds a set of working proxies: it collects lists from numerous public sources and runs them through a two-stage validation (section 3). If a cache from a previous session is available, it starts "warm" from that and validates in the background.

**Download.** The file is resolved and split into a queue of fixed-size chunks, downloaded by several parallel HTTP Range connections, each routed through a different proxy, decrypted in streaming fashion, and reassembled (sections 4 and 6).

**Pool maintenance.** For the entire duration of the download, a background component monitors the size and quality of the pool and replenishes it as proxies are exhausted or degrade (section 7).

---

## 3. The proxy pool: collection, validation, scoring

Public proxy lists are large and largely made up of addresses that are no longer operational. Using them unfiltered would produce constant failures. The program therefore applies a **two-stage validation**, sized to quickly discard useless candidates and spend the more expensive test resources only on the promising ones.

**Stage 1 — reachability.** A fast, high-concurrency pre-filter (up to 100 workers, 4 s timeout) against a highly reliable connectivity endpoint (Google's `generate_204`). It only verifies that the proxy can complete an HTTP round trip; it does not judge Mega reachability. It serves to eliminate dead proxies without wasting a test on stage 2's limited capacity.

**Stage 2 — Mega reachability.** Survivors are tested, at moderate concurrency (60 workers) because Mega rate-limits, against the host of Mega's download API — the same one used by real link resolution, not the homepage. The success criterion is any HTTP response received from the host, even an application-level error: it means the round trip reached its destination. A stricter criterion would discard proxies that are perfectly valid for downloading.

Validation stops early once the target number of alive proxies (200) is reached, and in any case never exceeds a candidate cap (3000), so startup doesn't turn into minutes of waiting.

It is expected, and not a flaw, that out of hundreds or thousands of candidates only a few dozen survive: free proxies have a high mortality rate, on the order of 70%.

**Reputation score.** Every proxy in the pool has a score. It starts at 0; a success increases it (+5), a failure penalizes it (−10), and below a threshold of −20 it is considered dead and set aside (but it can rejoin on a later refill if it reappears in the lists). Selection is round-robin by score; ties are broken in favor of the proxy with lower latency.

Penalties distinguish the cause: an explicit rejection from Mega's CDN due to IP saturation (403, 509) does not penalize the score, but rests the proxy for a short period instead (section 13); CDN overload (503) is instead a "hard" penalty; a transient error (timeout, insufficient throughput, network error) is a "soft" penalty. Successes — a completed segment or a successful egress IP check — are recorded and raise the score.

---

## 4. Download: parallel chunks, decryption, atomic write

A direct download from Mega proceeds in a single stream, as fast as the one connection serving it: with a slow free proxy, the download is slow. MDPR works around the limit by splitting the file into **fixed-size chunks** (32 MB by default) and downloading them with **several parallel HTTP Range connections** (10 by default), each routed through a different proxy. Completed chunks are reassembled in the correct order.

Rotation is therefore per-chunk, not per-file: if a proxy drops, at most the chunk in progress is lost, not the entire transfer. Files smaller than the parallelization threshold (1 MiB) are downloaded serially, since splitting would bring no benefit.

The program can also work on **several files at once**: the default is 1, adjustable from the GUI up to 5. Increasing it, however, multiplies the pressure on the proxy pool and can degrade all downloads in progress, which is why the default is sequential.

The payload delivered by Mega is encrypted. The program **decrypts it in streaming fashion** (AES-CTR) as chunks arrive, writing directly to the destination file: RAM usage stays constant even for files of many GB, and what lands on disk is already the final, usable file.

Writing follows the **`.part` + atomic rename** pattern: the transfer always happens on a `<name>.part` file, accompanied by a `.progress.json` sidecar that records completed chunks. Only when the download is complete is the file renamed (an atomic operation) to its final name. The existence of the final name is the only completion marker.

---

## 5. Experimental features

The "Experimental Features" panel exposes two controls, each with a short description and an "i" icon that opens the extended explanation: the number of **connections per file** (how many parts of the same file to download in parallel, each over a different proxy; default 10) and the **per-chunk budget** (maximum time given to a proxy to finish a chunk before switching; default 180 s, section 6), to experiment without recompiling the defaults. Speed-based proxy selection remains internal (for future reuse) and is not configurable from the GUI.

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

Free proxies wear out: one that was valid a few minutes ago may no longer be. If the program only used the set collected at startup, it would eventually run dry. A **background resupplier** checks at regular intervals (every 30 seconds) how many proxies are alive and, if it drops below the threshold (100), starts a scrape and validation without interrupting downloads in progress. To avoid bursts of resupplies when the pool oscillates right around the threshold, the resupplier "disarms" itself after each run and only re-arms once alive proxies climb back above a higher threshold (180). To catch silent degradation (proxies progressively slowing down without fully dying), it also forces a resupply if the last one happened more than 5 minutes ago.

If the pool empties at a critical moment, it's the download itself that requests an immediate resupply and waits as long as needed: at those times you may see a pause, during which the program is rebuilding the pool before continuing. All of this is automatic and requires no intervention.

---

## 8. Memory between sessions (warm start)

Building the pool for the first time takes a while (roughly half a minute to a couple of minutes). To avoid repeating that on every launch, the program persists the best proxies to disk and reloads them on the next launch, quickly re-validating them: proxies still alive are immediately available (a "warm" start), while a full search still starts in the background. Cache entries past their validity window (6 hours) are discarded on load. From the second session onward, startup is therefore noticeably faster.

---

## 9. Session controls and resume

During a session, the available controls are pause/resume and cancel, both globally and per individual file from the table. Pausing does not lose the proxies: on resume, work continues from where it was suspended. Canceling a single file can optionally also remove its already-downloaded data from disk.

Resume also covers involuntary interruptions (program closed, blackout, error). Thanks to the `.part` + sidecar scheme, on resume only the missing chunks are re-downloaded; a cycle is considered complete only when the final renamed file exists, so an interrupted file is never mistaken for complete.

---

## 10. Output, history, and logs

Downloaded files are saved in dedicated subfolders inside the project's `downloads` folder. All diagnostic/operational logs are collected in the project's `logs/` folder: the history of completed downloads (deduplicated by Mega handle, used to warn when a link already downloaded is re-entered), the log of abandoned links, per-source proxy metrics, a general technical activity log, and a universal structured log (`logs/events.jsonl`). They are not needed for normal use, but are available for diagnostics.

A **passive diagnostics suite**, always on, complements these logs: native crash tracebacks, multi-thread exception capture, a periodic heartbeat with memory usage, and session start/clean-exit markers. In case of a crash, the command-line tool `tools/report.py` reads `logs/events.jsonl` and `logs/crash.log` and produces a readable HTML report in `logs/reports/`, useful for reconstructing what the program was doing shortly before the problem.

---

## 11. Key parameters and defaults

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
| Pool refresh | every 30 s | refill if alive proxies < 100 (re-arms at 180); forced refresh after 5 min |
| Proxy cache validity | 6 hours | older entries discarded at startup |
| Proxy score | 0 / +5 / −10 / dead below −20 | initial / success / failure / threshold |

---

## 12. Expected behaviors

Some behaviors may look like anomalies but are part of normal operation:

- **A wait at startup before the download begins:** this is proxy collection and validation. From the second session on it's faster thanks to the cache.
- **Many failed attempts scrolling by:** this is the cost of free proxies; what matters is the final result, not the individual errors.
- **Variable and often modest speed:** depends on proxy quality, typically a few tens to a few hundred KB/s. The bottleneck is external to the program.
- **Brief pauses during the download:** this is pool resupply in action.
- **Files occasionally abandoned:** this happens with links no longer valid or files removed from Mega; the program flags it and moves on to the others.

---

## 13. Known limitations

- Free proxies have a high mortality rate (~70%): validation physiologically discards most of them.
- Speed is determined by the proxies, not the program.
- Mega can rate-limit the same file even from different IPs (403/509 from the CDN): this is the behavior the tool was originally built to measure. The affected proxy is not discarded but put to rest for 90 seconds, then returns to rotation.
- Integrity verification via the downloaded file's MAC is not yet implemented: it is a planned feature.
