# Demo runner MDPR — due modalita' separate: video reali (IT/EN) e screenshot
# puliti (IT/EN), entrambe con un giro reale del tool (download COMPLETI veri).
#
# Perche' due modalita' e non una sola con estrazione di frame: gli screenshot
# ricavati da un video escono spesso mossi o catturati a meta' transizione. Il
# video vuole ritmo (velocita' variabile in post-produzione); gli screenshot
# vogliono fotografie di stati FERMI (settling + cattura dedicata). Le due
# modalita' condividono lo stesso flusso "regia" (tour dei 5 menu, download
# reale, filtro Completati, apertura Explorer) ma non condividono l'output.
#
# Pilota la GUI VERA con metodi/slot Qt reali (nessun mouse/tastiera simulati).
#
# Architettura: il processo "genitore" (questo script invocato senza --_worker)
# fa da orchestratore puro Python (nessun Qt). Per ogni (modalita', lingua)
# rilancia SE STESSO come sottoprocesso con --_worker: garantisce una "nuova
# istanza pulita" (QApplication/Translator/orchestrator sono singleton di
# modulo, non vanno riusati fra due giri) e isola un eventuale blocco di un
# giro senza perdere gli altri. Un `--mode both` esegue prima TUTTI i pass
# screenshots (piu' veloci da rivedere, meno rischio di rompersi in post-
# produzione) poi TUTTI i pass video, ciascuno con il proprio backup/restore
# di preferenze e la propria pulizia di downloads/.
#
# === Contratto con MDPR (aggiornare se cambia) ===
#
# Questo script dipende da superficie PRIVATA della GUI (metodi con underscore,
# attributi interni), non solo da API pubbliche: e' una scelta deliberata (serve
# a pilotare cose — menu impostazioni, filtro job, dialogo di espansione — che
# non hanno un ingresso pubblico piu' pulito), ma vuol dire che un refactor
# interno la puo' rompere senza toccare nessun contratto "ufficiale". Questa
# sezione e' il modo per accorgersene: se tocchi uno di questi punti in
# src/gui o src/core, aggiorna QUI e nel codice sotto, poi rilancia `--dry-run`
# (lo verifica in automatico per import/slot/i18n; il resto — vedi "Verificato
# SOLO da un giro reale" — va controllato a mano o con un giro vero).
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
# - src.gui.about_dialog.AboutDialog                  (classe, SOLO per riconoscimento
#                                                       per nome nel watchdog: non piu'
#                                                       istanziata direttamente dal runner)
# - src.gui.experimental_dialog.ExperimentalFeaturesDialog  (idem)
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
# - MainWindow._open_about_dialog()                — apre AboutDialog (menu Info del tour)
# - MainWindow._open_experimental_dialog()         — apre ExperimentalFeaturesDialog
#                                                     (menu "Strumenti" del tour — vedi nota
#                                                     sotto: nella GUI si chiama "Sperimentale")
# - MainWindow._begin_folder_expansion(links)      — assegna self._expand_dialog: il
#                                                     dry-run verifica che "_expand_dialog"
#                                                     compaia nel sorgente del metodo (stesso
#                                                     trucco di _open_dialogs, non instanzia)
# - ControlsBar.set_download_dir(str)              — reindirizza i download di test
# - ControlsBar._show_settings_menu()              — apre il popup Impostazioni
# - ControlsBar._settings_menu                     — QMenu persistente, SOLO su istanza
# - ControlsBar.language_combo                     — QComboBox pubblico dentro il popup
#                                                     Impostazioni; .showPopup()/.hidePopup()
#                                                     per il "sub-menu" Lingua del tour
# - ControlsBar.theme_btn                          — QPushButton pubblico, .click() per il
#                                                     toggle tema del tour (non e' un menu:
#                                                     e' un pulsante, come da Contratto)
#   (_settings_menu/language_combo/theme_btn sono verificati dal dry-run costruendo una
#   ControlsBar() autonoma — headless, sicura: nessuna rete nel suo __init__)
# - LinkPanel.open_paste_dialog()                  — apre il dialogo "Incolla link Mega"
#                                                     (usato TRE volte dal tour: vuoto per
#                                                     mostrare l'interfaccia pulita, compilato
#                                                     per l'aggiunta reale, poi una terza volta
#                                                     al passo 15 col ri-tentativo degli STESSI
#                                                     link — vedi POPUP INTENZIONALI sopra)
# - JobsPanel._on_filter_button_clicked(category)  — applica un filtro (usato per "Completati")
# - JobsPanel.model                                — attributo, istanza di JobsModel (SOLO
#                                                     verificabile con un giro vero: JobsPanel
#                                                     non e' nel Contratto delle istanze headless)
# - JobsModel.jobs_iter()                          — polling dello stato job (NESSUN segnale
#                                                     Qt e' usato per lo stato: vedi sotto)
# - Job (dataclass): campi .file_id/.status/.progress/.speed/.file_name/.url/.output_path —
#   verificati con dataclasses.fields(Job), non serve istanza. .output_path e' NUOVO
#   (serve al passo 9, apertura Explorer sul file scaricato) rispetto alla versione precedente
#   del runner.
# - PasteLinksDialog.edit (QTextEdit) / .add_btn (QPushButton) / .cancel_btn (QPushButton) —
#   riempiti/cliccati dal watchdog. .cancel_btn e' NUOVO (chiude il giro "vuoto" del tour
#   senza confermare nulla). Verificati costruendo un PasteLinksDialog([], False) headless
#   (nessuna rete nel suo __init__).
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
# Chiavi i18n usate dal watchdog per RICONOSCERE un dialog: NESSUNA. Il
# watchdog distingue i dialog per CLASSE Python (isinstance/type(w).__name__:
# "PasteLinksDialog", "AboutDialog", "ExperimentalFeaturesDialog",
# "QProgressDialog", QMessageBox) e, per i due QMessageBox del tour, per
# QMessageBox.ButtonRole/Icon — MAI dal testo tradotto, quindi e' insensibile
# alla lingua per costruzione:
# - "gia' scaricato": si riconosce dall'INSIEME dei ButtonRole presenti
#   (Accept+Destructive+Reject insieme). Se link_panel.confirm_already_downloaded()
#   smettesse di usare uno di questi tre ruoli, il watchdog lo tratterebbe
#   come un dialog IGNOTO (chiuso dopo 4s col bottone di default): il
#   --dry-run non lo verifica (e' un comportamento, non un'API), va
#   controllato a mano se si tocca link_panel.py.
# - "cartelle espanse": si riconosce dal flag di stato del driver (armato
#   prima di ogni Avvia con un link cartella) insieme a Icon.Information + un
#   solo bottone. Se MainWindow._on_expansion_done() smettesse di essere
#   Icon.Information a un solo bottone, stessa sorte (dialog ignoto, 4s).
# La chiave i18n "main_window.expand_report_title" usata per il TITOLO di
# quel popup non serve al riconoscimento (che resta insensibile alla lingua
# come sopra): il --dry-run la verifica comunque, ma solo per accorgersi se
# la chiave sparisce dai dizionari (romperebbe il testo del popup, non la
# sua individuazione).
#
# NOTA SUL NOME "Strumenti": nel codice della GUI non esiste un menu chiamato
# "Strumenti". Il pulsante piu' vicino concettualmente (unica superficie a
# icona/dialogo separata oltre a Impostazioni/Aggiungi link/Tema/Info) e' il
# pulsante "Sperimentale" (icona 🧪, ExperimentalFeaturesDialog): e' quello che
# il tour apre per il quinto passo. Se in futuro nasce un vero menu
# "Strumenti", questo runner va aggiornato per puntare li'.
#
# POPUP INTENZIONALI (NON anomalie, NON da liquidare col ramo generico del
# watchdog): il giro reale ne mostra due, entrambi comportamenti VERI di
# MDPR. Il watchdog li riconosce PRIMA del suo ramo generico e li tratta come
# tappe scriptate del tour, con screenshot dedicato:
#
# - "Cartelle Mega espanse": QMessageBox.information(self,
#   t("main_window.expand_report_title"), "\n".join(report)) dentro
#   MainWindow._on_expansion_done() (src/gui/main_window.py). Compare SEMPRE
#   dopo un'espansione di cartella riuscita: FolderExpandWorker.run()
#   aggiunge almeno una riga di riepilogo (chiave "folder_expand.ok_line")
#   per ogni cartella espansa, quindi "report" non e' mai vuoto quando
#   l'input contiene un link cartella (sempre vero nel giro di questo
#   runner). Icona Information, UN solo bottone OK (AcceptRole). Il
#   watchdog lo riconosce da un flag di stato del driver ("sto aspettando
#   questo popup", armato dal driver appena PRIMA di ogni clic su Avvia che
#   include un link cartella — sia il primo giro sia il ri-tentativo del
#   passo 15) combinato con icona Information + un solo bottone: screenshot
#   "08-popup-cartelle-espanse.png" alla PRIMA comparsa, trattenuto ~5s in
#   video, poi chiuso con OK. Ricompare (chiuso, non ri-fotografato) al
#   ri-tentativo del passo 15, perche' la cartella viene rielencata da capo.
# - "Links already downloaded": funzione DI MODULO (non un metodo di
#   classe) confirm_already_downloaded(links, parent) in
#   src/gui/link_panel.py. Confronta i link (per handle Mega, non per
#   stringa URL) con download_history.log e, se almeno uno risulta gia'
#   scaricato, mostra UN QMessageBox (Icon.Warning) con TRE bottoni custom:
#   "Salta gia' scaricati" (AcceptRole, default — filtra i doppioni e
#   prosegue con gli altri), "Scarica comunque" (DestructiveRole — li tiene
#   tutti, li riscarica per davvero), "Annulla" (RejectRole — abortisce,
#   la funzione ritorna None). E' chiamata da DUE punti, non uno:
#   LinkPanel._on_paste() (subito dopo la conferma del dialogo "Incolla
#   link") e MainWindow._start_with_links() (subito dopo il clic su Avvia,
#   sulla lista GIA' espansa se c'erano cartelle). Al passo 15 del tour
#   (ri-tentativo con gli stessi link) scatta in ENTRAMBI i punti nello
#   stesso click: la prima comparsa (al paste, sui 2 link grezzi) va chiusa
#   in silenzio con "Scarica comunque" — altrimenti la lista si svuota li'
#   e il successivo Avvia non fa piu' scattare nulla; la seconda (all'Avvia,
#   sui 2 link ormai espansi — "2 di 2 gia' scaricati" coi link di test in
#   uso) e' quella VERA da mostrare: screenshot "15-popup-gia-scaricato.png",
#   poi chiusa con "Salta gia' scaricati" (NON "Scarica comunque": vogliamo
#   dimostrare l'anti-duplicati, non riscaricare per davvero). Il watchdog
#   la riconosce dall'INSIEME dei ButtonRole presenti (Accept+Destructive+
#   Reject insieme), non dal testo tradotto: insensibile alla lingua come il
#   resto del watchdog, e insensibile anche a QUANTE volte compare.
#
# File/formati letti o scritti (OPACHI: il runner fa backup/restore a
# livello di BYTE, non parsa mai le chiavi JSON):
# - preferences.json (REPO_ROOT) — l'unica scrittura la fa TR.set_preference(lang)
#   (chiave "language"); il runner fa solo backup su sidecar prima e restore dopo
# - session_state.json (REPO_ROOT) — cancellato prima di aprire MainWindow (evita
#   il prompt "Riprendi sessione?"); backup/restore identico a preferences.json
# - logs/download_history.log (LOGS_DIR di src.core.config) — backup/restore
#   IDENTICO a preferences.json/session_state.json (sidecar + self-heal), ma con
#   in piu' una PULIZIA MIRATA prima del giro: le righe che riguardano gli
#   handle dei due link di test (GfgljYpJ/LTwSwTqS, vedi _TEST_HISTORY_HANDLES)
#   vengono rimosse dal file live prima di aprire MainWindow, cosi' un residuo
#   di storico di un giro precedente non fa scattare "gia' scaricato" fin dal
#   PRIMO Avvia (lo vogliamo SOLO al ri-tentativo scriptato del passo 15). Il
#   file completo (storico vero incluso) torna al suo posto dal sidecar a fine
#   pass, qualunque cosa succeda nel frattempo — il giro scarica per davvero,
#   quindi durante il pass il file live si arricchisce di righe vere che
#   vanno scartate al restore, non fuse.
# - *.demo_orig_backup — sidecar di backup creati dal runner stesso (non di MDPR)
# - MyDocs/gallery/last-results.json — manifest del runner (non di MDPR): tiene
#   traccia dell'ultimo risultato OK per (modalita', lingua), cosi' un giro
#   `--mode screenshots` successivo a un giro `--mode video` non fa sparire la
#   sezione video da index.html (e viceversa). Riletto/aggiornato a ogni giro.
#
# Cartelle usate:
# - <output-dir>/downloads/  — destinazione download di test (svuotata a inizio
#   E fine di OGNI pass, mai la downloads/ reale del progetto)
# - <output-dir>/videos/, <output-dir>/screens/<lang>/, <output-dir>/timelines/,
#   <output-dir>/_tmp_segments_<lang>/, <output-dir>/_tmp_explorer_<lang>.mp4 — output
#   del runner, non di MDPR
#
# Flag --reset: PRIMA di qualunque pass (mai in --dry-run, che resta
# read-only), svuota <output-dir> (default MyDocs/gallery/) tranne le
# cartelle temporanee "_tmp_*" ancora attive e gli eventuali file nascosti,
# poi ricrea la cartella vuota. Vedi reset_gallery().
#
# Verificato SOLO da un giro reale (il --dry-run non ci arriva):
# - che i job passino DAVVERO per RUNNING/COMPLETED/ABANDONED con questi nomi
#   esatti (STATUS_* import OK non garantisce che jobs_iter() li usi ancora
#   cosi' — e' un comportamento, non una firma);
# - che ControlsBar._settings_menu/language_combo/theme_btn e i dialoghi Info/
#   Sperimentale/Incolla si aprano/chiudano visivamente come atteso;
# - che confirm_already_downloaded() assegni ancora i tre ButtonRole giusti
#   (vedi sopra) e che, al ri-tentativo del passo 15, scatti DAVVERO due
#   volte nello stesso click (paste + Avvia) cosi' come previsto — se in
#   futuro smettesse di scattare al paste, il driver chiuderebbe con "Scarica
#   comunque" un popup che invece e' gia' quello buono da fotografare, e la
#   sequenza si romperebbe in un modo che il --dry-run non vede;
# - che MainWindow._on_expansion_done() mostri DAVVERO il popup Information
#   ogni volta che c'e' un link cartella (il codice attuale lo garantisce,
#   vedi POPUP INTENZIONALI, ma e' un comportamento, non una firma);
# - il testo del titolo finestra (t("main_window.title", ...)) resta stabile
#   durante una sessione: serve a gdigrab per agganciare la finestra una volta
#   sola all'apertura (modalita' video);
# - che `QScreen.grabWindow(hwnd)` catturi correttamente il contenuto di popup
#   Qt (QMenu, popup di QComboBox) e non solo lo sfondo: e' un dettaglio di
#   composizione della finestra su Windows che non si puo' verificare offline
#   (modalita' screenshots);
# - che `ctypes.windll.user32.GetForegroundWindow()` restituisca davvero
#   l'HWND della finestra Explorer appena aperta (passo 9/Explorer) e non
#   un'altra finestra che avesse rubato il focus nel frattempo (modalita'
#   screenshots) — se sbaglia bersaglio, lo screenshot 14 mostra la finestra
#   sbagliata invece di fallire rumorosamente;
# - che il segmento Explorer (schermo intero, modalita' video) si concateni
#   senza artefatti visivi dopo lo scale+pad a WINDOW_W x WINDOW_H.
#
# Se cambi UNO qualunque di questi punti nel codice/GUI di MDPR, aggiorna
# questa sezione + il codice del runner, poi rilancia `--dry-run`. Se il
# cambio e' non-triviale, valuta anche un giro reale (~20-90+ min per
# modalita') prima di considerare "finito" il ciclo di lavoro (vedi
# .claude/rules/demo-runner.md).
from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.wintypes
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
_MANIFEST_NAME = "last-results.json"

