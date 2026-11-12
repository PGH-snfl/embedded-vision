# 공용 데이터와 모듈

- `paths.py`: 프로젝트·서비스·데이터의 기준 경로.
- `backend/`: Circuit Graph, 회로 설계, 보드 프로필·변환, 시뮬레이션 등 공용 코드.
- `data/`: 부품·보드 데이터, 예제, 사진 워크플로우, 출처.
- `data/simulator-catalog-snapshot.json`: 분석기가 편집기 설치 없이 읽는 부품 이름 목록. 핀·정격 검증 자료가 아닙니다. 편집기 빌드 후 `scripts/export_catalog.py`로 갱신합니다.

기존 `backend.*` import와 `data/` 경로는 루트의 호환 링크를 통해 유지합니다. 각 서비스가 상대 서비스의 API·작업 큐를 시작하지 않도록 하세요.
