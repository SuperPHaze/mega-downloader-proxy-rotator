# Demo runner MDPR — video reali (IT/EN) + galleria di screenshot.
#
# Pilota la GUI VERA con metodi/slot Qt reali (nessun mouse/tastiera simulati),
# registra con ffmpeg (gdigrab), fa scaricare per davvero i due link Mega dati,
# poi produce un taglio "bello" a velocita' variabile (ffmpeg setpts) + stills
# agli eventi. Riusabile tale e quale alle prossime release (bastano i due link
# di default o --folder-link/--file-link).
#
# Architettura: il processo "genitore" (questo script invocato senza --_worker)
# fa da orchestratore puro Python (nessun Qt). Per ogni lingua rilancia SE STESSO
# come sottoprocesso con --_worker: garantisce una "nuova istanza pulita" per
# lingua (QApplication/Translator/orchestrator sono singleton di modulo, non
# vanno riusati fra due giri) e isola un eventuale blocco di una lingua senza
# perdere l'altra.
#
# === Contratto con MDPR (aggiornare se cambia) ===
#
# Questo script dipende da superficie PRIVATA della GUI (metodi con underscore,
# attributi interni), non solo da API pubbliche: e' una scelta deliberata (serve
# a pilotare cose — menu impostazioni, filtro job — che non hanno un ingresso
# pubblico piu' pulito), ma vuol dire che un refactor interno la puo' rompere
# senza toccare nessun contratto "ufficiale". Questa sezione e' il modo per
# accorgersene: se tocchi uno di questi punti in src/gui o src/core, aggiorna
# QUI e nel codice sotto, poi rilancia `--dry-run` (lo verifica in automatico
# per import/slot/i18n; il resto — vedi "Verificato SOLO da un giro reale" — va
# controllato a mano o con un giro vero).
#
# Moduli/classi importati da src/ (rotti = ImportError, il --dry-run lo becca):
# - src.core.diagnostics                  (funzione: log_session_start)
# - src.core.config.APP_VERSION           (costante)
# - src.core.icon_loader.build_app_icon   (funzione)
# - src.core.logging_setup                (funzioni: setup_logging, install_qt_message_handler)
# - src.gui.i18n.TR                       (singleton; API: initialize(), set_preference(lang))
# - src.gui.main_window.MainWindow        (classe)
# - src.gui.jobs_model                    (costanti: STATUS_COMPLETED/ABANDONED/RUNNING/
#                                           CANCELLED/FAILED; classe Job, vedi sotto)
# - src.gui.jobs_panel.FILTER_COMPLETED   (costante)
# - src.gui.paste_links_dialog.PasteLinksDialog       (classe)
# - src.gui.about_dialog.AboutDialog                  (classe)
# - src.gui.experimental_dialog.ExperimentalFeaturesDialog  (classe)
#
# Slot/metodi/attributi chiamati o letti su MainWindow e sotto-widget (MOLTI
# sono privati/con underscore: e' voluto, vedi sopra). Verificati dal --dry-run
# con hasattr() a livello di CLASSE (mai instanziando MainWindow: costruirla fa
# rete e mostra una finestra vera):
# - MainWindow._on_start()                        — avvia il download (Fase 1)
# - MainWindow._open_detail(file_id)               — apre il dialogo di dettaglio job
# - MainWindow._open_dialogs                       — dict {file_id: JobDetailDialog}, SOLO
#                                                     su istanza (creato in __init__): il
#                                                     dry-run verifica invece che
#                                                     "self._open_dialogs" compaia nel
#                                                     sorgente di MainWindow.__init__
#                                                     (non instanzia MainWindow)
# - ControlsBar.set_download_dir(str)              — reindirizza i download di test
# - ControlsBar._show_settings_menu()              — apre il popup Impostazioni
# - ControlsBar._settings_menu                     — QMenu persistente, SOLO su istanza:
#                                                     il dry-run costruisce una ControlsBar()
#                                                     autonoma (headless, sicura: nessuna
#                                                     rete nel suo __init__) per verificarlo
# - LinkPanel.open_paste_dialog()                  — apre il dialogo "Incolla link Mega"
# - JobsPanel._on_filter_button_clicked(category)  — applica un filtro (usato per "Completati")
# - JobsPanel.model                                — attributo, istanza di JobsModel (SOLO
#                                                     verificabile con un giro vero: JobsPanel
#                                                     non e' nel Contratto delle istanze headless)
# - JobsModel.jobs_iter()                          — polling dello stato job (NESSUN segnale
#                                                     Qt e' usato per lo stato: vedi sotto)
# - Job (dataclass): campi .file_id/.status/.progress/.speed/.file_name/.url — verificati
#   con dataclasses.fields(Job), non serve istanza
# - PasteLinksDialog.edit (QTextEdit) / .add_btn (QPushButton)  — riempiti dal watchdog
# - AboutDialog(parent) / ExperimentalFeaturesDialog(parent) — costruttori, poi .exec() standard Qt
#
# Segnali osservati via connect(): NESSUNO. Il runner NON si collega a
# JobsModel.job_updated / aggregates_changed / TR.language_changed / a nessun
# segnale dell'orchestrator: lo stato dei job si legge per POLLING ogni 1s
# (JobsModel.jobs_iter() + i campi di Job sopra). Se lo stato dei job cambia
# forma (nuovo campo obbligatorio, rinomina di uno di quelli sopra), il
# polling si rompe silenziosamente (nessuna eccezione, semplicemente il
# runner smette di vedere le transizioni) — e' il rischio piu' insidioso di
# questo contratto, perche' il --dry-run NON lo becca (i campi ci sono, i
# valori possono comunque essere sbagliati): vedi "Verificato SOLO da un giro
# reale" sotto.
#
# Chiavi i18n usate dal watchdog dialog: NESSUNA. Il watchdog distingue i
# dialog per CLASSE Python (isinstance/type(w).__name__: "PasteLinksDialog",
# "AboutDialog", "ExperimentalFeaturesDialog", "QProgressDialog", QMessageBox)
# e per QMessageBox.ButtonRole (il bottone "Scarica comunque" dello storico
# "gia' scaricato" si riconosce da ButtonRole.DestructiveRole, non dal testo
# tradotto) — quindi e' insensibile alla lingua per costruzione. Se
# link_panel.confirm_already_downloaded() smettesse di assegnare
# DestructiveRole al bottone "scarica comunque", il watchdog lo tratterebbe
# come un dialog IGNOTO (chiuso dopo 4s col bottone di default — probabilmente
# "Salta", cioe' l'opposto di quel che serve alla demo): il --dry-run non lo
# verifica (e' un comportamento, non un'API), va controllato a mano se si
# tocca link_panel.py.
#
# File/formati letti o scritti (OPACHI: il runner fa backup/restore a
# livello di BYTE, non parsa mai le chiavi JSON):
# - preferences.json (REPO_ROOT) — l'unica scrittura la fa TR.set_preference(lang)
#   (chiave "language"); il runner fa solo backup su sidecar prima e restore dopo
# - session_state.json (REPO_ROOT) — cancellato prima di aprire MainWindow (evita
#   il prompt "Riprendi sessione?"); backup/restore identico a preferences.json
# - *.demo_orig_backup — sidecar di backup creati dal runner stesso (non di MDPR)
#
# Cartelle usate:
# - <output-dir>/downloads/  — destinazione download di test (svuotata a inizio
#   E fine di OGNI pass, mai la downloads/ reale del progetto)
# - <output-dir>/videos/, <output-dir>/<lang>/, <output-dir>/<lang>/uniform/,
#   <output-dir>/_tmp_segments_<lang>/ — output del runner, non di MDPR
#
# Verificato SOLO da un giro reale (il --dry-run non ci arriva):
# - che i job passino DAVVERO per RUNNING/COMPLETED/ABANDONED con questi nomi
#   esatti (STATUS_* import OK non garantisce che jobs_iter() li usi ancora
#   cosi' — e' un comportamento, non una firma);
# - che ControlsBar._settings_menu si apra/chiuda visivamente come atteso;
# - che confirm_already_downloaded() assegni ancora DestructiveRole al
#   bottone giusto (vedi sopra);
# - il testo del titolo finestra (t("main_window.title", ...)) resta stabile
#   durante una sessione (nessun contatore dinamico): serve a gdigrab per
#   agganciare la finestra una volta sola all'apertura.
#
# Se cambi UNO qualunque di questi punti nel codice/GUI di MDPR, aggiorna
# questa sezione + il codice del runner, poi rilancia `--dry-run`. Se il
# cambio e' non-triviale, valuta anche un giro reale (~20-90 min) prima di
# considerare "finito" il ciclo di lavoro (vedi .claude/rules/demo-runner.md).
from __future__ import annotations

