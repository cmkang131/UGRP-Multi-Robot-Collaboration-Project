# PREREG_L1LITE: L1-lite 본실험 사전 등록 (이동 + 슬롯 배정, 4통신 조건)

- 상태: **READY_FOR_REVIEW** (Codex 독립 검토 후 FROZEN. 동결 전에는 GPU 본실험을 시작하지 않습니다)
- 작성: Claude (2026-10-21), 브랜치 `dsh/l1lite-alloc`
- 상위 계획: `outputs/reports/claude-arch-parallel-20261019/l1-by-1105-plan.md` §1(설계)·§4(루프), `role-split-20261020.md`
- 구현 기록: 같은 디렉터리 `README.md`. 코드가 원본이며, 이 문서와 코드가 다르면 코드를 기준으로 하고 문서를 고칩니다(결과를 본 뒤에는 고치지 않습니다)
- 분석 스크립트: `scripts/analyze_l1lite.py`, 시험 `tests/test_analyze_l1lite.py`(가짜 데이터)

## 0. 이 문서 이전에 반영한 코드 변경 (검토 대상)

| 커밋 | 내용 | 근거 |
|---|---|---|
| `580e6159f` | test 표 no_comm 충돌 4/6, dev seed 701·702 분리 | role-split §2 |
| `20cdd50ba` | leader_en을 *follower 보고 → leader 배정 → follower ACK* 3라운드로 변경 | Codex 10/20 검토 §2(이전 구조에서는 leader가 follower 제약을 받기 전에 배정) |
| `548b65f15` | queue에 `nav_l1lite_seed_split`(test/dev) 기록·검증 | role-split §3 항목 2 |
| 이 문서 커밋 | `PREREG_L1LITE.md`, `scripts/analyze_l1lite.py`, `tests/test_analyze_l1lite.py` | — |

Codex 검토 요청 범위: 이 문서 + diff `2f62e62eb^..<이 문서 커밋>`(L1-lite 전체).

## 1. 질문 (탐색, 가설 검정 아님)

두 로봇 중 한 로봇만 아는 사적 제약이 있을 때, 통신 채널(없음 / 고정 enum / 자유 영어 대등 / 자유 영어 리더)에 따라 "서로 다른 슬롯 + 제약 준수 + 실제 도착"까지 가는 비율이 어떻게 달라지는지 조건별 n/6으로 *기술*합니다. 통계적 결론은 내지 않습니다(§9).

## 2. 과제와 조건 (요약, 상세는 README §1–§5)

- 두 로봇(r1 북 레인, r2 남 레인)이 서쪽에서 출발해 wide door를 지나 zone B의 left(북 절반)/right(남 절반) 슬롯에 하나씩 도착하고 ARRIVED claim을 냅니다. 집기·운반·내려놓기는 없습니다. claim은 "배달 신호"이고 물리적 성공 주장이 아닙니다.
- 주문서 `v_l1lite`: B-left 1건, B-right 1건, 담당 미지정. 사적 제약은 seed마다 한 로봇의 자기 brief(`own_constraint`)에만 들어갑니다.
- 네 조건 모두 LLM(`gemma-4-31b-it`, temperature 0.2, CoreWeave fp4, `harness/e2e_warp_runtime.py` Planner)이 t=0에 자기 첫 프레임 1장과 자기 brief로 슬롯을 결정하고, 그 뒤 주행은 r5 nav 스택(코드)이 합니다. 조건 간 차이는 채널뿐입니다.

| 조건 | 채널 | 라운드 |
|---|---|---|
| `no_comm` | 메시지 0. 후보는 사전 등록 기본 규칙 슬롯 1개(제약 슬롯, 없으면 자기 레인 슬롯) | 1 |
| `structured` | `{"act": my_constraint\|claim_slot\|ack, "slot": left\|right}` | 2(충돌 시 3) |
| `peer_en` | 자유 영어 `{"text"}` ≤400자 | 2(충돌 시 3) |
| `leader_en` | 자유 영어. leader=`seed % 2`. follower 보고 → leader 배정 → follower ACK | 3 |

- no_comm은 *규칙 baseline*입니다. 후보가 1개라 LLM이 협상할 수 없고, 충돌 seed에서는 구조상 실패합니다. 따라서 no_comm 성공 상한은 **2/6**(603, 606)이며, 이것은 측정 결과가 아니라 설계상 기대값입니다.

## 3. Seed 표 (동결, 코드 `harness/e2ewarp_l1lite.py`가 원본)

