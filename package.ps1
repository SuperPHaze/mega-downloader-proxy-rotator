# Crea un archivio .zip distribuibile del progetto.
# Uso:
#   powershell -ExecutionPolicy Bypass -File package.ps1
#
# Produce: dist\MegaProxyRotator-X.Y.Z.zip

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

# ── 1. Leggi versione da config.py ──────────────────────────────────────

Write-Step (L "Reading version..." "Lettura versione...")

$configPath = Join-Path $PSScriptRoot "src\core\config.py"
if (-not (Test-Path $configPath)) {
    Write-Err (L "File not found: $configPath" "File non trovato: $configPath")
    exit 1
}

$versionLine = Select-String -Path $configPath -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionLine) {
    Write-Err (L "APP_VERSION not found in config.py" "APP_VERSION non trovata in config.py")
    exit 1
}

$version = $versionLine.Matches[0].Groups[1].Value
Write-OK (L "Version: $version" "Versione: $version")

# ── 2. Prepara cartelle ────────────────────────────────────────────────

$folderName = "MegaProxyRotator-$version"
$distDir    = Join-Path $PSScriptRoot "dist"
$stageDir   = Join-Path $distDir $folderName
$zipPath    = Join-Path $distDir "$folderName.zip"

if (Test-Path $stageDir) {
    Remove-Item $stageDir -Recurse -Force -Confirm:$false
}
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force -Confirm:$false
}

New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Write-OK (L "Staging folder: $stageDir" "Cartella staging: $stageDir")

# ── 3. Copia solo i file tracciati da git (= file pubblici del repo) ───

Write-Step (L "Copying files (git-tracked only)..." "Copia file (solo file tracciati da git)...")

$sourceRoot = $PSScriptRoot

Push-Location $sourceRoot
try {
    $trackedFiles = git ls-files
} finally {
    Pop-Location
}

if (-not $trackedFiles) {
    Write-Err (L "git ls-files returned no files (missing or empty git repo)." "git ls-files non ha restituito alcun file (repo git assente o vuoto).")
    exit 1
}

foreach ($relPath in $trackedFiles) {
    $relPathNative = $relPath -replace '/', '\'
    $sourcePath = Join-Path $sourceRoot $relPathNative
    $destPath   = Join-Path $stageDir $relPathNative

    $destParent = Split-Path $destPath -Parent
    if ($destParent -and -not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
    }

    Copy-Item -Path $sourcePath -Destination $destPath -Force
}

Write-OK (L "Files copied: $($trackedFiles.Count) (from git ls-files)." "File copiati: $($trackedFiles.Count) (da git ls-files).")

# ── 4. Comprimi in .zip ───────────────────────────────────────────────

Write-Step (L "Creating archive $folderName.zip..." "Creazione archivio $folderName.zip...")

Compress-Archive -Path $stageDir -DestinationPath $zipPath -CompressionLevel Optimal
Write-OK (L "Archive created: $zipPath" "Archivio creato: $zipPath")

# ── 5. Pulizia staging ────────────────────────────────────────────────

Remove-Item $stageDir -Recurse -Force -Confirm:$false
Write-OK (L "Staging folder removed." "Cartella staging rimossa.")

# ── 6. Riepilogo ──────────────────────────────────────────────────────

$sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "$(L "  Package created successfully!            " "  Package creato con successo!            ")" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "$(L "  File:      $zipPath" "  File:      $zipPath")" -ForegroundColor Yellow
Write-Host "$(L "  Version:   $version" "  Versione:  $version")" -ForegroundColor Yellow
Write-Host "$(L "  Size:      $sizeMB MB" "  Dimensione: $sizeMB MB")" -ForegroundColor Yellow
Write-Host ""
Write-Host "$(L "  The user who receives the zip must:" "  L'utente che riceve lo zip deve:")" -ForegroundColor White
Write-Host "$(L "    1. Extract the folder" "    1. Estrarre la cartella")" -ForegroundColor White
Write-Host "$(L "    2. Run: powershell -ExecutionPolicy Bypass -File install.ps1" "    2. Eseguire: powershell -ExecutionPolicy Bypass -File install.ps1")" -ForegroundColor White
Write-Host "$(L "    3. Double-click avvia.bat" "    3. Doppio clic su avvia.bat")" -ForegroundColor White
Write-Host ""
