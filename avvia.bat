@echo off
rem Avvio normale, SILENZIOSO: pythonw.exe non apre alcuna finestra di
rem terminale. "start" fa partire l'app e lascia terminare subito questo
rem script invece di restare appeso al programma per tutta la sessione.
rem La console che Windows apre per qualunque .bat resta visibile per un
rem istante: e' il prezzo del doppio clic su un .bat.
rem Se l'app non parte e vuoi vedere il perche', usa avvia-debug.bat.
cd /d "%~dp0"
if not exist ".\venv\Scripts\pythonw.exe" (
    echo [ERRORE] Ambiente non installato: esegui prima install.bat
    pause
    exit /b 1
)
start "" ".\venv\Scripts\pythonw.exe" -m src.main
