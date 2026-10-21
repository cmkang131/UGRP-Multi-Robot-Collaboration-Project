# pairact-r1 실행 순서 (DeepSeek용 — 수집 사전 등록 v3)

v3 변경(Codex v2 재검토 HOLD 대응, 대응표 `CODEX_RESPONSE_V3.md`): 동결이 *2-커밋(X·Y) + 2단계(FROZEN_CORE → FROZEN)*로 바뀌었습니다. pre-freeze pilot은 수율 전용(`pilot_yield_only`)이라 녹화 probe·학습 입력으로 쓸 수 없습니다. probe 대상은 FROZEN_CORE에서 새로 돌리는 *probe source* 측정 run에서 고릅니다.
전제: P1 관문(≥38/40)은 수집을 막지 않는 병행 작업입니다. 수집 시작 조건은 *P2 smoke 전 구간 성공 ≥1* 하나이고 smoke-1c(seed 8420001·8420011·8420017) 운반 성공 2/3으로 충족했습니다(증거 해시는 `RUN_MANIFEST.json` `smoke`의 VM 기입 칸).
규칙: 새 run root만 씁니다. 원본·체크포인트는 덮어쓰지 않습니다. 오프피크(UTC 16:30–00:30)에만 실행하고 끝나면 VM을 정지합니다. 브랜치는 `dsh/pairact-carry-r1-v3`입니다.

## 0. 사전 확인 (CPU, 수 분)
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py   # 103 passed 기대 (skip 0)
```
`tests/test_pairact_collect.py`의 고정 스택 admission 테스트는 -c2 세 SHA 커밋이 로컬 저장소에 있어야 합니다(없으면 fail, skip 아님).

## 1. P3 수집 — 성공 시연만 학습 (오프피크)

정본: `COLLECT_PREREG_DRAFT.json`(v3, READY_FOR_REVIEW)과 `RUN_MANIFEST.json`(schema `ugrp.pairact_r1.run_manifest.v2`, DRAFT_VM_FILL). runner `scripts/run_pairact_collect.py`, 제어 로직 `harness/pairact_collect.py`, case 생성 `collect_cases.py`, 동결 `scripts/pairact_r1_freeze.py`.

동결 단계 요약:

| 단계 | prereg·manifest status | 허용 | 원장 purpose |
|---|---|---|---|
| 리뷰 중 | READY_FOR_REVIEW / DRAFT_VM_FILL | pilot 측정 run(수율만) | `pilot_yield_only` — probe-cases·convert-input이 거부 |
| 커밋 Y | FROZEN_CORE / FROZEN_CORE | probe source 측정 run, probe-cases, probe-episode, check-rows | `probe_source` (원장 header에 core_sha256) |
| 커밋 Z | FROZEN / FROZEN | 학습 수집 run, report, convert-input | `training` (header에 FROZEN·core_sha256) |

`core_sha256` = sha256(canonical JSON {prereg에서 status 제외, manifest에서 status·recording_check 3칸 제외}) — `harness.pairact_collect.core_sha256`. 파일에는 저장하지 않고 freeze 스크립트가 출력하며 원장 header가 기록합니다. Z에서 바뀌는 것은 status와 recording_check 3칸뿐이라 core_sha256이 그대로여야 합니다(스크립트가 검사).

### 1-0. 시작 조건과 스택 pin 갱신 절차
1. *P2 smoke 전 구간 성공 ≥1*: 충족(smoke-1c 2/3). smoke 해시 4칸은 VM에서 채웁니다.
2. *스택 pin*: 수집 스택은 -c3입니다. `RUN_MANIFEST.json` `stack.{teacher,adapter,root}.sha`는 지금 `[-c3 SHA 기입]`이고, placeholder가 남으면 FROZEN_CORE·FROZEN gate가 모두 거부합니다. -c3 스택이 push되면:
   ```bash
   git ls-remote origin dsh/pairact-p2-carrypath-c3 dsh/pairact-p2-carrypath-a-c3 dsh/pairact-p2-carrypath-r-c3
   # teacher -c3에 admission 커밋(dsh/pairact-p2-carrypath-c3-admission c6626187b의 cherry-pick)이 있는지:
   git -C $SRC/teacher grep -n "COLLECT_PROBE_STATUSES" -- harness/grasp_act_admission.py     # 1줄 이상
   grep -n "^DEPENDENCY_SHA" $SRC/adapter/harness/beampair_teacher.py                          # = teacher -c3 SHA
   grep -n "noise=False" $SRC/adapter/scripts/run_beampair1.py                                 # 단일 runner.run 호출, noise off 유지
   (cd $SRC/teacher && python -m pytest -q tests/test_pairact_p3_collect_admission.py tests/test_pair_carry_teacher_warp.py)  # admission 브랜치 단독 63 passed, -c3에서는 [-c3 기대치 기입]
   (cd $SRC/adapter && python -m pytest -q tests/test_pairact_p2_adapter.py)
   (cd $SRC/root && python -m pytest -q tests/test_pairact_p2_root.py)
   ```
   세 SHA를 manifest `stack.*.sha`에 쓰고 `note`의 c2 기준과 차이를 확인합니다. 이 갱신은 커밋 Y에 들어갑니다(manifest는 collector 파일이 아니므로 X를 바꾸지 않습니다). -c3 teacher의 경로 계획 변경은 다른 워커 소관이며 여기서 검토하지 않습니다.
   - 선택: adapter -a-c3이 `PAIRACT_P3_COLLECT_PREREG_CORE_SHA256` 환경변수를 `collect_recording_admission(..., expected_core_sha256=...)`로 넘기면 teacher가 prereg core도 대조합니다. 넘기지 않아도 파일 sha256 대조는 그대로입니다.
3. *녹화 승인*(teacher -c3 `collect_recording_admission`): prereg 스키마 v2 인정, 녹화 probe는 FROZEN_CORE/FROZEN, 데이터 녹화는 FROZEN만. 640x480 녹화 동등성 check는 그대로입니다.
4. *대체 경로*: 녹화 경로가 VM에서 처음 실패하면 그 밤은 측정 run만 하고 "수율 측정, 시연 아님"으로 보고합니다.

### 1-1. 준비 (CPU, 수 분)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c3      # -c3 스택 (1-0의 세 SHA)
mkdir -p $SRC
for t in teacher:$TEACHER_C3 adapter:$ADAPTER_C3 root:$ROOT_C3; do
  git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/${t%%:*} ${t#*:}      # VM 레포 경로는 [확인 필요]
done
COL=/home/ugrp/ugrp-sim/src/pairact-r1v3      # 이 브랜치 worktree (단계마다 X → Y → Z로 갱신)
git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $COL origin/dsh/pairact-carry-r1-v3
cd $COL && python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py     # 103 passed
P=$COL/experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json
M=$COL/experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json
EP="python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py --flow beampair \
 --adapter-source $SRC/adapter --teacher-source $SRC/teacher --cases {cases} --indices {indices} --cap-s 60 --out {out} \
 --vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
 --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
 --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
 --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
 --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --batch-per-world-speed-v1"
printf %s "$EP" | sha256sum      # -> RUN_MANIFEST.json command.episode_template_sha256 ($SRC가 펼쳐진 문자열을 episode_template에)
```

