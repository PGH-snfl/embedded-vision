#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
NODE_BIN="${WORKBENCH_NODE:-$(command -v node || true)}"
if [[ ! -x "$NODE_BIN" ]]; then echo 'Node.js가 없습니다. bash start.sh를 실행하세요.'; exit 1; fi
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)' || { echo 'Node.js 22 이상이 필요합니다. WORKBENCH_NODE에 실행 파일을 지정하세요.'; exit 1; }
export PATH="$(dirname "$NODE_BIN"):$PATH"
if [[ ! -d third_party/velxio/.git ]]; then
  mkdir -p third_party
  git clone --filter=blob:none --no-checkout https://github.com/davidmonterocrespo24/velxio.git third_party/velxio
  git -C third_party/velxio checkout 3aba596b8243398e27f4a70ca6f77426f70bab4f
  git -C third_party/velxio apply ../../patches/velxio-embedded.patch
  git -C third_party/velxio apply ../../patches/velxio-structure-edit.patch
  git -C third_party/velxio apply ../../patches/velxio-motion-bridge.patch
  git -C third_party/velxio apply ../../patches/velxio-robot-code.patch
  git -C third_party/velxio apply ../../patches/velxio-code-translation.patch
  git -C third_party/velxio apply ../../patches/velxio-rover-tabs.patch
  git -C third_party/velxio apply ../../patches/velxio-pot-live-control.patch
  git -C third_party/velxio apply ../../patches/velxio-photo-autorun.patch
  git -C third_party/velxio apply ../../patches/velxio-system-translation.patch
  git -C third_party/velxio apply ../../patches/velxio-action-layout.patch
  git -C third_party/velxio apply ../../patches/velxio-side-tools.patch
  git -C third_party/velxio apply ../../patches/velxio-physical-models.patch
  git -C third_party/velxio apply ../../patches/velxio-photo-structures.patch
  git -C third_party/velxio apply ../../patches/velxio-assembly.patch
  git -C third_party/velxio apply ../../patches/velxio-whole-structure.patch
  git -C third_party/velxio apply ../../patches/velxio-loading.patch
  git -C third_party/velxio apply ../../patches/velxio-object-lock.patch
  git -C third_party/velxio apply ../../patches/velxio-selection-card.patch
  git -C third_party/velxio apply ../../patches/velxio-context-tools.patch
  git -C third_party/velxio apply ../../patches/velxio-functional-environment.patch
  git -C third_party/velxio apply ../../patches/velxio-watering-circuit.patch
  git -C third_party/velxio apply ../../patches/velxio-enclosure-analysis.patch
  git -C third_party/velxio apply ../../patches/velxio-functional-build.patch
  git -C third_party/velxio apply ../../patches/velxio-photo-appearance.patch
  git -C third_party/velxio apply ../../patches/velxio-photo-explode.patch
  git -C third_party/velxio apply ../../patches/velxio-connected-wiring.patch
  git -C third_party/velxio apply ../../patches/velxio-photo-mount.patch
  git -C third_party/velxio apply ../../patches/velxio-view-animation.patch
  git -C third_party/velxio apply ../../patches/velxio-complete-runtime.patch
  git -C third_party/velxio apply ../../patches/velxio-multiboard-workflow.patch
  git -C third_party/velxio apply ../../patches/velxio-system-conversion-v2.patch
  git -C third_party/velxio apply ../../patches/velxio-portable-conversion.patch
  git -C third_party/velxio apply ../../patches/velxio-toolbar-cards.patch
fi
mkdir -p third_party/velxio/frontend/public/physical-models
cp data/physical-models/* third_party/velxio/frontend/public/physical-models/
cp data/environment-objects.json third_party/velxio/frontend/src/components/circuitiny/environmentPresets.json
cp data/watering-parts.json third_party/velxio/frontend/src/data/wateringParts.json
if [[ ! -f .tools/npm/bin/npm-cli.js ]]; then
  mkdir -p .tools/npm
  curl -fsSL https://registry.npmjs.org/npm/-/npm-10.9.4.tgz -o .tools/npm.tgz
  tar -xzf .tools/npm.tgz -C .tools/npm --strip-components=1
fi
cp patches/velxio-package-lock.json third_party/velxio/frontend/package-lock.json
cd third_party/velxio/frontend
"$NODE_BIN" ../../../.tools/npm/bin/npm-cli.js ci --legacy-peer-deps --ignore-scripts --no-audit --no-fund
"$NODE_BIN" scripts/copy-monaco.mjs
"$NODE_BIN" node_modules/vite/bin/vite.js build
