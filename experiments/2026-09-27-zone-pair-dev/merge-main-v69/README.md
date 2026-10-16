# PR #240 main 병합(v66 multiturn) 및 CI 수정 — 2026-09-28

작업 기준 HEAD `f87921dc52f7a3f12d41b4bc6ab5c30227890e8e`, 병합 대상 origin/main
`6e44c5e7d6d3cbad540c2c248dfea4d56b7d5b29`(PR #245 v66-multiturn 포함). Claude가 코디네이터 지시로 수행했다.
물리 step·모델 호출·네트워크 모델 요청은 하지 않았다. 새 물리 결과가 없어 TensorBoard 추가 대상도 없다.

## 1. main 충돌 해결과 번들 ID

충돌 파일은 `harness/zone_study_integration.py`와 `tests/test_zone_study_source_pinning.py` 두 개다.

- main의 multiturn 스케줄러(v66)와 #240의 pair v5h·표식 무관 인터페이스(v67)를 모두 보존했다.
- 합성 소스는 v66·v67 어느 쪽과도 다르다. 그래서 번호 예약 규칙에 따라 새 ID를 등록했다.
  - main과 열린 PR #240/#242/#243/#246 전체 ref의 최댓값은 v68(#246 `zone-pair-v68-beam-relative-recovery`)이다. 근거는 [번호 확인](id_audit.json)에 있다.
  - 새 ID는 **`zone-study-integration-v69-multiturn-landmark-agnostic`**다.
  - workflow `zone-study-integration-run`은 2.1.0(#240)·1.0.0(main)에서 **2.2.0**으로 올렸다.
- `RETIRED_BUNDLE_IDS`에 v65·v66·v67을 추가했다. v1·v2·v64는 main 그대로 유지했다.
  dev13·dev14 실행 기록과 `prereg_v5d~v5h`의 `versions` 문자열에 있는 v67은 바이트 그대로 두었다.
- 소스 고정 테스트의 변이 목록은 합집합으로 합쳤다. #240의 grasp/status/beam_track/align과 main의 `zone_study_decisions`를 모두 넣었다.
- multiturn 속성 테스트는 후보 번들을 v69로, 동결 기준을 v64로 확인한다. `no_comm == 동결 v64` 불변식은 바꾸지 않았다.

## 2. v5h는 실행된 과거 등록이 됨

main 병합으로 v5h grasp 계약이 덮는 소스 두 개가 바뀌었다.

- `scripts/run_zone_study_integration.py`: multiturn의 `call_policy`·`decision_limits`·`decision_events` 반영
- `configs/simulation_workflows.json`: workflow 2.2.0

scene 계약은 그대로다. 따라서 커밋된 `prereg_v5h.json`은 현재 소스에서 `grasp contract/hash mismatch`로 거부된다.
dev13·dev14는 이미 f87921dc에서 실행됐으므로 이 거부가 올바른 동작이다. 등록 파일·드라이버 검사는 바꾸지 않았다.

- `tests/zone_pair_current_source.py`
  - `assert_executed_v5h_is_historical`는 등록 커밋의 git blob으로 과거 영수증을 검증한다(`verify_registered_source`). 이어서 현재 소스가 정확한 오류로 거부되는지, 출력이 생기지 않는지 확인한다.
  - `current_source_v5h`는 테스트 전용 합성 fixture다. 커밋된 v5h의 소스 영수증만 현재 checkout에 다시 묶고 `registration_sha256`를 재봉인한다. 이 fixture는 등록·승인·실행 기록이 아니며 저장소에 쓰지 않는다.
- authorization·grasp·v5c·dock 테스트는 두 가지를 함께 검사한다. (a) 커밋된 v5h의 거부, (b) 합성 fixture에서의 기존 승인·prepare 논리. 다른 검사는 그대로다.

## 3. CI `offline-regressions` 4 failed 수정

### `test_zone_pair_v5.py` dev09·dev10

PR #246 커밋 `a5b486eb`의 `review2-fixes/ci-scene-fix`에서 #240 범위만 가져왔다.

- 원인은 테스트의 잘못된 가정이다. 테스트는 플랫폼 의존 카탈로그 해시(libm 마지막 비트)가 들어간 scene 해시를 모든 호스트가 승인한다고 가정했다.
- 가져온 것
  - `tests/test_zone_pair_v5.py`의 해당 hunk: native·registered·1 ULP 카탈로그 × dev09·dev10 회귀 6개
  - 헬퍼 `scripts/zone_pair_registered_source.py`: #246과 바이트 동일, 과거 등록을 등록 커밋의 git blob으로 읽는다
- 가져오지 않은 것: v6 기능 코드, `test_zone_pair_registered_source.py`(v6 테스트 포함), 드라이버 v6 분기
- expected hash·과거 prereg·`validate_scene`은 바꾸지 않았다.

### `test_zone_start_dock.py` dev13·dev14

- 원인: 테스트가 Mac 전용 절대 경로 `/Users/changmin/projects/ugrp/outputs/...`를 썼다. CI에서는 출력 경로 검사가 먼저 걸렸다.
- 수정
  - 커밋된 영수증에는 승인 봉투가 없다. dev13·dev14는 실행 checkout에만 추가한 봉투로 실행됐다.
  - 따라서 `--execute`는 모든 호스트에서 `prepare-only: execution_authorization ...`로 거부돼야 한다.
  - 이 거부를 `dev.primary_root()/outputs` 경로로 검사한다.
  - primary 밖 경로의 출력 거부도 별도로 정확한 오류로 검사한다.
- 병합 뒤 커밋된 v5h는 위 2절처럼 grasp 불일치로 거부된다. prepare 성공 경로는 합성 current-source 케이스(dev13·dev14)로 계속 검사한다.
- `registered_tree`는 #246과 같이 먼저 `verify_registered_source`로 과거 blob을 감사한다.

## 검증

- 실행 조건: `OMP_NUM_THREADS=2`, `-p no_physics`(`../merge-main-v65/no_physics.py`, `mj_step*` 호출 시 실패), `--basetemp=./.pytest_tmp`.
- sparse checkout에서 빠진 `experiments/2026-09-26-zone-study-offline-smoke/v{3,4,5}/example_trial_record.json.gz`는 `git checkout --ignore-skip-worktree-bits`로 받았다.
- 관련 전체 82개 파일 1차(테스트 수정 전): **15 failed / 8075 passed**, 1420.6 s.
  - 병합으로 v5h가 과거 등록이 되어 생긴 실패 10건: authorization 3, grasp 1, v5c 4, dock 2
  - sparse 누락 gz 3건
  - 물리 step 차단 2건: `test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera`, `test_zone_own_executor_host.py::test_team_host_isolation_abort_and_horizon_on_the_real_world`
- 수정 뒤 영향 파일 9개(authorization, grasp, v5c, v5, dock, r7_contract, source_pinning, integration_pair, multiturn_properties) 재실행: **1056 passed / 0 failed**, 2353 s(다른 작업의 부하로 느림).
- 물리 step이 필요한 위 2건은 사용자 지시(배터리, 물리 step 금지)로 로컬에서 돌리지 않았다. 이 2건은 CI에서 확인한다.
- 이 기록은 오프라인 코드 회귀다. 물리 실험·새 코호트 성공 근거가 아니다.
