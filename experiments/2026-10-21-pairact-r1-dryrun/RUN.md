# pairact-r1 학생 학습 파이프라인 dry-run (합성 녹화, gcp2 L4)

> **라벨: `SYNTHETIC_DRYRUN — 수집 데이터 아님 · 판정 아님 · teacher 시연 아님`**
>
> - 학습 데이터: *합성*. 시뮬레이터·teacher가 만든 녹화가 아닙니다(`scripts/pairact_r1_dryrun_synth.py`가 만든 단색+노이즈 JPEG와 규칙으로 정한 명령).
> - 정책 구분: 학습되는 것은 learned policy(학생 ACT)지만 합성 데이터 300 step smoke라서 **성능 의미가 없습니다**. teacher 결과가 아닙니다.
> - P5 결과: **dry-run 배관 확인, 판정 아님, 학습 데이터 합성**. 성공/실패 수를 어떤 표·n/20·n/40과도 합산하지 않고, 학생 성공률로 인용하지 않습니다.

목적은 하나입니다. 녹화(raw) → `convert` → stage sidecar → `train_grasp_act.py` pairact-r1 smoke 300 step → 체크포인트 저장·재로딩(`torch.equal`) → P5 `--student-eval` 1 world까지 *배관이 끝까지 도는지*만 확인합니다.

## 0. 브랜치·SHA

| tree | 브랜치 / SHA | 용도 |
|---|---|---|
| dry-run (`$DRY`) | `dsh/pairact-r1-dryrun` (base `origin/dsh/pairact-p5-student` `3c9337d5f`) — 실행 전 `git -C $DRY rev-parse HEAD`를 기록 | 합성 생성·convert·sidecar·학습·reload 검사 |
| 학생 worker (`$STU`) | `3c9337d5f5c9deefd49139b26ae7117022e3d5cc` (detached) | P5 worker `source`. root `-r-c5`의 `STUDENT_SHA`가 이 값이고 `source` HEAD가 다르면 시작을 거부합니다 |
| teacher | `dsh/pairact-p2-carrypath-c5` `75929e7719ad98a089e3dda5251f4249d8bae511` | P5 runner(`scripts/run_grasp_act_teacher.py`, `harness/pairact_student_eval.py`) |
| adapter | `dsh/pairact-p2-carrypath-a-c5` `3779d9615ef6dc8e38f57ab968a14a9e45189ecc` | |
| root | `dsh/pairact-p2-carrypath-r-c5` `a93082c343ef5f3687851bf4b0c9fb0f2484ada1` | `scripts/run_warp_flow_teacher.py --student-eval` |

학생 worker를 이 브랜치 worktree로 띄우면 안 되는 이유: root `load_student_eval`이 `git -C source rev-parse HEAD == STUDENT_SHA(3c9337d5f)`를 요구합니다. 이 브랜치는 그 위에 커밋이 있어서 HEAD가 다릅니다. 대신 이 브랜치는 worker가 읽는 파일(`harness/` 전체, `scripts/pairact_r1_student_worker.py`, `scripts/train_grasp_act.py`, 학습 config)을 바꾸지 않습니다. 그래서 여기서 학습한 체크포인트의 `adapter.json` 해시(`pairact_source_sha256`·`adapter_source_sha256`·`contract_sha256`)가 `$STU`의 `PairActActor.load` 검사와 맞습니다. 테스트 `test_worker_tree_files_identical_to_pinned_student_sha`가 이를 고정하고, 1단계에서 VM에서도 다시 확인합니다.

## 1. 사전 등록 동결이 필요 없는 이유

- 데이터가 합성입니다. teacher 녹화가 아니어서 teacher 녹화 승인(FROZEN prereg)의 대상이 아닙니다. 합성 생성기는 teacher·시뮬레이터를 import하지 않습니다.
- 판정이 없습니다. 오프라인 gate, 체크포인트 선택, P5 성공률 중 어느 것도 이 실행으로 정하지 않습니다.
- 학습 seed(8340000–8340199, 확장 8340200–8340599), validation(8341000–8341019), 보류(8342000–8342019), pilot(8343000–8343039)을 하나도 쓰지 않습니다. 보류 seed는 읽지도 만들지도 않습니다.

## 2. seed 겹침 확인

