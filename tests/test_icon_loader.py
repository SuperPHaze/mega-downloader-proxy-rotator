# Test della costruzione dell'icona dell'app.
#
# Perche' esistono: il ripiego al .png e l'avviso nel log non erano mai stati
# provati, e il sospetto (poi smentito misurando) era che non scattassero mai.
# Da qui in poi i tre casi — .ico buono, .ico illeggibile, nessuno dei due —
# sono coperti, e il numero di dimensioni caricate dal .ico reale e' una
# verifica di regressione: se un giorno ne entrasse una sola, Windows
# ingrandirebbe la stessa immagine per barra, finestra e commutatore.
import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from src.core import icon_loader
from src.core.config import APP_ICON_ICO_PATH, APP_ICON_PNG_PATH


def test_ico_reale_porta_piu_dimensioni(qt_app):
    """Il .ico versionato nel progetto e' multi-risoluzione: devono entrare
    tutte, non una sola."""
    assert APP_ICON_ICO_PATH.exists(), APP_ICON_ICO_PATH
    icon = icon_loader.build_app_icon()
    sizes = sorted((s.width(), s.height()) for s in icon.availableSizes())
    assert sizes, "nessuna dimensione caricata dal .ico reale"
    assert len(sizes) >= 2, sizes
    assert (16, 16) in sizes and (256, 256) in sizes, sizes


def test_ripiego_al_png_quando_l_ico_e_illeggibile(qt_app, tmp_path, monkeypatch, caplog):
    """Il caso che con il vecchio controllo era solo teorico: un .ico che
    ESISTE ma non si legge. Il ripiego deve scattare davvero."""
    rotto = tmp_path / "icon.ico"
    rotto.write_bytes(b"non sono una icona" * 20)
    monkeypatch.setattr(icon_loader, "APP_ICON_ICO_PATH", rotto)
    monkeypatch.setattr(icon_loader, "APP_ICON_PNG_PATH", APP_ICON_PNG_PATH)

    with caplog.at_level(logging.WARNING, logger="src.core.icon_loader"):
        icon = icon_loader.build_app_icon()

    assert icon.availableSizes(), "il ripiego al .png non ha caricato nulla"
    assert any("ripiego .png" in r.getMessage() for r in caplog.records), caplog.text


def test_ripiego_al_png_quando_l_ico_manca(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(icon_loader, "APP_ICON_ICO_PATH", tmp_path / "assente.ico")
    monkeypatch.setattr(icon_loader, "APP_ICON_PNG_PATH", APP_ICON_PNG_PATH)
    icon = icon_loader.build_app_icon()
    assert icon.availableSizes()


def test_avviso_quando_non_si_carica_nulla(qt_app, tmp_path, monkeypatch, caplog):
    """L'avviso che in tre mesi di log non era mai comparso: qui si verifica
    che esista davvero, invece di fidarsi del suo silenzio."""
    monkeypatch.setattr(icon_loader, "APP_ICON_ICO_PATH", tmp_path / "assente.ico")
    monkeypatch.setattr(icon_loader, "APP_ICON_PNG_PATH", tmp_path / "assente.png")

    with caplog.at_level(logging.WARNING, logger="src.core.icon_loader"):
        icon = icon_loader.build_app_icon()

    assert icon.availableSizes() == []
    assert icon.isNull()
    assert any(
        "Icona app non caricata" in r.getMessage() for r in caplog.records
    ), caplog.text


def test_non_solleva_mai_su_file_spazzatura(qt_app, tmp_path, monkeypatch):
    """`build_app_icon()` gira all'avvio, prima di qualunque finestra: un
    file corrotto non deve impedire l'avvio dell'applicazione."""
    for nome in ("icon.ico", "icon.png"):
        (tmp_path / nome).write_bytes(os.urandom(512))
    monkeypatch.setattr(icon_loader, "APP_ICON_ICO_PATH", tmp_path / "icon.ico")
    monkeypatch.setattr(icon_loader, "APP_ICON_PNG_PATH", tmp_path / "icon.png")
    assert icon_loader.build_app_icon() is not None
