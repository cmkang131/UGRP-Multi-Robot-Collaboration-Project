# PR #234 2차 리뷰 수정

기준 `ac743938d1b42172dc2d634b6558091d71fc858e`. NEW P1 2건·P2 1건을 수정했다.
코호트·MuJoCo·학습은 실행하지 않았다. `.git` 변경·커밋은 하지 않으며 coordinator가 커밋한다.
이 폴더는 단위 검사 기록이고, 앞선 실험/리뷰 로그는 그대로 보존한다.

## 수정

| 항목 | 파일과 행동 |
|---|---|
| unknown/시간 감쇠로 배치 허용 | `owncam_slot_inspection_v3.py`, `m1_owncam_memory_v3.py`, `owncam_memory_v3.py`: 실제 카메라 기하로 볼 수 있는 후방 관측점에서 빈 바닥 근거를 만들고 복귀 후 다시 검사. unknown은 허가하지 않음 |
| 같은 SIM 시각 새 frame 거부 | `owncam_pose_guard_v3.py`, `owncam_memory_v3.py`: `(timestamp, frame_id)`의 순서와 frame ID 재사용을 검사. 같은 시각의 새 촬영은 전달하되 PF·일관성·free 격자를 재누적하지 않음 |
| free 격자의 가시성 누락 | `owncam_visibility_v3.py`, `owncam_memory_v3.py`: 셀 전체와 xy/yaw ±2σ, 팔·벽·전경 가림에 track miss와 같은 `support_visible` 적용 |

`scripts/run_ci_tests.py`에 `tests/test_owncam_memory_v3_review2.py`를 등록했고,
v3 runner 소스 해시에 새 슬롯 절차 파일을 추가했다. 기존 v3의 unknown 허용 테스트는 별도 빈 바닥 관측을 명시적으로 요구하도록 바꿨다. frozen v2 파일은 바꾸지 않았다.

## 슬롯 절차와 실패 전달

1. 배치 경계에서 점유 기억이 있으면 `SLOT_OCCUPIED_IN_MEMORY`로 종료한다. 확률의 시간 감쇠와 별도로 관측만으로 갱신하는 `observation_existence_p`와 `slot_blocking`을 유지한다. 225초 뒤 일반 존재 확률이 0.20 아래로 내려가도 차단은 유지된다. 충분한 **가시 miss**로 관측 확률 ≤0.10인 경우만 차단을 풀며 새 검출은 다시 차단한다.
2. unknown이면 기존 own-pose/정적 지도/keep-out 경로 계획기로 슬롯 서쪽 0.95 m, 필요시 1.05 m 관측점으로 이동한다. 집게 PWM 1500을 유지한 SEARCH 자세에서 시간을 둔 여러 프레임을 촬영한다. 카메라/FOV/로봇 외형은 바꾸지 않는다.
3. 하중 바닥 관측에는 현재 자기 RGB의 큰 화물 cyan 마스크가 필수다. 마스크 상단보다 10 px 위, 기존 loaded 상단 제한 120 px 중 더 엄격한 값을 사용한다. 그 아래는 모든 열을 가린 것으로 취급한다. SEARCH의 팔 기하와 닫힌 집게의 횡방향 운동도 함께 고려한다. 가시성이 불명확하면 free를 쓰지 않는다.
4. 슬롯과 겹치는 **셀 전체**가 최근 free여야 복귀한다. 기본 슬롯은 중심 셀 4개만 보지 않고 외곽까지 포함한 16개 셀을 검사한다. held 이미지 기준을 재확인하고 기존 해제 준비 위치로 돌아간다. 도착 후 점유·바닥 근거 나이·새 pose fix·해제 자세·자기 RGB 부착을 모두 다시 검사해야 스킬을 호출한다.
5. 관측점 최대 2곳, 전체 120 SIM s, 바닥 근거 TTL 60 SIM s가 개발 후보값이다. 경로 실패·화물 재확인 실패·시간 초과·끝내 unknown이면 `SLOT_UNVERIFIED`와 `handoff.requires_upper_level_decision=true`를 반환한다. 반환값과 `summary.slot_handoff_v3`에 이유·슬롯·시도 횟수·해제 미시작을 남긴다. 기존 실행기는 done/outcome으로 중단하며 상위 실행기/LLM이 이 기록을 읽어 다음 행동을 결정할 수 있다. 자동 LLM 전송이나 조용한 재시작은 없다.

이 확인은 센서/검출 모형에 따른 빈 바닥 관측이다. 60초 동안 장애물이 새로 들어오지 않는다는 물리 보장은 아니다. TTL·관측점·하중 자세·detector recall·왕복 가능성과 거부율은 PR #227 이후 **새 dev**에서 검증해야 한다. 큰 위치 불확실성/가림 때문에 끝까지 확인하지 못하면 성공으로 바꾸지 않는다.

