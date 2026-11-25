"""Misure e comandi della connessione nei dettagli della sessione."""
from __future__ import annotations

from PyQt6.QtCore import QLocale, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui import style as _style
from src.gui.i18n import TR, t
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

    def __init__(self, label_key: str) -> None:
        super().__init__()
        self._label_key = label_key
        self._color_key = "text"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self._label = QLabel(t(label_key))
        self._label.setObjectName("secondaryText")
        self._label.setWordWrap(True)
        self._value = QLabel("—")
        v.addWidget(self._label)
        v.addWidget(self._value)

    def retranslate(self) -> None:
        self._label.setText(t(self._label_key))

    def set_value(self, text: str, color_key: str = "text") -> None:
        self._value.setText(text)
        if self._color_key != color_key:
            self._color_key = color_key
            self.restyle()

    def restyle(self) -> None:
        self._value.setStyleSheet(f"color: {_style.CURRENT_PALETTE[self._color_key]};")


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
        self._line_mbps: float | None = None
        self._line_busy = False
        self._line_failure = ""
        self._line_http_status = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        self._micro = QLabel(t("proxy_bar.micro"))
        self._micro.setObjectName("sectionTitle")
        layout.addWidget(self._micro)

        cards_grid = QGridLayout()
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setHorizontalSpacing(10)
        cards_grid.setVerticalSpacing(8)

        self._card_alive = _MetricCard("proxy_bar.card_alive")
        self._card_validation = _MetricCard("proxy_bar.card_validation")
        self._card_discarded = _MetricCard("proxy_bar.card_discarded")
        self._card_refills = _MetricCard("proxy_bar.card_refills")
        self._card_since = _MetricCard("proxy_bar.card_last_refill")
        self._card_band = _MetricCard("proxy_bar.card_band")
        self._card_band_proxy = _MetricCard("proxy_bar.card_band_proxy")
        self._cards = (self._card_band, self._card_band_proxy, self._card_alive,
                       self._card_validation, self._card_discarded, self._card_refills,
                       self._card_since)
        for index, card in enumerate(self._cards):
            cards_grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            cards_grid.setColumnStretch(column, 1)
        layout.addLayout(cards_grid)
        self._line_note = QLabel()
        self._line_note.setObjectName("secondaryText")
        self._line_note.setWordWrap(True)
        layout.addWidget(self._line_note)
        # Pulsante per rifare la misura della banda della linea (diretto, fuori
        # dai proxy). La misura iniziale parte da MainWindow all'avvio.
        self._speedtest_btn = QPushButton()
        self._speedtest_btn.clicked.connect(self.speedtest_requested.emit)

        # Pulsante per misurare la banda ATTRAVERSO il pool di proxy. Abilitato
        # solo quando il pool ha proxy vivi (durante una sessione): a riposo non
        # ci sono proxy da testare.
        self._proxy_speedtest_btn = QPushButton()
        self._proxy_speedtest_btn.setEnabled(False)
        self._proxy_speedtest_btn.clicked.connect(self.proxy_speedtest_requested.emit)

        self._reset_btn = QPushButton()
        self._reset_btn.clicked.connect(self._on_reset_cache)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        for button in (self._speedtest_btn, self._proxy_speedtest_btn, self._reset_btn):
            button.setObjectName("textAction")
            actions.addWidget(button)
        self._speedtest_btn.setObjectName("measureAction")
        actions.addStretch()
        layout.addLayout(actions)
        self.set_session_visible(False)
        self.retranslate()
        self.reset()

    def set_session_visible(self, visible: bool) -> None:
        for card in self._cards[1:]:
            card.setVisible(visible)
        self._proxy_speedtest_btn.setVisible(visible)

    # ---- i18n ----------------------------------------------------------------

    def retranslate(self) -> None:
        """Riscrive i testi e ricasca su ogni card (gemello di refresh_theme()).

        NON tocca i VALORI delle card: sono numeri e unita' di misura, gia'
        indipendenti dalla lingua, e riscriverli qui li azzererebbe."""
        self._micro.setText(t("proxy_bar.micro"))
        for card in self._cards:
            card.retranslate()
        self._refresh_line_test()
        self._speedtest_btn.setToolTip(t("proxy_bar.speedtest_tooltip"))
        self._proxy_speedtest_btn.setText(
            t("proxy_bar.proxy_speedtest_button")
        )
        self._proxy_speedtest_btn.setToolTip(t("proxy_bar.proxy_speedtest_tooltip"))
        self._reset_btn.setText(t("proxy_bar.reset_button"))
        self._reset_btn.setToolTip(t("proxy_bar.reset_tooltip"))

    # ---- slot da pool/validazione --------------------------------------------

    def on_pool_size(self, n: int) -> None:
        if n == 0:
            color = "accent_fail"
        elif n < 5:
            color = "accent_warn"
        else:
            color = "accent_ok"
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
        self._line_busy = True
        self._line_failure = ""
        self._refresh_line_test()

    def on_speedtest_result(self, mbit: float, ok: bool, reason: str = "network", status: int = 0) -> None:
        self._line_busy = False
        self._line_failure = ""
        if ok and mbit > 0:
            self._line_mbps = mbit
        else:
            self._line_failure = reason
            self._line_http_status = status
        self._refresh_line_test()

    def _refresh_line_test(self) -> None:
        caption = "button"
        if self._line_busy:
            caption = "running"
        elif self._line_failure:
            caption = "retry"
        self._speedtest_btn.setText(t(f"proxy_bar.speedtest_{caption}"))
        self._speedtest_btn.setEnabled(not self._line_busy)
        if self._line_mbps is not None:
            number = QLocale(TR.language()).toString(self._line_mbps, "f", 1)
            self._card_band.set_value(f"{number} Mbit/s")
        else:
            self._card_band.set_value(t("proxy_bar.unavailable") if self._line_failure else "—", "text_dim")
        note = ""
        if self._line_failure:
            note = t(f"proxy_bar.line_{self._line_failure}", status=self._line_http_status)
            if self._line_mbps is not None:
                note += " " + t("proxy_bar.last_measurement")
        self._line_note.setText(note)
        self._line_note.setVisible(bool(note))

    def on_proxy_speedtest_running(self) -> None:
        self._card_band_proxy.set_value("…")

    def on_proxy_speedtest_result(self, mbit: float, ok: bool) -> None:
        if ok and mbit > 0:
            self._card_band_proxy.set_value(f"{mbit:.0f} Mbit")
        else:
            self._card_band_proxy.set_value("—", "text_dim")

    # ---- reset cache ---------------------------------------------------------

    def _on_reset_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            t("proxy_bar.reset_confirm_title"),
            t("proxy_bar.reset_confirm_body"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            deleted = delete_proxy_cache()
        except OSError as exc:
            QMessageBox.warning(
                self,
                t("proxy_bar.reset_error_title"),
                t("proxy_bar.reset_error_body", error=exc),
            )
            return
        if deleted:
            QMessageBox.information(
                self, t("proxy_bar.cache_title"), t("proxy_bar.cache_deleted")
            )
        else:
            QMessageBox.information(
                self, t("proxy_bar.cache_title"), t("proxy_bar.cache_absent")
            )

    # ---- reset / tema ---------------------------------------------------------

    def reset(self) -> None:
        self._card_alive.set_value("—", "text_dim")
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
        self._card_band_proxy.set_value("—", "text_dim")
        self._proxy_speedtest_btn.setEnabled(False)

    def refresh_theme(self) -> None:
        for card in self._cards:
            card.restyle()
