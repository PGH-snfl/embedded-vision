#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
# Use the project's pinned Velxio Three.js/esbuild; no network access needed.
services/editor/vendor/velxio/frontend/node_modules/.bin/esbuild services/analyzer/frontend/rover-src/simulator.js --bundle --format=esm --minify --legal-comments=inline --outfile=services/analyzer/frontend/rover-simulator.js
mkdir -p services/analyzer/frontend/licenses
cp services/editor/vendor/velxio/frontend/node_modules/three/LICENSE services/analyzer/frontend/licenses/three-MIT.txt
