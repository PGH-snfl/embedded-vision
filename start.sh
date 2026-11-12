#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
EV_SETUP=1
EV_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --skip-setup) EV_SETUP=0 ;;
    --setup-only) bash scripts/bootstrap.sh; exit 0 ;;
    --no-open) EV_ARGS+=(--no-open) ;;
    --help|-h) echo 'bash start.sh [--setup-only | --skip-setup] [--no-open]'; echo '종료: 터미널에서 Ctrl+C. 포트: EMBEDDED_VISION_PORT / EMBEDDED_VISION_EDITOR_PORT'; exit 0 ;;
    *) echo "알 수 없는 옵션: $arg" >&2; exit 2 ;;
  esac
done
if [[ $EV_SETUP == 1 ]]; then bash scripts/bootstrap.sh; fi
if [[ ! -x .venv/bin/python ]]; then echo '먼저 bash start.sh --setup-only를 실행하세요.' >&2; exit 1; fi
exec .venv/bin/python scripts/launch.py "${EV_ARGS[@]}"
