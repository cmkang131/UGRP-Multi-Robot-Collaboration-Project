# PR #240 v5h — 정지 경계 P1 수정

기준 HEAD `c38f94e6c551d8c0fa9993945ff4df087754672e`의 미커밋 로컬 후보다.
진단 및 원본 해시는 [dev11_12_diagnosis.md](dev11_12_diagnosis.md)에 있다.
새 물리 실행·모델 호출·커밋·push·병합은 하지 않았다.

## 변경과 시간 계약

- `harness/zone_own_team_host.py::_apply/_hold`: 소수 4자리 반올림을 제거했다. 제어 입력이기도 한 명령 row의 `t`와 port에 전달되는 시각은 같은 raw SIM 시각이다. `motion_until`, relook 시작, 발행 close, 관측·명령 적분의 시간 표현을 생산 지점에서 통일한다. 명령 로그에도 raw 시각을 보존한다.
- `harness/zone_pair_guards.py::align_stop_ready`: 기존 조건을 유지하고 정지 대기 시 `align_relook_stop_wait`에 `checks`, `failed_checks`, `stopped_at_s`, `motion_until_s`, `report_t`를 기록한다. 미설정 `motion_until=-inf`는 로그에서 null이다. gate·보고 freshness·현재 정지 캐시가 막힌 경우를 구분할 수 있다.
- 전수 조사 추가 발견: `harness/owncam_memory.py`는 `last_fix['t']`를 millisecond로 반올림한 뒤 `last_look_fix`에 복사해 raw sweep 시작/현재 시각과 비교했다. 같은 **내부 raw 시간 보존** 계약으로 저장 시 반올림만 제거했다. v2/v3 소비 조건과 관측 수용·필터 알고리즘은 그대로다.
- `last_fix_t`의 raw 관측 전후 경계는 그대로다. `harness/owncam_time.py`는 변경하지 않았고, quantized report 비교의 기존 `1e-4 s` 허용만 유지한다. 실제 미종료 이동에는 epsilon을 도입하지 않았다.
- 게이트 임계값/dwell, relook 횟수·개별/총 시간, blockage 분류, 물리·접촉·카메라·weld OFF 설정은 변경하지 않았다.

## 시간 비교 전수 조사

범위는 `harness/zone_pair_*.py`, `harness/zone_own_team_host.py`, `harness/owncam_*.py`의 **39개 파일**이다. `round` 호출과 AST 시간 비교를 열거한 뒤 각 값의 생산 지점을 추적했다. 전체 파일 목록과 최종 소스 해시는 [time_audit.json](v5h_validation/time_audit.json)에 있다.

