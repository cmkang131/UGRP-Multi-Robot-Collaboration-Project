# ACT 레시피 감사 (ALOHA/act-plus-plus 대비) — Phase A

2026-10-18, act18 후속(task-8). **실행 없음·GPU 없음**. 근거는 공개 소스(아래 링크)·핀 고정 LeRobot 설치본 introspect·우리 코드/프로토콜·`results/doneprobe-r1/` 원본 계측이다. 성공을 주장하지 않는다.

## 0. 요약 판정

1. **done 헤드가 사실상 학습되지 않았다(버그급).** TRAIN 200에피소드·72,572행 중 양성 done 행은 정확히 200개(에피소드당 grasp 마지막 로컬 행 1개). episode-uniform 샘플링에서 양성 prior≈**0.00277**, batch 8에 양성이 하나라도 들어갈 확률은 **≈2.19%**다. 나머지 97.8% 스텝은 전부 음성이라 모델이 0으로 포화됐다. 실측 done 확률 최대 **0.000577**(전 8세계, tune·R8 동일, 문턱 .65/.5/.3/.2/.1 어느 것도 0틱 발화). → Phase B의 1순위 수정 대상.
2. **레시피 핵심값은 표준과 대체로 일치한다.** batch 8·lr 1e-5·AdamW wd 1e-4·KL 10·ResNet18 pretrained·chunk100(표준 후보 R100)·mean/std(floor .01) 정규화·ACT 이미지 aug 없음·100k update는 LeRobot 공통 기본과 일치한다. Lead가 우려한 "batch 32~64"는 ALOHA/act-plus-plus 기본과 다르다 — act-plus-plus 공식 학습 명령이 `--batch_size 8`이다(아래 인용). **batch는 편차 아님**.
3. **행동/기저(base)·done 계약은 표준 ACT와 구조적으로 다르다.** ALOHA는 측정 qpos(14) 절대 관절 목표 + Mobile base 속도 2차원(총 16차원, base는 5샘플 이동평균 전처리)이다. 우리는 wheel4(펄스 크기)+duration4+PWM5+done1 = 14차원이고, 디코더가 `abs(w)<0.155→0`, wheel을 .31–.40로 스냅, done을 `>=.65`로 자른다. 사용자 입력 제한(자기 RGB·자기 발행 명령)상 qpos 목표는 복제할 수 없지만, **base 표현·done 계약은 우리 고유 설계**이며 실패와 직접 연결된다.

## 1. 소스·핀

| 대상 | 핀/링크 |
|---|---|
| act-plus-plus (Mobile ALOHA 학습 코드) | <https://github.com/markfzp/act-plus-plus> (README·`imitate_episodes.py`·`constants.py`·`utils.py` 조회 2026-10-18) |
| ALOHA ACT 논문 | <https://arxiv.org/abs/2304.13705> |
| Mobile ALOHA 논문(co-training) | <https://arxiv.org/abs/2401.02117> |
| Diffusion Policy | <https://arxiv.org/abs/2303.04137> |
| LeRobot ACT 설정(설치본 introspect) | `ACTConfig()`: chunk100·n_action_steps100·temporal_ensemble_coeff None·use_vae True·latent32·kl10·lr1e-5·lr_backbone1e-5·wd1e-4·normalization MEAN_STD·ResNet18 pretrained |
| 우리 코드 | `scripts/act18_train.py`, `act18_policy.py`, `act18_evaluate.py`, `act18_stage.py`, `experiments/2026-10-17-act18/protocol.json`, harness `grasp_act_contract.py`(ACT_SHA `3f99d58c…` 핀 소스) |
| 우리 계측 원본 | `/home/ugrp/ugrp-sim/runs/act18/doneprobe-r1/`(gcp2 디스크 보존), Mac `experiments/2026-10-17-act18/results/doneprobe-r1/` |

## 2. 비교표

분류: **버그급**(동작을 설명하거나 막는 결함) / **편차**(의도·설계 차이, 효과 검증 필요) / **정상**(표준과 일치 또는 사용자 제약).

