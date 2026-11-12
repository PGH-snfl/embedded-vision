#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [[ $(uname -m) != x86_64 ]] || [[ ! -f /etc/os-release ]]; then
  echo '현재 자동 설치 대상: Ubuntu 22.04 x86_64. 다른 환경은 README 수동 설치를 확인하세요.' >&2; exit 1
fi
. /etc/os-release
if [[ $ID != ubuntu || $VERSION_ID != 22.04 ]]; then
  echo '이 설치기는 Ubuntu 22.04에서 검증합니다. 다른 배포판에 Jammy 패키지를 설치하지 않습니다.' >&2; exit 1
fi
umask 077
mkdir -p .tools .runtime/launcher
EV_PACKAGES=(git curl ca-certificates build-essential bubblewrap libngspice0 libgl1 libglib2.0-0 libgomp1 libelf1 ffmpeg xdg-utils)
EV_MISSING=()
for package in "${EV_PACKAGES[@]}"; do
  if [[ "$package" == libngspice0 ]] && ldconfig -p 2>/dev/null | grep 'libngspice.so.0 .*x86-64' >/dev/null; then continue; fi
  if ! dpkg-query -W -f='${Status}\n' "$package" 2>/dev/null | grep -x 'install ok installed' >/dev/null; then EV_MISSING+=("$package"); fi
done
if (( ${#EV_MISSING[@]} )); then
  echo "시스템 의존성을 설치합니다: ${EV_MISSING[*]}"
  if [[ $(id -u) -eq 0 ]]; then apt-get update; apt-get install -y "${EV_MISSING[@]}";
  else sudo -v </dev/tty; sudo apt-get update; sudo apt-get install -y "${EV_MISSING[@]}"; fi
fi
EV_UV="$(command -v uv || true)"
if [[ -z "$EV_UV" && -x "$HOME/.local/bin/uv" ]]; then EV_UV="$HOME/.local/bin/uv"; fi
if [[ -z "$EV_UV" ]]; then
  if [[ ! -x .tools/uv/uv ]]; then
    curl -fsSL https://astral.sh/uv/0.12.21/install.sh -o .tools/install-uv.sh
    UV_INSTALL_DIR="$PWD/.tools/uv" UV_NO_MODIFY_PATH=1 sh .tools/install-uv.sh
  fi
  EV_UV="$PWD/.tools/uv/uv"
fi
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
if [[ ! -x .venv/bin/python ]]; then "$EV_UV" venv --python 3.12 .venv; fi
EV_PY_HASH=$(sha256sum requirements.lock.txt | cut -d' ' -f1)
if [[ ! -f .tools/python-ready ]] || [[ $(cat .tools/python-ready) != "$EV_PY_HASH" ]]; then
  "$EV_UV" pip sync --python .venv/bin/python requirements.lock.txt
  printf '%s' "$EV_PY_HASH" > .tools/python-ready
fi
EV_NODE="${WORKBENCH_NODE:-$(command -v node || true)}"
if [[ ! -x "$EV_NODE" ]] || ! "$EV_NODE" -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||a===22&&b>=12?0:1)' 2>/dev/null; then
  EV_NODE="$PWD/.tools/node/bin/node"
  if [[ ! -x "$EV_NODE" ]]; then
    EV_NODE_VERSION=v22.16.0
    EV_ARCHIVE="node-$EV_NODE_VERSION-linux-x64.tar.xz"
    curl -fsSL "https://nodejs.org/dist/$EV_NODE_VERSION/$EV_ARCHIVE" -o ".tools/$EV_ARCHIVE"
    curl -fsSL "https://nodejs.org/dist/$EV_NODE_VERSION/SHASUMS256.txt" -o .tools/node-shasums.txt
    (cd .tools; awk -v name="$EV_ARCHIVE" '$2==name' node-shasums.txt > node-selected.sha256; test -s node-selected.sha256; sha256sum --check node-selected.sha256)
    mkdir -p .tools/node
    tar -xJf ".tools/$EV_ARCHIVE" -C .tools/node --strip-components=1
  fi
fi
export WORKBENCH_NODE="$EV_NODE"
EV_EDITOR_HASH=$(cat scripts/setup_workbench.sh patches/*.patch patches/velxio-package-lock.json data/environment-objects.json data/watering-parts.json data/physical-models/* | sha256sum | cut -d' ' -f1)
if [[ ! -f third_party/velxio/frontend/dist/index.html || ! -f .tools/editor-ready ]] || [[ $(cat .tools/editor-ready 2>/dev/null || true) != "$EV_EDITOR_HASH" ]]; then
  bash scripts/setup_workbench.sh
  printf '%s' "$EV_EDITOR_HASH" > .tools/editor-ready
fi
if [[ ! -f .tools/avr/manifest.json ]]; then bash scripts/setup_avr.sh; fi
.venv/bin/python - <<'PY'
import ctypes
from backend.emulator.toolchain import prepare
ctypes.CDLL('libngspice.so.0')
prepare()
print('설치 완료: Python / 편집기 / UNO 컴파일러 / ngspice')
PY