`constraint_table_digest()` = `702a680b6fbfbd8bb0004d4faed7ae5edccea38ac965ea20fc9ad0ea0dfdab99` (test + dev 표 전체)

| seed | 구분 | 제약 로봇 | 가능 슬롯 | no_comm 기본 결과 | 충돌 | leader(seed%2) | 제약 보유자 |
|---:|---|---|---|---|---|---|---|
| 601 | test | r1 | right | r1 right / r2 right | 충돌 | r2 | follower |
| 602 | test | r2 | left | r1 left / r2 left | 충돌 | r1 | follower |
| 603 | test | r1 | left | r1 left / r2 right | 분리 | r2 | follower |
| 604 | test | r1 | right | r1 right / r2 right | 충돌 | r1 | leader |
| 605 | test | r2 | left | r1 left / r2 left | 충돌 | r2 | leader |
| 606 | test | r2 | right | r1 left / r2 right | 분리 | r1 | follower |
| 701 | dev | r1 | right | r1 right / r2 right | 충돌 | r2 | follower |
| 702 | dev | r2 | right | r1 left / r2 right | 분리 | r1 | follower |

- test 균형: 제약 로봇 r1 3 / r2 3, 제약 슬롯 left 3 / right 3, no_comm 충돌 4/6.
- 601과 604, 602와 605는 제약 배치가 같습니다(leader 위치만 다름). 서로 다른 제약 배치는 4종입니다.
- dev seed(701·702)는 smoke와 공통 부품 tournament 전용이며 본실험 표에 합산하지 않습니다.

## 4. 주 지표 (run 1개당 성공 1/0)

`harness/e2ewarp_l1lite_eval.evaluate_run`이 raw artifact만으로 계산합니다. 성공은 아래 **전부**입니다.

1. 두 로봇이 서로 다른 슬롯을 골랐다(`distinct_slots`).
2. 사적 제약을 지켰다(제약 로봇의 슬롯 = 제약 슬롯).
3. GT 도착 2/2: 두 로봇의 최종 GT base xy가 *자기가 고른* 슬롯 사각형(zone B 북/남 절반) 안에 있다.
4. ARRIVED claim 2/2(자기 입력 기반 claim).
5. 로봇 간 접촉 0. 단 접촉 채널이 `contacts_available=true`일 때만 통과로 봅니다. 미관측은 0이 아닙니다.
6. allocation이 fatal이 아니고 `success_eligible=true`(이름 있는 오류 0, 메시지 스키마 위반 0).

측정되지 않은 성분(GT 누락, 접촉 채널 없음, 결정 기록 없음)은 실패입니다. 조건별 결과는 **n/6**으로 보고하고, 성분별 실패도 같이 보고합니다.

## 5. 보조 지표 (판정에 쓰지 않음)

| 지표 | 정의 |
|---|---|
| 완료 SIM 시간 | 두 로봇 ARRIVED claim 시각의 최댓값(claim 2/2인 run만), 조건별 성공 run 중앙값 |
| 최소 차체 간격 | base box 지지 반경 기반 하한(m), 조건별 최솟값·중앙값. 최소 중심 거리도 같이 |
| LLM 호출·토큰·비용 | `llm_ledger.json` usage 합. 비용은 고정가 prompt 0.1 / completion 0.34 USD per 1M. usage 누락 행 수를 따로 보고 |
| 발화 수 | 채널로 전달된 메시지 수(run당 평균) |
| 환각 | 거짓 `my_constraint` 주장 + 존재하지 않는 슬롯 언급(어휘 기반, 보수적) |
| 교착 | allocation deadlock 또는 60 SIM s까지 claim 2/2 미달 |

## 6. 설계: 4조건 × test seed 6 = 24 run

- seed당 run 1개, `nworld=1`, pair(r1, r2), SIM 예산 60 s(r5와 동일).
- 실행 순서는 아래 표로 고정합니다. seed 블록(601→606) 안에서 4조건을 Williams 4×4 행(블록 b는 행 b mod 4)으로 섞습니다. 블록 1–4에서 조건별 위치와 직전 조건 쌍이 균형이고, 블록 5–6은 행 0–1을 반복합니다. 표는 `python scripts/analyze_l1lite.py --print-order`의 출력과 같아야 하며, 시험이 이를 확인합니다.
- 1부 = order 1–12(seed 601–603), 2부 = order 13–24(seed 604–606). 밤 하나에 다 못 돌리면 1부와 2부로 나눕니다.

