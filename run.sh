#!/usr/bin/env bash
# Event Tracker — start the server (Flask + waitress on :8093).
set -euo pipefail
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "No venv found. Run ./setup.sh first." >&2
  exit 1
fi
. .venv/bin/activate
exec python app.py