| 용도 | seed | 결과 |
|---|---|---|
| 합성 train | 9990001 | `seeds.json`(이 브랜치, v3-shard의 `train_extension`·`pilot` 포함) 모든 범위와 겹치지 않음. 생성기가 실행할 때마다 다시 검사합니다(`seed_overlap`, 겹치면 거부) |
| 합성 validation | 9990002 | 위와 같음 |
| P5 1 world | 8420001 (P2 smoke-1c world 1, r13 case 1) | train·validation·heldout·pilot과 겹치지 않음. `known_ranges`의 beamact5 wide gate40(8420000–8420039)에 들어 있는데, 이것은 이미 실행된 P2 smoke world라서 예상된 결과입니다(테스트 `test_synthetic_seeds_do_not_overlap_registered_ranges`) |

`git grep -I -E '\b999000[0-9]\b'`(`*.py`·`*.json`·`*.md`)를 origin의 pairact ref 47개와 `origin/main`에 돌린 결과, 이 dry-run 브랜치 밖에서는 일치가 0건이었습니다(2026-10-21). 나머지 origin ref(전체 416개)는 시간 문제로 스캔하지 못했습니다 [확인 필요].

## 3. 경로 (VM)

```bash
TS=$(date -u +%Y%m%dT%H%MZ)
VMREPO=/home/ugrp/ugrp-sim/ugrp                          # VM 레포 경로 [확인 필요]
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c5                 # -c5 스택 (RUNBOOK 1-1 형식) [확인 필요: gcp2에 있는지]
DRY=/home/ugrp/ugrp-sim/src/pairact-r1-dryrun            # 이 브랜치
STU=/home/ugrp/ugrp-sim/src/pairact-p5/student           # 3c9337d5f detached
RUN=/home/ugrp/ugrp-sim/runs/pairact-r1-dryrun-$TS       # 새 run root (git tree 밖)
ACTPY=/home/ugrp/<act-venv>/bin/python                   # torch·lerobot ACT venv [확인 필요: gcp2 경로]
PYW=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python       # MJWarp venv (C4_RUN.md) [확인 필요: gcp2]
CFG=$DRY/experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json
```

`RUN`을 레포 checkout 밖에 둡니다. `train_grasp_act.py`의 `source_sha()`는 `git status --porcelain`이 비어 있지 않으면 거부하는데, `runs/`·`datasets/`는 `.gitignore`에 없습니다.

## 4. 순서

### 4-0. 준비 (CPU, 약 5–10분)
```bash
git -C $VMREPO fetch -q origin
mkdir -p $SRC $(dirname $STU)
git -C $VMREPO worktree add --detach $DRY origin/dsh/pairact-r1-dryrun
git -C $VMREPO worktree add --detach $STU 3c9337d5f5c9deefd49139b26ae7117022e3d5cc
for t in teacher:75929e7719ad98a089e3dda5251f4249d8bae511 adapter:3779d9615ef6dc8e38f57ab968a14a9e45189ecc root:a93082c343ef5f3687851bf4b0c9fb0f2484ada1; do
  [ -d $SRC/${t%%:*} ] || git -C $VMREPO worktree add --detach $SRC/${t%%:*} ${t#*:}
  test "$(git -C $SRC/${t%%:*} rev-parse HEAD)" = "${t#*:}" || echo "STACK_MISMATCH ${t%%:*}"
done
git -C $DRY rev-parse HEAD                                   # DRY_SHA 기록
git -C $DRY diff --quiet 3c9337d5f5c9deefd49139b26ae7117022e3d5cc HEAD -- harness scripts/pairact_r1_student_worker.py \
  scripts/train_grasp_act.py experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json && echo WORKER_FILES_SAME
cd $DRY && $ACTPY -m pytest -q tests/test_pairact_r1_dryrun.py          # 기대: 8 passed
cd $STU && $ACTPY -c "import scripts.pairact_r1_student_worker, harness.pairact_r1_student; print('worker import ok')"
mkdir -p $RUN
```