| 생산/소비 경로 | 발견 및 처리 |
|---|---|
| host `_apply`, `_hold` → `PairCommandGuard.on_command.motion_until` | 원인 생산 지점 2곳의 반올림 제거. raw `stopped_at >= motion_until`을 엄격 비교한다. |
| `PairCommandGuard.preclose_check`, `observe_standoff`, `_pose` 2분기, `_stationary_reobserve`, `check`, `align_stop_ready` | raw now/stop과 rounded 명령 종료 시각을 섞던 7개 비교 지점. host 수정으로 raw/raw 통일; 비교식은 유지. 보고/종료 비교만 기존 `report_at_or_after` 계약 적용. |
| `RestingBeamTrack.command/advance` → `zone_pair_obstruction.target_context` | command→capture 순서의 round-up이 beam 캐시를 지우거나 round-down이 raw 시계 역행으로 보일 수 있었다. host raw 통일로 해결; 실제 역행 거부와 drift 적분은 유지. |
| `PairGraspRelook.on_issued_command/_grasp` | rounded close 발행과 raw RGB 시각의 혼용 제거. GO/close 및 **close 이후** 이미지 요구는 그대로다. |
| `OwnCamLocalizer.command/predict_to/update` | cmd expiry, predict clock, arm settle이 raw 관측과 섞였다. host raw 통일로 해결; 동역학/필터·기존 숫자 오차 처리는 변경하지 않는다. |
| `PoseGuardV3.on_command/advance`, `OwnCamPoseSourceV3`, `GuardedPoseProviderV3`, memory-v3 `guard.advance` | rounded 명령과 raw frame의 단조 시계 비교가 tiny 역행을 거부할 수 있었다. host raw 통일; 진짜 역행은 계속 거부한다. |
| `owncam_memory.last_fix/last_look_fix` → v2/v3 `look_fix_since/look_fix_fresh` | 추가 독립 발견: 저장 때 millisecond 반올림 제거. raw sweep 직전 관측을 이후 관측으로 바꾸거나 현재 fix를 미래로 만드는 문제를 방지한다. |
| `PoseReport.as_dict`, localizer estimate → `owncam_time`, `check_limits`, admission | 보고 시각은 quantized일 수 있고 기존 양방향 `1e-4 s` 계약이 이미 있다. 변경 없음. `last_fix_t`, look 시작/종료는 raw 그대로다. |
| `zone_pair_status` GO/control 9자리 격자, executor `next_control` | 명시적 control 격자와 기존 `EPS` 비교다. host 4자리 명령 양자화와 다르며 변경 없음. |
| owncam drive/safety/slot/memory evidence deadlines, pair arm/frame/anchor deadlines | raw 입력·raw 내부 deadline, 또는 report/report 중복 제거 비교. 추가 시간 혼용 없음. 로그/스냅샷의 반올림 값은 해당 제어 조건에 재입력되지 않는다. |

기존 기록은 반올림된 명령을 그대로 갖는다. 이를 자동으로 보정하거나 과거 결과를 새 후보의 물리 성공으로 승계하지 않는다. 회귀에서는 원본의 독립 raw state 이벤트를 써서 **동일 입력을 새 host가 기록하는 경로**를 비교한다.

## v5h 사전등록

[prereg_v5h.json](prereg_v5h.json)은 v5g 바이트를 보존하는 새 등록이다.
`execution_source_sha=null`, `execution_authorization=null`, `execution_status=not_run`이다.

- dev13: nominal, seed **909**.
- dev14: carry-GO abort, seed **910**.
- v5g의 cargo setup·coarse order·intervention 및 판단/예산/물리 조건은 보존한다. ID/seed와 setup-only scene hash만 새 코호트로 바꿨다.
- runner는 v5h와 두 새 run만 허용한다. scene/grasp의 현재 소스 영수증을 갱신하고 source closure에 추가 수정한 `owncam_memory.py`를 포함한다. 별도 workflow/bundle ID는 할당하지 않았다.
- `registration_sha256 = scripts.zone_pair_authorization.digest(registration_payload(prereg))`. JSON 정렬·구분자 및 `execution_authorization`, `registration_sha256` 제외 규칙을 그대로 썼다.
- 코디네이터가 이후 커밋하고 `execution_source_sha`를 채우면 payload가 바뀌므로 등록 해시도 다시 계산해야 한다. 실행 승인은 현재 없으며 기존 인증 경로는 변경하지 않았다.

## 검증

최종 수치와 보존 검사는 아래 완료 기록에 덧붙인다.

새 회귀는 저장 보고 **158개(79+79)**의 기존 실패/수정 통과, 명령 시각의 양방향 반올림 경계, 실제 미종료 이동(1 ns 포함), 정지 전/오래된/미래/미초기화 보고, 높은 σ, gate dwell 대기, 표식 없는 fake provider, 새 fix 없음/거부, raw sweep 전·동시·미래 fix 거부, beam cache/pose guard 단조 시계, memory raw fix를 다룬다.

