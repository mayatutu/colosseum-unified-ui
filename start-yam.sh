#!/usr/bin/env bash
set -euo pipefail
STATION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$STATION_ROOT"
exec "$STATION_ROOT/.venv-gui/bin/python" "$STATION_ROOT/app.py" \
  --station "$STATION_ROOT/configs/yam.yaml" --host 0.0.0.0 --port "${1:-8772}"
