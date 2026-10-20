# pairact-r1 설계: 학습 ACT 공동 운반 정책 (P3 수집 사양 + P4 학습 준비)

상태: *초안. 수집·학습·GPU 실행은 하지 않았습니다.* 브랜치 `dsh/pairact-carry-r1`. 모든 신규 경로는 기본값 off입니다(`--pairact-r1-config`를 주지 않으면 `scripts/train_grasp_act.py` 동작이 바뀌지 않습니다).
작성: Claude 구현 워커(⑤), 2026-10-20(UTC). 상위 계획: `outputs/reports/claude-arch-parallel-20261019/aggressive-replan-1105.md` §8–9, `pair-act-carry-plan.md`.

## 0. base 결정
- base는 `main`(`01ac079fa`)을 그대로 씁니다. beamact4 스택(`harness/beamact_pair_student.py` StudentBarrier·`beamact4_policy.py`·`beamact3.py`)과 `experiments/2026-10-16-beamact{2,3,4}/README.md`가 이미 main에 있습니다.
- `origin/codex/beamact1`이 main보다 앞선 커밋 2개(`ff77792a4`, `f0261f053`)는 beamact3/4를 병합한 merge 커밋입니다. main 대비 diff는 삭제 5,389줄과 추가 55줄뿐이고 새 코드는 없습니다. 세 README도 두 ref에서 같습니다(`git diff --quiet` 통과). 그래서 새 base를 만들지 않았습니다.

## 1. 단독 ACT에서 배운 것 → pairact-r1 재사용 → beamact2/3 실패 원인

