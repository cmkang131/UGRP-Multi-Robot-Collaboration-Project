# pairact-r1 실행 순서 (DeepSeek용, 초안)

전제(2026-10-20 결정으로 갱신): P1 관문(≥38/40)은 수집을 막지 않는 병행 작업입니다. 수집은 P2 smoke 통과(§1-0), COLLECT_SPEC §4 recorder 수정(v7 시계, `teacher_phase`) 반영, 파지 구간 phase 어휘 고정(DESIGN §4-2) 뒤에 시작합니다. 하나라도 빠지면 시작하지 않습니다.
규칙: 새 run root만 씁니다. 원본·체크포인트는 덮어쓰지 않습니다. 오프피크(UTC 16:30–00:30)에만 실행하고, 끝나면 VM을 정지합니다. 브랜치는 `dsh/pairact-carry-r1`입니다.

## 0. 사전 확인 (CPU, 수 분)
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_pairact_r1.py        # 14 passed 기대
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 \
  origin/claude/beampair7 origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 \
  origin/dsh/pairact-p0-diag origin/dsh/act18-carry-retrain-r1 > runs/pairact-p3-<TS>/seed-check.json
```

## 1. P3 수집 — 성공 시연만 학습 (P2 smoke 통과 직후, 오프피크)

사전 등록: `COLLECT_PREREG_DRAFT.json`(현재 READY_FOR_REVIEW, Codex 검토 뒤 FROZEN). 결정: `outputs/reports/claude-arch-parallel-20261019/pairact-success-filter-decision.md`.
runner: `scripts/run_pairact_collect.py`(제어 로직 `harness/pairact_collect.py`, case 생성 `collect_cases.py`, 테스트 `tests/test_pairact_collect.py` 20개).

### 1-0. 시작 조건 (모두 만족해야 시작)
1. *P2 smoke 통과*: `$RUN/smoke-1/summary.json`에서 HOST_ERROR 0이고, `success=true ∧ carry_success=true`인 world가 *1개 이상*(전 구간 성공 ≥1/N; 결정 문서는 6 run 기준 ≥1/6, 현재 SMOKE.md는 3 world). 0이면 수집하지 않고 P2를 고칩니다.
2. 사전 등록이 `FROZEN`이고 그 sha256을 기록했습니다. `READY_FOR_REVIEW` 상태에서는 *측정 모드*만 허용합니다(runner가 학습 모드를 거부).
3. *[확인 필요] GPU 녹화 배선*: adapter `run_beampair1.py:419`가 `record_training=False, noise=False`로 고정되어 있고, teacher 녹화에는 `recording_proof.qualified`(≥38/40 관문 + 녹화 동등성 check)가 필요합니다. 이 배선이 풀리기 전에는 `--mode measurement`(수율 A·구간 측정, 텐서 없음)로만 돌립니다.

### 1-1. 준비 (CPU, 수 분)
```bash
SRC=/home/ugrp/ugrp-sim/src/pairact-p2        # SMOKE.md §2의 teacher/adapter/root worktree 재사용
COL=/home/ugrp/ugrp-sim/src/pairact-r1        # 이 브랜치(dsh/pairact-carry-r1) worktree
git -C /home/ugrp/ugrp-sim/ugrp worktree add --detach $COL origin/dsh/pairact-carry-r1   # 레포 경로는 [확인 필요]
cd $COL && python -m pytest -q tests/test_pairact_collect.py tests/test_pairact_r1.py     # 기대: 34 passed
RUNP3=/home/ugrp/ugrp-sim/runs/pairact-p3-$(date -u +%Y%m%dT%H%M)                         # 새 run root만
mkdir -p $RUNP3
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 origin/claude/beampair7 \
  origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 origin/dsh/pairact-p0-diag \
  origin/dsh/act18-carry-retrain-r1 origin/dsh/pairact-p2-carrypath origin/dsh/pairact-p2-carrypath-r \
  origin/dsh/pairact-p2-carrypath-a > $RUNP3/seed-check.json     # passed=true 필요 (2026-10-21 로컬: true)
sha256sum experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json | tee $RUNP3/PREREG_SHA256
git rev-parse HEAD > $RUNP3/COLLECT_SOURCE_SHA
```

### 1-2. 수집 1차 (GPU, 오프피크, 배치 20 world)
episode 명령은 SMOKE.md §3 플래그 그대로에서 `--cases/--indices/--out`만 runner가 채웁니다. `--cap-s 60`(파지) + runner가 운반 110 SIM s를 더합니다.
```bash
cd $SRC/root    # wrapper가 실행하는 root 체크아웃 확인은 SMOKE.md §3 [확인 필요] 그대로
EP="python /home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py --flow beampair \
 --adapter-source $SRC/adapter --teacher-source $SRC/teacher --cases {cases} --indices {indices} --cap-s 60 --out {out} \
 --vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1 \
 --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1 \
 --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml \
 --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json \
 --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json --batch-per-world-speed-v1"