import argparse
import base64
import dataclasses
import importlib
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Output SEMPRE relativo al repo root, mai alla cwd di chi lancia lo script
# ne' alla posizione dello script stesso (tools/demo/ non e' MyDocs/gallery/).
DEFAULT_OUTPUT_DIR = REPO_ROOT / "MyDocs" / "gallery"

DEFAULT_FOLDER_LINK = "https://mega.nz/folder/GfgljYpJ#R0c1lawLLRpGXbr1oy86tA"
DEFAULT_FILE_LINK = "https://mega.nz/file/LTwSwTqS#vtlB9H3KnaecHgN13Vvs3VjAQNYPRHHdCW0zlrvJHGQ"

WINDOW_W, WINDOW_H = 1440, 900
FFMPEG_FRAMERATE = "12"

# Coppie apri/chiudi che diventano un'unica finestra a 1x nel taglio "bello"
# (l'interazione intera resta a velocita' naturale, non solo un dintorno).
SPAN_PAIRS = [
    ("opening_phase_begin", "opening_phase_end"),
    ("detail_dialog_open", "detail_dialog_close"),
    ("settings_menu_open", "settings_menu_close"),
    ("about_dialog_open", "about_dialog_close"),
    ("experimental_dialog_open", "experimental_dialog_close"),
]
# Padding (secondi prima, secondi dopo) per gli eventi puntuali che meritano
# una sosta piu' lunga del default (2s prima / 4s dopo).
EVENT_PAD = {
    "job_completed_first": (2.0, 10.0),
    "job_abandoned_first": (2.0, 5.0),
    "all_completed": (2.0, 15.0),
    "completed_filter_shown": (2.0, 15.0),
    "safety_cap_triggered": (2.0, 15.0),
}
DEFAULT_PAD = (2.0, 4.0)

log = logging.getLogger("demo_runner")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Registra un giro reale del tool (IT/EN), produce video + galleria.",
    )
    p.add_argument("--lang", choices=["it", "en", "both"], default="both")
    p.add_argument("--folder-link", default=DEFAULT_FOLDER_LINK)
    p.add_argument("--file-link", default=DEFAULT_FILE_LINK)
    p.add_argument("--safety-cap-minutes", type=float, default=90.0)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument(
        "--dry-run", action="store_true",
        help="Valida il legame col codice di MDPR (import/slot/i18n) senza aprire "
             "MainWindow, ffmpeg o toccare download/preferenze. <5s, per CI/pre-commit.",
    )
    p.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# --dry-run: valida il legame col codice di MDPR SENZA eseguire nulla di vero
# (niente MainWindow, niente ffmpeg, niente tocco a preferences.json /
# session_state.json). Specchio meccanico della sezione Contratto in cima al
# file: se aggiungi un punto al Contratto, aggiungi il controllo corrispondente
# qui, altrimenti il Contratto e' solo prosa che nessuno verifica.
# ---------------------------------------------------------------------------

# (modulo, [nomi attesi]) — rispecchia "Moduli/classi importati" nel Contratto.
_DRY_RUN_IMPORTS = [
    ("src.core.diagnostics", ["log_session_start"]),
    ("src.core.config", ["APP_VERSION"]),
    ("src.core.icon_loader", ["build_app_icon"]),
    ("src.core.logging_setup", ["setup_logging", "install_qt_message_handler"]),
    ("src.gui.i18n", ["TR"]),
    ("src.gui.main_window", ["MainWindow"]),
    ("src.gui.jobs_model", [
        "STATUS_COMPLETED", "STATUS_ABANDONED", "STATUS_RUNNING",
        "STATUS_CANCELLED", "STATUS_FAILED", "Job",
    ]),
    ("src.gui.jobs_panel", ["FILTER_COMPLETED"]),
    ("src.gui.paste_links_dialog", ["PasteLinksDialog"]),
    ("src.gui.about_dialog", ["AboutDialog"]),
    ("src.gui.experimental_dialog", ["ExperimentalFeaturesDialog"]),
]
# Moduli aggiuntivi che il runner NON importa a livello di modulo (li
# raggiunge solo via window.controls/window.link_panel a runtime), ma che il
# dry-run deve importare in proprio per poter verificare quei punti del
# Contratto con hasattr() senza mai costruire una MainWindow.
_DRY_RUN_SUPPORT_IMPORTS = [
    ("src.gui.controls", ["ControlsBar"]),
    ("src.gui.link_panel", ["LinkPanel"]),
    ("src.gui.jobs_panel", ["JobsPanel"]),
]
# (classe, attributo) — rispecchia "Slot/metodi/attributi" nel Contratto,
# SOLO quelli verificabili a livello di classe (nessuna istanza richiesta).
_DRY_RUN_CLASS_ATTRS = [
    ("MainWindow", "_on_start"),
    ("MainWindow", "_open_detail"),
    ("ControlsBar", "set_download_dir"),
    ("ControlsBar", "_show_settings_menu"),
    ("LinkPanel", "open_paste_dialog"),
    ("JobsPanel", "_on_filter_button_clicked"),
]
_JOB_REQUIRED_FIELDS = {"file_id", "status", "progress", "speed", "file_name", "url"}
# Chiavi i18n usate dal watchdog dialog: NESSUNA (vedi Contratto — distingue
# per classe/ButtonRole, non per chiave tradotta). Lista vuota apposta: se in
# futuro il watchdog iniziasse a dipendere da una chiave, va aggiunta QUI.
_I18N_KEYS_USED = []