| 항목 | ALOHA/act-plus-plus 기본 | 우리 act18 | 분류 | 근거 |
|---|---|---|---|---|
| 행동 차원/의미 | 16 = qpos14(양팔 6관절×2+그리퍼2) + base 속도2. 절대 관절 목표. | 14 = wheel4(펄스크기)+duration4(≤.15s)+PWM5+done1. 관절 목표는 PWM 비율. | **편차** | contract `encode_action`/`decode_action`; ALOHA `state_dim=14`,`action_dim=16`,`target_qpos=action[:-2]` |
| base 처리 | base_action 2차원 연속 속도, 데이터 로드 시 **5샘플 이동평균**(`preprocess_base_action`→`smooth_base_action`). `calibrate_linear_vel`은 기본 c=0로 비활성(코드 주석). | wheel 명령을 펄스 크기+지속시간 8차원으로 인코딩. 디코드 시 `|w|<.155→0`, |w|→.31–.40 스냅, dt≤.15. 스무딩 없음. | **편차** | act-plus-plus `utils.py`; contract `decode_action` |
| 관측/state | qpos14(측정 관절) + 3~4 카메라 | 최근 4틱 자기 발행명령 252차원 + 과제 토큰. 측정 관절 없음. | **정상(사용자 제약)** | 사용자 결정: 자기 RGB·자기 명령 이력만. ALOHA qpos 그대로 복제 금지 |
| 정규화 | action/qpos mean/std, std floor 1e-2 | mean/std, fit_stats floor 0.01 | **정상** | act-plus-plus `get_norm_stats`/LeRobot MEAN_STD |
| batch | **8** (공식 명령 `--batch_size 8`) | 8 | **정상** | README 인용; LeRobot train 필수 인자도 8 계열 |
| lr/옵티마이저 | AdamW lr1e-5, backbone lr1e-5, wd1e-4 | AdamW lr1e-5 wd1e-4 (backbone 포함, 두 값 동일이라 등가) | **정상** | harness `make_policy`: optimizer_lr/backbone 1e-5, wd1e-4 |
| 스케줄/클립 | 상수 lr, AdamW; 학습 스텝당 1배치 | 상수 lr, grad clip 1.0(LeRobot 표준) | **정상** | act18_train.py |
| 학습량/선택 | sim 예제 2000 epochs(README; 직접 step 수와 구분), 실기 5000+·plateau 후 3–4배. **best val loss 선택** | 100k update 고정(LeRobot 기본), **best val 선택 없음**(고정 100k) | **편차**(선택 규칙) | act-plus-plus `train_bc`; 우리 protocol `checkpoint_selection`. 학습량 100k 자체는 LeRobot 표준 |
| chunk/실행 | chunk100(=2.0s @50Hz). 기본 query_frequency=100(청크 실행); `--temporal_agg` 시 매틱 재예측·k=.01 | R8 chunk8(=.8s @10Hz), R100 chunk100(=10s @10Hz). **매틱 재예측 + temporal ensemble k=.01** | **편차(정상 아님)**: 시간 스케일이 5배(10Hz vs 50Hz) | act-plus-plus eval; 우리 act18_evaluate Executor |
| temporal ensemble 가중 방향 | `exp(-k*arange(n))`, 쿼리시각 오름차순(오래된 예측에 큰 가중) | chunks 리스트 oldest→newest에 `exp(-.01*arange)` — 공식 구현과 같은 방향 | **정상(공식 구현 동일)** | 두 구현 대조 |
| 이미지 aug | ACT: **없음**(augment_images=False; crop/rotation/jitter는 Diffusion만) | 없음 | **정상** | act-plus-plus `utils.py` |
| history/프레임 | 관측 1스텝(qpos+현재 이미지) | 현재 RGB 1장(`current_full_v1`) | **정상** | act18 protocol |
| 카메라/해상도/Hz | 실기 3–4 카메라, 480×640, 50Hz | 자기 RGB 1장 640×480, 10Hz | **편차(사용자 제약)** | 사용자: top 카메라 금지·자기 RGB만. Hz는 시뮬 계약 |
| 구조 | ResNet18 pretrained, d512/FF3200, enc4/dec7(원본), CVAE32/KL10 | 동일 계열, dec1(원본 decoder 재사용 의도; SURVEY) | **정상(의도)** | SURVEY.md, harness make_policy |
| done/종료 | **없음.** 에피소드 종료는 환경 성공/시간. | 단일 tick 완료 분류 head(`balanced_bce_v1`), 디코드 문턱 .65. 평가가 `issued_done` 요구. | **버그급(설계 결함)**: 양성 희소·거의 학습 불가(3절) | contract `decode_action`; doneprobe 계측 |
| 데이터 | sim 50 eps/task; Mobile ALOHA co-training 825 eps. 다중 dataset_dir + sample_weights 지원 | v7 단일 dataset(240 eps: TRAIN200/VAL40; TRAIN 72,572행). co-training 미구현 | **편차(Phase C 대상)** | act-plus-plus `load_data`; dataset-r1 manifest |
| split/선택 | 첫 dataset에서 99/1, val loss로 선택 | 고정 TRAIN200 / TRAIN4·VAL8·FINAL40 시드 관문 | **편차** | protocol.json |
| 평가 계약 | 물리 성공/보상(환경) | `physical_success AND issued_done AND not cap_end` | **편차(계약; 5절)** | act18_evaluate/recount |

## 3. done 라벨 감사 (핵심)

