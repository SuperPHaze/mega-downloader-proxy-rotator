"""Recupero dei trasferimenti trovati nella destinazione dei download."""
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QLocale, QObject, QRunnable, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from src.core.partial_downloads import PartialDownload, link_handle, scan_partials
from src.gui.i18n import TR, t


class ScanSignals(QObject):
    finished = pyqtSignal(int, object, str)


class PartialScan(QRunnable):
    def __init__(self, root: Path, links: list[str], generation: int, signals: ScanSignals, stop: Event):
        super().__init__()
        self.root, self.links = root, links
        self.stop = stop
        self.generation, self.signals = generation, signals

    def run(self):
        try:
            entries = scan_partials(self.root, self.links, stop=self.stop)
        except OSError as exc:
            self.signals.finished.emit(self.generation, [], str(exc))
        else:
            self.signals.finished.emit(self.generation, entries, "")


class PartialDialog(QDialog):
    refresh_requested = pyqtSignal()
    recover_requested = pyqtSignal(object, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.resize(660, 360)
        self.entries: list[PartialDownload] = []
        self.busy = False
        self.error = ""
        self.root: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        self.folder = QLabel()
        self.folder.setTextFormat(Qt.TextFormat.PlainText)
        self.folder.setObjectName("secondaryText")
        self.folder.setWordWrap(True)
        layout.addWidget(self.folder)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("historyTable")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.empty = QLabel()
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.table)
        self.pages.addWidget(self.empty)
        layout.addWidget(self.pages, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.note)
        footer = QHBoxLayout()
        self.refresh = QPushButton()
        self.refresh.setAutoDefault(False)
        self.refresh.clicked.connect(self.refresh_requested)
        footer.addWidget(self.refresh)
        footer.addStretch()
        self.action = QPushButton()
        self.action.setProperty("primary", "true")
        self.action.clicked.connect(self._recover)
        footer.addWidget(self.action)
        layout.addLayout(footer)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.retranslate()

    def set_root(self, root: Path) -> None:
        self.root = root
        self.folder.setText(t("workspace.destination", folder=root.name or str(root)))
        self.folder.setToolTip(str(root))
        self.folder.setAccessibleDescription(str(root))

    def selection(self) -> PartialDownload | None:
        selected = self.table.selectionModel().selectedRows()
        return self.entries[selected[0].row()] if selected else None

    def set_entries(self, entries, busy=False, error=""):
        selected = self.selection()
        self.entries, self.busy, self.error = entries, busy, error
        self.table.blockSignals(True)
        self.table.setRowCount(len(entries))
        row_to_select = 0
        locale = QLocale(TR.language())
        for row, item in enumerate(entries):
            name = QTableWidgetItem(item.target.name)
            name.setToolTip(str(item.target.relative_to(item.root)))
            self.table.setItem(row, 0, name)
            amount = t("partial.zero")
            if item.saved:
                percent = (1000 * item.saved // item.size) / 10
                amount = t("partial.saved", percent=locale.toString(percent, "f", 1),
                           amount=locale.formattedDataSize(item.saved, 1))
            self.table.setItem(row, 1, QTableWidgetItem(amount))
            if selected and item.target == selected.target:
                row_to_select = row
        if entries:
            self.table.selectRow(row_to_select)
        self.table.blockSignals(False)
        self.pages.setCurrentWidget(self.table if entries else self.empty)
        self.empty.setText(t("partial.scanning" if busy else "partial.scan_error" if error else "partial.empty"))
        self.empty.setToolTip(error)
        self.refresh.setEnabled(not busy)
        self._selection_changed()

    def retranslate(self):
        self.setWindowTitle(t("partial.title"))
        if self.root is not None:
            self.set_root(self.root)
        self.table.setAccessibleName(self.windowTitle())
        self.table.setHorizontalHeaderLabels([t("history.name"), t("partial.progress")])
        self.refresh.setText(t("partial.refresh"))
        self.set_entries(self.entries, self.busy, self.error)

    def _selection_changed(self):
        item = self.selection()
        self.action.setEnabled(bool(item) and not self.busy)
        self.action.setText(t("partial.restart" if item and not item.saved else "partial.resume"))
        detail = ""
        if item:
            detail = (t("partial.remaining", amount=QLocale(TR.language()).formattedDataSize(item.size - item.saved, 1)) if item.saved
                      else t("partial.no_checkpoint"))
            if item.in_history:
                detail += " " + t("partial.in_history")
        self.note.setText(detail)
        self.note.setVisible(bool(detail))

    def _recover(self):
        item = self.selection()
        if not item or self.busy:
            return
        url = item.url
        if not url:
            value, ok = QInputDialog.getText(self, self.windowTitle(), t("partial.request_link", name=item.target.name))
            if not ok:
                return
            url = value.strip()
            handle = link_handle(url)
            if not handle or (item.handle and item.handle != handle):
                QMessageBox.warning(self, self.windowTitle(), t("partial.wrong_link"))
                return
        if not item.saved:
            box = QMessageBox(QMessageBox.Icon.Question, self.windowTitle(),
                              t("partial.confirm_restart", name=item.target.name), parent=self)
            box.setTextFormat(Qt.TextFormat.PlainText)
            restart = box.addButton(t("partial.restart_now"), QMessageBox.ButtonRole.AcceptRole)
            cancel = box.addButton(t("partial.cancel"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(cancel)
            box.setEscapeButton(cancel)
            box.exec()
            if box.clickedButton() is not restart:
                return
        self.recover_requested.emit(item, url)
