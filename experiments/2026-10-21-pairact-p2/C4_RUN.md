# pairact P2 -c4 실행 문서 (DeepSeek, gcp6)

gcp6 `pairact-p3-detour-20261021T0320Z`에서 막힌 4건에 대한 -c4 스택과 실행 순서입니다. 결과는 *미합산*입니다. pilot은 *수율 확인*용이며 수집 데이터가 아닙니다(녹화 없음).

## 1. 스택

| tree | 브랜치 | SHA |
|---|---|---|
| teacher | `dsh/pairact-p2-carrypath-c4` | `402bbf155ca162da7a74518eab9b8bd98138299a` |
| adapter | `dsh/pairact-p2-carrypath-a-c4` | `2e4460ee618894542e73e164f9f814a50426b3f8` |
| root | `dsh/pairact-p2-carrypath-r-c4` | 이 문서가 든 커밋 (`git rev-parse origin/dsh/pairact-p2-carrypath-r-c4`) |
| 렌더 | `dsh/e2e-min-render-fix` | `ddcc86f3ca783c68937144d7aa9eebe555a88c44` (`experiments/2026-10-21-e2e-min/RENDER_RERUN.md`) |

-c3과 다른 점:
- teacher: opt-in route 모드(`detour_v1`)에서는 handover 순간에 `raw/carry-route.json`(route, route_info, detour 통계, `plan_wall_s`, `route_plans`, `detour_searches`)을 쓰고, `result.json`의 `carry_route_plan`과 stderr `CARRY_ROUTE_PLANNED {…}`에도 남깁니다. wall cap으로 끝나도 남습니다. 기본 `straight_v1` 후보는 바뀐 것이 없습니다.
- root: 시작 시 MuJoCo·Warp 버전 검사(`RUNBOOK_VENV.md`), `progress.json`·`summary.json`의 `host_loop_s`, seed 범위 refs 명령(`SEED_REFS.md`, `make_seed_refs.py`, `make_p2_cases.py --seed-start`).

## 2. 원인 확인 결과 (코드 근거)

- **6.8 s/tick은 A* 재계산 때문이 아닙니다.** detour A*(`plan_formation_path`)는 `PairCarryTeacherWarp.__init__`에서만 호출됩니다. `start_from_runner`는 runner의 `carry is None` 분기에서 에피소드당 1회만 불립니다(`scripts/run_grasp_act_teacher.py`, `elif carry is not None:` 다음 `elif` 분기). teacher 테스트 `test_detour_search_runs_once_over_the_whole_rollout`가 롤아웃 전체에서 `plan_formation_path`·`carry_route`·`check_route`가 각 1회만 호출됨을 고정합니다.
- **tick당 wall은 world 수에 비례합니다.** root 루프(`scripts/run_warp_flow_teacher.py`의 `while active.any()`)는 world마다 직렬로 capture → tail ring·review JPEG 쓰기 → lane(teacher·runner Python) `next()`를 돌고, 그 뒤 batch `hooks.step`을 한 번 부릅니다. `hooks.step` 안의 `sync_render`도 world×로봇마다 CPU에서 remap과 JPEG 인코딩, `mj_kinematics`를 합니다(`scripts/warp_act_backend.py` `sync_render`).
  - smoke-1c: 3 world, 1501 s / 118.8 SIM s → 1.26 s/tick, world당 0.42 s.
  - 3-world detour: 707 s / 54.2 SIM s → 1.30 s/tick. smoke-1c와 같은 수준이라 회귀가 아닙니다.
  - 20-world: 6.8 s/tick → world당 0.34 s. per_world_wall_SIM은 3.4로, 차단 기준 6 미만이고 경고 기준 3.5 근처입니다.
  - 그래서 20 world에서 1.26 s/tick으로 돌아갈 수는 없습니다. 맞는 비교 단위는 world당 s/tick(또는 `per_world_wall_SIM`)입니다.
- [확인 필요] world당 0.34–0.42 s 중 어디가 큰지(JPEG/kinematics vs teacher)는 레포 기록에 없습니다. -c4의 `host_loop_s`(`capture_s`, `rings_review_s`, `lane_teacher_s`)와 기존 `timing`(`render`, `readback_remap_jpeg_kinematics`, `physics`)으로 다음 run에서 나뉩니다. 줄이는 수정은 이 숫자를 본 뒤에 합니다.
- 707 s wall cap은 레포 코드에 없습니다(VM wrapper 또는 실행 쪽 timeout으로 보입니다) [확인 필요]. 아래 실행에는 예상 wall에 맞춘 cap을 씁니다.

## 3. 순서

```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p2-c4; RUN=/home/ugrp/ugrp-sim/runs/pairact-p2-c4-$(date -u +%Y%m%dT%H%MZ)
PYW=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python; PYS=/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python
mkdir -p $SRC $RUN
for t in teacher:402bbf155ca162da7a74518eab9b8bd98138299a adapter:2e4460ee618894542e73e164f9f814a50426b3f8 root:origin/dsh/pairact-p2-carrypath-r-c4; do
  name=${t%%:*}; rev=${t#*:}; git -C /home/ugrp/ugrp-sim/ugrp fetch -q origin; git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/$name $rev
done
git -C $SRC/root rev-parse HEAD    # ROOT_SHA
cd $SRC/teacher && $PYW -m pytest -q tests/test_pair_carry_teacher_warp.py tests/test_pair_carry_detour.py tests/test_pair_carry_route_c4.py   # 기대 71 passed
cd $SRC/adapter && $PYW -m pytest -q tests/test_pairact_p2_adapter.py                                                                   # 기대 9 passed
cd $SRC/root    && $PYW -m pytest -q tests/test_pairact_p2_root.py tests/test_pairact_p2_runtime_pins.py tests/test_pairact_p2_seed_refs.py   # 기대 37 passed
```

