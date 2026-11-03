#!/usr/bin/env bash
# Native UI against a read-only dev backend (no ASR, no capture, no GPU).
# Starts the dev backend container on 127.0.0.1:8001 if it is not running.
# With the real stack up (./start-local-clova.sh), run instead:
#   .venv-ui/bin/python -m ui_native
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${CLOVA_IMAGE:-local-clova:rocm-v8-2-gamma-hotfix6}"
NAME="clova-dev-ui-backend"

[[ -x "$DIR/.venv-ui/bin/python" ]] || { echo "missing .venv-ui (python3 -m venv .venv-ui && .venv-ui/bin/pip install PySide6==6.12.0)" >&2; exit 1; }

if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  docker run -d --rm --name "$NAME" -p 127.0.0.1:8001:8000 \
    -v "$DIR:/workspace:ro" "$IMAGE" python3 /workspace/tools/dev-ui-backend.py >/dev/null
  for _ in $(seq 1 60); do
    curl -fsS --max-time 2 http://127.0.0.1:8001/api/library >/dev/null 2>&1 && break
    sleep 1
  done
fi

cd "$DIR"
exec .venv-ui/bin/python -m ui_native --backend http://127.0.0.1:8001 "$@"
