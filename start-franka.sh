#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONUTF8=1 PYTHONUNBUFFERED=1
exec .venv-gui/bin/python -B app.py --station configs/franka.yaml --host 0.0.0.0 --port "${1:-8772}"
