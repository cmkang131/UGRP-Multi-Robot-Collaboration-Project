# L1-lite slot allocation 구현 기록 (2026-10-20, CPU only)

상위 계획: `outputs/reports/claude-arch-parallel-20261019/l1-by-1105-plan.md` §1·§3.
상태: **구현 + CPU 단위 테스트만**. 실행·smoke·본실험·prereg 동결 없음(prereg는 Claude가 10/22 작성).
GPU/VM/gcp start 없음, 실제 LLM API 호출 없음(테스트는 stub), 시뮬레이션 import 없음.

## 0. 범위

- 과제: 두 로봇이 서쪽에서 wide door를 지나 zone B의 두 슬롯(left=north half,
  right=south half)에 하나씩 도착. 집기·운반·내려놓기 제외. 도착 claim이 "배달" 신호이며
  물리적 성공 주장이 아니다.
- 변경 파일 (상세는 §9):
  - `harness/e2ewarp_l1lite.py` (신규): 주문서 v_l1lite, seed별 사적 제약, 4조건 채널 스키마,
    LLM 할당 프로토콜, fail-closed 오류, 큐 binding.
  - `harness/e2ewarp_l1lite_eval.py` (신규): 주 지표·보조 지표 evaluator(순수 함수 + raw recount).
  - `tests/test_e2ewarp_l1lite.py` (신규): 50개 단위 테스트.
  - `harness/e2ewarp_nav_gate.py`: `E2EWARP_NAV_L1LITE=on_v1`일 때 `SLOT_BY_ROBOT` 대신
    실행 시 결정값을 binding. 기본 off에서 r5 동작 불변.
  - `harness/e2e_warp_runtime.py`: `Channels(..., message_schema='l1lite')` opt-in(기본 legacy).
  - `harness/e2ewarp_nav_mode.py`: `select(..., reason=)` 선택적 인자(기본 문구 불변).
  - `scripts/run_e2e_warp.py`: L1-lite opt-in에서 첫 자기 프레임으로 할당 → slot binding →
    `NavRobot` 생성 전에 주문 선택 → 코드 주행.
  - `scripts/run_ci_tests.py`: 새 테스트 모듈 등록(항목 추가만).

## 1. 주문서 v_l1lite

```
B-left  1건, required_robots=1, assigned_robot=None
B-right 1건, required_robots=1, assigned_robot=None
```

`harness.e2ewarp_l1lite.ORDER_SHEET`가 원본이며 `order_sheet()`는 깊은 복사본을 준다.
담당 로봇은 주문서에 쓰지 않는다. 할당은 LLM 결정 → `E2EWARP_NAV_L1LITE=on_v1`에서
`bind_slot_decisions()`로 고정 매핑을 대체한다.

## 2. Seed별 사적 제약 표 (결정론적, 코드가 원본)

`SEED_TABLE` (code -> documentation, 역방향 편집 금지):

| seed | 제약 받는 로봇 | 가능 슬롯 | no_comm 기본 결과 | 충돌? |
|---:|---|---|---|---|
| 601 | r1 | right | r1 right / r2 right | **충돌** |
| 602 | r1 | left  | r1 left / r2 right | 분리 |
| 603 | r2 | left  | r1 left / r2 left | **충돌** |
| 604 | r2 | right | r1 left / r2 right | 분리 |
| 605 | r1 | left  | r1 left / r2 right | 분리 |
| 606 | r2 | right | r1 left / r2 right | 분리 |

- `constraint_table_digest()` = **`252d0ebc867b0a5acdd2139e69a45c384f0466c2f88ec71574684e365d187e88`**
  (sha256; queue의 `nav_l1lite_constraints_sha256`에 기록. 표 자체는 로봇 입력에 쓰지 않는다).
- 균형: r1 3 / r2 3, 제약 슬롯 left 3 / right 3.
- no_comm 기본 규칙: "제약이 있으면 그 슬롯, 없으면 자기 스폰 레인 슬롯" (r1 north lane→left,
  r2 south lane→right). 이 규칙에서 충돌은 "제약 로봇의 슬롯 == 상대의 스폰 레인 슬롯"일 때만
  생긴다. r1 3/r2 3·left 3/right 3을 동시에 만족하면 충돌 수는 **짝수(0/2/4)** 이며,
  표는 균형을 위해 **2/6 충돌**(601, 603)을 택한다. 이 성질은 `table_violations()`가 import
  시점에 강제한다. (prereg에서 3/6 충돌을 원하면 left/right 제약을 4/2로 기울여야 한다.)
- 사적 제약은 해당 로봇의 `robot_brief()`의 `own_constraint`에만 쓰인다. 상대 brief에는
  `own_constraint: null`이고, 내비게이션 어댑터 allowlist(`nav_static`)는 이 키를 거부한다.

## 3. 네 조건 채널 (조건 이름은 기존 runner와 동일)

