#!/bin/bash
# Starts the studio tracker. Works from any folder and ignores whichever venv is active.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPYCACHEPREFIX="$HOME/.cache/liz_materials_pycache"

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python manage.py migrate --noinput
# First run: bring across data from the old app if its database file is here.
for legacy in jewelry_business.db ../nicegui_app/jewelry_business.db; do
  if [ -f "$legacy" ]; then
    .venv/bin/python manage.py import_legacy --if-empty "$legacy"
    break
  fi
done
.venv/bin/python manage.py collectstatic --noinput -v 0
.venv/bin/python manage.py backup_db

IP=$(ipconfig getifaddr en0 2>/dev/null || true)
echo
echo "Open http://localhost:8000 here${IP:+, or http://$IP:8000 on the iPad}."
echo "Press Ctrl+C (or close this window) to stop."
exec .venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 studio.wsgi:application