| order | part | block | seed | condition |
|---:|---:|---:|---:|---|
| 1 | 1 | 1 | 601 | no_comm |
| 2 | 1 | 1 | 601 | peer_en |
| 3 | 1 | 1 | 601 | structured |
| 4 | 1 | 1 | 601 | leader_en |
| 5 | 1 | 2 | 602 | peer_en |
| 6 | 1 | 2 | 602 | leader_en |
| 7 | 1 | 2 | 602 | no_comm |
| 8 | 1 | 2 | 602 | structured |
| 9 | 1 | 3 | 603 | leader_en |
| 10 | 1 | 3 | 603 | structured |
| 11 | 1 | 3 | 603 | peer_en |
| 12 | 1 | 3 | 603 | no_comm |
| 13 | 2 | 4 | 604 | structured |
| 14 | 2 | 4 | 604 | no_comm |
| 15 | 2 | 4 | 604 | leader_en |
| 16 | 2 | 4 | 604 | peer_en |
| 17 | 2 | 5 | 605 | no_comm |
| 18 | 2 | 5 | 605 | peer_en |
| 19 | 2 | 5 | 605 | structured |
| 20 | 2 | 5 | 605 | leader_en |
| 21 | 2 | 6 | 606 | peer_en |
| 22 | 2 | 6 | 606 | leader_en |
| 23 | 2 | 6 | 606 | no_comm |
| 24 | 2 | 6 | 606 | structured |

- 예상 비용: r5 2-robot run wall 약 274 s, N1 266–279 s → 24 run 약 1.9 h + 준비·회수(계획 §2 기준 약 3.5 GPU-h, gcp6 L4). LLM은 run당 약 2–6 호출, 약 $0.0003/run(무시 수준). 실측은 실행 보고서에 남깁니다.

## 7. 분모·실패 규칙 (결과 보기 전에 고정)

1. **분모는 계획된 24칸 전부**입니다. 조건별 분모는 항상 6입니다.
2. 실행하지 못한 칸(NOT_RUN), `HOST_ERROR`(VM 선점, CUDA 오류, LLM relay 불통 등 호스트 쪽 실패), 동결 SHA와 다른 `source_sha`(SHA_MISMATCH), 평가 report를 만들 수 없는 run(EVAL_MISSING)은 모두 **실패**로 셉니다. 사유는 따로 보고합니다.
3. `L1LITE_ALLOCATION_FAILED`(LLM 무응답, 형식 오류, 후보 밖 슬롯, leader 보고·배정·ACK 누락)는 실행 실패이자 본실험 실패입니다. `L1LITE_DUPLICATE_SLOT`은 슬롯을 그대로 bind해 주행하고(충돌 결과 측정), 성공은 불가입니다.
4. **재실행으로 칸을 바꾸지 않습니다.** 칸마다 순서상 첫 시도만 셉니다. 추가 시도는 원장에 남기되 표에는 넣지 않고 "추가 시도, 미합산"으로 보고합니다.
5. 실행 순서가 표와 다르면 프로토콜 편차로 기록합니다(성공 판정은 바꾸지 않음). 중단 후 재개는 다음 미실행 order부터 합니다.
6. NOT_RUN + HOST_ERROR가 24칸 중 5칸 이상이면 표는 그대로 보고하되 "실행 불완전"으로 표시하고 조건 비교 문장을 쓰지 않습니다. 다시 돌리려면 새 사전 등록이 필요합니다.
7. **smoke·dev 결과는 합산하지 않습니다.** seed 701·702 run과 `kind=smoke` run은 분석 스크립트가 제외 목록으로만 출력합니다.

## 8. nav 스택 SHA 고정

