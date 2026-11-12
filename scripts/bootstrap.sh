#!/usr/bin/env bash
# Install only the requested service; editor never installs the analyzer stack.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
EV_SERVICE="${1:-editor}"
if [[ "$EV_SERVICE" == all ]]; then bash "$0" editor; exec bash "$0" analyzer; fi
if [[ "$EV_SERVICE" != editor && "$EV_SERVICE" != analyzer ]]; then echo '서비스: editor / analyzer / all' >&2; exit 2; fi
if [[ $(uname -m) != x86_64 || ! -f /etc/os-release ]]; then echo '자동 설치 대상: Ubuntu 22.04 x86_64' >&2; exit 1; fi
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 22.04 ]]; then echo '자동 설치는 Ubuntu 22.04 x86_64에서 검증합니다.' >&2; exit 1; fi
umask 077
EV_PROJECT_ROOT="$PWD"
EV_SERVICE_ROOT="$PWD/services/$EV_SERVICE"
EV_VENV="$EV_SERVICE_ROOT/.venv"
mkdir -p "$EV_SERVICE_ROOT/.tools" .tools .runtime/launcher
EV_PACKAGES=(git curl ca-certificates xdg-utils)
if [[ "$EV_SERVICE" == editor ]]; then EV_PACKAGES+=(build-essential bubblewrap libelf1);
else EV_PACKAGES+=(ffmpeg libglib2.0-0 libgl1 libgomp1 libngspice0); fi
EV_MISSING=()
for package in "${EV_PACKAGES[@]}"; do
  if [[ "$package" == libngspice0 ]] && ldconfig -p 2>/dev/null | grep 'libngspice.so.0 .*x86-64' >/dev/null; then continue; fi
  if ! dpkg-query -W -f='${Status}\n' "$package" 2>/dev/null | grep -x 'install ok installed' >/dev/null; then EV_MISSING+=("$package"); fi
done
if (( ${#EV_MISSING[@]} )); then
  echo "시스템 의존성: ${EV_MISSING[*]}"
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
if [[ ! -x "$EV_VENV/bin/python" ]]; then "$EV_UV" venv --python 3.12 "$EV_VENV"; fi
EV_LOCK="$EV_SERVICE_ROOT/requirements.lock.txt"
EV_PY_HASH=$(sha256sum "$EV_LOCK" | cut -d' ' -f1)
if [[ ! -f "$EV_SERVICE_ROOT/.tools/python-ready" ]] || [[ $(cat "$EV_SERVICE_ROOT/.tools/python-ready") != "$EV_PY_HASH" ]]; then
  "$EV_UV" pip sync --python "$EV_VENV/bin/python" "$EV_LOCK"
  printf '%s' "$EV_PY_HASH" > "$EV_SERVICE_ROOT/.tools/python-ready"
fi
if [[ "$EV_SERVICE" == analyzer ]]; then
  "$EV_VENV/bin/python" -c 'from services.analyzer.app import app; print("분석기 설치 완료. 편집기·Node·AVR 설치는 실행하지 않았습니다.")'
  exit 0
fi
export EMBEDDED_EDITOR_PYTHON="$EV_VENV/bin/python"
"$EV_VENV/bin/python" scripts/migrate_editor_layout.py
EV_NODE="${WORKBENCH_NODE:-$(command -v node || true)}"
if [[ ! -x "$EV_NODE" ]] || ! "$EV_NODE" -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||a===22&&b>=12?0:1)' 2>/dev/null; then
  EV_NODE="$EV_SERVICE_ROOT/.tools/node/bin/node"
  if [[ ! -x "$EV_NODE" ]]; then
    EV_NODE_VERSION=v22.16.0;EV_ARCHIVE="node-$EV_NODE_VERSION-linux-x64.tar.xz"
    curl -fsSL "https://nodejs.org/dist/$EV_NODE_VERSION/$EV_ARCHIVE" -o "$EV_SERVICE_ROOT/.tools/$EV_ARCHIVE"
    curl -fsSL "https://nodejs.org/dist/$EV_NODE_VERSION/SHASUMS256.txt" -o "$EV_SERVICE_ROOT/.tools/node-shasums.txt"
    (cd "$EV_SERVICE_ROOT/.tools"; awk -v name="$EV_ARCHIVE" '$2==name' node-shasums.txt > node-selected.sha256; test -s node-selected.sha256; sha256sum --check node-selected.sha256)
    mkdir -p "$EV_SERVICE_ROOT/.tools/node";tar -xJf "$EV_SERVICE_ROOT/.tools/$EV_ARCHIVE" -C "$EV_SERVICE_ROOT/.tools/node" --strip-components=1
  fi
fi
export WORKBENCH_NODE="$EV_NODE"
EV_EDITOR_HASH=$(cat services/editor/scripts/setup_workbench.sh services/editor/patches/*.patch services/editor/patches/velxio-package-lock.json shared/data/environment-objects.json shared/data/watering-parts.json shared/data/physical-models/* | sha256sum | cut -d' ' -f1)
if [[ ! -f services/editor/vendor/velxio/frontend/dist/index.html || ! -f "$EV_SERVICE_ROOT/.tools/editor-ready" ]] || [[ $(cat "$EV_SERVICE_ROOT/.tools/editor-ready" 2>/dev/null || true) != "$EV_EDITOR_HASH" ]]; then
  bash services/editor/scripts/setup_workbench.sh
  printf '%s' "$EV_EDITOR_HASH" > "$EV_SERVICE_ROOT/.tools/editor-ready"
fi
if [[ ! -f "$EV_SERVICE_ROOT/.tools/avr/manifest.json" ]]; then bash services/editor/scripts/setup_avr.sh; fi
"$EV_VENV/bin/python" - <<'PY'
from backend.emulator.toolchain import prepare
prepare()
print('편집기 설치 완료: 자체 Python 환경 / 2D·3D UI / UNO 컴파일러. 분석기는 시작하지 않습니다.')
PY