### 3-0. 버전 (수 초)
`RUNBOOK_VENV.md`의 "실행 전 확인" 두 줄을 실행합니다. `RUNTIME_PIN_MISMATCH`가 나오면 멈추고 보고합니다.

### 3-1. seed 8343000–039 refs 생성 (GPU 불필요, 약 6–10분)
`SEED_REFS.md` §2의 a→e를 순서대로 실행합니다(`make_seed_refs.py plan --seed-start 8343000 --n 40`이 전체 명령을 출력합니다). b·c는 `PYS`(3.12)로, a는 `PYW`로 실행합니다. e의 출력 `$RUN/p2-seed8343000-cases.json`의 sha256와 `indices`를 기록합니다. refs가 없으면 e가 `MISSING_SEED_REFS`로 멈춥니다. 그때는 cases를 손으로 만들지 말고 보고합니다.

### 3-2. world 1·11·17 detour 재확인 (GPU, 약 25–40분)
```bash
cd $SRC/root && $PYW experiments/2026-10-21-pairact-p2/make_p2_cases.py --to pairact_p2_r13_detour \
  --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json --out $RUN/p2-detour-cases.json
cd $SRC/root && timeout 3h $PYW /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/p2-detour-cases.json --indices 0,1,2 --cap-s 60 --out $RUN/detour-3w --vm-hourly-usd 1.096 \
  --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
  --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
  --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
  --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
  --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json \
  --batch-per-world-speed-v1
```
- 실행 중: handover(약 23–25 SIM s) 직후 `$RUN/detour-3w/world-00k/raw/carry-route.json`이 생겨야 합니다. 로그에 `CARRY_ROUTE_PLANNED`가 찍힙니다. `plan_wall_s`, `route_plans=1`을 기록합니다.
- 판정은 `DETOUR_C3.md`와 같습니다. world 1은 `route_info.variant='detour'`이고 outcome이 `route_blocked`가 아니어야 합니다. world 11·17은 `carry.route`가 smoke-1c와 같아야 합니다.
- `summary.json`에 `runtime_pins`가 없으면 wrapper가 다른 root를 실행한 것입니다. 그 run은 무효이고 멈춥니다. `source_sha`는 ROOT_SHA와 같아야 합니다.
- 속도: `progress.json`의 `per_world_wall_SIM`, `timing`, `host_loop_s`를 보고에 그대로 붙입니다.

### 3-3. pilot seed 8343000–039 (GPU, 녹화 없음, 수율 확인)
3-2와 같은 명령에서 아래만 바꿉니다.
- `--cases`: `$RUN/p2-seed8343000-cases.json`
- `--indices`: 3-1 e의 `indices`
- `--canonical-xml`, `--per-world-model-references-v1`, `--rejection-table`: 3-1 manifest의 세 경로
- `--out`: `$RUN/pilot-8343000`
- `timeout 8h`

먼저 `--initialize-only`로 같은 명령을 돌리고 `make_seed_refs.py check-init`로 확인합니다(SEED_REFS.md f).
- 예상: world당 0.34 s/tick × 40 world면 13.6 s/tick입니다. world 상한은 170 SIM s(1700 tick)이고, 파지 실패 world는 약 60 SIM s에서 끝납니다. 그래서 2–6 h, L4 약 $1.1/h 기준 $2–7로 봅니다 [확인 필요].
- 3-2의 `per_world_wall_SIM`이 4를 넘으면 20+20 두 번으로 나눕니다. 이때 `--out`은 각각 따로 쓰고 합산하지 않습니다. 비용이 $20/런을 넘을 것으로 보이면 시작 전에 보고합니다.
- 보고 형식: world별 한 줄(seed, 파지 성공, 운반 시작, carry_success, carry_failure/교사 outcome, `route_info.variant`, 운반 SIM s). 그리고 `n/40 (수율 확인·미합산·수집 아님)`.

### 3-4. 렌더 재실행
`dsh/e2e-min-render-fix` `ddcc86f3c`의 `experiments/2026-10-21-e2e-min/RENDER_RERUN.md` 명령을 그대로 씁니다. `measure.json.scene_identity`의 `raw_identical=true`, `differing_fields=[]`를 확인합니다.

## 4. 막히면
- `RUNTIME_PIN_MISMATCH`: venv를 확인합니다(RUNBOOK_VENV.md). 다른 venv로 우회하지 않습니다.
- `MISSING_SEED_REFS` / check-init 실패: SEED_REFS.md §3 [확인 필요] 1번(P2 스택으로 다시 export)입니다. 보고합니다.
- `route_blocked_no_path`: `carry-route.json`을 첨부해 Claude에게 넘깁니다.
- HOST_ERROR는 1회만 다시 실행합니다(SMOKE.md §6).
