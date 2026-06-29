# Zona proxy "conservativa": riga di card compatte (Vivi, Validazione,
# Scartati, Ricariche, Ultimo refill), niente sparkline. Popolata da segnali
# dell'orchestrator (pool_size_changed, setup_progress, proxy_stats).
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from src.gui import style as _style
from src.proxy.proxy_cache import delete_proxy_cache


def _fmt_ago(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m"


class _MetricCard(QFrame):
    """Card compatta: etichetta piccola sopra, valore sotto."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setMinimumWidth(58)
        v = QVBoxLayout(self)
        v.setContentsMargins(5, 3, 5, 3)
        v.setSpacing(1)

        self._label = QLabel(label.upper())
        self._label.setFont(QFont("Segoe UI", 7))
        v.addWidget(self._label)

        self._value = QLabel("—")
        fv = QFont("Consolas", 11)
        fv.setWeight(QFont.Weight.Medium)
        self._value.setFont(fv)
        v.addWidget(self._value)

    def set_value(self, text: str, color: str | None = None) -> None:
        p = _style.CURRENT_PALETTE
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color or p['text']}; border: none;")

    def restyle(self) -> None:
        p = _style.CURRENT_PALETTE
        self.setStyleSheet(
            f"QFrame {{ background-color: {p['panel_alt']}; "
            f"border: 0.5px solid {p['border']}; border-radius: {_style.RADIUS_MD}px; }}"
        )
        self._label.setStyleSheet(
            f"color: {p['text_dim']}; letter-spacing: 0.5px; border: none;"
        )


class ProxyBar(QWidget):
    # Richiesta di un nuovo speed test della linea (diretto, gestita da MainWindow).
    speedtest_requested = pyqtSignal()
    # Richiesta di uno speed test ATTRAVERSO i proxy del pool live (MainWindow).
    proxy_speedtest_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._validation_text = "—"
        self._discarded = 0
        self._refills = 0
        self._since_seconds: float | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(3)

        self._micro = QLabel("PROXY")
        self._micro.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self._micro)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(4)

        self._card_alive = _MetricCard("Vivi")
        self._card_validation = _MetricCard("Validazione")
        self._card_discarded = _MetricCard("Scartati")
        self._card_refills = _MetricCard("Ricariche")
        self._card_since = _MetricCard("Ultimo refill")
        self._card_band = _MetricCard("Banda")
        self._card_band_proxy = _MetricCard("Banda proxy")
        self._cards = (
            self._card_alive,
            self._card_validation,
            self._card_discarded,
            self._card_refills,
            self._card_since,
            self._card_band,
            self._card_band_proxy,
        )
        for card in self._cards:
            cards_row.addWidget(card)

        # Pulsante per rifare la misura della banda della linea (diretto, fuori
        # dai proxy). La misura iniziale parte da MainWindow all'avvio.
        self._speedtest_btn = QPushButton("↻ Banda")
        self._speedtest_btn.setFixedHeight(22)
        self._speedtest_btn.setToolTip(
            "Misura la banda della linea (download diretto, senza proxy)."
        )
        self._speedtest_btn.clicked.connect(self.speedtest_requested.emit)
        cards_row.addWidget(self._speedtest_btn)

        # Pulsante per misurare la banda ATTRAVERSO il pool di proxy. Abilitato
        # solo quando il pool ha proxy vivi (durante una sessione): a riposo non
        # ci sono proxy da testare.
        self._proxy_speedtest_btn = QPushButton("↻ Banda proxy")
        self._proxy_speedtest_btn.setFixedHeight(22)
        self._proxy_speedtest_btn.setToolTip(
            "Misura la banda reale del pool di proxy (solo durante una sessione)."
        )
        self._proxy_speedtest_btn.setEnabled(False)
        self._proxy_speedtest_btn.clicked.connect(self.proxy_speedtest_requested.emit)
        cards_row.addWidget(self._proxy_speedtest_btn)

        cards_row.addStretch(1)
        self._reset_btn = QPushButton("Reset cache")
        self._reset_btn.setFixedHeight(22)
        self._reset_btn.setToolTip(
            "Cancella proxy_cache.json. Il prossimo avvio rifarà lo scrape da zero."
        )
        self._reset_btn.clicked.connect(self._on_reset_cache)
        cards_row.addWidget(self._reset_btn)
        layout.addLayout(cards_row)

        self._restyle_micro()
        self._restyle_cards()
        self.reset()

    # ---- slot da pool/validazione --------------------------------------------

    def on_pool_size(self, n: int) -> None:
        p = _style.CURRENT_PALETTE
        if n == 0:
            color = p["accent_fail"]
        elif n < 5:
            color = p["accent_warn"]
        else:
            color = p["accent_ok"]
        self._card_alive.set_value(str(n), color)
        # Il test "Banda proxy" ha senso solo con proxy vivi nel pool.
        self._proxy_speedtest_btn.setEnabled(n > 0)

    def on_validation_progress(self, done: int, total: int, _alive: int) -> None:
        self._validation_text = f"{done}/{total}"
        self._card_validation.set_value(self._validation_text)

    def on_validation_done(self) -> None:
        self._validation_text = "OK"
        self._card_validation.set_value(self._validation_text)

    # ---- slot da proxy_stats dell'orchestrator -------------------------------

    def on_proxy_stats(
        self, discarded_session: int, refill_count: int, seconds_since_last_refill: object,
    ) -> None:
        self._discarded = discarded_session
        self._refills = refill_count
        self._since_seconds = seconds_since_last_refill
        self._card_discarded.set_value(str(self._discarded))
        self._card_refills.set_value(str(self._refills))
        self._card_since.set_value(_fmt_ago(self._since_seconds))

    # ---- slot speed test linea -----------------------------------------------

    def on_speedtest_running(self) -> None:
        self._card_band.set_value("…")

    def on_speedtest_result(self, mbit: float, ok: bool) -> None:
        p = _style.CURRENT_PALETTE
        if ok and mbit > 0:
            self._card_band.set_value(f"{mbit:.0f} Mbit", p["accent_ok"])
        else:
            self._card_band.set_value("—", p["text_dim"])

    def on_proxy_speedtest_running(self) -> None:
        self._card_band_proxy.set_value("…")

    def on_proxy_speedtest_result(self, mbit: float, ok: bool) -> None:
        # Colore distinto (accent_info, blu) dalla banda di linea (accent_ok,
        # verde) per differenziare a colpo d'occhio le due misure.
        p = _style.CURRENT_PALETTE
        if ok and mbit > 0:
            self._card_band_proxy.set_value(f"{mbit:.0f} Mbit", p["accent_info"])
        else:
            self._card_band_proxy.set_value("—", p["text_dim"])

    # ---- reset cache ---------------------------------------------------------

    def _on_reset_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset cache proxy",
            "Cancellare la cache dei proxy?\n"
            "Il prossimo avvio sarà più lento perché rifarà lo scrape da zero.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            deleted = delete_proxy_cache()
        except OSError as exc:
            QMessageBox.warning(self, "Errore", f"Impossibile cancellare la cache:\n{exc}")
            return
        if deleted:
            QMessageBox.information(self, "Cache proxy", "Cache proxy cancellata.")
        else:
            QMessageBox.information(self, "Cache proxy", "Nessuna cache da cancellare.")

    # ---- reset / tema ---------------------------------------------------------

    def reset(self) -> None:
        p = _style.CURRENT_PALETTE
        self._card_alive.set_value("—", p["text_dim"])
        self._validation_text = "—"
        self._discarded = 0
        self._refills = 0
        self._since_seconds = None
        self._card_validation.set_value("—")
        self._card_discarded.set_value("0")
        self._card_refills.set_value("0")
        self._card_since.set_value("—")
        # NB: la card "Banda" NON viene azzerata: e' una proprieta' della linea
        # dell'utente (non della sessione), re-mostrata da MainWindow dal valore
        # in preferences e aggiornata dallo speed test.
        # La card "Banda proxy" INVECE e' specifica della sessione (dipende dal
        # pool corrente): la azzeriamo e disabilitiamo il pulsante finche' non
        # ci sono proxy vivi.
        self._card_band_proxy.set_value("—", p["text_dim"])
        self._proxy_speedtest_btn.setEnabled(False)

    def refresh_theme(self) -> None:
        self._restyle_micro()
        self._restyle_cards()

    def _restyle_micro(self) -> None:
        p = _style.CURRENT_PALETTE
        self._micro.setStyleSheet(
            f"color: {p['text_dim']}; letter-spacing: 1px; border: none;"
        )

    def _restyle_cards(self) -> None:
        for card in self._cards:
            card.restyle()
        p = _style.CURRENT_PALETTE
        btn_qss = (
            f"QPushButton {{ color: {p['text_dim']}; border: 1px solid {p['border']}; "
            f"border-radius: 4px; background: transparent; font-size: 8pt; padding: 2px 6px; }}"
            f"QPushButton:hover {{ background-color: {p['panel_alt']}; }}"
        )
        self._reset_btn.setStyleSheet(btn_qss)
        self._speedtest_btn.setStyleSheet(btn_qss)
        self._proxy_speedtest_btn.setStyleSheet(btn_qss)
