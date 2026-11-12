# Circuitiny 3D Arduino 편집기 통합

2026-10-28. 공개 저장소의 실제 소스와 라이선스를 확인한 뒤, Circuitiny의 3D 편집부를 현재 Velxio 웹 편집기에 이식했다. 완성된 Arduino용 Circuitiny 앱을 통째로 설치한 것은 아니다.

## 선정 근거

| 후보 | 확인된 기능 | 적용 판단 |
|---|---|---|
| [Circuitiny](https://github.com/mfranzon/circuitiny) · MIT | React Three Fiber 기반 3D 부품 선택·이동, 핀 선택 배선, 곡선 점퍼선. 원본은 Electron·ESP32·ESP-IDF 중심 | 3D 편집 소스 채택, UNO/기존 실행기에 맞게 변환 |
| [ohmlet](https://github.com/JENW1N/ohmlet) · MIT | 3D 빵판, 아날로그·디지털 소자 시뮬레이션. README에서 마이크로컨트롤러 미지원 명시 | Arduino 실행 기능을 직접 제공하지 않아 이번 통합에는 미채택 |
| [Breadboard-3D](https://github.com/RephilStudios/Breadboard-3D) | 3D 빵판 프로젝트 공개 | 확인한 저장소 루트에 명시적 라이선스가 없어 소스 이식 미채택 |
| [SparkBench](https://github.com/photon-cat/sparkbench) | AVR 실행 및 3D PCB 보기 | 편집 가능한 3D 빵판 요구와는 범위가 달라 미채택 |

Circuitiny 고정 커밋: `008c5f815f506da863e06f4239361c87aa42c060`.
ohmlet 조사 커밋: `02a5a72183d1630ff3d52a122414f44feb47fcce`.
원본은 각각 `third_party/circuitiny`, `third_party/ohmlet`에 보관했다. ohmlet 코드를 앱에 포함하지 않았다.

## 기능 확장

전체 부품 목록, 속성·핀 정보, 회전·복사, 빵판 회전, 배선 경유점·분기점, 센서 조작, 실제 LCD 화면과 파형 측정까지 확장했다. 최신 기능과 검증은 [2D/3D 기능 연동](3d-feature-parity.md)을 기준으로 한다.

## 초기 통합 기능

사진 분석 ③에서 **Velxio 그래픽 편집기 열기 → 3D 편집**.

- 부품을 클릭해 이동 화살표를 드래그하거나 2.54mm 한 칸 이동 버튼 사용.
- 미니 빵판을 옮기면 꽂힌 부품도 함께 이동. 부품 이동 시 실제 구멍에 맞추고 삽입 연결을 갱신.
- **핀 연결**에서 실제 3D 핀 두 개를 클릭하거나 시작/도착 핀 목록으로 연결.
- **＋ 저항 / ＋ LED**, 저항값 변경, 부품·점퍼선 삭제.
- **되돌리기 / 다시 적용**, 위·입체 시점, 화면 맞춤, 기존 2D 편집 전환.
- 기존 코드 편집·실제 AVR 컴파일·가상 MCU 실행·UART 출력 유지.
- 편집은 네이티브 프로젝트에 반영되어 브라우저 자동 저장과 `.vlx` 다운로드에 포함.

점퍼와 부품 다리가 이미 사용 중인 구멍에 겹치거나 전원–GND를 직접 잇는 배선은 거절한다. 이 검사는 모든 회로의 전기적 안전을 보장하는 ERC가 아니다. 코드 실행 중에는 3D 회로 편집을 막는다.

## 구조와 원본 재사용

`Circuitiny Viewer3D + project types/pin resolver → bridge.ts → Velxio native store/history → native electrical engine + AVR8js/ngspice`

`third_party/velxio/frontend/src/components/circuitiny/`:

- `Viewer3D.tsx`: 원본의 부품 선택, TransformControls, 핀 선택, 곡선 배선 렌더링을 실제 재사용.
- `project/`: 원본 스키마·부품 타입·핀 resolver. UNO target 및 숨김 삽입 연결 추가.
- `catalog.ts`, `EmbeddedBodies.tsx`: 네이티브 실제 핀 좌표와 UNO·미니 빵판·저항 형상 연결.
- `bridge.ts`: 실제 native wire CRUD, 구멍 중복/단락 검사, 이동·빵판 삽입 갱신, 원자적 Undo/Redo.
- `CircuitinyEditor.tsx`: 한국어 버튼, 핀 목록, 부품 속성, 배선 목록.
- `LICENSE`: Circuitiny 원본 MIT 고지 유지. 화면에도 원본 링크 표시.

3D 뒤의 네이티브 2D 컴포넌트를 유지해 핀 좌표·전기 엔진을 공유한다. LED 표시에는 ngspice 전류를 사용하며 깜빡임을 별도 타이머로 조작하지 않는다. 이식 원본의 Electron IPC, AI 에이전트, ESP-IDF 컴파일러, HAL 기반 native ESP32 실행기, 원본 ESP32 전용 DRC는 연결하지 않았다. 기존 사진 분석 모델 구성도 변경하지 않는다.

## 초기 통합 당시 범위와 제한

초기 버전의 3D 편집 지원은 **Arduino UNO R3 + 170구 미니 빵판 + 회전하지 않은 저항/LED**. 로컬 펌웨어 컴파일은 UNO와 기본 Arduino 코어 및 같은 프로젝트 소스만 지원한다. ESP32·Pico 실행과 임의 부품의 3D 모델은 지원하지 않는다. 3D에서 제외되는 부품은 안내하고 전체 회로는 2D에서 확인한다.

CAD/STEP 모델이나 기계 공차 검증이 아니다. 편집 결과는 원본 사진 분석 Circuit Graph나 KiCad에 자동 역반영되지 않는다. 실제 조립·정격·전원·실물 작동 확인은 별도다. Velxio 수정본의 AGPL-3.0 조건도 계속 적용된다.

## 초기 통합 검증

- 관련 프런트엔드 테스트 **90개 통과(4파일)**: 실제 wire 수정·Undo/Redo, 핀 별칭, 전원–GND 단락 차단, 사용 중 구멍 차단, 부품 이동과 삽입 연결의 원자적 복원, 새 LED 등록, 실행 중 편집 차단, 기존 빵판·LED·3D 모델 회귀.
- Vite production build 성공. 전체 upstream TypeScript 검사는 기존 오류로 실패하며, 새 Circuitiny 모듈의 오류는 없다.
- 실제 브라우저: UNO D6→빵판 A6 추가 후 2→3 점퍼 증가와 Undo 확인. 빵판 x=400→409.6px 한 칸 이동 및 Undo 후 400px 복원 확인. 실제 이동 화살표 드래그도 x=418.867px 이동 후 Undo로 400px 복원 확인. LED 추가 후 Undo 확인.
- 독립 검증 예제에서 실제 Arduino 코드 컴파일·실행, UART의 `LED ON/OFF`, 3D `D1 켜짐/꺼짐`, 실행 중 편집 차단과 정지 후 편집 복귀 확인. 5초 간격으로도 코드를 수정·재실행해 LED 상태를 확인한 뒤 원래 0.5초 코드로 복원.
- 기존 사용자 편집 세션은 초기화하지 않았다. 유료 모델 호출과 새 사진 분석 없이 검증.

증거: `outputs/circuitiny-editor/validation.vlx`, `editor.jpg`, `wiring.jpg`, build/test 로그.

재설치용 변경은 `patches/velxio-embedded.patch`, 의존성 잠금은 `patches/velxio-package-lock.json`에 포함한다. Circuitiny 원본을 별도로 설치·실행할 필요 없이 기존 `scripts/setup_workbench.sh`로 구성한다. React Three Fiber 9.6.0, Drei 10.7.7, Three 0.186.1을 고정했다.