| 조건 | 메시지 | 본문 스키마 | 비고 |
|---|---|---|---|
| `no_comm` | 0 (전송 시도도 drop) | — | 후보는 기본 규칙 슬롯 1개뿐, 벗어나면 `L1LITE_INVALID_SLOT` |
| `structured` | 고정 enum | `{"act": "my_constraint"\|"claim_slot"\|"ack", "slot": "left"\|"right"}` | 자유 텍스트 거부 |
| `peer_en` | 자유 영어 | `{"text": "..."}` (≤400자) | 한국어는 전달하되 언어 slip으로 기록(차단 아님) |
| `leader_en` | 자유 영어 | `{"text": "..."}` | leader=`seed % 2`, leader가 두 슬롯 배정, follower는 `ack_assignment`만 |

- 네 조건 모두 LLM이 슬롯을 결정한다. no_comm만 결정 후보가 기본 규칙 1개로 제한된다
  (사전 등록 baseline; LLM은 여전히 그 후보를 선택해야 하고, 없거나 다르면 named error).
- `structured`/`peer_en`: 라운드 1(claim) + 라운드 2(응답)를 **항상** 수행하고, 2라운드에서도
  두 선택이 같으면 라운드 3까지 간다. 3라운드에도 같으면 `L1LITE_DUPLICATE_SLOT`.
- `leader_en`: 라운드 1 leader 배정(메시지 필수) → 라운드 2 follower ack(메시지 필수).
- 같은 라운드의 전송은 그 라운드의 상대 입력에 들어가지 않는다(라운드 시작 시 inbox 스냅샷).

## 4. 결정 → 주행 연결 (default off 보장)

1. `scripts/run_e2e_warp.py`가 world scene을 만들고 transport를 초기화한다.
2. `E2EWARP_NAV_L1LITE=on_v1`이면 각 로봇의 **자기 첫 프레임 1장**과 자기 brief(주문서+사적
   제약)로 할당 LLM을 호출한다(`Planner` 재사용: CoreWeave fp4 고정, 요청/응답 archive,
   usage 원장). robotics 호출은 로봇당 1회 이상(조건별 라운드 수).
3. `slot-decisions.json` 기록 → `bind_slot_decisions()` → 로봇별 static `slots={robot: decided}`
   (상대 slot은 쓰지 않음) → `NavRobot` 생성.
4. LLM 결정은 주문 선택으로 코드에 전달되고(`L1-lite slot allocation (LLM) selected the order;
   code drives`), 그 시점부터 주행은 `SelfCentricNavigation`(r5 스택)이 한다. tick-0 추가
   판단 호출은 없다(결정 1회). 그래서 조건 간 차이는 채널뿐이다.
5. 기본(환경변수 없음): 위 분기를 타지 않고 기존 r5 경로 그대로(고정 `SLOT_BY_ROBOT`,
   `nav_slots` queue marker byte-identical, legacy 채널 스키마, 기존 `select` 문구).
   `test_runner_default_path_still_uses_the_fixed_r5_slot_mapping`이 이 경로를 모의 실행으로 고정한다.

Queue marker(opt-in에서만): `nav_l1lite=on_v1`, `nav_l1lite_order_sheet=v_l1lite`,
`nav_l1lite_constraints_sha256=<digest>`, `nav_l1lite_slot_assignment=llm_decision`.
`nav_l1lite`가 있으면 `nav_slots`는 금지(런타임 결정), gate mode는 `v230_r5`만, nworld=1·pair만.

## 5. Fail-closed 오류 (모두 이름 있는 코드)

| 코드 | 의미 | run 결과 |
|---|---|---|
| `L1LITE_NO_DECISION` | LLM 응답 없음(Planner None) | `L1LITE_ALLOCATION_FAILED`, 주행 없음 |
| `L1LITE_INVALID_DECISION` | 응답 형식 불일치(`act`/`message` 외 키 등) | 위와 같음 |
| `L1LITE_INVALID_SLOT` | 후보에 없는 슬롯/act | 위와 같음 |
| `L1LITE_DUPLICATE_SLOT` | 두 로봇 같은 슬롯(no_comm 충돌, 협상 실패) | slot은 bind되어 주행(충돌 측정), `success_eligible=false` → evaluator 성공 불가 |
| `L1LITE_LEADER_UNASSIGNED` | leader 배정 메시지 없음/무효 | 주행 없음 |
| `L1LITE_LEADER_ACK_MISSING` | follower ack 결정/메시지 없음 | 주행 없음 |
| `L1LITE_MESSAGE_INVALID` | 채널 스키마 위반 메시지(전달 안 됨) | 메시지 drop 기록, `success_eligible=false` |
| `L1LITE_SEED_UNKNOWN` | 표에 없는 seed | 즉시 오류 |
| `L1LITE_ORDER_CANDIDATE_MISSING` | 결정 슬롯의 주문 후보 없음 | 주행 없음 |
| `NAV_L1LITE_DECISION_UNBOUND` | env on인데 binding 없음 | navigation factory/큐 단계에서 거부 |
| `NAV_L1LITE_SLOTS_RUNTIME_DECISION` | L1-lite인데 `nav_slots`가 준비됨 | 거부 |
| `NAV_L1LITE_MODE_UNKNOWN` | env 값이 `on_v1` 아님 | 거부 |

