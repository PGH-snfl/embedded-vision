#!/usr/bin/env bash
set +x
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077
planner_data_root="${EMBEDDED_VISION_DATA:-$PWD/.runtime}"
mkdir -p -- "$planner_data_root"
read -rsp 'OpenAI API 키를 붙여넣고 Enter: ' planner_secret
printf '\n'
if [[ -z "$planner_secret" || "$planner_secret" == *[[:space:]]* ]]; then
  echo '빈 값이나 공백이 포함된 키는 저장하지 않았습니다.'
  exit 1
fi
planner_key_tmp=$(mktemp "$planner_data_root/.openai-key.XXXXXX")
trap 'rm -f -- "$planner_key_tmp"; unset planner_secret' EXIT
printf '%s' "$planner_secret" > "$planner_key_tmp"
chmod 600 "$planner_key_tmp"
mv -f -- "$planner_key_tmp" "$planner_data_root/openai-api-key"
unset planner_secret
printf '서버용 키를 소유자만 읽는 파일에 저장했습니다. 웹에서 상태 새로고침을 누르세요.\n'
printf '기존 OPENAI_API_KEY 환경변수가 있으면 해당 값이 우선합니다.\n'