| # | 단독 ACT 발견·수정 | 단독 근거 | pairact-r1 구현 (파일·심볼) | 연결된 beamact2/3 실패 원인 (근거) |
|---|---|---|---|---|
| D1 | 명령 이력 copycat 대책 ①: 학습 때 ±1–6 PWM dither 주입. 타깃은 바꾸지 않음 | C4b 1 world에서 이력만 바꾸면 open이 회복. teacher release 구간에는 3–9 크기 dither가 0. A-r1 diff `3a28d24b4` `scripts/act18_carry_r1.py` | `harness/pairact_r1.py` `history_dither`(act18과 같은 식·상수 6/0.5). `PairActDataset.augment`는 TRAIN에서만, readback 전에 끕니다 | 정렬·READY 단계 정지. beamact2 퍼널 "접근8 → 명목 정렬1 → READY1 → 파지0"(beamact2 README:14), beamact3 A "16→0→0→0→0"(beamact3 README:12). 학생 이력의 흔들림이 teacher 분포 밖이라 정지 상태로 굳는다는 가설 H-A1 |
| D2 | 명령 이력 copycat 대책 ②: 이력 dropout(오래된 k개 항목을 항목 k 내용으로 채움, age 유지) | 같은 `3a28d24b4` | `history_dropout(..., min_k)`. *act18과 다른 점 1개*: `dropout_min_k=12`. beamact3 arm A는 정규화 뒤 항목 0–10을 0으로 가리고 최근 5개만 남깁니다(`beamact3.py` `COMPACT_HISTORY=5`). act18 그대로 k∈1..15를 쓰면 보이는 항목에 닿는 경우가 k≥12인 4/15뿐이라 실효 확률이 0.1×4/15≈2.7%가 됩니다. k∈12..15로 좁혀 모든 dropout이 보이는 창에 닿게 했습니다 | 같음(D1). arm A는 이력 입력이 5×14=70차원입니다. 단독 R8의 224차원보다 작지만 문맥 벡터에서 여전히 가장 큰 블록입니다 |
| D3 | done 시계 수정(v7): ±1–2 PWM 변화로는 `pwm_elapsed_s`를 리셋하지 않고 \|ΔPWM\|≥3에서만 리셋 | C2c: 재학습 없이 HO4 done 0/12 → 11/12(`origin/dsh/act18-c2c-v7clock` `ac274afeb`, `scripts/act18_evaluate.py` `DeadbandIssuedClock`, `--issued-clock-deadband 2`) | `DeadbandIssuedClock(2)`. 규칙은 act18과 같습니다(직전 관측 PWM과 비교). deadband 0은 계약 `IssuedClock`과 같다는 것을 테스트로 확인했습니다. config `issued_clock_deadband: 2`. *시계는 수집 때 recorder가 계산해 기록하므로 P3 recorder에도 적용해야 합니다*(COLLECT_SPEC §4). 학습은 기록된 시계만 읽습니다 | 한쪽 done 고착 A 11/20, B 9/20(beamact4 README:9). 학생 dither가 시계를 계속 0으로 되돌리면 done head가 "아직 이르다"로 판단해 한쪽만 끝나지 않는 패턴과 같은 기전이라는 가설입니다. 공동 운반에서는 파지 done과 하차 done이 둘 다 이 시계에 묶입니다 |
| D4 | 단계 구간 오버샘플 | 단독 release 실패가 open 전이에 몰림(C2c: release 실패 10건 모두 open 명령 미발행) | `TRANSITIONS` = alignment→ready, ready→execute(파지 시작), carry→place(하차 시작), place→complete. h0 단계가 바뀌는 행의 앞뒤 10행(1 s)을 가중 3으로 뽑습니다. 단독 A-r1 `release_weight=3`과 같은 배율입니다. balanced BCE prior도 sampler 질량 기준으로 계산합니다(`weighted_completion_priors`, act18 `completion_priors`와 같은 형식) | 정렬 전 GO 20/20(beamact4 README:9): READY 전이 판단 오류. 하차는 beamact2 데이터에 아예 없었습니다(D9) |
| D5 | 학습 단계 head(beamact4 `beamact4_stage_v1`, 6분류) | beamact4 README:15·21. 학습·평가는 하지 않은 후보였습니다 | 8분류로 확장: 접근·정렬·READY·실행(파지)·*운반*·*하차*·복구·완료. 공유 decoder feature 위 `nn.Linear(dim_model, 8)`, valid horizon 평균 CE(beamact4 형식). 단계 타깃은 teacher phase에서 오프라인으로 만든 sidecar이고 입력이 아닙니다(`build_pairact_r1_stage_targets.py`). 모르는 phase는 거부합니다 | 정렬 전 GO 20/20. beamact2/3는 READY를 "그리퍼 PWM 감소"로 판정해서 정렬과 무관하게 GO가 나갔습니다 |
| D6 | StudentBarrier READY 동기화 | `beamact_pair_student.py` StudentBarrier(stage mode): `ready` 클래스일 때만 READY, approach/alignment/recover면 철회, 허가 없는 execute/complete는 WAIT | `PairActBarrier`: carry/place를 execute와 같은 GO 이후 단계로 묶습니다(`BEAMACT4_EQUIVALENT`). GO 전 carry/place 제안은 정지·PWM 유지입니다. 하차 전 두 번째 동기점(`pairact_r1_place_sync_v1`)은 구현했지만 r1 config에서는 off입니다. P2 `pair_carry_sync.py`와 역할이 겹치는지 [확인 필요] | 정렬 전 GO 20/20, 한쪽만 진행 |
| D7 | done_recovery(`beamact4_done_recovery_v1`) | beamact4 README:16: done 다음 틱에 이전 chunk를 버리고 다시 추론. done 철회 가능 | `PairActChunkExecutor(done_recovery=...)`. config에서 on | 한쪽 done 고착 A 11/20, B 9/20 |
| D8 | 시작 분포를 평가 분포에 맞춤 | beamact4 README:9: 평가 A/B 각각 초기 40로봇 중 30개가 맡은 끝 0.8 m 밖. TRAIN은 54/60,023행(0.090%), 최대 0.84855 m. beamact2 README:60: 평가 cold start 0.5–2 m, TRAIN은 0.8 m 이내만 선정 | 수집 시작 거리를 맡은 끝 기준 0.3–1.2 m 균등으로 둡니다(COLLECT_SPEC §2). P5 평가도 같은 생성기를 씁니다 | 접근 실패. beamact2 단계 미통과 "접근12·명목 정렬7·파지1"(beamact2 README:13), beamact3 A "정렬16/접근4"(beamact3 README:15) |
| D9 | 시연 범위 확장 | beamact2 TRAIN 166 seed/60,023행(beamact2 README:66). 출처 데이터는 beampair8 성공 185쌍(beamact3 README:17). 기록 범위는 ".8m 인수 라벨부터 자기 명령 단계 완료까지"(beampair8 README:39). 운반·하차 시연 0 | 한 에피소드 = cold start → 파지 → 3초 유지 → 운반(문 통과) → zone B 하차 → 후진·완료. 로봇별 stream은 skill `grasp` 구간과 skill `release`(destination B) 구간 두 개입니다(P2 recorder 설계) | 운반·하차 시연 0 |
| D10 | teacher 성공 에피소드만 학습 | `grasp_act_data.convert`가 `physical_success is True`만 받음 | P2 evaluator 성공(zone B 안·낙하 0·로봇 간 접촉 0) AND 공동 3초 유지 통과만 TRAIN·validation 텐서로 들어갑니다. 실패는 rejection table에만 남깁니다 | (데이터 품질) |
| D11 | 같은 seed 비교 + 사전 등록 + 체크포인트는 검증 seed로만 선택 | 단독 tournament 규칙 | 학습 seed 20261020. 체크포인트 선택은 validation 20 seed의 오프라인 gate로만 합니다(OFFLINE_GATE.md). 보류 20 seed는 수집도 선택도 하지 않고 P5에서만 씁니다 | (방법론) beamact2는 "고정 최종10000step"(beamact2 README:3), beamact3는 "final20000"(beamact3 README:3) |

