# Tema grafico dell'applicazione: palette chiara + scura, template QSS,
# funzioni per cambiare tema a caldo.
from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

# Token spaziatura e raggio.
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8
MARGIN_SM = 6
MARGIN_MD = 8
MARGIN_LG = 12

# Superfici neutre ispirate a Tokyo Night Day/Night. Il corallo del progetto segna azioni e avanzamento.
PALETTE_LIGHT: dict[str, str] = {
    "bg": "#eff0f4",
    "panel": "#fafafd",
    "panel_alt": "#e1e2e8",
    "text": "#242738",
    "text_dim": "#545b70",
    "border": "#d8dae3",
    "border_strong": "#b7bbcb",
    "scroll_thumb": "#8a90a4",
    "scroll_hover": "#686e84",
    "accent_ok": "#556078",
    "completed_track": "#969caf",
    "accent_info": "#a82f36",
    "accent_warn": "#815326",
    "accent_fail": "#a12d37",
    "accent_active": "#c53a3f",
    "primary": "#c53a3f",
    "on_primary": "#ffffff",
    "primary_hover": "#ae3037",
    "primary_pressed": "#95272f",
    "primary_disabled_bg": "#dfe0e7",
    "primary_disabled_fg": "#585f73",
    "danger": "#ac303a",
    "danger_hover_bg": "#f6e6e9",
    "danger_hover": "#efd8dd",
    "row": "#fafafd",
    "row_alt": "#f1f2f6",
    "status_bg_queued": "#e8e9ef",
    "status_bg_running": "#f6e6e9",
    "status_bg_completed": "#e8e9ef",
    "status_bg_failed": "#f6e6e9",
    "status_bg_cancelled": "#eceaf0",
    "status_bg_abandoned": "#f6e6e9",
    "card_bg": "#fafafd",
    "card_border": "#dcdee7",
    "selection_bg": "#e0e2ec",
}

PALETTE_DARK: dict[str, str] = {
    "bg": "#1a1b26",
    "panel": "#222430",
    "panel_alt": "#313443",
    "text": "#e2e5f0",
    "text_dim": "#aab0c4",
    "border": "#353849",
    "border_strong": "#53586d",
    "scroll_thumb": "#60667f",
    "scroll_hover": "#8b91aa",
    "accent_ok": "#b0b7ce",
    "completed_track": "#676d84",
    "accent_info": "#ff8186",
    "accent_warn": "#e3bb87",
    "accent_fail": "#ffa0a6",
    "accent_active": "#ff777b",
    "primary": "#ff777b",
    "on_primary": "#20202b",
    "primary_hover": "#ff8c90",
    "primary_pressed": "#ed666f",
    "primary_disabled_bg": "#383b4b",
    "primary_disabled_fg": "#a5abc0",
    "danger": "#ff9499",
    "danger_hover_bg": "#40303d",
    "danger_hover": "#4a303d",
    "row": "#222430",
    "row_alt": "#282a38",
    "status_bg_queued": "#303242",
    "status_bg_running": "#40303d",
    "status_bg_completed": "#303242",
    "status_bg_failed": "#402e3a",
    "status_bg_cancelled": "#393644",
    "status_bg_abandoned": "#402e3a",
    "card_bg": "#222430",
    "card_border": "#343747",
    "selection_bg": "#363a4e",
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
    font-weight: 400;
}}
QLabel {{ color: {text}; }}
QFrame {{ border: none; }}

QMenuBar, QMenu {{ background: {panel}; color: {text}; }}
QMenu::item:selected, QMenuBar::item:selected {{ background: {selection_bg}; color: {text}; }}

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
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {row_alt};
    border-color: {text_dim};
}}
QPushButton:pressed {{
    background-color: {selection_bg};
    color: {text};
    border-color: {border_strong};
}}
QPushButton:disabled {{
    background-color: {panel_alt};
    color: {text_dim};
    border-color: {border};
}}

/* --- Pulsante primario (Avvia) --- */
QPushButton[primary="true"] {{
    background-color: {primary};
    color: {on_primary};
    border-color: {primary};
    font-weight: 500;
    padding: 4px 14px;
    min-height: 22px;
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
    border: 1px solid {border_strong};
    border-radius: {RADIUS_MD}px;
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton#cancelQueue {{ background: transparent; color: {text_dim}; border-color: transparent; }}
QPushButton#cancelQueue:hover, QPushButton[danger="true"]:hover {{
    background-color: {danger_hover_bg};
    border-color: {danger};
    color: {danger};
}}
QPushButton#cancelQueue:pressed, QPushButton[danger="true"]:pressed {{
    background-color: {primary};
    color: {on_primary};
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
    selection-background-color: {selection_bg};
    selection-color: {text};
}}
QPlainTextEdit, QTextEdit {{
    font-size: 9pt;
    background-color: {panel_alt};
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
    font-weight: 500;
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
    background-color: {accent_active};
    border-radius: 3px;
}}

QToolTip {{
    background-color: {panel};
    color: {text};
    border: 1px solid {accent_info};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
}}

