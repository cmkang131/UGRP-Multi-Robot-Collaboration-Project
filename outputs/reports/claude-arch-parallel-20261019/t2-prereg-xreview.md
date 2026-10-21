# 공동 운반 수집 사전 등록 v3s 교차 검토 (Claude, 2026-10-21)

- 대상: `dsh/pairact-carry-r1-v3-shard` `6a68e4ca8`, `experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json` sha256 `76759f31de5b4d890a46b45aae005726d4810776f9ca64718c5d289a6200f9a7`(작업트리에서 직접 확인)
- 코드: `harness/pairact_collect.py`(이하 `pc`), `scripts/run_pairact_collect.py`(이하 `runner`)
- Codex 검토와 독립적으로 진행했습니다(Codex v3s 검토문은 읽지 않았습니다).
- 재현 테스트: `dsh/pairact-prereg-xreview` `b4202e794` `tests/test_pairact_prereg_xreview.py` 8개(X1–X8), 6a68e4ca8 기준 *8 passed*. 기존 `test_pairact_collect.py`·`test_pairact_collect_shard.py`도 *106 passed*입니다. 수집 코드는 고치지 않았습니다. 각 테스트는 현재 동작을 고정해 두었고, 수정이 들어가면 표시한 assert가 뒤집혀야 합니다.
- 모든 수치는 가짜 에피소드(FakeEpisode)에서 나온 값입니다. 시뮬레이터 결과도 수집 데이터도 아닙니다.

## 요약 판정
*HOLD 권고.* BLOCKER는 3건입니다. (B1) K>1에서는 같은 결과 함수로도 정지 사유와 학습 판정 클래스가 직렬과 달라집니다. 즉 샤딩이 "실행 방식만" 바꾸는 것이 아닙니다. (B2) K>1에서 STOP_SEEDS가 in-flight 재큐를 버립니다. (B3) validation batch에서 HOST_ERROR가 하나만 나와도 학습 불가 판정이 됩니다. 세 건 모두 FROZEN_CORE 전에 사전 등록 문구나 코드로 정해야 합니다. 동결 뒤에는 바꿀 수 없습니다.

---

## BLOCKER

### B1. K>1에서 정지 사유·판정 클래스가 직렬과 달라짐. `train_closed`는 최종 판정을 고정하지 못함
- 근거
  - `pc.train_stop` 425–428: `train_closed`는 7개 규칙을 *모두 다시 평가한 뒤* 맨 마지막 fallback으로만 쓰입니다. 최종 판정(`pc.decision` 447–483)은 close 이후에 끝난 in-flight batch 결과까지 포함한 집합에서 다시 계산됩니다.
  - prereg `sharding.stop`(263)은 "the first train stop seen … is written as train_closed and ends train planning"이라고 씁니다. `what_changes_vs_serial`(261)이 공개하는 것은 "the bin sequence … can differ" 하나뿐입니다.
  - prereg 안에서도 두 문장이 충돌합니다. `training_decision.per_stop.STOP_DISTANCE`(221)는 "NO_TRAIN_DISTANCE_GATE"이고, `training_decision.rule`(214)은 "distance gate fails on the *final* admitted set"입니다. 직렬 실행에서는 정지 시점 집합과 최종 집합이 같아서 충돌이 없지만, K>1에서는 둘이 갈립니다.
- 재현
  - X1: 원장에 `train_closed=STOP_DISTANCE`가 있어도, 최종 집합(A 160, 고른 거리)에서는 `decision`이 *TRAIN*으로 나옵니다. per_stop은 NO_TRAIN이어야 한다고 적고 있습니다.
  - X7: 같은 가짜 결과 함수(`test_pairact_collect_shard.outcome`)를 쓴 비교입니다. 직렬은 STOP_TARGET, A 204, N 480입니다. K=4는 STOP_DISTANCE → *NO_TRAIN_DISTANCE_GATE*, A 181, N 380입니다. 지연된 view에서 A≥150을 넘는 순간 원거리 비율이 25%에 못 미쳐 영구 정지가 걸렸습니다.
