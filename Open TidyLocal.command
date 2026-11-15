#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd -P) || {
  printf '%s\n' 'Sorry, TidyLocal could not find its project folder.'
  exit 1
}
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  printf '%s\n' 'TidyLocal is not set up yet (or its virtual environment is missing).'
  printf '\n%s\n' 'Open Terminal, cd to this project folder, then run:'
  printf '%s\n' 'python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock'
  printf '\n%s\n' 'After setup finishes, double-click Open TidyLocal.command again.'
  printf '%s' 'Press Return to close this window. '
  read -r _ || true
  exit 1
fi

if ! "$PYTHON" -c 'import fastapi, uvicorn, send2trash' >/dev/null 2>&1; then
  printf '%s\n' 'TidyLocal dependencies are missing from its project environment.'
  printf '\n%s\n' 'From this project folder, run:'
  printf '%s\n' '.venv/bin/python -m pip install -r requirements.lock'
  printf '\n%s\n' 'Then double-click Open TidyLocal.command again.'
  printf '%s' 'Press Return to close this window. '
  read -r _ || true
  exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON" launch.py
