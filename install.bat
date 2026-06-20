@echo off
rem Entry point unico di installazione: funziona da cmd, doppio clic o PowerShell.
rem Delega tutto a install.ps1 (trova Python, crea venv, AGGIORNA PIP,
rem installa dipendenze, smoke test, crea avvia.bat).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo.
    echo [ERRORE] Installazione fallita. Controlla l'output sopra.
    pause
    exit /b 1
)
exit /b 0
