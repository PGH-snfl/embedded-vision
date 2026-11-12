# 전체 구조 설계

사진에서 보이는 면은 관측 계층 `evPhotoStructure`에 보존한다. Pi 2륜 로봇과
Uno Motor Shield 전환 예제는 조립 배치 전에 별도의 설계 보완 계층을 추가한다.
원본 사진에 없던 부분은 `evDesignedStructure`, `INFERRED`,
`source_kind=DESIGN_COMPLETION`으로 표시한다. 사진 영역이나 관측 확률을 만들지 않는다.

현재 로봇 예제는 사진 구조 8개에 다음 11개를 추가한다.

- 반대쪽 바퀴, 반대쪽 측면 프레임
- 플랫폼 뒤쪽 지지대 2개
- 앞뒤 하부 가로 프레임 2개
- 볼 캐스터, 소켓, 지지축
- 좌우 모터 장착 브래킷

바퀴는 양면 허브와 고정 볼트, 스포크, 타이어 돌기를 가진 닫힌 입체이다.
지지대와 브래킷도 양 끝과 양쪽 면을 생성한다. 모두 개별 구조물로 선택하고
이동·크기·색상·회전을 편집할 수 있다. `설계 보완` 목록과 선택 패널에서
생성 이유를 확인하며 `반대쪽 보기`로 후면을 확인한다. 운동 화면은 아래에서도
회전해 볼 수 있다.

`mechanicalCompletion.ts`는 단위 mm의 공통 생성 규칙,
`mechanicalCompletionProject.ts`는 native 프로젝트 어댑터,
`mechanicalDetails.ts`는 편집기와 운동 화면이 공유하는 입체 상세 정의다.
`MechanicalShape.tsx`와 `rover-src/mechanical-shape.js`가 이를 렌더링한다.
구형 캐스터도 구조 저장 API에서 동일한 shape로 보존한다.

native의 `embeddedVision.structure_completion`, 운동 구조의
`completion_version`은 한 번 적용했다는 표시다. 사용자가 삭제·이동한 보완
부품을 재진입 시 임의로 다시 만들지 않는다. 두 화면의 편집 저장소는 기존처럼
별도이며 실시간 동기화는 하지 않는다.

추가 구조의 경계도 부품 배치와 배선 경로 탐색에 포함한다. 기존 전기 연결과
사용자 코드는 유지한다. 이 기능은 2륜 로봇 설계 규칙이며 임의의 로봇·드론을
일반 3D 메시로 복원하는 모델은 아니다. 가려진 형상과 실제 치수는 UNKNOWN이며,
220 mm 표시 축척·대칭·새 캐스터·고정 방법은 제작을 위한 실측 설계가 아니다.

재설치에는 `velxio-assembly.patch` 뒤에 `velxio-whole-structure.patch`를 적용한다.
