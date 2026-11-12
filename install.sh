#!/usr/bin/env bash
# Public entry point: download to a file, then execute, or pipe into bash.
set -euo pipefail
EV_REPO_URL="https://github.com/PGH-snfl/embedded-vision.git"
EV_INSTALL_DIR="${EMBEDDED_VISION_INSTALL_DIR:-$HOME/embedded-vision}"
if ! command -v git >/dev/null; then
  echo 'git 설치가 필요합니다. Ubuntu에서 sudo 비밀번호를 요청할 수 있습니다.'
  if [[ $(id -u) -eq 0 ]]; then apt-get update; apt-get install -y git ca-certificates;
  else sudo -v </dev/tty; sudo apt-get update; sudo apt-get install -y git ca-certificates; fi
fi
if [[ -e "$EV_INSTALL_DIR" ]]; then
  if [[ ! -d "$EV_INSTALL_DIR/.git" ]] || [[ $(git -C "$EV_INSTALL_DIR" remote get-url origin) != "$EV_REPO_URL" ]]; then
    echo "기존 경로를 덮어쓰지 않습니다: $EV_INSTALL_DIR" >&2; exit 1
  fi
  echo "기존 설치를 사용합니다: $EV_INSTALL_DIR (자동 pull/초기화 없음)"
else
  git clone --depth 1 "$EV_REPO_URL" "$EV_INSTALL_DIR"
fi
exec bash "$EV_INSTALL_DIR/start.sh" "$@"
