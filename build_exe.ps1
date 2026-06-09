# Builds VideoDuzenleyici.exe (single-file) into the project root, so the
# bundled app reuses the existing data/ folder next to it (projects, music,
# YouTube tokens). ffmpeg/ffprobe stay external and must remain on PATH.
#
# Usage:   powershell -ExecutionPolicy Bypass -File build_exe.ps1
# Needs:   pip install pyinstaller
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building VideoDuzenleyici.exe ..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --onefile --name VideoDuzenleyici `
    --distpath . --workpath build --specpath . `
    --add-data "app/static;app/static" `
    --collect-submodules uvicorn `
    --collect-data googleapiclient `
    --hidden-import app.main `
    --exclude-module librosa --exclude-module numba --exclude-module llvmlite `
    --exclude-module scipy --exclude-module matplotlib --exclude-module tkinter `
    --exclude-module pytest `
    desktop.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nDONE -> $PSScriptRoot\VideoDuzenleyici.exe" -ForegroundColor Green
    Write-Host "Cift tiklayarak calistirin; tarayici otomatik acilir (http://127.0.0.1:8000)."
} else {
    Write-Host "`nBuild FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
}
