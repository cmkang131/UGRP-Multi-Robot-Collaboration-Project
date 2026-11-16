# T11 — s6 순서·can 접근·pivot 설계 검토

**상태: 설계 선택 대기 / draft 전용 / 물리 실행 준비 안 됨.** 2026-09-30.
이번 PR은 문서와 평가 전용 정적 반례만 담는다. controller, 원본 s1–s6,
지도, 성공 번들, 본연구 DRAFT, seed, 성공 기준을 바꾸지 않는다.
새 dev fixture나 실행 bundle/workflow ID도 만들지 않는다. 병합하지 않는다.

원본 s6의 “서쪽만 가능 → end_pos 쪽 약90° 회전 → 한쪽 후퇴 → can 회수”는
아직 필요한 순서라고 입증되지 않았다. can 카탈로그는 모든 방향을 허용한다.
기존 정적 모델에서는 서쪽 파지 자리가 막히지 않고, 다른 초기 화물을 넣은
운반 경로도 존재한다. 아래의 회전 후보가 충돌을 피한다 해도 **선행 동작이
꼭 필요하다는 결론은 별개**다. 현재 static PASS는 H2 언어 표현력 가설의 전제를 보증하지 않는다.

## 1. 출처와 보존 범위

작업 시작 `HEAD = origin/main = 6594536b1a1afec6d9d109b35dd85a8426142d01`,
브랜치 `codex/s6-order-design`. 기본 checkout은 main·깨끗함을 확인했고 수정하지 않았다.
다음 상태와 실제 병합 SHA는 GitHub에서 조회했다. 과거 검증을 이번 결과에 합산하지 않는다.

