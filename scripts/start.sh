#!/usr/bin/env bash
# Starts Kavach on macOS / Linux at http://localhost:8000 (dashboard and API). Run scripts/setup.sh once first.
#   bash scripts/start.sh [port]
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
port="${1:-8000}"
venv_py="$root/backend/.venv/bin/python"
[ -x "$venv_py" ] || { echo "Run scripts/setup.sh first."; exit 1; }
[ -f "$root/frontend/dist/index.html" ] || { echo "The dashboard isn't built yet: run scripts/setup.sh."; exit 1; }
echo "Kavach on http://localhost:$port  (Ctrl+C to stop)"
exec "$venv_py" -m uvicorn app.serve:app --app-dir "$root/backend" --host 127.0.0.1 --port "$port"