### 4-1. 합성 녹화 생성 (CPU, 수 초)
```bash
cd $DRY && $ACTPY scripts/pairact_r1_dryrun_synth.py --out $RUN/convert-input
```
- 출력: `seed-9990001/`·`seed-9990002/` 각각 `{SOURCE_SHA, EXIT, SYNTHETIC.json, raw/{plan.json, result.json, student-camera.json, student-r1.jsonl, teacher-r1.jsonl, student-r2.jsonl, teacher-r2.jsonl, rgb/r?/*.jpg}}`, `protocol.json`, `SYNTHETIC_MANIFEST.json`.
- 로봇당 66행(grasp 38 + release 28), 640x480 JPEG 264장. teacher phase 19구간으로 8단계를 모두 덮습니다(recover = `relook`).
- `SOURCE_SHA`·`teacher_sha` = `SYNTHETIC-DRYRUN-not-a-teacher-sha`. convert는 문자열이 같은지만 봅니다.
- 같은 seed면 바이트까지 같은 출력이 나옵니다(테스트 `test_deterministic`). `SYNTHETIC_MANIFEST.json`의 `files`(sha256)를 기록합니다.

### 4-2. convert (CPU, 수 초)
```bash
cd $DRY && $ACTPY -c "from harness.grasp_act_data import convert; import json; \
convert('$RUN/convert-input', json.load(open('$RUN/convert-input/protocol.json')), '$RUN/dataset')"
```
기대: `$RUN/dataset/manifest.json`이 `status=complete`이고 episode 4개(9990001-r1/r2 train, 9990002-r1/r2 validation)이며 `missing_done_skills=[]`입니다. manifest의 `protocol`에 라벨과 `synthetic: true`가 그대로 들어갑니다.

### 4-3. stage sidecar + 데이터 확인 (CPU, 수 초)
```bash
cd $DRY && $ACTPY scripts/build_pairact_r1_stage_targets.py --dataset $RUN/dataset --output $RUN/stage
cd $DRY && $ACTPY scripts/pairact_r1_dryrun_check.py verify-data --dataset $RUN/dataset \
  --stage-targets $RUN/stage/stage-targets.json --out $RUN/check-data.json
```
기대: `missing_stages: []`이고 h0 stage 수(로컬 실측)가 approach 32, alignment 32, recover 12, ready 24, execute 52, carry 60, place 36, complete 16입니다. `check-data.json`이 `passed: true`여야 합니다.

### 4-4. 학습 smoke 300 step (GPU, gcp2 `ugrp-act-l4-gcp2`)
```bash
cd $DRY && $ACTPY scripts/train_grasp_act.py --dataset $RUN/dataset --output $RUN/smoke \
  --stage smoke --steps 300 --max-wall-s 1800 --run-class dev --profile-timing \
  --seed 20261020 --beamact3-v1 A --done-loss balanced_bce_v1 --execution-host-profile beamact1_gcp2 \
  --pairact-r1-config $CFG --pairact-r1-stage-targets $RUN/stage/stage-targets.json
echo "train exit=$?"
```
- `require_gcp2(training=True)`는 instance `ugrp-act-l4-gcp2` / `g2-standard-8` / project `ugrp-sim-b-1014`를 요구합니다.
- smoke 체크포인트는 100 step마다 저장됩니다(`step-000100/200/300`, `actor/` + `optimizer.pt` + `resume.json`). 학습기 자체가 마지막 체크포인트를 다시 읽어 in-memory 정책과 `torch.equal`인지 확인하고, 결과를 `summary.json`의 `readback_verified`에 남깁니다.
- `--run-class dev`이므로 `research_result: false`입니다. main 학습·approval은 만들지 않습니다.

### 4-5. 재로딩 `torch.equal` (GPU, 수 분)
```bash
cd $DRY && $ACTPY scripts/pairact_r1_dryrun_check.py reload --run $RUN/smoke --dataset $RUN/dataset \
  --stage-targets $RUN/stage/stage-targets.json --device cuda --out $RUN/check-reload.json
echo "reload exit=$?"
```
- 기존 `harness.pairact_r1.PairActActor.load`로 `step-000300/actor`를 독립적으로 두 번 불러, 고정 입력 두 개에서 출력이 같은지 봅니다. 새 로더는 없습니다.
  - 텐서 입력: `PairActDataset(validation, 증강 없음)[0]`에 beamact3 arm A 변환을 한 것. 학습기 readback과 같은 `predict_action_chunk`를 씁니다.
  - raw 입력: 합성 validation seed r1의 40번째 관측 행과 그 행의 자기 JPEG 4장. P5 worker와 같은 `predict_staged` 경로입니다.
