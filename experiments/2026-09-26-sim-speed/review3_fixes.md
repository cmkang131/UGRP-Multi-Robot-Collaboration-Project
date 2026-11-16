# PR #236 round-3 수정 기록 — 2026-09-27

기준은 `codex/sim-speed-fix@78945a3c3ab3cf4a0e24aeaa786d0f9f6736dd88`이다. 지정된 `codex-236-review.md` 73행 전체를 읽고 P1 3건·P2 3건을 수정했다. 이 worktree의 파일만 편집했다. `.git` 쓰기·fetch·커밋·push·live slot 디렉터리 접근·다른 worktree 변경은 하지 않았다. 커밋은 coordinator가 담당한다.

| 리뷰 | 수정 | 수정 전 실패 → 수정 후 통과 (`tests/test_sim_speed_review3.py`) |
|---|---|---|
| 1 P1 회수된 리더의 재사용 PGID에 신호 전달 | `poll()` 진입 전에 신호 전달을 차단하고, 미회수 자식의 시작 식별자와 리더 PGID를 확인한 경우에만 전달. 리더 회수 이후에는 전달하지 않고 남은 그룹의 종료를 기다림. SIGCHLD 기본 처리 요구 | `test_never_signal_reaped_group_even_when_pgid_reused` 2조건. 추가 양성/음성: live poll 중 보류 및 식별자 일치/불일치 |
| 2 P1 숨겨진 Linux PID를 sim 0개로 간주 | proc mount의 hidepid/부분 mount/overlay와 PID namespace를 확인. root 소유의 부팅별 호스트 기준이 없거나 불일치하면 입장 거부. 그룹 종료 확인에서도 census 불확실성은 예약 유지 | `test_linux_hidden_or_unproven_host_census_is_rejected` 4조건. 추가 정상 empty census, boot/namespace/overlay/subtree/hidepid 반례 및 `test_linux_group_exit_requires_visible_census` |
| 3 P1 동일한 로그 누락/절단을 전체 동일로 판정 | M1 v3 필수 로그 9개와 manifest SHA-256 요구. result 개수, frame 인덱스와 eval 정렬, frame/GT 시작·간격·종료, grasp/lift/carry/release/look_back 단계와 macro/skill/retention 증거 검증 | `test_identical_missing_full_logs_are_insufficient` 7조건, `test_full_log_completeness_beyond_qpos` 10조건. 잘못된 phase 타입 2조건도 증거 부족으로 처리 |
| 4 P2 5스텝 종료 후 상태 변경 누락 | 매 mj_step 직후 마지막 상태를 해시해 보존하고, 종료 상태와 별도 저장/대조. 정규 간격 사이 종료도 마지막 **물리 스텝** 스냅샷을 추가. profile schema v3 | `test_final_physics_state_preserved_before_between_checkpoint_mutation`. 추가 4/5스텝 저장 검증, 실제 MuJoCo 5스텝 반례 (`test_sim_speed_runtime.py::ProfileRestoreTests::test_last_step_survives_real_mujoco_state_mutation`) |
| 5 P2 로딩된 Python 호출자 이중 집계 | `sim_slot()`은 현재 PID가 미예약 MuJoCo 프로세스로 확인된 경우에만 한 자리를 기존 집계에서 예약으로 전환. 새 worker 입장에는 공제하지 않음 | `test_sim_slot_can_reserve_already_loaded_caller_at_cap_one`. 추가 새 worker 공제 금지 및 caller+child의 2개 예약 |
| 6 P2 JSON 값 비교로 바이트 차이 소실 | 명령·9개 로그·result 원본 파일 바이트 SHA-256 비교. JSON 파싱은 검증/진단용. prefix도 원본 행 바이트 유지; 키 누락/null 진단 구분 | `test_full_comparison_requires_original_bytes` 4조건: 숫자 표기/키 순서/공백, event log, result 직렬화, 추가 null 필드 |

정상 M1 전체 fixture와 prefix 양성 대조군도 통과했다. 종전 테스트의 최소 fixture는 실제 필수 로그 계약을 만족하는 공용 `tests/sim_speed_fixtures.py`로 바꿨다. round-2의 qpos 부정 테스트가 다른 로그 누락 때문에 우연히 통과하지 않도록 정상 전체 로그를 갖춘 뒤 qpos만 변조한다. 새 회귀 파일은 offline CI `TEST_PATTERNS`에 포함했다.

## 검증

