# MCU 시간에 맞춘 LED 밝기 갱신

2026-10-28. 화면용 50ms 폴링과 PWM 입력의 16ms 지연을 제거했다.

## 바뀐 동작

`CPU 사이클 → PWM duty + guest timestamp → 실제 SPICE 전류 → 공통 LED 출력 이벤트 → 2D / 3D`

- AVR 프레임 실행은 명령어 개수가 아니라 실제 CPU 사이클을 기준으로 한다. 여러 사이클이 필요한 명령어 때문에 프로그램 시간이 빨라지던 문제를 수정했다. 첫 프레임에서 임의의 50ms를 미리 실행하지 않는다. 속도 배율과 사이클 초과분도 반영한다.
- Uno의 PWM 모니터는 Arduino `analogWrite(0)` / `analogWrite(255)`가 비교 출력을 해제하는 경우 실제 출력 포트 수준을 읽어 끝값을 전달한다. 오래된 OCR 레지스터 값을 계속 사용하지 않는다.
- 모든 PWM duty 이벤트를 MCU timestamp와 함께 전달한다. 16ms 뒤 최신 값만 읽어 전체 회로를 다시 구성하던 경로를 제거했다.
- **한 보드 + LED 하나 + 저항·빵판의 정적 회로**는 SPICE에서 실제 OFF/ON 전류를 풀어 둔다. 준비가 끝나면 `Imean = (1-duty) × |Ioff| + duty × |Ion|`으로 각 MCU 출력 이벤트를 즉시 계산한다. duty 자체를 전류로 간주하거나 임의의 LED 점등을 만들지 않는다. 전압/전류 표시에도 평균 결과를 게시한다.
- 커패시터·인덕터·트랜지스터 등 동적 소자가 있는 회로, 여러 보드/LED/동시 PWM은 위 정적 근사를 적용하지 않는다. 기존 시간선·일반 회로 해석 경로를 이용한다. 이 경로의 모든 중간 밝기를 MCU 갱신률로 표시한다고 주장하지 않는다.
- 두 상태의 전류를 계산하는 첫 준비 중에는 최신 요청을 보존하며, 뒤늦게 도착한 이전 값으로 화면을 되돌리지 않는다. 회로 변경·정지 시 캐시를 무효화한다.
- 원래 2D LED 출력에서 공통 이벤트를 발생시킨다. 3D는 이 이벤트를 즉시 받아 같은 밝기와 timestamp를 사용하며, 별도 표시 타이머나 보간 애니메이션으로 주기를 바꾸지 않는다.
- `LED 밝기 · D1 …% · MCU 20.2ms (49.5Hz)`로 계산된 갱신 간격을 표시한다. `delay(20)` 외의 명령과 시리얼 출력도 실행 시간이 필요하므로 MCU의 실제 간격은 정확히 20.000ms와 다를 수 있다.
- 전기 해석에서 계산한 시간 평균 창(window)과 전원 정보를 프런트엔드 상태로 전달하는 어댑터의 누락도 수정했다.

## 검증

- 관련 **261개 테스트 / 15파일 통과**, production build 성공.
- 실제 Arduino 코어로 기존 밝기 조절 코드를 컴파일한 HEX를 이용했다. 0.5× / 1× / 2×에서 guest time과 wall-frame budget, `delay(20)` PWM 이벤트 간격, 0/255 끝값을 검증했다. 기존 AVR·ATtiny·시리얼·PinManager·회로 해석·편집 테스트도 통과했다.
- SPICE 상태 준비 후 20ms 간격의 51개 이벤트가 추가 solver 호출이나 타이머 진행 없이 즉시 게시되는지 검증했다. 준비 중 최신 값, 역순 timestamp, 정지 후 늦은 결과, 동적 소자 회로의 일반 경로도 검증했다.
- 실제 2D LED 핸들러를 통해 51개 출력 이벤트가 3D에 즉시 전달되며 같은 guest timestamp·밝기를 가지는지 확인했다.
- 실제 브라우저에서 생성된 UNO 밝기 코드를 컴파일·실행해 MCU 갱신 **약 20.2ms / 49.5Hz**를 확인했다.
- 전체 upstream TypeScript 검사에는 기존 오류가 남아 있다. 이번에 추가한 출력 이벤트·타이밍 테스트·3D 연결에는 오류가 없다.

## 표시의 물리적 한계

MCU의 PWM 점멸 주파수와 밝기 값의 갱신 주기는 다르다. 이 예제의 밝기 값은 대략 50Hz로 바뀌며, 더 빠른 PWM 펄스는 평균 밝기를 결정한다. 브라우저/모니터는 매 디스플레이 프레임에 최신 값을 그린다. 주사율보다 빠른 모든 중간 값을 각각 눈에 보이게 그릴 수는 없다. CPU가 빨라진 척하거나 느린 결과를 일정 속도로 재생해 시간축을 맞추지 않는다. 브라우저가 백그라운드이거나 부하가 높으면 실제 시간 대비 실행 속도가 낮아질 수 있다.

## 파일

- `third_party/velxio/frontend/src/simulation/AVRSimulator.ts`: 사이클 예산·PWM 끝값.
- `simulation/spice/CircuitSimulationService.ts`, `connectMcuEdgesToService.ts`, `start.ts`: MCU 이벤트·전류 캐시·상태 전달.
- `simulation/ledOutput.ts`, `simulation/parts/BasicParts.ts`: 공통 LED 출력 이벤트.
- `components/circuitiny/`: 타이머 없는 출력 반영과 주기 표시.
- `outputs/mcu-timing/validation.vlx`: 독립 예제. 사용자 프로젝트를 덮어쓰지 않았다.
- `outputs/mcu-timing/`: 실제 컴파일 결과, 테스트·빌드 로그, 브라우저 검증과 화면.
- 재설치 패치: `patches/velxio-embedded.patch`.