| 선행 | 실제 상태 / 병합 SHA | 사용한 근거와 한계 |
|---|---|---|
| [#202](https://github.com/kcm0127-dotcom/ugrp/pull/202) | MERGED / `0b7861cc2aa391e74e62dc342177a6163fb32338` | 정적 feasibility·편대 footprint. 3D 접촉·자기 RGB 실행 성공 아님 |
| [#249](https://github.com/kcm0127-dotcom/ugrp/pull/249) | MERGED / `a1307b73fc11d3c7e7ccdee8336e44eba002137a` | v3 모델·팔 장착 위치와 파지 거리 계약. s6 물리 검증을 승계하지 않음 |
| [#254](https://github.com/kcm0127-dotcom/ugrp/pull/254) | MERGED / `cd7cb31bc4ec873aaf7a7b2515e79f5e06bd0bf9` | 사전 등록 **문서** 병합. 연구는 DRAFT·미고정, H2 s6 방향 예측의 근거 확인 |
| [#255](https://github.com/kcm0127-dotcom/ugrp/pull/255) | MERGED / `1ed1f1e4bd51d1ec4907a6abe564c0635b45e7f1` | 최종 지도·v2 이관, 보고된 정적 90 tests. 팔·편대의 최종 물리 성공 아님 |
| [#302](https://github.com/kcm0127-dotcom/ugrp/pull/302) | OPEN·draft / **병합 SHA 없음** | head `dec67997815e4cdc564a9848ed6020eede45cbfa`의 REQUIREMENTS/TASKS·s6 반례. P09의 CI 취소 이력은 그 작업 기록이며 이 PR의 CI는 정상 수행 |

원본 [v1 s6](../../configs/zone_study_scenarios/s6_novel_relation.json)와
[v2 s6](../../configs/zone_study_scenarios_v2/s6_novel_relation_v2.json)는 그대로 둔다.
v2는 `zone_wide_two_doors_final_v1`, `walls_v3`, 표식0,
`cargo_noslip_v1`, weld OFF, seeds 651/652/653다. beam `(1.1, −.85, 1.5708)`,
can `(1.45, −.85, 0)`, cyan `(.4, −2.45, 0)`이며 숨은 시간 사건은 없다.
세 좌표와 item↔order 연결은 **장면/평가 전용**이다.

`audit.py`는 위 배치를 읽는 평가 도구다. 산출 경로·회전 중심·inventory를
robot payload나 plan 선택에 넘기지 않는다. 입력 파일 해시는
[data/static.json](data/static.json)의 `source_sha256`에 있다. v1/v2 s1–s6도 함께 고정했다.

## 2. 서로 다른 세 주장의 필요조건

`A`를 카탈로그가 허용하는 can 접근 자세와 경로의 집합, `W`를 사전 정의할
서쪽 접근 범위로 둔다. 지금 `W`의 각도 폭·접근 거리·허용 오차는 정해지지 않았다.
“한 번 못 갔다”는 모든 대안이 불가능하다는 증명이 아니다. 성공한 반례 하나는
필요조건 주장을 깨뜨리지만, 유한한 실패 몇 번은 필요성을 확증하지 못한다.

| 주장 | 성립에 필요한 조건 | 제어기가 사용할 수 있는 종료 근거 | 현재 판정 |
|---|---|---|---|
| **서쪽만 가능** | `A−W`의 북/동/남/사선 접근이 실제 전체 footprint·팔 자세·시야·파지 조건 아래 불가능하고, W에는 적어도 한 진입·회수 경로가 있어야 함. 단순 +x 관례는 can 금지 규칙이 아님 | 자기 RGB로 can 상대 위치·자기 접근 heading/거리와 불확실성을 추정하고 파지 가능한 창에 들어왔음을 연속 확인. 발행 goto나 카탈로그 자리 도달 계산만으로 종료 금지 | 카탈로그/정적 proxy 반례 있음. 최종 v3 파지는 미측정 |
| **빔 약90° 회전이 선행** | 회전 없는 모든 허용 can 접근·회수가 불가능해야 함. 작은 회전·병진 이동·빔 먼저 배송·다른 방향 우회도 배제해야 함. 고정한 회전 후에는 적어도 하나가 가능해야 함 | 자기 RGB에서 빔 축의 상대 변화, 고정점 추정의 이동 범위, 목표 공간의 여유를 확인. 양측 허용 상태 채널의 중단/유효 상태를 확인하되 심판 접촉·성공을 받지 않음 | 타 화물 포함 can 정적 경로 PASS. 회전 필요성 미확인 |
| **한쪽 후퇴가 선행** | 같은 회전 완료 자세에서 두 운반자가 남아 있으면 회수 불가, 정책이 선택한 한쪽이 정해진 안전 영역으로 후퇴하면 회수 가능해야 함. 다른 쪽 후퇴/역할교환 대안도 비교. 해제 전 단독 지지 가능성을 가정하지 않음 | 해당 로봇은 자기 영상으로 하중 해제/안전 자세와 후퇴 도착을 확인. can 담당은 자기 영상 또는 허용 메시지에 근거해 통로가 비었는지 판단. 후퇴 명령 발행·timer 만료는 완료 아님 | 후퇴 로봇·거리·도착 heading·하중 처리 미정. 필요성/실행성 모두 미확인 |

관측 종료식은 후속 사전 등록에서 수치로 고정한다. 예를 들어 회전 종료는
`|추정 Δyaw−목표 Δyaw|≤εyaw`, `추정 pivot drift≤εpivot`,
`추정 여유−위치/방향 불확실성 여유>δ`가 `k`회 연속 유지되는 경우로 둔다.
εyaw/εpivot/δ/k, 영상 age·불확실성 한계·timeout·정지 지연 상한은 아직 **미정**이며
실행 가능한 기본값으로 해석하지 않는다. 180° 축 대칭 때문에 방향을 구분하지 못하면
end_pos identity를 안다고 처리하지 않고 `unknown`으로 남긴다.

영상 무효, 가림, 자세 불확실, 한쪽 응답 소실/파지 의심, 예산 만료는 성공 종료가 아니다.
양측에 같은 중단 계약을 적용하고 추가 구동이 유한 시간 안에 멎는지 별도 평가한다.
통신 없는 조건에서도 공통 하위 enum 채널은 같아야 하며, 이 채널에 “빔 뒤 후퇴”라는
고수준 해법을 숨겨 넣지 않는다. 안전하게 내려놓는 동작 자체가 검증되지 않았다면
host가 정답 자세로 복구하지 않고 실패로 끝낸다.

## 3. 접근 방향·footprint·진입 경로의 정적 반례

카탈로그 can의 role은 `any`, 지름38 mm, 파지 반경 d=.155 m다.
임의 heading θ에 대해 base는 `b(θ)=(1.45−d cosθ, −.85−d sinθ, θ)`다.
θ=0/90/180/270°는 각각 서/남/동/북에서 can을 본다. θ 전체 `[0, 2π)`를
허용 대안으로 보며 카탈로그의 yaw=0 대표값을 서쪽 제한으로 바꾸지 않는다.

| 모델 | 서쪽 base x | 서쪽 자리 | 모든 heading과 제한 |
|---|---:|---|---|
| 빈 로봇 원판 r=.17 m, 외접16각형 | 1.295 | PASS, 기존 evaluator의 보수적 여유 **.00167 m** | 360/360 1° 샘플 clear. 아래 원형 상계로 전체 연속 heading도 이 proxy에서는 정적 장애물과 분리 |
| 운반 원판 r=.21 m | 1.295 | 차단 | 279/360 샘플 clear, 서쪽 부근81개 차단. 동·남·북은 clear. 연속 경계각은 미산정 |
| 기존 측정 chassis x=[−.100,.120], y=[−.105,.105] + 팔 strip | 1.295 | beam과 chassis 뒤끝 사이 약75 mm(무여유) | 360/360 및 연속 원형 상계 clear. 옛 측정 proxy이며 final-v3 아님 |
| v3 도면의 .185×.162 m 사각형 **민감도 proxy** | 1.2468 | 사각형 뒤끝과 beam 사이 약34.3 mm | 360/360 및 연속 원형 상계 clear. 팔·바퀴·커버·그리퍼 전체 충돌 footprint가 아니므로 최종 v3 PASS로 사용 불가 |
| 최종 v3 전체 충돌 형상·접근/파지 자세 | 모델 계약상 1.2468 | **미측정 / 지원 판정 불가** | 팔 전이·높이·하중·시야·위치 오차와 접촉 검사 필요 |

연속 heading 상계는 can 중심에서 가장 가까운 장애물(beam)까지 약 .330 m와,
can 기준으로 회전하는 proxy의 최대 꼭짓점 반경을 비교한다. r=.17 원판은
.326755 m, 기존 chassis+팔은 .275772 m, v3 도면 사각형은 .306594 m로 작다.
따라서 샘플 사이를 포함한 모든 heading에서 **해당 proxy와 벽/beam/cyan의 분리**를
보일 수 있다. can 자체는 목표 접촉 물체라 이 장애물 목록에서 뺐다. 원판은 자기 목표와
그리퍼 접촉을 표현하지 않으며, 이 계산은 파지 가능성/팔 충돌의 증명이 아니다.

1.67 mm는 `rect_distance − .17/cos(π/16)` 값이다. 실제 원판의 방향별 경계,
위치 오차, 50 mm 계획 격자보다 작은 틈을 주행 가능한 여유로 해석하면 안 된다.
v3는 `station_grasp_convention`에서 팔 회전축 +.0482 m를 더해 d=.2032 m다.
이를 옛 `.155` 카탈로그 편대와 섞지 않는다. 원본의 .39 m 폭/[1.10,1.49] 주석만으로
현재 모델의 실제 겹침을 확정하지 않는다.

**파지 자리에 설 수 있음(standability), spawn→자리 진입(route), 파지 후 운반은 다르다.**
이번 정적 계산은 전체 heading의 자리를 비교하고 세 화물의 **운반** 경로를 재검사했다.
can·beam·cyan 모두 다른 초기 화물이 있는 상태에서 `feasible`이고 원본 자세→격자 첫점
sweep도 통과했다. 자세열은 `data/static.json.routes`에 보존했다.
P09의 벽만 있는 can 2.25 m·beam 4.10 m/누적180°를 pivot이나 실제 접근 길이로 쓰지 않는다.
이번 결과도 초기 로봇 배정·동료 교통·spawn→정류장·그리퍼 진입·방출을 포함하지 않는다.
모든 연속 접근 경로를 열거/봉쇄했다는 주장이 아니며, 최종 v3의 허용 접근 집합은 아직 미확정이다.

## 4. 회전 중심·방향·bay 비교

beam 중심 C=(1.1,−.85), 축 θ≈π/2, end_pos **파지 접점**은
P=C+R(θ)(.27,0)≈(1.1,−.58)이다. 물체 끝(.30)과 파지점(.27),
end_pos **차체** (옛 proxy 약(1.1,−.425), v3 약(1.1,−.3768))는 다르다.
접점을 고정할 때 `C′=P−R(θ+Δθ)(.27,0)`으로 중심도 이동한다.

| 선택지 | ±90° 뒤 중심(원본 1.5708의 반올림) | 로봇 움직임·의미 |
|---|---|---|
| A. end_pos 접점 고정 | −90°: (.83,−.58), +90°: (1.37,−.58) | end_pos 차체도 접점 주위를 d만큼 돈다. 옛 모델 두 base 회전반경 .155/.695 m, v3 계약상 .2032/.7432 m. “한 로봇 정지” 동작 아님. 원문 의도에 가장 가까우나 ‘쪽으로’가 pivot을 명시한 것은 아니므로 선택 필요 |
| B. 중앙 고정 회전 | 양방향 모두 (1.1,−.85) | 옛 모델 두 base 반경 .425 m, v3 .4732 m. A와 도착 위치·sweep·시야가 다름. 같은 primitive의 다른 파라미터라고 자동 승계 불가 |
| C. 내려놓기→자리 이동→재파지 | 미정 | 하중을 바닥으로 넘기는 단계와 재인식·재파지·새 역할 접근이 필요. A의 연속 파지 pivot 의미를 보존한다고 볼 수 없음. 도착 배치가 없으므로 static sweep도 `unsupported` |

`audit.py`는 A/B 각 양방향을 원본 자세부터 1° 간격91개 자세로 비교했다.
화물 + 양쪽 chassis/팔의 **합집합**을 쓰며 margin=0/.03 m를 따로 남겼다.
can은 보수적 외접 사각형 장애물로 검사했다. 2D 겹침은 높이를 고려한 접촉 판정이 아니고,
샘플 clear도 연속 회전·최종 v3 성공을 보증하지 않는다.

| 후보 | 벽·cyan sweep | can sweep, margin=0 / .03 m | P2 및 P2-2 안에 편대 전체 유지 |
|---|---|---|---|
| A −90°(시계방향) | 두 margin 모두 겹침 샘플0 | 0/91, 0/91 | 둘 다 아니오 |
| A +90°(반시계방향) | 겹침 샘플0 | 12/91(47°부터), 20/91(43°부터) | 둘 다 아니오 |
| B −90° | 겹침 샘플0 | 22/91(−69°부터), 28/91(−63°부터) | 둘 다 아니오 |
| B +90° | 겹침 샘플0 | 22/91(69°부터), 28/91(63°부터) | 둘 다 아니오 |

P2의 x범위는 [.7,1.85], P2-2는 x=[.7,1.85], y=[−1.5,−.2]다.
이는 공개 pickup region에서 계산한 **주문 위치 표기 영역**이며 충돌 벽이 아니다.
영역 밖으로 나간다는 사실과 장애물 충돌을 구분한다. s6 지도에는 대피용 `bay_1`이 없다.
s4의 passing bay를 s6에 가져오거나 P2를 그 bay로 취급하지 않는다.
영역 안에서만 조작해야 한다는 새 제약을 채택하려면 별도 설계 변경이 필요하다.
상대 로봇의 위치는 별도 동적 장애물이며 이번 두 운반자+화물 외 세 번째 로봇의 sweep은 미정이다.

## 5. 요청하는 설계 결정

**권고안은 A −90°를 후속 진단 후보로만 두는 것**이다. 원본 의미의 성립이나
물리 실행 승인을 뜻하지 않는다. A +90°/B에는 위 정적 반례가 있으므로 같은 초기 배치에서
즉시 적용할 후보로 채택하지 않는다. C는 조작 과제가 달라 별도 dev 설계가 필요하다.

| 결정 항목 | 이 PR의 상태 | 후속에서 고정할 내용 |
|---|---|---|
| pivot 방식·부호·고정점 | **선택 대기**, 권고 A −90° | 접점/차체/중앙 구분, 도착 XYyaw, 오차 허용, 전체 sweep |
| can 접근 범위 | **선택 대기**, 기본 카탈로그 any 보존 | 서쪽만으로 제한하려면 물리 근거 또는 명시적인 새 공통 계약·가설 수정 |
| 후퇴 | **선택 대기** | 누가 선택하는지(고수준 정책), 양끝 중 역할, 하중 지지/해제, 목표 영역·heading·거리·실패 종료 |
| 원본 의미 유지 | **미확정** | 선행 없는 성공 반례가 나오면 “순서가 필수” 주장을 폐기/수정. 원본 파일은 그대로 보관 |

코디네이터의 선택은 이 문서/PR에 남기고, 설계 고정 후 **별도 controller PR과 별도 사전 등록**으로
진행한다. 답이 없으면 권고를 확정 결정으로 취급하지 않는다. 원본 의미가 유지되지 않으면
새 ID의 dev에서 다른 문제를 시험할 수 있지만 원본 s6를 대체하거나 651–653 seed의 의미를 바꾸지 않는다.

## 6. 네 조건의 공통 실행 계약과 H2의 비교 대상

`no_comm/peer_ko/leader_ko/structured`는 controller·config·센서·자기 기억 버전·
하위 상태 enum 채널이 같아야 한다. 차이는 통신 허용 범위뿐이다. 같은 입력/관측과
같은 primitive 요청에는 같은 하위 동작을 적용하고, s6 ID나 조건 이름으로 분기하는 host 해법을
넣지 않는다. role→robot 배정/leader 배정은 코드 hash와 별도 기록한다. 배정은 고수준 정책의
명시적 출력으로 받고 host가 private state를 보며 양보자/파트너를 선택하지 않는다.

입력은 자기 RGB·정적 지도·공개 주문·자기 명령 이력·허용 수신뿐이다. 센서 on/off도 네 조건에서
동일하게 고정한다. 접촉·심판·실시간 정답·비공개 사건 시각·setup identity lookup은 평가/장면에만 둔다.
P09/T11의 정답 기하 경로는 runtime planner 입력이 아니다.

현 structured 필드는 `act,item,zone,role,passage,location_ref,state,confidence,observed_at_sim_s,reply_to`다.
단일 메시지에 조건식·순서열·인과 edge를 넣을 필드는 없다. 다만 `reply_to`, 상태 보고와
여러 메시지의 시간 순서·공통 자기 기억으로 **상호작용하며 순서를 만들어낼 가능성**은 있다.
필드가 없다는 이유만으로 structured가 어떤 순서도 수행할 수 없다고 단정하지 않는다.
현재 action log enum에도 `pivot`/`rotate`/`retreat` 전용 action은 없다. 이 enum은 기록 계약이며,
`goto`/`yield_passage`가 존재한다고 대응 하위 제어가 이미 지원된다는 뜻은 아니다.

| 바꿀 대상 | #254 H2 `peer_ko−structured`에 미치는 영향 |
|---|---|
| 네 조건 공통으로 일반적인 회전·후퇴 primitive 추가 | 실행 가능한 행동 집합이 달라진다. 새 controller/API/관측 종료·비용 버전을 고정하고 같은 네 조건에서 다시 비교해야 함. `rotate_then_retreat_then_extract_can` 같은 s6 해법 매크로는 순서를 미리 제공하므로 금지 |
| structured에 `after`/`if`/순서 graph 또는 동등한 새 enum 추가 | 비교 기준의 표현력이 달라진다. 기존 H2의 제한된 schema 대비를 그대로 주장할 수 없음. 새로운 schema·가설/해석·token/SIM 비용·버전으로 별도 사전 등록 필요 |
| 기존 schema에서 `reply_to`·상태 왕복만 사용 | schema를 확장하지 않아도 순차 조정할 수 있는지 실제로 시험. 자연어 이득을 가정하고 structured를 불필요하게 제한하지 않음 |
| 모든 조건에 순서/후퇴 완료를 알려주는 새로운 하위 상태 채널 | 공통이어도 실험 과제를 풀어줄 수 있음. 안전/동기화 최소 상태와 고수준 인과 정보를 분리해 검토. 상태 enum 변경도 연구 버전 변경 |
| can을 서쪽 전용으로 제한하거나 장애물/dev 배치를 수정 | 원본 문제와 다른 비교 대상. 원본은 보존하고 새 fixture의 의미·seed·성공 기준·H2 방향 예측을 따로 승인/등록 |

본 PR은 #254의 DRAFT나 H2를 수정하지 않는다. 재등록 때에는 네 조건별 override가 아니라
공통 controller/config/센서/기억/enum hash, role assignment, message schema, 모델/prompt·비용을
각각 고정한다. 이후 4조건 효과는 같은 소스의 새 코호트에서만 판정한다.

## 7. 코디네이터가 나중에 실행할 물리 확인과 cap

**이 설계 PR: 0 SIM초, 새 모델 호출0, 학생 trial0.** 아래는 설계 선택 후의 별도 작업이며
이 PR로 실행을 승인하거나 총 비용을 정하지 않는다. 도착 자세·pivot 중심·staging/접근 길이·
실패 종료가 아직 고정되지 않아 **후속 총 물리비용은 미산정**이다.
정상/실패 **2×900=1,800 SIM초는 기준 제안일 뿐**, 아래 셀 수나 전체 합계에 넣지 않는다.
반복·양쪽 실패 분기·각도/접근 대안·모델 호출 예산도 따로 정해야 한다.

| 후속 비교 | 같게 둘 것 / 바꿀 것 | 확인할 항목 | SIM cap 상태 |
|---|---|---|---|
| (i) 선행 없이 can 접근 | 원본 초기 배치·spawn/역할 배정·controller 고정. 빔 pivot/후퇴 없이 서쪽·다른 허용 heading 대안 | 접근·파지·회수의 실제 성공/미도달. 한 번의 성공은 그 조건에서 “선행 필수”를 반박. 실패만으로 필요성을 확증하지 않음 | 셀/후보당900초 제안, 정식 cap 미고정 |
| (ii) 고정한 pivot/후퇴 후 can 접근 | (i)와 같은 초기 상태. 채택된 pivot·후퇴만 수행 | 회전 자체, 하중 유지/안전 해제, 후퇴 도착, can 접근·회수. 후퇴 없음/있음 비교가 있어야 후퇴의 필요성도 구분 가능 | 900초 제안. staging+접근+조작+후퇴+회수 전체 포함 |
| (iii) pivot 한쪽 실패 | 같은 배치에서 end_neg 실패 / end_pos 실패를 각각 고정된 주입으로 확인. host가 실패 시각을 controller에 알리지 않음 | 어느 쪽에서나 양쪽 추가 구동의 유한 중단, 하중·주변 안전, 거짓 완료0. 정지 명령과 실제 정지는 별도 | 실패 셀당900초 제안. 주입/검출/종료 지연과 셀 수 미정 |

이 세 비교군을 “정상1+실패1” 두 셀로 압축하지 않는다. 새 정답 staging을 쓰면
`stage_probe/not_e2e_success`로 분리하고 원본 spawn 시작 결과를 대신하지 않는다.
장면/제공자 T01(P01), 혼합 주문 T02(P02), can skill T04, 역할 배정 T07,
빔 초기 접근 T08과 자기 위치 추정·공통 중단 계약의 지원 범위를 먼저 확인한다.
그 작업의 미병합 코드나 과거 단계 성공을 이 설계의 실행 준비 근거로 승계하지 않는다.

실행 전 공통 조건: 최종3D v3·walls_v3·표식0·weld OFF·cargo_noslip_v1,
커밋/입력/설정/모델/지도 hash 고정, 공용 잠금, 여유 디스크 확인, 유한 관리 세션.
자기 영상의 파지/회전/후퇴 추정과 평가의 실제 pose·접촉·안전/배송 판정은 분리한다.
cap 도달은 실패/미도달로 남기고 staging·관측·대기·실패 정리 SIM초까지 기록한다.
ENOSPC는 HOST_ERROR이며 기록을 지우거나 같은 결과 파일을 덮지 않는다.

raw는 primary `outputs/`의 실행별 새 경로에 저장한다. 관측·발행 명령·실제 모델 요청/응답,
종료 원인, 모든 할당 실행의 분모, 성공률·시간·명령·모델 호출/응답시간·비용,
실패 주입 시각과 평가 자료를 보존한다. 원본 hash를 확인하고 실패까지 새 TensorBoard snapshot에
등록·실제 로딩/영상/표시값을 확인해야 물리 검증 결과를 전달할 수 있다.
현재는 정적 문서·반례만 있으므로 TensorBoard의 물리 성공 scalar나 dashboard를 만들지 않았다.

## 8. 재현과 검증 범위

[audit.py](audit.py)는 기존 정적 카탈로그·keepout·편대 계산을 재사용한다. MuJoCo/모델 SDK import,
network connect, schematic 렌더를 차단한다. 출력 파일은 이미 있으면 거절한다.

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-s6-order-design/audit.py --output /tmp/t11-static-NEW.json
```

관련 검사는 [test_audit.py](test_audit.py)의 정상/오류/경계 반례와 기존
`tests/test_zone_scenario_feasibility.py`다. 실제 `build_call_input`에 대해 네 조건별로
비공개 배치·setup binding·사건 시각·심판/접촉만 바꾸고 공개 payload가 같은지 검사한다.
미래 controller 동작 비간섭·양측 안전 종료의 검증은 아니며 별도 controller PR의 fake가 필요하다.
로컬 pytest는 공용 잠금을 얻은 뒤 실행한다. 정확한 결과·환경·해시는 [VERIFICATION.md](VERIFICATION.md)에 기록한다.
GitHub의 정상 CI(ACT/local-model tests 포함)는 허용하며 취소나 `[skip ci]`를 쓰지 않는다.

## 참고 자료

- Refs [#221](https://github.com/kcm0127-dotcom/ugrp/issues/221), [#224](https://github.com/kcm0127-dotcom/ugrp/issues/224), [#218](https://github.com/kcm0127-dotcom/ugrp/issues/218).
- [P09 REQUIREMENTS (고정 SHA)](https://github.com/kcm0127-dotcom/ugrp/blob/dec67997815e4cdc564a9848ed6020eede45cbfa/experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md), [TASKS T11 (같은 SHA)](https://github.com/kcm0127-dotcom/ugrp/blob/dec67997815e4cdc564a9848ed6020eede45cbfa/experiments/2026-09-30-scenario-capabilities/TASKS.md).
- [본연구 DRAFT §H2](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md), [정적 feasibility 범위](../../docs/zone_scenario_feasibility.md).
- [can·beam 카탈로그](../../sim/zone_cargo.py), [기존 편대 footprint](../../harness/zone_team_footprint.py), [v3 파지 거리](../../sim/masterpi_robot_models.py), [v3 형상](../../sim/masterpi_geometry_v3.py), [v3 collision 생성](../../sim/masterpi_model_v3.py).
- [structured 계약](../../harness/zone_study_contract.py), [입력 생성](../../harness/zone_study_inputs.py), [최종 두 문 지도](../../maps/zones_final/zone_wide_two_doors_final_v1.json).
- 새 외부 논문·OSS·의존성 없음. 기존 Python·pytest와 저장소 정적 기하만 재사용. Drive 조회/업로드 없음.
