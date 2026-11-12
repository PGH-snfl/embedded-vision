# 그래픽 회로·코드 편집기 — Velxio 통합

2026-10-27. 공식 저장소 중심으로 두 검색 흐름(웹 편집기, 대안 시뮬레이터)을 조사하고 실제 소스·빌드·브라우저 실행으로 선택을 검증했다.

## 선택

| 후보 | 장점 | 이번 요구에 대한 판단 |
|---|---|---|
| [Velxio](https://github.com/davidmonterocrespo24/velxio) | 웹 보드·부품·배선 편집, Monaco 코드 편집, AVR8js와 ngspice WASM 연결 | 채택. 원하는 작업을 한 화면에서 수행 가능 |
| [SimulIDE](https://github.com/SimulIDE/SimulIDE) | 회로·MCU·코드 편집을 갖춘 데스크톱 앱 | 웹에 직접 넣기보다 별도 데스크톱 도구에 적합 |
| [PICSimLab](https://github.com/lcgamboa/picsimlab) | 다양한 교육용 가상 보드와 주변 장치 | 공식 설명상 소스 코드 편집은 외부 IDE 사용 |
| [AVR8js](https://github.com/wokwi/avr8js) + [Wokwi elements](https://github.com/wokwi/wokwi-elements) | MIT 라이선스의 MCU 실행·시각 부품 라이브러리 | 완성된 회로 편집기와 코드 편집 기능을 별도로 구축해야 함 |

'가장 좋음'은 이번 웹 통합 요구 기준이다. 모든 보드 정확도나 모든 시뮬레이터의 우열을 뜻하지 않는다. 광고의 보드·부품 개수는 검증 수치로 사용하지 않았다. 공개 저장소에 있는 ngspice WASM을 실행했으며 별도 Pro overlay는 사용하지 않았다.

고정한 upstream commit: `3aba596b8243398e27f4a70ca6f77426f70bab4f`.

## 사용

1. `bash run.sh` — 사진 분석 서버, http://127.0.0.1:8766
2. 다른 터미널에서 `bash run_workbench.sh` — 편집기, http://127.0.0.1:8768/editor
3. 사진 분석 화면의 **③ 새 회로 구성 → Velxio 그래픽 편집기 열기**.
4. 왼쪽 코드 수정, 오른쪽 부품 우클릭으로 속성 변경, 핀 선택으로 배선 편집.
5. **▶ Run**으로 컴파일·실행. **Serial**에서 실제 가상 MCU 출력을 확인.
6. `.vlx 저장`으로 회로·배선·코드를 한 파일에 저장. 다시 열기는 폴더 아이콘.

사진에서 만든 회로는 새 탭으로 자동 전달된다. 분석 원본 배선을 복원하는 기능이 아니다. 사진의 저항값을 읽었다고 주장하지 않으며 10kΩ 두 개는 새 설계값이다.

## 구현 구조

`검증 가능한 부품 목록 → 제안 Circuit Graph → .vlx → Velxio stores → Monaco / board / wires → 격리 AVR 컴파일 → HEX → AVR8js ↔ ngspice WASM → UART`

- `backend/workbench/export.py`: 지원 회로와 연결을 검사하고 .vlx로 변환. 원본 Graph는 변경하지 않음. 오래된 분석은 409 반환.
- `frontend/workbench.js`: ③에서 열기·다운로드. 데이터는 URL fragment로 로컬 편집기에 전달하므로 HTTP 요청 로그에는 코드가 포함되지 않음.
- `third_party/velxio/frontend/src/components/EmbeddedVisionBridge.tsx`: 자동 가져오기, 분석 해시 + 설계 목표 버전 + 회로별 브라우저 저장·복원, 최초 제안 복원, 한국어 사용 순서.
- `backend/workbench/server.py`: 별도 localhost 서버. UNO 코드만 프로젝트 로컬 AVR 도구로 컴파일. bwrap으로 호스트 홈·분석 데이터·환경변수·네트워크를 분리, 실행시간·메모리 제한. 컴파일 실패는 새 실패 결과만 반환.
- `patches/velxio-embedded.patch`: upstream 변경 사항. `velxio-package-lock.json`으로 설치 버전 고정.

## 검증

- 브라우저에서 현재 사진의 부품 제안을 버튼 한 번으로 가져옴: UNO, 저항 2개, 연결 4개, Arduino 코드.
- 기본 10kΩ+10kΩ: 실제 컴파일 성공, 가상 MCU UART `512,0.5005,2.502` 확인. ADC 양자화로 이상적 2.500V와 작은 차이가 있음.
- 코드의 첫 메시지를 `EDIT_OK`로 수정하고 R1을 20kΩ으로 바꿈: 재컴파일 후 `EDIT_OK,ratio,estimated_voltage_V`, `341,0.3333,1.667` 확인. 미리 작성한 가짜 로그가 아님.
- 브라우저 새로고침 시 편집 내용 복원 확인.
- 전체 기존 테스트+초기 추가 테스트 233개 통과. 추가 API 테스트는 원본 불변·지원 범위·오래된 분석 차단을 검증.
- 소스 전체 TypeScript 검사에는 upstream 테스트 타입·미사용 변수 등의 오류가 남아 있다. 통합 모듈에 대한 오류는 없고 Vite 실제 빌드와 브라우저 경로는 성공했다. 전체 upstream 품질 검증 완료라고 주장하지 않는다.

## 현재 지원 범위

- 자동 변환·실행 검증: **Arduino UNO R3 분압 및 LED 지속 점등·깜빡임·밝기 조절 회로**.
- 편집기는 다른 보드도 표시하지만 이 로컬 컴파일 서버는 UNO만 지원한다. ESP32/Pico/QEMU, 외부 라이브러리 설치, 계정·클라우드 저장 기능은 연결하지 않았다.
- Arduino 기본 코어와 같은 폴더의 C/C++/헤더를 지원. .ino는 C++로 묶으며 Arduino IDE처럼 함수 선언을 자동 생성하지 않는다. 함수를 사용 위치보다 먼저 선언해야 한다. 외부 라이브러리는 현재 미지원.
- 자동 저장은 이 브라우저·이 원본 분석으로 연 편집 세션에 적용. `.vlx` 파일도 저장 권장. 그래픽 수정 결과를 기존 Circuit Graph나 KiCad에 자동으로 역반영하지 않는다.
- 시뮬레이션은 모델 범위의 계산이다. 실제 배선·전원 정격·보드 변형·부품 오차·실물 동작은 별도 확인 대상.

## 재설치 / 라이선스

`bash scripts/setup_avr.sh` 다음 `bash scripts/setup_workbench.sh`. Node.js 22 이상 필요; `WORKBENCH_NODE`에 실행 파일 경로 지정 가능. bwrap이 실행 불가능하면 컴파일은 실패 처리하며 격리를 해제하지 않는다.

Velxio는 [AGPLv3](https://github.com/davidmonterocrespo24/velxio/blob/master/LICENSE)이며 상용 이중 라이선스도 제공한다. 수정본 배포·네트워크 제공 시 해당 소스 제공 의무를 확인해야 한다. 원본 LICENSE와 공개 소스·수정 patch를 로컬에 유지한다. 프로토타입은 localhost에서 실행하며 클라우드 업로드나 유료 서비스를 사용하지 않는다.

LED 목표 선택·밝기 계산 연결 수정·실행 검증은 [goal-simulator.md](goal-simulator.md)에 기록했다.

사용자용 단계형 화면·접기/펼치기·실행 오류 표시 개선은 [simulator-friendly-ui.md](simulator-friendly-ui.md)를 참고한다.

[빵판 배치·3D 조립 보기 사용법](breadboard-3d.md)

[현재 3D 편집 기능과 Circuitiny 오픈소스 통합](circuitiny-integration.md): 부품 이동·핀 배선·추가·삭제·Undo/Redo와 실제 Arduino 실행.
