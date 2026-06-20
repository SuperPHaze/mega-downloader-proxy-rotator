# Tema grafico dell'applicazione: palette chiara + scura, template QSS,
# funzioni per cambiare tema a caldo.
from __future__ import annotations

from PyQt6.QtWidgets import QApplication

# Token spaziatura e raggio.
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8
MARGIN_SM = 6
MARGIN_MD = 8
MARGIN_LG = 12

PALETTE_LIGHT: dict[str, str] = {
    "bg": "#f4f5f7",
    "panel": "#ffffff",
    "panel_alt": "#f0f2f5",
    "text": "#1f2328",
    "text_dim": "#6b7280",
    "border": "#d7dbe0",
    "border_strong": "#b7bdc6",
    "accent_ok": "#15803d",
    "accent_info": "#2563eb",
    "accent_warn": "#b45309",
    "accent_fail": "#dc2626",
    "accent_active": "#7c3aed",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_pressed": "#1e40af",
    "primary_disabled_bg": "#c7d2fe",
    "primary_disabled_fg": "#eef2ff",
    "danger": "#dc2626",
    "danger_hover_bg": "#fee2e2",
    "danger_hover": "#fecaca",
    "row": "#ffffff",
    "row_alt": "#f3f4f6",
    "status_bg_queued": "#eceef1",
    "status_bg_running": "#f1e7fd",
    "status_bg_completed": "#dcfce7",
    "status_bg_failed": "#fee2e2",
    "status_bg_cancelled": "#fef3c7",
    "status_bg_abandoned": "#fecaca",
    "card_bg": "#ffffff",
    "card_border": "#e5e7eb",
    "selection_bg": "#dbe4ff",
}

PALETTE_DARK: dict[str, str] = {
    "bg": "#0d1117",
    "panel": "#161b27",
    "panel_alt": "#1e2435",
    "text": "#e2e8f0",
    "text_dim": "#94a3b8",
    "border": "#2a3045",
    "border_strong": "#3a4060",
    "accent_ok": "#22c55e",
    "accent_info": "#60a5fa",
    "accent_warn": "#fbbf24",
    "accent_fail": "#f87171",
    "accent_active": "#a78bfa",
    "primary": "#3b82f6",
    "primary_hover": "#2563eb",
    "primary_pressed": "#1d4ed8",
    "primary_disabled_bg": "#1e3366",
    "primary_disabled_fg": "#6080aa",
    "danger": "#f87171",
    "danger_hover_bg": "#4d1818",
    "danger_hover": "#4d1818",
    "row": "#161b27",
    "row_alt": "#1e2435",
    "status_bg_queued": "#252b3d",
    "status_bg_running": "#251c3d",
    "status_bg_completed": "#152a1e",
    "status_bg_failed": "#3d1515",
    "status_bg_cancelled": "#3d2f10",
    "status_bg_abandoned": "#4d1818",
    "card_bg": "#161b27",
    "card_border": "#2a3045",
    "selection_bg": "#253060",
}

# Palette corrente: aggiornata da apply_theme() in-place cosi' i riferimenti
# importati direttamente restano validi.
CURRENT_PALETTE: dict[str, str] = dict(PALETTE_LIGHT)

# Backward compat: PALETTE punta sempre a PALETTE_LIGHT (tema chiaro fisso).
# Codice tema-aware deve usare CURRENT_PALETTE.
PALETTE = PALETTE_LIGHT