`L1LITE_ALLOCATION_FAILED`도 `E2E_success=false`, `research_result=false`이고
`rejection_table.json`에 코드가 남는다. 어떤 경로도 성공을 주장할 수 없다.

## 6. Evaluator (eval-only)

주 지표 `success` = 아래 전부:

1. 두 로봇 GT base xy가 **자기 chosen slot zone** 안 (zone B north/south half).
2. own-input ARRIVED claim 2/2.
3. 두 슬롯이 서로 다름.
4. 사적 제약 준수(제약 없음 또는 chosen==constraint).
5. 로봇-로봇 접촉 0 (`contacts_available=true`일 때만; 미관측은 0이 아님).
6. allocation이 fatal 아님 + `success_eligible=true`.

미측정은 실패로 처리한다(누락 GT·제약 map·접촉 채널·allocation record).

보조: `completion_sim_s`, `min_center_distance_m`, `min_body_gap_m`(회전 base box support
radius 하한), LLM `calls/prompt_tokens/completion_tokens/cost_usd`(CoreWeave fp4 고정가
0.1/0.34 USD per 1M, 2026-10-16), `utterances`, `hallucination`
(거짓 `my_constraint` + 없는 슬롯 언급), `deadlock_60s`
(할당 deadlock 또는 60 SIM s까지 claim 2/2 미달).

`evaluate_run(run_dir)`은 raw artifact만 읽고(`slot-decisions.json`,
`world-00/eval-geometry.json`, `evaluation-state.npz`, `nav-events.json`,
`contact-ledger.json`, `llm_ledger.json`, `messages.json`, `result.json`) 입력 sha256을
report에 남긴다. run 상태를 쓰지 않는다.

## 7. 테스트

```
/home/ubuntu/.venv-ugrp/bin/python -m pytest -q tests/test_e2ewarp_l1lite.py   # 50 passed
/home/ubuntu/.venv-ugrp/bin/python -m pytest -q tests/test_e2e_warp.py \
  tests/test_e2ewarp_nav_gate.py tests/test_e2ewarp_nav_mode.py \
  tests/test_e2ewarp_nav_v230_r2.py tests/test_e2ewarp_nav_v230_r3.py \
  tests/test_e2ewarp_nav_v230_r4.py tests/test_e2ewarp_nav_v230_r5.py \
  tests/test_e2ewarp_selfnav.py                                                # 193 passed
```

테스트 축: 주문서/표 균형·digest, 사적 제약 비누출(brief + adapter allowlist), no_comm 메시지 0,
no_comm 충돌 named error, 결정 실패 fail-closed, 채널 격리(4조건), 라운드 inbox 격리,
leader 배정/ack, evaluator 성공·각 실패 성분·aux·60s deadlock·환각, raw recount,
기본 off r5 고정 매핑, L1-lite queue marker 검증, 모의 runner(할당→binding→주행, 실패 경로).

## 8. Prereg(Claude 10/22)로 넘기는 미확정/확인 필요

- 24 run 설계(4조건 × 6 seed), 조건×seed 교차 순서, run root: 계획 §1 그대로. 실행 없음.
- seed 표: 위 601–606. 3/6 충돌을 원하면 균형(3/3, 3/3)을 깨야 함(§2).
- 할당 호출은 로봇 자기 첫 프레임 1장을 포함한다(t=0, 주행 전 1회). 조건별 라운드 수:
  no_comm 1, structured/peer_en 2(+충돌 시 3), leader_en 2 → 로봇당 1–3 호출.
- `nworld=1`만 허용(결정 binding이 run 전역). seed당 run 1개.
- `no_comm`은 후보를 기본 규칙 1개로 제한했다(LLM은 그 후보를 선택·확인). prereg에서
  "두 후보 + 기본 규칙 검증"으로 바꿀 수 있으나, 그러면 조건 baseline이 LLM 추첨이 된다.
- 실패·HOST_ERROR도 분모; `L1LITE_ALLOCATION_FAILED`는 실행 실패로 기록.
- calibration·scene·r5 상수는 r5 그대로이며 새 상수 없음(1.5 m stage2, 0.52 m claim 등 불변).
- 아직 실행 전이므로 **어떤 n/N도 주장하지 않는다**(테스트 통과 수만 보고).

## 9. 검증 범위 / 한계

- CPU 단위 테스트만. MJWarp·물리·렌더·LLM API·GCP 접촉 없음.
- 모의 runner 테스트는 물리/transport/Planner를 대체하므로 실제 GPU 배선을 검증하지 않는다.
- evaluator의 min body gap은 support-radius 하한(근사)이며 접촉 판정은 contact ledger를 쓴다.
- hallucination 검사는 어휘 기반(보수적)이며 의미 판정이 아니다.