# Coppie apri/chiudi (modalita' video) che diventano un'unica finestra a 1x nel
# taglio "bello" (l'interazione intera resta a velocita' naturale, non solo un
# dintorno del timestamp).
SPAN_PAIRS = [
    ("opening_phase_begin", "opening_phase_end"),
    ("detail_dialog_open", "detail_dialog_close"),
    ("settings_menu_open", "settings_menu_close"),
    ("about_dialog_open", "about_dialog_close"),
    ("experimental_dialog_open", "experimental_dialog_close"),
    ("paste_menu_open", "paste_menu_close"),
    ("expand_report_open", "expand_report_close"),
    ("duplicate_popup_open", "duplicate_popup_close"),
    ("explorer_open", "explorer_close"),
]
# Padding (secondi prima, secondi dopo) per gli eventi puntuali che meritano
# una sosta piu' lunga del default (2s prima / 4s dopo) nel taglio video.
EVENT_PAD = {
    "theme_toggled": (1.0, 3.0),
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
        description="Registra un giro reale del tool (IT/EN): video e/o galleria di screenshot.",
    )
    p.add_argument("--mode", choices=["video", "screenshots", "both"], default=None,
                    help="video = solo registrazione+taglio; screenshots = solo foto a stato "
                         "fermo; both = screenshots poi video. Obbligatorio fuori da --dry-run.")
    p.add_argument("--lang", choices=["it", "en", "both"], default="both")
    p.add_argument("--folder-link", default=DEFAULT_FOLDER_LINK)
    p.add_argument("--file-link", default=DEFAULT_FILE_LINK)
    p.add_argument("--safety-cap-minutes", type=float, default=90.0)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument(
        "--dry-run", action="store_true",
        help="Valida il legame col codice di MDPR (import/slot/i18n) per ENTRAMBE le modalita' "
             "senza aprire MainWindow, ffmpeg o toccare download/preferenze. <5s, per CI/pre-commit.",
    )
    p.add_argument(
        "--reset", action="store_true",
        help="Svuota <output-dir> (tranne cartelle temporanee attive) PRIMA del giro. "
             "Nessun effetto in combinazione con --dry-run (resta read-only).",
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
    ("src.core.config", ["APP_VERSION", "LOGS_DIR", "DOWNLOAD_HISTORY_LOG"]),
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
    ("src.gui.link_panel", ["LinkPanel", "confirm_already_downloaded"]),
    ("src.gui.jobs_panel", ["JobsPanel"]),
]
# (classe, attributo) — rispecchia "Slot/metodi/attributi" nel Contratto,
# SOLO quelli verificabili a livello di classe (nessuna istanza richiesta).
_DRY_RUN_CLASS_ATTRS = [
    ("MainWindow", "_on_start"),
    ("MainWindow", "_open_detail"),
    ("MainWindow", "_open_about_dialog"),
    ("MainWindow", "_open_experimental_dialog"),
    ("MainWindow", "_begin_folder_expansion"),
    ("MainWindow", "_on_expansion_done"),
    ("ControlsBar", "set_download_dir"),
    ("ControlsBar", "_show_settings_menu"),
    ("LinkPanel", "open_paste_dialog"),
    ("JobsPanel", "_on_filter_button_clicked"),
]
_JOB_REQUIRED_FIELDS = {"file_id", "status", "progress", "speed", "file_name", "url", "output_path"}
# Il watchdog stesso non dipende da NESSUNA chiave i18n per RICONOSCERE un
# dialog (vedi Contratto — distingue per classe/ButtonRole/Icon, mai per
# testo tradotto). Questa lista verifica solo che le chiavi usate per
# COSTRUIRE i popup "intenzionali" del tour esistano ancora nei due
# dizionari (una chiave sparita romperebbe il testo del popup, non la sua
# individuazione).
_I18N_KEYS_USED = ["main_window.expand_report_title"]

