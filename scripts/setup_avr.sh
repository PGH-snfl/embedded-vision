#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname -- "$0")/../services/editor/scripts/setup_avr.sh" "$@"