모든 pytest는 지정 interpreter `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`, `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, worktree 내부 `TMPDIR`/`--basetemp`를 사용했다. 슬롯 파일은 임시 디렉터리에만 만들었다. lifecycle 테스트는 실제 flock·자식 프로세스를 사용하지만 입장 census는 격리 fixture이며, Linux 호스트 가시성은 별도 proc fixture로 검증했다.

- 여섯 항목 핵심 회귀 **29 failed → 모두 통과**. HEAD 원본 3개 모듈을 worktree 안에 복사해 새 테스트에 로드했다. 원본 worktree나 Git 이력을 바꾸지 않았다. 기록: `tmp/round3-tests/red-verified.txt` (1.63초).
- 그룹 종료 가시성·잘못된 phase 타입 추가 반례 **3 failed → 모두 통과**: `additional-red.txt`.
- 실제 MuJoCo 5스텝 종료 후 상태 변경 **1 failed → 통과**: `runtime-red.txt` (0.60초).
- 최종 관련 검사 **127 passed, 37 subtests passed** (34.66초): `final.txt`. 신규 round-3 파일은 45개이며 기존 round-2·도구·슬롯·exact-v1·복원 테스트를 함께 실행했다.
- 테스트용 CLI의 Linux 가시성 격리를 명시한 뒤 관련 프로세스 수명 검사 3개도 재확인했다: `cli-final.txt`.
- `git diff --check`, DRAFT JSON 파싱·미실행 상태·2 seed/8회·필수 로그 9개 확인 통과.

최종 검사 명령:

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/tmp/test-env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_sim_speed_review3.py tests/test_sim_speed_review2.py \
  tests/test_sim_speed_tools.py tests/test_sim_slots.py tests/test_exact_speedups.py \
  tests/test_sim_speed_runtime.py::ProfileRestoreTests \
  --basetemp="$PWD/tmp/round3-tests/final"
```

핵심 red 재현은 `tmp/round3-tests/run_baseline.py`로 HEAD의 `baseline_sim_{slots,equivalence,profile}.py`를 로드하고 round-3의 표에 적힌 7개 핵심 테스트 함수만 선택했다. signal 반례는 실제 PGID 재사용을 강제하지 않은 합성 순서 검사다.

`sim/exact_speedups.py`는 HEAD와 현재 파일이 바이트 동일하다. SHA-256은 `bed93e497127dd4b9c35f58fad1209a2ca6f0e3aed72de4945f6983f08ddac49`다. exact-v1 산술·접촉 필터·기본값을 변경하지 않았다.

## 남은 범위

- 실제 Linux 호스트의 hidepid/namespace/관리자 기준 배치 및 완전한 Mac 호스트 census 통합은 이번 작업에서 실행하지 않았다. Linux는 관리자가 실제 호스트에서 `/etc/ugrp/sim-slots-host.json`을 준비하기 전에는 거부한다. 이 파일을 자동 생성하거나 실제 슬롯 경로를 갱신하지 않았다. 제한 환경을 sim 0개로 해석하지 않는다.
- 리더 회수 뒤에는 다른 작업에 잘못 신호를 보내지 않기 위해 후속 SIGINT/SIGTERM을 숫자 PGID에 전달하지 않는다. 자손이 자연 종료하지 않거나 liveness를 확인할 수 없으면 예약을 유지하며 기다린다. 자동 강제 종료는 없다.
- 기록기는 마지막 mj_step 상태를 매번 갱신하지만 저장된 qpos 자료는 여전히 주기별 샘플이다. 초기 상태부터 모든 물리 스텝을 포함하는 **누적 상태 체인**은 아직 없다. 추가 해싱 오버헤드를 포함해 향후 A/B는 동일 계측을 사용해야 한다.
- [전체 A/B 초안](prereg_default_check_DRAFT.json)에 필수 파일·원본 바이트·완전성 정책과 현재 M1 단계 필드를 반영했다. 여전히 **미등록·미실행**, execution_authorized=false다. 최종 SHA/환경/입력/실행 명령/예산, 누적 상태 기록·연속성 검증, 실제 단계/도달 판정과 표준 workflow 연결을 확정한 후 2 seed × 4회 전체 A/B가 필요하다. 연구 기본값은 계속 `none`, exact-v1 기본값 채택은 HOLD다.
- 전체 에피소드·성능 비교·pair 실행은 하지 않았다. 내부에서 Git 저장소를 생성/커밋하는 `PairProfSourceTests`와 전체 CI 실행기는 호출하지 않았다. 이번에는 새 실험 결과가 없어 TensorBoard snapshot을 만들지 않았고, 실제 A/B 결과 전달 조건은 초안에 유지했다. Drive는 사용하지 않았다.