최초 집중 실행의 테스트 fixture 인터페이스 누락을 보완했다. 후속 집중 실행은 **224 passed, 3 failed**였고, 3건은 최신 등록 테스트가 이전 seed/선행 등록/revision을 기대하던 부분이었다. v5h로 갱신했다. 첫 전체 실행은 **1,567 passed, 1 failed, 2 skipped, 275 subtests passed**였다. 실패는 memory v2 보존 검사에서 이번 raw-time 수정의 새 SHA를 허용하지 않았기 때문이다. 과거 `v2_preservation.json`은 유지하고 `test_owncam_memory_v3.py`에 이번 파일의 정확한 successor SHA만 명시했다. 다른 파일과 과거 실험 기록은 여전히 기존 해시와 같아야 한다. 과거 결과의 자격을 수정본에 승계하지 않는다.

물리 step이 필요한 기존 두 host 테스트는 비물리 플러그인이 명시적으로 skip한다. 실행한 모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, `tests.pose_provider_no_physics`를 적용했다.

## 남은 범위

새 dev13/dev14 물리 실행과 표식 없는 실제 위치 추정/파지 성능은 미검증이다. gate·relook 예산·blockage 개선은 별도 후속이다. 이번 결과는 코드 회귀와 prepare-only 검증이므로 신규 TensorBoard 실험 snapshot은 만들지 않았다. UGRP 예외에 따라 Drive는 사용하지 않았다.

시작 시 `git fetch origin`은 공용 `.git/worktrees/.../FETCH_HEAD` 쓰기 제한으로, `gh pr list`는 GitHub 연결 실패로 완료하지 못했다. 원격 최신 PR 상태를 확인한 결과가 아니며 PR 댓글·커밋·push·병합도 하지 않았다.

## 최종 완료 기록

**1,687 passed / 0 failed / 2 skipped / 275 subtests passed**, 141.34초. 두 skip은 실제 물리 host 테스트다.

비물리 가드 `physical_step_attempts=0`, `real_vision_worker_attempts=0`, `network_attempts=0`. dev13·dev14 prepare는 `prepared_not_executed`, `applied=null`, `physical_success=null`, `model_calls=0`이며 원본 prepare manifest를 보존했다.

원본 주요 파일 12개와 frame input 158개, 과거 사전등록 12개 해시 일치. `owncam_time`, align/gate/blockage/파지/필터 소스 및 memory-v2 보존 manifest는 기준 HEAD와 바이트가 같다. `.pytest_tmp` 삭제 완료. 최종 `git diff --check` 통과.

v5h 등록 해시: `65229f3ea40bf4fccba508214f83fc84574fcd65a469047b985a88563902e79f`. 실행 소스/승인은 null 유지.

전체 명령·수치: [result.json](v5h_validation/result.json). 최종 pytest 출력: [pytest_final.txt](v5h_validation/pytest_final.txt). 원본/과거 파일 보존: [preservation.json](v5h_validation/preservation.json).

## 변경 파일 목록

- `experiments/2026-09-27-zone-pair-dev/changes_v5h.md`
- `experiments/2026-09-27-zone-pair-dev/dev11_12_diagnosis.md`
- `experiments/2026-09-27-zone-pair-dev/prereg_v5h.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/dev13_prepare_manifest.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/dev14_prepare_manifest.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/first_full.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/focused.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/preservation.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/pytest_final.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/result.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_validation/time_audit.json`
- `harness/owncam_memory.py`
- `harness/zone_own_team_host.py`
- `harness/zone_pair_guards.py`
- `scripts/run_zone_pair_dev.py`
- `scripts/zone_pair_grasp_contract.py`
- `tests/fixtures/zone_pair_v5h/README.md`
- `tests/fixtures/zone_pair_v5h/host_v5g.py`
- `tests/fixtures/zone_pair_v5h/reports.json`
- `tests/test_owncam_memory_v3.py`
- `tests/test_zone_pair_authorization.py`
- `tests/test_zone_pair_grasp.py`
- `tests/test_zone_pair_v5c.py`
- `tests/test_zone_pair_v5h.py`
- `tests/test_zone_start_dock.py`

