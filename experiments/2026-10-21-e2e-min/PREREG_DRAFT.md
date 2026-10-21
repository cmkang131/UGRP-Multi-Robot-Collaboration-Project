# 최소 E2E 사전 등록 초안 (상태: DRAFT, 2026-10-21 경로 변경 반영)

> **DRAFT입니다. 이 문서로는 실행할 수 없습니다.** 실행하려면 [확인 필요] 항목을 모두 채운 FROZEN 버전을 커밋하고, Codex의 독립 검토를 받고, 코드 SHA를 고정해야 합니다.
> sim 전용, seed 1개, n≤6입니다. 사례 수준이며 성공률을 주장하지 않습니다. 다른 실험과 합산하지 않습니다.
> **경로 변경(Claude 결정, 2026-10-21):** E2E-0(teacher 집기·내려놓기)은 폐기했습니다. teacher 경로는 쓰지 않습니다. 첫 E2E는 E2E-1'입니다.

## 1. 과제
두 로봇(r1·r2)이 서쪽 픽업 영역에서 출발합니다. 각자 자기 앞의 작은 큐브 하나를 집습니다(r1 `cyan_1`, r2 `red_1`, role west). 그것을 든 채 넓은 문을 지나 zone B의 배정 슬롯(좌=북쪽 절반, 우=남쪽 절반)에 내려놓습니다.
- 슬롯은 L1-lite의 LLM 배정(`peer_en`, 사적 제약 메커니즘 그대로)으로 정합니다.
- 큐브는 ACT 근거리 접근 범위(0.6–1.1 m, 방위 ±55°) 안에 둡니다. 탐색 단계는 없고, 이것은 과제 정의입니다.
- 장면은 D4 결과로 정합니다. UNIFY_V6이면 v6, 아니면 v5로 재보정한 nav 장면입니다. [확인 필요: D4 결과]
- 운반 자세(hold 규칙)는 운반 자세 렌더 시험 판정으로 정합니다(`CARRY_POSE_RENDER_DRAFT.md`). [확인 필요: 10/21 밤 결과]

## 2. 레벨 정의
| 레벨 (코드 키) | ① 배정 | ② 집기 | ③ 운반 | ④ 내려놓기 | `e2e_substitutions` | 시도 수 | 보고 표기 |
|---|---|---|---|---|---|---|---|
| **E2E-1'** (`E2E-1p`) | LLM | ACT 학생(R8 + v7 시계, deadband 2, C2c 구성) | nav r5 코드 | 규칙 스크립트 `release_open_v1` | `[{"stage":"release","by":"rule_script:release_open_v1"}]` | smoke 1(합산하지 않음) + 본 3 | "혼합 E2E(학생 집기 + nav 운반 + 규칙 내려놓기)" |
| E2E-2 (`E2E-2`) | LLM | ACT 학생 | nav r5 코드 | ACT 학생(release 승자 구성) [확인 필요] | `[]` | 6 | "순수 E2E n/6" |

- **등록 N(고정):** E2E-1' 3, E2E-2 6. smoke는 이 N 밖이며 합산하지 않습니다. `scripts/report_tables.py e2e`(브랜치 `dsh/report-auto`)가 같은 값을 상수로 갖고, 등록 N보다 많은 본 run은 거부합니다.
- E2E-1' smoke 1회는 배관 확인용입니다. 폐기된 E2E-0이 맡던 역할을 대신합니다. 판정과 합산에는 쓰지 않습니다. smoke를 둘지는 Claude가 [확인 필요]합니다.
- `release_open_v1`은 자기 명령만 씁니다(GT, 지도, 상단 카메라 없음).
  1. 정지 `stop_ticks`
  2. 그리퍼 PWM1을 hold 값에서 2000까지 5 tick 동안 선형으로 올리고 3 tick 유지
  3. 바퀴 −0.35, 0.1 s 펄스로 후진. 자기 명령 odometry로 `backoff_m`에 도달할 때까지 합니다.
  4. done
- 2000은 teacher open 값 분포의 중앙값입니다(200/200 에피소드가 2000). 지시서에 적힌 "약 2009"와는 다르며, 데이터 값을 씁니다.

## 3. seed와 고정값
- **seed: [확인 필요]** L1-lite 표에 있는 seed여야 합니다(test 601–606, dev 701–702는 tournament 전용). nav 스폰은 seed와 무관합니다.
- 큐브 xy는 제안값이 r1 (−0.05, −2.375), r2 (−0.05, −2.875)입니다. [확인 필요] 값은 config `cubes`로 동결합니다.
- 코드는 `dsh/e2e-min`의 동결 SHA를 씁니다. [확인 필요] runner 패치는 DeepSeek이 적용하고 검증한 뒤의 SHA입니다.
- ACT는 다음과 같이 고정합니다.
  - source: `dsh/act18-c2c-v7clock` 실행 source `257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8`
  - checkpoint: R8 step-100000 `e1ec6592…8d5a`
  - executor: TE n_action_steps 1, coeff .01
  - done head와 loop overlay는 쓰지 않습니다.
