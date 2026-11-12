#!/usr/bin/env bash
set -euo pipefail
EV_PROJECT_ROOT=$(cd -- "$(dirname -- "$0")/../.." && pwd)
export EMBEDDED_VISION_DATA="${EMBEDDED_EDITOR_DATA:-$EV_PROJECT_ROOT/.runtime/editor}"
exec bash "$EV_PROJECT_ROOT/configure_openai.sh"
