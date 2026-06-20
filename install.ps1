# Installer completo per Mega Proxy Downloader.
# Da eseguire dalla root del progetto (la cartella che contiene src/):
#
#   powershell -ExecutionPolicy Bypass -File install.ps1

param([ValidateSet("EN","IT")][string]$Lang = "EN")

function L([string]$en, [string]$it) {
    if ($Lang -eq "IT") { return $it } else { return $en }
}

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Err($msg) {
    Write-Host "    [ERROR] $msg" -ForegroundColor Red
}

function Write-Warn($msg) {
    Write-Host "    [WARN] $msg" -ForegroundColor Yellow
}

# ---- 1. Trova Python 3.11+ -------------------------------------------

Write-Step (L "Checking Python..." "Verifica Python...")

$pythonExe = $null

# Prova "python" diretto
try {
    $output = python --version 2>&1
    if ($LASTEXITCODE -eq 0 -and "$output" -match "Python 3\.(\d+)") {
        if ([int]$matches[1] -ge 11) {
            $pythonExe = "python"
            Write-OK (L "Found: $output" "Trovato: $output")
        }
    }
} catch {}

# Prova "python3" se non trovato
if (-not $pythonExe) {
    try {
        $output = python3 --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$output" -match "Python 3\.(\d+)") {
            if ([int]$matches[1] -ge 11) {
                $pythonExe = "python3"
                Write-OK (L "Found: $output" "Trovato: $output")
            }
        }
    } catch {}
}

# Prova il launcher "py" con versioni decrescenti
if (-not $pythonExe) {
    foreach ($v in @("3.14", "3.13", "3.12", "3.11")) {
        try {
            $output = py "-$v" --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$output" -match "Python 3\.(\d+)") {
                if ([int]$matches[1] -ge 11) {
                    $pythonExe = "py"
                    $script:pyFlag = "-$v"
                    Write-OK (L "Found: $output (py $script:pyFlag)" "Trovato: $output (py $script:pyFlag)")
                    break
                }
            }
        } catch {}
    }
}

if (-not $pythonExe) {
    Write-Err (L "Python 3.11+ not found in PATH." "Python 3.11+ non trovato nel PATH.")
    Write-Host ""
    Write-Host "    $(L "Download Python from: https://www.python.org/downloads/" "Scarica Python da: https://www.python.org/downloads/")" -ForegroundColor Yellow
    Write-Host "    $(L "During installation, tick 'Add Python to PATH'." "Durante l'installazione spunta 'Add Python to PATH'.")" -ForegroundColor Yellow
    exit 1
}

# Helper per chiamare python con eventuale flag -3.xx
function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments=$true)]$PyArgs)
    if ($script:pyFlag) {
        & $pythonExe $script:pyFlag @PyArgs
    } else {
        & $pythonExe @PyArgs
    }
}

# ---- 2. Crea venv ----------------------------------------------------

$venvPath = ".\venv"
$venvPy   = ".\venv\Scripts\python.exe"

if (Test-Path $venvPy) {
    Write-Step (L "venv already exists: reusing it." "venv gia esistente: lo riuso.")
} elseif (Test-Path $venvPath) {
    Write-Warn (L "venv folder present but corrupted, recreating it." "Cartella venv presente ma corrotta, la ricreo.")
    Remove-Item $venvPath -Recurse -Force -Confirm:$false
    Write-Step (L "Creating venv in $venvPath..." "Creazione venv in $venvPath...")
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Invoke-Python -m venv $venvPath
    $ErrorActionPreference = $prevEAP
    if ($LASTEXITCODE -ne 0) {
        Write-Err (L "venv creation failed." "Creazione venv fallita.")
        exit 1
    }
    Write-OK (L "venv created." "venv creato.")
} else {
    Write-Step (L "Creating venv in $venvPath..." "Creazione venv in $venvPath...")
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Invoke-Python -m venv $venvPath
    $ErrorActionPreference = $prevEAP
    if ($LASTEXITCODE -ne 0) {
        Write-Err (L "venv creation failed." "Creazione venv fallita.")
        exit 1
    }
    Write-OK (L "venv created." "venv creato.")
}

if (-not (Test-Path $venvPy)) {
    Write-Err (L "Corrupted venv: $venvPy does not exist. Delete the venv folder and try again." "venv corrotto: $venvPy non esiste. Elimina la cartella venv e riprova.")
    exit 1
}

# ---- 3. Aggiorna pip + setuptools + wheel ----------------------------