## review10 후속 — standalone raw 시각과 memory 시간 계약 (2026-09-28)

기준 HEAD는 `dde83c3d2501e3b5edf92f52fc1a12195f2d781a`다. 위의 v5h 최초 검증과
prepare 기록은 당시 기록으로 보존했다. 이 절의 변경은 후속 미커밋 후보이며,
과거 결과를 새 시간 계약의 결과로 재해석하지 않는다.

- **P1:** `scripts/record_owncam_localization.py::LoggingPort.apply/hold`의 시각
  반올림을 제거했다. sink는 기록기뿐 아니라 실제 standalone M1/memory 제어기의
  입력이므로 port와 같은 raw SIM 시간을 전달한다. action의 `t`도 port 시각을
  덮어쓸 수 없다. 실제 역행 거부와 PoseGuard 적분·만료·정착 조건은 유지한다.
- 같은 LoggingPort를 쓰는 localization Recorder, closed-loop, M1, memory v2/v3,
  M2 pair 경로를 확인했다. Recorder/closed-loop/M1의 `inputs/frames.jsonl` 시각은
  offline localizer replay에 재입력될 수 있어 raw로 통일했다. M1 runtime 영수증에는
  공유 LoggingPort 소스도 추가했다. 평가 전용·화면 표시 기록의 반올림은 유지한다.
- **P2:** `harness/owncam_memory_time.py`에 `raw_sim_v1`을 정의하고 메모리
  snapshot·fix·event, standalone `memory_runner.json`과 manifest의 student,
  CLI `condition_label`, pair grasp contract 및 통합 실행 bundle의
  `memory_time_contract`에 기록한다. memory algorithm의 v2/v3 schema와 시간 계약을
  별도로 식별한다. 계약이 없는 과거 기록의 표시에는 새 계약을 추정해 붙이지 않는다.
  matched OFF도 memory를 사용하므로 같은 계약을 기록한다.
- `last_fix/last_look_fix`의 raw 저장은 이전 v5h 동작 그대로이며 이번에는 버전
  표기를 추가했다. v2/v3의 since/freshness 조건·허용 오차, frozen PF의 quantized
  report 및 기존 `1e-4 s` 보고 비교 계약은 변경하지 않았다. raw fix 시각을
  반올림된 report나 age에서 역산하지 않는다.

### 후속 전수 조사와 보존

`harness/owncam_*`, M1 harness, `scripts/record_owncam_*`, M1 runner와
closed-loop의 **39개 파일·198개 round 호출**을 AST로 열거하고 시각 소비자를
추적했다. [time_audit.json](v5h_review10_validation/time_audit.json)에 소스 해시와
분류를 남겼다. 남은 시간 반올림은 diagnostic event/snapshot·평가·wall/load 출력과
기존 PF 보고 계약이다. `cyan.t`는 시간 판단에 쓰이지 않고 cluster는 좌표만 읽는다.
step 개수/PWM/기하 값의 정수화는 명령·관측 시계 반올림과 구분했다.

[보존 검사](v5h_review10_validation/preservation.json)는 **348개 모두 일치**한다.
원본 주요 파일 12개와 입력 frame JSON 158개, 과거 사전등록 12개,
유지 runtime/보존 manifest 7개, 기존 fixture 3개, 과거 RGB bundle 및 memory v2/v3
기록 156개를 확인했다. 과거 bundle·freeze·결과 파일을 수정하지 않았다.
기존 보존 테스트는 변경된 현재 소스의 정확한 successor SHA만 명시하며,
임의 변경은 계속 실패한다. 새 테스트 파일은 CI 목록에도 등록했다.

### 사전등록과 비물리 검증

- `prereg_v5h.json`에 후속 계약과 현재 source 영수증을 반영하고 registration hash를
  다시 계산했다: `f1425ccff7494c60c53279fa3a2a13aadb1f6710728017e05f5a7f5afc73b45d`.