### 1-2. (선택) pilot 측정 run — READY_FOR_REVIEW, 녹화 off, seed 8343000–039
```bash
RUNP=/home/ugrp/ugrp-sim/runs/pairact-p3-pilot-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNP
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 origin/claude/beampair7 \
  origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 origin/dsh/pairact-p0-diag \
  origin/dsh/act18-carry-retrain-r1 origin/dsh/pairact-p2-carrypath origin/dsh/pairact-p2-carrypath-r \
  origin/dsh/pairact-p2-carrypath-a origin/dsh/pairact-p2-carrypath-c origin/dsh/pairact-p2-carrypath-a-c \
  origin/dsh/pairact-p2-carrypath-r-c origin/dsh/pairact-p5-student > $RUNP/seed-check.json   # passed=true -> sha256을 seed_check.vm_seed_check_sha256에
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNP --mode measurement --noise off \
  --batch-size 20 --max-batches 2 --deadline-utc $DEADLINE --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
```
- 원장 purpose는 `pilot_yield_only`입니다. "수율 측정, 시연 아님"으로만 보고하며 probe·학습 입력에 쓰지 않습니다(runner가 거부).
- *중단·재시작*: 같은 명령을 다시 실행하면 `ledger.jsonl`에서 이어갑니다. 최종 summary가 있는 배치는 다시 돌리지 않고 집계만 합니다. 중간에 끊긴 배치는 남은 slot만 `try-2`로 1회 재시도하고 두 번째도 끊기면 환경 실패로 닫습니다. HOST_ERROR world는 같은 seed·구간으로 1회 재배정되고, 그 재배정 slot이 생성기에서 setup 거부되면 대기열에서 빠집니다(다시 고르지 않음).