## 2. beamact2/3/4 결과 요약 (근거 인용)
- beamact2: "학생 성공은 0/20"(README:3). 종료 "cap_end16·학생 실패4·HOST_ERROR0"(README:12). 10k step, 감독 8,250.397 s(2.292 h), main 7,109.814 s(README:11). 학습 seed 20261015(README:66).
- beamact3: "A0/20·B0/20, 모두 NOT_READY"(README:3). 20k step. main wall A 10,120.58 s, B 12,782.31 s(README:27). 오프라인 wheel MAE는 줄었지만 전환 구간 MAE는 A 0.126, persistence 0.232(README:10)이고 closed-loop은 0/20이었습니다.
- beamact4: 위 두 결과를 진단한 문서입니다. 수치는 기존 beamdiag 판정이고 새 측정이 아닙니다(README:9).

## 3. 학습 GPU-h 추정 (P4)
| 근거 | 값 | 20k step 환산 |
|---|---|---|
| beamact2 10k, L4(warp3와 공유), 감독 wall | 2.292 h | 선형 4.58 h |
| beamact2 10k, main wall | 1.975 h | 선형 3.95 h |
| beamact3 20k 실측, main wall | A 2.81 h, B 3.55 h | 그대로 2.8–3.6 h |
- 주의: beamact2 README:11은 이 wall 값을 "속도 판정에 사용 안 함"(warp3와 GPU 공유)이라고 적었습니다. 그래서 위 값은 상한 쪽 근사로만 씁니다.
- 배치 8·chunk 8·백본은 그대로라 step 비용은 데이터 크기와 거의 무관합니다. 추가분은 stage head Linear(8)와 CPU dither/dropout(numpy, 항목당 수 μs)이라 작다고 봅니다[추정, 실측 아님].
- *등록 예산: 학습 4.6 GPU-h*(beamact2 선형, 보수적). smoke 300 step 약 0.1 h. 오프라인 gate(체크포인트 20개 × validation clean+dither 2회)는 0.5–1.5 h[확인 필요: pair 에피소드 행 수가 beamact2의 validation 6,908행보다 2–3배 많을 것으로 봅니다]. *P4 합계 약 5.2–6.2 GPU-h, L4 약 $1/h 근사로 약 $5–6.*
- 1 세션 상한은 `--max-wall-s 25200`(7 h)입니다. WALL_CAP으로 끊기면 `--resume`으로 이어갑니다(기존 트레이너 기능).

## 4. 위험과 미확인 사항
1. *dither 3–6과 v7 시계의 불일치*: 학습 dither는 이력 PWM만 바꾸고 기록된 시계는 바꾸지 않습니다. 배포에서 ±3–6 변화는 v7 시계를 리셋합니다. 단독 A-r1 + C2c 조합과 같은 불일치이고 r1에서는 그대로 둡니다. G5(dither 이력 오프라인 검사)로 영향만 봅니다.
2. *grasp 구간 teacher phase 어휘* [확인 필요]: 운반 구간은 P2 `carry:<phase>`(14개)에 맞췄습니다. 파지 구간(MJWarp beamact5 teacher)의 `teacher_phase` 값은 확인하지 못했습니다. 모르는 값은 sidecar 생성에서 거부되므로 P3 smoke 직후 실제 어휘로 `TEACHER_PHASE_TO_STAGE`를 고정해야 합니다(코드 변경 1곳, 사전 등록 전에 끝내야 합니다).
3. *P2 recorder 시계*: `pair_carry_recorder.py`(P2 worktree, 미커밋)는 `contract.IssuedClock()`(v6)을 씁니다. P3에서는 `DeadbandIssuedClock(2)`로 바꿔야 합니다. P2 워커 ④와 조율이 필요합니다.
4. *시작 분포 상한 1.2 m*: beamact2 평가 cold start는 0.5–2 m였습니다. r1은 수집과 평가를 모두 0.3–1.2 m로 맞추므로 beamact2와 같은 분포 비교가 아닙니다. 1.2–2 m는 "지도 주행(nav) → ACT 입구" 영역으로 남깁니다(beamact4 `handoff_v1` 명세).
5. *place_sync off*: 두 로봇의 하강 시작이 어긋나면 빔이 기웁니다. r1에서는 학습 단계 head와 teacher 시연에 맡깁니다. P2 동기 모듈과 합칠지는 P2 smoke 뒤에 결정합니다.
6. *init*: beamact3 체크포인트가 아니라 새 초기화(ImageNet ResNet18)로 시작합니다. beamact2/3와 같은 방식이고, 실패한 정책의 편향을 이어받지 않으려는 선택입니다.

## 5. 산출물
- 코드: `harness/pairact_r1.py`, `scripts/train_grasp_act.py`(플래그 2개, 기본 off), `scripts/build_pairact_r1_stage_targets.py`, `scripts/pairact_r1_offline.py`, `scripts/check_pairact_r1_seeds.py`, `tests/test_pairact_r1.py`
- 문서·설정: `COLLECT_SPEC.md`, `OFFLINE_GATE.md`, `PAIRACT_R1_TRAIN_CONFIG_DRAFT.json`, `PAIRACT_R1_EVAL_PREREG_DRAFT.json`, `seeds.json`, `RUNBOOK.md`(DeepSeek 실행 순서)
