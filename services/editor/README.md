# 편집기 서비스

프로젝트 루트에서 `bash services/editor/start.sh`로 실행합니다. 기본 주소: http://127.0.0.1:8768/.

- `app.py`, `backend/workbench/`: 독립 HTTP API와 격리 UNO 컴파일.
- `web/`: 편집기 홈, 예제 선택, `.vlx` 파일 가져오기.
- `frontend -> vendor/velxio/frontend`: 2D·3D 회로·코드 UI.
- `patches/`, `scripts/`: 편집기 재현·설치.
- `requirements.lock.txt`, `.venv/`: 분석 패키지를 제외한 Python 실행 환경.

분석 서버·작업 큐·사진 입력을 시작하지 않습니다. `.vlx`의 보드·부품·배선·코드·구조물은 그대로 가져옵니다. 프로젝트 원본은 `EMBEDDED_EDITOR_DATA` (기본 `.runtime/editor`)에 보관하며 브라우저 초안과 파일 다운로드도 유지합니다.

공통 회로·보드 전환은 `shared/`에 있습니다. 기존 분석 프로젝트의 외부 동작 미리보기는 분석기 API가 필요할 수 있습니다. UNO 컴파일·회로 편집은 독립적으로 동작합니다.

홈의 ‘아두이노 따라 하기 예제’에서 LED·버튼·센서·LCD 학습 프로젝트를 엽니다. 사용법은 [학습 가이드](../../docs/arduino-lessons.md), 설명 데이터는 `data/arduino-lessons.json`입니다.
