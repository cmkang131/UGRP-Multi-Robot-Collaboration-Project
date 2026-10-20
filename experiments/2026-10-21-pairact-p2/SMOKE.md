# pairact P2 smoke: MJWarp GT 공동 운반·하차 (world 1·11·17, gcp6)

설계: teacher 브랜치 `dsh/pairact-p2-carrypath`의 `experiments/2026-10-21-pairact-p2/DESIGN.md`.
목적은 *경로가 GPU에서 끝까지 돌고 evaluator가 판정을 남기는지* 확인하는 것입니다. 관문이 아닙니다.

## 0. 규칙

- 오프피크(UTC 16:30–00:30)에만 실행합니다. VM은 gcp6 하나, 새 VM 금지, 끝나면 정지합니다.
- 새 run root `/home/ugrp/ugrp-sim/runs/pairact-p2/`만 씁니다. r13 cases·plan·export·native refs·rejection table은 *읽기만* 합니다.
- *결과 미합산*: 이 smoke의 파지 성공·운반 성공은 r13 gate(37/40)나 다른 어떤 실행과도 합산하지 않습니다. CPU 결과(beampair7, b-v6e)와도 합산하지 않습니다.
- 학습 기록 off(runner가 carry와 기록을 함께 켜면 거부합니다).
- 재실행은 1회까지입니다. 두 번째도 HOST_ERROR면 멈추고 Claude 리뷰를 요청합니다.

## 1. 스택

| tree | 브랜치 | SHA |
|---|---|---|
| teacher | `dsh/pairact-p2-carrypath` | `208e61490cfc19aef2a95954841e76a929fc0666` |
| adapter | `dsh/pairact-p2-carrypath-a` | `76532d0dd6aa770cea19c65a734b893159d898de` |
| root | `dsh/pairact-p2-carrypath-r` | 이 문서가 들어 있는 커밋(`git rev-parse origin/dsh/pairact-p2-carrypath-r`) |

smoke는 기본 하강(`grasp_height`)으로 돌립니다. 바닥 접촉 하강은 별도 후보 `pairact_p2_r13_floor`(teacher DESIGN §2-1, 기본 off)이고, smoke에서 `not_resting`이나 공중 열기가 보일 때 *다른 world 집합*으로 따로 확인합니다.

r13과 다른 점은 adapter 후보 `pairact_p2_r13`(= `beamact5_r13` 프로필 + `pair_carry=pair_carry_gt_v1`, `carry_cap_s=110`)과 pin 3개, root summary의 `carry_success`/`carry_failure` 필드뿐입니다. physics/contact/scene 플래그는 r13 실행과 같습니다.

## 2. 준비 (CPU, 수 분)

```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p2; RUN=/home/ugrp/ugrp-sim/runs/pairact-p2
mkdir -p $SRC $RUN
for t in teacher:208e61490cfc19aef2a95954841e76a929fc0666 adapter:76532d0dd6aa770cea19c65a734b893159d898de root:origin/dsh/pairact-p2-carrypath-r; do
  name=${t%%:*}; rev=${t#*:}
  git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/$name $rev   # 기존 레포 경로는 [확인 필요]
done
git -C $SRC/root rev-parse HEAD   # 이 값을 ROOT_SHA로 기록

# 순수 함수 테스트 (simulator 불필요)
cd $SRC/teacher && python -m pytest -q tests/test_pair_carry_teacher_warp.py          # 기대: 34 passed
cd $SRC/adapter && python -m pytest -q tests/test_pairact_p2_adapter.py               # 기대: 3 passed
cd $SRC/root    && python -m pytest -q tests/test_pairact_p2_root.py                  # 기대: 6 passed

# cases: r13 cases(sha 3d4e065d…)에서 world 1·11·17만 뽑고 candidate만 바꿉니다
cd $SRC/root && python experiments/2026-10-21-pairact-p2/make_p2_cases.py \
  --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json \
  --out $RUN/p2-smoke-cases.json      # 출력 sha256과 seed 3개를 기록
```

### smoke world 선택 규칙 (결정적, 운반 실행 전 고정)

1. 입력: `r13-funnel-attempt1.json`(이 폴더, `claude/beamact5-r2-t` `0610c95e5`의 `experiments/2026-10-17-beamact5/runs/gate39-r13-run/funnel-attempt1.json`과 바이트 동일, sha256 `31027ffb…f60c2`). r13 39-gate attempt 1의 world별 기록입니다.
2. `succ = true`인 world만 남깁니다(37개).
3. `sim`(에피소드 종료 SIM s = 두 teacher 모두 `complete` = 공동 파지 + 3초 유지 완료 시각) 오름차순, 동률이면 `case`(world id) 오름차순으로 정렬합니다.
4. 앞의 3개를 씁니다. 코드: `make_p2_cases.select_worlds()`, 테스트 `test_smoke_worlds_are_fastest_r13_grasps`.

| 순위 | world | attempt1 sim | attempt2 sim(참고) |
|---|---|---|---|
| 1 | 1 | 22.8 | 23.0 |
| 2 | 11 | 24.3 | 24.3 |
| 3 | 17 | 25.2 | 24.7 |
| (4) | 13 | 26.9 | 27.5 |

