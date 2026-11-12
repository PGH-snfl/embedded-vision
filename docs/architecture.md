> 현재 SaaS 구조와 구현/남은 확장 단계는 [saas-architecture.md](saas-architecture.md)를 참고하세요. 아래는 최초 M1 결정 기록입니다.

# M1 결정 기록

핵심 경로: PNG/JPEG → 정규화된 이미지 → 색상 후보/수동 관측 → Circuit Graph → 사용자 검토 → 웹 회로/검토 순서/JSON.

FastAPI + Pydantic + SQLite + OpenCV + Pillow를 사용한다. 프런트는 빌드 없는 JavaScript/SVG로 M1을 검증한다. 향후 React/TypeScript로 교체해도 같은 API/Graph를 사용한다. 대규모 모델, 가중치 다운로드, 외부 AI 전송은 수행하지 않는다.

원래 관측은 수정하지 않는다. 판단을 바꾸면 근거를 추가하고 revision을 증가시킨다. UNKNOWN 값은 null이고 후보는 별도다. CONFIRMED에는 존재하는 evidence ID가 필요하다. 단자 라벨과 데이터시트 pin_mapping을 분리하고 후자는 UNKNOWN으로 유지한다.

전선의 물리적 경로와 전기적 연결을 분리한다. 확정 net과 추정을 포함한 초안 net을 따로 파생한다. 모양의 교차·선 색·브레드보드 관습으로 숨은 도통을 추가하지 않는다. 원래 자산 SHA256은 방향 보정/EXIF 제거 후 저장된 PNG에 대한 해시다.

검증 API는 구조 PASS, 연결 BLOCKED/REVIEWED, 나머지 NOT_RUN을 반환한다. REVIEWED는 연결 검토가 끝났다는 뜻이며 전기 안전 PASS가 아니다. KiCad endpoint는 M1에서 항상 409로 거절한다. EDA 매핑·데이터시트 검증·ERC 없이 생산 가능한 설계인 것처럼 내보내지 않는다.

다음 단계 전 필요한 증거:

- 실제 ESP32 보드 변형을 특정한 사진과 핀아웃 문서
- 부품/배선 끝점의 사람이 확인한 정답, 가림/교차/흐림을 포함한 평가 사진
- 모델 검출 전/사용자 수정 후 정확도를 나눈 기록
- 논리 단자 → 실제 커넥터 위치 → KiCad 심벌 핀 번호 매핑
- 생성 회로도 재로딩 후 연결 대조와 ERC 결과
