#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
# Use the project's pinned Velxio Three.js/esbuild; no network access needed.
third_party/velxio/frontend/node_modules/.bin/esbuild frontend/rover-src/simulator.js --bundle --format=esm --minify --legal-comments=inline --outfile=frontend/rover-simulator.js
mkdir -p frontend/licenses
cp third_party/velxio/frontend/node_modules/three/LICENSE frontend/licenses/three-MIT.txt
