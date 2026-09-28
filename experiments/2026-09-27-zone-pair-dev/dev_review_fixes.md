# Dev 드라이버 리뷰 P1/P2 수정 — 2026-09-27

기준: PR #235, `codex/zone-pair-executor`, HEAD
`6d25954db079c0684e81559c9f07a0f6e4ef9cb5`.
리뷰 원문: `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-pair-dev-review.md`.
이번 결과는 **미커밋 로컬 수정과 비물리 소프트웨어 테스트**다.

## 수정과 선택 근거

- **P1:** 기존 `run_m2_pair.py`의 `DOOR_PLAN`, `M2DoorStudent` 생성자·`_cp_open`과
  `docs/zone_m2_pair.md`를 먼저 확인했다. 기존 dev 801/802의 긴 운반에서는
  0.06–0.1 rad/m 방향 오차가 기록됐고, 파지 중 영상에는 빔만 보여 위치를 다시
  추정하기 어려웠다. 따라서 **x=2.40 체크포인트를 유지**하고 내림·방출·재위치추정·
  재파지를 계획된 set-down으로 분리했다. 동결 M2의 stored-grip v3 동작과
  최대 0.85 m 구간을 유지한다. 기존 M2 성공을 새 실행기 성공으로 승계하지 않는다.
  - 양쪽 lower GO, 해당 segment/상태, 다음 carry GO 전 구간, 정적 종점 12 cm 이내를
    모두 만족해야 예외다. 종점·허용치·이유를 설계 문서와 DRAFT prereg에 실행 전에 기록했다.
  - 기울기·바닥 관통·금지 접촉은 면제하지 않는다. 문 slab 안 y 경계도 유지한다.
  - 빔 전체가 문 동쪽으로 나온 뒤 양쪽 carry·공동 파지·4 cm 들림을 0.2 SIM초 유지해야
    문 통과다. 2.40 도달만으로 통과하지 않는다. 최종 B 배치·방출은 이후 별도 판정이다.
- **P2-1:** trace 시작·끝을 manifest 실제 시간에 맞추고 최대 간격·timestep 격자를 검사한다.
  접촉 기록은 동일한 양 끝·정확한 스텝 수·최대 간격·내부 누락 0건을 요구한다.
  초기 관측을 물리 스텝과 구분하고 정확한 종료 trace를 접촉 중복 집계 없이 추가한다.
  누락은 `EVIDENCE_INCOMPLETE`, abort 진단도 통과하지 못한다.
- **P2-2:** 평가 진입 직후 원본 manifest의 사전등록 SHA256과 저장된 prereg 바이트를 비교한다.
  해시 누락·불일치는 score 호출 전에 거절한다. prepare는 원본 바이트를 보존하고,
  읽기·manifest 생성·복사 사이의 변경도 거절한다. 실행 plan 종점도 prereg와 대조한다.

제어기·executor 경로, 물리 설정, 카메라, 모델 입력에는 변경이 없다.
추가 segment 메타데이터와 GT 판정은 `eval_only/`에서만 사용한다.

## 수정 전 실패 → 수정 후 통과

생산 코드 수정 전에 테스트를 먼저 추가해 같은 작업 트리에서 실패를 확인했다.
fixture는 JSON·배열·가짜 world/포트만 사용하며 MuJoCo model 생성·stepping·렌더링과
외부 모델 호출은 없다. 합성 영상 receipt도 테스트용 바이트이며 실제 검토 영상이 아니다.

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| P1: x=2.40 내림·방출·재파지 후 운반·최종 방출 | 1 failed: `door=false` | 동일 회귀 통과, 계획된 set-down 별도 기록 |
| P2-1: 앞/뒤 trace·접촉 스텝 누락, 내부 gap, timestep/격자, 시작 누락, 비유한 접촉 시각 | 11 failed: 잘못된 `physical_success=true` | 동일 11건 모두 미완료로 거절 |
| P2-2: 허용치 사후 변경, 해시 누락·변경, compact JSON 원본 보존 | 4 failed: 변경 기준 통과 또는 복사 해시 불일치 | 동일 4건 모두 통과; 불일치는 평가 전 거절 |

수정 전 명령 결과: **16 failed / 63 deselected, 0.49 s**.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_dev.py -k 'review_p1_planned or review_p2' \
  --basetemp=./.pytest_tmp --tb=short
```

추가 반례는 GO 없는 하역·한쪽만 내림·잘못된 segment·종점 밖 하역·기울기·관통·벽 접촉,
재파지 후 낙하, 문 동쪽에서 낮음/파지 없음/carry 아님을 검사한다.
원본 기준에서 B 배치가 실패한 trace의 허용치를 2 cm→20 cm로 바꾼 재평가도 거절한다.
정상 파일 평가, 0이 아닌 시작 시각, observer의 초기/마지막 표본·접촉 중복 방지·내부
tick 누락을 별도 검증했다. 두 seed의 정적 계획과 prereg 종점도 정확히 일치한다.

최종 관련 회귀: **528 passed / 3 deselected, 18.33 s**.
여기에는 dev 테스트 86건과 기존 PairTeam/STATUS/단독 실행기/M2/workflow 회귀가 포함된다.
동결 M2 import 32개와 원본 SHA 검사가 통과했다. `git diff --check`도 통과했다.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_dev.py \
  tests/test_zone_pair_review7.py tests/test_zone_pair_review6.py tests/test_zone_pair_review5.py \
  tests/test_zone_pair_review4.py tests/test_zone_pair_review3.py tests/test_zone_pair_review2.py \
  tests/test_zone_pair_review.py tests/test_zone_pair_executor.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_pair_owncam_approach.py tests/test_m2_pair_door_v3.py \
  tests/test_simulation_workflow_manager.py tests/test_zone_study_protocol.py \
  tests/test_simulation_scenes.py --basetemp=./.pytest_tmp \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world and not test_source_fingerprint_includes_calibration_requirements_and_sparse_absence and not test_parent_exit_cleans_background_child' \
  --tb=short
```

제외 3건은 실제 MuJoCo world 검사, sandbox의 임시 `.git` 쓰기 검사,
`ps` 제한이 있는 자식 종료 검사다. 사용자 허용에 따라 비물리 테스트는 잠금 없이 실행했다.
검사 뒤 `.pytest_tmp`를 삭제하고 부재를 확인했다.

## 남은 범위

- 실제 운반·접촉·r3 비간섭·영상·실험 TensorBoard는 미실행/미검증이다.
  소프트웨어 회귀만 수행했으므로 실험 snapshot이나 viewer는 만들지 않았다.
- `git fetch origin`은 공용 `.git` 쓰기 제한, `gh pr list`는 네트워크 제한으로 실패했다.
  최신 원격 PR/CI·중복 작업은 확인하지 못했다. 지정된 로컬 HEAD 기준으로만 수정했다.
- HEAD는 `6d25954` 그대로다. Git 커밋·push·PR 수정·병합, 기본 checkout 갱신은 하지 않았다.
  기록은 로컬 프로젝트에 저장했으며 UGRP 예외에 따라 Drive는 사용하지 않았다.
- 코디네이터의 검토·소스 커밋/고정 후에만 별도 승인된 dev 실행으로 물리 검증을 진행한다.