def run_dry_run() -> int:
    t_start = time.monotonic()
    errors: list[str] = []
    counts = {"imports": 0, "slots": 0, "i18n": 0}
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    ns: dict[str, object] = {}
    for mod_name, names in _DRY_RUN_IMPORTS + _DRY_RUN_SUPPORT_IMPORTS:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            errors.append(f"runner rotto: import fallito: {mod_name} ({type(exc).__name__}: {exc})")
            continue
        for name in names:
            if not hasattr(mod, name):
                errors.append(f"runner rotto: {mod_name}.{name} non esiste piu'")
                continue
            ns[name] = getattr(mod, name)
            counts["imports"] += 1

    if errors:
        return _dry_run_report(errors, counts, t_start)

    for cls_name, attr in _DRY_RUN_CLASS_ATTRS:
        cls = ns.get(cls_name)
        if cls is None or not hasattr(cls, attr):
            errors.append(f"runner rotto: {cls_name}.{attr} non esiste piu'")
        else:
            counts["slots"] += 1

    Job_cls = ns.get("Job")
    if Job_cls is not None:
        actual_fields = {f.name for f in dataclasses.fields(Job_cls)}
        missing = _JOB_REQUIRED_FIELDS - actual_fields
        if missing:
            errors.append(f"runner rotto: Job manca i campi {sorted(missing)}")
        else:
            counts["slots"] += len(_JOB_REQUIRED_FIELDS)

    MainWindow = ns.get("MainWindow")
    if MainWindow is not None:
        try:
            init_src = inspect.getsource(MainWindow.__init__)
            if "_open_dialogs" not in init_src:
                errors.append("runner rotto: MainWindow.__init__ non assegna piu' self._open_dialogs")
            else:
                counts["slots"] += 1
        except (OSError, TypeError) as exc:
            errors.append(f"runner rotto: impossibile leggere il sorgente di MainWindow.__init__ ({exc})")

    ControlsBar = ns.get("ControlsBar")
    if ControlsBar is not None:
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([sys.argv[0]])
            cb = ControlsBar()
            if not hasattr(cb, "_settings_menu"):
                errors.append("runner rotto: ControlsBar()._settings_menu non esiste piu'")
            else:
                counts["slots"] += 1
            cb.deleteLater()
            del app
        except Exception as exc:
            errors.append(
                f"runner rotto: impossibile verificare ControlsBar._settings_menu "
                f"({type(exc).__name__}: {exc})",
            )

    try:
        from src.gui import strings_en, strings_it
        for key in _I18N_KEYS_USED:
            if key not in strings_it.STRINGS or key not in strings_en.STRINGS:
                errors.append(f"runner rotto: chiave i18n mancante (IT/EN): {key}")
            else:
                counts["i18n"] += 1
    except Exception as exc:
        errors.append(f"runner rotto: impossibile importare i dizionari i18n ({type(exc).__name__}: {exc})")

    downloads_probe = DEFAULT_OUTPUT_DIR / "downloads"
    pre_existed = downloads_probe.exists()
    try:
        downloads_probe.mkdir(parents=True, exist_ok=True)
        if not downloads_probe.exists():
            errors.append(f"runner rotto: impossibile creare {downloads_probe}")
        elif not pre_existed:
            downloads_probe.rmdir()  # dry-run: nessun effetto collaterale residuo
    except OSError as exc:
        errors.append(f"runner rotto: impossibile creare {downloads_probe} ({exc})")

    return _dry_run_report(errors, counts, t_start)


def _dry_run_report(errors: list[str], counts: dict, t_start: float) -> int:
    elapsed = time.monotonic() - t_start
    if errors:
        print(f"dry-run FALLITO in {elapsed:.2f}s:", flush=True)
        for e in errors:
            print(f"  - {e}", flush=True)
        return 1
    print(
        f"dry-run OK: {counts['imports']} imports, {counts['slots']} slots, "
        f"{counts['i18n']} chiavi i18n, tutto in ordine ({elapsed:.2f}s)",
        flush=True,
    )
    return 0


# ---------------------------------------------------------------------------
# Orchestratore (processo genitore, niente Qt qui dentro)
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    if args.dry_run:
        return run_dry_run()
    if args._worker:
        result = run_worker_pass(args)
        print("RESULT_JSON:" + json.dumps(result), flush=True)
        return 0 if result.get("ok") else 1

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print(
            "ffmpeg/ffprobe non trovati nel PATH. Installa con "
            "'winget install ffmpeg' (o 'choco install ffmpeg -y') e rilancia.",
            flush=True,
        )
        return 2

    # Se un giro precedente e' stato ucciso a forza (kill esterno: niente
    # finally Python), il sidecar di backup e' rimasto residuo col vero
    # originale — ripristina PRIMA di spawnare qualunque worker.
    _self_heal_stale_backups(REPO_ROOT / "preferences.json", REPO_ROOT / "session_state.json")

    out_dir = Path(args.output_dir).resolve()
    (out_dir / "videos").mkdir(parents=True, exist_ok=True)

    langs = ["it", "en"] if args.lang == "both" else [args.lang]
    results: dict[str, dict] = {}
    for lang in langs:
        print(f"[demo_runner] === Avvio pass '{lang}' ===", flush=True)
        results[lang] = spawn_worker(lang, args, out_dir)
        r = results[lang]
        if r.get("ok"):
            print(
                f"[demo_runner] Pass '{lang}' OK: raw={r.get('raw_duration_s'):.0f}s "
                f"bello={r.get('cut_duration_s'):.0f}s stills={len(r.get('stills', []))}",
                flush=True,
            )
        else:
            print(f"[demo_runner] Pass '{lang}' FALLITO: {r.get('error')}", flush=True)

    downloads_dir = out_dir / "downloads"
    if downloads_dir.exists():
        shutil.rmtree(downloads_dir, ignore_errors=True)

    build_index_html(out_dir, results)
    write_readme(out_dir, args)
    write_report(out_dir, results)
    print(f"[demo_runner] Fatto. Apri {out_dir / 'index.html'}", flush=True)
    return 0 if all(r.get("ok") for r in results.values()) else 1