### 1-3. 커밋 X·Y — FROZEN_CORE (Codex 재검토 통과 뒤)
1. *커밋 X*: Codex가 통과시킨 collector 코드 커밋(`COLLECTOR_FILES` + `collect_cases.py`를 마지막으로 바꾼 커밋). `X=$(git -C $COL rev-parse HEAD)`. 이후 이 파일들은 바꾸지 않습니다(바뀌면 runner가 거부).
2. VM에서 읽기 전용 명령(`RUN_MANIFEST.json` `fill_commands`)으로 VM 기입 칸을 채웁니다. 22칸 = prereg 1 + collector 1 + command 2 + assets 5 + host 5 + smoke 4 + recording_check 3 + seed_check 1이며, *이 단계에서는 recording_check 3칸을 뺀 19칸*을 채우고 stack 세 SHA도 채웁니다. 타입: sha256은 64자리 소문자 hex, 커밋은 40자리, `assets.mesh_assets_sha256`은 {절대경로: sha256}, `smoke.carry_eval_sha256`은 {world-000, world-001, world-002: sha256}. 빈 문자열·`[VM 기입]`·`[확인 필요]`·`<...>`는 gate가 거부합니다.
3. `python $COL/scripts/pairact_r1_freeze.py core --collector-sha $X --verify-assets` → prereg·manifest status FROZEN_CORE, `collector.source_sha`, `prereg.core_sha256`을 쓰고 stage core gate(스키마·타입·placeholder·prereg/limits 교차·X 조상·collector 파일 X..HEAD 불변·자산 재해시)를 통과해야 파일을 씁니다. 출력의 `core_sha256`을 `CORE`로 적어 둡니다.
4. *커밋 Y*: prereg·manifest 두 파일만 커밋하고 메시지에 `CORE`를 적습니다(Claude/Codex 확인 뒤 push). `$COL`을 Y로 갱신합니다(추적 파일이 clean해야 다음 단계가 진행됩니다).

### 1-4. FROZEN_CORE — probe source → 녹화 probe → check (GPU, 오프피크)
```bash
RUNC=/home/ugrp/ugrp-sim/runs/pairact-p3-probesrc-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNC
# ① probe source: FROZEN_CORE 측정 run (녹화 off, pilot seed, 채택 후보 3개가 나올 때까지 1–2 batch)
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNC --mode measurement --noise off \
  --batch-size 20 --max-batches 1 --deadline-utc $DEADLINE --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
# ② probe 대상: probe source 원장(purpose probe_source, header core_sha256 == 현재 core)의 첫 채택 후보 3개
python $COL/scripts/run_pairact_collect.py probe-cases --prereg $P --run-root $RUNC --run-manifest $M --out $RUNC/probe-cases.json
# ③ 녹화 probe 3 world (data_admitted=false, check 불필요; teacher가 FROZEN_CORE를 probe에만 인정)
python $COL/scripts/run_pairact_collect.py probe-episode --prereg $P --run-root $RUNC --run-manifest $M \
  --episode-cmd "$EP" --out $RUNC/probe-1
# ④ check rows(원장 core_sha256 포함) → teacher의 기존 함수로 recording check
python $COL/scripts/run_pairact_collect.py check-rows --prereg $P --run-root $RUNC --run-manifest $M --out $RUNC/check-rows.json \
  --baseline-raws <②가 출력한 baseline_raws 3개> --probe-raws $RUNC/probe-1/world-00{0,1,2}/raw
(cd $SRC/teacher && python -c "import json;from harness.grasp_act_admission import recording_mode_equivalence as f;r=json.load(open('$RUNC/check-rows.json'));print(json.dumps(f(r['baseline'],r['recorded'])))") > $RUNC/recording-check.json
```
- ①의 purpose가 `pilot_yield_only`이면(prereg가 아직 READY) ②가 거부합니다. 1-2의 pilot 원장도 ②에서 거부됩니다.
- ②–④ 중 하나라도 실패하거나 `recording-check.json`의 `qualified`가 true가 아니면 FROZEN으로 가지 않고 원인을 로그와 함께 Claude에게 넘깁니다. probe source 수율은 pilot과 합산하지 않습니다.

