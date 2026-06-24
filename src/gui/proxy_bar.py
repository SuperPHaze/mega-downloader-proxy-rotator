# Zona proxy "spinta": valore guida (N vivi) + sparkline della dimensione
# del pool nel tempo + sub-riga compatta (validazione/scartati/ricariche/
# ultimo refill). Popolata da segnali dell'orchestrator (pool_size_changed,
# setup_progress, proxy_stats).
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.gui import style as _style
from src.gui.sparkline import Sparkline


def _fmt_ago(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m"


class ProxyBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._validation_text = "—"
        self._discarded = 0
        self._refills = 0
        self._since_seconds: float | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        self._micro = QLabel("PROXY")
        self._micro.setFont(QFont("Segoe UI", 8))
        layout.addWidget(self._micro)
        p = _style.CURRENT_PALETTE
        self._micro.setStyleSheet(
            f"color: {p['text_dim']}; letter-spacing: 1px; border: none;"
        )

        self._alive_value = QLabel("—")
        fv = QFont("Consolas", 16)
        fv.setWeight(QFont.Weight.DemiBold)
        self._alive_value.setFont(fv)
        layout.addWidget(self._alive_value)

        self._pool_spark = Sparkline(color_key="accent_ok")
        layout.addWidget(self._pool_spark)

        self._sub_line = QLabel()
        self._sub_line.setFont(QFont("Consolas", 8))
        layout.addWidget(self._sub_line)

        self.reset()

    # ---- slot da pool/validazione --------------------------------------------

    def on_pool_size(self, n: int) -> None:
        p = _style.CURRENT_PALETTE
        self._alive_value.setText(f"{n} vivi")
        if n == 0:
            color = p["accent_fail"]
        elif n < 5:
            color = p["accent_warn"]
        else:
            color = p["accent_ok"]
        self._alive_value.setStyleSheet(f"color: {color};")
        self._pool_spark.add_sample(float(n))

    def on_validation_progress(self, done: int, total: int, _alive: int) -> None:
        self._validation_text = f"{done}/{total}"
        self._refresh_sub_line()

    def on_validation_done(self) -> None:
        self._validation_text = "OK"
        self._refresh_sub_line()

    # ---- slot da proxy_stats dell'orchestrator -------------------------------

    def on_proxy_stats(
        self, discarded_session: int, refill_count: int, seconds_since_last_refill: object,
    ) -> None:
        self._discarded = discarded_session
        self._refills = refill_count
        self._since_seconds = seconds_since_last_refill
        self._refresh_sub_line()

    def _refresh_sub_line(self) -> None:
        p = _style.CURRENT_PALETTE
        since = _fmt_ago(self._since_seconds)
        self._sub_line.setText(
            f"valid. {self._validation_text} · scartati {self._discarded} · "
            f"ric. {self._refills} · {since}"
        )
        self._sub_line.setStyleSheet(f"color: {p['text_dim']};")

    # ---- reset / tema ---------------------------------------------------------

    def reset(self) -> None:
        p = _style.CURRENT_PALETTE
        self._alive_value.setText("—")
        self._alive_value.setStyleSheet(f"color: {p['text_dim']};")
        self._pool_spark.reset()
        self._validation_text = "—"
        self._discarded = 0
        self._refills = 0
        self._since_seconds = None
        self._refresh_sub_line()

    def refresh_theme(self) -> None:
        p = _style.CURRENT_PALETTE
        self._micro.setStyleSheet(
            f"color: {p['text_dim']}; letter-spacing: 1px; border: none;"
        )
        self._pool_spark.refresh_theme()
        self._refresh_sub_line()