def spawn_worker(lang: str, args, out_dir: Path) -> dict:
    argv = [
        sys.executable, str(SCRIPT_PATH),
        "--_worker", "--lang", lang,
        "--folder-link", args.folder_link,
        "--file-link", args.file_link,
        "--safety-cap-minutes", str(args.safety_cap_minutes),
        "--output-dir", str(out_dir),
    ]
    # Margine oltre il safety-cap per lasciare tempo al post-processing
    # (segmenti ffmpeg + stills) dentro lo stesso sottoprocesso.
    hard_timeout = args.safety_cap_minutes * 60 + 900
    try:
        proc = subprocess.run(
            argv, cwd=str(REPO_ROOT), timeout=hard_timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "lang": lang, "ok": False, "error": "hard_timeout_subprocess",
            "stdout_tail": (exc.stdout or "")[-4000:],
            "stderr_tail": (exc.stderr or "")[-4000:],
        }
    result = _extract_result_json(proc.stdout or "")
    if result is None:
        return {
            "lang": lang, "ok": False, "error": "no_result_json",
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
    result["returncode"] = proc.returncode
    return result


def _extract_result_json(stdout: str):
    for line in reversed(stdout.splitlines()):
        if line.startswith("RESULT_JSON:"):
            try:
                return json.loads(line[len("RESULT_JSON:"):])
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------
# Backup/restore dello stato locale non tracciato che il giro tocca davvero
# (preferenze lingua, sessione da ripristinare): il tool si comporta in modo
# reale, ma la preferenza lingua/tema di Pietro non deve restare alterata da
# un giro dimostrativo.
#
# Il backup vive su DISCO (sidecar), non solo in memoria: un kill esterno del
# processo (Task Manager, chiusura del terminale, OOM) salta i blocchi
# `finally` Python, e un backup solo in RAM andrebbe perso lasciando lo stato
# reale dell'utente alterato senza modo di recuperarlo. Il sidecar si
# autoripristina all'inizio del PROSSIMO giro se ne trova uno residuo.
# ---------------------------------------------------------------------------

_BACKUP_SUFFIX = ".demo_orig_backup"


def _backup_sidecar(path: Path) -> Path:
    return path.with_name(path.name + _BACKUP_SUFFIX)


def _self_heal_stale_backups(*paths: Path) -> None:
    """Da chiamare PRIMA di tutto, a inizio pass: se il giro precedente e'
    stato ucciso a forza, il sidecar contiene l'originale vero e il file
    principale e' ancora quello mutato dal giro morto. Ripristina."""
    for p in paths:
        if _backup_sidecar(p).exists():
            log.warning("Backup residuo per %s: ripristino da un giro precedente interrotto a forza", p)
            _restore_from_backup(p)


def _ensure_original_backup(path: Path) -> None:
    sidecar = _backup_sidecar(path)
    if sidecar.exists():
        return  # gia' presente (non dovrebbe succedere dopo il self-heal, difensivo)
    payload = {
        "existed": path.exists(),
        "content_b64": base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else "",
    }
    sidecar.write_text(json.dumps(payload), encoding="utf-8")


def _restore_from_backup(path: Path) -> None:
    sidecar = _backup_sidecar(path)
    if not sidecar.exists():
        return
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        if payload.get("existed"):
            path.write_bytes(base64.b64decode(payload.get("content_b64", "")))
        elif path.exists():
            path.unlink()
    except (OSError, json.JSONDecodeError, ValueError):
        log.exception("Impossibile ripristinare %s dal backup", path)
    finally:
        try:
            sidecar.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Worker: un giro completo (una lingua), in un processo Python dedicato.
# ---------------------------------------------------------------------------

def run_worker_pass(args) -> dict:
    lang = args.lang
    if lang not in ("it", "en"):
        return {"lang": lang, "ok": False, "error": "lang_non_valido_per_worker"}

    out_dir = Path(args.output_dir).resolve()
    videos_dir = out_dir / "videos"
    timeline_path = out_dir / f"timeline-{lang}.jsonl"
    downloads_dir = out_dir / "downloads"
    prefs_path = REPO_ROOT / "preferences.json"
    session_path = REPO_ROOT / "session_state.json"

    _self_heal_stale_backups(prefs_path, session_path)
    _ensure_original_backup(prefs_path)
    _ensure_original_backup(session_path)
    result: dict = {"lang": lang, "ok": False}

    try:
        if downloads_dir.exists():
            shutil.rmtree(downloads_dir, ignore_errors=True)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        if session_path.exists():
            session_path.unlink()

        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        from src.core import diagnostics
        from src.core.config import APP_VERSION
        from src.core.icon_loader import build_app_icon
        from src.core.logging_setup import install_qt_message_handler, setup_logging
        from src.gui.i18n import TR
        from src.gui.main_window import MainWindow

        setup_logging()
        diagnostics.log_session_start(APP_VERSION)
        install_qt_message_handler()

        def excepthook(exc_type, exc_value, exc_tb):
            log.critical("Eccezione non gestita", exc_info=(exc_type, exc_value, exc_tb))
            sys.__excepthook__(exc_type, exc_value, exc_tb)

        sys.excepthook = excepthook

        app = QApplication([sys.argv[0]])
        icon = build_app_icon()
        app.setWindowIcon(icon)

        TR.initialize()
        TR.set_preference(lang)

        window = MainWindow()
        window.setWindowIcon(icon)
        _fit_geometry(window, app)
        # Reindirizza i download nella cartella di test isolata (senza emettere
        # download_dir_changed: set_download_dir non persiste su preferences.json).
        window.controls.set_download_dir(str(downloads_dir))
        window.show()

        timeline_fh = timeline_path.open("w", encoding="utf-8")
        driver = DemoDriver(window, lang, args, out_dir, timeline_fh)
        QTimer.singleShot(1000, driver.begin)
        app.exec()
        timeline_fh.close()

        result["ok"] = True
        result["stop_reason"] = driver.result.get("stop_reason", "sconosciuto")
        result["notable"] = driver.notable

        raw_path = videos_dir / f"raw-{lang}.mp4"
        result["raw_path"] = str(raw_path)
        if not raw_path.exists() or raw_path.stat().st_size == 0:
            result["ok"] = False
            result["error"] = "video_raw_mancante_o_vuoto"
            return result

        events = _read_events(timeline_path)
        result["events_count"] = len(events)
        result["timeline_path"] = str(timeline_path)

        demo_path = videos_dir / f"demo-{lang}.mp4"
        tmp_dir = out_dir / f"_tmp_segments_{lang}"
        cut_info = build_variable_speed_cut(raw_path, events, demo_path, tmp_dir)
        result.update(cut_info)
        result["demo_path"] = str(demo_path)

        lang_dir = out_dir / lang
        stills = extract_stills(raw_path, events, lang_dir, cut_info["raw_duration_s"])
        result["stills"] = stills
        result["stills_dir"] = str(lang_dir)
        return result
    except Exception as exc:  # noqa: BLE001 — vogliamo comunque il RESULT_JSON
        log.exception("Errore nel pass %s", lang)
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        _restore_from_backup(prefs_path)
        _restore_from_backup(session_path)
        if downloads_dir.exists():
            shutil.rmtree(downloads_dir, ignore_errors=True)


def _fit_geometry(window, app) -> None:
    screen = app.primaryScreen()
    w, h = WINDOW_W, WINDOW_H
    x, y = 20, 20
    if screen is not None:
        avail = screen.availableGeometry()
        w = min(w, avail.width() - 40)
        h = min(h, avail.height() - 40)
        x, y = avail.x() + 20, avail.y() + 20
    window.setGeometry(x, y, w, h)


def _read_events(timeline_path: Path) -> list[dict]:
    events = []
    with timeline_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# DemoDriver — pilota MainWindow via metodi/slot Qt reali, registra la timeline.
# ---------------------------------------------------------------------------

class DemoDriver:
    # Dialog che apriamo noi stessi con exec(): il watchdog li chiude dopo
    # questo hold, ma il log open/close resta a carico di chi li apre (una
    # sola sorgente di verita' per gli eventi, niente timer in corsa).
    _DIALOG_CLOSE_HOLD_S = {
        "AboutDialog": 8.0,
        "ExperimentalFeaturesDialog": 10.0,
    }
    # Dialog che si autogestiscono (progress non bloccante dell'espansione
    # cartelle): il watchdog non deve toccarli.
    _IGNORED_MODAL_TYPES = {"QProgressDialog"}

    def __init__(self, window, lang: str, args, out_dir: Path, timeline_fh) -> None:
        self.window = window
        self.lang = lang
        self.out_dir = out_dir
        self.folder_link = args.folder_link
        self.file_link = args.file_link
        self.safety_cap_s = args.safety_cap_minutes * 60.0
        self.timeline_fh = timeline_fh

        self.t0: float | None = None
        self.ffmpeg_proc = None
        self._finished = False
        # Riferimenti FORTI (non id()): un dialog chiuso puo' essere raccolto
        # dal GC e un nuovo dialog puo' riottenere lo stesso id() Python,
        # facendolo ignorare per errore come "gia' gestito".
        self._handled_modals: list = []
        self._jobs_seen = False
        self._last_status: dict[int, str] = {}
        self._first_completed_logged = False
        self._first_abandoned_logged = False
        self._detail_opened = False
        self._settings_sequence_started = False
        self._speed_stable_ticks = 0
        self._all_done_triggered = False
        self.notable: list[str] = []
        self.result: dict = {}

        self._watchdog_timer = None
        self._ticker_timer = None

    # ---- avvio -------------------------------------------------------------

    def begin(self) -> None:
        from PyQt6.QtCore import QTimer

        self.ffmpeg_proc = self._start_ffmpeg()
        self.t0 = time.monotonic()
        self.log_event("recording_started", title=self.window.windowTitle())
        self.log_event("opening_phase_begin")
        self.log_event("dashboard_empty")

        self._watchdog_timer = QTimer()
        self._watchdog_timer.timeout.connect(self._watchdog_tick)
        self._watchdog_timer.start(300)

        self._ticker_timer = QTimer()
        self._ticker_timer.timeout.connect(self._ticker_tick)
        self._ticker_timer.start(1000)

        QTimer.singleShot(int(self.safety_cap_s * 1000), self._on_safety_cap)
        QTimer.singleShot(5000, self._phase1_paste)

    def _start_ffmpeg(self):
        raw_path = self.out_dir / "videos" / f"raw-{self.lang}.mp4"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        title = self.window.windowTitle()
        cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", FFMPEG_FRAMERATE,
            "-draw_mouse", "0",
            "-i", f"title={title}",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(raw_path),
        ]
        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd=str(self.out_dir),
        )

    # ---- fase 1: apertura ---------------------------------------------------

    def _phase1_paste(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self.window.link_panel.open_paste_dialog()  # il watchdog compila e conferma
        if self._finished:
            return
        self.log_event("paste_links")
        QTimer.singleShot(1200, self._phase1_click_start)

    def _fill_paste_dialog(self, dlg) -> None:
        from PyQt6.QtCore import QTimer

        text = f"{self.folder_link}\n{self.file_link}"
        dlg.edit.setPlainText(text)
        QTimer.singleShot(
            1200, lambda: dlg.add_btn.click() if dlg.add_btn.isEnabled() else self._safe_close(dlg),
        )

    def _phase1_click_start(self) -> None:
        if self._finished:
            return
        self.window._on_start()
        self.log_event("start_clicked")
        self.log_event("opening_phase_end")

    # ---- ticker periodico: stato job + trigger fase 2/3/4 -------------------

    def _ticker_tick(self) -> None:
        if self._finished:
            return
        model = self.window.jobs_panel.model
        jobs = list(model.jobs_iter())

        if jobs and not self._jobs_seen:
            self._jobs_seen = True
            self.log_event("jobs_created", count=len(jobs))

        for j in jobs:
            prev = self._last_status.get(j.file_id)
            if prev == j.status:
                continue
            self._last_status[j.file_id] = j.status
            if prev is None:
                continue  # comparsa iniziale del job, non e' una transizione
            self.log_event(
                "job_status_changed", job=j.file_id,
                name=j.file_name or j.url, status=j.status,
            )
            if j.status == self._STATUS_COMPLETED() and not self._first_completed_logged:
                self._first_completed_logged = True
                self.log_event("job_completed_first", job=j.file_id, name=j.file_name)
            if j.status == self._STATUS_ABANDONED() and not self._first_abandoned_logged:
                self._first_abandoned_logged = True
                self.log_event("job_abandoned_first", job=j.file_id, name=j.file_name)

        if not self._detail_opened:
            candidate = next(
                (j for j in jobs if j.status == self._STATUS_RUNNING() and j.progress > 10), None,
            )
            if candidate is not None:
                self._detail_opened = True
                self._open_detail(candidate.file_id)

        if not self._settings_sequence_started:
            agg_speed = sum(j.speed for j in jobs)
            self._speed_stable_ticks = self._speed_stable_ticks + 1 if agg_speed > 0 else 0
            if self._speed_stable_ticks >= 3:
                self._settings_sequence_started = True
                self.log_event("settings_sequence_start")
                self._open_settings_menu()

        terminal = self._TERMINAL_STATUSES()
        if jobs and all(j.status in terminal for j in jobs) and not self._all_done_triggered:
            self._all_done_triggered = True
            self.log_event("all_completed")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self._phase4_show_completed_filter)

    # Import differiti delle costanti di stato (evita import Qt a livello di
    # modulo per il solo processo "genitore", che non ha bisogno di PyQt6).
    @staticmethod
    def _STATUS_COMPLETED():
        from src.gui.jobs_model import STATUS_COMPLETED
        return STATUS_COMPLETED

    @staticmethod
    def _STATUS_ABANDONED():
        from src.gui.jobs_model import STATUS_ABANDONED
        return STATUS_ABANDONED

    @staticmethod
    def _STATUS_RUNNING():
        from src.gui.jobs_model import STATUS_RUNNING
        return STATUS_RUNNING

    @staticmethod
    def _TERMINAL_STATUSES():
        from src.gui.jobs_model import (
            STATUS_ABANDONED, STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED,
        )
        return {STATUS_COMPLETED, STATUS_ABANDONED, STATUS_CANCELLED, STATUS_FAILED}

    # ---- fase 2: dettaglio job + impostazioni/about/sperimentali ------------

    def _open_detail(self, file_id: int) -> None:
        from PyQt6.QtCore import QTimer

        self.window._open_detail(file_id)
        self.log_event("detail_dialog_open", job=file_id)
        QTimer.singleShot(20000, lambda: self._close_detail(file_id))

    def _close_detail(self, file_id: int) -> None:
        if self._finished:
            return
        dlg = self.window._open_dialogs.get(file_id)
        if dlg is not None:
            dlg.close()
        self.log_event("detail_dialog_close", job=file_id)

    def _open_settings_menu(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        menu = self.window.controls._settings_menu
        QTimer.singleShot(5000, menu.close)
        self.log_event("settings_menu_open")
        self.window.controls._show_settings_menu()  # blocca finche' il menu non chiude
        if self._finished:
            return
        self.log_event("settings_menu_close")
        QTimer.singleShot(1500, self._open_about)

    def _open_about(self) -> None:
        if self._finished:
            return
        from src.gui.about_dialog import AboutDialog

        dlg = AboutDialog(self.window)
        self.log_event("about_dialog_open")
        dlg.exec()  # il watchdog lo chiude dopo _DIALOG_CLOSE_HOLD_S["AboutDialog"]
        if self._finished:
            return
        self.log_event("about_dialog_close")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, self._open_experimental)

    def _open_experimental(self) -> None:
        if self._finished:
            return
        from src.gui.experimental_dialog import ExperimentalFeaturesDialog

        dlg = ExperimentalFeaturesDialog(self.window)
        self.log_event("experimental_dialog_open")
        dlg.exec()  # il watchdog lo chiude dopo _DIALOG_CLOSE_HOLD_S["ExperimentalFeaturesDialog"]
        if self._finished:
            return
        self.log_event("experimental_dialog_close")

    # ---- fase 4: completamento -----------------------------------------------

    def _phase4_show_completed_filter(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        from src.gui.jobs_panel import FILTER_COMPLETED

        try:
            self.window.jobs_panel._on_filter_button_clicked(FILTER_COMPLETED)
        except Exception:
            log.exception("impossibile applicare il filtro Completati")
        self.log_event("completed_filter_shown")
        QTimer.singleShot(15000, lambda: self._finish("natural_completion"))

    # ---- safety cap -----------------------------------------------------------

    def _on_safety_cap(self) -> None:
        if self._finished:
            return
        incomplete = [
            j.file_id for j in self.window.jobs_panel.model.jobs_iter()
            if j.status not in self._TERMINAL_STATUSES()
        ]
        self.log_event("safety_cap_triggered", incomplete=incomplete)
        self._finish("safety_cap")

    # ---- watchdog dialog inattesi ---------------------------------------------

    def _watchdog_tick(self) -> None:
        if self._finished:
            return
        from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

        from src.gui.paste_links_dialog import PasteLinksDialog

        w = QApplication.activeModalWidget()
        if w is None:
            return
        if any(w is h for h in self._handled_modals):
            return
        cls_name = type(w).__name__
        if cls_name in self._IGNORED_MODAL_TYPES:
            return  # si autogestisce (es. il progress dell'espansione cartelle)
        self._handled_modals.append(w)

        from PyQt6.QtCore import QTimer

        if isinstance(w, PasteLinksDialog):
            self._fill_paste_dialog(w)
        elif isinstance(w, QMessageBox):
            self._handle_message_box(w)
        elif cls_name in self._DIALOG_CLOSE_HOLD_S:
            # Aperto deliberatamente da noi (About/Sperimentali): il log
            # open/close resta a carico di chi lo apre, qui solo il timer.
            hold_ms = int(self._DIALOG_CLOSE_HOLD_S[cls_name] * 1000)
            QTimer.singleShot(hold_ms, lambda: self._safe_close(w))
        elif isinstance(w, QDialog):
            title = w.windowTitle()
            self.log_event("unexpected_dialog", title=title)
            self.notable.append(f"Dialogo modale inatteso durante il giro {self.lang}: {title!r}")
            QTimer.singleShot(4000, lambda: self._safe_close(w))

    def _handle_message_box(self, box) -> None:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QMessageBox

        title = box.windowTitle()
        text = box.text()
        self.log_event("message_box", title=title, text=text[:200])
        anyway = None
        for b in box.buttons():
            if box.buttonRole(b) == QMessageBox.ButtonRole.DestructiveRole:
                anyway = b
        default = box.defaultButton()
        buttons = box.buttons()
        target = anyway or default or (buttons[0] if buttons else None)
        if anyway is None:
            self.notable.append(
                f"QMessageBox inatteso durante il giro {self.lang}: {title!r} — {text[:150]!r}",
            )
        delay = 1500 if anyway is not None else 4000
        if target is not None:
            QTimer.singleShot(delay, lambda: self._safe_click(target))

    @staticmethod
    def _safe_click(btn) -> None:
        try:
            btn.click()
        except RuntimeError:
            pass  # widget gia' distrutto (finestra chiusa nel frattempo)

    @staticmethod
    def _safe_close(w) -> None:
        try:
            w.accept()
        except Exception:
            try:
                w.close()
            except Exception:
                pass

    # ---- chiusura -----------------------------------------------------------

    def _finish(self, reason: str) -> None:
        if self._finished:
            return
        self._finished = True

        if not self._detail_opened:
            self.log_event(
                "detail_dialog_open", skipped=True,
                reason="nessun job ha superato il 10% prima dello stop",
            )
        if not self._settings_sequence_started:
            self.log_event(
                "settings_sequence_start", skipped=True,
                reason="velocita' aggregata mai stabilmente sopra zero prima dello stop",
            )
        if not self._all_done_triggered:
            self.log_event("all_completed", skipped=True, reason=f"interrotto ({reason})")

        self.log_event("recording_stop_requested", reason=reason)
        self._stop_ffmpeg()
        try:
            self.window.close()
        except Exception:
            log.exception("errore in window.close()")
        self.result["stop_reason"] = reason

        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        QTimer.singleShot(500, QApplication.instance().quit)

    def _stop_ffmpeg(self) -> None:
        if self.ffmpeg_proc is None:
            return
        try:
            if self.ffmpeg_proc.stdin:
                self.ffmpeg_proc.stdin.write(b"q")
                self.ffmpeg_proc.stdin.flush()
        except Exception:
            pass
        try:
            self.ffmpeg_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()
        self.log_event("recording_stopped")

    # ---- log timeline ---------------------------------------------------------

    def log_event(self, event: str, **fields) -> None:
        t = round(time.monotonic() - self.t0, 2) if self.t0 is not None else 0.0
        rec = {"t": t, "event": event, "lang": self.lang, **fields}
        self.timeline_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.timeline_fh.flush()


# ---------------------------------------------------------------------------
# Post-processing: taglio a velocita' variabile + stills.
# ---------------------------------------------------------------------------

def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_variable_speed_cut(raw_path: Path, events: list[dict], out_path: Path, tmp_dir: Path) -> dict:
    duration = probe_duration(raw_path)

    by_name_times: dict[str, list[float]] = {}
    for e in events:
        if e.get("skipped"):
            continue
        by_name_times.setdefault(e["event"], []).append(e["t"])

    windows: list[tuple[float, float]] = []
    consumed: set[tuple[str, float]] = set()
    for open_name, close_name in SPAN_PAIRS:
        opens = by_name_times.get(open_name, [])
        closes = by_name_times.get(close_name, [])
        for ot, ct in zip(opens, closes):
            windows.append((max(0.0, ot - 1.0), min(duration, ct + 1.0)))
            consumed.add((open_name, ot))
            consumed.add((close_name, ct))

    for e in events:
        if e.get("skipped"):
            continue
        key = (e["event"], e["t"])
        if key in consumed:
            continue
        pre, post = EVENT_PAD.get(e["event"], DEFAULT_PAD)
        windows.append((max(0.0, e["t"] - pre), min(duration, e["t"] + post)))

    windows.sort()
    merged: list[list[float]] = []
    for s, en in windows:
        if merged and s <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], en)
        else:
            merged.append([s, en])

    segments: list[tuple[float, float, float]] = []
    cursor = 0.0
    for s, en in merged:
        if s > cursor:
            gap = s - cursor
            speed = 8.0 if gap > 60.0 else 4.0
            segments.append((cursor, s, speed))
        segments.append((s, en, 1.0))
        cursor = en
    if cursor < duration:
        gap = duration - cursor
        speed = 8.0 if gap > 60.0 else 4.0
        segments.append((cursor, duration, speed))
    segments = [(s, en, sp) for s, en, sp in segments if en - s > 0.05]

    if not segments:
        segments = [(0.0, duration, 1.0)]

    onex_total = sum(en - s for s, en, sp in segments if sp == 1.0)
    other_total_at_base = sum(en - s for s, en, sp in segments if sp != 1.0)
    projected = onex_total + sum((en - s) / sp for s, en, sp in segments if sp != 1.0)
    target_lo, target_hi = 300.0, 480.0
    if other_total_at_base > 0 and not (target_lo <= projected <= target_hi):
        target = target_hi if projected > target_hi else target_lo
        needed_other_duration = max(1.0, target - onex_total)
        mult = other_total_at_base / needed_other_duration
        mult = max(2.0, min(30.0, mult))
        segments = [(s, en, sp if sp == 1.0 else mult) for s, en, sp in segments]

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    seg_files = []
    for i, (s, en, sp) in enumerate(segments):
        seg_path = tmp_dir / f"seg_{i:04d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{s:.3f}", "-to", f"{en:.3f}", "-i", str(raw_path),
            "-an", "-filter:v", f"setpts=PTS/{sp:.4f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(seg_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        seg_files.append(seg_path)

    list_path = tmp_dir / "concat_list.txt"
    with list_path.open("w", encoding="utf-8") as fh:
        for sp in seg_files:
            fh.write(f"file '{sp.name}'\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)],
        check=True, capture_output=True, cwd=str(tmp_dir),
    )
    shutil.rmtree(tmp_dir, ignore_errors=True)

    cut_duration = probe_duration(out_path)
    return {"segments": len(segments), "raw_duration_s": duration, "cut_duration_s": cut_duration}


