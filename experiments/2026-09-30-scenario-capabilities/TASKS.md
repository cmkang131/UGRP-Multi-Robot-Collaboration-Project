# P09 후속 task prompts — 한 항목당 한 PR

이 문서는 실행하지 않은 작업 배정안이다. T01/T02는 병렬 진행 중인 P01/P02 소유 작업에 요구/시험을 전달하며 별도 중복 구현하지 않는다. T08–T10은 정적 계약 PR(a)와 하위 제어 PR(b)을 분리한다. 구현 전 열린 PR과 최신 소스를 대조하고 번호/번들은 프로젝트 절차로 새로 예약한다.

## 모든 prompt에 적용하는 계약

- AGENTS.md/CONTRIBUTING.md/README.md/docs/current_status.md를 읽고 fetch/열린 PR 확인. 자기 worktree/브랜치와 지정 파일만 수정한다. 선행 PR의 실제 병합 SHA/검증 범위를 기록한다.
- 원본 `configs/zone_study_scenarios{,_v2}/s1–s6`, 기존 지도/실험/성공 번들을 보존한다. 새 dev fixture는 원본을 대체하지 않으며 본연구 DRAFT·seed·성공 기준을 몰래 바꾸지 않는다.
- `no_comm/peer_ko/leader_ko/structured` 모두 **동일한 controller/config/센서/자기 기억 버전/상태 enum 채널**을 쓴다. 조건 차이는 통신 허용 범위뿐이다. role assignment와 제어 코드 해시를 따로 기록한다. 4조건별 override, s6 전용 host 해법, host가 고르는 양보/파트너는 금지한다.
- 자기 RGB·정적 지도·공개 주문·자기 명령과 허용 수신만 사용한다. 비공개 배치/사건 시각/현재 정답/접촉/심판을 제어에 주지 않는다. setup manifest의 item identity 연결은 평가/장면 전용이다. P09의 inventory/feasibility 경로를 robot 입력으로 쓰지 않는다.
- fake 검사에는 정상·미지원/오류·경계 반례와 private 변화 비간섭 검사를 넣는다. 물리 단계는 별도 작업에서 실행한다. 새 모델 호출은 이 prompt의 기본 예산에 포함하지 않는다.
- 물리 시험은 최종3D 모델·walls_v3·표식0·weld OFF·cargo_noslip_v1로, 실행 전 커밋/입력/설정 고정 및 공용 잠금. raw를 primary `outputs/`에 보존하고 staging 포함 SIM초, 명령/관측, 실패 원인, 성공률 분모를 남긴다. 실패 후 같은 결과 파일을 덮지 않는다.
- 아래 cap은 **한 후보 최소 진단 제안**이며 검증 완료·4조건 효과/확증 결과가 아니다. 정상/실패 셀마다 cap 도달은 실패/미도달로 남긴다. 실행 결과는 TensorBoard snapshot과 원본 해시까지 확인한다. 구현 PR과 물리 검증 결과의 준비 판정을 구분한다.

## T01 — 최종 지도 경로와 장면/provider 계약 (P01 소유)

**Prompt:** `zone_final_env.maps_dir_for()`를 재사용해 v2 6종에서 공개 지도 파일, 장면 지도, provider/model/calibration 선택이 같은 ID·해시를 가리키게 하라. `scripts/run_zone_study_integration.py::run_bundle`, `sim/zone_geometry_scene.py`, `sim/zone_own_scene_provider.py` 및 provider registry의 P01 작업과 합의한 부분만 고친다. 물건/controller 확대는 하지 않는다.

- Fake: 3지도 resolver, 잘못된 해시/unknown ID 거절, 표식키0, 지도 크기/벽·통로 보존. renderer/host/world 생성 없이 검사한다.
- 물리: 최종3지도 각 reset→30초 정지. 초기 겹침·v3 모델/벽·자기 RGB를 평가 기록으로 확인. 통로 통과 판정은 없음.
- Cap: 정적0, 물리3×30=90 SIM초. **READINESS C1의 동일 셀과 중복 계산하지 않는다.** s2/s4/s6 차단 R0를 닫는다.

## T02 — 혼합 재고 및 order/item/count 어댑터 (P02 소유)

