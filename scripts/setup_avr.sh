#!/usr/bin/env bash
# Project-local Ubuntu Jammy amd64 toolchain. No sudo or global package changes.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
mkdir -p .tools/avr/packages .tools/avr/root
(cd .tools/avr/packages && apt-get download 'gcc-avr=1:5.4.0+Atmel3.6.2-3' 'binutils-avr=2.26.20160125+Atmel3.6.2-4' 'avr-libc=1:2.0.0+Atmel3.6.2-3' 'libsimavr-dev=1.6+dfsg-3' 'libsimavr2=1.6+dfsg-3' 'arduino-core-avr=1.8.4+dfsg1-1' libelf-dev)
.venv/bin/python - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
root=Path('.tools/avr');manifest=[]
for package in sorted((root/'packages').glob('*.deb')):
    subprocess.run(['dpkg-deb','-x',str(package),str(root/'root')],check=True)
    manifest.append({'file':package.name,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()})
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
from backend.emulator.toolchain import prepare
prepare()
print('UNO compiler and simavr ready in .tools/avr')
PY
