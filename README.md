# Embedded Vision

사진·영상의 **구성품 목록 → 기능 추론 → 부족한 부품 보완 → 시스템 데이터시트 → 회로·배선·코드 → 3D 편집·조립 가이드 → 사용자 조작 시뮬레이션**을 연결하는 웹 프로토타입입니다.

**[단계별 HTML 튜토리얼](https://pgh-snfl.github.io/embedded-vision/)** · [튜토리얼 원본](tutorial.html) · [공통 워크플로우](docs/common-workflow.md) · [오픈소스 출처](THIRD_PARTY_NOTICES.md)

## 한 명령으로 설치·실행

자동 설치 검증 대상: **Ubuntu 22.04 x86_64 데스크톱**. 인터넷과 `curl`이 필요합니다. 부족한 시스템 패키지는 sudo 비밀번호를 요청할 수 있습니다. Windows/macOS/ARM/다른 Ubuntu 버전은 이 설치기로 검증하지 않았습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/PGH-snfl/embedded-vision/main/install.sh | bash
```

`~/embedded-vision`에 소스를 복제하고 Python 3.12, Node.js, 편집기 의존성, UNO 컴파일러를 준비한 다음 브라우저를 엽니다. **처음에는 다운로드·빌드 시간이 필요합니다.** 설치 스크립트의 내용을 먼저 보려면 [install.sh](install.sh)와 [bootstrap.sh](scripts/bootstrap.sh)를 확인하세요. KiCad 설치는 기본 실행에 필요하지 않습니다.

- 사진 입력 화면: <http://127.0.0.1:8766/>
- 회로·코드·3D 편집기: <http://127.0.0.1:8768/editor>
- 설치·사용 튜토리얼: <http://127.0.0.1:8766/tutorial>
- 종료: 실행한 터미널에서 **Ctrl+C**. 실행기가 시작한 두 서버만 종료하며 데이터는 보존합니다.

다음 실행:

```bash
cd "$HOME/embedded-vision" && bash start.sh
```

이미 해당 경로가 있으면 설치기는 저장소 출처를 확인해 기존 설치를 실행합니다. 자동 `pull`, 초기화, 사용자 파일 덮어쓰기를 하지 않습니다. 사용자 지정 설치 경로는 `EMBEDDED_VISION_INSTALL_DIR`로 설정할 수 있습니다.

Git으로 직접 받으려면:

```bash
git clone https://github.com/PGH-snfl/embedded-vision.git "$HOME/embedded-vision"
cd "$HOME/embedded-vision"
bash start.sh
```

## 먼저 API 키 없는 예제 확인

상단 **예제 둘러보기 → 보드별 공통 워크플로우 → Arduino UNO → 회로·코드·시뮬레이터 열기**를 선택합니다. 편집기에서 코드를 실행하고 입력 부품을 조작해 출력을 확인하세요. 내장 보드 예제는 유료 AI 분석을 호출하지 않습니다. **실제 촬영 사진 분석** 버튼은 AI 호출을 하는 별도 경로입니다.

HTML 파일을 직접 열어도 목차·테마·명령어 보기·명령어 복사가 동작합니다. 버튼은 명령을 복사하며, 사용자가 터미널에 붙여넣어 실행합니다.

## 사진·영상 AI 분석

새 터미널에서 키를 숨김 입력합니다. 키를 채팅·HTML·소스에 넣지 마세요.

```bash
cd "$HOME/embedded-vision" && bash configure_openai.sh
```

키는 `.runtime/openai-api-key`에 소유자만 읽도록 저장합니다. 환경변수 `OPENAI_API_KEY`가 있으면 그 값이 우선합니다. 키를 저장한 뒤 웹에서 상태를 갱신하고 입력하세요. **입력 이미지/영상 프레임은 OpenAI API로 전송되며 계정의 비용이 발생합니다.**

현재 모델 ID는 `backend/planner/selection.py`의 Sol `gpt-6.1-sol`, Astra `gpt-6-astra`입니다. 사용자 계정에서 해당 모델의 접근 권한과 크레딧이 필요합니다. 기본 분석과 필요한 심화 검토를 분리하며 모델 선택 버튼도 제공합니다. 접근 불가·잔액 부족을 분석 성공으로 처리하거나 다른 모델로 몰래 바꾸지 않습니다. JSON 출력 형식의 준수는 회로의 사실 정확도를 보장하지 않습니다.

사진은 관측 부품부터 분석하고 원본 영역 확대·후보 재검토·누락/중복 검사를 진행합니다. 그 뒤 기능을 추론하고 새 설계에 필요한 부품을 채웁니다. 관측 사실, 추론, 새 설계 선정값을 구분합니다. 숨겨진 원본 배선을 정확히 복원하는 기능으로 보장하지 않습니다.

## 편집기와 실행 범위

- 회로·빵판 배선, 코드 편집, 부품 추가, 핀 연결, 그래픽 조립 가이드.
- 같은 장면의 수직 2D 보기와 3D 회전, 구조물 조립·분해·회로 보기, 장착 부품과 함께 움직이는 배선.
- 기본 잠금과 선택 카드의 명시적 이동 활성화. 상단 기능별 카드와 접을 수 있는 상세 도구.
- 보드 전환은 규칙으로 회로·전원·핀·배선을 먼저 바꾸고 AI는 확정된 하드웨어에 맞는 코드를 작성합니다.
- **UNO:** 로컬 AVR 컴파일, AVR8js 코드 실행, 지원 소자에 대한 ngspice 전기 계산.
- **ESP32 / Pico / Linux Raspberry Pi:** 설계·핀·언어 프로필이 있습니다. 해당 펌웨어의 실행에는 별도 실행 서비스가 필요하며 기본 설치의 UNO 로컬 컴파일러로 대신 실행하지 않습니다.
- 로봇·급수 등 가상 환경의 동작 미리보기는 실제 역학·비행·물리·전력 검증과 다릅니다. 모든 사진의 자동 실행 성공이나 원본과 동일한 내부를 보장하지 않습니다. 최종 실물 조립·검증은 사용자가 수행합니다.

KiCad·ERC/DRC·추가 SPICE 모듈과 SaaS 기초 코드도 포함합니다. 기본 설치의 목적은 **웹 편집기와 시뮬레이터**입니다. KiCad/PCB는 선택적인 후속 작업이며 설치기가 실행하지 않습니다. 호스팅용 SaaS 구성은 [SaaS 문서](docs/saas-architecture.md)와 `deploy/`를 참고하세요. 로컬 기본 실행은 로그인 없이 `127.0.0.1`에만 바인딩합니다.

## 실행 옵션과 문제 해결

```bash
bash start.sh --setup-only             # 설치만
bash start.sh --skip-setup --no-open   # 준비된 환경, 브라우저 자동 열기 생략
bash start.sh --help
```

기존 포트를 강제로 종료하지 않습니다. 충돌하면 다른 포트로 실행하세요.

```bash
EMBEDDED_VISION_PORT=8866 EMBEDDED_VISION_EDITOR_PORT=8868 bash start.sh
```

브라우저가 자동으로 열리지 않으면 터미널에 출력한 주소를 직접 여세요. 별도 데이터 경로를 쓰려면 `EMBEDDED_VISION_DATA=/절대/경로`를 서버와 `configure_openai.sh`에 똑같이 지정합니다. `.env.example`은 변수 설명용이며 실행기가 임의의 `.env`를 shell로 실행하지 않습니다.

로그:

```bash
tail -n 60 .runtime/launcher/analysis.log .runtime/launcher/editor.log
curl -fsS http://127.0.0.1:8766/api/health
curl -fsS http://127.0.0.1:8768/api/health
```

`bwrap` 오류는 운영체제의 격리 실행 설정을 확인하세요. 컴파일 격리를 끄는 우회는 설치기에 넣지 않았습니다. API 401은 키, 403/404는 모델 접근, 429는 잔액·요청 한도 등을 확인합니다. 과거 분석 결과를 열거나 서버를 재시작하는 것만으로 유료 재분석하지 않습니다.

## 구조와 설치 방식

```text
backend/        FastAPI, vision, planner, circuit, design, workbench, simulation, saas
frontend/       사진·영상 입력, 단계별 분석, 데이터시트·가이드
patches/        고정 Velxio 원본에 적용하는 편집기 수정 + npm lockfile
data/           부품·보드 프로필, 공통 워크플로우, 공개 예제·출처
scripts/        로컬 설치, 실행기, 편집기·AVR 준비, 튜토리얼 생성
tests/          Python / JavaScript 자동 검증
licenses/       재사용 소스의 원본 라이선스
docs/           기능 설명과 개발 기록
```

Velxio 원본 커밋 `3aba596b8243398e27f4a70ca6f77426f70bab4f`를 다운로드하고 `scripts/setup_workbench.sh`에 명시한 패치를 순서대로 적용합니다. 원본·의존성·빌드 결과는 `third_party/`, `.tools/`, `.venv/`에 생성하고 저장소에는 넣지 않습니다. Python 의존성은 `requirements.lock.txt`, 편집기 의존성은 `patches/velxio-package-lock.json`으로 고정합니다.

### 업데이트와 기존 편집기 보존

`git status --short`로 수정 여부를 확인한 뒤 `git pull --ff-only`하세요. 설치기는 기존 벤더 소스를 초기화하지 않습니다. 새 편집기 패치가 추가된 버전으로 업데이트했다면 기존 변경을 보존한 채 명시적으로 재구성합니다. 실행 중인 서버를 종료하고 다음을 실행하세요.

```bash
mv third_party/velxio "third_party/velxio-backup-$(date +%Y%m%d-%H%M%S)"
bash start.sh
```

백업에만 있는 사용자 변경은 비교·병합한 뒤 사용하세요. 설치 중 다운로드나 패치 적용이 중단돼 불완전한 checkout이 생긴 경우도 같은 방식으로 보존 후 재구성합니다. `git reset --hard`로 사용자의 편집기 변경을 지우지 않습니다.

개발용 수동 단계: Python 3.12 가상환경에 `requirements.lock.txt` 설치 → Node 22.12 이상을 `WORKBENCH_NODE` 또는 PATH에 준비 → `bash scripts/setup_workbench.sh` → `bash scripts/setup_avr.sh` → `bash start.sh --skip-setup`. 수동 단계도 AVR 패키지 때문에 Ubuntu 22.04 x86_64를 기준으로 합니다.

## 공개 범위·검증·라이선스

공개 소스에는 구현 코드·편집기 패치·문서·테스트·출처가 있는 예제를 포함합니다. **사용자 업로드, API 키, `.runtime/`, `outputs/`, 로그, 의존성 설치본은 제외**합니다. `data/photos/arduino-camera.jpg`는 CC BY-SA 3.0 공개 예제이며 [원작자·수정 내역](data/photos/ATTRIBUTION.md)을 유지합니다.

[릴리스 설치 검증 기록](docs/public-release-validation.md)은 이번 설치·실행 검사의 범위를 기록합니다. 과거 문서는 당시 구현과 테스트의 기록이며 일부 `outputs/` 참조는 공개하지 않은 로컬 증거입니다. 현재 처리 규칙은 [공통 워크플로우](docs/common-workflow.md)와 `data/workflows/photo-system-v1.json`을 우선합니다.

AGPL-3.0. 기존 MIT 소스·CC BY-SA 사진/보드 자료의 별도 라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 확인하세요.