**Prompt:** `host_spec`의 pair-only와 order_id=item_id 결합을 제거하되 `orders`와 setup inventory를 별도 객체로 보존하라. cyan2/red2의 fungible count, specific beam_1/crate_1/can_1, 혼합 solo+team을 모두 표현하는 정적 연결만 구현하라. `sim/zone_geometry_scene._resolve`의 cargo 존재 시 색 상자 삭제를 전체 inventory 보존 계약으로 바꾸고, generic cargo에 solo can/tile도 있는 것을 처리하라. runtime 인식이 성공했다고 표시하지 말라.

- Fake: 정식6 JSON에서 물건 수7/4/4/4/4/3, 주문 수6/3/4/4/3/3, 모든 ID와 목적지 보존. 중복ID·누락/초과 count·잘못된 kind/item 연결 거절. `order-5`를 `beam_1`로 덮는 우회 금지. private pose/event만 바꿔 robot 공개 입력은 동일해야 한다.
- 물리: 원본 s1 재고로 한 정상 전체 배달과 한 중복/오배정 실패 실행. 현재 미지원 품종은 해당 하위 작업이 닫힌 뒤 실행한다. 물건을 숨기거나 주문을 줄여 정상으로 세지 않는다.
- Cap: 2×900=1,800초 제안. 경로는 s1 3.30–7.15 m, 실제 동시 배정/완주 시간은 미측정. R1 어댑터 완료와 전체 수행 완료를 구분한다.

## T03 — red/green 색 상자 M1 확장

**Prompt:** cyan만 허용하는 `ZoneOwnExecutor.deliver`/`M1OwnCamDelivery`와 연결된 wrist 검출/holding/placement의 색 처리를 명시적인 kind로 바꿔라. 이 PR의 신규 종류는 red·green 색 상자만이다. can/tile/crate의 shape/grasp는 별도 PR이다. 지원 enum을 바꾸기 전에 색 혼동·확신 거절 fixture를 고정하라.

- Fake: 저장된 독립 라벨 RGB에서 cyan/red/green 혼동, 그림자·가림·검은 화면, 다른 kind의 후보/holding을 성공으로 세지 않는 반례. 세 kind에 같은 정책을 사용한다. M1 cyan 회귀, unknown kind fail-closed, 4조건 동일 skill/config.
- 물리: red→B, green→C 각각 정상1+오인식/파지실패1. 시험 fixture는 정식 배치 범위에서 고정하고 새 camera/view 임의 조작 금지.
- Cap: 2종×2×900=3,600초. 정적 운반 red 6.55–9.35 m, green 3.30–7.50 m. 최종 환경 인식 라벨/보정 자료 수집·재학습 필요성은 미산정. R2 색 범위만 닫는다.

## T04 — can 단독 접근/파지/방출

**Prompt:** catalog can의 직경 .038 m, 높이 .050 m, 80 g, grasp role `any`에 맞는 자기 RGB 상대 접근·holding·방출 skill을 독립적으로 등록하라. box용 팔/높이/색 threshold 재사용을 성공으로 가정하지 말라. s6의 서쪽 전용 제약을 이 PR에서 새 규칙으로 몰래 강제하지 말라.

- Fake: 원통 중심/가림/바닥 색과의 혼동, 빈 집게·미파지·잘못된 물건, 허용하지 않는 pose에서 거절. 색 상자 API 회귀, can kind/height/role 연결과 RGB 출처를 검사한다.
- 물리: s1/s5 `(0.4,−0.85,0)` can 정상1+실패1의 접근→C 방출. s6의 can은 T11 설계/접근 검증을 별도로 요구한다.
- Cap: 2×900=1,800초, 정적3.30 m. s6 2.25 m는 타 물건과의 can 진입을 입증하지 않는다. 학습/보정 반복 수는 미산정.

## T05 — tile 낮은 파지/자세

**Prompt:** .060×.040×.012 m tile(25 g)의 .007 m grasp 높이, west/east 가능한 파지 중 공개 계약에서 선택한 역할, 자기 RGB holding/방출 판단을 연결하라. `zone_study_inputs.FORMATIONS`가 tile west 한 개를 내보내는 현재 계약과 catalog의 두 대안 중 어느 것을 지원할지 명시한다. 첫 PR은 west만이어도 제한을 표기하라.

- Fake: tile/배경/상자 혼동, 낮은 물체 탐지 실패, 팔 명령 높이 범위, 잘못된 역할 거절; 하위 제어 완료와 심판 배송 완료 분리.
- 물리: `(1.0,−.85,0)`→B 또는 C 중 고정한 기본 목적지 정상1+미파지1. 다른 목적지는 정식 코호트에서 별도 커버한다.
- Cap: 2×900=1,800초; 정적 운반 B 5.55 m/C 2.70 m. 보정·마찰/접촉 자료는 미측정.

