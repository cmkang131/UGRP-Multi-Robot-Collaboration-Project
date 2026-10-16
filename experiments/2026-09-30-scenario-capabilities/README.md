# P09 — 정식 6시나리오 실행 능력과 후속 작업

2026-09-30 정적 감사. **C6/C7 전체 파일럿은 아직 준비되지 않았다.** v2의 정적 필요조건은 s1–s5 `feasible`, s6 `conditional`이지만, 실행기는 cyan 단독 및 제한된 r1/r2 빔 운반만 받는다. 다색·can·tile·heavy_crate, 혼합 재고/identity, r3 파트너, 새 통로, 회전/순서·사건 복구를 각각 닫아야 한다.

- 요청 감사 기준: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.
- 배정 checkout/branch: `/Users/changmin/projects/ugrp-wt/e2e-p09-caps`, `codex/scenario-capabilities`; 시작 HEAD/main `d17ca4345affef8cf027e121cf1f3197b36c23e0`. 그 사이 변경은 별도 절차 조사 기록이며 이 감사의 입력 코드·지도·시나리오는 기준 SHA와 같다. 파일별 해시는 [manifest](data/manifest.json)의 `input_sha256`, 함수 위치는 `symbols`를 따른다.
- 후속: [READINESS S01/S04/S13, C6/C7](https://github.com/kcm0127-dotcom/ugrp/blob/codex/e2e-readiness/experiments/2026-09-30-e2e-readiness/READINESS.md), [#298](https://github.com/kcm0127-dotcom/ugrp/pull/298).
- **문서와 정적 검사만 변경했다.** 기존 s1–s6·지도·controller·bundle/workflow registry는 바꾸지 않는다. **로컬 정적 감사**의 물리/SIM/렌더/모델 호출 0회, 학생 trial 0회. 초기 자동 CI를 범위 이탈로 해석해 취소한 것은 잘못됐으며 [취소 이력과 정정](CI_INCIDENT.md)에 원본 증거를 보존한다. 원격까지 모델0으로 주장하지 않는다. raw 삭제·Drive·병합 없음. 작은 dev cyan+봉 시험은 C6/C7의 대체가 아니다.

**정상 GitHub CI는 허용되며 필수 검증이다. workflow를 취소하지 않는다. 커밋 지시어로 CI를 건너뛰지 않는다.** B3 지침 정정과 B4의 T02 범위 분리는 [수정·검증 기록](REVIEW_FIXES.md)을 따른다. T02는 P02 다음의 별도 확장 과제이며, cyan 1개 + 봉 1개인 #307의 완료 조건에 소급 추가하지 않는다.

**입력 경계:** 이 폴더의 원본 배치·숨은 사건·정적 해법은 전부 평가 전용이다. robot 프롬프트/제어기에 전달하지 않는다.

## 1. 원본 추출과 시나리오별 차이

전체 23개 주문행·26개 물건의 종류/개수/identity/ID/역할/초기 자세/정류장/목적지/사건은 [REQUIREMENTS.md](REQUIREMENTS.md)와 [inventory.json](data/inventory.json)에 원본 경로·JSON pointer와 함께 추출했다. 다음은 코드 거절 조건과의 연결이다. `R*`는 §3, `T*`는 [TASKS.md](TASKS.md)의 한 PR 단위 작업이다.

| 시나리오 | 주문행/물건 | 요구 | 실행 차단 및 후속 | 최종 학생/물리 |
|---|---:|---|---|---|
| s1 normal mixed | 6/7 | cyan×2→A, red→B, can→C, tile→B, beam→A, green→C; 빔 남북 자세 | R1 혼합/identity, R2 비cyan, R4 초기 빔 자세; T01–T08 | 미측정 |
| s2 unmapped blockage | 3/4 | cyan×2→A, green→C, heavy_crate→B; 45초 좁은 문 막힘→넓은 문 | R0 지도, R1 혼합, R2 green, R3 crate, R5 문 선택; T01–T03/T06/T07/T09/T13 | 미측정 |
| s3 late rendezvous | 4/4 | beam→A, cyan/red→B, tile→C; 12초부터 r3 40초 정지 | R1/R2/R3/R4; r3를 짝으로 쓸 수 없어 지연-집결 상호작용도 제한; T01–T03/T05/T07/T08/T12 | 미측정 |
| s4 narrow door standoff | 4/4 | cyan/red/green→A/B/C, beam→A; 0.5 m 복도·bay, 적재 출하와 복귀의 양방향 사용 | R0/R1/R2/R4/R5; `kind=door` 없는 지도에서 `next()` 실패 가능; T01–T03/T07/T08/T10 | 미측정 |
| s5 moved/dropped item | 3/4 | 특정 cyan_1→A, red×2→B, can→C; 30초 이동, 62.5초 낙하 | R1 solo can 재고 경로, R2 red/can, R6 특정 개체/재탐색·낙하; T02–T04/T13 | 미측정 |
| s6 novel relation | 3/3 | 특정 can_1→C, 특정 beam_1→A, cyan→B; 빔 약90° 회전→한쪽 후퇴→서쪽 can 접근이라는 설계 | R0/R1/R2/R3/R4/R7; T01/T02/T04/T07–T09/T11. 기하가 순서를 강제한다는 주장도 미확정 | 미측정 |

공통 기본 배치는 `arena_default`다. 후보 base는 x=−0.85, y=−2.25/−0.85/0.55, yaw=0이고, `sim/zone_arena.py::episode`(329–361)는 화물 sampling 후 로봇 순서를 shuffle한다. 시나리오만으로 r1/r2/r3의 정확한 spawn 대응을 고정하지 않는다. 역할/leader 순환과 물리 spawn 할당도 별개다. v2 seed는 601–653의 기존 개발 묶음이며 새 확증 seed를 발급하지 않았다.

## 2. 정적 재검사 결과와 한계

[기존 evaluator](../../harness/zone_scenario_feasibility.py#L830)에 `maps_dir=maps_dir_for(scenario['map_id'])`를 매번 전달했다. 기본 `maps/zones`만 지정하는 CLI 일괄 호출로 새 두 지도 파일을 찾았다고 가정하지 않았다. 입력 카탈로그 해시와 실제 파일 해시를 대조했다. [재현·검증](VERIFICATION.md), [원시 정적 결과](data/feasibility.json), [검사 코드](audit.py).

| 시나리오 | r=.17/.21 m 단독 원판 도달성 | 전체 편대+화물, 초기 타 물건 포함 | 같은 경로 역방향 sweep | 사건 검사 | 학생/물리 |
|---|---|---|---|---|---|
| s1 | 두 반지름 모두 PASS | 7/7 feasible | 7/7 true | 사건 없음 | 미측정 |
| s2 | 모두 PASS | 4/4 feasible | 4/4 true | 막힘 뒤 4/4 경로 유지 | 미측정 |
| s3 | 모두 PASS | 4/4 feasible | 4/4 true | robot_hold: 정적 geometry 미검사 | 미측정 |
| s4 | 모두 PASS | 4/4 feasible | 4/4 true | 사건 없음; 두 편대 교행/bay 양보 미검사 | 미측정 |
| s5 | 모두 PASS | 4/4 feasible | 4/4 true | 이동 뒤 4/4 유지, drop 미검사 | 미측정 |
| s6 | 모두 PASS | 3/3 feasible, **파지 자리 warning** | 3/3 true | 시간 사건 없음; 순서 강제 아님 | 미측정 |

`evaluate`의 초기 타 물건 포함 검사는 `blocking[*].verdict`다. 보존한 `routes`의 자세열·길이와 역방향 sweep은 **벽만 있는 운반 경로**다. 별도 `event_routes`는 기존 evaluator와 같이 사건 하나의 장애물/이동만 적용한다. 타 물건 초기 배치+여러 사건+동료 교통을 동시에 실행한 궤적이 아니다.

검사 격자는 0.05 m, yaw 12단계(+원본 초기 yaw), 계획 여유는 0.03 m다. 전체 편대는 `zone_team_footprint`의 화물+모든 운반자 섀시/팔로 계산했다. 단독 원판 .17/.21 m와 구별한다. 원본 시작→격자 시작 연결 sweep도 26/26 true를 확인했다. 이 발자국은 기존 2-D 카탈로그 모델이다. 최종 로봇 v3, 0.4 m 벽과 팔의 3-D 접촉·하중/마찰·손목 시야까지 검증한 것은 아니다.

역방향 true는 **같은 장애물, 같은 편대/heading으로 자세열을 역순 검사한 값**이다. 독립적인 동쪽 spawn에서의 접근, 내려놓은 뒤 빈 로봇 복귀, 다른 편대와 동시 교행, bay 진입/대피/재출발, 실제 후진 제어는 미측정이다. 모든 원본 주문은 서쪽 pickup→동쪽 목적지이며, s4의 양방향 요구에는 후속 복귀/재작업도 포함된다.

`passages_used`는 `crossing_zones()`의 **확장된 문 입구 영역** 방문 목록이다. s2 막힘 후 cyan의 이 필드에는 `door_narrow`도 남지만, 중심선 교차는 `door_wide`뿐이다. 보조 `passage_centre_crossings`/`reverse_passage_centre_crossings`와 전체 sweep을 같이 읽는다. 목록에 있다는 것만으로 해당 문 통과를 주장하지 않는다.

### s6: 순서 관계의 설계는 아직 닫히지 않았다

- can base 정류장은 `(1.295, −0.85, 0)`이다. 반지름 .17 m의 외접 다각형 기준 최소 여유는 **0.00167 m**, `station_clearance_tight`; `station_not_standable`은 아니다. 초기 타 물건을 넣은 can 운반 경로도 `feasible`이고, `clearing_needs_precedence`는 발생하지 않았다.
- 원본 주석의 섀시 폭 .39 m와 [기존 발자국](../../harness/zone_team_footprint.py#L25)의 x=[−.10,.12], y≈±.105 모델을 혼동하지 않는다. 자리에서 설 수 있다는 검사와 그 자리까지 주행할 수 있다는 검사는 다르다. **충돌 없는 spawn→파지 자리 경로 길이는 미산정**이다.
- [cargo catalogue](../../sim/zone_cargo.py#L128)는 can의 `any` 접근을 허용한다. 원본의 “서쪽에서만”은 현재 관례/설계 의도이며 모든 방향을 막는 물리 제약의 증명이 아니다.
- 중심 기준 경로의 yaw 변화(이번 beam 경로는 누적180°)는 원본이 의도한 **end_pos 쪽 약90° 회전→후퇴→can 추출**의 실행 가능성/필요성 증명이 아니다. pivot 위치·후퇴 거리·관측 가능한 완료 조건·정형 메시지 비교 범위를 T11에서 먼저 정의한다. **원본 배치를 여기서 보정하지 않는다.**

## 3. 지원 등급과 정확한 거절 지점

등급은 “이미 지원 / 정적 어댑터 부족 / 하위 제어·인식 필요 / 물리 미확인 / 설계 범위 미확정”이다. ‘이미 지원’은 명시한 정적/API 계층만 뜻한다. 같은 기능이 다른 계층에서 여러 행을 가질 수 있다.

| ID / 등급 | 능력·대상 | exact file / 함수 / 이유 | 후속 | 최종 물리 |
|---|---|---|---|---|
| A0 이미 지원 | 6개 v2 JSON·공개 주문 identity/count·정적 지도·화물 종류/필요 인원 | `harness/zone_final_env.py::maps_dir_for:105`, `harness/zone_study_scenarios.py::validate:700`, `harness/zone_study_inputs.py::FORMATIONS:50`; 지원 schema가 실행 지원을 뜻하지 않음 | T01/T02에서 계약 재사용 | 미측정 |
| A1 이미 지원 | cyan 단독 API, r1/r2 빔 1개 API, 4조건 공통 enum 상태 채널 | `harness/zone_own_executor.py::deliver:277`, `harness/zone_pair_executor.py::PairTeam.start:501`, `harness/zone_study_integration.py::executor_plan:261`; 각 아래 제한 안에서만 | 기존 후보를 승계하지 않고 재검증 | 미측정 |
| R0 정적 어댑터 부족 | s2/s4/s6 지도 resolver/장면/provider | `scripts/run_zone_study_integration.py::run_bundle:349`의 `validate(scenario)`/`bundle_for(scenario)`가 maps_dir 생략; `sim/zone_geometry_scene.py::geometry_map:11`의 `unknown geometry map: ...`; `MAP_IDS:8` 문1개만. `vision_pose_source.py::VisionPoseSourceV2.map_ids:268`도 같은 지도만 | T01(P01 소유) | 미측정 |
| R1 정적 어댑터 부족 | 혼합 물건, order_id≠item_id, count>1 | `scripts/run_zone_study_integration.py::host_spec:318`(333–339): `M2 dev supports a pair-only order with explicit static sheet and matching order/item id`; solo can을 cargo로 넣으면 342–343 `pair setup without a team order`. `sim/zone_geometry_scene.py::_resolve:26`(40–43)은 cargo 존재 시 기존 색 상자 inventory 삭제 | T02(P02 이후 별도 확장, 담당 미정) | 미측정 |
| R2 하위 제어·인식 필요 | red/green 색, can/tile 종류·파지 높이 | `harness/zone_own_executor.py::deliver:277`(285–286) `KIND_NOT_SUPPORTED_BY_M1_SKILL`; `_step_deliver:576`에서 `box_kind='cyan'`. `harness/m1_owncam_delivery.py::__init__:94`(97–98) `M1 v1 delivers the cyan box` | T03/T04/T05 | 미측정 |
| R3 하위 제어·인식 필요 | heavy_crate 및 r3 파트너/역할 교환 | `harness/zone_study_integration.py::executor_plan:261`(275–283): `UNSUPPORTED_TEAM_ORDER`, `UNSUPPORTED_PAIR_ROLE`; `harness/zone_pair_executor.py::PairTeam.start:501`(537–547): `UNSUPPORTED_PAIR`, `UNSUPPORTED_PAIR_ORDER` | T06/T07 | 미측정 |
| R4 정적 어댑터 부족 | 모든 원본 빔의 90° 초기 자세·coarse sheet | `harness/zone_pair_executor.py::make_plan:28`: `BAD_COARSE_ORDER_SHEET`, `ORDER_SHEET_NOT_ON_COARSE_GRID`, `PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE`; x∈[.7,1.2], abs(y−.05)≤.15, abs(yaw)≤10°. `harness/pair_owncam_approach.py::coarse_order_sheet:48`는 .1 m/10°; 원본 eval 정답으로 runtime sheet를 보충하면 안 됨 | T08a | 미측정 |
| R4b 하위 제어·인식 필요 | 위 시작점→자기 영상 접근/정렬; 빔 회전 | `make_plan:52–62`는 고정 heading의 축 정렬 route, `PairTeam.start:573–574`가 계획 예외를 `INVALID_PAIR_PLAN`으로 감쌈. 필터 범위만 넓히면 안 됨 | T08b/T11 | 미측정 |
| R5 정적 어댑터 부족 | 좁은/넓은 문 선택, corridor/bay | `make_plan:46–48`는 door_1, [2.2,.05], .5 m만 허용(`UNSUPPORTED_PAIR_MAP`). `zone_own_executor.__init__:134`, `m1_owncam_delivery.__init__:117`는 첫 `kind=door`; 복도는 `StopIteration`, 두 문은 첫 문을 고정 선택 | T09a/T10a | 미측정 |
| R5b 하위 제어·인식 필요 | 관측한 막힘 우회, 편대 방향 전환, 양방향 복귀/양보 | 고정 M1 door/exit, M2 route에는 사건 관측 기반 통로 선택·bay 대피 정책의 연결이 없음. 정적 경로 발견은 이 상태 전이를 수행하지 않음 | T09b/T10b | 미측정 |
| R6 정적 어댑터 부족 | 특정 개체와 fungible count 구분 | `deliver:280–305`는 order_id로 lookup 후 pickup_slot만 넘김; `identity/item_ids` 선택을 하위 제어에 전달하지 않음. count2를 item ID 한 개로 바꾸거나 host 정답 바인딩을 robot에 주면 안 됨 | T02 + T13a | 미측정 |
| R6b 하위 제어·인식 필요 | 이동한 특정 cyan 재식별, red 낙하 발견/재파지 | `m1_owncam_delivery.__init__:94`는 box_kind/slot을 받음; 동일 색 개체 구별을 입증하지 않음. `sim/zone_hidden_events.py::HiddenEventPhysics.apply:233`(268–286): 이동 시 held면 `none_item_held`, 낙하 시 unheld면 `none_item_not_held`; 효과는 평가 전용 | T13b | 미측정 |
| R7 설계 범위 미확정 | s6 서쪽 전용 접근·pivot90°·후퇴·순서 인과 | `configs/zone_study_scenarios_v2/s6_novel_relation_v2.json::eval.*`와 `zone_scenario_feasibility.check_free_robot_access:734`의 여유 결과 불일치; `zone_cargo._build:128` can any 접근. `executor_plan:261`는 claim/continue/wait/release뿐이며 pivot primitive 없음 | T11 | 미측정 |
| P 물리 미확인 | 최종 모델/벽/위치 추정에서 26개 배달·사건·역할·동료 교통 | 정적 geometry/pytest/과거 단계 probe가 닫을 수 없는 계층. 파지·하중·미끄러짐·거짓 성공·3-D 접촉·own-RGB 오인식/위치 오차·최종 zone 착지를 별도 기록 | 각 T 물리 시험, C6/C7 | 전부 미측정 |

위 코드는 **정적으로 읽어 거절 조건을 연결**했다. controller/host/scene를 instantiate하여 시험하지 않았다. 특히 `make_plan`의 함수 내부 import는 `scripts.run_m2_pair`→기존 controller/실험 모듈로 이어지므로 P09는 실행하지 않는다. 예외 순서상 앞의 지도/host 거절에 가려지는 후속 미지원도 표에 남겼다.

## 4. 비용과 완료 판정

[REQUIREMENTS §경로/정류장](REQUIREMENTS.md)의 실제 설정 좌표와 이번 정적 경로 길이를 사용한다. ‘실제’는 원본/계산 값이라는 뜻이며 **실제 주행 시간이나 통과 결과가 아니다**.

- 벽만 고려한 운반 길이: 물건별 **2.25–9.35 m**, s2 사건 후 **3.35–9.55 m**. 남북 빔의 이번 경로 누적 회전은 s1/s3/s6 180°, s4 90°다. BFS는 기하 경로 예시이지 시간 최적 경로가 아니다. s2 cyan_1은 5.15→9.55 m로 늘어난다.
- spawn 후보→파지 정류장 직선거리와 정류장 yaw를 각 item/role별로 저장했다. 충돌 없는 접근 거리, 재측위/정렬/파지/해제/staging SIM초, 관측·사고 SIM 비용은 **미측정**이다. `arena_default`를 특정 로봇의 준비 완료 자세로 바꾸지 않는다.
- 예산 산식: `T = T_reset/staging + L_approach/v_empty + L_carry/v_loaded + abs(delta_yaw)/omega + T_observe/align/grasp/release + T_event/recovery`. 정적 길이만 알려졌다. 예를 들어 **가정** v_loaded=.05 m/s라면 9.55 m의 병진 항만 191초다. 이를 완주 예상시간이나 900초 cap의 보증으로 쓰지 않는다.
- 후속 최소 물리 확인은 **능력/조건 셀당 정상1+실패1, 각 900 SIM초 cap**을 제안한다. reset/staging부터 cap에 포함하고 실패·미도달·ENOSPC(HOST_ERROR)를 분모/기록에 남긴다. staging 시간·제어 진행을 별도 출력한다. 정답 staging을 쓰는 격리 probe는 `stage_probe/not_e2e_success`로 표시하며 최종 실제 출발 시험을 대체하지 않는다.
- [TASKS 예산표](TASKS.md#예산-합계와-미산정)는 **한 후보, 한 controller의 기능 확인** 제안이다. 4조건을 별도 하위 제어기로 구현하지 않는다. 모든 4조건의 입력·status channel·controller/config 해시 동일성을 fake 검사한 뒤 C6/C7에서 조건별로 실제 연결한다.
- T11의 pivot/순서 과제, final-v3 보정/인식 데이터 확보·개발 반복 횟수, 막힘 후 실행 당시 시작 자세/동료 교통, 확증 반복 수가 미확정이므로 **전체 개발비용은 미산정**이다. 900초 cap을 기능 수 없이 곱하거나 wall 시간으로 환산하지 않는다.
- C6 제안은 정식6×1 smoke block×4조건=24회, 최대43,200 SIM초(12 h). C7 #254 정식 외부 파일럿은6×3seed×4=72회, 최대129,600초(36 h). 합48 SIM-h는 기능 개발비용과 별도이며, 작은 dev/24회 파일럿으로72회 설계를 완료하지 않는다. 이 문서는 seed/사전 등록을 고정하거나 실행을 승인하지 않는다.

## 5. 남은 물리 미측정 목록

1. 최종3지도·로봇v3 reset/초기 접촉, 무표식 위치 추정, RGB/지도/모델 해시 일치(P01/P03).
2. cyan/red/green/can/tile/crate의 탐색→접근→파지→운반→목적지 방출, specific identity와 같은 색 두 물건의 오인식/중복 배달.
3. 정식3종 빔 시작 배치의 실제 접근, r3 포함6가지 역할 배정, 한쪽 실패/상태 채널/지연 중 안전 종료, 낙하 없는 공동 운반.
4. 좁은 문·넓은 문·복도에서 전체 편대 통과, 방향 전환, 양방향 복귀/대치, bay 대피. 3-D 팔·화물·벽 접촉도 포함.
5. s2 막힘의 실제 발생과 자기 카메라 발견/우회, 반대편·pickup에서의 비가시성. s3 r3 12–52초 정지와 집결 지연의 실제 성립.
6. s5 30초 이동/이미 파지 no-op, 62.5초 낙하/미파지 no-op, 그 이후 재탐색·재식별·재파지와 거짓 성공0.
7. s6 서쪽 접근의 실제 제약, end_pos pivot·후퇴·can 회수의 순서 필요성 및 실행 가능성.
8. 같은 소스·controller로 정식6종 C6/C7 완주, 실패 포함 성공률·SIM시간·명령·모델 호출/응답시간·비용 및 원장 정산. static PASS를 성공률에 넣지 않는다.

이번에는 새로운 학습/모델/물리 실행 결과가 없으며 정적 문서·검사만 요청받았다. TensorBoard 이벤트/성공 scalar나 화면을 만들지 않았다. 후속 실제 실행은 프로젝트 TensorBoard 절차로 실패까지 새 snapshot에 등록해야 한다.

## 참고 자료

- [#202](https://github.com/kcm0127-dotcom/ugrp/pull/202), [기존 feasibility 설명](../../docs/zone_scenario_feasibility.md): v1 결과와 이번 v2 재검사를 구분한다.
- [#255](https://github.com/kcm0127-dotcom/ugrp/pull/255), [원본 지도 이관 기록](../2026-09-28-final-map-scenario-v2/README.md), [catalog](../../maps/zones_final/catalog.json).
- [#254](https://github.com/kcm0127-dotcom/ugrp/pull/254), [본연구 DRAFT](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md): 문서 PR은 MERGED, 사전 등록은 미고정 DRAFT다.
- 이슈 [#219](https://github.com/kcm0127-dotcom/ugrp/issues/219), [#220](https://github.com/kcm0127-dotcom/ugrp/issues/220), [#221](https://github.com/kcm0127-dotcom/ugrp/issues/221), [#222](https://github.com/kcm0127-dotcom/ugrp/issues/222), [#223](https://github.com/kcm0127-dotcom/ugrp/issues/223), [#224](https://github.com/kcm0127-dotcom/ugrp/issues/224)의 본문과 최근2개 댓글을 조회했다. 과거 probe/host 결과를 P09 신규 증거에 합산하지 않았다.
- 착수 시 열린 PR: #298/#297/#295/#293/#292/#285. P01/P02/P03/P05/P06 및 #292/#293와 소유 범위를 분리했다. controller/사전 등록/공용 registry를 수정하지 않았다.
- 새 논문/OSS 도입 없음. 기존 Python 표준 라이브러리, NumPy, pytest와 정적 기하 evaluator를 재사용했다. Pillow는 기존 투영기 import 의존성이고 renderer는 금지 hook으로 차단했다.
