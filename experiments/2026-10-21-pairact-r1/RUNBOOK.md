# pairact-r1 실행 순서 (DeepSeek용, 초안)

전제: P1 관문 통과, P2 smoke 통과, COLLECT_SPEC §4 recorder 수정(v7 시계, `teacher_phase`) 반영, 파지 구간 phase 어휘 고정(DESIGN §4-2). 하나라도 빠지면 시작하지 않습니다.
규칙: 새 run root만 씁니다. 원본·체크포인트는 덮어쓰지 않습니다. 오프피크(UTC 16:30–00:30)에만 실행하고, 끝나면 VM을 정지합니다. 브랜치는 `dsh/pairact-carry-r1`입니다.

## 0. 사전 확인 (CPU, 수 분)
```
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_pairact_r1.py        # 14 passed 기대
python scripts/check_pairact_r1_seeds.py --scan-refs origin/main origin/codex/beamact1 \
  origin/claude/beampair7 origin/claude/beampair8 origin/claude/beampair9 origin/claude/beamact5 \
  origin/dsh/pairact-p0-diag origin/dsh/act18-carry-retrain-r1 > runs/pairact-p3-<TS>/seed-check.json
```

## 1. P3 수집 (gcp6 또는 gcp2, 약 4.5 GPU-h [확인 필요])
- 수집 명령은 P2 runner가 확정된 뒤 정합니다 [확인 필요: P2 워커 ④의 `scripts/run_grasp_act_teacher.py` 운반 모드 인자]. seed는 train 8340000–8340199와 validation 8341000–8341019입니다. heldout은 수집하지 않습니다.
- 수집이 끝나면 `rejection_table.json`, `start-distance-hist.json`(COLLECT_SPEC §2 관문), `SHA256SUMS`를 남깁니다.

## 2. 변환 + stage sidecar (CPU)
```
# protocol: train_seeds=성공 train seed, validation_seeds=성공 validation seed (heldout 금지)
python -c "from harness.grasp_act_data import convert; import json; convert('runs/pairact-p3-<TS>', json.load(open('<protocol.json>')), 'datasets/pairact-r1-<TS>')"
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