- 비교 항목: `action_chunk`, `done_logit`, `stage_logits`, `staged_chunk`, `staged_stage_logits`. 모두 `torch_equal: true`이고 `trainer_readback_verified: true`여야 합니다.

### 4-6. P5 `--student-eval` 1 world (GPU, MJWarp)
```bash
# 학생 config (키 6개 정확히. 라벨은 student-eval.LABEL.json에 따로 들어감)
cd $DRY && $ACTPY scripts/pairact_r1_dryrun_check.py student-eval-config --python $ACTPY --source $STU \
  --model $RUN/smoke/step-000300/actor --config $STU/experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json \
  --device cuda --out $RUN/student-eval.json
# worker 단독 기동 확인: 모델을 읽고 ready 한 줄을 출력한 뒤 EOF에서 끝나야 함
cd $STU && $ACTPY -m scripts.pairact_r1_student_worker --model $RUN/smoke/step-000300/actor \
  --config $STU/experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json --device cuda < /dev/null
#   기대 출력: {"ready": true, "mode": "pairact_r1_student_eval_v1"}
# cases: P2 smoke와 같은 r13 world 1·11·17 → index 0 = world 1 = seed 8420001
cd $SRC/root && $PYW experiments/2026-10-21-pairact-p2/make_p2_cases.py \
  --r13-cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json --out $RUN/p5-cases.json
$PYW -c "import json; c=json.load(open('$RUN/p5-cases.json')); s=c[0]['plan']['seed']; print(s); assert s==8420001"
cd $SRC/root && timeout 1h $PYW /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py \
  --flow beampair --adapter-source $SRC/adapter --teacher-source $SRC/teacher \
  --cases $RUN/p5-cases.json --indices 0 --cap-s 60 --out $RUN/p5-student --vm-hourly-usd 1.096 \
  --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
  --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
  --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
  --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
  --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --batch-per-world-speed-v1 \
  --student-eval $RUN/student-eval.json
echo "p5 exit=$?"
cd $DRY && $ACTPY scripts/pairact_r1_dryrun_check.py p5-report --p5-out $RUN/p5-student --out $RUN/check-p5.json
```
- 플래그는 SMOKE.md §3 / C4_RUN.md §3-2와 같고 `--indices 0`과 `--student-eval`만 다릅니다. 후보는 `make_p2_cases.py` 기본값(`pairact_p2_r13`)입니다. world 1은 smoke-1c에서 teacher 운반 경로가 막혔던 world(root `DETOUR_C3.md`)지만, 학생 평가에서는 teacher가 운반하지 않습니다. 이 dry-run은 배관만 보므로 후보 선택은 결과 해석에 영향이 없습니다.
- 모델 경로는 `.../step-000300/actor`입니다. `PairActActor.load`가 `SHA256.json`을 `actor/` 안에서 읽습니다. P5_STUDENT_EVAL.md 예시의 `main/step-<선택>`에는 `/actor`가 빠져 있습니다.
- 학생은 합성 데이터만 봤기 때문에 실제 카메라에서 의미 있는 행동을 기대하지 않습니다. 대부분 접근 단계에서 cap(60 + carry 110 SIM s)까지 갈 것으로 보이며, 이것은 정상입니다.
- `timeout 1h`는 비용 상한용입니다. timeout으로 끝나면 실패로 보고합니다.

## 5. 성공 기준 (모두 만족해야 "배관 통과". 판정 아님)

1. 4-0 ~ 4-6 각 명령의 exit 0. `STACK_MISMATCH`가 없고 `WORKER_FILES_SAME`이 출력돼야 합니다.
2. `check-data.json` `passed: true` (`missing_stages: []`).
3. `$RUN/smoke/summary.json`: `status: complete`, `steps_completed: 300`, `readback_verified: true`.
4. `check-reload.json`: `torch_equal: true`(5개 출력 모두).
5. `$RUN/p5-student/summary.json`: `HOST_ERROR: 0`, `student_eval` 존재, `source_sha == a93082c3…`, `worlds[0].teacher_steps == 0`.
6. `world-000/raw/result.json`(또는 `.zst`) `student_eval`: `funnel` 존재, `teacher_steps == 0`, `gt_inputs_to_student == 0`, `student_execution: true`. 이 항목은 `check-p5.json` `passed: true`로 한 번에 확인합니다.