### 1-5. 커밋 Z — FROZEN
```bash
python $COL/scripts/pairact_r1_freeze.py final --recording-dir $RUNC --expect-core $CORE --verify-assets
```
recording_check 3칸을 `$RUNC/{probe-cases,check-rows,recording-check}.json` sha256으로 채우고 status를 FROZEN으로 바꾼 뒤 stage final gate(세 파일 해시 대조·qualified 포함)를 통과해야 씁니다. core_sha256이 `CORE`와 다르면 거부합니다. *커밋 Z*(두 파일만, 메시지에 CORE) → push → `$COL`을 Z로 갱신.

### 1-6. 학습 수집 run (FROZEN, 새 run root)
```bash
RUNT=/home/ugrp/ugrp-sim/runs/pairact-p3-train-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNT
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNT --mode training --noise off \
  --batch-size 20 --max-batches 4 --deadline-utc $DEADLINE --recording-check $RUNC/recording-check.json \
  --run-manifest $M --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
```
- runner는 시작 전에 stage final gate를 다시 돌립니다(`--recording-check`는 `$RUNC/recording-check.json`이어야 하고 옆의 두 파일도 해시 대조, 자산 재해시는 생략 불가). 원장 header에 FROZEN·core_sha256·manifest sha256이 남습니다.
- 학습 run은 train seed 8340000부터 소비합니다. pilot·probe source 수율은 따로 보고하고 합산하지 않습니다.
- world마다 sidecar 검사(두 로봇 teacher/student stream, `teacher_phase` 대응표)를 원장 기록 전에 합니다. 통과해야 채택됩니다.
- validation 20 seed는 train이 멈춘 뒤(STOP_TARGET·STOP_CAP·STOP_SEEDS·STOP_ALL_BINS_LIMITED)에 같은 명령으로 이어서 돕니다. STOP_HOST 뒤에는 호스트를 고친 것을 보고한 다음 `--validation-after-host-fix`를 붙여 다시 실행합니다.

### 1-7. 볼 것과 보고
```bash
python $COL/scripts/run_pairact_collect.py report --prereg $P --run-root $RUNT     # 같은 파일 sha256 또는 같은 내용(status 제외)이어야 함
```
- `report.json`: `purpose`·`freeze_stage`·`core_sha256`, `A.text`(그대로 인용: 물리 성공 S/시도 N, 최종 채택 A/시도 N), `A.bins`(구간별 N·S·A·성공률·need·환경 실패·생성기 거부·구간 범위 제한·운반 실패 하위 사유), `A.by_seed_phase`, `validation.text`(S/20·A/20), `ks`(세 그룹, pair 단위), `distance_gate`, `decision`, `run_state`.
- 생성기 거부 행(`setup_rejected`): 관문별 누적 통과·거부, 막은 물체 이름(정적 장애물 id·cargo id·`bounds`·`beam_1`·`peer_robot`·인증 stance 차단자), 관문별 최소 틈 또는 `not_measured`, 생성기 SHA·파일 sha256, 절대경로 재현 명령(`collect_cases.py --slot-json ... --stdout`).
- 보고 표기: n/200은 쓰지 않습니다. pilot·probe source는 "수율 측정, 시연 아님"입니다. B(교사 관문 n/40), C(학습 n/20)와 섞지 않습니다.
- 멈춤·판정(사전 등록 `stop_rules`·`training_decision`): STOP_RECORD, STOP_HOST, STOP_DISTANCE, STOP_TARGET, STOP_ALL_BINS_LIMITED, STOP_CAP(시도 600), STOP_SEEDS. 판정 4단계: TRAIN / TRAIN_DATA_RANGE_LIMITED / TRAIN_SMALL_DATA(80≤A<150) / NO_TRAIN_BELOW_FLOOR(A<80) 및 NO_TRAIN_DISTANCE_GATE / NO_TRAIN_VALIDATION_INSUFFICIENT / NO_TRAIN_RECORD_ERROR. MAX_BATCHES·DEADLINE은 다음 밤 같은 명령으로 이어갑니다.
- DART 노이즈는 기본 off입니다.

