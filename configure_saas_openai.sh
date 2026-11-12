#!/usr/bin/env bash
set +x
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec .venv/bin/python -m backend.saas.envfile configure
