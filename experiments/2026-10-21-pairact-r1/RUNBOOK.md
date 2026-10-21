# pairact-r1 실행 순서 (DeepSeek용, 초안 — 수집 사전 등록 v2)

전제(2026-10-21 v2): P1 관문(≥38/40)은 수집을 막지 않는 병행 작업입니다. 수집 시작 조건은 *P2 smoke 전 구간 성공 ≥1* 하나이고, smoke-1c(seed 8420001·8420011·8420017)에서 운반 성공 2/3으로 충족했습니다. 증거 해시는 `RUN_MANIFEST.json` `smoke`에 [VM 기입]으로 남아 있습니다.
규칙: 새 run root만 씁니다. 원본·체크포인트는 덮어쓰지 않습니다. 오프피크(UTC 16:30–00:30)에만 실행하고, 끝나면 VM을 정지합니다. 브랜치는 `dsh/pairact-carry-r1-v2`입니다.

## 0. 사전 확인 (CPU, 수 분)
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py   # 67 passed 기대
```

## 1. P3 수집 — 성공 시연만 학습 (오프피크)

정본: `COLLECT_PREREG_DRAFT.json`(v2, 현재 READY_FOR_REVIEW, Codex 재검토 뒤 FROZEN)과 `RUN_MANIFEST.json`(같이 동결). 대응표: `CODEX_RESPONSE_V2.md`.
runner: `scripts/run_pairact_collect.py`(제어 로직 `harness/pairact_collect.py`, case 생성 `collect_cases.py`).
수집 스택은 *-c2 스택*입니다: teacher `dsh/pairact-p2-carrypath-c2` `4b080d35`, adapter `dsh/pairact-p2-carrypath-a-c2` `aaabddb1`, root `dsh/pairact-p2-carrypath-r-c2` `612ef643`. -c 스택(`d128984d`)은 adapter `run()`의 `runner.run` 2회 호출 때문에 root bridge가 VM 진입 전에 거부하므로 쓰지 않습니다(Codex 후속 감사, -c2에서 수정·테스트).

### 1-0. 시작 조건 (모두 만족해야 시작)
1. *P2 smoke 전 구간 성공 ≥1*: 충족(smoke-1c 2/3). DeepSeek이 `RUN_MANIFEST.json` `smoke.*_sha256`을 채웁니다(VM 읽기 전용).
2. *pilot 측정 run*은 `READY_FOR_REVIEW`에서도 됩니다. *학습 run*은 사전 등록과 manifest가 둘 다 `FROZEN`이고 manifest에 [VM 기입]이 하나도 없어야 합니다(runner가 거부).
3. *녹화 승인*: -c2 후보 `pairact_p3_collect`는 ≥38/40 관문 요구 대신 FROZEN 사전 등록 sha256 일치를 요구하고, 640x480 녹화 동등성 check는 그대로 요구합니다.
4. *대체 경로*: 녹화 경로가 VM에서 처음 실패하면 그 밤은 pilot 측정 run만 하고 "수율 측정, 시연 아님"으로 보고합니다.

### 1-1. 준비 (CPU, 수 분)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p3c2      # -c2 스택
mkdir -p $SRC
for t in teacher:4b080d35a3dcbbd8fb8a992e1f1106a7289757b2 adapter:aaabddb1725191ebaa11f0849bf6446f612e150b root:612ef6437d1eab4ad98a3fa8ee331760c4dc5595; do
  git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $SRC/${t%%:*} ${t#*:}      # 레포 경로는 [확인 필요]
done
(cd $SRC/teacher && python -m pytest -q tests/test_pairact_p3_collect_admission.py tests/test_pair_carry_teacher_warp.py)  # 기대: 60 passed (고정 SHA 0c22a2826 필요, 없으면 fail)
(cd $SRC/adapter && python -m pytest -q tests/test_pairact_p2_adapter.py)            # 기대: 7 passed
(cd $SRC/root && python -m pytest -q tests/test_pairact_p2_root.py)                  # 기대: 10 passed (고정 adapter run() bridge 변환 runner_call=1)
COL=/home/ugrp/ugrp-sim/src/pairact-r1v2      # 이 브랜치(dsh/pairact-carry-r1-v2) worktree, FROZEN 커밋
git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $COL origin/dsh/pairact-carry-r1-v2   # 레포 경로는 [확인 필요]
cd $COL && python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py     # 기대: 67 passed
P=$COL/experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json
M=$COL/experiments/2026-10-21-pairact-r1/RUN_MANIFEST.json
RUNP=/home/ugrp/ugrp-sim/runs/pairact-p3-pilot-$(date -u +%Y%m%dT%H%M)                  # 새 run root만
mkdir -p $RUNP
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 origin/claude/beampair7 \
  origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 origin/dsh/pairact-p0-diag \
  origin/dsh/act18-carry-retrain-r1 origin/dsh/pairact-p2-carrypath origin/dsh/pairact-p2-carrypath-r \
  origin/dsh/pairact-p2-carrypath-a origin/dsh/pairact-p2-carrypath-c origin/dsh/pairact-p2-carrypath-a-c \
  origin/dsh/pairact-p2-carrypath-r-c origin/dsh/pairact-p5-student > $RUNP/seed-check.json   # passed=true 필요 (2026-10-21 로컬: true, pilot 포함)
sha256sum $P $M | tee $RUNP/PREREG_MANIFEST_SHA256
```
manifest의 [VM 기입] 채우기: `RUN_MANIFEST.json` `fill_commands` 순서대로 읽기 전용 명령만 씁니다. 채운 값은 동결 커밋에 넣습니다(Claude/Codex 확인 뒤).