## T06 — heavy_crate 쌍 lug 수행

**Prompt:** long_beam 전용 API 거절을 단순 삭제하지 말고 heavy_crate의 west/east lug, 900 g, 2인 파지·동시 들기·holding·운반·배치 계약을 별도 skill로 추가하라. beam의 end_neg/end_pos·상대 길이·빛깔을 crate로 그대로 복사하지 않는다. `executor_plan`과 PairTeam은 명시적 kind dispatch만 추가한다.

- Fake: crate→west/east 역할, body 대신 lug 목표, 한쪽 ready/holding 누락·heartbeat 중단·잘못된 역할·동일 로봇 중복 거절, 한쪽 실패 전파. 미지원 crate API가 fake 긍정만으로 physical supported가 되지 않아야 한다.
- 물리: s2 `(1.275,−2.15,0)`에서 west `(1.02,−2.15,0)`, east `(1.53,−2.15,π)`의 실제 접근→B 배달 정상1+한쪽 파지실패1. 대칭 파트너 확장은 T07.
- Cap: 2×900=1,800초. 이번 정적 편대 경로는 넓은 문3.35 m. 하중/관절/마찰 한계·양측 holding 인식은 미측정이며 불가능하면 물건/정책을 몰래 바꾸지 않고 설계 차단으로 보고한다.

## T07 — r3와 역할 교환

**Prompt:** `executor_plan.roles`, `PAIR=('r1','r2')`, `PairTeam`/상태 endpoint/명령 routing의 actor 고정을 role→robot mapping으로 바꿔라. r1/r2, r1/r3, r2/r3의 각 양끝 배정6개를 지원하되 고수준 요청으로 선택하고 host가 상대 private state를 보고 배정하지 않는다. 새 메시지 정보량을 늘리지 말고 기존 고정 enum 상태 채널을 4조건 모두 유지한다.

- Fake: 6개 배정×4조건, 잘못된/self/중복 partner, 제출 불일치, timeout/재시도, peer private state 변조 비간섭, r3 쌍에서 r1/r2 명령으로 새지 않음. 기존 고정 역할 기록은 변경하지 않는다.
- 물리: 동일한 사전 고정 배치에서 역할 배정6개 각각 정상1+한쪽 실패1. 한 역할에서만 통과하면 그 셀만 지원으로 기록한다.
- Cap: 12×900=10,800초. 실제 spawn assignment·접근 및 asymmetric 카메라 품질에 따라 달라짐; 이전 r1/r2 성공을 다른 네 배정으로 복제하지 않는다. s3 r3 지연 의미를 닫는 선행이다.

## T08a — 정식 빔 초기 자세의 정적 sheet/plan 계약

**Prompt:** 기존 `make_plan`이 받는 .1 m/10° 공개 coarse sheet를 원본 남북 빔3종 `(1.275,.45,π/2)`, `(.125,.45,π/2)`, `(1.1,−.85,π/2)`에도 적용할 수 있는 새 정적 plan 계약을 만들라. setup에서 사전 고정한 공개 coarse 정보의 허용 범위/오차를 명시하라. 상세 eval 배치/실시간 정답을 읽어 sheet를 생성하거나 로봇을 정류장에 teleport하지 말라. 새로운 역할 접근 heading/geometry 계획을 반환하고 제어기를 실행하지 않는다.

- Fake: 현재 세 자세의 `PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE` 반례, 잘못된 grid/출처, 초기 위치 오차 범위, 모든 carrier swept footprint/경계, ID/order 해시, 정적 입력만으로 결정됨을 검사한다. 미지원 경로에는 명시적 refusal을 유지한다.
- 물리/Cap: 이 PR은0 SIM초. 실제 접근·회전 수행은 T08b/T11/T09b/T10b의 몫이다. static PASS를 E2E admission으로 승격하지 않는다.

## T08b — 남북 빔의 실제 접근/정렬 인계

**Prompt:** T08a 정류장을 목표로 출발부터 자기 RGB 위치 추정·prestation→양끝 상대 정렬을 수행하게 하라. 실제 접근 posterior·servo·history를 연속 인계하고 probe용 준비 자세로 바꾸지 않는다. #292 및 P03/P05/P06 제어 작업과 최신 후보/함수 소유를 조율한다. 운반 중 pivot은 이 PR에 넣지 않는다.