- 영향: 같은 seed 풀, 같은 판정 함수인데도 K 값에 따라 "학습함/학습 안 함"이 바뀝니다. K는 core 값이고(prereg 257) 판정 전에 고정하므로 사후 선택은 아닙니다. 다만 "execution only" 표기는 사실과 다르고, 공개 범위도 부족합니다.
- 권고 수정(둘 중 하나를 사전 등록)
  1. *drain-then-decide*(권장): lagged view에서 정지 후보가 보이면 `train_closed`를 쓰지 않습니다. in-flight가 다 끝날 때까지 `batch_skipped`로 기다리고, 완전한 view에서 `train_stop`을 다시 평가합니다. 그 결과가 참일 때만 close합니다. 이렇게 하면 정지 판정은 항상 직렬과 같은 완전한 데이터에서 내려지고, 남는 차이는 in-flight overshoot와 배정 순서뿐입니다. 이 방식은 B2와 R5도 같이 해결합니다.
  2. 아니면 `decision()`이 `train_closed.stop`을 우선 쓰도록 하고(STOP_DISTANCE → 항상 NO_TRAIN), `what_changes_vs_serial`에 "K>1에서는 정지 사유·N·판정 클래스가 직렬과 다를 수 있다"를 명시합니다.

### B2. K>1에서 STOP_SEEDS가 in-flight batch의 HOST_ERROR 재큐를 기다리지 않음
- 근거
  - `pc.train_stop` 422–424는 "train 재큐 없음 ∧ 미소비 seed 없음"이면 STOP_SEEDS입니다. view에는 마지막 batch의 계획(seed 소비)은 들어 있지만 결과(HOST_ERROR → 재큐)는 아직 없습니다. 그래서 다음 경계에서 바로 `train_closed=STOP_SEEDS`가 써집니다(`pc.close_row` 1364–1368, `runner.run_shard` 373–376).
  - STOP_CAP은 `reserved`로 in-flight를 기다립니다(`pc.plan_batch` 550, `runner.run_shard` 377–380 `batch_skipped`). STOP_SEEDS에는 이런 대기가 없어서 두 규칙이 비대칭입니다.
  - prereg `sharding.attempt_cap`(262): "environment failures of the in-flight batches … are re-queued as in the serial run". seed가 다 떨어진 상황에서는 이 문장이 거짓이 됩니다.
- 재현: X2(setup 거부 10%로 seed가 cap보다 먼저 소진, 마지막 seed 8340599 HOST_ERROR 1회). 직렬은 재큐 1회 시도, K=2는 재큐 0회이고 N이 1 작습니다.
- 영향: 최대 (K−1)×batch_size개의 재큐가 사라집니다. seed 소진은 A가 80/150 경계 근처일 때 생기기 쉬운 상황이라 판정 tier가 직접 바뀔 수 있습니다.
- 권고: B1-1(drain-then-decide)로 해결하거나, STOP_SEEDS 조건에 "in-flight train batch 없음"을 추가합니다.

### B3. validation batch에서 HOST_ERROR world가 1개만 나와도 NO_TRAIN_VALIDATION_INSUFFICIENT
- 근거
  - validation은 20 seed를 batch 하나로 돌립니다(`pc._fixed_bin_slots` 529–535, batch_size 20).
  - summary.HOST_ERROR>0이면 batch가 unclean이 되고(`pc.batch_is_clean` 640), unclean batch의 성공은 전부 `success_not_admitted:batch_not_clean`이 됩니다(`pc.judge` 629–630).
  - 재큐되는 것은 HOST_ERROR world 하나뿐입니다(`requeue_eligible`). complete world는 다시 돌리지 않습니다.
  - validation gate는 채택 ≥8/20이고 "no extra validation seeds, no replacement"입니다(prereg 298).
