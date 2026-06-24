# Test per i pulsanti filtro a selezione esclusiva di JobsPanel (sostituiscono
# la precedente tendina). Richiede una QApplication offscreen (PyQt6).
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from src.gui.jobs_panel import (
    FILTER_COMPLETED,
    FILTER_IN_PROGRESS,
    FILTER_NOT_COMPLETED,
    JobsPanel,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_filter_is_in_progress(qapp):
    panel = JobsPanel()
    assert panel._filter_category == FILTER_IN_PROGRESS
    assert panel._filter_buttons[FILTER_IN_PROGRESS].isChecked()


def test_clicking_completed_button_switches_filter(qapp):
    panel = JobsPanel()
    panel._filter_buttons[FILTER_COMPLETED].click()
    assert panel._filter_category == FILTER_COMPLETED


def test_clicking_not_completed_button_switches_filter(qapp):
    panel = JobsPanel()
    panel._filter_buttons[FILTER_NOT_COMPLETED].click()
    assert panel._filter_category == FILTER_NOT_COMPLETED


def test_filter_buttons_are_mutually_exclusive(qapp):
    panel = JobsPanel()
    panel._filter_buttons[FILTER_COMPLETED].click()
    assert panel._filter_buttons[FILTER_COMPLETED].isChecked()
    assert not panel._filter_buttons[FILTER_IN_PROGRESS].isChecked()
    assert not panel._filter_buttons[FILTER_NOT_COMPLETED].isChecked()


def test_filter_changes_card_visibility(qapp):
    # isHidden() riflette il flag esplicito impostato da _apply_filter(),
    # a differenza di isVisible() che dipende anche dalla visibilita' degli
    # antenati (qui mai mostrati: niente show() in un test offscreen).
    # _apply_filter() viene richiamato esplicitamente dopo il cambio di stato
    # del modello: non c'e' un binding automatico job_updated -> filtro
    # (comportamento gia' esistente, non toccato da questa modifica).
    panel = JobsPanel()
    panel.reset(["https://mega.nz/file/AAA#bbb", "https://mega.nz/file/CCC#ddd"])
    panel.model.mark_completed(0)
    panel._apply_filter()
    # Default FILTER_IN_PROGRESS: il job completato deve risultare nascosto.
    assert panel._cards[0].isHidden() is True
    panel._filter_buttons[FILTER_COMPLETED].click()
    assert panel._cards[0].isHidden() is False
    assert panel._cards[1].isHidden() is True