_QSS_TEMPLATE = """
QMainWindow, QDialog {{
    background-color: {bg};
    color: {text};
}}
QWidget {{
    color: {text};
    font-family: "Segoe UI", "Roboto", Arial, sans-serif;
    font-size: 10pt;
}}
QLabel {{ color: {text}; }}
QFrame {{ border: none; }}

QStatusBar {{
    background-color: {panel};
    color: {text_dim};
    border-top: 1px solid {border};
    padding: 2px 4px;
    font-size: 9pt;
}}

/* --- Pulsanti base --- */
QPushButton {{
    background-color: {panel};
    color: {text};
    border: 1px solid {border_strong};
    border-radius: {RADIUS_MD}px;
    padding: 5px 14px;
    min-height: 26px;
}}
QPushButton:hover {{
    background-color: {selection_bg};
    border-color: {accent_info};
}}
QPushButton:pressed {{
    background-color: {primary_pressed};
    color: #ffffff;
    border-color: {primary_pressed};
}}
QPushButton:disabled {{
    background-color: {panel_alt};
    color: {text_dim};
    border-color: {border};
}}

/* --- Pulsante primario (Avvia) --- */
QPushButton[primary="true"] {{
    background-color: {primary};
    color: #ffffff;
    border-color: {primary_hover};
    font-weight: bold;
    padding: 6px 20px;
    min-height: 30px;
    font-size: 10pt;
}}
QPushButton[primary="true"]:hover {{
    background-color: {primary_hover};
    border-color: {primary_pressed};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {primary_pressed};
}}
QPushButton[primary="true"]:disabled {{
    background-color: {primary_disabled_bg};
    color: {primary_disabled_fg};
    border-color: {primary_disabled_bg};
}}

/* --- Pulsante distruttivo (Annulla) --- */
QPushButton[danger="true"] {{
    background-color: {panel};
    color: {danger};
    border: 1px solid {danger};
    border-radius: {RADIUS_MD}px;
    padding: 5px 14px;
    min-height: 26px;
}}
QPushButton[danger="true"]:hover {{
    background-color: {danger_hover_bg};
    border-color: {danger};
    color: {danger};
}}
QPushButton[danger="true"]:pressed {{
    background-color: {danger};
    color: #ffffff;
}}
QPushButton[danger="true"]:disabled {{
    color: {text_dim};
    border-color: {border};
    background-color: {panel_alt};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox {{
    background-color: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: {RADIUS_SM}px;
    padding: 3px 6px;
    selection-background-color: {accent_info};
    selection-color: #ffffff;
}}
QPlainTextEdit, QTextEdit {{
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 9pt;
    background-color: {panel_alt};
}}
QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button {{
    border: none;
    background: {panel_alt};
}}
QComboBox QAbstractItemView {{
    background-color: {panel};
    color: {text};
    selection-background-color: {selection_bg};
    border: 1px solid {border};
}}

QTableView {{
    background-color: {panel};
    alternate-background-color: {row_alt};
    color: {text};
    gridline-color: {border};
    border: 1px solid {border};
    selection-background-color: {selection_bg};
    selection-color: {text};
}}
QHeaderView::section {{
    background-color: {panel_alt};
    color: {text};
    padding: 5px 8px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-weight: bold;
}}
QTableCornerButton::section {{
    background-color: {panel_alt};
    border: 1px solid {border};
}}

QProgressBar {{
    background-color: {panel_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    text-align: center;
    height: 10px;
    font-size: 8pt;
    max-height: 10px;
}}
QProgressBar::chunk {{
    background-color: {accent_ok};
    border-radius: 3px;
}}

QScrollBar:vertical {{
    background: {bg};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border_strong};
    min-height: 24px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: {text_dim}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    background: {bg};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border_strong};
    min-width: 24px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{ background: {text_dim}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

QToolTip {{
    background-color: {panel};
    color: {text};
    border: 1px solid {accent_info};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
}}

QCheckBox {{ color: {text}; }}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {border_strong};
    background: {panel};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{
    background: {accent_ok};
    border-color: {accent_ok};
}}

QSplitter::handle {{
    background: {border};
}}
"""


def build_qss(palette: dict) -> str:
    return _QSS_TEMPLATE.format(
        RADIUS_SM=RADIUS_SM,
        RADIUS_MD=RADIUS_MD,
        RADIUS_LG=RADIUS_LG,
        **palette,
    )


def apply_theme(app: QApplication, dark: bool) -> None:
    new_pal = PALETTE_DARK if dark else PALETTE_LIGHT
    CURRENT_PALETTE.clear()
    CURRENT_PALETTE.update(new_pal)
    app.setStyleSheet(build_qss(CURRENT_PALETTE))


LIGHT_QSS = build_qss(PALETTE_LIGHT)
DARK_QSS = build_qss(PALETTE_DARK)