- 재현: X3(모든 에피소드 성공, validation seed 8341003 world 1개만 소실). validation S 20, A 1, E 1이고 최종 상태는 *NO_TRAIN_VALIDATION_INSUFFICIENT*입니다.
- 영향: 환경 실패 하나가 행동 판정(학습 금지)으로 바뀝니다. status table의 원칙("environment: excluded from N")과 정면으로 어긋납니다. train 쪽에서 unclean batch가 아무것도 채택하지 않는 규칙(audit 1)은 데이터 손실에 그치지만, validation에서는 판정 자체를 끝냅니다.
- 권고(❗결정 필요, 하나를 사전 등록)
  1. validation unclean batch의 complete world도 같은 seed로 1회 재큐합니다(환경 실패와 같은 처리).
  2. validation은 batch_size를 작게(예: 5) 잡아 피해 범위를 줄입니다.
  3. validation gate 분모를 "clean batch에서 판정된 world"로 바꾸고, 하한을 8/(clean 수)로 비율화합니다.
  - 권고는 1입니다. 판정 함수가 바뀌지 않고 status table 원칙과도 맞습니다.

---

## 권고

### R1. bin_limit은 S/N 기준, 배정은 A_b 기준이라 "성공은 하는데 채택이 안 되는" 구간이 예산을 독식
- 근거: `pc.pending_bin_limits` 364(`successes/attempts`)와 `pc.allocate` 512–518(`need = 20 − A_b`, `p = (A_b+1)/(N_b+2)`, 하한 0.05). prereg `bin_limit.rule`(182)은 물리 성공률을, `allocation.quantity`(241)는 A_b를 씁니다.
- 재현: X4. B5가 30회 중 15회 성공했지만 전부 handoff라서 A=0입니다. 이 구간은 제한되지 않고, 20슬롯 중 *14개 이상*을 받습니다(weight = 20/0.05 = 400, 다른 구간은 약 29).
- 영향: 원거리나 away 구간에서 search/approach handoff가 잦으면(실측 비율은 [확인 필요]), 그 구간이 cap 600까지 시도를 빨아들이고 다른 구간이 굶습니다. A≥200에서 한 구간만 need>0으로 남아도 같은 일이 생깁니다.
- 권고: bin_limit 조건을 "S_b/N_b < 0.2 *또는* A_b/N_b < 0.1(N_b≥20)"으로 넓히거나, 한 batch에서 한 구간이 받을 수 있는 슬롯 상한(예: batch의 50%)을 사전 등록합니다.

### R2. 거리 관문의 근거 문장과 수치가 맞지 않음. STOP_DISTANCE가 A=150에서 너무 일찍 영구 정지
- 근거: prereg `distance_gate.rationale`(338)은 "25% … while allowing the far bins to be bin_limited"라고 씁니다. 그런데 B4·B5가 둘 다 제한되면 0.8 m 초과 거리는 B2/B3(0.6–0.9 m)의 상위 1/3에서만 나옵니다. 그러면 약 (B2+B3)/3/A ≈ 16%가 되어 25%에 못 미칩니다.
- 재현: X5(B0–B3 각 38, B4·B5 각 3, A 158) → share < 0.25, 관문 실패. 기존 테스트 `test_bin_limit_closes_hopeless_bin_and_marks_range_limited`도 이 경우 NO_TRAIN_DISTANCE_GATE를 허용합니다.
- 추가: STOP_DISTANCE는 A가 150을 넘는 첫 경계부터 매 경계마다 평가하고 영구 정지시킵니다(`pc.train_stop` 412–413). 원거리 구간이 느리게 차는 중간 상태에서도 바로 NO_TRAIN이 됩니다. X7(K=4)에서 실제로 이렇게 됐습니다.
- 권고: (i) rationale을 "B4·B5 둘 다 제한되면 사실상 NO_TRAIN_DISTANCE_GATE"로 고칩니다(의도를 명시). (ii) STOP_DISTANCE는 "A≥150 ∧ 원거리 구간(B4, B5)이 모두 need==0 또는 bin_limited"일 때만 평가해서, 일시적인 불균형으로 영구 정지되는 것을 막습니다.

### R3. STOP_HOST "연속 2 batch"를 전역 index로 셈. 샤드 하나가 계속 고장나도 발동하지 않음
- 근거: `pc.consecutive_unclean_batches` 392–401은 batch 번호 역순으로 연속 unclean을 셉니다. batch k는 shard k%K 소유라서 고장난 shard의 batch는 K개 간격으로만 나타납니다.
- 재현: X8(K=2, shard 1은 summary가 항상 HOST_ERROR). train batch 30개 중 15개가 unclean인데 STOP_HOST가 *발동하지 않습니다*. N 600 중 300이 채택 불가로 소모되고 A는 100입니다.
- 영향: 두 VM 배정(RUNBOOK 88: gcp6 [0,1,2], gcp2 [3,4,5])에서 한 VM의 호스트 문제가 정지 없이 시도 예산을 태웁니다.
- 권고: 샤드별(또는 VM별) 연속 2 unclean 규칙, 또는 "최근 완료된 2K batch 중 unclean ≥ K"를 사전 등록합니다.

