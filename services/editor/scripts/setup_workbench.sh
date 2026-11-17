#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../../.."
EV_PROJECT_ROOT="$PWD"
NODE_BIN="${WORKBENCH_NODE:-$(command -v node || true)}"
if [[ ! -x "$NODE_BIN" ]]; then echo 'Node.js가 없습니다. bash start.sh를 실행하세요.'; exit 1; fi
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)' || { echo 'Node.js 22 이상이 필요합니다. WORKBENCH_NODE에 실행 파일을 지정하세요.'; exit 1; }
export PATH="$(dirname "$NODE_BIN"):$PATH"
if [[ ! -d services/editor/vendor/velxio/.git ]]; then
  mkdir -p services/editor/vendor
  git clone --filter=blob:none --no-checkout https://github.com/davidmonterocrespo24/velxio.git services/editor/vendor/velxio
  git -C services/editor/vendor/velxio checkout 3aba596b8243398e27f4a70ca6f77426f70bab4f
  git -C services/editor/vendor/velxio apply ../../patches/velxio-embedded.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-structure-edit.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-motion-bridge.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-robot-code.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-code-translation.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-rover-tabs.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-pot-live-control.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-photo-autorun.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-system-translation.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-action-layout.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-side-tools.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-physical-models.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-photo-structures.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-assembly.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-whole-structure.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-loading.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-object-lock.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-selection-card.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-context-tools.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-functional-environment.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-watering-circuit.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-enclosure-analysis.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-functional-build.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-photo-appearance.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-photo-explode.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-connected-wiring.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-photo-mount.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-view-animation.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-complete-runtime.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-multiboard-workflow.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-system-conversion-v2.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-portable-conversion.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-toolbar-cards.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-independent-editor.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-arduino-lessons.patch
  git -C services/editor/vendor/velxio apply ../../patches/velxio-compact-toolbars.patch
fi
# Check the newest patch first because it changes context used by older patches.
if ! git -C services/editor/vendor/velxio apply --reverse --check ../../patches/velxio-compact-toolbars.patch 2>/dev/null; then
# A later patch can alter earlier patch context. Check the newest state first.
if ! git -C services/editor/vendor/velxio apply --reverse --check ../../patches/velxio-arduino-lessons.patch 2>/dev/null; then
  if ! git -C services/editor/vendor/velxio apply --reverse --check ../../patches/velxio-independent-editor.patch 2>/dev/null; then
    if git -C services/editor/vendor/velxio apply --check ../../patches/velxio-independent-editor.patch; then
      git -C services/editor/vendor/velxio apply ../../patches/velxio-independent-editor.patch
    else
      echo '기존 편집기 변경을 보존했습니다. README의 벤더 백업·재구성 절차를 확인하세요.' >&2
      exit 1
    fi
  fi
  if git -C services/editor/vendor/velxio apply --check ../../patches/velxio-arduino-lessons.patch; then
    git -C services/editor/vendor/velxio apply ../../patches/velxio-arduino-lessons.patch
  else
    echo '학습 가이드 패치 충돌: 기존 변경을 보존했습니다. 벤더 백업·재구성 절차를 확인하세요.' >&2
    exit 1
  fi
fi
  if git -C services/editor/vendor/velxio apply --check ../../patches/velxio-compact-toolbars.patch; then
    git -C services/editor/vendor/velxio apply ../../patches/velxio-compact-toolbars.patch
  else
    echo '도구 모음 패치 충돌: 기존 변경을 보존했습니다. 벤더 백업·재구성 절차를 확인하세요.' >&2
    exit 1
  fi
fi
mkdir -p services/editor/vendor/velxio/frontend/public/physical-models
cp shared/data/physical-models/* services/editor/vendor/velxio/frontend/public/physical-models/
cp shared/data/environment-objects.json services/editor/vendor/velxio/frontend/src/components/circuitiny/environmentPresets.json
cp shared/data/watering-parts.json services/editor/vendor/velxio/frontend/src/data/wateringParts.json
if [[ ! -f services/editor/.tools/npm/bin/npm-cli.js ]]; then
  mkdir -p services/editor/.tools/npm
  curl -fsSL https://registry.npmjs.org/npm/-/npm-10.9.4.tgz -o services/editor/.tools/npm.tgz
  tar -xzf services/editor/.tools/npm.tgz -C services/editor/.tools/npm --strip-components=1
fi
cp services/editor/patches/velxio-package-lock.json services/editor/vendor/velxio/frontend/package-lock.json
cd services/editor/vendor/velxio/frontend
"$NODE_BIN" "$EV_PROJECT_ROOT/services/editor/.tools/npm/bin/npm-cli.js" ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund
"$NODE_BIN" scripts/copy-monaco.mjs
EV_NEXT_DIST="$PWD/.dist-next"
"$NODE_BIN" node_modules/vite/bin/vite.js build --outDir "$EV_NEXT_DIST"
"${EMBEDDED_EDITOR_PYTHON:-$EV_PROJECT_ROOT/services/editor/.venv/bin/python}" - <<'PYBUILD'
from pathlib import Path
import shutil,time
new=Path('.dist-next');old=Path('dist')
if old.exists():
 for p in (old/'assets').glob('*'):
  dest=new/'assets'/p.name
  if p.is_file() and not dest.exists():shutil.copy2(p,dest)
 backup=Path('.dist-backup-'+str(time.time_ns()));old.rename(backup)
new.rename(old)
# Compatibility for scripts predating service separation.
root=Path.cwd().parents[4]
legacy=root/'third_party/velxio'
legacy.parent.mkdir(exist_ok=True)
if not legacy.exists() and not legacy.is_symlink():legacy.symlink_to('../services/editor/vendor/velxio',target_is_directory=True)
PYBUILD

cd -- "$EV_PROJECT_ROOT"
"${EMBEDDED_EDITOR_PYTHON:-$EV_PROJECT_ROOT/services/editor/.venv/bin/python}" scripts/export_catalog.py
