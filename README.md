<div align="center">

# Mega Downloader Proxy Rotator · MDPR

**English** · [Italiano](README.it.md)

**Download more than 5 GB/day from Mega.nz** — by splitting each download into many fragments, each routed through a **different free proxy** in parallel, there are no limits.

<!-- DEMO: upload the video (demo.mp4) here by dragging it into the GitHub web editor after publishing -->




https://github.com/user-attachments/assets/b4e0839b-6545-4614-9437-22f5ee564264





![version](https://img.shields.io/badge/version-1.9.0-blue)
![python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![gui](https://img.shields.io/badge/GUI-PyQt6-green)
![license](https://img.shields.io/badge/license-MIT-green)

[Website](https://superphaze.github.io/mega-downloader-proxy-rotator) · [Download](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) · [How it works](#%EF%B8%8F-how-it-works) · [Report a bug](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues)

</div>

---

## 🚀 Overview

A **Windows desktop app** (Python + PyQt6) that downloads files from Mega.nz by routing traffic through public, free HTTP proxies. The file is split into a **queue of fixed-size fragments**, downloaded in parallel — each through a different proxy — decrypted on the fly and reassembled. It started as a technical IP-rotation experiment and is now a real-world downloader: single-user, single-process.

## ✨ What makes it different

- **Built for Mega** — public-link resolution and AES decryption are built in (no dependency on `mega.py`).
- **Validated, scored pool of free proxies** — scraped from dozens of sources, two-stage validation, per-proxy reputation, on-disk cache, background regeneration.
- **A different proxy for every fragment** — rotation is per-fragment, not per-file: if a proxy dies, you lose at most one fragment.
- **Granular resume** — completed fragments survive crashes, proxy changes, and changes to the number of connections.

## 🧩 Features

- Queue of **fixed-size fragments** (32 MB by default) pulled by 10 parallel HTTP Range connections (configurable), with up to 5 files at once.
- **Streaming decryption** to disk (constant RAM even for multi-GB files), `.part` pattern + atomic rename.
- **Resume** of interrupted downloads and **restart** of failed/abandoned/cancelled ones (only the missing fragments are re-fetched).
- **Configurable per-file time limit**; past the threshold the file is abandoned.
- **Download history** with a warning for links already downloaded (deduplicated by Mega handle).
- **Per-fragment watchdog**: drops proxies that are too slow or fail to finish in time.
- **"Experimental Features" panel** present but empty in this version (no levers configurable from the interface).
- **Passive crash diagnostics**, always on (memory heartbeat, multi-thread tracebacks), universal structured logging (`logs/events.jsonl`), and an HTML report generator (`tools/report.py`).
- **Tabbed interface** with a dashboard (instantaneous/average/peak/minimum session speed, ETA, time, job counters) and a dedicated proxy section (alive, validation, discarded, refills), button-based job filters, light/dark theme, global and per-job pause/resume/cancel.
- **CLI mode** for headless machines.

## ⚡ Quick install (Windows 10/11)

**To use it** — download the ready-made package:
1. Go to the [latest Release](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) and download the `.zip`.
2. Extract it, then double-click **`install.bat`** (creates the environment and installs everything).
3. Launch with **`avvia.bat`**.

**From source** — requires Python 3.11–3.14 on your PATH:
```bash
git clone https://github.com/SuperPHaze/mega-downloader-proxy-rotator
cd mega-downloader-proxy-rotator
install.bat
```

> The `venv` is not portable across machines: if you move the project, don't copy `venv/` — re-run `install.bat`.

> **Script language** — `install.ps1` and `package.ps1` print their messages in **English by default**. For Italian, run them with `-Lang IT`, e.g. `powershell -ExecutionPolicy Bypass -File install.ps1 -Lang IT`.

## 🔧 Quick usage

1. Paste one or more `https://mega.nz/...` links (or import them from a `.txt` file).
2. Adjust the options in the **Settings** menu and press **Start**.
3. Follow progress, speed, and attempts for each file; pause, restart, or cancel whenever you want.

Headless CLI:
```powershell
.\venv\Scripts\python.exe -m tools.cli_download "https://mega.nz/file/..."
```

## ⚙️ How it works

1. **Source the proxies** — scrape public sources → two-pass screening (is it alive? does it reach Mega?) → scored pool.
2. **Download** — resolve the link, split into fragments, N parallel connections over different proxies, streaming decryption, reassembly and atomic rename.
3. **Keep the pool healthy** — a background refresher replaces exhausted proxies without stopping downloads.

## 📚 Documentation

- [`CLAUDE.md`](CLAUDE.md) — module map and full data flow.
- [`Docs/OPERATING_GUIDE.md`](Docs/OPERATING_GUIDE.md) — technical guide to how the tool works.

## ⚠️ Known limitations

- Free proxies have a high death rate (~70%): it's normal for validation to discard most of them.
- Speed depends on the proxies: typically from tens to a few hundred KB/s.
- Mega may rate-limit the same file even from different IPs (403/509 from the CDN).
- File MAC verification is not yet implemented (planned).

## 🛡️ Disclaimer

This tool is meant **solely for downloading files you own or have the right to download**. Working around a service's technical limits may touch its terms of use, and public proxies are run by unknown third parties: use it responsibly and **never for sensitive data**. The author provides a neutral technical tool and assumes no responsibility for misuse.

## 📄 License

Released under the **MIT** license — free to use, modify, and redistribute, including commercially, with no warranty. See [`LICENSE`](LICENSE).

---

<div align="center">
Created by <b>SuperPHaze</b> · Alese (SuperPietro) Haze
</div>