def extract_stills(raw_path: Path, events: list[dict], lang_dir: Path, duration: float) -> list[str]:
    lang_dir.mkdir(parents=True, exist_ok=True)
    uniform_dir = lang_dir / "uniform"
    uniform_dir.mkdir(parents=True, exist_ok=True)

    produced = []
    idx = 0
    seen_slugs: set[str] = set()
    for e in events:
        if e.get("skipped"):
            continue
        idx += 1
        base_slug = re.sub(r"[^a-z0-9]+", "-", e["event"].lower()).strip("-") or "event"
        slug, n = base_slug, 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        seen_slugs.add(slug)
        t = max(0.0, min(duration - 0.1, e["t"] + 3.0))
        out_path = lang_dir / f"{idx:02d}-{slug}.png"
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(raw_path), "-vframes", "1", "-q:v", "2", str(out_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        produced.append(out_path.name)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_path), "-vf", "fps=1/30", str(uniform_dir / "frame-%03d.png")],
        check=True, capture_output=True,
    )
    return produced


# ---------------------------------------------------------------------------
# Output: index.html, README.md, report testuale.
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def build_index_html(out_dir: Path, results: dict[str, dict]) -> None:
    langs = [l for l in ("it", "en") if results.get(l, {}).get("ok")]

    video_cols = "\n".join(
        f'''<div class="col">
      <h2>{l.upper()}</h2>
      <video controls preload="metadata" src="videos/demo-{l}.mp4"></video>
      <p class="meta">Durata: {results[l]["cut_duration_s"]:.0f}s (raw: {results[l]["raw_duration_s"]:.0f}s) — {results[l]["segments"]} segmenti</p>
    </div>'''
        for l in langs
    ) or "<p>Nessun video disponibile: entrambi i pass sono falliti.</p>"

    still_names: dict[str, str] = {}
    for l in langs:
        for name in results[l].get("stills", []):
            slug = name.split("-", 1)[1] if "-" in name else name
            still_names.setdefault(slug, name)

    still_rows = []
    for slug in sorted(still_names):
        cells = []
        for l in langs:
            match = next((n for n in results[l].get("stills", []) if n.endswith(slug)), None)
            if match:
                cells.append(f'<img src="{l}/{match}" alt="{_esc(slug)} ({l})" loading="lazy">')
            else:
                cells.append('<div class="missing">—</div>')
        still_rows.append(
            f'<div class="still-row"><div class="still-label">{_esc(slug)}</div>'
            + "".join(f'<div class="still-cell">{c}</div>' for c in cells)
            + "</div>",
        )

    raw_links = "\n".join(
        f'<li><a href="videos/raw-{l}.mp4">raw-{l}.mp4</a> ({results[l]["raw_duration_s"]:.0f}s)</li>'
        for l in langs
    )

    html = f"""<title>MDPR — Demo bilingue</title>
<style>
  :root {{ --bg:#0f1117; --panel:#171a23; --text:#e8e8ec; --muted:#9aa0ac; --accent:#5b8cff; --border:#2a2e3a; }}
  @media (prefers-color-scheme: light) {{
    :root:not([data-theme="dark"]) {{ --bg:#f5f6f8; --panel:#ffffff; --text:#1b1e24; --muted:#5b6270; --accent:#3358d8; --border:#e2e4ea; }}
  }}
  :root[data-theme="light"] {{ --bg:#f5f6f8; --panel:#ffffff; --text:#1b1e24; --muted:#5b6270; --accent:#3358d8; --border:#e2e4ea; }}
  * {{ box-sizing: border-box; }}
  body {{ background:var(--bg); color:var(--text); font-family: -apple-system, Segoe UI, sans-serif; margin:0; padding:24px 32px 64px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .sub {{ color:var(--muted); margin-top:0; margin-bottom: 24px; }}
  .videos {{ display:flex; gap:20px; flex-wrap:wrap; margin-bottom: 32px; }}
  .col {{ flex:1 1 480px; background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px; }}
  .col h2 {{ margin-top:0; font-size:1rem; }}
  video {{ width:100%; border-radius:6px; background:#000; }}
  .meta {{ color:var(--muted); font-size:0.85rem; }}
  h2.section {{ font-size:1.1rem; border-bottom:1px solid var(--border); padding-bottom:6px; margin-top:36px; }}
  .still-row {{ display:grid; grid-template-columns: 200px repeat({max(len(langs),1)}, 1fr); gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--border); }}
  .still-label {{ color:var(--muted); font-size:0.85rem; }}
  .still-cell img {{ width:100%; border-radius:6px; border:1px solid var(--border); display:block; }}
  .missing {{ color:var(--muted); font-size:0.8rem; }}
  ul {{ color:var(--text); }}
  a {{ color:var(--accent); }}
</style>
<h1>MDPR — Demo bilingue (download reali)</h1>
<p class="sub">Generato da <code>demo_runner.py</code>. Video "belli" a velocita' variabile (interazioni a 1x, attese accelerate).</p>

<div class="videos">
{video_cols}
</div>

<h2 class="section">Screenshot agli eventi</h2>
<div class="stills">
{"".join(still_rows) if still_rows else "<p>Nessuno still disponibile.</p>"}
</div>

<h2 class="section">Grezzi (archivio)</h2>
<ul>
{raw_links}
</ul>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def write_readme(out_dir: Path, args) -> None:
    content = f"""# MDPR — Demo runner (video + galleria bilingue)

