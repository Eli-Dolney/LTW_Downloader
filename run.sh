#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d ".venv" ]]; then
  echo "Creating Python 3.12 virtual environment..."
  python3.12 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

export TK_SILENCE_DEPRECATION=1
exec .venv/bin/python downloader.py
