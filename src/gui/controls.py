# Barra comandi: Avvia, Pausa/Riprendi, Annulla, Impostazioni (popup),
# Sperimentale (dialog separato), Aggiungi link, toggle tema, Info.
# Le opzioni di configurazione (paralleli, limite, pezzo, cartella di download,
# riduzione a icona, lingua) sono raggruppate in un QMenu+QWidgetAction
# persistente, accessibile dal pulsante Impostazioni.
# I widget sottostanti (concurrency_combo, time_limit_spin, chunk_size_combo)
# restano attributi della classe: getter e segnali sono invariati.
# Il pulsante Sperimentale apre ExperimentalFeaturesDialog (gui/experimental_dialog.py),
# una superficie isolata per le leve in prova: non ne ospita i widget qui.
#
# i18n: nessun testo utente hard-coded qui dentro. I testi si leggono con
# `t("controls.*")` e `retranslate()` li riesegue al cambio di lingua (e' il
# gemello di `refresh_theme()` per il tema). Vedi gui/i18n.py.
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QStyle,
    QWidget,
    QWidgetAction,
)

from src.core.config import (
    MAX_CONCURRENT_DOWNLOADS,
    MAX_FILE_DURATION_MINUTES,
    OUTPUT_DIR,
    PARALLEL_CHUNK_SIZE_MB,
)
from src.gui.i18n import TR, t

# Spaziatura fra icona e testo dei pulsanti che hanno un'icona: e' impaginazione,
# non testo, quindi resta nel codice e non nei dizionari (nessuna lingua puo'
# dimenticarsela).
_ICON_PAD = "  "


