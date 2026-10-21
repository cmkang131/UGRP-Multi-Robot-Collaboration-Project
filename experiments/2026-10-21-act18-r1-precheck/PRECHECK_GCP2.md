# A-r1 학습 전 점검 실행 문서 (gcp2, DeepSeek 실행용)

라벨: **PRE_TRAIN_BASELINE — 학습 전 점검, 판정 아님, 수집 데이터 아님**

근거: `outputs/reports/claude-arch-parallel-20261019/carry-place-owner-plan-v1.md` §D·A0–A1, `experiments/2026-10-17-act18/CARRY_RETRAIN_R1_DRAFT.md` §3(G-r1..G-r6), `scripts/act18_carry_r1.py`.

## 1. 대상
- 브랜치: `dsh/act18-r1-gate-precheck` (기반 `origin/dsh/act18-carry-retrain-r1` 3a28d24b4). 실행 SHA는 이 브랜치의 HEAD(이 문서를 담은 커밋)를 씁니다.
- 도구: `scripts/act18_r1_gate_precheck.py` (`data-stats`, `baseline-gate`, 둘 다 `--enabled` 없으면 실행 안 됨)
- 정책: learned, R8 step-100000(재학습 전). 데이터: teacher 데모(act17-v7 dataset-r1).
- 데이터셋(VM): `/home/ugrp/ugrp-sim/runs/act17-v7/dataset-r1`, manifest sha256 `44c1c460…b198`(protocol·bf16-probe·CO_PREREG 기록과 같음).
- R8 체크포인트(VM): `/home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000`, model.safetensors sha256 `e1ec6592…bb8d5a`(CARRY_RETRAIN_R1_CONFIG_DRAFT.json, C4b 도구 기록). 도구는 이 sha가 아니면 멈춥니다.
  - gcp2에 step-100000이 있는지는 [확인 필요]. 같은 디렉터리의 step-10000은 gcp2 open-loop 기록(`results/open-R8-10k-summary.json`)에 있습니다. 없으면 실행하지 말고 보고합니다.
- protocol: 이 브랜치의 `experiments/2026-10-17-act18/protocol.json`(VAL8 seed 목록을 읽음).
- 소스 위치(VM): 기존 관행처럼 `/home/ugrp/ugrp-sim/src/<SHA>`에 이 브랜치 SHA를 체크아웃합니다. 정확한 배포 절차는 DeepSeek 기존 절차를 따릅니다([확인 필요]). LeRobot은 `/home/ugrp/ugrp-sim/src/3f99d58c…`(ACT_SHA)를 그대로 씁니다.

## 2. 명령
```bash
cd /home/ugrp/ugrp-sim/src/<SHA>
TS=$(date -u +%Y%m%dT%H%M%SZ)
RUN=/home/ugrp/ugrp-sim/runs/act18-r1-gate-precheck-$TS
DS=/home/ugrp/ugrp-sim/runs/act17-v7/dataset-r1
R8=/home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000

# (0) 해시 확인
sha256sum $DS/manifest.json $R8/model.safetensors

# (1) CPU: 데이터 통계 (GPU 불필요, 데이터셋 읽기만)
python scripts/act18_r1_gate_precheck.py data-stats --enabled --dataset $DS --run-root $RUN

# (2) GPU 스모크(64행)는 다른 run root에 씁니다
sleep 1; SMOKE=/home/ugrp/ugrp-sim/runs/act18-r1-gate-precheck-$(date -u +%Y%m%dT%H%M%SZ)
python scripts/act18_r1_gate_precheck.py baseline-gate --enabled --dataset $DS --checkpoint $R8 \
  --protocol experiments/2026-10-17-act18/protocol.json \
  --run-root $SMOKE --limit-rows 64

# (3) GPU 본 실행: R8 추론만
python scripts/act18_r1_gate_precheck.py baseline-gate --enabled --dataset $DS --checkpoint $R8 \
  --protocol experiments/2026-10-17-act18/protocol.json --run-root $RUN \
  [--c4b-replay <C4b-GPU 출력 replay.json>]
```
- run root 이름 규칙: `runs/act18-r1-gate-precheck-YYYYMMDDTHHMMSS[Z]`. 스모크 결과는 본 실행과 섞지 않습니다.
- 출력: `$RUN/data-stats.json`, `$RUN/baseline-gate.json`(덮어쓰기 금지, 기존 run root 아닌 곳에는 쓰지 않음). 원본 데이터셋·체크포인트는 읽기만 합니다.
- `--c4b-replay`: G-r5는 C4b 재생 V0 arm 결과입니다. R8 기준값은 C4b-GPU 실행의 V0 출력 그 자체라 새 forward를 하지 않고 붙입니다. C4b-GPU 출력 경로는 [확인 필요]이며, 없으면 G-r5는 `not_computed`로 남습니다.

