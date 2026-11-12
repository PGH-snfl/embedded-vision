#!/usr/bin/env bash
# Compatibility entry point. Canonical editor setup lives in its own service.
set -euo pipefail
exec bash "$(dirname -- "$0")/../services/editor/scripts/setup_workbench.sh" "$@"
