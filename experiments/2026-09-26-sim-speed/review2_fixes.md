# PR #209 round-2 수정 기록 — 2026-09-27

작업 위치는 `codex-sim-speed-fix`, 기준 HEAD는 `325559eb59f034685dca667801647a046bb93690`이다. 지정 리뷰 `codex-209-review2.md` 전체의 P1 네 항목·P2 세 항목을 대상으로 했다. `.git` 변경·fetch·커밋·push·PR 댓글·live slot 접근·다른 worktree 변경·새 에피소드 실행은 하지 않았다. 커밋은 coordinator가 담당한다.

| 리뷰 | 변경 | 수정 전 실패 → 수정 후 통과 테스트 (`tests/test_sim_speed_review2.py`) |
|---|---|---|
| 1 P1 qpos 증거가 양쪽 모두 잘려도 통과 | 각 측의 step/t/sha256 형식, 간격/순서/총 스텝/시간/개수/최종 상태를 profile과 대조. 구간 미도달은 양쪽 모두 같아도 `insufficient_evidence`. 전체 비교는 최종 시간과 result.sim_s도 대조 | `test_qpos_schema_rejects_identical_malformed_rows` 6조건, `test_qpos_completeness` 11조건 |
| 2 P1 열린 FD 오인·자식보다 빠른 release | 커널 잠금과 PID/start identity가 맞는 예약만 연결. release는 close만 수행. CLI는 자기 작업 그룹의 살아 있는 자손이 종료될 때까지 예약 유지. 신호도 그 그룹에만 전달 | `test_release_keeps_inherited_child_reservation`, `test_open_slot_file_without_lock_is_not_a_reservation`, `test_cli_holds_until_background_child_without_fd_exits` |
| 3 P1 다중 자식을 슬롯 하나로 집계 | 예약 하나가 MuJoCo 로딩 프로세스 하나만 상쇄. 추가 자손은 별도 집계. `--workers N` / `workers=N`은 N개 슬롯을 원자적으로 예약 | `test_nine_children_cannot_hide_behind_one_reservation`, `test_nine_children_count_is_nine_with_verified_owner`, `test_multiworker_reservation_is_atomic` |
| 4 P1 부분 census·PID 재사용 | 살아 있는 Linux PID의 maps/fd/stat 권한·형식 오류는 거부. macOS lsof 비정상 종료/부분 결과 거부. Linux 시작 tick 및 macOS libproc 시작 초/마이크로초 식별자를 검증하고 스냅샷 사이 변화도 거부 | `test_live_proc_permission_error_fails_closed`, `test_partial_lsof_failure_is_not_a_census`, `test_pid_reuse_cannot_cover_a_new_sim`, 추가 Linux/macOS snapshot 반례 |
| 5 P2 import를 실제 실행으로 표현 | 계약을 `loaded_mujoco_process_upper_bound`로 명시. import-only 프로세스와 queue FD opener도 센다. `active_sim_count=null`; 실제 stepping을 관측했다고 보고하지 않음 | `test_import_only_contract_is_explicit` |
| 6 P2 비용/timeout | 저비용 주장을 제거. 단조 시계의 총 입장 deadline을 nonblocking 전역 잠금·census subprocess·스캔 루프·예약 반환에 적용. census 자체도 5초 예산 | `test_timeout_includes_admission_lock_wait`, `test_lsof_and_identity_scan_share_admission_deadline` |
| 7 P2 Linux root | Mac 기존 공용 root 유지, Linux는 worktree/HOME과 독립적인 `/var/tmp/ugrp-sim-slots`. 다중 사용자의 공용 그룹·권한 설정은 관리자 조건으로 명시 | `test_linux_root_is_shared_across_worktrees_and_portable` |

`sim_profile.py`는 v2 메타데이터와 간격 사이 종료의 마지막 상태를 기록한다. 배치 stepping·다중 world·timestep 변경·마지막 step 뒤 상태 변경은 증거 오류로 표시한다. 주기별 단일 상태 샘플을 매 스텝 누적 상태 해시라고 표현하지 않는다. 기존 v1 원본에 최종 메타데이터를 사후 주입하지 않았으며, 이런 원본은 새 검사로 전체 상태 동등성을 인증할 수 없다.

