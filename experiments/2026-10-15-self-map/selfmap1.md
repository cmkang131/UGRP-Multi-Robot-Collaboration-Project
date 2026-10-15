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

## 저장 RGB 결과

실행 소스 `63f15e8ea47ac13189b10869c29a67459e445fb3`, 토글 on,
명령 prior `s2_pulse_v122_rotL_v1`. 기존 실행의 제어기 pose를 재사용하지 않고 자기 명령으로
새 추정기를 돌렸다. 이 prior는 원본 E2E10 제어기의 재현 주장과 별개인 이번 후보 구성이다.
환경 Python 3.12·OpenCV/NumPy/SciPy 버전과 모든 출력/입력 해시는 [summary.json](summary.json).

| 항목 | s61001 r2 | s61002 r2 |
|---|---:|---:|
| 실행 상태 | RECORDED (부분 RGB) | RECORDED (부분 RGB) |
| RGB 재생 / 원장 frame | 126 / 2,308 | 116 / 2,353 |
| 누락 RGB | 2,182 | 2,237 |
| 저장 표본 시각 범위 (SIM s, 중간 누락 있음) | 1.3–260.5 | 1.3–204.7 |
| 지도 삽입 / 재생 RGB | 10 / 126 | 10 / 116 |
| 시각 pose 갱신 / 재생 RGB (bootstrap 제외) | 14 / 126 | 10 / 116 |
| 점유 IoU (교집합 / 합집합) | 14 / 309 = 4.53% | 11 / 309 = 3.56% |
| 벽 RMSE (예측 occupied N) | 0.08645 m (23) | 0.10954 m (20) |
| 전체 벽→예측 p95 (GT 표본 N) | 3.78017 m (564) | 3.82132 m (564) |
| free 탐색 커버리지 | 362 / 2,755 = 13.14% | 364 / 2,755 = 13.21% |
| known 영역 / 전체 도면 | 392 / 3,055 | 394 / 3,055 |
| frontier 경로 제안 / 재생 RGB | 0 / 126 | 0 / 116 |
| 자기 지도 완료 선언 / 재생 RGB | 0 / 126 | 0 / 116 |

두 실행은 따로 보고하며 기존 egomap 코호트와 합산하지 않는다. 재생은 과거 행동을 고정한
분석이다. 새 경로를 실제로 따라간 시험이 아니며, 약 5%만 남은 RGB로 전체 탐색을 복원하지 못한다.
작은 벽 RMSE는 관측된 극히 일부 점유에 대한 값이다. 전체 벽까지의 p95와 전체 커버리지를
함께 보면 지도 완성 증거가 아니다. `NOT_READY_FOR_COMPLETE_MAPPING_OR_DRIVING`.

로그에서 관측한 범위: s61001 지도 삽입 시각 1.7–4.7초 10개, s61002 1.7–7.1초 10개.
필터 전 frontier는 입장 허용 frame 중 각 7개/6개에서 남아 있었다(최대 92/91 cells).
즉 후보 경로 0을 완료로 잘못 선언하지 않았다. `pose_revision_requires_rebuild`는
105/126·83/116회, `visual_pose_unavailable`은 111/126·105/116회 기록됐다(사유 중복 가능).
이는 분기/보류 사유의 계수이며 실제 물리 실패 원인 진단이 아니다. 원본 영상을 보고
시각 실패 원인을 판정한 작업은 이번에 수행하지 않았다.

출력은 `/Users/changmin/projects/ugrp/outputs/selfmap1-63f15e8e/{s61001-r2,s61002-r2}/`.
map/trace가 64 KiB를 넘어 zstd로 보관했고 해제 바이트와 SHA-256이 일치함을 확인했다.
`compression-manifest.json`에 원래 파일 SHA와 archive 경로/SHA를 함께 남겼다.
압축 지도에서 재평가한 s61001 지표도 원래 평가와 동일했다. 원본 저장 RGB·명령은 변경하지 않았다.
raw는 로컬 보관이며 원격 백업 완료를 주장하지 않는다. 생성 자료 합계는 1 MiB 미만이고
확인 당시 로컬 여유 공간은 84.69 GiB였다.

## 남은 범위

- 이번 구현의 합성 관측 시험에서는 frontier 선택→A* 경로 출력이 확인됐으나,
  저장 RGB 표본에서는 경로 제안이 0회다. 연속 RGB로 초기 둘러보기/footprint 관측을 검증해야 한다.
- 큰 pose 보정 뒤 과거 pose로 점유를 재삽입하는 기능은 아직 없다. 보류 상태를 지도 완성으로
  바꾸지 않는다. 정적 지도 제공 모드와 일반 장애물/다른 구역 인식도 후속 범위다.
- 실주행 executor·관측 sweep 주기·정식 workflow/실행 번들 편입 및 물리 완주는 미검증이다.
  오프라인 지표 계산은 끝났으므로 이번에는 신규 물리 요청/GCP 큐를 만들지 않았다.

## 개발 중 확인한 오류

최초 3파일 시험은 17 passed/6 failed였다. 기존 B 기억 모듈의 동결 색/형태 설정을
전달하지 않은 생성자 연결 오류였다. `active_wall_mapping`과 같은 동결 설정을 재사용했다.
다음 22 passed/1 failed는 합성 fixture의 로봇 footprint 뒤편이 unknown이라 경로가 없는
정상 동작이었다. 코드의 unknown 안전 조건을 완화하지 않고 시험 관측 범위를 보완했다.
최종 관련 3파일 **24 passed (2.34 s)**. 실제 환경/주행 시험 수가 아니라 오프라인 계약 시험 수다.
첫 재생 SHA `9f13d4c7b6b2c4f3dec5b2e5fe2fda8842e13c18`은 126행 처리 뒤 snapshot의
NumPy int64 JSON 직렬화 오류로 HOST_ERROR였다. [실패 기록](failed-attempt.json)과 trace를
보존했고 평가 분모에 넣지 않았다. 좌표를 Python int로 내보내고 zone의 좌표계 라벨도
natural-floor frame으로 맞췄다. 수정된 2파일 16시험 통과(1.14 s), 압축 입력 읽기 수정 후
해당 1파일 5시험 통과(1.24 s). #496 8시험 코드는 변경하지 않았다.

## 참고 자료

[설계 문서 참고 자료](../../docs/self_map_integration.md#참고-자료)에 원문/초록 확인 범위를 기록했다.
Moravec–Elfes occupancy, Yamauchi frontier, gmapping/slam_toolbox의 pose–map 분리를 적용한다.
확인하지 않은 1989 Elfes 논문 전문을 읽은 것으로 인용하지 않는다.
