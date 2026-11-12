# 통합 프로토타입 0.2 — 2026-10-20 검증 기록

## 결과

기존 M1에 OCR, 핀 위치 기반 배선 후보, 영상 프레임 추출, 부품 카탈로그, KiCad/PCB 생성·검사, ngspice, Arduino 코드, 조립 안내, 제한된 자연어 명령을 연결했다. **ESP32 LED/버튼과 RC 필터의 명시적 설계 예제**가 검증 대상이다. 실제 사용자 사진을 완전히 복원한 결과는 아니다.

자동 테스트 **53 passed, 1 warning**. 경고는 Starlette TestClient의 httpx 사용 중단 예고이며 테스트 실패가 아니다. 실제 KiCad와 libngspice를 호출했고 모의 PASS/가짜 파형을 사용하지 않았다.

## 검증한 경로

| 대상 | 검증 |
|---|---|
| ESP32 LED/버튼 | Graph → 편집 가능한 schematic → KiCad가 추출한 netlist와 연결 집합 대조 PASS → ERC 0건 → PCB 생성 → DRC 0건 |
| RC 필터 | 같은 생성·검사 경로 PASS. PCB pad별 net이 회로도 매핑과 일치함을 대조 |
| RC 시뮬레이션 | DC 입력/출력 일치, AC 이론 전달함수와 오차 1e-6 이하, 실제 transient 출력 변화 |
| ESP32 근사 모델 | 실제 ngspice 계산 LED 전류가 테스트 범위 1~15 mA 안에 있음. GPIO는 이상적 신호원, LED는 일반 근사 모델 |
| OCR | 설치된 RapidOCR ONNX 모델로 합성 이미지의 ESP32 표식 인식. 부품 후보는 INFERRED, 연결 자동 확정 0개 |
| 배선 | 선명한 색상 선 + 사용자 핀 위치로 INFERRED 후보 생성. 모호한 핀/중복 연결은 배제 |
| 영상 | 실제 AVI 디코딩, 시간순 주요 프레임 최대 6개 추출 |
| 저장·API | 수정 충돌, 원본 보존, 잘못된 입력 거절, 여러 사진의 근거 분리, 값 변경 후 재계산과 이전 검사 결과 무효화 |
| 안전 조건 | 미확인 연결, 전원 단락, 지원 예제와 다른 토폴로지, 범위를 벗어난 저항값의 생성/해석 차단 |
| 펌웨어 | GPIO23 LED / GPIO18 버튼 계약과 `.ino` 소스 생성. 보드 컴파일·실행은 미검증 |

검증 환경: Python 3.12.14, KiCad CLI/pcbnew 10.0.6, RapidOCR ONNX Runtime 1.4.4. Python 의존성은 `requirements.lock.txt`에 고정했다.

## 브라우저 검증

Chrome에서 로컬 앱을 열어 다음을 확인했다.

- ESP32/RC 예제 생성, 연결/ERC/DRC PASS 표시, 실제 회로도/PCB SVG 로딩.
- RC transient 762개 표본, AC 301개 표본의 두 채널 표시.
- `차단 주파수를 1kHz로 맞춰` 명령으로 R1=1591.54943 Ω 변경, 리비전 2 저장, 실제 파형 재계산.
- Arduino 코드 생성·다운로드 링크, GPIO 명령 매핑, 버튼 조작에 따른 LED ON 설명을 확인했다. 최종 화면의 브라우저 오류 로그는 없었다.
- 업로드 데이터 검증은 API 테스트로 수행했다. 브라우저 자동 파일 업로드는 확장의 로컬 파일 접근 설정 때문에 검증하지 않았으며 해당 설정을 변경하지 않았다.

화면 기록: `integrated-rc.jpg`, `integrated-esp32.jpg`. 서버 주소: http://127.0.0.1:8766.

## 산출물

`outputs/integrated-2026-10-20/esp32_led_button/` 및 `rc_filter/`에 다음을 저장했다.

