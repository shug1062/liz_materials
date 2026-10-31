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
# First run: bring across data from the old app (put jewelry_business.db in the data folder).
for legacy in data/jewelry_business.db jewelry_business.db ../nicegui_app/jewelry_business.db; do
  if [ -f "$legacy" ]; then
    .venv/bin/python manage.py import_legacy --if-empty "$legacy"
    break
  fi
done
.venv/bin/python manage.py collectstatic --noinput -v 0
.venv/bin/python manage.py backup_db

IP=$(ipconfig getifaddr en0 2>/dev/null || true)
export STUDIO_LAN_IP="$IP"
echo
echo "Open http://localhost:8000 here${IP:+, or http://$IP:8000 on the iPad}."
echo "For a lasting address, reserve this laptop's current IP in your router's DHCP settings."
echo "Press Ctrl+C (or close this window) to stop."
exec .venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 studio.wsgi:application
