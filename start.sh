#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
EV_SETUP=1;EV_SETUP_ONLY=0;EV_SERVICE=editor;EV_ARGS=()
while (( $# )); do
 case "$1" in
  --service) [[ $# -ge 2 ]] || { echo '--service 값이 필요합니다.' >&2; exit 2; };EV_SERVICE="$2";shift 2 ;;
  --skip-setup) EV_SETUP=0;shift ;;
  --setup-only) EV_SETUP_ONLY=1;shift ;;
  --no-open) EV_ARGS+=(--no-open);shift ;;
  --help|-h) echo 'bash start.sh [--service editor|analyzer|all] [--setup-only|--skip-setup] [--no-open]';echo '기본: 편집기만 실행. 종료: Ctrl+C. 각 서비스는 별도 터미널에서 실행할 수 있습니다.';exit 0 ;;
  *) echo "알 수 없는 옵션: $1" >&2;exit 2 ;;
 esac
done
case "$EV_SERVICE" in editor|analyzer|all) ;; *) echo '서비스: editor / analyzer / all' >&2;exit 2;; esac
if [[ $EV_SETUP == 1 || $EV_SETUP_ONLY == 1 ]]; then bash scripts/bootstrap.sh "$EV_SERVICE"; fi
if [[ $EV_SETUP_ONLY == 1 ]]; then exit 0; fi
EV_LAUNCH_SERVICE="$EV_SERVICE";[[ "$EV_SERVICE" == all ]] && EV_LAUNCH_SERVICE=editor
EV_PYTHON="$PWD/services/$EV_LAUNCH_SERVICE/.venv/bin/python"
if [[ ! -x "$EV_PYTHON" ]]; then echo '선택한 서비스 환경이 없습니다. --skip-setup 없이 실행하세요.' >&2;exit 1; fi
exec "$EV_PYTHON" scripts/launch.py --service "$EV_SERVICE" "${EV_ARGS[@]}"