측정: v7 `dataset-r1`(TRAIN 200 eps)을 원본 `samples.json`/teacher 라벨에서 재계수. 명령: 2026-10-18 gcp2, `act17_data.read`(TRAIN 72,572행, 에피소드 행수 316–452·중앙 360).

- 라벨 정의: harness `paired_segments(done_label='last_local_row_v1')` — (robot, skill, object_kind, role, destination_zone, episode) 구간마다 **마지막 `local_skill_sample=True` 행 1개**에만 done=1. grasp 구간의 그 행은 hold 끝이다(교사 로그의 release/lookaround done=`local_skill_sample=False`라 폐기). → done은 "관측 가능한 사건"이 아니라 **스케줄러 종료 표식**이다.
- 양성 수: 200행(에피소드당 1). 음성 72,372행.
- raw 양성 비율 0.002756, **episode-uniform·episode 내 uniform 행 prior 0.002766**(≈1/361).
- balanced BCE 실제 가중(현재 구현): 양성 `0.5/prior≈180.8`, 음성 `0.5/(1-prior)≈0.5014`. 하지만 손실은 배치의 유효 원소 평균이고, **batch 8에 양성이 포함될 확률 ≈2.19%**(100k 중 약 2,190스텝). 즉 97.8% 스텝은 양성 신호가 없어 확률을 0으로 미는 방향으로만 학습된다.
- 실측 결과(doneprobe-r1): done 확률 최대 **0.000577**(raw·ensemble 모두, 8세계), 전체 구간 p≈2.4e-4. tune(2k post-close 가중)과 R8(100k) 모두 동일.
- 결론: 현재 done 손실/샘플링으로는 done을 배울 수 없다. 문턱(.65) 하향은 답이 아니다(0.1에서도 0틱). 완료 신호는 별도 감독 설계가 필요하다.

## 4. done 학습 개선안 3개 (Lead 지시로 Phase A에서 설계만)

| 안 | 내용 | 예상 GPU | 장점 | 위험·검증 |
|---|---|---|---|---|
| (a) 양성 오버샘플링·pos_weight | 배치의 50%에서 positive 행 1개 + uniform 7개로 구성, 나머지 50%는 uniform. 손실은 `pos_weight=(1-prior)/prior≈361`(또는 class-balanced CE를 양성 포함 배치에 한정). | 5k≈13분, 20k≈50분 (+TRAIN4 14분/회) | 구현 작음, 기존 데이터 그대로 | positive만 과대표집하면 과발화·조기 스킬 전환. TRAIN4 물리 결과로만 판정, done 확률 분포(전체·구간별) 기록 |
| (b) done 전용 history 입력 | 현재 입력(state=명령 이력, 현재 RGB 1장)에 done 판단용 특징을 추가: 명령 이력 길이 확대(4→8틱) 또는 최근 프레임 2–4장(history montage) + done head 전용 MLP. | (a)와 동일 계열 | "시퀀스 어디쯤인지" 정보를 직접 줌 | 입력 계약 변경 → 화이트리스트·입력 감사 재검증 필요. 비용은 데이터 경로(history)에 따라 증가 |
| (c) 라벨 재정의 | 단일 tick 대신 마지막 K틱(예: 5틱=0.5s) done=1 window, 또는 종료까지 남은 시간 회귀(임계 이하에서 발화). | 학습 동일, 평가 계약 변경 | 양성 신호 5배·매끄러움, 캘리브레이션 가능 | 평가 계약 변경 → 사용자 승인 필요, 기존 act18 결과와 합산 불가. K·문턱을 사전등록 |

권고 순서: (a)를 B1(5k)에서 먼저 검증 → 효과 있으면 (b)/(c)를 Phase C 전에 한 번만 비교. 세 안 모두 새 후보·자체 관문이며 기존과 pooling 금지.

## 4. Phase B 후보(승인 대기, 실행 전 Lead 보고)

공통: gcp2 L4 1대, bf16 autocast, v7 TRAIN200 그대로(새 녹화 0), 새 후보 `act18-std`, 기존 R8/R100/tune과 **합산·pooling 금지**, 판정은 TRAIN4 4/4(적합도) → 통과 시에만 VAL8.

