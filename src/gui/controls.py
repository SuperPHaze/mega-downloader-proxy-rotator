# Barra comandi: Avvia, Pausa/Riprendi, Annulla, Impostazioni (popup),
# Sperimentale (dialog separato), Aggiungi link, toggle tema, Info.
# Le tre opzioni di configurazione (paralleli, limite, pezzo) sono raggruppate
# in un QMenu+QWidgetAction persistente, accessibile dal pulsante Impostazioni.
# I widget sottostanti (concurrency_combo, time_limit_spin, chunk_size_combo)
# restano attributi della classe: getter e segnali sono invariati.
# Il pulsante Sperimentale apre ExperimentalFeaturesDialog (gui/experimental_dialog.py),
# una superficie isolata per le leve in prova: non ne ospita i widget qui.
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QStyle,
    QWidget,
    QWidgetAction,
)

from src.core.config import MAX_CONCURRENT_DOWNLOADS, MAX_FILE_DURATION_MINUTES, PARALLEL_CHUNK_SIZE_MB


class ControlsBar(QWidget):
    start_requested = pyqtSignal()
    pause_toggled = pyqtSignal(bool)    # True = pausa, False = riprendi
    cancel_requested = pyqtSignal()
    concurrency_changed = pyqtSignal(int)
    paste_links_requested = pyqtSignal()
    theme_toggled = pyqtSignal(bool)    # True = tema scuro
    info_requested = pyqtSignal()
    experimental_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._paused = False
        self._dark = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Avvia (primario).
        self.start_btn = QPushButton("  Avvia")
        self.start_btn.setProperty("primary", "true")
        play_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.start_btn.setIcon(play_icon)
        self.start_btn.clicked.connect(self.start_requested)
        layout.addWidget(self.start_btn)

        # Pausa / Riprendi.
        self.pause_btn = QPushButton("  Pausa")
        pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.pause_btn.setIcon(pause_icon)
        self.pause_btn.clicked.connect(self._on_pause)
        layout.addWidget(self.pause_btn)

        # Annulla (distruttivo rosso).
        self.cancel_btn = QPushButton("  Annulla")
        self.cancel_btn.setProperty("danger", "true")
        cancel_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        self.cancel_btn.setIcon(cancel_icon)
        self.cancel_btn.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel_btn)

        layout.addStretch(1)

        # --- Controlli di configurazione (ospitati nel popup, non in barra). ---

        self.concurrency_combo = QComboBox()
        self.concurrency_combo.setToolTip(
            "Quanti file scaricare contemporaneamente.\n"
            "Default 1 (sequenziale): con proxy gratuiti, parallelizzare\n"
            "degrada tutti i download."
        )
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
        self.time_limit_spin.setToolTip(
            "Minuti massimi per scaricare un singolo file (wall-clock).\n"
            "Superato il limite, il file viene abbandonato e si passa al successivo.\n"
            "Il tempo in pausa è incluso nel conteggio."
        )
        self.time_limit_spin.setFixedWidth(64)

        self.chunk_size_combo = QComboBox()
        self.chunk_size_combo.setToolTip(
            "Dimensione di ogni pezzo scaricato da un proxy diverso.\n"
            "Pezzi più piccoli = più resistenza ai proxy instabili,\n"
            "più richieste HTTP al CDN Mega.\n"
            "Tagli grandi (128/256 MB): adatti a file molto grandi su proxy buoni."
        )
        # Tagli grandi (128/256 MB) per file molto grandi su proxy buoni: con
        # proxy lenti il watchdog per-segmento (PARALLEL_SEGMENT_ATTEMPT_MAX_DURATION_S
        # = 180s, soglia 200 KB/s) può abortire il tentativo prima che il pezzo
        # finisca, e un proxy che muore a metà pezzo spreca più byte. Restano
        # opzioni a disposizione dell'utente; il default 32 MB non cambia.
        for mb in (4, 8, 16, 32, 64, 128, 256):
            self.chunk_size_combo.addItem(f"{mb} MB", mb * 1024 * 1024)
        idx = self.chunk_size_combo.findData(PARALLEL_CHUNK_SIZE_MB * 1024 * 1024)
        if idx >= 0:
            self.chunk_size_combo.setCurrentIndex(idx)
        self.chunk_size_combo.setFixedWidth(84)

        # Pulsante Impostazioni: apre il popup con i tre controlli.
        self._settings_btn = QPushButton("⚙  Impostazioni")
        self._settings_btn.setToolTip(
            "Configura download paralleli, limite di durata e dimensione pezzo.\n"
            "Non modificabile durante una sessione di download."
        )
        self._settings_btn.clicked.connect(self._show_settings_menu)
        layout.addWidget(self._settings_btn)

        # Popup persistente con QWidgetAction: creato UNA sola volta.
        # I widget (combo, spin) sono figli del container row, che è figlio
        # dell'action, che è figlio del menu, che è figlio di ControlsBar.
        # Durata di vita = durata di ControlsBar.
        self._settings_menu = QMenu(self)
        _lbl_w = 126  # larghezza etichetta allineata
        for _row_label, _row_widget in (
            ("Paralleli:", self.concurrency_combo),
            ("Limite min/file:", self.time_limit_spin),
            ("Pezzo:", self.chunk_size_combo),
        ):
            _container = QWidget()
            _hl = QHBoxLayout(_container)
            _hl.setContentsMargins(12, 6, 12, 6)
            _hl.setSpacing(10)
            _lbl = QLabel(_row_label)
            _lbl.setFixedWidth(_lbl_w)
            _hl.addWidget(_lbl)
            _hl.addWidget(_row_widget)
            _wa = QWidgetAction(self._settings_menu)
            _wa.setDefaultWidget(_container)
            self._settings_menu.addAction(_wa)

        # Funzioni Sperimentali: superficie separata da Impostazioni, apre un
        # dialog proprio (vedi gui/experimental_dialog.py). Bloccato durante
        # una sessione attiva, come Impostazioni.
        self._experimental_btn = QPushButton("🧪  Sperimentale")
        self._experimental_btn.setToolTip(
            "Funzioni in prova (connessioni per file, selezione proxy per "
            "velocità). Disattivate di default.\n"
            "Non modificabile durante una sessione di download."
        )
        self._experimental_btn.clicked.connect(self.experimental_requested)
        layout.addWidget(self._experimental_btn)

        # Aggiungi link — sempre visibile.
        self.paste_btn = QPushButton("  Aggiungi link")
        paste_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        self.paste_btn.setIcon(paste_icon)
        self.paste_btn.clicked.connect(self.paste_links_requested)
        layout.addWidget(self.paste_btn)

        # Toggle tema chiaro/scuro.
        self.theme_btn = QPushButton("\U0001f319")   # 🌙
        self.theme_btn.setToolTip("Passa al tema scuro")
        self.theme_btn.setFixedWidth(36)
        self.theme_btn.clicked.connect(self._on_theme_toggle)
        layout.addWidget(self.theme_btn)

        # Info — pulsante autonomo, sempre accessibile (non dentro Impostazioni).
        self.info_btn = QPushButton("ℹ️  Info")
        self.info_btn.clicked.connect(self.info_requested)
        layout.addWidget(self.info_btn)

        # Stato iniziale: solo Avvia e Impostazioni attivi.
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

    def _show_settings_menu(self) -> None:
        pos = self._settings_btn.mapToGlobal(
            self._settings_btn.rect().bottomLeft()
        )
        self._settings_menu.exec(pos)

    def _on_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.setText("  Riprendi")
            resume_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            self.pause_btn.setIcon(resume_icon)
        else:
            self.pause_btn.setText("  Pausa")
            pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            self.pause_btn.setIcon(pause_icon)
        self.pause_toggled.emit(self._paused)

    def _on_theme_toggle(self) -> None:
        self._dark = not self._dark
        self.theme_btn.setText("☀️" if self._dark else "\U0001f319")  # ☀️ / 🌙
        self.theme_btn.setToolTip(
            "Passa al tema chiaro" if self._dark else "Passa al tema scuro"
        )
        self.theme_toggled.emit(self._dark)

    def reset(self) -> None:
        self._paused = False
        pause_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        self.pause_btn.setIcon(pause_icon)
        self.pause_btn.setText("  Pausa")
        self.set_running(False)

    def set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        # Il pulsante Impostazioni blocca l'accesso al popup durante la sessione:
        # i tre controlli all'interno non possono essere modificati a download attivo.
        self._settings_btn.setEnabled(not running)
        self._experimental_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.cancel_btn.setEnabled(running)

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self.theme_btn.setText("☀️" if dark else "\U0001f319")
        self.theme_btn.setToolTip(
            "Passa al tema chiaro" if dark else "Passa al tema scuro"
        )

    def get_concurrency(self) -> int:
        return int(self.concurrency_combo.currentData() or 1)

    def get_file_time_limit_s(self) -> int:
        """Ritorna il limite di durata per file in secondi."""
        return self.time_limit_spin.value() * 60

    def get_chunk_size_bytes(self) -> int:
        """Ritorna la dimensione del chunk in byte (scelta dalla GUI)."""
        return int(self.chunk_size_combo.currentData() or PARALLEL_CHUNK_SIZE_MB * 1024 * 1024)
