# 최소 E2E 사전 등록 초안 (상태: DRAFT)

> **DRAFT입니다. 이 문서로는 실행할 수 없습니다.** 실행하려면 [확인 필요] 항목을 모두 채운 FROZEN 버전을 커밋하고, Codex의 독립 검토를 받고, 코드 SHA를 고정해야 합니다.
> sim 전용, seed 1개, n≤6입니다. 사례 수준이며 성공률을 주장하지 않습니다. 다른 실험과 합산하지 않습니다.

## 1. 과제
두 로봇(r1·r2)이 서쪽 픽업 영역에서 출발합니다. 각자 자기 앞의 작은 큐브(role west 박스) 하나를 집고, 그것을 든 채 넓은 문(door_wide)을 지나 zone B의 배정 슬롯에 내려놓습니다. 슬롯은 좌=북쪽 절반, 우=남쪽 절반입니다.
- 슬롯은 L1-lite의 LLM 배정(`peer_en`, 사적 제약 메커니즘 그대로)으로 정합니다.
- 큐브는 ACT 근거리 접근 범위(0.6–1.1 m, 방위 ±55°) 안에 두므로 탐색 단계가 없습니다. 이것은 과제 정의입니다.
- 장면은 D4 장면 적합성 시험 결과로 정합니다. UNIFY_V6이면 v6, 아니면 nav를 v5로 재보정한 장면입니다. [확인 필요: D4 결과]

## 2. 레벨 정의
| 레벨 | ① 배정 | ② 집기 | ③ 운반(nav r5) | ④ 내려놓기 | `e2e_substitutions` | 시도 수 | 보고 표기 |
|---|---|---|---|---|---|---|---|
| E2E-0 | LLM | teacher | nav 코드 | teacher | `["grasp:teacher","release:teacher"]` | 1 | "배관 확인, 연구 결과 아님" |
| E2E-1 | LLM | ACT(R8 + v7 시계, deadband 2) | nav 코드 | teacher | `["release:teacher"]` | 3 | "혼합 E2E(내려놓기 teacher)" |
| E2E-2 | LLM | ACT | nav 코드 | ACT(release 승자 구성) [확인 필요] | `[]` | 6 | "순수 E2E n/6" |

## 3. seed와 고정값
- **seed: [확인 필요]** 아래 두 조건을 동시에 만족하는 seed 1개입니다.
  - (a) L1-lite 표에 있는 seed입니다. test는 601–606, dev는 701–702이고 dev는 tournament 전용입니다 [`harness/e2ewarp_l1lite.py:96-110`]. nav 스폰은 seed와 무관합니다.
  - (b) 두 큐브 위치가 각 로봇 레인 스폰(−0.8982, −2.375/−2.875, yaw 0)에서 본 ACT 시작 분포 안에 있습니다.
  - seed와 큐브 좌표(제안 r1 (−0.05, −2.375), r2 (−0.05, −2.875)), 큐브 kind는 world builder 구현 뒤에 동결합니다.
- 코드는 `dsh/e2e-min`의 동결 SHA를 씁니다. [확인 필요]
- 체크포인트는 R8 step-100000(`e1ec6592…8d5a`)입니다.
- nav는 r5 상수 그대로입니다(1.5 m stage-2, ±15°, 0.52 m, path cap 1.0 m).
- hold 규칙은 `last_hold_all_servos_v1`입니다. [확인 필요: §7 위험 1]
- 단계 예산(SIM s)은 grasp 90, settle 3.1, carry 60, release 45입니다. release는 [확인 필요]입니다.
- 실행 순서는 E2E-0 1회 → (통과 시) E2E-1 3회 → E2E-2 6회입니다. 같은 레벨 안에서는 같은 seed를 반복합니다.
- run root는 새로 만듭니다: `runs/e2e-min-<level>-<UTC TS>/`. GPU는 L4 gcp6만 씁니다.
- 실패와 HOST_ERROR도 분모에 넣습니다. smoke run은 합산하지 않습니다.

## 4. 성공 기준 (사전 등록, 결과를 본 뒤 바꾸지 않음)
run 하나가 성공하려면 아래가 **모두** 참이어야 합니다. 계산은 `harness/e2e_min_eval.evaluate`와 `recount_run`이 합니다.
1. 배정 성공: L1-lite 기록이 `success_eligible`이고, 좌·우가 1개씩이며, handoff 슬롯이 배정 결과와 같습니다.
2. GT상 두 큐브의 최종 xy가 각자 배정된 슬롯 zone 안에 있습니다.
3. 낙하 0: 두 로봇 모두 측정되었고 `carry_drop`이 False입니다(§6).
4. 로봇 간 접촉 0: MJWarp 채널이 available이고 0 pair입니다.
5. 자기 도착 claim 2/2입니다.

측정하지 않은 항목은 0으로 치지 않습니다. 하나라도 측정이 없으면 실패입니다.

## 5. 보조 지표 (판정에 쓰지 않음)
- 단계별 도달(allocate/grasp/carry/release/done)과 각 도달 시각, FAIL 코드 분포
- 총 SIM 시간과 wall 시간
- LLM 호출 수, 토큰, 비용(CoreWeave fp4 단가)
- 사적 제약 준수 여부, 최소 차체 간격, 로봇-장면 접촉
- 대체 단계 목록과 레벨의 일치 여부(`substitutions_match_level`)

## 6. 낙하 지표 동결값 [확인 필요]
- 창은 NAV_CARRY 진입부터 이탈까지입니다.
- `floor`는 큐브 하단 여유 ≤ 0.005 m, `detach`는 큐브와 base의 수평 거리 > 0.35 m, `no_grip`(측정 시)은 최대 손가락 힘 < 0.1 N입니다. 셋 다 5 tick 연속이어야 합니다.
- 임계값은 E2E-0 전에 teacher 운반 trace로 확인한 뒤 동결합니다.

## 7. 영상 규칙
- 실제 시뮬레이션 녹화만 씁니다. 합성, 편집으로 만든 장면, 재연은 쓰지 않습니다.
- 상단 카메라(`cctv_top`, `cctv_top_east`)는 **평가·기록 전용**이며 제어 입력이 아닙니다(`top_camera_control=false`).
- 대체 단계는 영상 오버레이 텍스트로 넣지 않습니다. **보고서와 영상 설명문**에 `e2e_substitutions`를 적습니다.
- 성공 영상만 고르지 않고, 실패를 포함한 전체 n/N을 함께 보고합니다.

## 8. 중단·분기 규칙
- E2E-0에서 운반 중 낙하가 나면 hold 방식을 고친 뒤(새 사전 등록) 하루 늦춥니다.
- D4 결과가 BRANCH_NAV_V5이면 nav를 v5로 재보정하고(+1일) E2E-2는 11/5 이후로 넘깁니다.
- 한 레벨 안에서 결과를 본 뒤 seed, 임계, 코드를 바꾸지 않습니다. 바꾸려면 새 라운드와 새 사전 등록이 필요합니다.

## 9. 한계 (보고서에 명시)
혼합 E2E 성공은 "통합이 돌아간다"는 증거일 뿐, 각 단계를 학생 정책이 해냈다는 증거가 아닙니다. 협력 운반(L2)은 범위 밖입니다.
