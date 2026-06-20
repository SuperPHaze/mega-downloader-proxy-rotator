# Entry point: avvia QApplication e mostra la MainWindow.
from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.core.icon_loader import build_app_icon
from src.core.logging_setup import setup_logging
from src.gui.main_window import MainWindow


def _set_windows_app_user_model_id() -> None:
    # Senza un AppUserModelID esplicito, Windows mostra nella taskbar l'icona
    # generica di Python invece di quella dell'app (le finestre vengono
    # raggruppate sotto il processo host, non sotto l'identita' dell'app).
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "megaproxydownloader.app"
        )
    except Exception:
        pass


def main() -> int:
    log_file = setup_logging()
    log = logging.getLogger("main")
    log.info("Avvio applicazione. Log: %s", log_file)

    # Hook globale: cattura eccezioni non gestite e le scrive nel log.
    def excepthook(exc_type, exc_value, exc_tb):
        log.critical("Eccezione non gestita", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    _set_windows_app_user_model_id()

    app = QApplication(sys.argv)
    icon = build_app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