| 안 | 변경 | 예상 GPU | 위험 |
|---|---|---|---|
| B1 (done-only 격리) | R8/R100 100k 체크포인트에서 **5,000 step** fine-tune, 변경은 done 감독뿐: batch마다 최소 1개 양성 행 보장(양성 1+uniform 7, 50% 배치) + `pos_weight=(1-prior)/prior` 또는 balanced CE 재정의. 행동 손실 가중은 그대로. | 학습 ≈13분 + TRAIN4 ≈14분 = **~30분** | 양성 오버샘플로 done 과발화(스킬 조기 전환) 위험. TRAIN4로만 판정, VAL은 통과 시 |
| B2 (표준 정렬 fit) | chunk100·bf16·**20,000 step** from scratch, B1에서 확정된 done 감독 적용. batch8·lr1e-5·KL10·mean/std는 표준 그대로(수정 없음). | 학습 ≈50분 + TRAIN4 ≈14분 = **~65분** | 20k로 부족할 수 있음(표준 100k 대비). 실패 시 원인표(행동 붕괴/정규화/배치/done) |
| (선택) B3 | base action 이동평균·penalty 없이 wheel 펄스 표현 유지하되, TRAIN4 정지 병리를 겨냥한 early-stop 완화는 **금지**(아이디어 튜닝 금지) | - | - |

권고: **B1 먼저**(done 수정만 격리, 30분), 통과/부분 개선 확인 후 B2. B1·B2 모두 원본·SHA·funnel·거부표 기록.
※ Done 이외의 "표준 편차"는 대부분 사용자 제약(단일 RGB·명령 이력) 또는 시간 스케일(10Hz)에서 오므로 Phase B에서 바꾸지 않는다. base 펄스 표현 변경은 평가 계약 변경을 수반하므로 Phase C/D에서 별도 사전등록.

## 5. 평가 계약 후보 메모 (실행 금지, 사용자 결정용)

현재 게이트는 `issued_done`을 요구한다. done=0이면 물리 성공도 실패로 처리된다. 실제 R8은 물리 lift 2/4(88601·88603, finger 5.1N)·tune lift 4/4에서도 done 0으로 전부 실패 처리됐다. 대안(모두 기존 결과와 **합산 금지**):

- **(i) 물리 성공 정의로 분리**: 새 후보의 TRAIN/VAL 성공 = 평가 전용 GT의 `grasp/lift/hold(필요 시 release)`로 사전등록하고 issued_done을 요구하지 않는다. 장점: done-head 결함과 물리 성능 평가를 분리, 표준 ACT(종료 표식 없음)와도 부합. 단점: 게이트 의미 변경 → 기존 act18 결과와 비교 불가, 스킬 전환·release 진입이 done에 묶인 실행 구조라 done 없이는 release/최종 성공 정의를 별도로 정해야 함.
- **(ii) 규칙 기반 종료**: 자기 발행 명령 이력만으로(예: 그리퍼 close 명령 후 lift/자세 명령이 N틱 유지) done을 내는 코드 종료기. 장점: 실행 시퀀스가 진행되어 release/최종 성공 측정 가능, 학습 불필요. 단점: 손으로 짠 종료 규칙이 평가·행동에 개입하므로 기본 off 토글·사전등록·입력 감사(자기 명령만) 필요, "정책이 판단" 원칙과 충돌 소지.
- (iii) 참고: 표준 ALOHA는 done이 없다. 우리 프로토콜의 done 요구는 act17에서 온 고유 계약이므로, 새 후보의 성공 정의를 바꾸는 것은 사용자 결정 사항이다.
- 어느 쪽이든 **실제 프로토콜 변경은 사용자 승인 후**, 새 후보 prereg에 실패/성공 정의·funnel·비교 금지 범위를 명시한다.

## 6. Phase C 메모(참고)

act-plus-plus `load_data`는 `dataset_dir_l` 리스트+`sample_weights`로 co-training을 지원한다(BatchSampler가 에피소드 단위 가중). 우리는 단일 dataset 경로이고, v7 240 eps 외 act16w 40세계·근거리 데이터가 별도 준비되어 있다. Phase C에서 조건 토큰으로 구분해 혼합하고, 결과 pooling과 구분해 기록해야 한다. 근거: Mobile ALOHA arXiv 2401.02117 co-training.

## 7. 증거

- done 라벨 계수: 2026-10-18 gcp2(정지 전) `act17_data.read`로 TRAIN 200 eps/72,572행/양성 200/prior 0.002766 확인. 명령·출력은 이 문서에 기록, VM 디스크 보존.
- done 확률 계측: `results/doneprobe-r1/`(analysis 4 JSON sha `d88209f0…`·`3838d5af…`·`55e05aa9…`·`e561c5c7…`; done logs sha `01d201ec…`·`d0bf6927…`·`773d3bc2…`·`7eae8dfd…`; stage summaries `f9c27cd7…`·`42daf507…`), 요약은 `summary.json`의 doneprobe 항목.
- 레시피 값: pinned LeRobot `ACTConfig()` introspect(위 1절), harness `make_policy` 소스, `contract.encode_action/decode_action` 소스, act-plus-plus README/`imitate_episodes.py`/`utils.py`.
- gcp2는 Phase A 동안 유휴 → **정지**(2026-10-17T20:10:40Z TERMINATED), 원본 디스크 보존.
