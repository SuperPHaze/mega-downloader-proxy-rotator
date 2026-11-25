# Comandi della coda e finestra delle impostazioni.
from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.config import (
    MAX_CONCURRENT_DOWNLOADS,
    MAX_FILE_DURATION_MINUTES,
    OUTPUT_DIR,
    PARALLEL_CHUNK_SIZE_MB,
)
from src.gui.i18n import TR, t

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
        self._running = False
        self._start_allowed = True
        self._link_count = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._heading = QLabel()
        self._heading.setObjectName("pageTitle")
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(self._heading)
        self._destination = QLabel()
        self._destination.setObjectName("secondaryText")
        self._destination.setTextFormat(Qt.TextFormat.PlainText)
        self._destination.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        heading.addWidget(self._destination)
        layout.addLayout(heading, 1)

        self.paste_btn = QPushButton()
        self.paste_btn.setProperty("primary", "true")
        self.paste_btn.clicked.connect(self.paste_links_requested)
        self.paste_btn.hide()  # nella coda vuota lo stesso comando è al centro
        layout.addWidget(self.paste_btn)

        # Avvia (primario).
        self.start_btn = QPushButton()
        self.start_btn.setProperty("primary", "true")
        self.start_btn.clicked.connect(self.start_requested)
        layout.addWidget(self.start_btn)

        # Pausa / Riprendi.
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self._on_pause)
        layout.addWidget(self.pause_btn)

        # Annulla (distruttivo rosso).
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("cancelQueue")
        self.cancel_btn.setProperty("danger", "true")
        self.cancel_btn.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel_btn)

        # Controlli di configurazione, condivisi fra le sessioni.

        self.concurrency_combo = QComboBox()
        for v in range(1, 6):
            self.concurrency_combo.addItem(str(v), v)
        idx = self.concurrency_combo.findData(MAX_CONCURRENT_DOWNLOADS)
        if idx >= 0:
            self.concurrency_combo.setCurrentIndex(idx)
        self.concurrency_combo.currentIndexChanged.connect(
            lambda: self.concurrency_changed.emit(self.get_concurrency())
        )

        self.time_limit_spin = QSpinBox()
        self.time_limit_spin.setRange(1, 600)
        self.time_limit_spin.setValue(MAX_FILE_DURATION_MINUTES)

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

        self.settings_btn = QPushButton(self)
        self.settings_btn.setObjectName("settingsButton")
        self.settings_btn.clicked.connect(self.show_settings)
        layout.addWidget(self.settings_btn)
        self._settings_dialog = QDialog(self)
        self._settings_dialog.setMinimumWidth(420)
        settings = QVBoxLayout(self._settings_dialog)
        settings.setContentsMargins(18, 18, 18, 16)
        settings.setSpacing(12)
        self._download_group = QGroupBox()
        self._app_group = QGroupBox()
        settings.addWidget(self._download_group)
        settings.addWidget(self._app_group)
        self._settings_labels: dict[str, QLabel] = {}
        downloads = QFormLayout(self._download_group)
        application = QFormLayout(self._app_group)
        for form in (downloads, application):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(9)
        self.theme_btn = QPushButton()
        self.theme_btn.clicked.connect(self._on_theme_toggle)
        for form, key, widget in (
            (downloads, "controls.row_concurrency", self.concurrency_combo),
            (downloads, "controls.row_time_limit", self.time_limit_spin),
            (downloads, "controls.row_chunk", self.chunk_size_combo),
            (downloads, "controls.row_download_dir", self.download_dir_btn),
            (application, "controls.row_language", self.language_combo),
            (application, "controls.row_theme", self.theme_btn),
            (application, "controls.row_minimize", self.minimize_reset_btn),
            (application, "controls.row_maintenance", self.maintenance_btn),
        ):
            label = QLabel()
            label.setBuddy(widget)
            form.addRow(label, widget)
            self._settings_labels[key] = label

        self.allow_duplicates = QCheckBox()
        downloads.addRow(self.allow_duplicates)
        self._experimental_btn = QPushButton()
        self._experimental_btn.clicked.connect(self._settings_dialog.accept)
        self._experimental_btn.clicked.connect(self.experimental_requested)
        downloads.addRow(self._experimental_btn)
        footer = QHBoxLayout()
        self.info_btn = QPushButton()
        self.info_btn.clicked.connect(self._settings_dialog.accept)
        self.info_btn.clicked.connect(self.info_requested)
        footer.addWidget(self.info_btn)
        footer.addStretch()
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._buttons.rejected.connect(self._settings_dialog.reject)
        footer.addWidget(self._buttons)
        settings.addLayout(footer)

        # Tutti i testi in un colpo solo: la stessa chiamata che il cambio di
        # lingua rieseguirà a caldo.
        self.retranslate()

        self.set_running(False)

    # ---- i18n --------------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive ogni testo utente della barra nella lingua corrente.

        Chiamato dal costruttore e da MainWindow._on_language_changed: e'
        l'elenco dei setText/setToolTip, non ricostruisce widget (i riferimenti
        e lo stato — pausa, tema, cartella scelta — restano quelli)."""
        self._heading.setText(t("workspace.queue_title"))
        self.start_btn.setText(t("controls.start"))
        self.cancel_btn.setText(t("controls.cancel"))
        self.paste_btn.setText(t("controls.paste_links"))
        self.settings_btn.setText(t("controls.settings"))
        self._settings_dialog.setWindowTitle(t("controls.settings"))
        self.allow_duplicates.setText(t("link_panel.allow_duplicates"))
        self.allow_duplicates.setToolTip(t("link_panel.allow_duplicates_tooltip"))
        self._download_group.setTitle(t("workspace.transfers"))
        self._app_group.setTitle(t("controls.application"))
        self._experimental_btn.setText(t("controls.experimental"))
        self.info_btn.setText(t("controls.info"))
        self._buttons.button(QDialogButtonBox.StandardButton.Close).setText(t("job_detail.close"))

        self.concurrency_combo.setToolTip(t("controls.concurrency_tooltip"))
        self.time_limit_spin.setToolTip(t("controls.time_limit_tooltip"))
        self.chunk_size_combo.setToolTip(t("controls.chunk_size_tooltip"))
        self.settings_btn.setToolTip(t("controls.settings_tooltip"))
        self._experimental_btn.setToolTip(t("controls.experimental_tooltip"))
        self.language_combo.setToolTip(t("controls.language_tooltip"))
        self.maintenance_btn.setText(t("controls.maintenance_button"))
        self.maintenance_btn.setToolTip(t("controls.maintenance_tooltip"))

        for _key, _lbl in self._settings_labels.items():
            _lbl.setText(t(_key))
        label_width = max(label.sizeHint().width() for label in self._settings_labels.values())
        for label in self._settings_labels.values():
            label.setFixedWidth(label_width)

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

    def show_settings(self) -> None:
        self._settings_dialog.exec()

    def _foreign_download_dir(self) -> bool:
        path = self._download_dir
        return bool(path and not Path(path).is_absolute() and (
            PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute()
        ))

    def ensure_local_download_dir(self) -> bool:
        if not self._foreign_download_dir():
            return True
        self._choose_download_dir()
        return bool(self._download_dir and not self._foreign_download_dir())

    def _choose_download_dir(self) -> None:
        if self._foreign_download_dir():
            title = t("controls.choose_local_download_dir")
            start_dir = str(OUTPUT_DIR.parent)
        else:
            title = t("controls.choose_download_dir_title")
            start_dir = self._download_dir or str(OUTPUT_DIR)
        parent = self._settings_dialog if self._settings_dialog.isVisible() else self.window()
        chosen = QFileDialog.getExistingDirectory(parent, title, start_dir)
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
            # Una preferenza copiata da Windows può contenere una lettera di
            # unità o un percorso UNC anche sul Mac. La scelta resta intatta.
            path = Path(self._download_dir)
            if PureWindowsPath(self._download_dir).drive:
                path = PureWindowsPath(self._download_dir)
            name = path.name or self._download_dir
            self.download_dir_btn.setText(name)
            self.download_dir_btn.setToolTip(
                t("controls.download_dir_tooltip_chosen", path=self._download_dir)
            )
        else:
            name = OUTPUT_DIR.name
            self.download_dir_btn.setText(t("controls.download_dir_default"))
            self.download_dir_btn.setToolTip(t("controls.download_dir_tooltip_default"))

        self._destination.setText(t("workspace.destination", folder=name))
        self._destination.setToolTip(self._download_dir or str(OUTPUT_DIR))

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
        if sys.platform == "darwin":
            key += "_mac"
        self.minimize_reset_btn.setToolTip(t(key))
        # Con la domanda gia' attiva non c'e' niente da ripristinare: il
        # pulsante spento dice da solo qual e' lo stato corrente.
        self.minimize_reset_btn.setEnabled(self._minimize_target != "ask")

    def _on_minimize_reset(self) -> None:
        # Il popup si chiude prima: la finestra chiamante scrive la riga di
        # stato, e un menu aperto sopra la nasconderebbe.
        self.minimize_ask_requested.emit()

    # ---- manutenzione ------------------------------------------------------

    def _on_maintenance(self) -> None:
        # Come per la cartella di download: il popup si chiude PRIMA di aprire
        # una finestra modale, altrimenti si annidano due cicli di eventi sul
        # menu.
        self._settings_dialog.accept()
        self.maintenance_requested.emit()

    def _on_pause(self) -> None:
        self._paused = not self._paused
        self._refresh_pause_button()
        self.pause_toggled.emit(self._paused)

    def _refresh_pause_button(self) -> None:
        self.pause_btn.setText(t("controls.resume" if self._paused else "controls.pause"))

    def _on_theme_toggle(self) -> None:
        self._dark = not self._dark
        self._refresh_theme_button()
        self.theme_toggled.emit(self._dark)

    def _refresh_theme_button(self) -> None:
        self.theme_btn.setText(t("controls.use_light" if self._dark else "controls.use_dark"))
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
        self._start_allowed = enabled
        self._update_start_button()

    def set_link_count(self, count: int) -> None:
        self._link_count = count
        self._update_start_button()

    def _update_start_button(self) -> None:
        ready = self._link_count > 0 and not self._running
        self.start_btn.setVisible(ready)
        self.start_btn.setEnabled(ready and self._start_allowed)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._update_start_button()
        self._download_group.setEnabled(not running)
        self.maintenance_btn.setEnabled(not running)
        for button in (self.pause_btn, self.cancel_btn):
            button.setVisible(running)
            button.setEnabled(running)
        if running:
            self.paste_btn.show()

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