- Fake: 남쪽 end_neg yaw≈+π/2, 북쪽 end_pos yaw≈−π/2; 새 정류장/범위·self_pose_uncertain·교차 접근·own-image-invalid·실패 status, 실제 history 인계 검사. 실패 시 숨은 GT 재초기화 금지.
- 물리: 원본3종 배치 각 실제 spawn→정렬 진입 정상1+실패1. 정렬 posterior 오차 평가와 성공/미도달을 기록한다. carry까지 안 갔으면 배달 성공이라고 하지 않는다.
- Cap: 3×2×900=5,400초. 파지 자리까지 직선 하한은 역할/배치/후보 spawn에 따라 약1.03–3.78 m이며 충돌 없는 접근 길이는 아직 없다. staging/팔 전이 SIM초도 cap에 넣는다.

## T09a — 두 문 선택용 정적 경로 인터페이스

**Prompt:** M1 첫 door, M2 door_1 상수에서 벗어나 `door_narrow(.5 m)`/`door_wide(1 m)` 후보 경로를 정적 입력·선택된 화물/편대 footprint로 계산하는 작은 인터페이스를 만든다. 반환은 방향/heading 포함 경로와 거절 이유뿐이며 숨은 사건을 자동 주입하지 않는다. P01 지도 등록과 분리한다.

- Fake: 좁은 문/넓은 문 각각의 허용·차단, 반대 방향, 전체 편대 모서리와 crop된 point/disc 계획의 반례. 통로 mouth 방문을 crossing으로 세지 않는 P09 회귀 재사용. 미래의 private blockage만 바꿔 아직 관측하지 않은 plan은 같아야 한다.
- 물리/Cap:0 SIM초. s2 45초 막힘에 대한 실제 관측·우회는 T09b. 설계상 controller가 따를 수 없는 회전 경로는 지원 밖으로 거절한다.

## T09b — 관측한 막힘 뒤 두 문 우회

**Prompt:** 자기 RGB에서 직접 확인한 막힘/허용 메시지 이후에만 T09a로 재계획하고 같은 하위 navigation을 모든 조건에서 사용하라. 원본 s2의 event 시각/좌표를 controller에 전달하지 않는다. current belief와 private referee를 분리한다.

- Fake: 관측 전 경로 불변, 직접 관측 후 narrow→wide, 메시지 미수신 no_comm의 사전 우회 금지, 양쪽 막힘일 때 안전 거절, 한쪽 편대 동작 중 실패. map/prior/hash의 4조건 동등성.
- 물리: solo와 pair 두 profile 각각 정상1+막힘1. 45초 event의 실제 obstacle 발생·own RGB 가시/비가시와 wide 통과를 따로 확인한다. 모르는 obstacle을 host가 미리 경로에 넣지 않는다.
- Cap: 2profile×2×900=3,600초. s2 cyan_1 정적5.15→9.55 m, cyan_2 4.55→8.95, green3.30→4.50, crate3.35→3.35. event 시점 실제 위치와 탐색/왕복은 미측정이므로 이 차이를 실제 지연 추정치로 쓰지 않는다.

## T10a — 복도/bay와 방향의 정적 계약

**Prompt:** `kind=door` 없는 corridor 지도를 안전하게 처리하고, corridor_1 통과와 bay_1 정지/대피/재진입을 별도 정적 검사로 정의하라. 전체 편대에 대한 bay 적합성을 검사하되 pair가 들어갈 수 있다고 가정하지 않는다. 원판 통과·물건 회전·양방향 pose 경로·동시 점유를 서로 다른 반환 필드로 둔다.

- Fake: corridor만 있는 지도에서 StopIteration 제거, bay 내부 점유/경계 여유, 편대 폭과 길이 및 yaw sweep, 동쪽→서쪽 경로, pair+solo(3대) 교통. 2pair(4대) 교행은 원본 팀3대와 다름을 거절/표시한다.
- 물리/Cap:0 SIM초. 어떤 편대가 bay에 들어갈 수 있는지 불명하면 `unsupported`/설계 미확정으로 남긴다. static reverse true는 동시에 교행 가능하다는 뜻이 아니다.

## T10b — 복도 통과/후퇴/양보 제어

**Prompt:** T10a의 지원 가능한 경로에서 자기 관측·자기 타이머·허용 메시지로 진입/후퇴/대기/재진입을 수행하는 제어를 연결하라. host 정답 기반 자동 후퇴 규칙은 쓰지 않는다. pair가 bay에 들어갈 수 없으면 할 수 있는 로봇이 양보하는 결정을 controller/고수준 정책이 하게 하며 host가 답을 정하지 않는다.