- nav는 r5 상수 그대로입니다(1.5 m stage-2, ±15°, 0.52 m, path cap 1.0 m).
- hold 규칙은 렌더 판정 결과를 따릅니다. 지금 실행할 수 있는 것은 `act_lift_end` 판정, 즉 `last_hold_all_servos_v1`뿐입니다.
- 단계 예산(SIM s)은 grasp 90, settle 3.1, carry 60, release 45입니다. release는 [확인 필요]입니다.
- 루프 전체 예산은 `sim_budget_s` [확인 필요, 제안 200]입니다.
- `release_open_v1`의 `stop_ticks`(제안 3)와 `backoff_m`(제안 0.15)은 [확인 필요]입니다.
- 실행 순서는 E2E-1' smoke → 본 3회 → (내려놓기 승자가 정해지면) E2E-2 6회입니다. 같은 레벨 안에서는 같은 seed를 반복합니다.
- run root는 새로 만듭니다: `runs/e2e-min-<level>-<UTC TS>/`.
- VM은 ACT env와 checkpoint, nav env를 모두 갖춘 L4 한 대입니다. [확인 필요] nav runner admission은 gcp6 전용이고 ACT 자산은 gcp2에 있습니다.
- 실패와 HOST_ERROR도 분모에 넣습니다. HOST_ERROR는 재실행하지 않습니다(단독 ACT·공동 운반 tournament와 같은 규칙). 시작하지 못한 run만 순서대로 이어서 돌립니다.

## 4. 성공 기준 (사전 등록, 결과를 본 뒤 바꾸지 않음)
run 하나가 성공하려면 아래가 **모두** 참이어야 합니다. 계산은 `harness/e2e_min_eval.evaluate`와 `recount_run`이 합니다.
1. 배정 성공: L1-lite 기록이 `success_eligible`이고, 좌·우가 1개씩이며, handoff 슬롯이 배정 결과와 같습니다.
2. GT상 두 큐브의 최종 xy가 각자 배정된 슬롯 zone 안에 있습니다.
3. 낙하 0: 두 로봇 모두 측정되었고 `carry_drop`이 False입니다(§6).
4. 로봇 간 접촉 0: 채널이 available이고 0 pair입니다.
5. 자기 도착 claim 2/2입니다.

측정하지 않은 항목은 0으로 치지 않고 실패로 봅니다.

## 5. 보조 지표 (판정에 쓰지 않음)
- 단계별 도달과 각 시각, FAIL 코드 분포, 총 SIM 시간과 wall 시간
- LLM 호출 수, 토큰, 비용
- 사적 제약 준수, 최소 차체 간격, 로봇-장면 접촉
- ACT grasp done 시각과 C2c 대비 차이(보고만 합니다)
- `release_open_v1` 로그(단계, 후진 거리)
- 대체 단계와 레벨의 일치 여부

## 6. 낙하 지표 동결값 [확인 필요]
- 창은 NAV_CARRY 진입부터 이탈까지입니다.
- `floor`는 큐브 하단 여유 ≤ 0.005 m, `detach`는 큐브와 base의 수평 거리 > 0.35 m, `no_grip`(측정 시)은 최대 손가락 힘 < 0.1 N입니다. 셋 다 5 tick 연속이어야 합니다.
- 임계값은 E2E-1' smoke의 운반 trace로 확인한 뒤 동결합니다.

## 7. 영상 규칙
- 실제 시뮬레이션 녹화만 씁니다.
- 상단 카메라는 평가·기록 전용입니다(`top_camera_control=false`).
- 대체 단계(`release_open_v1`)는 영상 오버레이로 넣지 않고 **보고서와 영상 설명문**에 적습니다.
- 성공 영상만 고르지 않고 전체 n/N과 함께 보고합니다.

## 8. 중단·분기 규칙
- 운반 자세 렌더에서 셋 다 실패하면 `gripper_hold_arm_search_v1`의 낙하 위험 시험을 새로 사전 등록합니다. 그 결과가 나오기 전에는 E2E를 실행하지 않습니다.
- D4 결과가 BRANCH_NAV_V5이면 nav를 v5로 재보정하고(+1일) E2E-2는 11/5 이후로 넘깁니다.
- smoke에서 운반 중 낙하가 나면 hold 방식을 고친 뒤(새 사전 등록) 하루 늦춥니다.
- 한 레벨 안에서 결과를 본 뒤 seed, 임계, 코드를 바꾸지 않습니다.

## 9. 한계 (보고서에 명시)
- E2E-1' 성공은 "학생 집기 + 코드 운반 + 규칙 내려놓기의 통합이 돌아간다"는 증거입니다. 내려놓기를 학생이 해냈다는 증거가 아닙니다.
- r2의 ACT 집기는 학습 분포(r1 단독) 밖일 수 있습니다.
- 협력 운반(L2)은 범위 밖입니다.

## 10. 보고 행 (report_tables.py e2e)
- 행 파일 `e2e-rows.jsonl`은 run root 밖의 새 report 디렉터리에 둡니다. 첫 행은 `{"type":"header","prereg_sha256":"<FROZEN 문서 sha256>"}`입니다.
- run마다 `{"type":"run","level":"E2E-1p"|"E2E-2","seed":<S>,"smoke":true|false,"status":"complete"|"HOST_ERROR","report_path":"<recount_run 출력 JSON>"}` 한 행을 씁니다. report는 `harness.e2e_min_eval.recount_run(run_dir)` 출력(`ugrp.e2e_min.evaluation.v1`)입니다.
- HOST_ERROR run은 report 없이 `status: "HOST_ERROR"`만 적어도 되고, 실패로 세며 단계 도달은 0입니다.
- 명령: `python scripts/report_tables.py e2e --prereg experiments/2026-10-21-e2e-min/PREREG.md --rows <report>/e2e-rows.jsonl --out <report>`.