- **dev13/909, dev14/910 유지**. `execution_source_sha=null`,
  `execution_authorization=null`, `execution_status=not_run`을 유지한다.
  두 run은 새 등록으로 prepare-only 검증했으며 새 manifest를 이 후속 기록에 보존했다.
  `applied=null`, 물리 성공 없음. 기존 prepare manifest를 덮어쓰지 않았다.
- 실제 `M1OwnCamDeliveryMemV3`와 가짜 port·자기 이미지로 수정 전 **7 failed**를
  재현했다. `2.000049` 관측 후 hold에서 하향 반올림 역행, `2.000051` 명령 후
  raw 관측에서 상향 반올림 역행을 확인했다. hold·arm·mecanum, 실제 역행 거부,
  입력 frame timestamp, `look_fix_since`와 freshness 만료 경계·미래 fix,
  기록/표시/번들 시간 계약을 검사했다. 수정 후 최초 집중 검사는 **30 passed**였다.
- 첫 전체 검사는 **1,744 passed / 4 failed / 2 skipped / 378 subtests passed**였다.
  실패는 새 raw frame 소스의 M1/M2 보존 hash 2건, 새 시간 계약 모듈의 import 허용
  목록 1건, 이전 v5g `copy` import의 허용 목록 누락 1건이었다. 과거 manifest를
  변경하지 않고 exact successor/명시적 허용 목록으로 정리했다. 후속 집중 검사는
  **59 passed / 0 failed / 269 subtests passed**다.
- 모든 pytest는 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`,
  `tests.pose_provider_no_physics` 가드로 실행했다. 실제 MuJoCo step이 필요한
  기존 host 테스트 2개는 명시적으로 skip한다. 최종 수치는 아래 완료 기록과
  [pytest_final.txt](v5h_review10_validation/pytest_final.txt)에 있다.

코드/prepare 검증만 수행했으므로 TensorBoard 실험 snapshot은 추가하지 않았다.
신규 물리 실행·실제 모델 호출·잠금 획득·Git 커밋·push·병합은 없다.
원격 최신 상태 조회는 공용 Git 메타데이터 쓰기 제한과 GitHub 연결 실패로
미완료다. 로컬 브랜치/HEAD와 사용자 지정 리뷰 대상은 일치한다.

### review10 최종 완료 기록

**1,765 passed / 0 failed / 2 skipped / 381 subtests passed**, 149.97초.
가드의 physical_step_attempts, real_vision_worker_attempts, network_attempts는 모두 0이다.
`.pytest_tmp` 삭제와 `git diff --check` 통과를 확인했다.
전체 명령·검증 기록: [result.json](v5h_review10_validation/result.json).

### review10 변경 파일

- `experiments/2026-09-27-zone-pair-dev/changes_v5h.md`
- `experiments/2026-09-27-zone-pair-dev/prereg_v5h.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/dev13_prepare_manifest.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/dev14_prepare_manifest.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/preservation.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/pytest_final.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/pytest_focused.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/pytest_full.txt`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/result.json`
- `experiments/2026-09-27-zone-pair-dev/v5h_review10_validation/time_audit.json`
- `harness/owncam_memory.py`
- `harness/owncam_memory_time.py`
- `scripts/record_owncam_localization.py`
- `scripts/run_ci_tests.py`
- `scripts/run_m1_owncam.py`
- `scripts/run_m1_owncam_memory.py`
- `scripts/run_m1_owncam_memory_v3.py`
- `scripts/run_owncam_closed_loop.py`
- `scripts/run_zone_study_integration.py`
- `scripts/zone_pair_grasp_contract.py`
- `tests/test_m1_owncam.py`
- `tests/test_owncam_memory.py`
- `tests/test_owncam_memory_time.py`
- `tests/test_owncam_memory_v3.py`
- `tests/test_record_owncam_time.py`
- `tests/test_zone_pair_executor.py`