`worlds[0].success`·`carry_success`·`funnel.reached`는 기록만 하고 판정이나 성공률로 쓰지 않습니다(`check-p5.json`에서는 `*_not_a_judgement` 키로 들어갑니다).

## 6. 예상 GPU 시간·비용 (gcp2 L4, $1.096/h. 청구 단가는 미확인)

| 단계 | 예상 wall | 근거 |
|---|---|---|
| 4-0 ~ 4-3 준비·합성·convert·sidecar | 약 0.1 h | VM이 켜진 동안 과금. 합성·convert·sidecar는 로컬 실측 각 수 초 |
| 4-4 smoke 300 step | 약 0.05–0.1 h | 132 train 행, batch 8. step 시간은 `--profile-timing`으로 실측 [확인 필요] |
| 4-5 reload | < 0.05 h | 모델 2회 로드 + forward 4회 |
| 4-6 P5 1 world | 약 0.2–0.4 h | 최대 170 SIM s = 1700 tick × world당 0.34–0.42 s/tick(C4_RUN.md) ≈ 10–12분 + 학생 worker 추론(로봇 2대/tick) + Warp 초기화 [확인 필요] |
| **합계** | **약 0.35–0.65 h ≈ $0.4–0.7** | 요청에 적힌 ≤0.5 h보다 P5 world가 cap까지 가면 조금 길 수 있습니다. 상한은 1 h(≈$1.1)이고 런당 $20보다 훨씬 낮습니다 |

끝나면 VM을 정지합니다. 실측 wall은 `smoke/summary.json`의 `wall_s`, `p5-student/summary.json`, `progress.json`에서 읽어 보고합니다.

## 7. 실패 시 보고 항목

- 실패한 단계 번호, 명령 전문, exit code, stderr 마지막 50줄.
- `DRY_SHA`, 세 -c5 SHA의 실제 `rev-parse` 값, `$STU` HEAD, `WORKER_FILES_SAME` 출력 여부.
- 4-1 ~ 4-3: `SYNTHETIC_MANIFEST.json` sha256, `dataset/manifest.json`의 `status`·`error_type`, `stage-targets.json`의 `missing_stages`.
- 4-4: `smoke/summary.json` 전체(`status`, `error_type`, `steps_completed`, `readback_verified`, `host`, `timing.step_mean_s`), `progress.jsonl` 마지막 줄.
- 4-5: `check-reload.json` 전체. `torch_equal: false`이면 어느 출력이 다른지.
- 4-6: worker 기동 출력(`student worker startup mismatch`·SHA 불일치 메시지), `p5-student/summary.json`의 `status`·`HOST_ERROR`·`error`·`traceback` 끝부분, `check-p5.json`.
- HOST_ERROR는 같은 명령으로 1회만 다시 실행합니다(새 `--out`). 두 번째도 실패하면 멈추고 보고합니다.

## 8. [확인 필요]

- VM 경로: `$VMREPO`, `$ACTPY`(gcp2의 ACT venv), `$PYW`(gcp2에 `.venv-warp`가 있는지), `$SRC`(gcp2에 -c5 스택이 있는지).
- `beamact5-tools/run_warp_flow_teacher_gcp6.py` wrapper와 `--gcp6-isolated-v1`이 gcp2(`ugrp-act-l4-gcp2`)에서 받아들여지는지. RUNBOOK 1-6b는 gcp2에서도 같은 `$EP`를 쓴다고 적었지만 wrapper 내용은 레포에 없습니다. 안 되면 4-6만 gcp6에서 실행하고(`$RUN/smoke/step-000300/actor`를 같은 절대경로로 복사), 그 사실을 보고합니다.
- canonical XML·native refs·rejection table(`/home/ugrp/ugrp-sim/runs/beamact5/...`)이 gcp2에 있는지.
- smoke step 시간, P5 1 world의 Warp 초기화 시간과 학생 worker의 tick당 비용(실측으로 갱신).