## 3. 계산 내용
- `data-stats`: teacher release 구간 PWM 변화 분포(0 / 1–2 / 3–9 / 10–19 / ≥20, servo별), release 진입 행 수, release 질량(에피소드 균등 vs release 가중 w=3), grasp·release done 라벨 비율(행 기준·샘플러 질량 기준), teacher open 시점(se), 등록값(±6, p=.5, dropout .1, seed 20261017)으로 dither/dropout을 적용한 전후 이력 변화 분포. split별(train/validation).
- `baseline-gate`: validation 40 중 VAL8 제외 32 episode의 teacher 관측으로 G-r1(grasp done recall/false-done @.65), G-r2(release 동일), G-r3(정규화 h0 action L1), G-r4(dither 이력에서 teacher open tick ±0.5 s 안 raw chunk pwm1 ≥ 1900 episode 비율; clean 입력 값도 같이), G-r5(C4b V0 첨부), G-r6(teacher grasp 행 TE pwm1 ≥ 1900 횟수). 추가로 release 구간 raw chunk 안 open 예측이 처음 나온 tick·chunk row·teacher open 대비 선행 시간(clean·dither 각각).
- 지표 정의는 DRAFT §3을 그대로 옮겼고, 표에 없는 세부 결정은 출력의 `operationalisation`에 적었습니다. 그중 [확인 필요] 두 가지:
  - G-r3 L1에서 done 차원 제외(차원 0..12).
  - G-r6 "조기 open": teacher grasp는 열린 집게로 시작하므로 grasp 전체 행 기준 횟수와 "teacher가 닫힌 행"에 한정한 횟수를 둘 다 냅니다. 어느 쪽이 gate인지 결정이 필요합니다.
- G-r6의 C2c grasp 구간 재생은 해당 도구가 없어 계산하지 않습니다([확인 필요]).
- 출력에 판정 필드는 없습니다(`verdict: null`). DRAFT 임계값은 참고로만 함께 적습니다.

## 4. 예상 GPU 시간과 비용
- 행 수: validation 32 episode × TRAIN 평균 362.9행/episode(72,572/200, B1_PREREG) ≈ 11.6k행 [추정; 실제는 출력 `rows`]. dither forward는 release 행만 추가합니다(release 비율 [확인 필요], 상한 = 전체 행).
- 추론 속도 근거: gcp2 L4에서 R8 open-loop 1,430행 26.3 s(batch 8, JPEG 로드 포함) ≈ 54행/s(`results/open-R8-10k-summary.json`).
- forward 11.6k–23.2k → 약 4–7분. 데이터셋 해시 확인·모델 로드·스모크 포함 GPU 점유 약 0.2 h, 상한 0.5 h. data-stats는 CPU 수 분.
- 비용: L4 $1.096/h × 0.2–0.5 h ≈ $0.22–0.55. 상한 1 h($1.10)를 넘으면 중지하고 보고합니다. 런당 $20 상한보다 훨씬 작습니다.

## 5. 결과 해석 규칙
- 이 baseline으로 A-r1을 열지 말지 정하지 않습니다. A-r1 개시는 owner plan §D 그대로입니다(평가 측 후보 A-c1~c3 tournament에서 승자 없음, 개선 +3/24 미만, 또는 C4b에서 V-img만 회복).
- 목적은 두 가지뿐입니다. G-r 측정 도구가 실제 데이터·체크포인트에서 끝까지 도는지, 그리고 현행 R8의 기준값이 어디에 있는지(특히 G-r4: dither 이력에서 open 예측이 나오는지).
- A-r1 학습 후에는 같은 도구·같은 입력·같은 dither seed로 새 체크포인트를 재야 R8 값과 비교할 수 있습니다. 현재 도구는 R8 sha만 받으므로 A-r1 측정 때는 체크포인트 인자 확장이 필요합니다([확인 필요], 별도 커밋).
- 이 결과는 수집 데이터가 아니고 폐루프 성능도 아닙니다. 기존 결과와 합산하지 않습니다.

## 6. 사전 등록 동결이 필요 없는 이유
- 결정을 내리지 않는 측정입니다. 출력으로 후보를 고르거나 버리지 않고, 통과/실패 판정 필드도 없습니다.
- 대상이 이미 고정된 R8 체크포인트와 고정된 teacher 데이터이고, 학습·선택·조정이 없습니다. 바꿀 수 있는 자유도(seed, 행 선택)는 코드 기본값으로 이 커밋에 고정돼 있습니다.
- 단, DRAFT §3 임계값(−2%p, +10%, 90%, 6/10)은 "학습 전에 동결"로 되어 있습니다. 이 baseline 숫자를 본 뒤 임계값을 바꾸면 그 변경은 사전 등록 위반으로 다룹니다. 임계값 동결 커밋은 A-r1 학습 전에 따로 합니다.

## 7. 보고 항목 (DeepSeek)
실행 SHA, 호스트, `sha256sum` 결과, 두 JSON 경로와 sha256, `rows`·`episodes`·`forwards`·`wall_s`, GPU 시간·비용, G-r1..G-r6과 open 첫 등장 요약, 오류가 있으면 원문.