# Handle Mega dei due link di test (vedi DEFAULT_FOLDER_LINK/DEFAULT_FILE_LINK
# sopra): usati per ripulire da download_history.log le righe residue di un
# giro precedente prima di aprire MainWindow (vedi "File/formati" nel
# Contratto).
_TEST_HISTORY_HANDLES = ("GfgljYpJ", "LTwSwTqS")


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
        try:
            expand_src = inspect.getsource(MainWindow._begin_folder_expansion)
            if "_expand_dialog" not in expand_src:
                errors.append(
                    "runner rotto: MainWindow._begin_folder_expansion non assegna piu' self._expand_dialog"
                )
            else:
                counts["slots"] += 1
        except (OSError, TypeError, AttributeError) as exc:
            errors.append(
                f"runner rotto: impossibile leggere il sorgente di MainWindow._begin_folder_expansion ({exc})"
            )

    ControlsBar = ns.get("ControlsBar")
    if ControlsBar is not None:
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([sys.argv[0]])
            cb = ControlsBar()
            for attr in ("_settings_menu", "language_combo", "theme_btn"):
                if not hasattr(cb, attr):
                    errors.append(f"runner rotto: ControlsBar().{attr} non esiste piu'")
                else:
                    counts["slots"] += 1
            cb.deleteLater()
            del app
        except Exception as exc:
            errors.append(
                f"runner rotto: impossibile verificare gli attributi di ControlsBar() "
                f"({type(exc).__name__}: {exc})",
            )

    PasteLinksDialog = ns.get("PasteLinksDialog")
    if PasteLinksDialog is not None:
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([sys.argv[0]])
            dlg = PasteLinksDialog([], False)
            for attr in ("edit", "add_btn", "cancel_btn"):
                if not hasattr(dlg, attr):
                    errors.append(f"runner rotto: PasteLinksDialog().{attr} non esiste piu'")
                else:
                    counts["slots"] += 1
            dlg.deleteLater()
            del app
        except Exception as exc:
            errors.append(
                f"runner rotto: impossibile verificare gli attributi di PasteLinksDialog() "
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

    logs_dir = ns.get("LOGS_DIR")
    history_name = ns.get("DOWNLOAD_HISTORY_LOG")
    if logs_dir is None or history_name is None:
        errors.append(
            "runner rotto: LOGS_DIR/DOWNLOAD_HISTORY_LOG non importati, "
            "impossibile calcolare il path di download_history.log"
        )
    else:
        history_path = logs_dir / history_name
        if history_path.name != history_name:
            errors.append(f"runner rotto: path di download_history.log calcolato male ({history_path})")
        else:
            counts["slots"] += 1

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
        f"{counts['i18n']} chiavi i18n, tutto in ordine (entrambe le modalita', {elapsed:.2f}s)",
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

    if args.mode is None:
        print(
            "--mode e' obbligatorio: video | screenshots | both (oppure usa --dry-run).",
            flush=True,
        )
        return 2

    needs_ffmpeg = args.mode in ("video", "both")
    if needs_ffmpeg and (shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None):
        print(
            "ffmpeg/ffprobe non trovati nel PATH. Installa con "
            "'winget install ffmpeg' (o 'choco install ffmpeg -y') e rilancia.",
            flush=True,
        )
        return 2

    out_dir = Path(args.output_dir).resolve()
    if args.reset:
        reset_gallery(out_dir)

    # Se un giro precedente e' stato ucciso a forza (kill esterno: niente
    # finally Python), il sidecar di backup e' rimasto residuo col vero
    # originale — ripristina PRIMA di spawnare qualunque worker.
    _self_heal_stale_backups(
        REPO_ROOT / "preferences.json", REPO_ROOT / "session_state.json", _history_log_path(),
    )

    (out_dir / "videos").mkdir(parents=True, exist_ok=True)
    (out_dir / "screens").mkdir(parents=True, exist_ok=True)
    (out_dir / "timelines").mkdir(parents=True, exist_ok=True)

    run_modes = ["screenshots", "video"] if args.mode == "both" else [args.mode]
    langs = ["it", "en"] if args.lang == "both" else [args.lang]

    manifest = _load_manifest(out_dir)
    overall_ok = True
    for mode in run_modes:
        print(f"[demo_runner] === Avvio modalita' '{mode}' ===", flush=True)
        mode_results: dict[str, dict] = {}
        for lang in langs:
            print(f"[demo_runner] --- pass '{mode}'/'{lang}' ---", flush=True)
            mode_results[lang] = spawn_worker(mode, lang, args, out_dir)
            r = mode_results[lang]
            if r.get("ok"):
                print(f"[demo_runner] '{mode}'/'{lang}' OK: stop_reason={r.get('stop_reason')}", flush=True)
            else:
                print(f"[demo_runner] '{mode}'/'{lang}' FALLITO: {r.get('error')}", flush=True)
                overall_ok = False
        manifest.setdefault(mode, {}).update(mode_results)
        _save_manifest(out_dir, manifest)

    downloads_dir = out_dir / "downloads"
    if downloads_dir.exists():
        shutil.rmtree(downloads_dir, ignore_errors=True)

    build_index_html(out_dir, manifest)
    write_readme(out_dir, args, manifest)
    write_report(out_dir, manifest)
    print(f"[demo_runner] Fatto. Apri {out_dir / 'index.html'}", flush=True)
    return 0 if overall_ok else 1


def reset_gallery(out_dir: Path) -> None:
    """--reset: svuota out_dir PRIMA di qualunque pass. Salta i file nascosti
    (nessuno oggi, ma "tranne file nascosti" e' un requisito esplicito) e le
    cartelle temporanee "_tmp_*" ancora attive (residuo di un giro precedente
    che potrebbe essere in corso altrove) — tutto il resto viene cancellato."""
    if out_dir.exists():
        for entry in out_dir.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.name.startswith("_tmp_"):
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    print("reset: cartella MyDocs/gallery/ svuotata", flush=True)


def spawn_worker(mode: str, lang: str, args, out_dir: Path) -> dict:
    argv = [
        sys.executable, str(SCRIPT_PATH),
        "--_worker", "--mode", mode, "--lang", lang,
        "--folder-link", args.folder_link,
        "--file-link", args.file_link,
        "--safety-cap-minutes", str(args.safety_cap_minutes),
        "--output-dir", str(out_dir),
    ]
    # Margine oltre il safety-cap per lasciare tempo al post-processing
    # (segmenti ffmpeg, in modalita' video) dentro lo stesso sottoprocesso.
    hard_timeout = args.safety_cap_minutes * 60 + 900
    try:
        proc = subprocess.run(
            argv, cwd=str(REPO_ROOT), timeout=hard_timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "lang": lang, "mode": mode, "ok": False, "error": "hard_timeout_subprocess",
            "stdout_tail": (exc.stdout or "")[-4000:],
            "stderr_tail": (exc.stderr or "")[-4000:],
        }
    result = _extract_result_json(proc.stdout or "")
    if result is None:
        return {
            "lang": lang, "mode": mode, "ok": False, "error": "no_result_json",
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
# Manifest: ultimo risultato OK per (modalita', lingua). Serve perche' i giri
# video e screenshots avvengono tipicamente in SESSIONI SEPARATE (non sempre
# --mode both): senza un manifest persistente, un giro `--mode screenshots`
# da solo ricostruirebbe un index.html senza la sezione video del giro
# precedente (e viceversa).
# ---------------------------------------------------------------------------

def _load_manifest(out_dir: Path) -> dict:
    path = out_dir / _MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("Manifest %s illeggibile, riparto da zero", path)
        return {}


def _save_manifest(out_dir: Path, manifest: dict) -> None:
    path = out_dir / _MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _history_log_path() -> Path:
    from src.core.config import DOWNLOAD_HISTORY_LOG, LOGS_DIR
    return LOGS_DIR / DOWNLOAD_HISTORY_LOG


def _strip_test_history_lines(path: Path) -> None:
    """Rimuove da download_history.log le righe che riguardano i due handle
    di test (_TEST_HISTORY_HANDLES), PRIMA di aprire MainWindow. Senza
    questo, uno storico con residui di un giro precedente (stesso link di
    default) farebbe scattare "gia' scaricato" fin dal PRIMO Avvia invece
    che solo al ri-tentativo scriptato del passo 15. Il file viene comunque
    ripristinato per intero dal sidecar a fine pass (vedi _restore_from_backup):
    questa funzione tocca solo la copia LIVE usata durante il giro."""
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        log.exception("Impossibile leggere %s per la pulizia pre-giro", path)
        return
    kept = [line for line in lines if not any(h in line for h in _TEST_HISTORY_HANDLES)]
    if len(kept) != len(lines):
        try:
            path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            log.exception("Impossibile ripulire %s dai link di test", path)


# ---------------------------------------------------------------------------
# Worker: un giro completo (una modalita', una lingua), in un processo Python
# dedicato.
# ---------------------------------------------------------------------------

def run_worker_pass(args) -> dict:
    lang = args.lang
    mode = args.mode
    if lang not in ("it", "en"):
        return {"lang": lang, "mode": mode, "ok": False, "error": "lang_non_valido_per_worker"}
    if mode not in ("video", "screenshots"):
        return {"lang": lang, "mode": mode, "ok": False, "error": "mode_non_valido_per_worker"}

    out_dir = Path(args.output_dir).resolve()
    videos_dir = out_dir / "videos"
    screens_lang_dir = out_dir / "screens" / lang
    mode_key = "video" if mode == "video" else "screens"
    timeline_path = out_dir / "timelines" / f"timeline-{mode_key}-{lang}.jsonl"
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    downloads_dir = out_dir / "downloads"
    prefs_path = REPO_ROOT / "preferences.json"
    session_path = REPO_ROOT / "session_state.json"
    history_path = _history_log_path()

    _self_heal_stale_backups(prefs_path, session_path, history_path)
    _ensure_original_backup(prefs_path)
    _ensure_original_backup(session_path)
    _ensure_original_backup(history_path)
    _strip_test_history_lines(history_path)
    result: dict = {"lang": lang, "mode": mode, "ok": False}

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
        driver = DemoDriver(window, lang, args, out_dir, timeline_fh, mode)
        QTimer.singleShot(1000, driver.begin)
        app.exec()
        timeline_fh.close()

        result["ok"] = True
        result["stop_reason"] = driver.result.get("stop_reason", "sconosciuto")
        result["notable"] = driver.notable

        events = _read_events(timeline_path)
        result["events_count"] = len(events)

        if mode == "video":
            raw_path = videos_dir / f"raw-{lang}.mp4"
            if not raw_path.exists() or raw_path.stat().st_size == 0:
                result["ok"] = False
                result["error"] = "video_raw_mancante_o_vuoto"
                return result
            demo_path = videos_dir / f"demo-{lang}.mp4"
            tmp_dir = out_dir / f"_tmp_segments_{lang}"
            explorer_raw = driver.explorer_raw_path
            if explorer_raw is not None and not (explorer_raw.exists() and explorer_raw.stat().st_size > 0):
                explorer_raw = None
            cut_info = build_variable_speed_cut(raw_path, events, demo_path, tmp_dir, explorer_raw)
            result.update(cut_info)
            result["explorer_segment_included"] = explorer_raw is not None
        else:
            screens_lang_dir.mkdir(parents=True, exist_ok=True)
            result["screenshots"] = list(driver.screenshots)
            if not driver.screenshots:
                result["notable"] = list(result.get("notable") or []) + [
                    "nessuno screenshot prodotto in questo giro"
                ]

        return result
    except Exception as exc:  # noqa: BLE001 — vogliamo comunque il RESULT_JSON
        log.exception("Errore nel pass %s/%s", mode, lang)
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        _restore_from_backup(prefs_path)
        _restore_from_backup(session_path)
        _restore_from_backup(history_path)
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
# DemoDriver — pilota MainWindow via metodi/slot Qt reali, registra la
# timeline e (a seconda della modalita') la registrazione video o gli
# screenshot a stato fermo.
#
# Il tour dei 5 menu (Impostazioni, Sperimentale/"Strumenti", Aggiungi link
# vuoto, Tema, Info) avviene tutto in apertura, PRIMA di aggiungere i link
# veri: e' un cambio deliberato rispetto alla versione precedente del runner
# (che apriva Impostazioni/Info/Sperimentale a meta' download, quando la
# velocita' aggregata si stabilizzava) perche' il tour non ha piu' bisogno di
# aspettare nulla di asincrono — la dashboard e' comunque vuota in quel
# momento, quindi tanto vale farlo subito e in modo deterministico.
#
# Nota sui passi 4/5 del flusso richiesto ("Job pronti pre-avvio" prima di
# "Avvio"): nella GUI reale i job compaiono nel modello SOLO dopo aver
# invocato MainWindow._on_start() (LinkPanel tiene i link in una lista
# interna non visibile finche' non si clicca Avvia — non esiste una coda
# "pronta ma non ancora avviata" visibile a schermo). I due passi sono quindi
# uniti: si clicca Avvia e si cattura il primo istante in cui i job compaiono
# (ancora in coda/appena partiti), invece di una fase separata pre-Avvio.
# ---------------------------------------------------------------------------

class DemoDriver:
    # Attese reali (millisecondi) usate SOLO in modalita' video: tengono un
    # menu/dialogo visibilmente aperto abbastanza a lungo da avere footage
    # reale da mantenere a 1x nel taglio (il post-processing puo' scegliere
    # la velocita' di un intervallo gia' registrato, non fabbricarne di
    # nuovo). In modalita' screenshots non servono: basta il settling.
    SETTINGS_HOLD_MS = 5000
    LANGUAGE_POPUP_HOLD_MS = 1500
    EXPERIMENTAL_HOLD_MS = 10000
    ABOUT_HOLD_MS = 8000
    PASTE_EMPTY_HOLD_MS = 4000
    DETAIL_HOLD_MS = 20000
    EXPLORER_RECORD_MS = 9000
    FOLDER_EXPANDED_HOLD_MS = 5000
    ALREADY_DOWNLOADED_HOLD_MS = 5000

    # Attesa di settling (modalita' screenshots): tempo dopo un'azione prima
    # di catturare, cosi' lo stato e' fermo e non a meta' transizione/repaint.
    SETTLE_MS = 500
    INTRO_SETTLE_MS = 1500

    # Dialog aperti dal watchdog generico (non dal driver stesso, che non ha
    # un riferimento diretto: MainWindow._open_about_dialog()/
    # _open_experimental_dialog() costruiscono+eseguono il dialog al proprio
    # interno). slug = nome file screenshot, hold_attr = nome dell'attributo
    # di classe con l'attesa in modalita' video.
    _DIALOG_TOUR = {
        "AboutDialog": ("06-menu-info", "ABOUT_HOLD_MS"),
        "ExperimentalFeaturesDialog": ("03-menu-strumenti", "EXPERIMENTAL_HOLD_MS"),
    }
    # Dialog che si autogestiscono (progress non bloccante dell'espansione
    # cartelle): il watchdog non deve toccarli (in modalita' screenshots viene
    # comunque tentata una cattura best-effort, vedi _maybe_capture_expansion_dialog).
    _IGNORED_MODAL_TYPES = {"QProgressDialog"}

    def __init__(self, window, lang: str, args, out_dir: Path, timeline_fh, mode: str) -> None:
        self.window = window
        self.lang = lang
        self.mode = mode
        self.out_dir = out_dir
        self.folder_link = args.folder_link
        self.file_link = args.file_link
        self.safety_cap_s = args.safety_cap_minutes * 60.0
        self.timeline_fh = timeline_fh

        self.t0: float | None = None
        self.ffmpeg_proc = None
        self.explorer_ffmpeg_proc = None
        self.explorer_raw_path: Path | None = None
        self._finished = False
        # Riferimenti FORTI (non id()): un dialog chiuso puo' essere raccolto
        # dal GC e un nuovo dialog puo' riottenere lo stesso id() Python,
        # facendolo ignorare per errore come "gia' gestito".
        self._handled_modals: list = []
        # "tour_empty" al passo 2c, "retry_same_links" al ri-tentativo (passo 15).
        self._paste_dialog_mode = "fill_and_confirm"
        self._jobs_seen = False
        self._last_status: dict[int, str] = {}
        self._first_completed_logged = False
        self._first_abandoned_logged = False
        self._detail_opened = False
        self._expansion_shot_done = False
        self._progress_shot_done = False
        self._all_done_triggered = False
        self._filter_shown = False
        self._explorer_done = False
        # Popup "Cartelle Mega espanse" (vedi POPUP INTENZIONALI nel
        # Contratto): armato prima di ogni Avvia che include un link cartella.
        self._awaiting_expand_report = False
        self._expand_report_shot_done = False
        # Popup "gia' scaricato" (idem): None finche' non inizia il
        # ri-tentativo del passo 15; poi "silent_anyway" per la comparsa al
        # paste, "skip_and_shoot" per quella vera all'Avvia.
        self._duplicate_popup_mode = None
        self._duplicate_popup_shot_done = False
        self.notable: list[str] = []
        self.screenshots: list[str] = []
        self.result: dict = {}

        self._watchdog_timer = None
        self._ticker_timer = None

    # ---- avvio -------------------------------------------------------------

    def begin(self) -> None:
        from PyQt6.QtCore import QTimer

        if self.mode == "video":
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
        QTimer.singleShot(self.INTRO_SETTLE_MS, self._tour_step_startup_shot)

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

    def _start_explorer_ffmpeg(self) -> None:
        path = self.out_dir / f"_tmp_explorer_{self.lang}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", FFMPEG_FRAMERATE,
            "-draw_mouse", "0",
            "-i", "desktop",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(path),
        ]
        self.explorer_ffmpeg_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd=str(self.out_dir),
        )
        self.explorer_raw_path = path

    # ---- tour dei 5 menu (fase 2, tutto in apertura) ------------------------

    def _tour_step_startup_shot(self) -> None:
        if self._finished:
            return
        self._maybe_capture("01-startup", self.window, self._tour_step_settings)

    def _tour_step_settings(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        controls = self.window.controls
        menu = controls._settings_menu
        self.log_event("settings_menu_open")

        def after_shot() -> None:
            if self._finished:
                return
            if self.mode == "screenshots":
                self._tour_settings_language(menu)
            else:
                QTimer.singleShot(self.SETTINGS_HOLD_MS, lambda: self._close_settings_menu(menu))

        self._maybe_capture("02-menu-impostazioni", menu, after_shot)
        controls._show_settings_menu()  # blocca (nested loop) finche' menu.close()
        if self._finished:
            return

    def _tour_settings_language(self, menu) -> None:
        if self._finished:
            return
        combo = self.window.controls.language_combo
        combo.showPopup()
        self.log_event("settings_menu_language_open")
        popup = combo.view().window()

        def after_lang_shot() -> None:
            if self._finished:
                return
            combo.hidePopup()
            self.log_event("settings_menu_language_close")
            self._close_settings_menu(menu)

        self._maybe_capture("02b-menu-impostazioni-lingua", popup, after_lang_shot)

    def _close_settings_menu(self, menu) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self.log_event("settings_menu_close")
        menu.close()
        QTimer.singleShot(300, self._tour_step_experimental)

    def _tour_step_experimental(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self.log_event("experimental_dialog_open")
        self.window._open_experimental_dialog()  # blocca; il watchdog cattura+chiude
        if self._finished:
            return
        self.log_event("experimental_dialog_close")
        QTimer.singleShot(300, self._tour_step_paste_empty)

    def _tour_step_paste_empty(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self._paste_dialog_mode = "tour_empty"
        self.log_event("paste_menu_open")
        self.window.link_panel.open_paste_dialog()  # blocca; il watchdog cattura+annulla
        if self._finished:
            return
        self.log_event("paste_menu_close")
        self._paste_dialog_mode = "fill_and_confirm"
        QTimer.singleShot(300, self._tour_step_theme)

    def _tour_step_theme(self) -> None:
        if self._finished:
            return
        self.window.controls.theme_btn.click()
        self.log_event("theme_toggled")
        self._maybe_capture("05-menu-tema", self.window, self._tour_step_info)

    def _tour_step_info(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self.log_event("about_dialog_open")
        self.window._open_about_dialog()  # blocca; il watchdog cattura+chiude
        if self._finished:
            return
        self.log_event("about_dialog_close")
        QTimer.singleShot(300, self._tour_step_paste_fill)

    # ---- fase 3: aggiunta link reale + avvio ---------------------------------

    def _tour_step_paste_fill(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self.window.link_panel.open_paste_dialog()  # blocca; il watchdog compila e conferma
        if self._finished:
            return
        self.log_event("paste_links")
        QTimer.singleShot(500, self._phase_click_start)

    def _fill_paste_dialog(self, dlg, shot_name: str | None) -> None:
        """Compila il dialogo coi due link di test e clicca Aggiungi.
        shot_name=None per il ri-tentativo del passo 15 (i link sono gia'
        stati fotografati la prima volta, non li rifotografiamo)."""
        from PyQt6.QtCore import QTimer

        text = f"{self.folder_link}\n{self.file_link}"
        dlg.edit.setPlainText(text)

        def after_fill() -> None:
            if self._finished:
                return
            if dlg.add_btn.isEnabled():
                dlg.add_btn.click()
            else:
                self._safe_close(dlg)

        def after_wait() -> None:
            if self._finished:
                return
            if shot_name is not None:
                self._maybe_capture(shot_name, dlg, after_fill)
            else:
                self._settle_then(after_fill)

        QTimer.singleShot(1200, after_wait)

    def _settle_then(self, then) -> None:
        """Come _maybe_capture, ma senza catturare nulla: solo il respiro
        (settling in screenshots, minimo in video) prima di proseguire."""
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        delay = self.SETTLE_MS if self.mode == "screenshots" else 50
        QTimer.singleShot(delay, then)

    def _phase_click_start(self) -> None:
        if self._finished:
            return
        self._awaiting_expand_report = True
        self.window._on_start()
        self.log_event("start_clicked")
        self.log_event("opening_phase_end")

    # ---- ticker periodico: stato job + trigger fasi successive --------------

    def _ticker_tick(self) -> None:
        if self._finished:
            return
        model = self.window.jobs_panel.model
        jobs = list(model.jobs_iter())

        if jobs and not self._jobs_seen:
            self._jobs_seen = True
            self.log_event("jobs_created", count=len(jobs))
            if self.mode == "screenshots" and not self._expansion_shot_done:
                self.notable.append(
                    "salto: 09-espansione-cartella: completata troppo velocemente per essere "
                    "fotografata (o nessun link cartella nel giro)"
                )
            self._maybe_capture("10-job-in-attesa", self.window, lambda: None)

        if not self._progress_shot_done and any(j.status == self._STATUS_RUNNING() for j in jobs):
            self._progress_shot_done = True
            self._maybe_capture("11-download-in-corso", self.window, lambda: None)

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

        terminal = self._TERMINAL_STATUSES()
        if jobs and all(j.status in terminal for j in jobs) and not self._all_done_triggered:
            self._all_done_triggered = True
            self.log_event("all_completed")
            self._maybe_capture("13-tutti-completati", self.window, self._phase_filter_completed)

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

    # ---- dettaglio job (>10% di progresso) -----------------------------------

    def _open_detail(self, file_id: int) -> None:
        from PyQt6.QtCore import QTimer

        self.window._open_detail(file_id)
        self.log_event("detail_dialog_open", job=file_id)
        dlg = self.window._open_dialogs.get(file_id)
        if self.mode == "screenshots" and dlg is not None:
            self._maybe_capture("12-dialogo-dettaglio-job", dlg, lambda: self._close_detail(file_id))
        else:
            QTimer.singleShot(self.DETAIL_HOLD_MS, lambda: self._close_detail(file_id))

    def _close_detail(self, file_id: int) -> None:
        if self._finished:
            return
        dlg = self.window._open_dialogs.get(file_id)
        if dlg is not None:
            dlg.close()
        self.log_event("detail_dialog_close", job=file_id)

    # ---- completamento: filtro + Explorer ------------------------------------

    def _phase_filter_completed(self) -> None:
        if self._finished:
            return
        from src.gui.jobs_panel import FILTER_COMPLETED

        try:
            self.window.jobs_panel._on_filter_button_clicked(FILTER_COMPLETED)
        except Exception:
            log.exception("impossibile applicare il filtro Completati")
        self._filter_shown = True
        self.log_event("completed_filter_shown")
        self._maybe_capture("14-filtro-completati", self.window, self._phase_retry_duplicate_links)

    # ---- ri-tentativo con gli stessi link (passo 15: anti-duplicati) --------

    def _phase_retry_duplicate_links(self) -> None:
        """Riapre "Incolla link Mega" con gli STESSI due link (mai rimossi da
        LinkPanel dopo il primo Avvia) e clicca Aggiungi: e' gia' sufficiente
        a far scattare confirm_already_downloaded() una prima volta dentro
        LinkPanel._on_paste() (vedi POPUP INTENZIONALI nel Contratto) — quella
        comparsa va chiusa in silenzio con "Scarica comunque", altrimenti la
        lista si svuota qui e il successivo Avvia non innesca piu' nulla."""
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self._paste_dialog_mode = "retry_same_links"
        self._duplicate_popup_mode = "silent_anyway"
        self.log_event("retry_paste_open")
        self.window.link_panel.open_paste_dialog()  # blocca; vedi docstring sopra
        if self._finished:
            return
        self.log_event("retry_paste_close")
        self._paste_dialog_mode = "fill_and_confirm"
        self._duplicate_popup_mode = "skip_and_shoot"
        QTimer.singleShot(500, self._phase_retry_click_start)

    def _phase_retry_click_start(self) -> None:
        if self._finished:
            return
        self._awaiting_expand_report = True
        self.window._on_start()
        self.log_event("retry_start_clicked")
        # Da qui in poi il proseguimento (Explorer) e' innescato dal watchdog
        # stesso, subito dopo aver chiuso il popup "gia' scaricato" vero
        # (quello dell'Avvia, non quello silenzioso del paste) — vedi
        # _handle_duplicate_popup. Nessun link supera il filtro (entrambi
        # gia' scaricati), quindi qui non nascono nuovi job da attendere.

    def _first_completed_output_path(self) -> str | None:
        for j in self.window.jobs_panel.model.jobs_iter():
            if j.status == self._STATUS_COMPLETED() and j.output_path:
                return j.output_path
        return None

    def _tour_explorer(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        self._explorer_done = True
        path = self._first_completed_output_path()
        if not path:
            self.log_event("explorer_step", skipped=True, reason="nessun job completato con output_path")
            self.notable.append("salto: apertura Explorer: nessun file completato disponibile")
            self._finish("natural_completion")
            return

        if self.mode == "video":
            self._stop_ffmpeg()
            self.log_event("main_recording_stopped_for_explorer")
            subprocess.run(["explorer", f"/select,{path}"], check=False)
            self.log_event("explorer_open")
            self._start_explorer_ffmpeg()
            QTimer.singleShot(self.EXPLORER_RECORD_MS, self._finish_explorer_video)
        else:
            subprocess.run(["explorer", f"/select,{path}"], check=False)
            self.log_event("explorer_open")
            QTimer.singleShot(self.SETTLE_MS + 1000, self._capture_explorer)

    def _finish_explorer_video(self) -> None:
        if self._finished:
            return
        self._stop_explorer_ffmpeg()
        self.log_event("explorer_close")
        self._finish("natural_completion")

    def _capture_explorer(self) -> None:
        if self._finished:
            return

        def finish_explorer() -> None:
            self.log_event("explorer_close")
            self._finish("natural_completion")

        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            self.notable.append(
                "salto: 16-explorer-file-selezionato: impossibile determinare la finestra Explorer"
            )
            finish_explorer()
            return
        self._do_capture_then("16-explorer-file-selezionato", hwnd, finish_explorer)

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

    # ---- watchdog dialog inattesi (e dialog aperti dai veri slot MainWindow) --

    def _watchdog_tick(self) -> None:
        if self._finished:
            return
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

        from src.gui.paste_links_dialog import PasteLinksDialog

        if self.mode == "screenshots":
            self._maybe_capture_expansion_dialog()

        w = QApplication.activeModalWidget()
        if w is None:
            return
        if any(w is h for h in self._handled_modals):
            return
        cls_name = type(w).__name__
        if cls_name in self._IGNORED_MODAL_TYPES:
            return  # si autogestisce (es. il progress dell'espansione cartelle)
        self._handled_modals.append(w)

        if isinstance(w, PasteLinksDialog):
            self._handle_paste_dialog(w)
        elif isinstance(w, QMessageBox):
            self._handle_message_box(w)
        elif cls_name in self._DIALOG_TOUR:
            self._handle_tour_dialog(w, cls_name)
        elif isinstance(w, QDialog):
            title = w.windowTitle()
            self.log_event("unexpected_dialog", title=title)
            self.notable.append(f"Dialogo modale inatteso durante il giro {self.lang}: {title!r}")
            QTimer.singleShot(4000, lambda: self._safe_close(w))

    def _handle_paste_dialog(self, dlg) -> None:
        from PyQt6.QtCore import QTimer

        if self._paste_dialog_mode == "tour_empty":
            if self.mode == "screenshots":
                self._maybe_capture("04-menu-aggiunta-link-vuoto", dlg, lambda: self._safe_reject(dlg))
            else:
                QTimer.singleShot(self.PASTE_EMPTY_HOLD_MS, lambda: self._safe_reject(dlg))
        elif self._paste_dialog_mode == "retry_same_links":
            self._fill_paste_dialog(dlg, None)
        else:
            self._fill_paste_dialog(dlg, "07-dialogo-incolla-link-compilato")

    def _handle_tour_dialog(self, w, cls_name: str) -> None:
        from PyQt6.QtCore import QTimer

        slug, hold_attr = self._DIALOG_TOUR[cls_name]
        if self.mode == "screenshots":
            self._maybe_capture(slug, w, lambda: self._safe_close(w))
        else:
            hold_ms = getattr(self, hold_attr)
            QTimer.singleShot(hold_ms, lambda: self._safe_close(w))

    def _maybe_capture_expansion_dialog(self) -> None:
        if self._expansion_shot_done or self._jobs_seen:
            return
        dlg = getattr(self.window, "_expand_dialog", None)
        if dlg is None:
            return
        self._expansion_shot_done = True
        try:
            self._grab_and_save("09-espansione-cartella", dlg)
        except Exception:
            log.exception("cattura del dialogo di espansione fallita")
            self.notable.append("salto: 09-espansione-cartella: cattura fallita")

    # Ruoli che identificano il popup "gia' scaricato" di
    # confirm_already_downloaded() (src/gui/link_panel.py): l'INSIEME dei tre
    # ButtonRole, non il testo — vedi POPUP INTENZIONALI nel Contratto.
    @staticmethod
    def _duplicate_popup_roles():
        from PyQt6.QtWidgets import QMessageBox
        return {
            QMessageBox.ButtonRole.AcceptRole,
            QMessageBox.ButtonRole.DestructiveRole,
            QMessageBox.ButtonRole.RejectRole,
        }

    def _handle_message_box(self, box) -> None:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QMessageBox

        roles = {box.buttonRole(b) for b in box.buttons()}
        if roles == self._duplicate_popup_roles():
            self._handle_duplicate_popup(box)
            return
        if (
            self._awaiting_expand_report
            and len(box.buttons()) == 1
            and box.icon() == QMessageBox.Icon.Information
        ):
            self._handle_expand_report_popup(box)
            return

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

    def _handle_expand_report_popup(self, box) -> None:
        """Popup "Cartelle Mega espanse" (QMessageBox.information in
        MainWindow._on_expansion_done): intenzionale, non un dialog ignoto —
        vedi POPUP INTENZIONALI nel Contratto. Fotografato solo alla PRIMA
        comparsa (08); ricompare (chiuso, non rifotografato) al ri-tentativo
        del passo 15, perche' la cartella viene rielencata da capo."""
        from PyQt6.QtCore import QTimer

        self._awaiting_expand_report = False
        self.log_event("expand_report_open", title=box.windowTitle())

        def close_and_log() -> None:
            self._safe_close(box)
            self.log_event("expand_report_close")

        if self.mode == "screenshots":
            if not self._expand_report_shot_done:
                self._expand_report_shot_done = True
                self._maybe_capture("08-popup-cartelle-espanse", box, close_and_log)
            else:
                self._settle_then(close_and_log)
        else:
            self._expand_report_shot_done = True
            QTimer.singleShot(self.FOLDER_EXPANDED_HOLD_MS, close_and_log)

    def _handle_duplicate_popup(self, box) -> None:
        """Popup "gia' scaricato" (confirm_already_downloaded): intenzionale
        — vedi POPUP INTENZIONALI nel Contratto. In modalita' "silent_anyway"
        (comparsa al paste del ri-tentativo) si clicca "Scarica comunque" in
        silenzio, senza fotografare, per non svuotare la lista prima
        dell'Avvia; in "skip_and_shoot" (comparsa vera, all'Avvia) si
        fotografa e si clicca "Salta gia' scaricati", poi si prosegue col
        passo Explorer — nessun job nuovo nascera' da attendere, essendo
        tutti i link filtrati come doppioni."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QMessageBox

        skip_btn = None
        anyway_btn = None
        for b in box.buttons():
            role = box.buttonRole(b)
            if role == QMessageBox.ButtonRole.AcceptRole:
                skip_btn = b
            elif role == QMessageBox.ButtonRole.DestructiveRole:
                anyway_btn = b

        if self._duplicate_popup_mode == "skip_and_shoot":
            self.log_event("duplicate_popup_open", title=box.windowTitle())
            target = skip_btn or anyway_btn
            first_shot = not self._duplicate_popup_shot_done
            self._duplicate_popup_shot_done = True

            def click_and_continue() -> None:
                self._safe_click(target)
                self.log_event("duplicate_popup_close")
                self._duplicate_popup_mode = None
                QTimer.singleShot(800, self._tour_explorer)

            if self.mode == "screenshots" and first_shot:
                self._maybe_capture("15-popup-gia-scaricato", box, click_and_continue)
            else:
                QTimer.singleShot(self.ALREADY_DOWNLOADED_HOLD_MS, click_and_continue)
        else:
            self.log_event("duplicate_popup_paste_stage", title=box.windowTitle())
            target = anyway_btn or skip_btn
            QTimer.singleShot(300, lambda: self._safe_click(target))

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

    @staticmethod
    def _safe_reject(dlg) -> None:
        try:
            dlg.cancel_btn.click()
        except Exception:
            try:
                dlg.reject()
            except Exception:
                pass

    # ---- cattura screenshot (solo modalita' screenshots) -----------------------

    def _maybe_capture(self, name: str, widget, then) -> None:
        """Punto d'attesa comune ai due modi: in screenshots fa il settling
        (SETTLE_MS) e salva il PNG; in video e' solo un respiro minimo prima
        di proseguire (il "hold" vero per la registrazione lo fanno i
        chiamanti con QTimer piu' lunghi attorno a questa chiamata, quando la
        tappa e' un menu/dialogo che deve restare visibilmente aperto)."""
        if self._finished:
            return
        from PyQt6.QtCore import QTimer

        if self.mode == "screenshots":
            QTimer.singleShot(self.SETTLE_MS, lambda: self._do_capture_then(name, widget, then))
        else:
            QTimer.singleShot(50, then)

    def _do_capture_then(self, name: str, widget, then) -> None:
        if self._finished:
            return
        try:
            self._grab_and_save(name, widget)
        except Exception:
            log.exception("cattura screenshot fallita per %s", name)
            self.notable.append(f"salto: {name}: cattura fallita")
        then()

    def _grab_and_save(self, name: str, target) -> None:
        from PyQt6.QtWidgets import QApplication

        hwnd = target if isinstance(target, int) else int(target.winId())
        screen = QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("nessuno schermo primario disponibile")
        pix = screen.grabWindow(hwnd)
        if pix.isNull():
            raise RuntimeError(f"grabWindow ha restituito una pixmap vuota per {name}")
        lang_dir = self.out_dir / "screens" / self.lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        out_path = lang_dir / f"{name}.png"
        if not pix.save(str(out_path), "PNG"):
            raise RuntimeError(f"salvataggio PNG fallito: {out_path}")
        self.screenshots.append(out_path.name)
        self.log_event("screenshot_saved", name=out_path.name)

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
        if not self._all_done_triggered:
            self.log_event("all_completed", skipped=True, reason=f"interrotto ({reason})")
        if not self._filter_shown:
            self.log_event("completed_filter_shown", skipped=True, reason=f"interrotto ({reason})")
        if not self._explorer_done:
            self.log_event("explorer_open", skipped=True, reason=f"interrotto ({reason})")
        if self.mode == "screenshots":
            if not self._expand_report_shot_done:
                self.notable.append(
                    "salto: 08-popup-cartelle-espanse: popup non mostrato prima dello stop"
                )
            if not self._duplicate_popup_shot_done:
                self.notable.append(
                    "salto: 15-popup-gia-scaricato: popup non mostrato prima dello stop"
                )

        self.log_event("recording_stop_requested", reason=reason)
        self._stop_ffmpeg()
        self._stop_explorer_ffmpeg()
        try:
            self.window.close()
        except Exception:
            log.exception("errore in window.close()")
        self.result["stop_reason"] = reason

        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        QTimer.singleShot(500, QApplication.instance().quit)

    def _stop_ffmpeg(self) -> None:
        proc = self.ffmpeg_proc
        if proc is None:
            return
        self.ffmpeg_proc = None
        try:
            if proc.stdin:
                proc.stdin.write(b"q")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.log_event("recording_stopped")

    def _stop_explorer_ffmpeg(self) -> None:
        proc = self.explorer_ffmpeg_proc
        if proc is None:
            return
        self.explorer_ffmpeg_proc = None
        try:
            if proc.stdin:
                proc.stdin.write(b"q")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # ---- log timeline ---------------------------------------------------------

    def log_event(self, event: str, **fields) -> None:
        t = round(time.monotonic() - self.t0, 2) if self.t0 is not None else 0.0
        rec = {"t": t, "event": event, "lang": self.lang, "mode": self.mode, **fields}
        self.timeline_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.timeline_fh.flush()


# ---------------------------------------------------------------------------
# Post-processing (solo modalita' video): taglio a velocita' variabile,
# con in coda l'eventuale segmento Explorer a schermo intero.
# ---------------------------------------------------------------------------

def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_variable_speed_cut(
    raw_path: Path, events: list[dict], out_path: Path, tmp_dir: Path,
    extra_segment_path: Path | None = None,
) -> dict:
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

    # Segmento Explorer (schermo intero, 1x): scalato/letterboxato al frame
    # size del resto del video cosi' la concatenazione con "-c copy" resta
    # valida (stesso codec/risoluzione/framerate/pixfmt di tutti gli altri
    # segmenti). Sempre in coda, mai finestrato: e' gia' breve di suo.
    if extra_segment_path is not None:
        extra_seg = tmp_dir / f"seg_{len(seg_files):04d}_explorer.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", str(extra_segment_path),
            "-vf",
            f"scale={WINDOW_W}:{WINDOW_H}:force_original_aspect_ratio=decrease,"
            f"pad={WINDOW_W}:{WINDOW_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FFMPEG_FRAMERATE}",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            str(extra_seg),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        seg_files.append(extra_seg)

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


# ---------------------------------------------------------------------------
# Output: index.html, README.md, report testuale — costruiti dal manifest
# (unione dell'ultimo risultato OK per ogni (modalita', lingua), non solo
# dal risultato del giro appena fatto: vedi la sezione Manifest sopra).
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def build_index_html(out_dir: Path, manifest: dict) -> None:
    video = manifest.get("video", {})
    screenshots = manifest.get("screenshots", {})
    video_langs = [l for l in ("it", "en") if video.get(l, {}).get("ok")]
    shot_langs = [l for l in ("it", "en") if screenshots.get(l, {}).get("ok")]

    video_cols = "\n".join(
        f'''<div class="col">
      <h2>{l.upper()}</h2>
      <video controls preload="metadata" src="videos/demo-{l}.mp4"></video>
      <p class="meta">Durata: {video[l]["cut_duration_s"]:.0f}s (raw: {video[l]["raw_duration_s"]:.0f}s) — {video[l]["segments"]} segmenti</p>
    </div>'''
        for l in video_langs
    ) or "<p>Nessun video disponibile (esegui <code>--mode video</code>).</p>"

    shot_names: list[str] = []
    seen: set[str] = set()
    for l in shot_langs:
        for name in screenshots[l].get("screenshots", []):
            if name not in seen:
                seen.add(name)
                shot_names.append(name)
    shot_names.sort()

    shot_rows = []
    for name in shot_names:
        cells = []
        for l in shot_langs:
            if name in screenshots[l].get("screenshots", []):
                cells.append(f'<img src="screens/{l}/{name}" alt="{_esc(name)} ({l})" loading="lazy">')
            else:
                cells.append('<div class="missing">—</div>')
        label = name.rsplit(".", 1)[0]
        shot_rows.append(
            f'<div class="still-row"><div class="still-label">{_esc(label)}</div>'
            + "".join(f'<div class="still-cell">{c}</div>' for c in cells)
            + "</div>",
        )

    raw_links = "\n".join(
        f'<li><a href="videos/raw-{l}.mp4">raw-{l}.mp4</a> ({video[l]["raw_duration_s"]:.0f}s)</li>'
        for l in video_langs
    ) or "<li>Nessuno.</li>"

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
  .still-row {{ display:grid; grid-template-columns: 220px repeat({max(len(shot_langs), 1)}, 1fr); gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--border); }}
  .still-label {{ color:var(--muted); font-size:0.85rem; }}
  .still-cell img {{ width:100%; border-radius:6px; border:1px solid var(--border); display:block; }}
  .missing {{ color:var(--muted); font-size:0.8rem; }}
  ul {{ color:var(--text); }}
  a {{ color:var(--accent); }}
</style>
<h1>MDPR — Demo bilingue (download reali)</h1>
<p class="sub">Generato da <code>demo_runner.py</code>. Video "belli" a velocita' variabile in alto,
galleria di screenshot puliti sotto (catturati a stato fermo, non estratti dal video).</p>

<div class="videos">
{video_cols}
</div>

<h2 class="section">Screenshot (stato fermo)</h2>
<div class="stills">
{"".join(shot_rows) if shot_rows else '<p>Nessuno screenshot disponibile (esegui <code>--mode screenshots</code>).</p>'}
</div>

<h2 class="section">Grezzi (archivio)</h2>
<ul>
{raw_links}
</ul>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def write_readme(out_dir: Path, args, manifest: dict) -> None:
    content = f"""# MDPR — Demo runner (video + galleria di screenshot bilingue)

Materiale generato da `demo_runner.py`: due modalita' separate, entrambe basate su un giro
REALE del tool (download COMPLETI veri, niente stub/fake).

- **`--mode video`**: due video reali del tool (IT/EN), un taglio "bello" a velocita' variabile
  e le registrazioni grezze.
- **`--mode screenshots`**: una galleria di foto a STATO FERMO (settling + cattura, non frame
  estratti da un video: niente sfocatura da movimento o transizioni a meta').
- **`--mode both`**: esegue prima tutti i pass screenshots, poi tutti i pass video.

Entrambe le modalita' pilotano un tour completo dei 5 punti della barra comandi (Impostazioni,
Sperimentale, Aggiungi link, Tema, Info), poi aggiungono i due link Mega veri, avviano il
download (compare il popup "Cartelle Mega espanse", momento intenzionale del tour), aprono il
dettaglio del primo job che supera il 10%, attendono il completamento reale di tutti i job,
applicano il filtro "Completati", ri-incollano gli STESSI due link e cliccano di nuovo Avvia per
mostrare la funzione anti-duplicati (popup "Links already downloaded", chiuso senza riscaricare)
e infine aprono Esplora risorse con il file scaricato in evidenza.

## Cosa contiene

- `videos/raw-it.mp4`, `videos/raw-en.mp4` — registrazioni grezze (durata reale, modalita' video).
- `videos/demo-it.mp4`, `videos/demo-en.mp4` — tagli "belli" a velocita' variabile (~5-8 min),
  col segmento Explorer finale a schermo intero incollato in coda.
- `screens/it/`, `screens/en/` — screenshot numerati a stato fermo (modalita' screenshots).
- `timelines/timeline-video-it.jsonl`, `timeline-video-en.jsonl`,
  `timelines/timeline-screens-it.jsonl`, `timeline-screens-en.jsonl` — log eventi per pass.
- `last-results.json` — manifest interno del runner (ultimo risultato OK per modalita'/lingua):
  permette a un giro `--mode screenshots` di non far sparire la sezione video di un giro
  precedente in `index.html`, e viceversa.
- `index.html` — galleria statica auto-contenuta (apri a doppio clic).

Lo script che genera tutto questo, `demo_runner.py`, vive altrove — e' un
file TRACCIATO del progetto: `tools/demo/demo_runner.py`. Vedi anche
`.claude/rules/demo-runner.md` per la regola che lo tiene allineato al
codice della GUI.

## Come rilanciarlo (prossima release)

```
python tools/demo/demo_runner.py --mode video       --lang both
python tools/demo/demo_runner.py --mode screenshots --lang both
python tools/demo/demo_runner.py --mode both        --lang both
```

Di default usa i due link qui sotto. Per cambiarli:

```
python tools/demo/demo_runner.py --mode both --lang both \\
  --folder-link <url cartella Mega> \\
  --file-link <url file singolo Mega> \\
  --safety-cap-minutes 90
```

Prima di un giro lungo, `python tools/demo/demo_runner.py --dry-run` verifica
in meno di 5 secondi che il runner sia ancora allineato al codice del tool
(import, slot, chiavi i18n, per ENTRAMBE le modalita') senza scaricare o
registrare nulla.

Un giro completo (IT+EN) dura 20-90+ minuti reali per modalita' (dipende dai proxy gratuiti
disponibili al momento): il runner scarica per davvero fino al completamento di tutti i job,
non accelera nulla durante il giro — la velocita' variabile (modalita' video) e' SOLO nel
taglio finale, in post-produzione.

## Se qualcosa va storto

- **ffmpeg non installato**: serve solo per `--mode video`/`both`. `winget install ffmpeg`
  (o `choco install ffmpeg -y`), poi rilancia.
- **La finestra non viene agganciata da ffmpeg (gdigrab)**: gdigrab risolve il titolo UNA
  volta all'apertura dello stream e poi cattura sempre la stessa finestra (handle), anche se
  il titolo cambia dopo — nella pratica qui il titolo di MDPR resta comunque stabile durante
  una sessione (non include contatori dinamici). Se il tool viene rinominato/il titolo cambia
  radicalmente, aggiorna la logica di aggancio in `DemoDriver._start_ffmpeg`.
- **Uno screenshot manca dalla galleria**: la modalita' screenshots salta (con nota nel
  report) le tappe non catturabili invece di fermare l'intero giro — es. l'espansione di una
  cartella troppo veloce da fotografare, o un popup che non si presta alla cattura. Controlla
  `run-report.md` per l'elenco dei salti.
- **Una lingua viene troncata dal safety cap** (`--safety-cap-minutes`, default 90): non e' un
  errore, e' un dato reale (pool proxy debole al momento del giro). Il runner chiude comunque
  i job in corso e ferma la registrazione/cattura; il report finale lo segnala.
- **Il pool proxy e' scarso**: molte attese/retry — fa parte del punto (mostrare come il tool
  reagisce). Se in 10 minuti reali non parte NESSUN download, e' il caso di controllare i
  proxy prima di rilanciare.
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
- Screenshot: `QScreen.grabWindow(hwnd)` sul HWND della finestra bersaglio (finestra principale,
  dialogo modale, o — per il passo Explorer — la finestra in primo piano rilevata via
  `ctypes`/`GetForegroundWindow`), con un settling di 500ms dopo l'azione prima di catturare.
- Video, segmento Explorer: registrazione a schermo intero separata (`gdigrab -i desktop`,
  ~9s), poi scalata/letterboxata alla risoluzione del resto del video e incollata in coda nel
  taglio finale, cosi' la concatenazione resta valida (stesso codec/risoluzione/framerate).
- Cartella download di test isolata: `MyDocs/gallery/downloads/` (svuotata a inizio E fine di
  OGNI pass, cosi' ogni pass riparte da un download reale e non da un file gia' completo).
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


def write_report(out_dir: Path, manifest: dict) -> None:
    lines = ["# Report giro demo", ""]
    for mode in ("screenshots", "video"):
        results = manifest.get(mode, {})
        if not results:
            continue
        lines.append(f"## Modalita': {mode}")
        for lang, r in results.items():
            lines.append(f"### {lang}")
            lines.append(f"- ok: {r.get('ok')}")
            lines.append(f"- stop_reason: {r.get('stop_reason')}")
            if mode == "video":
                lines.append(f"- raw_duration_s: {r.get('raw_duration_s')}")
                lines.append(f"- cut_duration_s: {r.get('cut_duration_s')}")
                lines.append(f"- segments: {r.get('segments')}")
                lines.append(f"- explorer_segment_included: {r.get('explorer_segment_included')}")
            else:
                lines.append(f"- screenshots: {len(r.get('screenshots', []))}")
            if r.get("error"):
                lines.append(f"- error: {r.get('error')}")
            for note in r.get("notable", []) or []:
                lines.append(f"- NOTABILE: {note}")
            lines.append("")
    (out_dir / "run-report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
