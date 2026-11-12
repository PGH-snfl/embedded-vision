#!/usr/bin/env bash
set -euo pipefail
EV_PROJECT_ROOT=$(cd -- "$(dirname -- "$0")/../.." && pwd)
export EMBEDDED_VISION_DATA="${EMBEDDED_ANALYZER_DATA:-${EMBEDDED_VISION_DATA:-$EV_PROJECT_ROOT/.runtime}}"
exec bash "$EV_PROJECT_ROOT/configure_openai.sh"