### R4. bin_limit 지연 효과를 정량으로 공개하지 않음
- 근거: `pc.boundary_rows` 1355–1361은 lagged view의 N_b로 판정합니다. 희망 없는 구간은 그 사이에도 weight 400(need/p_floor)을 유지해서 in-flight batch마다 슬롯을 대부분 가져갑니다.
- 재현: X7. B5 시도가 직렬 22, K=4 *36*입니다.
- 권고: `what_changes_vs_serial`에 "제한 구간이 최대 약 (K−1)×batch_size 시도를 더 받을 수 있다"를 추가합니다.

### R5. K>1에서 train in-flight 중에 validation이 계획됨
- 근거: close 뒤 `pc.plan_batch` 557은 lagged view의 `decision()`이 TRAINABLE·pending이면 validation을 계획합니다. prereg `seeds.validation.rule`(287)은 "only after the train stop (never during … collection)"입니다.
- 재현: X6(K=3) — 첫 validation batch 직전 2개 index 안에 train batch가 있습니다(동시 실행).
- 영향: lagged 판정이 TRAINABLE이어도 in-flight 결과로 최종 판정이 STOP_RECORD 등으로 바뀔 수 있습니다. 그러면 validation seed 20개를 이미 쓴 뒤입니다(교체 금지 규칙). B1-1로 같이 해결됩니다.

### R6. K는 FROZEN_CORE에 고정되는데, K 경합 측정은 동결 뒤 "첫 샤드 batch"에서 함
- 근거: prereg `sharding.K`(257, core), `known_blockers`(360), RUNBOOK 1-6a·88("1-6a의 K 측정 전이면 3샤드가 안전").
- 문제: 측정 결과를 보고 K를 바꾸면 새 run root에서 같은 train seed(8340000…)를 다시 수집하게 됩니다. 이것은 결과를 본 뒤의 2차 시도이고, run root 폐기 규칙이 사전 등록되어 있지 않습니다.
- 권고: K 경합 측정은 FROZEN_CORE 전에 measurement 모드(pilot seed)로 끝냅니다. STATUS 716의 "K=4 pilot seed 8343020–039 재실행" smoke가 이 역할을 합니다. 다만 measurement 모드는 `_fixed_bin_slots`(비적응)라서 K>1 lag 경로(warmup, deficit, bin_limit, 정지)는 검증하지 못합니다. 그 smoke는 "결정성·경합 측정용"으로만 라벨해야 합니다. 그리고 "학습 run root를 폐기하는 조건과 그 뒤 seed 처리"를 사전 등록합니다.

### R7. merge의 seed 중복 검사 범위가 좁음
- 근거: `runner.merge` 443–447은 key를 `(batch, split, seed)`로 잡아서, 다른 batch에서 같은 seed가 비재큐로 쓰인 경우를 잡지 못합니다. `pc.running_seeds`(1338)는 *동시에* 실행 중인 경우만 봅니다. flock(`runner.shard_lock` 284)은 같은 파일시스템 안에서만 막아 주고, 두 VM 사이에서 rsync가 잘못된 방향으로 덮어쓰는 것은 막지 못합니다.
- 권고: merge에서 split별 "비재큐 seed는 1회, 재큐는 environment 실패 뒤 1회"를 전역 검사합니다. 각 shard 원장이 이전 merge 기록(`merge.json` sha·행 수)의 prefix인지도 확인합니다.

### R8. tier 2/3은 yaw 범위를 보지 않음
- 근거: 거리 관문(`pc.distance_gate` 379)은 거리만 봅니다. away 구간 B1·B3·B5가 모두 부족해도 TRAIN_DATA_RANGE_LIMITED가 되고, 라벨만 붙습니다(prereg 224).
- 권고: P5 heldout 보고를 bin별(특히 facing/away)로 분리하는 것을 EVAL prereg에 명시합니다. 원하면 "yaw 한쪽 3구간이 모두 A_b<20이면 NO_TRAIN"을 추가합니다.