- Fake: 4조건 동일 navigation, 쌍 한쪽 이탈·heartbeat 끊김·대기 timeout·대치 반복에서 안전 종료, 교통 충돌/불가능 경로 refusal, waypoint를 완료로 간주하지 않음.
- 물리: solo/pair×동/서 방향×정상/대치 실패=8셀. 실제 team은 최대3대다. 각 셀의 장면/하중/정류장·상대 위치를 사전 고정하고 병진/회전·접촉과 재출발을 평가한다.
- Cap:8×900=7,200초. s4 이번 정적 운반 길이4.05–9.35 m, beam 누적90°·green120°. 빈 로봇 복귀·bay 후퇴 거리와 현장 지연은 미산정. 이 시험만으로 원본 s4 동적 성공을 확정하지 않는다.

## T11 — s6 순서·서쪽 can 접근·end_pos pivot 설계 결정

**Prompt:** **첫 PR은 문서/정적 반례만** 작성하라. 원본 s6를 그대로 보존하고 “서쪽만 가능”, “빔90° 회전이 선행”, “한쪽 후퇴가 선행” 각각의 필요조건/관측 가능한 종료 기준을 정의하라. 반례는 can any-heading catalog, base x1.295 여유1.67 mm, 타 물건 포함 경로 PASS다. pivot 중심을 end_pos 접점으로 할지, 중앙 회전/내려놓기-재파지로 할지, 원본 의미를 유지할 수 있는지 설계 결정을 받는다. 원본을 새 dev로 대체하지 않는다.

- Fake/정적: 현 기하에서 가능한 모든 허용 접근과 bay/obstacle/cargo 회전 sweep을 비교. 원판/측정 chassis/최종v3 footprint 차이, ‘자리 standability’와 ‘진입 route’ 차이. 순서/인과를 표현하지 않는 structured schema와 공통 action primitive를 바꿀 때 #254 H2의 비교 대상이 어떻게 달라지는지 적는다.
- 후속 물리 시험: 동일 초기 배치에서 (i)선행 없이 can 접근, (ii)고정한 pivot/후퇴 후 can 접근, (iii)pivot 한쪽 실패. 실제 필요성·성공과 양쪽 실패 안전을 분리한다. 이는 설계 고정 뒤 **별도 controller PR과 별도 사전 등록**이 필요하다.
- Cap: 이 설계 PR0. 후속 조작의 도착 자세·회전 중심·staging/접근 길이·실패 종료가 없어서 **총 물리비용 미산정**. 정상/실패2×900=1,800초는 기준 제안일 뿐 합계에 넣지 않는다. 현재 static PASS가 언어 표현력 가설의 전제를 보증하지 않는다.

## T12 — r3 지연 집결/재배정/취소

**Prompt:** T07 이후 `r3_hold_late`에서 짝 대기·재배정·취소가 자기 입력과 허용 통신으로만 일어나게 하라. P06/기존 PairTeam rendezvous/state 채널의 소유 작업과 조율한다. host가 12–52초 이벤트를 알려주거나 늦을 상대를 미리 선택하지 않는다. leader 순환(r1/r2/r3)과 pair role은 별도 축이다.

- Fake: r3를 각 끝 역할에 배정, timeout 전/직전/후 제출, 40초 명령 불응 상태와 종료 뒤 재요청, 4조건별 peer private state 변화 비간섭, 취소 후 기존 job의 명령 잔류0. r3가 solo일 때 ‘짝 지연 성립’으로 잘못 세지 않음.
- 물리: 정상 집결1+원본12–52초 r3 hold1. 실제 바퀴 정지/own 인지·partner 대기와 재개·leader=r3 경우를 분리 기록한다. 전체3 leader 값은 C6/C7 또는 후속 확대에서 채운다.
- Cap:2×900=1,800초. 40초는 지연 주입량이지 makespan 증가 확정치가 아니다. 정식 s3 배달 완료는 여기서 대신하지 않는다.

## T13a — specific identity와 fungible count의 자기 관측 실행

**Prompt:** T02의 정적 binding과 별개로, 공개 specific item과 자기 RGB track, 같은 색 fungible count의 관계를 정의하고 하위 job에 전달하라. `cyan_1`의 이름만으로 이미지에서 동일성을 알 수 있다고 가정하지 않는다. 구분 불가하면 unknown/재탐색/실패로 남긴다. host GT item lookup을 controller에 노출하지 않는다.