class ControlsBar(QWidget):
    start_requested = pyqtSignal()
    pause_toggled = pyqtSignal(bool)    # True = pausa, False = riprendi
    cancel_requested = pyqtSignal()
    concurrency_changed = pyqtSignal(int)
    paste_links_requested = pyqtSignal()
    theme_toggled = pyqtSignal(bool)    # True = tema scuro
    info_requested = pyqtSignal()
    experimental_requested = pyqtSignal()
    download_dir_changed = pyqtSignal(str)  # "" = torna al default
    minimize_ask_requested = pyqtSignal()   # rimetti la domanda alla riduzione
    maintenance_requested = pyqtSignal()     # apri la finestra Manutenzione

    def __init__(self) -> None:
        super().__init__()
        self._paused = False
        self._dark = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Avvia (primario).
        self.start_btn = QPushButton()
        self.start_btn.setProperty("primary", "true")
        play_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.start_btn.setIcon(play_icon)
        self.start_btn.clicked.connect(self.start_requested)
        layout.addWidget(self.start_btn)

        # Pausa / Riprendi.
        self.pause_btn = QPushButton()
        pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.pause_btn.setIcon(pause_icon)
        self.pause_btn.clicked.connect(self._on_pause)
        layout.addWidget(self.pause_btn)

        # Annulla (distruttivo rosso).
        self.cancel_btn = QPushButton()
        self.cancel_btn.setProperty("danger", "true")
        cancel_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        self.cancel_btn.setIcon(cancel_icon)
        self.cancel_btn.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel_btn)

        layout.addStretch(1)

        # --- Controlli di configurazione (ospitati nel popup, non in barra). ---

        self.concurrency_combo = QComboBox()
        for v in range(1, 6):
            self.concurrency_combo.addItem(str(v), v)
        idx = self.concurrency_combo.findData(MAX_CONCURRENT_DOWNLOADS)
        if idx >= 0:
            self.concurrency_combo.setCurrentIndex(idx)
        self.concurrency_combo.currentIndexChanged.connect(
            lambda: self.concurrency_changed.emit(self.get_concurrency())
        )
        self.concurrency_combo.setFixedWidth(54)

        self.time_limit_spin = QSpinBox()
        self.time_limit_spin.setRange(1, 600)
        self.time_limit_spin.setValue(MAX_FILE_DURATION_MINUTES)
        self.time_limit_spin.setFixedWidth(64)

        self.chunk_size_combo = QComboBox()
        # Tagli grandi (128/256 MB) per file molto grandi su proxy buoni: con
        # proxy lenti il watchdog per-segmento (PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S
        # = 180s, soglia 200 KB/s) può abortire il tentativo prima che il pezzo
        # finisca, e un proxy che muore a metà pezzo spreca più byte. Restano
        # opzioni a disposizione dell'utente; il default 32 MB non cambia.
        # L'unità di misura non si traduce: le voci restano "N MB".
        for mb in (4, 8, 16, 32, 64, 128, 256):
            self.chunk_size_combo.addItem(f"{mb} MB", mb * 1024 * 1024)
        idx = self.chunk_size_combo.findData(PARALLEL_CHUNK_SIZE_MB * 1024 * 1024)
        if idx >= 0:
            self.chunk_size_combo.setCurrentIndex(idx)
        self.chunk_size_combo.setFixedWidth(84)

        # Cartella di download: "" = default (downloads/ del programma). Il
        # bottone mostra il nome della cartella scelta e apre un selettore.
        self._download_dir: str = ""
        self.download_dir_btn = QPushButton()
        self.download_dir_btn.clicked.connect(self._choose_download_dir)
        self.download_dir_btn.setMinimumWidth(150)

        # Riduzione a icona: dove va la finestra quando la si riduce. Qui c'e'
        # solo la via per RIMETTERE la domanda ("chiedi ogni volta"): la scelta
        # vera si fa nel momento della riduzione, dove l'utente ha il contesto.
        # Il valore corrente arriva da MainWindow (set_minimize_target), come
        # per la cartella di download: i pannelli non leggono le preferenze.
        self._minimize_target = "ask"
        self.minimize_reset_btn = QPushButton()
        self.minimize_reset_btn.clicked.connect(self._on_minimize_reset)
        self.minimize_reset_btn.setMinimumWidth(150)

        # Lingua dell'interfaccia: "Automatica (<lingua rilevata>)" / Italiano /
        # English. Il dato di ogni voce è la PREFERENZA ('auto'|'it'|'en'), non
        # la lingua effettiva: 'auto' deve restare revocabile.
        self.language_combo = QComboBox()
        for _pref in ("auto", "it", "en"):
            self.language_combo.addItem("", _pref)
        self.language_combo.setMinimumWidth(150)
        self.language_combo.currentIndexChanged.connect(self._on_language_selected)

        # Manutenzione: apre la finestra che azzera storico, stato di sessione,
        # cartella dei download, log e cache dei proxy. Qui c'e' solo la porta:
        # l'elenco di cio' che sparisce e le conferme stanno nella finestra
        # (gui/maintenance_dialog.py), che e' l'unico posto in cui si cancella.
        self.maintenance_btn = QPushButton()
        self.maintenance_btn.clicked.connect(self._on_maintenance)
        self.maintenance_btn.setMinimumWidth(150)

        # Pulsante Impostazioni: apre il popup con i controlli.
        self._settings_btn = QPushButton()
        self._settings_btn.clicked.connect(self._show_settings_menu)
        layout.addWidget(self._settings_btn)

        # Popup persistente con QWidgetAction: creato UNA sola volta.
        # I widget (combo, spin) sono figli del container row, che è figlio
        # dell'action, che è figlio del menu, che è figlio di ControlsBar.
        # Durata di vita = durata di ControlsBar.
        self._settings_menu = QMenu(self)
        # Le etichette restano raggiungibili per chiave: retranslate() le
        # riscrive senza ricostruire il menu.
        self._settings_labels: dict[str, QLabel] = {}
        _lbl_w = 126  # larghezza etichetta allineata
        for _row_key, _row_widget in (
            ("controls.row_concurrency", self.concurrency_combo),
            ("controls.row_time_limit", self.time_limit_spin),
            ("controls.row_chunk", self.chunk_size_combo),
            ("controls.row_download_dir", self.download_dir_btn),
            ("controls.row_minimize", self.minimize_reset_btn),
            ("controls.row_language", self.language_combo),
            ("controls.row_maintenance", self.maintenance_btn),
        ):
            _container = QWidget()
            _hl = QHBoxLayout(_container)
            _hl.setContentsMargins(12, 6, 12, 6)
            _hl.setSpacing(10)
            _lbl = QLabel()
            _lbl.setFixedWidth(_lbl_w)
            _hl.addWidget(_lbl)
            _hl.addWidget(_row_widget)
            self._settings_labels[_row_key] = _lbl
            _wa = QWidgetAction(self._settings_menu)
            _wa.setDefaultWidget(_container)
            self._settings_menu.addAction(_wa)

        # Funzioni Sperimentali: superficie separata da Impostazioni, apre un
        # dialog proprio (vedi gui/experimental_dialog.py). Bloccato durante
        # una sessione attiva, come Impostazioni.
        self._experimental_btn = QPushButton()
        self._experimental_btn.clicked.connect(self.experimental_requested)
        layout.addWidget(self._experimental_btn)

        # Aggiungi link — sempre visibile.
        self.paste_btn = QPushButton()
        paste_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.paste_btn.setIcon(paste_icon)
        self.paste_btn.clicked.connect(self.paste_links_requested)
        layout.addWidget(self.paste_btn)

        # Toggle tema chiaro/scuro.
        self.theme_btn = QPushButton()
        self.theme_btn.setFixedWidth(36)
        self.theme_btn.clicked.connect(self._on_theme_toggle)
        layout.addWidget(self.theme_btn)

        # Info — pulsante autonomo, sempre accessibile (non dentro Impostazioni).
        self.info_btn = QPushButton()
        self.info_btn.clicked.connect(self.info_requested)
        layout.addWidget(self.info_btn)

        # Tutti i testi in un colpo solo: la stessa chiamata che il cambio di
        # lingua rieseguirà a caldo.
        self.retranslate()

        # Stato iniziale: solo Avvia e Impostazioni attivi.
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

    # ---- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive ogni testo utente della barra nella lingua corrente.

        Chiamato dal costruttore e da MainWindow._on_language_changed: e'
        l'elenco dei setText/setToolTip, non ricostruisce widget (i riferimenti
        e lo stato — pausa, tema, cartella scelta — restano quelli)."""
        self.start_btn.setText(_ICON_PAD + t("controls.start"))
        self.cancel_btn.setText(_ICON_PAD + t("controls.cancel"))
        self.paste_btn.setText(_ICON_PAD + t("controls.paste_links"))
        self._settings_btn.setText("⚙  " + t("controls.settings"))        # ⚙
        self._experimental_btn.setText("\U0001f9ea  " + t("controls.experimental"))  # 🧪
        self.info_btn.setText("ℹ️  " + t("controls.info"))           # ℹ️

        self.concurrency_combo.setToolTip(t("controls.concurrency_tooltip"))
        self.time_limit_spin.setToolTip(t("controls.time_limit_tooltip"))
        self.chunk_size_combo.setToolTip(t("controls.chunk_size_tooltip"))
        self._settings_btn.setToolTip(t("controls.settings_tooltip"))
        self._experimental_btn.setToolTip(t("controls.experimental_tooltip"))
        self.language_combo.setToolTip(t("controls.language_tooltip"))
        self.maintenance_btn.setText(t("controls.maintenance_button"))
        self.maintenance_btn.setToolTip(t("controls.maintenance_tooltip"))

        for _key, _lbl in self._settings_labels.items():
            _lbl.setText(t(_key))

        # Testi che dipendono dallo stato corrente.
        self._refresh_pause_button()
        self._refresh_theme_button()
        self._refresh_download_dir_button()
        self._refresh_minimize_button()
        self._refresh_language_combo()

    def _refresh_language_combo(self) -> None:
        """Riallinea etichette e voce selezionata del selettore di lingua.

        I nomi delle lingue restano nella lingua stessa; solo "Automatica" e
        la sua parentesi con la lingua rilevata seguono la lingua corrente.
        `blockSignals` evita il rientro: riscrivere il combo non deve valere
        come una scelta dell'utente."""
        blocked = self.language_combo.blockSignals(True)
        try:
            detected = t(f"controls.language_{TR.detected_language()}")
            self.language_combo.setItemText(
                0, t("controls.language_auto_detected", lang=detected)
            )
            self.language_combo.setItemText(1, t("controls.language_it"))
            self.language_combo.setItemText(2, t("controls.language_en"))
            idx = self.language_combo.findData(TR.preference())
            if idx >= 0:
                self.language_combo.setCurrentIndex(idx)
        finally:
            self.language_combo.blockSignals(blocked)

    def _on_language_selected(self) -> None:
        # La ritraduzione non parte da qui: TR emette language_changed e la
        # MainWindow fa il fan-out sui pannelli (come per il tema).
        TR.set_preference(str(self.language_combo.currentData() or "auto"))

    # ---- comandi -----------------------------------------------------------

    def _show_settings_menu(self) -> None:
        pos = self._settings_btn.mapToGlobal(
            self._settings_btn.rect().bottomLeft()
        )
        self._settings_menu.exec(pos)

    def _choose_download_dir(self) -> None:
        # Chiudo il popup prima di aprire il dialog modale (evita event loop
        # annidati sul menu). Un percorso vuoto = l'utente ha annullato.
        self._settings_menu.close()
        start_dir = self._download_dir or str(OUTPUT_DIR)
        chosen = QFileDialog.getExistingDirectory(
            self, t("controls.choose_download_dir_title"), start_dir
        )
        if chosen:
            self.set_download_dir(chosen)
            self.download_dir_changed.emit(chosen)

    def set_download_dir(self, path: str) -> None:
        """Imposta la cartella di download mostrata (senza emettere il segnale).
        `path` vuoto = default. Solo il nome finale è mostrato sul bottone."""
        self._download_dir = path or ""
        self._refresh_download_dir_button()

    def _refresh_download_dir_button(self) -> None:
        if self._download_dir:
            name = Path(self._download_dir).name or self._download_dir
            self.download_dir_btn.setText(name)
            self.download_dir_btn.setToolTip(
                t("controls.download_dir_tooltip_chosen", path=self._download_dir)
            )
        else:
            self.download_dir_btn.setText(t("controls.download_dir_default"))
            self.download_dir_btn.setToolTip(t("controls.download_dir_tooltip_default"))

    def get_download_dir(self) -> str:
        """Cartella di download scelta ("" = usa il default)."""
        return self._download_dir

    # ---- riduzione a icona -------------------------------------------------

    def set_minimize_target(self, value: str) -> None:
        """Destinazione corrente della riduzione a icona ("ask"/"tray"/
        "taskbar"), senza emettere il segnale: serve solo a scrivere il
        suggerimento e ad accendere il pulsante quando c'e' qualcosa da
        annullare."""
        self._minimize_target = str(value or "ask")
        self._refresh_minimize_button()

    def get_minimize_target(self) -> str:
        return self._minimize_target

    def _refresh_minimize_button(self) -> None:
        self.minimize_reset_btn.setText(t("controls.minimize_reset"))
        key = {
            "tray": "controls.minimize_tooltip_tray",
            "taskbar": "controls.minimize_tooltip_taskbar",
        }.get(self._minimize_target, "controls.minimize_tooltip_ask")
        self.minimize_reset_btn.setToolTip(t(key))
        # Con la domanda gia' attiva non c'e' niente da ripristinare: il
        # pulsante spento dice da solo qual e' lo stato corrente.
        self.minimize_reset_btn.setEnabled(self._minimize_target != "ask")

    def _on_minimize_reset(self) -> None:
        # Il popup si chiude prima: la finestra chiamante scrive la riga di
        # stato, e un menu aperto sopra la nasconderebbe.
        self._settings_menu.close()
        self.minimize_ask_requested.emit()

    # ---- manutenzione ------------------------------------------------------

    def _on_maintenance(self) -> None:
        # Come per la cartella di download: il popup si chiude PRIMA di aprire
        # una finestra modale, altrimenti si annidano due cicli di eventi sul
        # menu.
        self._settings_menu.close()
        self.maintenance_requested.emit()

    def _on_pause(self) -> None:
        self._paused = not self._paused
        self._refresh_pause_button()
        self.pause_toggled.emit(self._paused)

    def _refresh_pause_button(self) -> None:
        if self._paused:
            self.pause_btn.setText(_ICON_PAD + t("controls.resume"))
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        else:
            self.pause_btn.setText(_ICON_PAD + t("controls.pause"))
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.pause_btn.setIcon(icon)

    def _on_theme_toggle(self) -> None:
        self._dark = not self._dark
        self._refresh_theme_button()
        self.theme_toggled.emit(self._dark)

    def _refresh_theme_button(self) -> None:
        self.theme_btn.setText("☀️" if self._dark else "\U0001f319")  # ☀️ / 🌙
        self.theme_btn.setToolTip(
            t("controls.theme_tooltip_to_light")
            if self._dark
            else t("controls.theme_tooltip_to_dark")
        )

    def reset(self) -> None:
        self._paused = False
        self._refresh_pause_button()
        self.set_running(False)

    def set_start_enabled(self, enabled: bool) -> None:
        """Abilita/disabilita il solo Avvia, senza toccare gli altri comandi.

        Serve alle fasi pre-sessione che fanno rete (espansione dei link
        cartella): la sessione non e' ancora partita, quindi set_running(True)
        darebbe uno stato mentito (Pausa/Annulla attivi su nulla).
        """
        self.start_btn.setEnabled(enabled)

    def set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        # Il pulsante Impostazioni blocca l'accesso al popup durante la sessione:
        # i controlli all'interno non possono essere modificati a download attivo.
        self._settings_btn.setEnabled(not running)
        self._experimental_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.cancel_btn.setEnabled(running)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._refresh_theme_button()

    def get_concurrency(self) -> int:
        return int(self.concurrency_combo.currentData() or 1)

    def get_file_time_limit_s(self) -> int:
        """Ritorna il limite di durata per file in secondi."""
        return self.time_limit_spin.value() * 60

    def get_chunk_size_bytes(self) -> int:
        """Ritorna la dimensione del chunk in byte (scelta dalla GUI)."""
        return int(self.chunk_size_combo.currentData() or PARALLEL_CHUNK_SIZE_MB * 1024 * 1024)