`sim/exact_speedups.py`는 변경하지 않았다. 기준 HEAD와 현재 파일 바이트 동일 및 SHA-256 `bed93e497127dd4b9c35f58fad1209a2ca6f0e3aed72de4945f6983f08ddac49`를 확인했다. 기본값은 계속 `none`이다.

## 검증

Python은 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. 모든 pytest에 `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, worktree 안의 `TMPDIR` 및 `--basetemp`를 지정했다. 모든 슬롯 테스트는 임시 root를 사용한다. CLI 입장 테스트의 census는 독립 fixture로 한정하고 실제 flock·자식 프로세스 수명을 확인했다.

- 수정 전 핵심 회귀: **26 failed** (`tmp/round2-tests/red.txt`). 입력 파일·Linux proc fixture·실제 상속 FD 및 잠금 대기 반례로 원래 결함을 재현했다.
- 확장 회귀: 원본 소스의 읽기 전용 복사본을 별도 모듈로 로드해 새 API/경계도 확인했다 (`red-final.txt`, 별도 CLI 반례 `red-background2.txt`). 복사본만 사용했으며 `.git`은 쓰지 않았다.
- 최종 관련 검사: **71 passed, 3 skipped, 35 subtests passed** (`tmp/round2-tests/final.txt`). 새 테스트 파일의 35개에는 정상 전체/종료 잔여 구간의 양성 대조군도 포함된다.
- exact-v1 기존 비트 동일성 + 준비 실패 복원: **10 passed, 2 subtests passed** (`tmp/round2-tests/exact.txt`). 전체 에피소드 A/B나 속도 측정은 하지 않았다.
- `git diff --check`, 사전등록 초안 JSON 파싱·미실행 상태·2 seed/8회 순서 검사 통과.

최종 관련 검사 명령:

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/tmp/test-env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_sim_speed_tools.py tests/test_sim_slots.py tests/test_sim_speed_review2.py \
  tests/test_sim_speed_runtime.py::RealCensusTests \
  --basetemp="$PWD/tmp/round2-tests/final"
```

별도 검사 명령은 같은 환경 변수로 `tests/test_exact_speedups.py tests/test_sim_speed_runtime.py::ProfileRestoreTests`, `--basetemp="$PWD/tmp/round2-tests/exact"`였다. 새 회귀 파일은 offline CI 목록에도 추가했다.

## 남은 범위

- 실제 전체 호스트 census 통합 3개는 샌드박스가 일부 PID의 커널 정보 조회를 거부하여 건너뛰었다. 이 환경에서는 입장 자체가 fail-closed로 거부된다. 전 프로세스 가시성이 있는 Mac/Linux에서 실제 census·통합 입장은 추가 확인해야 한다. Linux 분기는 임시 proc fixture로 검증했으며 실제 Linux 호스트 실행은 하지 않았다.
- `PairProfSourceTests`는 내부에서 Git 저장소를 만들고 커밋하므로 이번 파일 편집 전용 작업에서는 실행하지 않았다. pair 에피소드도 실행하지 않았다.
- 예약은 협력적 입장 제어다. 런처는 최대 동시 로딩 프로세스 수를 사전에 `workers`로 예약해야 한다. 과소 신고/우회한 명령의 임의 fork를 OS 수준으로 제한하지 않는다. 기존 식별자 없는 예약은 보수적으로 중복 집계될 수 있다. Linux 다중 사용자 권한은 관리자 설정이 필요하다.
- [전체 A/B 사전등록 초안](prereg_default_check_DRAFT.json)은 **미등록·미실행**이다. s93 A1/B1/B2/A2, s95 B1/A1/A2/B2의 8회와 최대 1회 인프라 대체를 제안한다. 최종 후보 SHA·환경·자산 해시·예산 확정, 매 스텝 누적 상태 기록과 연속성 검증, 관리 workflow 연결 후 등록해야 한다. 파지·상승·운반·방출·최종 확인과 seed별 instruction 5% 감소 게이트를 모두 만족하기 전에는 exact-v1 기본값 채택을 보류한다.
- 새 실험/학습 결과가 없으므로 TensorBoard snapshot은 만들지 않았다. 실제 A/B 결과의 새 snapshot·데이터 로딩·영상·대시보드 확인은 초안의 전달 조건에 포함했다. 결과는 로컬 보관이며 Drive는 사용하지 않는다.