- 본실험 source SHA = 이 문서를 FROZEN으로 바꾸는 커밋(`dsh/l1lite-alloc`)입니다. 모든 run의 `result.json` `source_sha`가 이 값이어야 합니다(§7-2).
- nav 제어 코드는 r5(`219d08779`) 그대로입니다. 현재 `harness/e2ewarp_selfnav.py` sha256 `7295fba5…3d63`, `harness/e2ewarp_nav_contacts.py` `7bfa561e…6b`로 r5 보고서 값과 같습니다. `nav_gate.py`/`nav_mode.py`/`run_e2e_warp.py`/`e2e_warp_runtime.py`의 차이는 default-off L1-lite opt-in뿐이며, `test_runner_default_path_still_uses_the_fixed_r5_slot_mapping`이 기본 경로를 고정합니다. gate mode는 `v230_r5`만 허용됩니다(`L1LITE_REQUIRES_V230_R5`).
- **N1 승자 규칙**: nav tournament(계획 §4.1)에서 승자가 확정되면(r5 baseline 대비 PASS seed ≥+1, 확인 seed 604/605 재확인 통과) 그 SHA의 nav 변경을 이 브랜치에 넣고, 이 문서를 개정해 Codex 재검토를 받은 뒤 동결합니다. 승자가 없으면 r5로 고정합니다.
- 현재 판단: N1 s601–603은 3/3 PASS로 기록돼 있습니다(STATUS 10/20 11:34 UTC, tar `98641d55`). 그러나 r5 baseline arm과의 비교표와 확인 seed run 기록은 찾지 못했습니다 **[확인 필요: N1에서 돈 mode가 `v230_r5`인지 `v230_n1`인지, baseline arm 결과, 604/605 확인 run 여부]**. r5 자체가 seed 601에서 PASS였으므로 baseline이 3/3이면 어떤 arm도 +1을 넘을 수 없습니다. 위 확인 전까지 **r5로 고정**합니다.

## 9. smoke 게이트와 중단 조건

- smoke: dev seed 701 × 4조건(시간이 되면 702 × 4조건 추가), 동결 SHA 또는 런타임 파일(`harness/e2ewarp_l1lite.py`, `harness/e2ewarp_l1lite_eval.py`, `harness/e2ewarp_nav_gate.py`, `harness/e2ewarp_nav_mode.py`, `harness/e2ewarp_selfnav.py`, `harness/e2ewarp_nav_contacts.py`, `harness/e2e_warp_runtime.py`, `scripts/run_e2e_warp.py`)이 동결 SHA와 바이트 동일한 SHA에서 돌립니다. 아니면 조건당 1 run을 다시 돌립니다. smoke 결과는 합산하지 않습니다.
- **end-to-end 통과 기준(조건마다)**: smoke run 1개 이상이 (a) HOST_ERROR 없이 끝나고, (b) `slot-decisions.json`이 fatal 없이 기록되고, (c) 주행 후 `evaluate_run` report의 측정 성분(`slots_measured`, `gt_measured`, `claims_measured`, `contacts_available`)이 모두 true입니다. 성공 여부는 묻지 않습니다(no_comm 701은 충돌이 정상).
- **중단 조건**: smoke에서 조건 하나라도 end-to-end가 안 되면 본실험을 연기합니다. 원인을 고치고(네 조건 공통 부품만), smoke를 다시 하고, 이 문서를 개정해 재검토를 받습니다. 본실험은 최소 하루 늦춥니다.
- 공통 부품 tournament(계획 §4.2, dev seed 2개 × 4조건)를 돌리면 그 결과도 합산하지 않고, 승자 구성으로 이 문서를 개정한 뒤 동결합니다. 본실험 결과를 본 뒤 코드를 고치는 일은 없습니다.
- N1 조건(계획 §2): N1이 seed 3개 중 2개 미만 PASS였다면 seed 601 하나 반복(N=6)으로 축소해야 하지만, N1이 3/3 PASS로 기록돼 있어 이 축소는 적용하지 않습니다.

## 10. 분석 절차

1. DeepSeek가 run root `runs/e2ewarp-l1lite-<UTC TS>/`에 order별 디렉터리 `o<NN>-<condition>-s<seed>/`를 만들고, 원장 `ledger.json`(스키마 `ugrp.e2ewarp.l1lite_ledger.v1`, `scripts/analyze_l1lite.py` docstring)을 run마다 한 행씩 추가합니다. smoke/dev 행은 `kind`를 `smoke`/`dev`로 씁니다.
2. 분석: `python scripts/analyze_l1lite.py runs/e2ewarp-l1lite-<TS>/ledger.json --out-json analysis.json --out-md analysis.md`. 스크립트는 run 디렉터리에 쓰지 않고, `evaluate_run`으로 raw를 다시 셉니다.
3. 출력: 조건별 n/6과 seed별 O/x, 1차 실패 사유 집계, 보조 지표 표, run별 실패 사유 전체, 제외 행, 프로토콜 편차, 원장 sha256.
4. 독립 재계수: Codex가 raw manifest로 GT 판정을 따로 계산해 스크립트 결과와 대조합니다(요약 성공 플래그를 그대로 세지 않음).

