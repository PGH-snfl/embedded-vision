#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export EV_SAAS_DEVELOPMENT="${EV_SAAS_DEVELOPMENT:-1}"
export EV_SAAS_MODE=1
unset OPENAI_API_KEY
exec .venv/bin/python -m uvicorn backend.saas.entrypoint:app --host 127.0.0.1 --port "${EV_SAAS_PORT:-8770}"
