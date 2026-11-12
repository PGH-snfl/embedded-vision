#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname -- "$0")/services/analyzer/start.sh" --skip-setup "$@"
