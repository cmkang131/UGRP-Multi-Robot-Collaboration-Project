# selfmap1 — 자기 지도 연결 1차 (2026-10-15)

브랜치 `claude/map-selfmap`, 시작 main `c72a2b50628e549fee8032378f4c7cf709fe688c`.
설계·지표·참고 자료는 [self_map_integration.md](../../docs/self_map_integration.md).

## 범위와 조정

- 시작 전 origin fetch·열린 PR 확인 완료, 시작 작업 트리 clean.
- 범위 코멘트: [#496](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/496#issuecomment-6182798550), [#437](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/437#issuecomment-6182799017), [#440](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/440#issuecomment-6182799573).
- #496의 3파일을 고정 SHA에서 바이트 그대로 가져옴. [dependency.json](dependency.json) 참조.
- 기본 off. 자기 RGB/발행 명령만으로 pose→점유→frontier 경로 제안과 운용 종료 판정.
- 새 물리·렌더·학습·모델 호출·원격 접속 없음. ACT 및 기존 실행기는 변경하지 않음.
- 시작 모델 endpoint 경보 파일 없음, 연속 확인 실패 0. LLM 배치 사용 없음.

## 검증 계획과 저장 자료

변경 경로 시험은 `test_natural_floor_slam.py`, `test_self_map_integration.py`,
`test_offline_self_map.py` 3파일에 한정한다. 토글 off 동일 객체, pose 좌표 변환,
중복/peer/정답 필드 거부, command-only/held 삽입 보류, 큰 pose 점프 재구성 요구,
frontier 경로와 완료 판정, 고정 분모·외부 FP·평가 분리를 검사한다.

`outputs/frontier-visibility-v1/new-seed`에는 JPEG가 없어 이 실행은 RGB 재생에 쓰지 않는다.
회수된 E2E10 저장 RGB 표본을 사용한다:

- 원장: `/Users/changmin/projects/ugrp/outputs/azure-runs/e2e10-a-s61001-r2/raw`
- RGB: `/Users/changmin/projects/ugrp/outputs/e2e11-stall-odometry/selected-frames/e2e10-a-s61001-r2/raw`
- 같은 형태의 `e2e10-a-s61002-r2`도 별도 실행으로 평가하며 합산 성능으로 보고하지 않는다.
- 원본 파일은 삭제/덮어쓰지 않는다. 선택 RGB는 과거 진단용 표본이라 확증 자료가 아니다.
- 실제 코드 SHA를 커밋한 뒤 replay, 별도 evaluate를 실행한다. 결과와 해시는 후속 기록에 추가한다.

## 개발 중 확인한 오류

최초 3파일 시험은 17 passed/6 failed였다. 기존 B 기억 모듈의 동결 색/형태 설정을
전달하지 않은 생성자 연결 오류였다. `active_wall_mapping`과 같은 동결 설정을 재사용했다.
다음 22 passed/1 failed는 합성 fixture의 로봇 footprint 뒤편이 unknown이라 경로가 없는
정상 동작이었다. 코드의 unknown 안전 조건을 완화하지 않고 시험 관측 범위를 보완했다.
최종 관련 3파일 **24 passed (2.34 s)**. 실제 환경/주행 시험 수가 아니라 오프라인 계약 시험 수다.

## 참고 자료

[설계 문서 참고 자료](../../docs/self_map_integration.md#참고-자료)에 원문/초록 확인 범위를 기록했다.
Moravec–Elfes occupancy, Yamauchi frontier, gmapping/slam_toolbox의 pose–map 분리를 적용한다.
확인하지 않은 1989 Elfes 논문 전문을 읽은 것으로 인용하지 않는다.