Materiale generato da `demo_runner.py`: due video reali del tool (IT/EN) con download
COMPLETI veri, un taglio "bello" a velocita' variabile e una galleria di screenshot.
Niente stub, niente fake: e' il tool vero che scarica dai due link Mega dati.

## Cosa contiene

- `videos/raw-it.mp4`, `videos/raw-en.mp4` — registrazioni grezze (durata reale).
- `videos/demo-it.mp4`, `videos/demo-en.mp4` — tagli "belli" a velocita' variabile (~5-8 min).
- `timeline-it.jsonl`, `timeline-en.jsonl` — log eventi (usato dal post-processing).
- `it/`, `en/` — screenshot agli eventi + `uniform/` (uno ogni 30s, copertura).
- `index.html` — galleria statica auto-contenuta (apri a doppio clic).

Lo script che genera tutto questo, `demo_runner.py`, vive altrove — e' un
file TRACCIATO del progetto: `tools/demo/demo_runner.py`. Vedi anche
`.claude/rules/demo-runner.md` per la regola che lo tiene allineato al
codice della GUI.

## Come rilanciarlo (prossima release)

```
python tools/demo/demo_runner.py --lang both
```

Di default usa i due link qui sotto. Per cambiarli:

```
python tools/demo/demo_runner.py --lang both \\
  --folder-link <url cartella Mega> \\
  --file-link <url file singolo Mega> \\
  --safety-cap-minutes 90
```

