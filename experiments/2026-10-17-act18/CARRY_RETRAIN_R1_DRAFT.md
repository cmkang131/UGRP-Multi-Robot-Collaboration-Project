# A-r1 재학습 후보 초안 (실행 금지, DRAFT)

근거: `outputs/reports/claude-arch-parallel-20261019/carry-place-owner-plan-v1.md` §D. 대상 가설은 H-A1(자기 명령 이력 copycat)입니다. 이 커밋은 코드와 설정 초안만 담고, 학습과 GPU 실행은 하지 않았습니다.

## 1. 변경 범위 (모두 기본 off)

| 항목 | 위치 | 기본 | 초안 값 |
|---|---|---|---|
| 후보 등록 | `scripts/act18_policy.py` `CANDIDATES['act18-carry-r1']=8`, `PILOT_CANDIDATES`, `PILOT_KINDS`(`carry_history_robust_finetune_v1`) | 선택 안 하면 무영향 | — |
| 이력 dither | `scripts/act18_carry_r1.py` `history_dither`, 플래그 `--history-dither-pwm`, `--history-dither-prob` | None | 6, 0.5 |
| 이력 dropout | `history_dropout`, `--history-dropout-prob` | None | 0.1 |
| release 오버샘플 | `release_row_weights` + `CarryR1Dataset.sample`(`carry_release_weighted_v1`), `--release-weight` | None | 3.0 |
| 학습 진입 | `scripts/act18_train.py`: 위 옵션은 `--candidate act18-carry-r1`과 `--init-checkpoint`(R8)에서만 허용, 다른 tuning 옵션과 결합 금지 | — | 10k step, seed 20261017 |

- dither: raw context의 16×5 issued PWM 값마다 확률 p로 ±1–6 PWM 정수를 더합니다(500–2500 clip). 정답 action(teacher clean command)은 바꾸지 않습니다. 정책이 dither 이력을 보고도 teacher 행동을 내도록 학습합니다.
- dropout: 확률 p로 k∈[1,15]를 뽑아 가장 오래된 k개 이력의 명령 내용을 k번째 항목 내용으로 채웁니다(에피소드 시작 시 `OwnHistory`의 반복 패딩과 같은 형태). 나이(age) 열은 유지합니다.
- 오버샘플: 에피소드 균등 추출은 유지하고, 에피소드 안에서 release skill 행의 가중을 w로 둡니다. balanced BCE prior는 같은 표본 측도로 다시 계산합니다(`completion_priors`).
- 증강은 train/deploy 변환 동일성 검사 뒤에 켜집니다(`data.augment=True`). 검증·선택 데이터에는 적용하지 않습니다.
- 원본 R8, finish-r3, 데이터셋은 읽기만 합니다. 새 체크포인트는 `runs/act18-carry-retrain-r1-<TS>/train/step-<N>/`에, R8 대비 데이터·설정 차이는 run root의 `diff/`에 기록합니다.

## 2. 설정 초안
`CARRY_RETRAIN_R1_CONFIG_DRAFT.json`. 학습 GPU 시간은 R8 학습 기록으로 다시 산정해야 합니다([확인 필요]).

## 3. 오프라인 gate (학습 후, 폐루프 평가 전, 모두 통과해야 함)
GPU 추론만 쓰고 시뮬레이션은 돌리지 않습니다. 비교 기준은 같은 입력에 대한 R8 step-100000입니다.

| ID | 질문 | 데이터 | 통과 조건 |
|---|---|---|---|
| G-r1 | teacher 데모에서 grasp done 회귀가 없는가 | VAL8을 제외한 validation episode의 teacher 관측 | grasp done 행에서 h0 done 확률 ≥ .65 recall이 R8보다 낮지 않음(차이 ≥ −2%p), done이 아닌 grasp 행의 false-done 비율이 R8 이하 |
| G-r2 | teacher 데모에서 release done 회귀가 없는가 | 같은 데이터, release 행 | G-r1과 같은 기준을 release에 적용 |
| G-r3 | action 정확도가 크게 나빠지지 않았는가 | 같은 데이터 | 정규화 action L1(h0)이 R8 대비 +10% 이내 |
| G-r4 | dither 이력에서도 open을 예측하는가 | 같은 validation release 행에 ±1–6 dither(학습과 같은 규칙, 고정 seed)를 넣은 입력 | teacher open tick ±0.5 s 안에서 raw chunk pwm1 ≥ 1900이 episode의 ≥ 90%에서 나옴(R8 수치를 같이 보고) |
| G-r5 | 실제 실패 이력에서 open이 회복되는가 | C4b 재생 도구(`scripts/act18_c4b_counterfactual.py`)로 C2c 실패 10 world의 V0 재생 | TE pwm1 ≥ 1900이 실패 10 중 ≥ 6, 성공 9 world의 open 유지 9/9 |
| G-r6 | grasp 중 조기 open이 없는가 | teacher grasp 행과 C2c grasp 구간 재생 | grasp 구간 TE pwm1 ≥ 1900 발생 0 |

- 하나라도 실패하면 폐루프 평가로 넘어가지 않고, 결과와 실패 항목을 보고합니다.
- G-r5는 오프라인 재생이라 폐루프 성공을 뜻하지 않습니다. 통과하면 tournament A와 같은 사전 등록 규칙(HO4+TRAIN4, N=3, release 물리 성공 +3/24, G −2/24)으로 A-base와 비교합니다.
- 임계값(−2%p, +10%, 90%)은 초안 값이며, 학습 전에 동결합니다.

## 4. 하지 않은 것
- 학습, GPU 실행, 체크포인트 생성은 하지 않았습니다.
- R8 학습 wall time과 정확한 비용은 로컬에서 찾지 못해 [확인 필요]로 남겼습니다.