python $COL/scripts/run_pairact_collect.py collect --prereg $COL/experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json \
  --run-root $RUNP3 --mode measurement --noise off --batch-size 20 --max-batches 4 \
  --deadline-utc <오늘 날짜>T00:00Z --dependency-root $SRC/teacher --frozen-root $SRC/root \
  --candidate pairact_p2_r13 --episode-cmd "$EP"
```
- 첫 배치는 validation 20 seed(8341000–019, 구간 index%6, 목표·상한 미포함)입니다. 그다음부터 train seed 8340000부터 순서대로, 구간 B0–B5 round-robin(구간마다 시도 4회 전까지) → 결손 가중 할당입니다.
- *중단·재시작*: 같은 명령을 다시 실행하면 `ledger.jsonl`에서 이어갑니다. 최종 summary가 있는 배치는 다시 돌리지 않고 집계만 하고, 중간에 끊긴 배치는 남은 slot만 `try-2`로 1회 재시도합니다. 두 번째도 끊기면 그 slot은 host_error로 닫습니다. HOST_ERROR world는 같은 seed·구간으로 1회 재배정됩니다. 배치 HOST_ERROR가 2번 연속이면 멈춥니다(STOP_HOST) → 로그·progress.json 보존 후 Claude 리뷰.
- `--max-batches`·`--deadline-utc`: 오프피크 끝(UTC 00:30) 전에 새 배치를 시작하지 않도록 둡니다. 배치 1개 wall은 smoke 실측(world당 wall/SIM)으로 정합니다 [확인 필요].
- 원본 보존: 모든 배치 출력은 `$RUNP3/batches/bXXX/try-N/`(world-XXX/raw 포함)에 남고, 실패도 지우지 않습니다.

### 1-3. 볼 것과 보고
```bash
python $COL/scripts/run_pairact_collect.py report --prereg $COL/experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json --run-root $RUNP3
```
- `report.json`: `A.text`(그대로 인용), `A.bins`(구간별 시도·성공·채택·성공률·need), `validation`, `ks`(성공 vs 실패 시작 거리·|yaw| KS, 참고용), `distance_gate`(COLLECT_SPEC §2), `failures`(단계:사유 집계), `stop`.
- 보고 표기: *A* "교사 시연 수집: 성공 n / 시도 N (데이터 필터용, 학습 결과 아님)" + 구간 표. B(교사 관문 n/40), C(학습 n/20)와 섞지 않고, smoke·r13·CPU 결과와 합산하지 않습니다. 측정 모드면 "녹화 없음"을 같이 적습니다.
- 멈춤 사유: STOP_TARGET(채택 200 ∧ 구간마다 ≥20), STOP_CAP(시도 600; 채택 <150이면 학습 안 함, 구간 미달이면 "데이터 범위 제한"), STOP_HOST, MAX_BATCHES/DEADLINE(다음 밤 같은 명령으로 이어감).
- DART 노이즈는 기본 off입니다. 켜려면 사전 등록 개정 + Claude 승인 + 새 run root(`--noise on`)가 필요하고, GPU adapter가 noise를 고정 off로 넘기는 문제[확인 필요]가 먼저 풀려야 합니다.

### 1-4. 변환 입력 (학습 모드 ledger만)
```bash
python $COL/scripts/run_pairact_collect.py convert-input --prereg <FROZEN prereg> --run-root $RUNP3 \
  --teacher-sha 59299f903f4a2f9a2eabe5ff0e442e0ce25e8266 --out $RUNP3/convert-input
# -> seed-<seed>/{SOURCE_SHA,EXIT,raw -> 원본 world raw symlink} + protocol.json(train/validation = 채택 seed)
```
채택된 성공만 들어갑니다. 실패·handoff 성공은 들어가지 않습니다. 이어서 §2를 `runs_root=$RUNP3/convert-input`, `protocol=$RUNP3/convert-input/protocol.json`으로 돌립니다.

## 2. 변환 + stage sidecar (CPU)
```
# protocol: train_seeds=성공 train seed, validation_seeds=성공 validation seed (heldout 금지)
python -c "from harness.grasp_act_data import convert; import json; convert('$RUNP3/convert-input', json.load(open('$RUNP3/convert-input/protocol.json')), 'datasets/pairact-r1-<TS>')"
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
`PAIRACT_R1_EVAL_PREREG_DRAFT.json`의 [확인 필요] 항목(에피소드 cap)을 채워 커밋한 뒤에 실행합니다. 평가 runner는 P2 evaluator와 PairActBarrier 연결이 필요하고, 아직 구현되지 않았습니다(남은 일).
