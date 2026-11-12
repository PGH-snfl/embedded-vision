# 분석기 서비스

프로젝트 루트에서 `bash services/analyzer/start.sh`로 별도 실행합니다. 기본 주소: http://127.0.0.1:8766/.

`backend/`는 사진·영상 입력, OCR, AI 분석 작업, 데이터시트, KiCad 선택 모듈과 SaaS 코드를 소유하고 `frontend/`는 단계별 분석 화면입니다. 분석기 설치에는 Node·AVR·편집기 빌드가 필요하지 않습니다. 편집기 미설치 시 공용 부품 목록 스냅샷을 사용합니다.

`bash services/analyzer/configure_openai.sh`로 키를 숨김 입력합니다. 데이터는 기존 `.runtime/`를 보존하며 `EMBEDDED_ANALYZER_DATA`로 바꿀 수 있습니다. 사진 분석은 유료 외부 API를 사용할 수 있습니다.

결과 `.vlx`를 별도 편집기에서 엽니다. 기존 편집기 직접 열기 경로도 유지합니다. 기본 `start.sh`는 이 서비스를 시작하지 않습니다.