Prima di un giro lungo, `python tools/demo/demo_runner.py --dry-run` verifica
in meno di 5 secondi che il runner sia ancora allineato al codice del tool
(import, slot, chiavi i18n) senza scaricare o registrare nulla.

Un giro completo (IT+EN) dura 20-90+ minuti reali (dipende dai proxy gratuiti disponibili
al momento): il runner scarica per davvero, non accelera nulla durante la registrazione —
la velocita' variabile e' SOLO nel taglio finale, in post-processing.

## Se qualcosa va storto

- **ffmpeg non installato**: `winget install ffmpeg` (o `choco install ffmpeg -y`), poi rilancia.
- **La finestra non viene agganciata da ffmpeg (gdigrab)**: gdigrab risolve il titolo UNA
  volta all'apertura dello stream e poi cattura sempre la stessa finestra (handle), anche se
  il titolo cambia dopo — nella pratica qui il titolo di MDPR resta comunque stabile durante
  una sessione (non include contatori dinamici). Se il tool viene rinominato/il titolo cambia
  radicalmente, aggiorna la logica di aggancio in `DemoDriver._start_ffmpeg`.
- **Una lingua viene troncata dal safety cap** (`--safety-cap-minutes`, default 90): non e' un
  errore, e' un dato reale (pool proxy debole al momento del giro). Il runner chiude comunque
  i job in corso e ferma la registrazione; il report finale lo segnala.
