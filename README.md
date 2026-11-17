# Embedded Editor / Analyzer

**회로·배선·코드·3D 편집기**를 기본 서비스로 실행합니다. 사진·영상 분석기는 별도 서비스입니다. 같은 저장소에서 코드·실행 환경·화면을 분리했고, 부품·보드 데이터와 회로 형식만 공용으로 사용합니다.

[HTML 튜토리얼](https://pgh-snfl.github.io/embedded-vision/) · [서비스 분리 설명](docs/service-separation.md) · [오픈소스 출처](THIRD_PARTY_NOTICES.md)

## 편집기 시작

자동 설치 검증 대상은 **Ubuntu 22.04 x86_64 데스크톱**입니다. 인터넷과 curl이 필요하며 부족한 시스템 패키지는 sudo 비밀번호를 요청할 수 있습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/PGH-snfl/embedded-vision/main/install.sh | bash
```

`~/embedded-vision`에 설치한 뒤 **편집기만** 실행하고 <http://127.0.0.1:8768/>을 엽니다. 처음에는 Python·Node·편집기·UNO 컴파일러 다운로드와 빌드 시간이 필요합니다. 분석용 OCR·영상 패키지와 분석 서버는 설치·실행하지 않습니다. Windows/macOS/ARM은 이 설치기로 검증하지 않았습니다.

이미 설치했다면:

```bash
cd "$HOME/embedded-vision"
bash services/editor/start.sh
```

프로젝트의 `bash start.sh`도 같은 편집기 실행 명령입니다. 홈에서 **아두이노 편집기 열기** 또는 **프로젝트 파일 불러오기**를 선택합니다. API 키 없이 예제를 편집하고 UNO 코드를 실행할 수 있습니다. 종료는 실행한 터미널의 **Ctrl+C**입니다.

## 아두이노 따라 하기 예제

홈에서 LED 깜빡이기·밝기 조절·버튼 LED·조도 센서 자동 조명·LCD 표시 예제 5개를 선택할 수 있습니다. **가이드와 함께 열기 → ① 준비물 → ② 배선 → ③ 실행 확인**으로 진행합니다. 회로·코드가 미리 입력되고 배선 그림·3D 핀 강조·직접 확인 체크·코드 해설을 제공합니다. [자세한 사용법](docs/arduino-lessons.md).

## 서비스 디렉터리

```text
services/
  editor/       회로·코드·3D 편집기, 컴파일 서버, 패치, 전용 Python 환경
    web/        독립 편집기 홈
    frontend/   설치된 Velxio frontend를 가리키는 링크
    vendor/     설치 시 생성하는 Velxio 소스·의존성 (공개 제외)
    patches/    재현 가능한 편집기 수정
    scripts/    편집기·AVR 설치
  analyzer/     사진·영상 분석 API, 분석 화면, 전용 Python 환경
shared/
  backend/      공통 회로·설계·보드 전환·시뮬레이션 모듈
  data/         보드·부품 목록, 예제, 워크플로우
backend/        기존 Python import 경로를 유지하는 호환 링크
scripts/        서비스 선택 설치·실행, 튜토리얼 생성
```

각 서비스의 `start.sh`, `app.py`, `requirements.lock.txt`, `.venv/`가 독립적입니다. 분석기를 끄거나 설치하지 않아도 편집기 기본 작업이 가능합니다. 공용 코드 때문에 아직 두 개의 독립 저장소는 아닙니다. 이전 `frontend/`, `data/`, `patches/` 경로는 호환 링크로 남겼습니다.

## 분석기는 필요할 때 실행

별도 터미널에서:

```bash
cd "$HOME/embedded-vision"
bash services/analyzer/start.sh
```

분석기 주소는 <http://127.0.0.1:8766/>입니다. 사진의 **관측 부품 → 기능 추론 → 부족한 부품 보완 → 시스템 데이터시트 → 회로·코드·구조물**을 생성합니다. 분석 결과 `.vlx`는 편집기 홈에서 불러올 수 있습니다. 기존 분석 화면의 편집기 직접 열기도 유지했습니다.

사진 AI 분석에는 서버용 API 키가 필요합니다. 새 터미널에서 숨김 입력합니다.

```bash
bash services/analyzer/configure_openai.sh
```

키는 기본 `.runtime/openai-api-key`에 소유자만 읽도록 저장합니다. `OPENAI_API_KEY` 환경변수가 우선합니다. 키를 대화·소스·HTML에 넣지 마세요. 사진/영상 프레임의 AI 분석과 AI 코드 작성은 외부 API를 호출하며 비용이 발생할 수 있습니다. 재시작·프로젝트 가져오기는 사진 재분석을 시작하지 않습니다.

기본 편집기는 키 없이 동작합니다. 선택적인 AI 코드 작성용 키는 `bash services/editor/configure_openai.sh`로 `.runtime/editor/openai-api-key`에 저장합니다. 기존 공용 키가 있으면 편집기도 호환해서 읽습니다. 분석 중간 메모는 자유 형식, 최종 통합 결과만 JSON으로 검증하는 규칙은 유지합니다.

## 실행·저장 설정

```bash
bash start.sh --setup-only                 # 편집기 설치만
bash start.sh --skip-setup --no-open        # 준비된 편집기 실행
bash start.sh --service analyzer           # 분석기만
bash start.sh --service all                # 두 서비스 함께
bash start.sh --help
```

별도 터미널에서 실행한 서비스는 각각 종료합니다. `all` 모드에서는 한 서비스가 종료돼도 나머지를 유지하며, Ctrl+C로 실행기가 시작한 서비스들을 종료합니다. 기존 서버는 강제 종료하지 않습니다.

- 편집기 데이터: `.runtime/editor/` (`EMBEDDED_EDITOR_DATA`로 변경).
- 분석기 데이터: 기존 `.runtime/` 보존 (`EMBEDDED_ANALYZER_DATA` 또는 기존 `EMBEDDED_VISION_DATA`로 변경).
- 편집기 로그: `.runtime/launcher/editor.log`; 분석기 로그: `.runtime/launcher/analyzer.log`.
- 다른 포트: `EMBEDDED_VISION_EDITOR_PORT=8868 bash start.sh`. 분석기는 `EMBEDDED_VISION_PORT` 사용.
- 브라우저 자동 초안과 내려받은 `.vlx` 파일을 구분하세요. 편집기 홈에서 가져온 프로젝트 원본은 편집기 데이터 폴더에 보관합니다.

## 편집기 기능과 실행 범위

상단 도구는 프로젝트·실행·화면·저장 그룹으로 작게 배치하고, 상세 도구는 메뉴에서 펼칩니다. [도구 모음 구성](docs/compact-editor-toolbar.md).


회로·빵판·부품·배선과 코드 편집, 같은 장면의 2D/3D 보기, 구조물 조립·분해, 그래픽 조립 가이드, 기본 잠금과 선택 후 이동 활성화를 유지합니다. 보드 전환은 규칙으로 전원·핀·배선을 구성한 뒤 선택적으로 AI가 코드를 작성합니다.

**UNO는 로컬 AVR 컴파일·AVR8js 실행을 지원**합니다. ESP32·Pico·Linux Raspberry Pi는 설계·핀·언어 프로필을 제공하며 실제 펌웨어 실행에는 해당 실행 환경이 필요합니다. 기존 분석 프로젝트에 연결된 로봇 동작 미리보기 등은 분석기의 API를 추가로 사용할 수 있습니다. 회로 편집·UNO 실행은 분석기와 독립적입니다. KiCad/PCB 작업은 기본 실행에 포함하지 않습니다.

## 개발·업데이트

서비스별 Python 의존성은 각각 `services/*/requirements.lock.txt`, 편집기 npm 의존성은 `services/editor/patches/velxio-package-lock.json`으로 고정합니다. Velxio 고정 원본에 `services/editor/scripts/setup_workbench.sh`의 패치를 순서대로 적용합니다. 설치기는 기존 벤더 소스를 초기화하지 않습니다.

업데이트 전에 `git status --short`를 확인하고 `git pull --ff-only`하세요. 기존 벤더에 추가 패치를 반영해야 하면 서버를 종료하고 벤더를 백업한 뒤 재구성합니다.

```bash
mv services/editor/vendor/velxio "services/editor/vendor/velxio-backup-$(date +%Y%m%d-%H%M%S)"
bash services/editor/start.sh
```

백업에만 있는 사용자 변경은 비교·병합하세요. 구버전의 실제 `third_party/velxio` 설치본을 새 버전으로 옮기는 절차는 [서비스 분리 설명](docs/service-separation.md)에 있습니다. 테스트용 JS 의존성은 `npm ci --prefix tests`로 설치합니다.

공개 소스에는 사용자 업로드·키·`.runtime/`·`outputs/`·설치된 의존성을 포함하지 않습니다. 공개 예제 사진과 부품 자료의 출처·라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 따릅니다. AGPL-3.0.