### 1-8. 변환 입력 (판정 TRAIN·TRAIN_DATA_RANGE_LIMITED·TRAIN_SMALL_DATA, validation 끝난 뒤)
```bash
python $COL/scripts/run_pairact_collect.py convert-input --prereg $P --run-root $RUNT --run-manifest $M \
  --recording-check $RUNC/recording-check.json --teacher-sha $TEACHER_C3 --out $RUNT/convert-input
# -> seed-<seed>/{SOURCE_SHA,EXIT,raw -> 원본 world raw symlink} + protocol.json(core_sha256, decision, data_range_limited, small_data, result_labels)
```
FROZEN 학습 원장이 아니거나(pilot·probe source 포함) core_sha256이 다르거나 판정이 학습 불가면 runner가 거부합니다. [확인 필요] world result.json의 `source_sha`가 teacher -c3 SHA인지 첫 배치에서 확인합니다.

## 2. 변환 + stage sidecar (CPU)
```
# protocol: train_seeds=성공 train seed, validation_seeds=성공 validation seed (heldout 금지)
python -c "from harness.grasp_act_data import convert; import json; convert('$RUNT/convert-input', json.load(open('$RUNT/convert-input/protocol.json')), 'datasets/pairact-r1-<TS>')"
python scripts/build_pairact_r1_stage_targets.py --dataset datasets/pairact-r1-<TS> --output datasets/pairact-r1-<TS>-stage
```
`missing_stages`에 approach·alignment·ready·execute·carry·place·complete 중 하나라도 있으면 멈추고 보고합니다. recover는 teacher 시연에 없을 수 있습니다.

## 3. P4 학습 (gcp2 L4, 학습 4.6 GPU-h 예산)
```
CFG=experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json
ST=datasets/pairact-r1-<TS>-stage/stage-targets.json
COMMON="--dataset datasets/pairact-r1-<TS> --seed 20261020 --beamact3-v1 A --done-loss balanced_bce_v1 \
  --execution-host-profile beamact1_gcp2 --pairact-r1-config $CFG --pairact-r1-stage-targets $ST"
# smoke
python scripts/train_grasp_act.py $COMMON --output runs/pairact-carry-r1-<TS>/smoke --stage smoke --steps 300 --max-wall-s 1800
# approval.json: approved=true, stage=main, source_sha, dataset_manifest_sha256, smoke_summary_sha256,
#   steps=20000, blank_images=false, gate_promotion_authorized_if_all_conditions_pass=false, beamact3_v1="A",
#   pairact_r1_config_sha256, pairact_r1_stage_targets_sha256  (Claude 본체 승인 후 작성)
python scripts/train_grasp_act.py $COMMON --output runs/pairact-carry-r1-<TS>/main --stage main --steps 20000 \
  --checkpoint-every 1000 --max-wall-s 25200 --smoke-summary runs/pairact-carry-r1-<TS>/smoke/summary.json \
  --approval runs/pairact-carry-r1-<TS>/approval.json --profile-timing
# WALL_CAP이면: 같은 명령에 --resume runs/pairact-carry-r1-<TS>/main/step-<마지막>
```
`--profile-timing`으로 step 시간 실측을 남깁니다. GPU-h 실측은 STATUS에 적습니다.

## 4. 오프라인 gate + 선택 (gcp2, 0.5–1.5 GPU-h [확인 필요])
```
python scripts/pairact_r1_offline.py --run runs/pairact-carry-r1-<TS>/main --dataset datasets/pairact-r1-<TS> \
  --stage-targets $ST --output runs/pairact-carry-r1-<TS>/offline
```
`selection.json`의 verdict가 `NOT_READY_NO_CHECKPOINT_PASSES`이면 P5를 돌리지 않고 보고합니다.

## 5. P5 (보류 20 seed, 학생·teacher 같은 seed)
`PAIRACT_R1_EVAL_PREREG_DRAFT.json`의 [확인 필요] 항목(에피소드 cap)을 채워 커밋한 뒤에 실행합니다. 체크포인트 SHA를 커밋한 뒤 보류 20 seed에 규칙 A 정적 검사를 적용하고, 제외 seed 목록을 커밋한 다음에만 rollout합니다(제외 seed는 분모에서 빼고 대체하지 않음). 그 전에는 heldout 결과를 만들거나 읽지 않습니다. 평가 runner는 P2 evaluator와 PairActBarrier 연결이 필요하고, 아직 구현되지 않았습니다(남은 일).
