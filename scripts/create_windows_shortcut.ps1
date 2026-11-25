# Explorer starts pythonw directly, with the project folder as the working directory.
$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$shortcutPath = Join-Path $projectDir "Mega Downloader Proxy Rotator.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $projectDir "venv\Scripts\pythonw.exe"
$shortcut.Arguments = "-m src.main"
$shortcut.WorkingDirectory = $projectDir
$shortcut.IconLocation = (Join-Path $projectDir "assets\icon.ico") + ",0"
$shortcut.Save()