### 1-2a. pilot 측정 run (GPU, 오프피크, 녹화 off, seed 8343000–039)
episode 명령은 SMOKE.md §3 플래그 그대로에서 `--cases/--indices/--out`만 runner가 채웁니다. `--rejection-table`은 절대경로, `--cap-s`는 명시해야 합니다(runner가 검사하고 원장 header에 sha256을 남깁니다).
```bash
cd $SRC/root
EP="python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py --flow beampair \
 --adapter-source $SRC/adapter --teacher-source $SRC/teacher --cases {cases} --indices {indices} --cap-s 60 --out {out} \
 --vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
 --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
 --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
 --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
 --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --batch-per-world-speed-v1"
printf %s "$EP" | sha256sum      # -> RUN_MANIFEST.json command.episode_template_sha256
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNP --mode measurement --noise off \
  --batch-size 20 --max-batches 4 --deadline-utc <오늘 날짜>T00:00Z --run-manifest $M \
  --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
```
- pilot 40 seed만 씁니다(구간 = (seed−8343000) % 6, 적응형 배정 없음). *validation과 heldout은 측정 run에서 절대 돌리지 않습니다.* 끝나면 `PILOT_DONE`.
- *중단·재시작*: 같은 명령을 다시 실행하면 `ledger.jsonl`에서 이어갑니다. cases 생성 중 끊기면 아무것도 남지 않고, `batch_planned` 뒤에 끊기면 cases를 다시 만들어 원장의 sha256과 대조합니다. 최종 summary가 있는 배치는 다시 돌리지 않고 집계만 합니다. 중간에 끊긴 배치는 남은 slot만 `try-2`로 1회 재시도하고, 두 번째도 끊기면 그 slot은 환경 실패로 닫습니다. HOST_ERROR world는 같은 seed·구간으로 1회 재배정됩니다.
- 원본 보존: 모든 배치 출력은 `$RUNP/batches/bXXX/try-N/`에 남고, 실패도 지우지 않습니다.