- `reference.png`: 관측 사진이 아닌 설계 예시 그림.
- `circuit-graph.json`: 상태·핀·연결·출처가 있는 공통 데이터.
- `tutorial.json`: 연결 단계, 물리 핀, 이유, 확인 사항.
- `kicad/project.zip`: 회로도·PCB·프로젝트·매핑·연결·ERC/DRC 보고서.
- `simulation/`: 실제 입력 deck 및 계산 결과. ESP32는 transient/DC, RC는 transient/AC/DC.
- ESP32의 `esp32_led_button.ino`: 버튼 입력으로 LED를 제어하는 코드.

생성은 **파일/CLI 방식**이다. KiCad GUI를 실시간 편집하거나 MCP PCB 동기화 도구를 실행했다고 주장하지 않는다. PCB의 연결은 회로도에서 KiCad가 내보낸 netlist만 사용한다.

## 중요한 설계 경계

- CONFIRMED는 해당 근거 범위의 확정이다. 사용자 확인이나 예제 정의를 사진 인식 성공으로 치환하지 않는다. UNKNOWN 값·핀·내층을 임의로 채우지 않는다.
- OCR의 confidence는 문자 인식 원점수다. 실제 부품/연결 정확도를 뜻하는 보정 확률이 아니다.
- ESP32-DevKitC V4에 지정한 물리 핀: 3V3=J2.1, GND=J3.1, GPIO23=J3.2, GPIO18=J3.9. WROOM 표식만으로 DevKitC V4라 단정하지 않는다.
- PCB U1은 외부 4핀 헤더다. ESP32 개발보드를 장착하는 정확한 풋프린트로 오인하면 안 된다. `mapping.json`에 물리 핀과 PCB 헤더 핀을 분리한다.
- 헤더·수동소자 중심의 ERC는 MCU 출력 충돌·정격·열·부품 실물 차이를 모두 검증하지 않는다. DRC의 제조 간격 통과도 작동 보증이 아니다.
- 최대 6개 지원 부품을 위한 단순 2층 라우터다. 산업용 자동 배치·배선기 또는 일반 회로 설계 도구의 대체품이 아니다.
- Test Point 이름은 동일하지만 별도 측정용 패드를 추가하지 않았다. 전류 재생은 선택한 직렬 경로의 branch 결과이며 회로 전체 전류 해석 표시가 아니다. AC 화면은 전류 진폭만 표시한다.
- 스키마의 0.1.0 표기는 기존 저장 데이터 호환을 유지했다. 선택적 필드(프로필·자산·핀 위치·카탈로그·매개변수)를 확장했으며 제품 버전은 0.2다.

## 다음 개발 단계

1. 실제 ESP32/LED/버튼 사진의 단자·배선 정답을 수집하고 정확도·모호한 후보 거절률을 측정한다.
2. 보드/부품 검출, 브레드보드 행·전원 레일 도통, 가림/중첩 처리와 다중 시점 동일 부품 매칭을 추가한다.
3. 사진에서 검증한 회로를 지원 회로 프로필과 연결하고, 지원되지 않는 모델·핀·풋프린트 확인 화면을 확장한다.
4. 실제 부품·코드 컴파일·보드 업로드·측정 파형으로 시뮬레이션과 대조한다.
5. 범용 AI 모델은 관측 근거가 있는 변경 제안으로만 연결하고, 사용자 확인과 검사 계층을 유지한다. PCB 역설계는 그 이후 단계다.

## 1차 자료

- [Espressif ESP32-DevKitC V4](https://documentation.espressif.com/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html): 모델·헤더 핀 확인.
- [Espressif 회로도](https://dl.espressif.com/dl/schematics/esp32_devkitc_v4-sch-20180607a.pdf): 개발보드 회로 근거.
- [Kingbright WP7113ID](https://www.kingbrightusa.com/images/catalog/SPEC/WP7113ID.pdf): LED 패키지·정격 근거. 사용한 SPICE 다이오드 모델은 제조사 모델이 아니다.
- [Omron B3F](https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3f.pdf): 버튼 구조·치수 대조 자료.
- [KiCad schematic 파일 형식](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/): 파일 생성 형식.
- [RapidOCR 소스](https://github.com/RapidAI/RapidOCR): 로컬 OCR 기반.
