# GUI live per il monitor di velocita' download.
#
# Riutilizza le funzioni di scan di `tools.monitor_speed` (cosi' la logica
# di misura resta una sola, condivisa con la versione CLI).
#
# Uso:
#   .\venv\Scripts\python.exe -m tools.monitor_gui
#   .\venv\Scripts\python.exe -m tools.monitor_gui --interval 0.5 --temp-dir "C:\Users\<user>\AppData\Local\Temp"
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tools.monitor_speed import (
    human_bytes,
    human_speed,
    relpath,
    scan_detailed,
    scan_mega_temp,
    scan_sizes_from_detailed,
)


class Sparkline(QWidget):
    """Mini grafico a linea dei campioni recenti di velocita' istantanea."""

    def __init__(self, maxlen: int = 120) -> None:
        super().__init__()
        self.samples: deque[float] = deque(maxlen=maxlen)
        self.setMinimumHeight(80)
        self.setStyleSheet("background-color: #111; border: 1px solid #333;")

    def add(self, value: float) -> None:
        self.samples.append(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if not self.samples:
            painter.setPen(QPen(QColor("#666")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "in attesa di dati...")
            return
        peak = max(self.samples) or 1.0
        # Griglia orizzontale (3 livelli).
        painter.setPen(QPen(QColor("#222"), 1))
        for i in range(1, 4):
            y = int(h * i / 4)
            painter.drawLine(0, y, w, y)
        # Linea.
        pen = QPen(QColor("#2bd47d"), 2)
        painter.setPen(pen)
        n = len(self.samples)
        if n == 1:
            v = next(iter(self.samples))
            y = int(h - (v / peak) * (h - 4) - 2)
            painter.drawLine(0, y, w, y)
        else:
            step = w / (n - 1)
            prev_pt = None
            for i, v in enumerate(self.samples):
                x = int(i * step)
                y = int(h - (v / peak) * (h - 4) - 2)
                if prev_pt is not None:
                    painter.drawLine(prev_pt[0], prev_pt[1], x, y)
                prev_pt = (x, y)
        # Etichetta peak in alto a destra.
        painter.setPen(QPen(QColor("#888")))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(4, 12, f"peak finestra: {human_speed(peak)}")


class BigNumber(QWidget):
    """Riquadro 'KPI' con label e numero grande."""

    def __init__(self, title: str, color: str = "#2bd47d") -> None:
        super().__init__()
        self._color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: #aaa; font-size: 11px;")
        self.value = QLabel("—")
        f = QFont("Consolas", 18, QFont.Weight.Bold)
        self.value.setFont(f)
        self.value.setStyleSheet(f"color: {color};")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        self.setStyleSheet("background-color: #1a1a1a; border-radius: 6px;")

    def set(self, text: str) -> None:
        self.value.setText(text)


class MonitorWindow(QMainWindow):
    def __init__(self, root: Path, temp_dir: Path, interval_ms: int, temp_max_age: float) -> None:
        super().__init__()
        self.root = root
        self.temp_dir = temp_dir
        self.interval_ms = interval_ms
        self.temp_max_age = temp_max_age

        self.setWindowTitle("Mega Proxy Downloader — Monitor velocita'")
        self.resize(980, 640)
        self.setStyleSheet("""
            QMainWindow { background-color: #0e0e0e; color: #eee; }
            QLabel { color: #ddd; }
            QGroupBox { color: #ccc; border: 1px solid #333; border-radius: 4px; margin-top: 10px; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
            QTableWidget { background-color: #141414; color: #eee; gridline-color: #2a2a2a;
                           selection-background-color: #1f3a2a; }
            QHeaderView::section { background-color: #1a1a1a; color: #bbb; border: 0; padding: 4px; }
            QPushButton { background-color: #222; color: #eee; border: 1px solid #444;
                          padding: 4px 10px; border-radius: 3px; }
            QPushButton:hover { background-color: #2c2c2c; }
        """)

        central = QWidget()
        outer = QVBoxLayout(central)

        # Header: path + bottoni cambia cartella.
        header = QHBoxLayout()
        self.lbl_root = QLabel()
        self.lbl_temp = QLabel()
        for lbl in (self.lbl_root, self.lbl_temp):
            lbl.setStyleSheet("color: #aaa; font-family: Consolas; font-size: 11px;")
        btn_root = QPushButton("Cambia downloads...")
        btn_root.clicked.connect(self._pick_root)
        btn_temp = QPushButton("Cambia TEMP...")
        btn_temp.clicked.connect(self._pick_temp)
        self.btn_pause = QPushButton("Pausa")
        self.btn_pause.setCheckable(True)
        self.btn_pause.toggled.connect(self._toggle_pause)
        header.addWidget(self.lbl_root, 1)
        header.addWidget(btn_root)
        header.addWidget(self.lbl_temp, 1)
        header.addWidget(btn_temp)
        header.addWidget(self.btn_pause)
        outer.addLayout(header)

        # KPI row.
        kpi_row = QHBoxLayout()
        self.kpi_inst = BigNumber("Velocita' istantanea", "#2bd47d")
        self.kpi_avg = BigNumber("Media sessione", "#5aa0ff")
        self.kpi_peak = BigNumber("Picco", "#ffb84a")
        self.kpi_session = BigNumber("Scaricato (sessione)", "#e879f9")
        self.kpi_active = BigNumber("Download attivi", "#f87171")
        for k in (self.kpi_inst, self.kpi_avg, self.kpi_peak, self.kpi_session, self.kpi_active):
            kpi_row.addWidget(k, 1)
        outer.addLayout(kpi_row)

        # Sparkline.
        spark_box = QGroupBox("Throughput (ultimi ~60s)")
        spark_layout = QVBoxLayout(spark_box)
        self.spark = Sparkline(maxlen=int(60_000 / max(100, interval_ms)))
        spark_layout.addWidget(self.spark)
        outer.addWidget(spark_box)

        # Tabella temp attivi.
        temp_box = QGroupBox("Download in corso (file temp di mega.py)")
        temp_layout = QVBoxLayout(temp_box)
        self.tbl_temp = QTableWidget(0, 4)
        self.tbl_temp.setHorizontalHeaderLabels(["File temp", "Dimensione", "Velocita'", "Eta'"])
        self.tbl_temp.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_temp.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_temp.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_temp.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_temp.verticalHeader().setVisible(False)
        self.tbl_temp.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        temp_layout.addWidget(self.tbl_temp)
        outer.addWidget(temp_box, 1)

        # Tabella cicli completati on-disk.
        cycle_box = QGroupBox("Cicli on-disk (downloads/<hash>/ciclo_N)")
        cycle_layout = QVBoxLayout(cycle_box)
        self.tbl_cycles = QTableWidget(0, 3)
        self.tbl_cycles.setHorizontalHeaderLabels(["Ciclo", "Dimensione", "File"])
        self.tbl_cycles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_cycles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_cycles.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_cycles.verticalHeader().setVisible(False)
        self.tbl_cycles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cycle_layout.addWidget(self.tbl_cycles)
        outer.addWidget(cycle_box, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

        # Stato campionamento.
        self.prev_detailed = scan_detailed(self.root)
        self.prev = scan_sizes_from_detailed(self.prev_detailed)
        self.prev_temp = scan_mega_temp(self.temp_dir, self.temp_max_age)
        self.baseline_total_disk = sum(self.prev.values())
        self.baseline_total_temp = sum(v["size"] for v in self.prev_temp.values() if v["recent"])
        self.session_bytes = 0  # somma delle crescite (disk + temp) dall'avvio
        self.start_time = time.monotonic()
        self.last_time = self.start_time
        self.peak_inst = 0.0
        self.tick = 0

        self._refresh_header()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(self.interval_ms)

    def _refresh_header(self) -> None:
        self.lbl_root.setText(f"downloads: {self.root}")
        self.lbl_temp.setText(f"TEMP: {self.temp_dir}")

    def _pick_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Cartella downloads", str(self.root))
        if d:
            self.root = Path(d)
            self._reset_baseline()
            self._refresh_header()

    def _pick_temp(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Cartella TEMP di mega.py", str(self.temp_dir))
        if d:
            self.temp_dir = Path(d)
            self._reset_baseline()
            self._refresh_header()

    def _reset_baseline(self) -> None:
        self.prev_detailed = scan_detailed(self.root)
        self.prev = scan_sizes_from_detailed(self.prev_detailed)
        self.prev_temp = scan_mega_temp(self.temp_dir, self.temp_max_age)
        self.baseline_total_disk = sum(self.prev.values())
        self.session_bytes = 0
        self.start_time = time.monotonic()
        self.last_time = self.start_time
        self.peak_inst = 0.0
        self.tick = 0
        self.spark.samples.clear()
        self.spark.update()

    def _toggle_pause(self, paused: bool) -> None:
        if paused:
            self.timer.stop()
            self.btn_pause.setText("Riprendi")
            self.statusBar().showMessage("Campionamento in pausa.")
        else:
            self.last_time = time.monotonic()  # evita un dt enorme al riavvio
            self.timer.start(self.interval_ms)
            self.btn_pause.setText("Pausa")
            self.statusBar().showMessage("Ripreso.")

    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self.last_time
        self.last_time = now
        self.tick += 1

        curr_detailed = scan_detailed(self.root)
        curr = scan_sizes_from_detailed(curr_detailed)
        curr_total_disk = sum(curr.values())
        curr_temp = scan_mega_temp(self.temp_dir, self.temp_max_age)

        # Delta cicli on-disk (solo positivi).
        cycle_delta = 0
        for cycle_dir, size in curr.items():
            old = self.prev.get(cycle_dir, 0)
            d = size - old
            if d > 0:
                cycle_delta += d

        # Delta temp (solo positivi, per file).
        temp_rows: list[tuple[Path, dict, int]] = []  # (path, meta, delta)
        temp_delta = 0
        for p, meta in curr_temp.items():
            old_size = self.prev_temp.get(p, {}).get("size", 0) if p in self.prev_temp else 0
            d = meta["size"] - old_size
            if d > 0:
                temp_delta += d
            temp_rows.append((p, meta, d))

        total_delta = cycle_delta + temp_delta
        inst = total_delta / dt if dt > 0 else 0.0
        self.session_bytes += total_delta
        elapsed = now - self.start_time
        avg = self.session_bytes / elapsed if elapsed > 0 else 0.0
        if inst > self.peak_inst:
            self.peak_inst = inst

        n_active = sum(1 for _, _, d in temp_rows if d > 0) + sum(
            1 for cd, s in curr.items() if s - self.prev.get(cd, 0) > 0
        )

        # KPI.
        self.kpi_inst.set(human_speed(inst))
        self.kpi_avg.set(human_speed(avg))
        self.kpi_peak.set(human_speed(self.peak_inst))
        self.kpi_session.set(human_bytes(self.session_bytes))
        self.kpi_active.set(str(n_active))

        # Sparkline.
        self.spark.add(inst)

        # Tabella temp: mostra solo recenti, ordinati per velocita' desc poi per size desc.
        recent = [(p, m, d) for p, m, d in temp_rows if m.get("recent")]
        recent.sort(key=lambda x: (-x[2], -x[1]["size"]))
        self.tbl_temp.setRowCount(len(recent))
        for row, (p, meta, d) in enumerate(recent):
            speed = d / dt if dt > 0 else 0.0
            name_item = QTableWidgetItem(p.name)
            size_item = QTableWidgetItem(human_bytes(meta["size"]))
            speed_item = QTableWidgetItem(human_speed(speed) if d > 0 else "— idle —")
            age_item = QTableWidgetItem(f"{meta['age_s']:.1f}s")
            for item in (name_item, size_item, speed_item, age_item):
                item.setFont(QFont("Consolas", 10))
            if d > 0:
                speed_item.setForeground(QColor("#2bd47d"))
            else:
                speed_item.setForeground(QColor("#777"))
            self.tbl_temp.setItem(row, 0, name_item)
            self.tbl_temp.setItem(row, 1, size_item)
            self.tbl_temp.setItem(row, 2, speed_item)
            self.tbl_temp.setItem(row, 3, age_item)

        # Tabella cicli: tutti i cicli on-disk con almeno 1 file.
        non_empty = [(cd, info) for cd, info in curr_detailed.items() if info.get("total", 0) > 0]
        non_empty.sort(key=lambda x: -x[1]["total"])
        self.tbl_cycles.setRowCount(len(non_empty))
        for row, (cd, info) in enumerate(non_empty):
            cycle_item = QTableWidgetItem(relpath(cd, self.root))
            size_item = QTableWidgetItem(human_bytes(info["total"]))
            files_item = QTableWidgetItem(", ".join(info.get("files", {}).keys()) or "—")
            for item in (cycle_item, size_item, files_item):
                item.setFont(QFont("Consolas", 10))
            self.tbl_cycles.setItem(row, 0, cycle_item)
            self.tbl_cycles.setItem(row, 1, size_item)
            self.tbl_cycles.setItem(row, 2, files_item)

        self.statusBar().showMessage(
            f"tick={self.tick}  dt={dt:.3f}s  durata={elapsed:.1f}s  "
            f"on_disk={human_bytes(curr_total_disk)}  "
            f"temp_recenti={len(recent)}/{len(curr_temp)}"
        )

        self.prev = curr
        self.prev_detailed = curr_detailed
        self.prev_temp = curr_temp


def main() -> None:
    parser = argparse.ArgumentParser(description="GUI live monitor velocita' download Mega Proxy Downloader")
    parser.add_argument("--dir", default="./downloads", help="Cartella radice dei download")
    parser.add_argument("--temp-dir", default=tempfile.gettempdir(), help="Cartella TEMP di mega.py (default: %%TEMP%% del sistema)")
    parser.add_argument("--interval", type=float, default=0.5, help="Intervallo di campionamento in secondi (default: 0.5)")
    parser.add_argument("--temp-max-age", type=float, default=30.0, help="Eta' massima (s) dei file megapy_* per considerarli attivi")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    win = MonitorWindow(
        root=Path(args.dir).resolve(),
        temp_dir=Path(args.temp_dir).resolve(),
        interval_ms=max(100, int(args.interval * 1000)),
        temp_max_age=args.temp_max_age,
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
