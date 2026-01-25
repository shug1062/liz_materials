#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# Prefer python3 on macOS
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found. Install Python 3.8+ from https://www.python.org/downloads/" >&2
  exit 1
fi

# Create venv if missing
if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi

# Activate venv
# shellcheck disable=SC1091
source "venv/bin/activate"

pip install --upgrade pip
pip install -r requirements.txt

echo "Starting Silver Jewellery Studio Tracker..."
echo "Open http://localhost:8080 in your browser"

"$PYTHON_BIN" app_new.py
