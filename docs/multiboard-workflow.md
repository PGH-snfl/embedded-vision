# 보드별 공통 워크플로우 v3

편집기에서 [시스템 전환](system-conversion.md)으로 현재 회로·코드를 다른 보드로 함께 변경할 수 있다. 새 결과는 원본과 별도의 초안으로 연다.

사진 구성품 → 기능 → 보드·필수 부품 선정 → 데이터시트 → 회로·배선·코드 → 구조·장착 → 편집·조립 가이드 → 입력 조작 → 실행 검사·저장.

관측한 보드가 기능에 맞으면 우선 유지한다. 가려진 제어기는 새 설계의 선정값으로 결정한다. 보드 변경은 코드 문자열 번역으로 처리하지 않으며 GPIO 배정, 전원, 구동 회로, 언어, 실행기, 시험 조건을 함께 구성한다. 다른 보드의 설계가 잘못됐다고 UNO 예제를 자동 대입하지 않는다.

| 선정 보드 | 생성 코드 | 편집·배선·장착·가이드 | 실제 코드 실행 |
|---|---|---|---|
| Arduino UNO | Arduino C++ `sketch.ino` | 공통 편집기 | 로컬 AVR + ngspice |
| Raspberry Pi Pico RP2040 | MicroPython `main.py` | 공통 편집기 | 로컬 RP2040 + ngspice |
| ESP32 DevKit V1 | MicroPython `main.py` | 공통 편집기 | ESP32 QEMU 서비스 연결 필요 |
| Raspberry Pi 4B | Linux Python `main.py` | 공통 편집기 | QEMU·Linux 이미지·GPIO 서비스 연결 필요 |

Pico와 Linux Raspberry Pi는 서로 다른 보드다. Pi에는 임의의 A0를 만들지 않는다. 3.3V GPIO에 5V 신호를 직접 연결하지 않도록 설계 지침을 제공한다. 이 지침은 범용 전기 안전 검사를 대체하지 않는다.

## 실행 규칙과 결과

- `data/board-profiles.json`: 보드 ID, 표시 핀, 언어, 파일명, 전압, ADC, 실행기, 필요한 서비스, 참고 문서의 공통 원본.
- `/api/workflow`: 프로파일을 포함한 공통 워크플로우와 해시. 사진/영상 분석의 같은 모델 호출에 전달한다.
- `/api/board-profiles`: 보드별 지원 정보. SaaS에서는 `/api/w/{workspace}/board-profiles`.
- `/api/board-profiles/{board}/example`: 보드별 버튼 LED 예제. 관측된 원본이나 사용자의 분석 결과가 아니다.
- `evBoardRuntime`: 설계 시 실행 상태는 `not_run`. 실제 검사 후 보드에 실행·전기·입출력 결과와 `evSimulationVerification`을 저장한다. 프로파일의 지원 선언은 PASS가 아니다.
- UNO/Pico의 자동 시험은 실제 코드와 별도 가상 CPU, ngspice를 사용한다. 키보드·버튼·센서 조작과 기존 구조·배선 보기를 공유한다.
- ESP32/Pi는 현재 로컬 서버에 전용 서비스가 없으므로 실행 버튼에서 필요한 서비스를 설명한다. 회로/코드 편집은 가능하다. 실행 완료로 표시하지 않는다.

## 검증 예제

[웹에서 보드별 예제 열기](http://127.0.0.1:8897/board-workflow.html). 메인 화면의 ‘예제 열기 → 보드별 공통 워크플로우’에서도 접근한다. 네 보드는 같은 버튼→LED 기능을 서로 다른 핀과 코드로 구성한다. Pico는 실제 배포 MicroPython UF2, LittleFS WASM, RP2040 CPU와 ngspice로 실행한다. 단순 규칙 계산이나 Python 코드 문자열 검사가 아니다.

`tests/test_multiboard_workflow.py`는 네 보드의 단일 사진 호출 계약·회로·코드·장착·데이터시트·API를 확인한다. `multiboard-functional.test.ts`는 Pico 버튼→LED 및 ADC→PWM 밝기 제어를 실제 실행한다. 실물 검증, 임의 사진의 인식 정확도, 무선 통신 및 Linux/ESP32 실행은 이 검증에 포함하지 않는다. 새 유료 AI 호출과 기존 분석의 일괄 재생성은 수행하지 않는다.

2026-11-10 검증: 관련 서버 검사 73개, 편집기 검사 88개 통과. 마지막 AVR 실행 루프 변경 뒤 AVR 검사 9개를 추가 재검사해 통과했다. Pico는 부팅 후 마지막 500ms를 측정하며 버튼 해제/ADC 최소에서 LED 0A, 버튼 누름/ADC 최대에서 약 4.87mA를 측정했다. UNO 버튼 예제도 실제 격리 컴파일에 성공했다. Vite 배포 빌드 성공. 전체 TypeScript 검사는 기존 오류 359개가 남아 있으며 이번 변경으로 추가된 오류는 0개다.

로컬 8897·8766 및 SaaS 8770의 같은 워크플로우 해시, 네 보드 예제, 페이지 응답을 확인했다. 편집기 8768·SaaS의 Pico 펌웨어 SHA256도 일치한다. 서버·작업자 재시작 전후 기존 입력/분석 파일 139개가 동일함을 확인했다. 벤더 패치 30개를 기반 소스부터 재적용해 233개 파일 일치를 확인했다. 증거는 `outputs/multiboard-workflow/`에 저장했다. 브라우저 조작은 CUA의 `Cannot read properties of undefined (reading 'timeoutMs')` 오류로 확인하지 못했으며 HTTP 확인과 실제 회로 실행 검사를 브라우저 화면 확인으로 표시하지 않는다.

## 참고 자료

- [Raspberry Pi Pico 데이터시트](https://datasheets.raspberrypi.org/pico/pico-datasheet.pdf)
- [Pico와 Linux Pi의 차이](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
- [Raspberry Pi GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio)
- [Espressif GPIO 기능](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html)

표시 핀과 좌표는 저장소의 기존 보드 요소를 기준으로 하며, ESP32 DevKit V1과 DevKitC의 헤더를 동일한 제품으로 취급하지 않는다. Pico 일반형은 기존 Pico W 그림을 공유하는 제한이 있다. 일반 Pico 프로파일에서 무선 기능을 제공하지 않는다.
