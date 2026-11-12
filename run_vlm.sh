#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
runtime=".runtime/vlm/runtime/llama-b11669/llama-server"
models=".runtime/vlm/models"
if [[ ! -x "$runtime" || ! -f "$models/Qwen3-VL-2B-Instruct-Q8_0.gguf" ]]; then
  echo "모델/실행 파일이 없습니다. docs/camera-vision.md의 설치 안내를 확인하세요."
  exit 1
fi
.venv/bin/python - <<'PY'
from pathlib import Path
import os,secrets
p=Path('.runtime/vlm/api-key')
if not p.exists():
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
PY
exec "$runtime" -m "$models/Qwen3-VL-2B-Instruct-Q8_0.gguf" \
  --mmproj "$models/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf" \
  --alias Qwen3-VL-2B-Instruct-Q8_0 --host 127.0.0.1 --port 8768 \
  -c 4096 -t 4 -tb 4 --parallel 1 -ngl 0 --no-webui \
  --api-key-file .runtime/vlm/api-key --cors-origins http://127.0.0.1:8766 \
  --image-min-tokens 1024 --image-max-tokens 1280
