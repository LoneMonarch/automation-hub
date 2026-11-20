#!/usr/bin/env bash
# Developer launcher. End users use the packaged application.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -x venv/bin/python3 ]; then
  echo "Developer environment missing. Use the packaged Automation Hub app, or create a Python 3.13 venv and install requirements.txt."
  exit 1
fi
exec venv/bin/python3 desktop.py