- Fake: 같은 색 두 개, count2 중 중복 target, 기존 track 소실/재등장, item_id/order_id 다름, 오배송 후 잘못 완료 주장. peer의 실제 배송 상태만 바꾸면 자신이 관측하기 전 claim이 바뀌지 않아야 한다. 모델 없이 고정 action으로 4조건 계약을 검사한다.
- 물리: specific target 재탐색 정상1+같은 색 교환/가림 실패1. 미파지/오인식을 포함해 거짓 동일성/성공0 여부를 본다.
- Cap:2×900=1,800초. 저장 fixture로 구별 불가능하면 인식 정보 설계가 필요하므로 추가자료·정체성 처리 비용은 미산정. 정식 s5는 cyan1개지만 이동 후 track 연속성은 여전히 확인한다.

## T13b — 이동/낙하 후 복구와 no-op 분리

**Prompt:** 원본 s5의 cyan 이동30초와 red_1 낙하62.5초를 그대로 유지하고 사건의 효과/무효와 학생의 발견/복구를 분리하라. `HiddenEventPhysics.apply`의 `none_item_held`/`none_item_not_held`를 평가에만 보존한다. 미파지 no-op를 억지 낙하/거짓 실패로 바꾸거나 사건 효과를 controller에 성공/실패 통보하지 않는다.

- Fake: 이동시 unheld→move, held→no-op; 낙하시 held→open fault, unheld→no-op 4분기. 주문 initial_location 불변, event schedule/holder truth가 robot 입력에 유출되지 않음. student absent/dropped 믿음은 own RGB 근거로만 바뀌어야 한다. 제어 명령 발행은 물체 이동 성공이 아니다.
- 물리: 4분기 각1개, 공통 초기 seed/설정과 사건 직전 상태를 기록. 효과 있는 실행에서만 이동/낙하 복구 성공률을 따로 내되 모든 할당 실행·no-op 분모도 남긴다. no-op가 많으면 사건 성립 부족으로 보고한다. 원본 시간을 사후 수정하지 않는다.
- Cap:4×900=3,600초. cyan 운반은 원래6.35 m, 이동 후5.15 m의 정적 예시; 낙하 위치·재파지 접근 길이는 물리에 의해 정해져 미산정이다. 색/red와 can 지원 T03/T04, identity T13a가 선행이다.

## 예산 합계와 미산정

아래는 **각 시험을 독립 실행한다고 가정한 1차 상한**이다. 이미 같은 실행으로 검증한 셀을 재사용하면 그 run ID로 연결하고 한 번만 더한다. 물리0인 정적 PR을 900초 기능으로 중복 계산하지 않는다.

| PR/시험 | 셀×cap | 제안 SIM초 | 현재 측정 |
|---|---:|---:|---|
| T01 장면 | 3×30 | 90 (기존 C1과 중복 제외) | 미측정 |
| T02 혼합/재고 | 2×900 | 1,800 | 미측정 |
| T03 red/green | 4×900 | 3,600 | 미측정 |
| T04 can | 2×900 | 1,800 | 미측정 |
| T05 tile | 2×900 | 1,800 | 미측정 |
| T06 crate | 2×900 | 1,800 | 미측정 |
| T07 역할6종 | 12×900 | 10,800 | 미측정 |
| T08a/T09a/T10a 정적 계약 | 0 | 0 | 구현 전 |
| T08b 실제 접근3종 | 6×900 | 5,400 | 미측정 |
| T09b 두 문/막힘2profile | 4×900 | 3,600 | 미측정 |
| T10b 복도2profile·2방향 | 8×900 | 7,200 | 미측정 |
| T11 s6 설계 | 0; controller 별도 | **미산정** | 미측정 |
| T12 지연 | 2×900 | 1,800 | 미측정 |
| T13a identity | 2×900 | 1,800 | 미측정 |
| T13b 사건4분기 | 4×900 | 3,600 | 미측정 |

T01/C1을 제외한 유한 제안은 **50셀×900=45,000 SIM초=12.5 SIM-h**다. 최소 기능 진단이므로 4조건×3seed 등의 통계 코호트가 아니다. T11, 반복 개발·데이터/보정, 추가 회귀/확증, 기존 P03/P05/P06의 공통 E2E 비용은 포함하지 않는다. C6 12 h + C7 36 h를 더해도 전체 개발비용의 확정 총계가 되지 않는다. 처리량을 재지 않았으므로 wall 환산은 하지 않는다.