### 1-2b. 녹화 동등성 check → 학습 run (사전 등록·manifest FROZEN 뒤)
pilot run과 학습 run은 *다른 run root*입니다. 학습 run은 train seed 8340000부터 소비하고, pilot의 수율은 따로 보고하며 합산하지 않습니다.
```bash
# ① probe 대상: pilot run의 첫 채택 후보 3개(같은 case 바이트, 후보만 pairact_p3_collect)
python $COL/scripts/run_pairact_collect.py probe-cases --prereg $P --run-root $RUNP --out $RUNP/probe-cases.json
# ② 녹화 probe 3 world (data_admitted=false, check 불필요)
PAIRACT_P3_COLLECT_PREREG=$P PAIRACT_P3_COLLECT_PREREG_SHA256=$(sha256sum $P | cut -d' ' -f1) PAIRACT_P3_RECORDING_PROBE=1 \
  bash -c "$(echo "$EP" | sed "s#{cases}#$RUNP/probe-cases.json#; s#{indices}#0,1,2#; s#{out}#$RUNP/probe-1#")"
# ③ check rows → teacher의 기존 함수로 check 생성 (규칙 변경 없음)
python $COL/scripts/run_pairact_collect.py check-rows --prereg $P --run-root $RUNP --out $RUNP/check-rows.json \
  --baseline-raws <①이 출력한 baseline_raws 3개> --probe-raws $RUNP/probe-1/world-00{0,1,2}/raw
(cd $SRC/teacher && python -c "import json;from harness.grasp_act_admission import recording_mode_equivalence as f;r=json.load(open('$RUNP/check-rows.json'));print(json.dumps(f(r['baseline'],r['recorded'])))") > $RUNP/recording-check.json
# ④ 학습 run (새 run root, FROZEN 사전 등록 + FROZEN manifest)
RUNT=/home/ugrp/ugrp-sim/runs/pairact-p3-train-$(date -u +%Y%m%dT%H%M); mkdir -p $RUNT
python $COL/scripts/run_pairact_collect.py collect --prereg $P --run-root $RUNT --mode training --noise off \
  --batch-size 20 --max-batches 4 --deadline-utc <날짜>T00:00Z --recording-check $RUNP/recording-check.json \
  --run-manifest $M --dependency-root $SRC/teacher --frozen-root $SRC/root --adapter-root $SRC/adapter --episode-cmd "$EP"
```
- ②나 ③이 실패하면 학습 run을 시작하지 않고 원인을 로그와 함께 Claude에게 넘깁니다.
- 학습 run에서 world마다 sidecar 검사(두 로봇 teacher/student stream, `teacher_phase` 대응표)를 원장 기록 전에 합니다. 통과해야 채택됩니다.
- validation 20 seed는 train이 멈춘 뒤(STOP_TARGET·STOP_CAP·STOP_SEEDS·STOP_ALL_BINS_LIMITED)에 같은 명령으로 이어서 돕니다. STOP_HOST 뒤에는 호스트를 고친 것을 보고한 다음 `--validation-after-host-fix`를 붙여 다시 실행합니다.

### 1-3. 볼 것과 보고
```bash
python $COL/scripts/run_pairact_collect.py report --prereg $P --run-root $RUNT     # 원장 header의 사전 등록 sha256이 다르면 거부
```
- `report.json`: `A.text`(그대로 인용: 물리 성공 S/시도 N, 최종 채택 A/시도 N), `A.bins`(구간별 N·S·A·성공률·need·환경 실패·생성기 거부·구간 범위 제한·운반 실패 하위 사유), `A.by_seed_phase`(확장 전후), `validation.text`(S/20·A/20), `ks`(세 그룹, pair 단위), `distance_gate`, `decision`, `run_state`.
- 보고 표기: n/200은 쓰지 않습니다. 200은 채택 목표입니다. pilot은 "수율 측정, 시연 아님"입니다. B(교사 관문 n/40), C(학습 n/20)와 섞지 않습니다.
- 멈춤·판정(사전 등록 `stop_rules`·`training_decision`): STOP_RECORD(필수 필드 누락 → 새 run root), STOP_HOST(batch 2개 연속 비정상), STOP_DISTANCE, STOP_TARGET(채택 200 ∧ 구간마다 ≥20 또는 구간 범위 제한), STOP_ALL_BINS_LIMITED, STOP_CAP(시도 600), STOP_SEEDS(seed 소진, 환경 실패로 시도 <600일 수 있음). 판정: TRAIN / TRAIN_DATA_RANGE_LIMITED / NO_TRAIN_BELOW_MINIMUM / NO_TRAIN_DISTANCE_GATE / NO_TRAIN_VALIDATION_INSUFFICIENT / NO_TRAIN_RECORD_ERROR. MAX_BATCHES·DEADLINE은 다음 밤 같은 명령으로 이어갑니다.
- DART 노이즈는 기본 off입니다.

### 1-4. 변환 입력 (학습 모드, 판정 TRAIN 또는 TRAIN_DATA_RANGE_LIMITED, validation 끝난 뒤)
```bash
python $COL/scripts/run_pairact_collect.py convert-input --prereg $P --run-root $RUNT \
  --teacher-sha 4b080d35a3dcbbd8fb8a992e1f1106a7289757b2 --out $RUNT/convert-input
# -> seed-<seed>/{SOURCE_SHA,EXIT,raw -> 원본 world raw symlink} + protocol.json(train/validation = 채택 seed, decision, data_range_limited)
```
원장 header의 사전 등록 sha256이 다르거나 판정이 학습 불가면 runner가 거부합니다. [확인 필요] world result.json의 `source_sha`가 teacher -c2 SHA(4b080d35)인지 첫 배치에서 확인합니다(convert가 대조).

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
