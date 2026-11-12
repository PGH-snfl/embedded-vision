#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
unset EV_SAAS_MODE
if [[ ! -x .venv/bin/python ]]; then
  echo "먼저 README.md의 가상환경 설치 단계를 실행하세요."
  exit 1
fi
exec .venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port "${EMBEDDED_VISION_PORT:-8766}"
