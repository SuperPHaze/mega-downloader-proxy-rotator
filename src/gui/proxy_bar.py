# Sezione proxy: salute del pool (vivi/validazione) + metriche di sessione
# sui refill (scartati/ricariche/ultimo refill). Popolata da segnali
# dell'orchestrator (pool_size_changed, setup_progress, proxy_stats).
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QWidget

from src.gui import style as _style
from src.gui.kpi_card import KpiCard


def _fmt_ago(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s fa"
    return f"{secs // 60}m fa"


class ProxyBar(QWidget):
    def __init__(self) -> None:
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.k_alive = KpiCard("Vivi")
        self.k_validation = KpiCard("Validazione")
        self.k_discarded = KpiCard("Scartati")
        self.k_refills = KpiCard("Ricariche")
        self.k_last_refill = KpiCard("Ultimo refill")

        for w in (
            self.k_alive, self.k_validation, self.k_discarded,
            self.k_refills, self.k_last_refill,
        ):
            layout.addWidget(w)

        layout.addStretch(1)
        self.reset()

    # ---- slot da pool/validazione ----------------------------------------

    def on_pool_size(self, n: int) -> None:
        p = _style.CURRENT_PALETTE
        self.k_alive.set_value(str(n))
        if n == 0:
            self.k_alive.set_color(p["accent_fail"])
        elif n < 5:
            self.k_alive.set_color(p["accent_warn"])
        else:
            self.k_alive.set_color(p["accent_ok"])

    def on_validation_progress(self, done: int, total: int, _alive: int) -> None:
        p = _style.CURRENT_PALETTE
        self.k_validation.set_value(f"{done}/{total}")
        self.k_validation.set_color(p["accent_warn"])

    def on_validation_done(self) -> None:
        p = _style.CURRENT_PALETTE
        self.k_validation.set_value("OK")
        self.k_validation.set_color(p["accent_ok"])

    # ---- slot da proxy_stats dell'orchestrator ---------------------------

    def on_proxy_stats(
        self, discarded_session: int, refill_count: int, seconds_since_last_refill: object,
    ) -> None:
        p = _style.CURRENT_PALETTE
        self.k_discarded.set_value(str(discarded_session))
        self.k_discarded.set_color(p["accent_warn"] if discarded_session else p["text_dim"])
        self.k_refills.set_value(str(refill_count))
        self.k_refills.set_color(p["accent_info"] if refill_count else p["text_dim"])
        self.k_last_refill.set_value(_fmt_ago(seconds_since_last_refill))
        self.k_last_refill.set_color(p["text"] if seconds_since_last_refill is not None else p["text_dim"])

    # ---- reset / tema ------------------------------------------------------

    def reset(self) -> None:
        p = _style.CURRENT_PALETTE
        for w in (
            self.k_alive, self.k_validation, self.k_discarded,
            self.k_refills, self.k_last_refill,
        ):
            w.set_value("—")
            w.set_color(p["text_dim"])

    def refresh_theme(self) -> None:
        for w in (
            self.k_alive, self.k_validation, self.k_discarded,
            self.k_refills, self.k_last_refill,
        ):
            w.refresh_theme()