- **Il pool proxy e' scarso**: il video mostrera' molte attese/retry — fa parte del punto
  (mostrare come il tool reagisce). Se in 10 minuti reali non parte NESSUN download, e' il
  caso di controllare i proxy prima di rilanciare.
- **Il PC va in sospensione durante il giro**: un giro dura facilmente 20-90+ minuti; se il
  risparmio energetico sospende il PC, il processo viene ucciso a forza (osservato). Disattiva
  la sospensione automatica prima di lanciare un giro lungo. Se succede comunque, le preferenze
  e la sessione si autoripristinano da sole al giro successivo (vedi sotto) — ma il giro
  interrotto va rilanciato da capo.

## Dettagli tecnici

- Pilotaggio via metodi/slot Qt reali (nessun mouse/tastiera simulati): vedi `DemoDriver` in
  `tools/demo/demo_runner.py`. Un "watchdog" generico intercetta dialog modali inattesi (es. lo
  storico "gia' scaricato", riconosciuto per `QMessageBox.ButtonRole`, non per testo tradotto)
  e non blocca mai il giro. Vedi la sezione "Contratto con MDPR" in cima al runner per l'elenco
  completo di cosa dipende da cosa nel codice del tool.
- Cartella download di test isolata: `MyDocs/gallery/downloads/` (svuotata a inizio E fine di
  OGNI pass, IT e EN inclusi, cosi' l'altra lingua riparte da un download reale e non da un
  file gia' completo).
- La preferenza lingua (`preferences.json`) e la sessione da ripristinare
  (`session_state.json`) vengono salvate su un sidecar su disco (`*.demo_orig_backup`) prima
  del giro e ripristinate dopo: il giro dimostrativo non lascia alterata la lingua/tema reale
  dell'app sulla macchina. Il backup e' su disco (non solo in RAM) apposta: se il processo
  viene ucciso a forza (Task Manager, sospensione del PC) i blocchi `finally` di Python
  saltano, ma il sidecar resta — il giro SUCCESSIVO se ne accorge e ripristina l'originale
  prima di fare qualunque altra cosa.
- `logs/download_history.log`, `logs/proxy_cache.json` ecc. si aggiornano per davvero (e'
  comportamento normale dell'app, non un effetto collaterale del runner).
- Prima di un giro lungo, `--dry-run` (vedi sopra) verifica in automatico che il runner sia
  ancora allineato al codice della GUI: se qualcosa e' cambiato (un metodo rinominato, una
  classe spostata) lo dice in meno di 5 secondi invece di scoprirlo a meta' di un giro da
  90 minuti.

Link di default usati in questo giro:
- Cartella: `{args.folder_link if hasattr(args, "folder_link") else DEFAULT_FOLDER_LINK}`
- File singolo: `{args.file_link if hasattr(args, "file_link") else DEFAULT_FILE_LINK}`
"""
    (out_dir / "README.md").write_text(content, encoding="utf-8")


def write_report(out_dir: Path, results: dict[str, dict]) -> None:
    lines = ["# Report giro demo", ""]
    for lang, r in results.items():
        lines.append(f"## {lang}")
        lines.append(f"- ok: {r.get('ok')}")
        lines.append(f"- stop_reason: {r.get('stop_reason')}")
        lines.append(f"- raw_duration_s: {r.get('raw_duration_s')}")
        lines.append(f"- cut_duration_s: {r.get('cut_duration_s')}")
        lines.append(f"- segments: {r.get('segments')}")
        lines.append(f"- stills: {len(r.get('stills', []))}")
        if r.get("error"):
            lines.append(f"- error: {r.get('error')}")
        for note in r.get("notable", []):
            lines.append(f"- NOTABILE: {note}")
        lines.append("")
    (out_dir / "run-report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
