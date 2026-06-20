# EventBus minimale per pubblicare eventi cross-layer in modalita' read-only per i subscriber.
# Opzionale: i segnali principali viaggiano direttamente sui QThread worker.
from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    event = pyqtSignal(str, dict)

    def emit_event(self, name: str, payload: dict | None = None) -> None:
        self.event.emit(name, payload or {})
