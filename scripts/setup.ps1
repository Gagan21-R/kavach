# One-time setup on Windows: Python packages, settings file, database and dashboard build.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Needs Python 3.11+ (tested on 3.13) and Node.js 20+.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

Step "Checking Python and Node.js"
$py = $null
foreach ($candidate in @(@("py", "-3.13"), @("py", "-3"), @("python"))) {
    try {
        $v = & $candidate[0] $candidate[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.11") { $py = $candidate; break }
    } catch {}
}
if (-not $py) { throw "Python 3.11 or newer was not found. Install Python 3.13 from https://www.python.org/downloads/" }
Write-Host "Python $v ($($py -join ' '))"
try { $node = (node --version) } catch { throw "Node.js was not found. Install Node.js 20 or newer from https://nodejs.org/" }
if ([int]($node.TrimStart("v").Split(".")[0]) -lt 20) { throw "Node.js $node is too old; install Node.js 20 or newer." }
Write-Host "Node.js $node"

Step "Creating the Python environment (backend\.venv)"
$venvPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py[0] $py[1..9] -m venv (Join-Path $backend ".venv") }
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $backend "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Installing Python packages failed." }

Step "Settings (backend\.env)"
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) { Write-Host "Keeping the existing backend\.env" }
else { Copy-Item (Join-Path $backend ".env.example") $envFile; Write-Host "Created backend\.env from .env.example" }

Step "Database (backend\consent_court.db)"
Push-Location $backend
try { & $venvPy -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw "Database migration failed." } } finally { Pop-Location }

Step "Building the dashboard"
Push-Location $frontend
try {
    npm ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run build; if ($LASTEXITCODE -ne 0) { throw "Dashboard build failed." }
} finally { Pop-Location }

Write-Host "`nKavach is ready. Start it with:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\start.ps1"
Write-Host "then open http://localhost:8000 and create an account."
