<div align="center">

# Mega Downloader Proxy Rotator · MDPR

**English** · [Italiano](README.it.md)

**Download more than 5 GB/day from Mega.nz** — by splitting each download into many fragments, each routed through a **different free proxy** in parallel, there are no limits.

<!-- DEMO: upload the video (demo.mp4) here by dragging it into the GitHub web editor after publishing -->








https://github.com/user-attachments/assets/1ebcd19c-38f5-40b5-86ff-5a1c87154a2d










![version](https://img.shields.io/badge/version-2.3.0-blue)
![python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue)
![platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![gui](https://img.shields.io/badge/GUI-PyQt6-green)
![license](https://img.shields.io/badge/license-MIT-green)

[Website](https://superphaze.github.io/mega-downloader-proxy-rotator) · [Download](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) · [How it works](#%EF%B8%8F-how-it-works) · [Report a bug](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/issues)

</div>

---

## 🚀 Overview

A **desktop app for Windows and macOS** (Python + PyQt6) that downloads files **and entire folders** from Mega.nz by routing traffic through public, free HTTP proxies. The file is split into a **queue of fixed-size fragments**, downloaded in parallel — each through a different proxy — decrypted on the fly and reassembled. It started as a technical IP-rotation experiment and is now a real-world downloader: single-user, single-process. The interface is **bilingual, Italian and English**.

## ✨ What makes it different

- **Built for Mega** — public-link resolution and AES decryption are built in (no dependency on `mega.py`).
- **Validated, scored pool of free proxies** — scraped from dozens of sources (around 70), two-stage validation (optionally three with a speed test), per-proxy reputation, on-disk cache, background regeneration.
- **A different proxy for every fragment** — rotation is per-fragment, not per-file: if a proxy dies, you lose at most one fragment.
- **Granular resume** — completed fragments survive crashes, proxy changes, and changes to the number of connections.

## 🧩 Features

- Queue of **fixed-size fragments** (32 MB by default) pulled by 10 parallel HTTP Range connections, with support for multiple files at once (configurable; see the guide for parameters).
- **Streaming decryption** to disk (constant RAM even for multi-GB files), `.part` pattern + atomic rename.
- **Resume** of interrupted downloads and **restart** of failed/abandoned/cancelled ones (only the missing fragments are re-fetched).
- **Configurable per-file time limit**; past the threshold the file is abandoned.
- **Recover downloads** is available even when the queue is empty. Select an interrupted file in the download folder to see the saved bytes and resume the missing chunks. If there is no chunk record, you can confirm **Restart from zero**. With the queue open, the same list is available under **Partial files**.
- **History** lists completed downloads from this and previous sessions. Search by file name, check the completion date and size, or open the folder where a file was saved.
- **Add links to a running session**: new links join the queue without stopping the downloads or redoing the proxy collection; you choose whether to put them at the end or right after the current file, and links already in the session are flagged before they are added.
- **Mega folder links** (`/folder/`): the folder is expanded into its individual files, saved as a tree under a single folder carrying the original name (see the guide).
- **Per-fragment watchdog**: drops proxies that are too slow or fail to finish in time.
- **"Experimental Features" panel** with connections per file, fragment budget, and speed-based selection with configurable threshold (real speed test + throughput-based proxy selection).
- **Passive crash diagnostics**, always on (memory heartbeat, multi-thread tracebacks), universal structured logging (`logs/events.jsonl`), and an HTML report generator (`tools/report.py`).
- **Download queue** with a link preview, status filters, current speed and time remaining. Open **Session details** below the queue to see statistics and connection information.
- **Bilingual Italian/English interface**: on first launch it follows the system language, then you choose it in Settings (Automatic / Italiano / English) and the change is immediate, with no restart. The whole interface is translated, error messages included; messages in the log files stay in Italian because they are there for diagnostics.
- **Minimize to the Dock** on macOS. On Windows you can choose the taskbar or the notification area. The icon menu can reopen the window.
- **Disk data maintenance**: from Settings you can clear the download history, the saved session, the download folder, the logs and the proxy cache. Each entry shows how much it actually takes up, nothing is pre-selected, the list of what will go is shown before anything is deleted, and while a download is running the dangerous entries are disabled.
- **CLI mode** for headless machines.

## ⚡ Quick install (Windows 10/11)

**To use it** — download the ready-made package:
1. Go to the [latest Release](https://github.com/SuperPHaze/mega-downloader-proxy-rotator/releases/latest) and download the `.zip`.
2. Extract it, then double-click **`install.bat`** (creates the environment and installs everything: the app, the tests and the tools in `tools/`).
3. Open the **Mega Downloader Proxy Rotator** shortcut created by the installer. Click **Debug** in the bottom bar to show or hide the log below the queue.

**From source** — requires Python 3.11–3.14 on your PATH:
```bash
git clone https://github.com/SuperPHaze/mega-downloader-proxy-rotator
cd mega-downloader-proxy-rotator
install.bat
```

A single command sets everything up: runtime dependencies (`requirements.txt`), test/tool dependencies (`requirements-dev.txt`, needed by `pytest` and `tools/demo/demo_runner.py`) and the check/installation of **ffmpeg** (needed only by the demo runner in video mode; the app itself does not use it). To install just the base app, with no tests/tools and no ffmpeg: `powershell -ExecutionPolicy Bypass -File install.ps1 -Minimal`.

> The `venv` is not portable across machines: if you move the project, don't copy `venv/` — re-run `install.bat`.

> **Script language** — `install.ps1` and `package.ps1` print their messages in **English by default**. For Italian, run them with `-Lang IT`, e.g. `powershell -ExecutionPolicy Bypass -File install.ps1 -Lang IT`.

## Run on macOS

With Python 3.11–3.14 installed, open **Mega Downloader Proxy Rotator.app** in Finder. Keep the app in the extracted folder alongside `src`. The first launch sets up the Python environment, and later launches reuse it. **Debug** shows the log in the same window. The red close button quits the app.

A manual test of version 2.3.0 on Apple Silicon with Python 3.14.10 confirmed that a download started.

## 🔧 Quick usage

1. Choose **Add links** to paste one address per line, or **Import from file** to open a `.txt` list. On Mac you can use **⌘L** and confirm with **⌘Return**.
2. Review the list and destination. Use **Settings** (**⌘,** on Mac) to change the folder. Press **Start** when the queue is ready.
3. The queue shows progress, speed and time remaining. Expand a file to open its details. Select **Session details** below the list for statistics.

Headless CLI:
```powershell
.\venv\Scripts\python.exe -m tools.cli_download "https://mega.nz/file/..."
```

> We recommend keeping the default values (1 download, 32 MB chunk); for tuning see the [guide](Docs/OPERATING_GUIDE.md).

## ⚙️ How it works

1. **Source the proxies** — scrape public sources → two-pass screening (is it alive? does it reach Mega?) → scored pool.
2. **Download** — resolve the link, split into fragments, N parallel connections over different proxies, streaming decryption, reassembly and atomic rename.
3. **Keep the pool healthy** — a background refresher replaces exhausted proxies without stopping downloads.

## 📚 Documentation

- [`CLAUDE.md`](CLAUDE.md) — module map and full data flow.
- [`Docs/OPERATING_GUIDE.md`](Docs/OPERATING_GUIDE.md) — technical guide to how the tool works.

## ⚠️ Known limitations

- Free proxies have a high death rate: it's normal for validation to discard most of them.
- Speed depends on the proxies: typically from tens to a few hundred KB/s.
- Mega may rate-limit the same file even from different IPs (403/509 from the CDN): temporarily blocked proxies are put to rest and reused (details in the [guide](Docs/OPERATING_GUIDE.md)).
- File MAC verification is not yet implemented (planned).

## 🛡️ Disclaimer

This tool is meant **solely for downloading files you own or have the right to download**. Working around a service's technical limits may touch its terms of use, and public proxies are run by unknown third parties: use it responsibly and **never for sensitive data**. The author provides a neutral technical tool and assumes no responsibility for misuse.

## 📄 License

Released under the **MIT** license — free to use, modify, and redistribute, including commercially, with no warranty. See [`LICENSE`](LICENSE).

---

<div align="center">
Created by <b>SuperPHaze</b> · Alese (SuperPietro) Haze
</div>