Write-Step (L "Upgrading pip, setuptools, wheel..." "Aggiornamento pip, setuptools, wheel...")
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $venvPy -m pip install --upgrade pip setuptools wheel --quiet
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    Write-Host "    $(L "WARNING: pip/setuptools/wheel upgrade FAILED." "ATTENZIONE: upgrade di pip/setuptools/wheel FALLITO.")" -ForegroundColor Red
    Write-Host "    $(L "This step is required to resolve recent PyQt6/PyQt6-sip wheels" "Questo passaggio e' necessario per risolvere i wheel recenti di")" -ForegroundColor Red
    Write-Host "    $(L "with the pip bundled in the venv (often too old)." "PyQt6/PyQt6-sip con il pip bundled nel venv (spesso troppo vecchio).")" -ForegroundColor Red
    Write-Host "    $(L "The script CONTINUES anyway, but the next step" "Lo script PROSEGUE comunque, ma lo step successivo")" -ForegroundColor Red
    Write-Host "    $(L "(installing dependencies from requirements.txt) may fail with" "(installazione dipendenze da requirements.txt) potrebbe fallire con")" -ForegroundColor Red
    Write-Host "    $(L "an unclear error (e.g. ResolutionImpossible on PyQt6-sip)." "un errore poco chiaro (es. ResolutionImpossible su PyQt6-sip).")" -ForegroundColor Red
    Write-Host "    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    Write-Host ""
} else {
    Write-OK (L "pip upgraded." "pip aggiornato.")
}

# ---- 4. Installa dipendenze ------------------------------------------

Write-Step (L "Installing dependencies from requirements.txt..." "Installazione dipendenze da requirements.txt...")
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $venvPy -m pip install -r requirements.txt
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0) {
    Write-Err (L "Dependency installation failed. Check the output above." "Installazione dipendenze fallita. Controlla l'output sopra.")
    exit 1
}
Write-OK (L "Dependencies installed." "Dipendenze installate.")

# Il backport "pathlib" (PyPI) rompe Python moderno: rimuovilo SOLO se presente,
# senza far fallire l'installazione (pip scrive su stderr se non c'e').
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
& $venvPy -m pip uninstall -y pathlib *> $null
$ErrorActionPreference = $prevEAP

# ---- 5. Crea launcher .bat -------------------------------------------

Write-Step (L "Creating launcher avvia.bat..." "Creazione launcher avvia.bat...")

$batContent = '@echo off
cd /d "%~dp0"
.\venv\Scripts\python.exe -m src.main
if errorlevel 1 pause'

$batContent | Out-File -FilePath ".\avvia.bat" -Encoding ascii
Write-OK (L "avvia.bat created in the project root." "avvia.bat creato nella root del progetto.")

# ---- 6. Smoke test ---------------------------------------------------

Write-Step (L "Smoke test: importing key modules..." "Smoke test: import moduli chiave...")

$testScript = @'
import sys
errors = []
for name, imp in [
    ("PyQt6",        "from PyQt6.QtWidgets import QApplication"),
    ("requests",     "import requests"),
    ("bs4",          "from bs4 import BeautifulSoup"),
    ("lxml",         "import lxml"),
    ("pycryptodome", "from Crypto.Cipher import AES"),
    ("src.core",     "from src.core.config import OUTPUT_DIR"),
]:
    try:
        exec(imp)
    except Exception as e:
        errors.append(f"{name}: {e}")
if errors:
    for err in errors:
        print(f"FAIL: {err}")
    sys.exit(1)
else:
    print("ALL_OK")
'@

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$result = & $venvPy -c $testScript 2>&1
$ErrorActionPreference = $prevEAP
if ("$result" -match "ALL_OK") {
    Write-OK (L "All modules import correctly." "Tutti i moduli si importano correttamente.")
} else {
    Write-Err (L "Smoke test failed:" "Smoke test fallito:")
    Write-Host "    $result" -ForegroundColor Red
    exit 1
}

# ---- Riepilogo -------------------------------------------------------

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "$(L "  Installation completed successfully!  " "  Installazione completata con successo!  ")" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "$(L "  Quick start:" "  Avvio rapido:")" -ForegroundColor White
Write-Host "$(L "    Double-click avvia.bat" "    Doppio clic su avvia.bat")" -ForegroundColor Yellow
Write-Host ""
Write-Host "$(L "  Or from a terminal:" "  Oppure da terminale:")" -ForegroundColor White
Write-Host "    .\venv\Scripts\python.exe -m src.main" -ForegroundColor Yellow
Write-Host ""