- attempt 2(`r13-funnel-attempt2.json`, `376c006f1`)에 같은 규칙을 적용해도 1·11·17이 나옵니다(테스트 `test_attempt2_agrees_on_the_same_three_worlds`). 판정에는 attempt 1만 씁니다.
- 이전 선택 6·10·20(54.7 / 49.5 / 36.3 SIM s, attempt2의 20은 55.2 s)은 파지 cap 60 s에 가까워 운반 경로를 보기 전에 파지 변동으로 smoke가 끝날 위험이 있어 바꿨습니다. 이 규칙은 *파지 속도*만 보고 운반 결과를 보고 고른 것이 아닙니다.
- 빨리 잡는 world만 쓰므로 운반 시작 배치가 쉬운 쪽으로 치우칠 수 있습니다. smoke는 경로가 끝까지 도는지만 보며, 성공률 근거로 쓰지 않습니다.

## 3. 실행 (GPU, 오프피크)

r13 실행(`diag-r13-27-repeat1/summary.json`의 `reproduce`)과 같은 플래그에서 source·cases·indices·out만 바꿉니다.

```bash
cd $SRC/root   # r13은 WARP_SOURCE_ROOT로 cd하지 않아 texture 경로 오류가 난 적이 있습니다(README-r3 §3-2)
python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair \
  --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/p2-smoke-cases.json --indices 0,1,2 \
  --cap-s 60 --out $RUN/smoke-1 --vm-hourly-usd 1.096 \
  --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
  --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
  --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
  --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
  --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json \
  --batch-per-world-speed-v1
```

- [확인 필요] `beamact5-tools/run_warp_flow_teacher_gcp6.py`는 VM에만 있는 wrapper라 레포에서 내용을 볼 수 없습니다. 이 wrapper가 *어느 root 체크아웃*을 실행하는지 먼저 확인합니다. root 경로를 고정해 두었다면 복사본(`run_warp_flow_teacher_gcp6_p2.py`)에서 root 경로만 `$SRC/root`로 바꿉니다. 판정 기준: 실행 후 `summary.json`의 `source_sha`가 ROOT_SHA와 같아야 합니다. 다르면 그 실행은 무효입니다.
- `--cap-s 60`은 파지 구간 cap이고, runner가 handover 뒤 110 SIM s를 더합니다(최대 170 SIM s/world).
- 예상: world 3개 × 최대 170 SIM s. r13의 per-world wall/SIM 비율로 약 25–50분 [확인 필요], L4 약 $1.1/h라 약 $1 이하. 실측 wall·비용을 기록합니다.

## 4. 볼 것

| 파일 | 내용 |
|---|---|
| `$RUN/smoke-1/summary.json` | `worlds[].success`(= 파지 gate 성공, 기존 정의), `carry_success`, `carry_failure`, `source_sha`, HOST_ERROR |
| `world-00k/raw/carry-eval.json` | evaluator 판정: success, failure, funnel(1 m 운반·문 통과·zone 안·내려놓음·해제·정지), drop_events, robot_robot_contact_ticks, wall_contact_*(기록만), final_beam_pose |
| 같은 파일 → `drive_response` | *eval-only* 단계·로봇별 명령 몸체 속도 대비 GT 몸체 속도(`speed_ratio`, `turn_ratio`, `stall_ticks`, 바퀴 듀티·펄스 폭). 성공 판정·단계 timeout과 무관(`affects_* = false`) |
| 같은 파일 → `phase_report` | 단계별 소요·cap·교사 timeout 코드(교사 events)와 같은 단계 drive 집계를 *나란히, 따로* 표시. 보고 시 timeout 단계의 `speed_ratio`를 같이 적습니다 |
| `world-00k/raw/result.json(.zst)` → `carry` | 교사 outcome, events(단계 전환 시각), route·route_info(문 폭 필요/가용, 대기점, variant), max_stretch_m, max_track_err_m, retreat 종류 |
| `world-00k/raw/teacher-r?.jsonl` | 운반 라벨(`teacher_phase = carry:<단계>`) |
| `world-00k/review-2hz/` | 자기 카메라 2 Hz(검토용) |

파지가 실패한 world는 `carry.started = false`(`no_joint_hold_3s`)로 남고 운반 판정이 없습니다. 이것은 운반 실패가 아니라 *운반 미시작*으로 따로 셉니다.

## 5. 사전 등록 (실행 전 고정)

- smoke 통과 조건(P2 완료 기준): 3개 world 모두 실행 완료(HOST_ERROR 0), 파지가 된 world는 모두 운반이 시작되고(`carry` 존재) `carry-eval.json`이 생성됩니다.
- 운반 성공 정의(DESIGN §5): 빔 GT footprint가 zone B 안(내려놓음·해제·정지) ∧ 낙하 0 ∧ 로봇 간 접촉 0. 벽 접촉은 기록만 합니다.
- 보고 형식: world별 한 줄(seed, 파지 성공, 운반 시작, carry_success, carry_failure 또는 교사 outcome, 도달한 퍼널 마지막 단계, 운반 SIM s, 벽 접촉 tick). *n/3을 합산 성공률로 쓰지 않습니다.*
- smoke 결과로 `Params` 상수를 바꾸면 그것은 새 후보이고, 다른 world 집합에서 다시 확인합니다.

## 6. 막히면

- HOST_ERROR(CUDA 700, SIGSEGV): 로그와 `progress.json`을 보존하고, 1 world(`--indices 0`)로 1회만 다시 봅니다. P0 진단(CUDA fault) 결과와 같이 보고합니다.
- `route_blocked`·`staging_unclear`·`door_clearance_insufficient`: 경로 기하 문제입니다. `route_info`와 handover 오프셋을 첨부해 Claude에게 넘깁니다.
- `formation_tracking_lost`·`*_timeout`: 몸체 속도 환산(DESIGN §3 [확인 필요])일 가능성이 큽니다. `carry.events`와 `max_track_err_m`을 첨부합니다.
- `not_resting`: 하강 목표 높이 문제(DESIGN §8-5). `final_min_z`를 첨부합니다.
