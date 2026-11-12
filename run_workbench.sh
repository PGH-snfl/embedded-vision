#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -f third_party/velxio/frontend/dist/index.html ]]; then
  echo '먼저 bash scripts/setup_workbench.sh를 실행하세요.'
  exit 1
fi
exec .venv/bin/python -m uvicorn backend.workbench.server:app --host 127.0.0.1 --port "${EMBEDDED_VISION_EDITOR_PORT:-8768}"
