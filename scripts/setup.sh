#!/usr/bin/env bash
# One-time setup on macOS / Linux: Python packages, settings file, database and dashboard build.
#   bash scripts/setup.sh
# Needs Python 3.11+ (tested on 3.13) and Node.js 20+.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
step() { printf '\n==> %s\n' "$1"; }

step "Checking Python and Node.js"
py=""
for candidate in python3.13 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    py="$candidate"; break
  fi
done
[ -n "$py" ] || { echo "Python 3.11 or newer was not found. Install Python 3.13 from https://www.python.org/downloads/"; exit 1; }
"$py" --version
command -v node >/dev/null 2>&1 || { echo "Node.js was not found. Install Node.js 20 or newer from https://nodejs.org/"; exit 1; }
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || { echo "Node.js $(node --version) is too old; install 20 or newer."; exit 1; }
echo "Node.js $(node --version)"

step "Creating the Python environment (backend/.venv)"
[ -x "$root/backend/.venv/bin/python" ] || "$py" -m venv "$root/backend/.venv"
venv_py="$root/backend/.venv/bin/python"
"$venv_py" -m pip install --quiet --upgrade pip
"$venv_py" -m pip install --quiet -r "$root/backend/requirements-dev.txt"

step "Settings (backend/.env)"
if [ -f "$root/backend/.env" ]; then echo "Keeping the existing backend/.env"
else cp "$root/backend/.env.example" "$root/backend/.env"; echo "Created backend/.env from .env.example"; fi

step "Database (backend/consent_court.db)"
(cd "$root/backend" && "$venv_py" -m alembic upgrade head)

step "Building the dashboard"
(cd "$root/frontend" && npm ci --no-audit --no-fund && npm run build)

printf '\nKavach is ready. Start it with:\n  bash scripts/start.sh\nthen open http://localhost:8000 and create an account.\n'