## fixture 노출과 검증 범위

기존 fixture는 원래 **memory_v2 test split의 s162/s164/s165**다. 원본 `result.json`의 `split=test`, 프레임 인덱스 해시, 저장 RGB 6장 해시를 확인했다. 이미 v3 개발·회귀에 사용한 노출 자료이므로 v3의 미개봉 test/성능 표본으로 사용하지 않는다. [상위 README](../README.md)와 [prereg_DRAFT.json](../prereg_DRAFT.json)의 `exposed_fixture_policy`에 명시했다. 미래 test는 노출 seed 161–166 및 dev와 분리된 **새 미개봉 seed/episode만** 사용한다.

저장된 해제 자세/화물 RGB만 넣으면 이제 세 경우 모두 관측 절차로 들어간다. 긍정 검사에서는 별도의 빈 슬롯 근거 또는 합성 정밀 pose·검출 부재를 명시적으로 공급한다. 실제 저장 화물 마스크와 합성 관측점 기하로 슬롯 16개 셀을 볼 수 있음을 확인했지만, 이 위치를 실제 로봇이 방문한 영상이나 v3 에피소드 재실행 성공은 아니다. 기존 v2의 PF 보고서에는 v3 likelihood/innovation 근거가 없으므로 그 일관성 역시 주입된 전제다.

## 테스트

Python `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`.
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1` 및
OpenCV GCD `setNumThreads(0)`/`getNumThreads()==1`. 모든 pytest는 `--basetemp=./.pytest_tmp`.

| 범위 | 결과 |
|---|---|
| 수정 전 세 항목의 핵심 반례 | 6 failed — `before-corrected-fixture.txt` |
| 최종 테스트를 기준 runtime에 read-only 적용 | 6 failed, 20 deselected — `before-confirmed.txt` |
| 2차 리뷰 회귀·경계 | 26 passed — `boundaries-after.txt` |
| v3/기존 memory/M1/localizer/visual_attachment/v9 스킬 | **229 passed, 382 subtests passed** — `final-single-thread.txt` |

`reproduce_baseline.py`는 `git show ac743938:<파일>`로 네 기준 모듈을 메모리에만 읽는다. checkout/index/소스를 바꾸지 않는다. 위 환경변수를 설정하고 `python experiments/2026-09-27-zone-owncam-memory-v3/review2-fixes/reproduce_baseline.py`로 실행하면 6개 실패(exit 1)가 기대 결과다.

최종 검사는 기존 `review-fixes/run_review_tests.py -q --basetemp=./.pytest_tmp`에 다음 모듈을 넘겼다: `test_owncam_memory_v3_review2`, `test_owncam_memory_v3_review`, `test_owncam_memory_v3`, `test_owncam_memory`, `test_m1_owncam`, `test_owncam_localizer`, `test_visual_attachment`, `test_wrist_zone_skill_v9` (모두 `tests/*.py`). 원격 CI나 전체 프로젝트 CI 실행은 아니다.

초기 촬영 fixture의 누락 필드, 빈 후보 배열의 bool dtype 오류, 후보 필터 전 검사 중단도 로그에 남겼다. `before.txt`는 입력 fixture 오류가 포함되어 있어 반례 근거로 쓰지 않고 수정된 before 로그를 사용한다. `after-initial.txt`는 후보가 너무 많은 경로의 테스트를 29개 통과 후 직접 중단한 기록이며, 평균 FOV의 필수조건으로 후보만 줄인 뒤 전체를 재검증했다.

## 남은 작업

- coordinator의 검토·커밋·원격 CI.
- PR #227 연결과 새 dev에서 실제 슬롯 관측/왕복, 화물 유지, false free/false absence 및 명시적 실패율 확인.
- DRAFT의 새 seed 예약·소스/조건 동결 후 신규 코호트. 이번 수정에는 물리 성공률/속도/TensorBoard 실험 결과가 없다.

## 참고 자료

- 제공된 `codex-234-review2.md` 전체. 출처 경로와 SHA-256은 `verification.json`에 기록한다.
- [현재 v3 설계](../../../docs/design/2026-09-27-owncam-memory-v3.md), [최초 구현 기록](../README.md), [1차 리뷰 당시 기록](../review-fixes/README.md). 1차 기록의 unknown 허용 계약은 폐기했다.
- `harness/owncam_memory.py`의 고정 카메라/FOV, `harness/visual_arm.py`의 팔 기하, `harness/visual_attachment.py`의 기존 자기 RGB 화물 마스크. 실행 중 시뮬레이터 정답은 읽지 않는다.