## 11. 해석 한계 (보고서에 그대로 씁니다)

- n=6/조건은 **탐색 수준**입니다. 조건 간 차이에 통계 검정을 하지 않고, "효과가 있다/없다"는 결론을 쓰지 않습니다. n/6과 사유만 기술합니다.
- 배정 문제가 단순해서(슬롯 2개, 제약 1개), 측정하는 통신 효과는 "정보 비대칭 해소"에 한정됩니다. 집기·운반·내려놓기 실패 요인은 들어 있지 않습니다. 보고서 제목과 본문에 *L1-lite(이동·배정 과제, 집기 제외)*로 씁니다.
- no_comm은 규칙 baseline이라 상한 2/6이 설계로 정해져 있습니다. no_comm과 다른 조건의 차이에는 "채널 유무"와 "후보 수(1 대 2)"가 함께 들어 있습니다.
- 스폰 위치가 seed와 무관하게 같을 가능성이 있습니다(N1 기록: seed 601–603 스폰 동일) **[확인 필요: 604–606 스폰]**. 그렇다면 seed 간 차이는 사적 제약 배치(4종)와 LLM 샘플링(temperature 0.2)뿐이고, 601/604·602/605는 제약 배치 반복입니다.
- 주행 성공은 r5 nav 스택에 달려 있습니다. 주행 실패(GT 밖, claim 누락, 접촉)는 조건과 무관한 실행 실패일 수 있으므로 성분별 사유를 같이 보고합니다.
- sim 전용입니다. 실물 주장을 하지 않습니다. claim은 자기 입력 기반 신호이고 물리적 성공이 아닙니다.
- 환각 검사는 어휘 기반이라 놓치는 경우가 있습니다. 최소 차체 간격은 근사 하한입니다.

## 12. 실행 명령 (DeepSeek용, 동결 후에만)

환경변수(모든 run 공통):

```
E2EWARP_NAV_GATE_MODE=v230_r5
E2EWARP_NAV_ARRIVAL=odom_projection
E2EWARP_NAV_L1LITE=on_v1
```

run마다(order 표 순서대로, `<C>`=condition, `<S>`=seed, `<NN>`=order 두 자리):

```
python scripts/run_e2e_warp.py --mode nav --prepare --nworld 1 --seed <S> --condition <C> \
  --arrival-odom-projection --output runs/e2ewarp-l1lite-<TS>/o<NN>-<C>-s<S> ...
python scripts/run_e2e_warp.py --mode nav --execute --queue runs/e2ewarp-l1lite-<TS>/o<NN>-<C>-s<S>/queue.json \
  --expected-source-sha <FROZEN_SHA> ...
```

`...`(calibration 경로, `--host-receipt`, `--components`, `--relay-url`)는 r5 실행과 같은 값을 씁니다 **[확인 필요: r5 run의 정확한 prepare/execute 인자를 DeepSeek 실행 보고서에서 그대로 복사]**. prepared queue에 `nav_l1lite=on_v1`, `nav_l1lite_constraints_sha256=702a680b…ab99`, `nav_l1lite_seed_split=test`, `nav_l1lite_slot_assignment=llm_decision`이 있고 `nav_slots`가 없어야 합니다.

## 13. Codex 검토 요청 항목

1. 주 지표 6성분과 "미측정 = 실패" 처리가 evaluator 코드와 일치하는지.
2. leader_en 3라운드 변경(`20cdd50ba`)이 10/20 §2 지적을 해소하는지, 다른 조건과 비교해 정보 조건이 공정한지(leader_en만 follower 발화 1회가 필수).
3. no_comm 후보 1개 규칙 baseline을 그대로 둘지(대안: 후보 2개 + 기본 규칙 검증. 이 경우 baseline이 LLM 추첨이 됨).
4. 분모 규칙(§7)과 분석 스크립트 동작이 같은지(`tests/test_analyze_l1lite.py`).
5. 실행 순서 표와 1부·2부 분할.
6. §8 nav SHA 규칙과 N1 [확인 필요] 항목 처리.

## 14. 동결 절차

1. Codex 검토 → 지적 반영 커밋 → 재검토 OK.
2. 상태를 FROZEN으로 바꾸고, 그 커밋 SHA와 이 문서 sha256을 STATUS.md에 기록한 뒤 push합니다.
3. smoke(§9) 통과 확인 → 본실험 1부 → 2부 → 분석(§10) → Codex 독립 재계수.
