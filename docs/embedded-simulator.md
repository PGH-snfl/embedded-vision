# UNO 임베디드 시스템 시뮬레이터

현재 지원은 **Arduino UNO R3 + 10kΩ 저항 두 개의 분압 회로**다.
웹의 ③ 회로 제안 아래 임베디드 시스템 시뮬레이터 또는 생성된 프로젝트의
④ 결과 → 임베디드 실행에서 실행한다.

## 실행 구조

1. 동일 Circuit Graph의 연결·부품 사양을 확인한다.
2. ngspice DC 계산으로 A0의 정상 상태 전압을 얻는다.
3. 화면에 제공하는 것과 동일한 Arduino 소스를 공식 Arduino AVR core와 함께 컴파일한다.
4. ELF를 simavr ATmega328P(16MHz, AVcc=5V)에 적재한다.
5. ADC 변환 요청 때 계산한 전압을 ADC0에 전달한다.
6. 실제 AVR UART 출력 이벤트를 수집해 ADC값·비율·전압·반복 간격을 검사한다.
7. 결과와 원시 이벤트를 저장한다. 웹의 슬라이더/재생은 이 저장된 실행 기록을 보여준다.

회로와 펌웨어 간 연결은 **DC 정상 상태를 전달하는 단방향 연결**이다.
GPIO 피드백이 있는 양방향 회로 연동이나 SPICE와 MCU의 시간 동기화는 구현하지 않았다.
Arduino API를 Python/JavaScript 함수로 흉내 내는 방식이 아니다.

## 시험 모드

- 현재 회로: ngspice가 계산한 2.5V를 ADC0에 연결한다.
- ADC 입력 시험: 0~500ms에 1.25V, 500~1000ms에 2.5V, 이후 3.75V를 가상 ADC 핀에 넣는다.
  이것은 코드의 입력 응답 시험이며 10kΩ 분압 회로가 해당 파형을 출력했다는 뜻이 아니다.

가상 실행 시간은 1.5초(24,000,000 CPU cycles)로 고정한다.
실제 UART에서 현재 회로는 `511,0.4995,2.498`을 약 200ms마다 출력했다.
10비트 ADC가 전압을 정수로 바꾸며 생기는 양자화 때문에 이상적인 2.5V와 출력 추정치가 약간 다르다.
입력 시험에서는 raw값이 255 → 511 → 767로 바뀌었다.

## 파일과 API

- `backend/emulator/toolchain.py`: 프로젝트 내부 AVR 툴체인·Arduino core 컴파일
- `backend/emulator/uno_runner.c`: simavr ADC/UART 연결 및 제한된 CPU 실행
- `backend/emulator/service.py`: SPICE 입력, 컴파일, 실행, 결과 검사 및 해시
- `backend/emulator/routes.py`: 새 회로 제안/저장된 설계용 API
- `frontend/emulator.js`: 가상 UNO, 시리얼 모니터, 기록 재생

`GET/POST /api/projects/{project}/inventory/{plan}/emulator`
`GET/POST /api/projects/{project}/emulator`

POST에는 `expected_revision`과 `scenario`(`circuit` 또는 `input_steps`)만 허용한다.
외부 C++ 소스, ELF, 임의 MCU, 실행 명령, 무제한 실행 시간을 받지 않는다.
입력 revision·Graph 해시·펌웨어 해시·툴체인 해시·실행 구현 해시가 달라지면 이전 결과를 재사용하지 않는다.
컴파일/실행 실패 후 이전 PASS를 최신 결과로 보여주지 않는다. 원래 사진이나 KiCad 파일은 수정하지 않는다.

실행 결과는 `.runtime/emulations/{project}/inventory/{plan}/{run_id}/` 또는
`.runtime/emulations/{project}/r{revision}/{run_id}/`에 보존한다.
`firmware.cpp`, `firmware.elf`, `firmware.hex`, `events.jsonl`, `result.json`, SPICE 입력/결과를 포함한다.

## 로컬 도구 구성

Ubuntu Jammy amd64에서 `bash scripts/setup_avr.sh`로 재구성한다.
공식 Ubuntu 저장소 패키지를 `.tools/avr/` 안에 다운로드·압축 해제하며 sudo나 전역 설치를 사용하지 않는다.
호스트 C 컴파일러, libelf 런타임, 프로젝트 Python 환경이 필요하다.

사용 버전: simavr 1.6, AVR GCC 5.4, Arduino AVR core 1.8.4, avr-libc 2.0.
최신 upstream을 임의로 섞지 않고 현재 OS 저장소에서 제공하는 조합으로 실제 컴파일·실행을 검증했다.
패키지 파일 SHA256은 `.tools/avr/manifest.json`에 기록한다.

오픈소스 출처·라이선스:
- https://github.com/buserror/simavr — GPL-3.0. 헤더/라이브러리로 연결한 `uno_runner.c`도 GPL-3.0-or-later 표기.
- https://github.com/arduino/ArduinoCore-avr — 공식 AVR core. 배포물의 개별 라이선스/저작권 고지를 유지한다.
- https://ngspice.sourceforge.io/shared.html — 공유 라이브러리 회로 계산.
패키지 저작권 원문은 `.tools/avr/root/usr/share/doc/`에 보존되어 있다.
재배포 시 각 의존성의 소스 제공 등 라이선스 조건을 함께 검토해야 한다.

## 검증 결과 및 한계

전체 테스트 **227개 통과**. 실제 AVR 실행으로 두 시험 모드를 통과했다.
A0 대신 A1을 읽도록 바꾼 음성 테스트는 FAIL, C++ 문법 오류는 컴파일 실패로 처리했다.
원시 이벤트가 없거나 검토되지 않은 배선, 오래된 입력, 임의 소스 요청은 통과시키지 않는다.

ESP32/Pico, LCD/모터, 사용자가 편집한 임의 코드, 부트로더, USB 인터페이스, ADC 잡음·공차·부하,
실제 조립 및 부품 정격 검증은 미지원이다. 가상 MCU PASS는 실물 안전·작동을 보증하지 않는다.
