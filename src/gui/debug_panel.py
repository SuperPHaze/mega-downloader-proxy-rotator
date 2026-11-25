"""Lettore del log della sessione, incorporato nella finestra dei download."""
from __future__ import annotations

import codecs
import io
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QTextCursor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QToolButton, QVBoxLayout,
)

from src.gui.i18n import t


class DebugPanel(QFrame):
    hide_requested = pyqtSignal()
    # Una sessione può produrre megabyte mentre il pannello è chiuso.
    _READ_LIMIT = 64 * 1024

    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self.setObjectName("debugPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.setMinimumHeight(100)
        self.setMaximumHeight(260)
        self._path = log_path
        self._identity: tuple[int, int] | None = None
        self._offset = 0
        self._anchor = b""
        utf8 = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._decoder = io.IncrementalNewlineDecoder(utf8, translate=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 9)
        layout.setSpacing(3)
        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("sectionTitle")
        header.addWidget(self._title, 1)
        self._hide_button = QToolButton()
        self._hide_button.setObjectName("utilityAction")
        self._hide_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._hide_button.clicked.connect(self.hide_requested)
        header.addWidget(self._hide_button)
        layout.addLayout(header)
        self.output = QPlainTextEdit()
        self.output.setObjectName("debugOutput")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(600)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setTabChangesFocus(True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSizeF(max(12, font.pointSizeF()))
        self.output.setFont(font)
        self._title.setBuddy(self.output)
        layout.addWidget(self.output)
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._refresh)
        self.retranslate()

    def retranslate(self) -> None:
        self._title.setText(t("debug.title"))
        self.output.setAccessibleName(t("debug.title"))
        self.output.setPlaceholderText(t("debug.empty"))
        self._hide_button.setText(t("debug.hide"))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _refresh(self) -> None:
        try:
            with self._path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                tail = max(0, stat.st_size - self._READ_LIMIT)
                reset = identity != self._identity or not tail <= self._offset <= stat.st_size
                if not reset:
                    # La manutenzione può svuotare e riscrivere lo stesso file fra due letture.
                    stream.seek(self._offset - len(self._anchor))
                    reset = stream.read(len(self._anchor)) != self._anchor
                if not reset and self._offset == stat.st_size:
                    return
                # Anche una singola riga anomala, senza ritorni a capo, rimane limitata.
                reset = reset or self.output.document().characterCount() > 4 * self._READ_LIMIT
                stream.seek(tail if reset else self._offset)
                data = stream.read(self._READ_LIMIT)
                self._offset = stream.tell()
        except OSError:
            if self._identity is not None:
                self.output.clear()
                self._identity = None
            return

        self._identity = identity
        self._anchor = ((b"" if reset else self._anchor) + data)[-32:]
        scroll = self.output.verticalScrollBar()
        follow = reset or (scroll.value() == scroll.maximum() and not self.output.textCursor().hasSelection())
        first_visible = None if follow else self.output.firstVisibleBlock()
        if reset:
            self._decoder.reset()
            self.output.clear()
            if tail and b"\n" in data[:-1]:
                data = data.partition(b"\n")[2]
        cursor = QTextCursor(self.output.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(self._decoder.decode(data))
        if follow:
            scroll.setValue(scroll.maximum())
        elif first_visible is not None and first_visible.isValid():
            # Quando Qt scarta le righe più vecchie, resta sul messaggio che si stava leggendo.
            scroll.setValue(first_visible.blockNumber())