QCheckBox {{ color: {text}; }}
QWidget#workspace, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
QWidget#sessionDetails, QScrollArea#detailsScroll {{ background: {panel}; border: none; border-radius: 8px; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#emptyTitle {{ font-size: 18px; font-weight: 500; }}
QLabel#sectionTitle {{ font-size: 14px; font-weight: 500; }}
QLabel#metricValue {{ font-size: 18px; font-weight: 500; }}
QLabel#fileName {{ font-size: 14px; font-weight: 500; }}
QLabel#statusBadge, QLabel#secondaryText, QLabel#transferRate {{
    color: {text_dim}; font-size: 12px; font-weight: 400;
}}
QLabel#transferPercent {{ color: {text}; font-size: 12px; }}
QWidget#queueSurface {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}
QWidget#queueList {{ background: {panel}; }}
QFrame#card {{ background: {panel}; border: none; border-bottom: 1px solid {card_border}; }}
QFrame#jobDetails {{ border: none; border-top: 1px solid {border}; }}
QFrame#failureNotice {{ background: {status_bg_failed}; border-radius: 5px; }}
QLabel#failureTitle {{ color: {accent_fail}; font-weight: 500; }}
QFrame#hairline {{ background: {border}; }}
QWidget#updateBanner {{ background: {panel_alt}; border-radius: 5px; }}
QPushButton#queueFilter {{
    background: transparent; color: {text_dim}; border: none; border-bottom: 2px solid transparent;
    border-radius: 0; min-height: 22px; padding: 2px 8px;
}}
QPushButton#queueFilter:checked {{ border-bottom-color: {accent_active}; color: {text}; }}
QToolButton#detailsToggle, QPushButton#textAction, QToolButton#rowAction, QToolButton#rowMenu {{
    background: transparent; color: {text_dim}; border: 1px solid transparent;
    border-radius: 4px; min-height: 22px; padding: 1px 5px;
}}
QToolButton#detailsToggle:hover, QPushButton#textAction:hover, QPushButton#queueFilter:hover,
QToolButton#rowAction:hover, QToolButton#rowMenu:hover {{
    background: {selection_bg}; color: {text};
}}
QPushButton#textAction:disabled {{ color: {text_dim}; }}
QToolButton#rowAction {{ padding: 0; min-width: 24px; }}
QToolButton#rowMenu {{ padding: 0 4px; min-width: 24px; font-size: 17px; }}
QToolButton#rowMenu::menu-indicator {{ image: none; width: 0; height: 0; }}

QScrollBar:vertical {{ background: {bg}; width: 11px; margin: 0; border: none; }}
QScrollBar:horizontal {{ background: {bg}; height: 11px; margin: 0; border: none; }}
QScrollBar::handle:vertical {{
    background: {scroll_thumb}; min-height: 26px; margin: 2px 3px; border-radius: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {scroll_thumb}; min-width: 26px; margin: 3px 2px; border-radius: 2px;
}}
QScrollBar::handle:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: transparent; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: transparent; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar::up-arrow, QScrollBar::down-arrow, QScrollBar::left-arrow, QScrollBar::right-arrow {{
    image: none; width: 0; height: 0;
}}
QGroupBox {{ border: 1px solid {border}; border-radius: 8px; margin-top: 12px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {text_dim}; }}
QListWidget {{ alternate-background-color: {row_alt}; }}
QListWidget::item {{ padding: 8px 6px; }}
QListWidget::item:selected {{ background: {selection_bg}; color: {text}; }}
QPushButton:focus, QPushButton#cancelQueue:focus, QPushButton#queueFilter:focus, QToolButton#rowAction:focus,
QPushButton#textAction:focus, QToolButton#rowMenu:focus, QToolButton#detailsToggle:focus,
QTextEdit:focus, QListWidget:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {accent_info};
}}
QPushButton[primary="true"]:focus {{ border-color: {text}; }}
QSplitter::handle {{
    background: {border};
}}
"""


@lru_cache(maxsize=8)
def disclosure_icon(expanded: bool, ink: str) -> QIcon:
    """Chevron da 12 px anche quando lo stile nativo ingrandisce le frecce."""
    pixmap = QPixmap(24, 24)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(ink), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    if expanded:
        path.moveTo(2, 4)
        path.lineTo(6, 8)
        path.lineTo(10, 4)
    else:
        path.moveTo(4, 2)
        path.lineTo(8, 6)
        path.lineTo(4, 10)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def ui_font(points: int, weight: QFont.Weight = QFont.Weight.Normal, *, fixed: bool = False) -> QFont:
    family = QFontDatabase.SystemFont.FixedFont if fixed else QFontDatabase.SystemFont.GeneralFont
    font = QFontDatabase.systemFont(family)
    font.setPointSize(points)
    font.setWeight(weight)
    return font


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
    hints = app.styleHints()
    if app.platformName() == "cocoa" and hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    palette = app.style().standardPalette()
    roles = QPalette.ColorRole
    for role, key in (
        (roles.Window, "bg"), (roles.WindowText, "text"), (roles.Base, "panel"),
        (roles.AlternateBase, "row_alt"), (roles.Text, "text"), (roles.Button, "panel"),
        (roles.ButtonText, "text"), (roles.Highlight, "selection_bg"),
        (roles.HighlightedText, "text"), (roles.PlaceholderText, "text_dim"),
        (roles.ToolTipBase, "panel"), (roles.ToolTipText, "text"),
        (roles.Link, "accent_info"), (roles.LinkVisited, "accent_info"), (roles.Accent, "accent_active"),
    ):
        palette.setColor(role, QColor(new_pal[key]))
    for role in (roles.Text, roles.WindowText, roles.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(new_pal["text_dim"]))
    app.setPalette(palette)
    app.setStyleSheet(build_qss(CURRENT_PALETTE))


LIGHT_QSS = build_qss(PALETTE_LIGHT)
DARK_QSS = build_qss(PALETTE_DARK)
