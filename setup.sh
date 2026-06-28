#!/usr/bin/env bash
# Event Tracker — one-time setup. Builds backend venv + frontend bundle.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Backend: creating venv & installing deps"
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
python -c "import app; app.init_db(); print('DB initialized at', app.DB_PATH)"
deactivate
cd ..

echo "==> Frontend: installing deps & building"
cd frontend
npm install
npm run build
cd ..

echo ""
echo "Setup complete. Start the app with:  ./run.sh"
