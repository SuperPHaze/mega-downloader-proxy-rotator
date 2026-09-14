@echo off
rem Avvio di riserva, con la finestra del terminale VISIBILE: e' il
rem comportamento che avvia.bat aveva prima dell'avvio silenzioso.
rem Serve quando l'app non parte e in logs\ non c'e' abbastanza per capire
rem perche' (per esempio un errore prima che il logging sia attivo).
cd /d "%~dp0"
.\venv\Scripts\python.exe -m src.main
if errorlevel 1 pause
