# 공개 소스 설치 검증 · 2026-11-12

이번 검증은 **Ubuntu 22.04 x86_64에서 공개할 소스만 복사한 별도 폴더**를 대상으로 했다. 기존 서비스·개인 업로드·분석 결과·API 키·기존 가상환경·벤더 설치본을 복사하지 않았다. 같은 호스트의 패키지·다운로드 캐시는 재사용할 수 있으므로 새 운영체제 전체를 설치한 검증과 구분한다.

## 확인한 결과

- Python 3.12 새 가상환경에 `requirements.lock.txt` 설치 성공.
- Node.js v22.16.0 공식 배포본 다운로드와 SHA256 확인 성공.
- 고정 Velxio 원본을 새로 내려받아 관리 패치 33개 적용, npm lockfile 설치, Monaco 복사와 Vite 프로덕션 빌드 성공.
- Ubuntu AVR·Arduino core·simavr 패키지를 프로젝트 안에 추출하고 코어/실행기 빌드 성공.
- 분석·편집기 서버를 기존 서비스와 다른 포트 18966/18968에서 실행. `/`, `/editor`, `/tutorial`, 두 `/api/health`, `/runtime-config.js` 응답 확인.
- 실제 UNO 점멸 코드를 HTTP 컴파일 API에 넣어 격리 컴파일 성공. HEX 2,948바이트 생성.
- 내장 UNO 예제의 부품 5개·배선 5개와 보드·코드 그룹 생성 확인.
- 설치 재실행 시 의존성 재설치·편집기 재빌드 없이 준비 결과를 재사용.
- Ctrl+C로 실행기가 시작한 두 서버 종료. 기존 8766/8768 등의 서버는 종료하지 않음.

## 자동 검사

```bash
.venv/bin/python -m pytest \
  tests/test_public_launcher.py \
  tests/test_goal_simulator.py \
  tests/test_embedded_emulator.py \
  tests/test_multiboard_workflow.py \
  tests/test_divider_simulation.py -q
```

**49개 통과.** 실제 simavr 명령 실행·ADC/UART/타이머·LED 밝기 동작, libngspice 분압 계산, 보드별 핀·언어·워크플로우, 포트 충돌 방지와 설정 전달을 포함한다. 테스트용 모델 응답을 사용하는 검사는 유료 AI 인식 성능 검사가 아니다. 별도로 기존 입력 보존·컴파일 API 관련 검사 12개도 통과했다(일부 검사 중복).

```bash
.tools/node/bin/node --test --test-reporter=spec \
  tests/tutorial.test.mjs tests/workbench-return-url.test.mjs
```

**4개 통과.** 명령어 펼치기·정확한 텍스트 복사·file:// 복사 대체 경로·테마 저장·목차 연결, 원래 분석 주소 유지와 사용자 지정 편집기 포트를 검사한다. 실제 브라우저 대신 jsdom DOM 환경에서 동작을 검증했다.

## 공개 주소에서 재설치 확인

실제 `raw.githubusercontent.com/PGH-snfl/embedded-vision/main/install.sh`를 받아 새로운 경로에 설치했다. 공개 Git 복제부터 Python·Node·편집기·AVR 준비, 두 서버 기동(19066/19068), 화면 응답과 내장 UNO 버튼·LED 예제 코드의 격리 컴파일까지 성공했다. 예제 HEX 3,204바이트를 생성했다. API 호출은 없었다.

공개 저장소는 PUBLIC이며 튜토리얼 `https://pgh-snfl.github.io/embedded-vision/`의 Pages 빌드 성공과 실제 HTML 응답, 명령어 보기·복사 버튼 각 8개를 확인했다. GitHub OAuth의 추가 workflow 권한 없이 main 브랜치 `/docs`의 정적 HTML로 배포한다.

## 설치 중 수정한 문제

- 다중 아키텍처로 설치된 시스템 패키지 조회 결과를 잘못 미설치로 판단하던 문제 수정.
- 임시 폴더 안 설치본에서 컴파일러 마운트가 `/tmp` 격리로 가려지던 순서 수정. 네트워크·개인 경로 격리는 유지.
- 종료 직후 TCP 연결 정리 상태를 다른 서버의 포트 점유로 오인하지 않도록 재사용 옵션 적용.
- 보드별 예제 페이지에도 실행 시 편집기 포트 전달.
- 로컬 튜토리얼은 스크립트·스타일 해시를 서버 정책에 등록하고 정적 호환본은 외부 JS/CSS로 제공한다. 보기·복사 기능을 허용하면서 다른 페이지의 보안 정책을 유지한다. 관련 검사 3개를 최종 수정 후 다시 통과했다.
- 예전 LED 목표 테스트 3개가 관측 목록을 직접 바꾸고 무결성 해시를 갱신하지 않던 테스트 입력을 기존 공통 봉인 함수로 수정. 실제 서비스의 목록 변조 거부 검사는 유지.

## 공개 범위와 미검증 사항

게시 전 Git 인덱스에서 API/GitHub/AWS 키·개인 키 패턴과 제외 디렉터리를 검사했다. 소스·테스트·문서·패치·출처 있는 예제만 게시한다. API 키·사용자 업로드·분석 기록·`outputs/`·설치된 의존성은 제외한다.

**유료 AI 호출 0회.** 현재 계정의 모델 접근·크레딧과 새 사진 인식 정확도는 검증하지 않았다. 실물 회로 작동도 검증하지 않았다. 브라우저 자동 조작 연결 오류 때문에 최종 화면의 실제 클릭·스크린샷 시각 검사는 완료하지 못했다. HTTP 화면 제공·DOM 상호작용·컴파일·지원 에뮬레이터·SPICE 검사와 구분한다.

공개 저장소·튜토리얼 웹 주소와 설치 명령은 README를 따른다. 다른 운영체제와 보드 전용 원격 실행 서비스는 이번 기본 설치 검증 범위 밖이다.