---

## 정보

- I1. *pilot 분리는 코드에서 강제되고 있습니다.* 허점은 찾지 못했습니다.
  - READY 단계 measurement의 header는 purpose `pilot_yield_only`입니다(`runner.main` 652–659, `pc.header` 243–247).
  - probe source에서 거부됩니다(`pc.require_probe_source` 279–280).
  - convert-input에서 거부됩니다(`pc.convert_input` 853–859: purpose, mode, FROZEN·core 일치. CLI는 core를 넘김 `runner.main` 572–573).
  - training 모드는 FROZEN일 때만 로드됩니다(`pc.load_prereg` 93–95).
  - 같은 run root에서 header가 다르면 거부합니다(`runner.run` 197, `run_shard` 330).
  - convert-input은 파일 sha256이 일치해야 합니다(core 대체 없음, 853). 그래서 READY 시절 원장은 FROZEN 뒤에도 입력이 될 수 없습니다.
- I2. pilot 26/40은 *-c4 스택* 결과입니다(STATUS.md 14행). prereg pin은 -c5입니다. FROZEN_CORE probe source run이 같은 pilot seed(8343000–039)를 다시 돌리는데, 두 보고서의 문구가 같습니다("pilot 수율 측정", `pc.report` 791). 그래서 purpose와 stack을 문구에 넣어 구분할 것을 권합니다. pilot 수율은 train 수율 기대치(33% 가정)의 근거가 아닙니다.
- I3. 시간 순서는 git으로 확인했습니다. v3s prereg 커밋 `c5a154faf`가 05:43Z, pilot 종료가 09:10Z(STATUS 14)입니다. tier 수치(`bcfefaadc`)는 00:27Z입니다. 판정 규칙은 pilot 결과 전에 고정되었습니다.
- I4. 정지 우선순위: STOP_HOST가 STOP_TARGET보다 먼저 평가됩니다. 그래서 목표를 달성했어도 마지막 2 batch가 unclean이면 validation이 `--validation-after-host-fix`를 기다립니다. 판정 클래스는 같으므로 의도인지 확인만 하면 됩니다. STOP_RECORD는 validation의 record_error에도 걸립니다(`pc.train_stop` 407). 보수적이고 문제없습니다.
- I5. episode 종료 뒤 `exit-try-N.json`을 쓰기 전에 crash하면 exit가 unknown이 되어 batch가 unclean이 되고, 성공 전부가 미채택됩니다(`runner.run_batch` 262–263, `exit_code` 84–86). 드물고 보수적이지만 B3 경로(validation)에서는 치명적일 수 있습니다.
- I6. 재시작과 merge에서 이중 집계 경로는 찾지 못했습니다. ingest는 `done_slots`로 slot별 1회만 기록하고(`runner.ingest` 111–113), view는 결과를 `shown` 집합으로 1회만 붙입니다(`pc.shard_view` 1322–1330). 원장 계획이 결정적이라 own 원장 일부가 손실돼도 같은 계획이 재생성되고, `cases.json` sha가 대조됩니다(`runner.batch_cases` 176). 단 R7의 운영 실수 경로는 검사하지 않습니다.
- I7. 중단된 try를 다시 돌리면 try-1에 완료된 world raw가 있어도 같은 seed를 다시 실행합니다. 원장이 그 결과를 관측하지 않았으므로 선택 편향은 아닙니다. 보고서에 "interrupted 재실행 수"를 표시하면 감사가 쉬워집니다.

## DeepSeek 실행 전 조치(2개)
1. B1–B3의 처리 방식을 오너가 정하고 prereg를 v3s2로 개정합니다(FROZEN_CORE 전). 권고는 drain-then-decide와 validation 재큐(B3-1)입니다.
2. K 경합과 결정성 측정을 measurement 모드에서 FROZEN_CORE 전에 끝내고(R6), 적응 경로는 가짜 테스트(X2/X7)로만 검증되었다고 라벨합니다.
