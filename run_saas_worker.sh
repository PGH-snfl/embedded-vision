#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export EV_SAAS_DEVELOPMENT="${EV_SAAS_DEVELOPMENT:-1}"
export EV_SAAS_MODE=1
exec .venv/bin/python -m backend.saas.worker "$@"
