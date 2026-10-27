# Starts Kavach on Windows at http://localhost:8000 (dashboard and API). Run scripts\setup.ps1 once first.
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Port 8000]
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Run scripts\setup.ps1 first." }
if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) { throw "The dashboard isn't built yet: run scripts\setup.ps1." }
Write-Host "Kavach on http://localhost:$Port  (Ctrl+C to stop)" -ForegroundColor Green
& $venvPy -m uvicorn app.serve:app --app-dir (Join-Path $root "backend") --host 127.0.0.1 --port $Port
