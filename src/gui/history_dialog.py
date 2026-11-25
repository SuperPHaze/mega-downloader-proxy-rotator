"""Storico consultabile mentre la coda continua a scaricare."""
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel, QDateTime, QLocale, QModelIndex, QSortFilterProxyModel, Qt, QUrl,
)
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QStackedWidget, QTableView, QVBoxLayout,
)

from src.core.download_history import HistoryEntry, history_entries
from src.gui.format_helpers import fmt_bytes
from src.gui.i18n import TR, t, tn


class _HistoryModel(QAbstractTableModel):
    headers = ("history.name", "history.date", "history.size")

    def __init__(self, parent):
        super().__init__(parent)
        self.entries: list[HistoryEntry] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return t(self.headers[section])
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.path or entry.name
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if index.column() == 0:
            return entry.name
        if index.column() == 1:
            date = QDateTime.fromString(entry.completed_at, Qt.DateFormat.ISODate)
            return QLocale(TR.language()).toString(date, QLocale.FormatType.ShortFormat) or "—"
        return fmt_bytes(entry.size) if entry.size >= 0 else "—"

    def reload(self):
        entries = history_entries()
        extra = len(entries) - len(self.entries)
        if extra >= 0 and entries[extra:] == self.entries:
            if extra:
                self.beginInsertRows(QModelIndex(), 0, extra - 1)
                self.entries = entries
                self.endInsertRows()
            return
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()


class HistoryDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.resize(660, 410)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        self.search = QLineEdit()
        self.search.setObjectName("historySearch")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.model = _HistoryModel(self)
        self.filtered = QSortFilterProxyModel(self)
        self.filtered.setSourceModel(self.model)
        self.filtered.setFilterKeyColumn(0)
        self.filtered.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table = QTableView()
        self.table.setObjectName("historyTable")
        self.table.setModel(self.filtered)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.empty = QLabel()
        self.empty.setObjectName("secondaryText")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.table)
        self.pages.addWidget(self.empty)
        layout.addWidget(self.pages, 1)

        footer = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName("secondaryText")
        footer.addWidget(self.count, 1)
        self.open_folder = QPushButton()
        self.open_folder.setAutoDefault(False)
        self.open_folder.clicked.connect(self._open_folder)
        footer.addWidget(self.open_folder)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        layout.addLayout(footer)
        self.search.textChanged.connect(self._filter)
        self.table.selectionModel().selectionChanged.connect(self._update_state)
        self.table.activated.connect(self._open_folder)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.search.setFocus)
        self.retranslate()

    def showEvent(self, event):
        super().showEvent(event)
        self.reload()

    def reload(self):
        self.model.reload()
        self._update_state()

    def retranslate(self):
        self.setWindowTitle(t("history.title"))
        self.search.setPlaceholderText(t("history.search"))
        self.search.setAccessibleName(t("history.search"))
        self.table.setAccessibleName(t("history.title"))
        self.open_folder.setText(t("history.open_folder"))
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(t("job_detail.close"))
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 2)
        if self.model.entries:
            self.model.dataChanged.emit(self.model.index(0, 1), self.model.index(len(self.model.entries) - 1, 1))
        self._update_state()

    def _filter(self, query):
        self.filtered.setFilterFixedString(query.strip())
        self._update_state()

    def _selection(self) -> HistoryEntry | None:
        selected = self.table.selectionModel().selectedRows()
        return self.model.entries[self.filtered.mapToSource(selected[0]).row()] if selected else None

    def _update_state(self):
        n = self.filtered.rowCount()
        self.pages.setCurrentWidget(self.table if n else self.empty)
        self.empty.setText(t("history.no_match" if self.model.entries else "history.empty"))
        self.count.setText(tn("history.count", n))
        entry = self._selection()
        self.open_folder.setEnabled(bool(entry and entry.path))
        self.open_folder.setToolTip(entry.path if entry else "")

    def _open_folder(self):
        entry = self._selection()
        if entry is None or not entry.path:
            return
        folder = Path(entry.path).parent
        if folder.is_absolute() and folder.is_dir() and QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            return
        QMessageBox.information(self, self.windowTitle(), t("history.unavailable"))
