# crossroom-stageA-fix — Stage A 실패 수정 설계 (2026-10-18)

Status: **설계 + 사전등록 준비**. 실행은 Stage B 게이트 이후. 별도 후보
`crossroom-stageA-fix`이며 Stage A/B, visgoal r4/B/C와 합산하지 않는다.

## 근거 (Stage A 원본 재계수)

Stage A(무적재, 180 Sim초, nworld=16, 16 서쪽 시작) 결과:

| 지표 | 값 | 근거 |
|---|---:|---|
| GT door_crossed | 1/16 | eval-only base crossing, 문 개구부 y 통과 조건 |
| 스킬 gap_cross 주장 | 9/16 | trace stage `gap_cross`/`gap_forward` |
| 허위 gap 주장 | **9/9** | gap 단계에 진입한 9개 전부 GT 문 통과 없음(e02는 gap 주장 없이 GT 통과) |
| 통과 시 lateral offset | -0.1634 m | e02, 문 중심 대비 base y 오차 |
| 통과 시 min jamb gap | **-0.1084 m** | e02, 문틀과 로봇 외곽 겹침(무적재 통과 예산 ±0.055 m) |
| 계획된 도착 | 1/16 (GT-inside 0) | e02, GT margin -0.0281 m |
| found(문 통과 전 포함) | 4/16 | e02, e05, e06, e07 (e05-07은 beam end-band 오탐 의심) |

원인 사슬: (a) 벽 따라가기에서 side wall foot이 3틱 사라지면 곧바로 gap으로
판정 → 픽업룸/코너에서 허위 gap → 잘못된 방에서 east_search. (b) 통과 시
문 중심 정렬 제어가 없어 문틀과 10.8 cm 겹침. (c) 근거리 파란 색 띠(beam
end band)가 페인트 크기 조건을 통과해 found 오탐. (d) 접촉 이벤트 미기록.

## 수정 후보 설계

새 후보 `crossroom-stageA-fix`는 **기본 off 토글 4개**로 구성하고, 실행
queue에서만 켠다. Stage A 원본 결과와 합산 금지, 자체 관문으로 판정한다.

### ① 양쪽 wall-face 확인형 gap 트리거 (`crossroom_gap_twosided_v1`)

현재: `_follow`에서 side wall이 3틱 없으면 즉시 `gap_cross`.
수정: gap 진입 전에 "문 형태"를 확인한다.

1. side wall을 최소 `gap_track_min_ticks`(12틱=1.2 SIM초) 동안 추적했던
   상태에서만 gap 후보가 된다(첫 코너/시작 직후 오탐 방지).
2. gap 후보 시점에 **같은 side 전방 섹터**(벽을 오른쪽으로 따라갈 때
   bearing -160°..-20°, range ≤1.6 m)에 wall foot이 계속 보여야 한다.
   실제 문에서는 문 건너편(북쪽 divider segment)이 전방 섹터에 남는다.
3. 위 조건이 3틱 연속 성립하지 않으면 gap 대신 `follow`를 유지하고
   side wall 재획득을 기다린다(회전 없음, bounded 10틱).
4. 허위/실제 gap 판정을 trace event로 남긴다: `gap_candidate`,
   `gap_confirmed`, `gap_rejected_front_missing`.
5. **합격 기준 아님(측정)**: 수정 후에도 GT 문 통과가 아니면 실패다.
   gap 주장 수와 GT 통과 수를 항상 병기한다.

구현 위치: `scripts/vgs_fix.py` 서브클래스 `FixedVisualGoalSearch
(VisualGoalSearch)`에서 `_follow` 오버라이드. vendored 정책 바이트는
수정하지 않고 provenance에 기반 커밋(c390105c2)과 오버라이드 범위를
기록한다. **구현 완료**: `gap_rejected_front_missing`/`gap_confirmed`
이벤트, `gap_claims/gap_confirmed/gap_rejected` 카운터.

### ② 문 중심 lateral 정렬 (`crossroom_door_align_v1`)

현재: 90° 회전 후 `gap_forward`가 front wall이 보이거나 16틱이면 직진해
문을 통과한다(lateral 제어 없음).
수정: 회전 완료 직후부터 문 중앙 정렬 루프를 둔다.

1. 현재 heading 기준 왼쪽/오른쪽 섹터에서 가장 가까운 wall foot(문틀
   남/북 segment)을 찾는다(각각 ≤1.0 m).
2. 두 점이 모두 있으면 횡오차 추정치 `lat = (r_left - r_right)/2`를
   계산하고, |lat| > 0.02 m이면 제자리 회전 대신 작은 조향(60 ms 펄스)
   으로 줄인다. 회전 중에는 전진하지 않는다(적재 시에도 안전).
3. 문틀 양쪽이 안 보이면 side wall foot 하나 + 문 폭(0.50 m) 기하로
   근사하되, 추정 불확실성(±0.04 m)을 event에 남기고 진행 여부를
   `align_uncertain`으로 표시한다.
4. 최소 jamb clearance 추정치가 `ROBOT_HALF_WIDTH_M + 0.02`(=0.215 m
   중심 여유 기준 0.02 m) 미만이면 정지 후 재정렬한다.
5. 통과 후 GT lateral offset/min jamb gap을 eval-only로 계속 기록한다.

**Stage B(적재)와의 관계**: 이 정렬 루프는 적재 시에도 필요하므로
`carry_mode`에서 전진 금지·회전 금지 규칙을 함께 둔다. 단 적재 실행은
별도 Stage B-fix 조건이고 이 후보(무적재)와 합산하지 않는다.

### ③ 근거리 blue end-band 오탐 거부 (`crossroom_paint_area_v1`)

현재: `MIN_COLOUR_PIXELS=600`(존 크기)만 확인하고, `floor_patch` 미터 피팅은
부가 조건이다. 근거리 파란 색 띠는 화면상 크게 보일 수 있어 600px 조건을
통과한다.
수정: 색 성분이 metric 피팅까지 성공하더라도 **metric extent**(피팅된
바닥점들의 대각 길이, `floor_patch` record의 `extent_m`)가
`PAINT_MIN_EXTENT_M = 0.15 m` 미만이면 목적지 페인트로 받지 않는다.

- 근거: long_beam blue band의 실제 footprint는 0.036 x 0.041 m
  (`zone_cargo.py` band half extents 0.018/0.0205) → 대각 0.054 m. zone B는
  0.6 x 1.4 m이므로 보이는 zone 패치의 extent는 최소 0.30 m. 임계값 0.15 m는
  두 알려진 기하 값 사이이며 gate episode로 조정하지 않는다.
- `extent_m`가 없는 record(피팅 실패/비피팅)는 필터하지 않고
  `not_measured`로 기록한다(오탐을 줄이는 필터이지 found를 늘리지 않는다).
- 오탐 거부는 trace event `paint_rejected_small_area`로 남긴다.
- 이 수정은 **found 오탐만 줄이는 것**이지 성공을 늘리는 것이 아니다.
  수정 후 found/pre-cross found와 GT 문 통과를 분리 보고한다.

### ④ collision_events 기록 (`crossroom_contacts_v1`)

현재: `collision_events`가 `not_measured`였다. 이유: 러너가 MJWarp 접촉
배열을 읽지 않았다(Draft §3.4 지표는 eval-only 접촉 rising edge를 요구).

확인: `mujoco_warp` Data에 접촉 관련 필드가 존재한다 —
`contact`, `nacon`, `naconmax`, `actuator_force`, `qfrc_constraint`,
`cqfrc_constraint`. 구현:

1. 각 control tick 뒤 `wd.nacon[w]`(world별 활성 접촉 수)를 eval-only로 기록.
2. `wd.contact` 구조체에서 geom id 쌍을 읽어 m.geom_bodyid로 r1 body와
   wall/cargo/peer/floor 범주로 분류한다(정확한 하위 필드 이름은 러너
   구현 시 확인 후 prereg에 고정).
3. 접촉 rising edge를 `collision_events`로 기록: tick, category, geom pair,
   blocked_object 이름, 최소 거리/접촉 여부. `blocked_object`는 wall 이름
   (`wall_divider_1`), cargo item id, `peer_r2/r3`, `floor` 중 하나.
4. 기록은 eval-only이며 제어기 입력으로 절대 전달하지 않는다.
5. `collision_events`가 0인 실행과 `nacon` 기록 실패를 구분한다
   (후자는 `contact_record_error`로 실패 라벨).
6. **구현 완료**: `scripts/contact_recorder.py` (nacon per world, rising edge
   에서 contact.geom/worldid를 읽어 geom category 분류; layout 불명이면
   `layout_unknown`/`errors`로 보고하고 추측하지 않음). 수정 후 preflight에서
   레이아웃을 확인해 필드 이름을 prereg에 고정한다.

### ⑤ 적재 시 화물 근접 가림 처리 (`crossroom_carry_occlusion_v1`, Stage B에서 측정)

Stage B 원본에서 적재 화물(빨간 box)이 자기 RGB 하단에 **화면 폭 전체 밴드**로
잡혀 근접 바닥 영역을 가린다. 그 결과 obstacle_avoid 이벤트 0(Stage A 4,736),
e00 obstacle 검출 0틱(Stage A 859틱), wall point zero 비율 3.3%(Stage A 1.7%)
였고 16/16이 허위 gap으로 픽업룸 east_search를 돌았다.
수정(적재 전용, 별도 조건):
1. **하단 밴드 마스킹/사용 금지**: held box로 판정된 색 성분의 bbox(화면 하단
   밴드)를 obstacle·wall·paint 검출 입력에서 마스킹하고, 마스킹 영역과
   비율을 trace에 기록한다. 마스킹은 "본 것"과 "가려서 못 본 것"을 구분하는
   evidence이지 정답 보정이 아니다.
2. **상단 영역 우선 검출**: obstacle/wall foot 검출 ROI를 마스킹되지 않은
   상단·중단 영역 우선으로 재구성하고, 가려진 근접 영역이 필요한 판단
   (문 앞 근접 wall foot)은 `blocked_by_cargo`로 표시해 추정값 대신 미관측을
   남긴다.
3. **화물 자세로 하단 시야 확보 여지 측정**: carry 자세(SEARCH arm + closed
   gripper)에서 box가 화면 하단 몇 %를 차지하는지, arm/wrist servo를 조금
   올린 자세에서 그 비율이 얼마나 줄어드는지 setup-only로 측정한다
   (perception ROI와 box footprint, 정답 미사용). 자세 변경은 별도
   토글·별도 조건이며 이 표에 근거를 남긴 뒤에만 켠다.
4. **loaded 전용 후보 `crossroom-stageB-fix` prereg**: 적재 monitor
   (`carry_state_own.py`)를 재사용하고 위 1-3을 기본 off 토글로 묶는다.
   Stage B baseline과 합산 금지, unloaded crossroom-stageA-fix 결과가 나온
   뒤에 실행한다. funnel은 Stage B와 동일하게 유지하고 `cargo_held` ·
   `blocked_by_cargo` · obstacle 검출 카운트를 추가 지표로 보고한다.

**반사실 검증 설계 (⑤ 전용, 별도 조건):** held-box mask의 효과는 상관·프레임·
코드조건만으로 주장하지 않는다. loaded 전용 후보 `crossroom-stageB-fix`를
**2-arm**으로 사전등록한다: arm M0 = Stage B baseline과 동일(마스크 off, 같은
starts·cap·monitor), arm M1 = 마스킹/상단 ROI/화물 자세 항목만 on. 두 arm은
같은 16 starts·180 Sim초·nworld16으로 실행하고 **결과를 합산하지 않는다**.
비교 지표: obstacle 검출 틱, wall-zero 비율, 허위 gap claim 수, GT door
crossing, arrived_declared, cargo_held 유지, `blocked_by_cargo` 비율. arm M0은
Stage B baseline의 재현이므로 baseline과 조건 차이가 없을 때만 비교 기준으로
쓴다. 이 반사실은 **무적재 fix gate에서는 box가 없어 측정할 수 없다** —
무적재 fix는 Stage A의 gap/정렬/오탐 수정만 측정하고, held-box mask는
`crossroom-stageB-fix` 카드에서 별도로 검증한다.

이 항목은 적재 전용 게이트(별도 조건)로 측정하고 무적재 fix와 합산하지 않는다.

## 사전등록(초안) — crossroom-stageA-fix

| 항목 | 값 |
|---|---|
| 조건 | 무적재, 16 서쪽 시작(N8+F8), 180 SIM초, nworld=16, s1 v7 전체 장면 |
| 호스트 | gcp3 (Stage A와 같은 호스트, 별도 조건) |
| 정책 | vendored Stage A 정책 + 위 4개 수정 토글 on (기본 off) |
| funnel | Stage A와 동일 + `gap_claim_vs_gt` 표(주장 n vs GT n), `collision_events` |
| 성공 기준 | 없음(측정). Stage A 대비: (a) 9/9 허위 gap 주장 감소, (b) 통과 시 |
|              | lateral offset/jamb gap 개선, (c) found 오탐 감소, (d) 접촉 기록 |
| 합산 금지 | Stage A, Stage B, visgoal r4/B/C, egonav, ACT |
| 입력 감사 | controller_boundary_v1 (기존) + 접촉 배열은 eval-only |
| 실행 순서 | Stage B gate 완료·정리 후. 새 freeze commit → preflight → gate |

## 구현 상태 (2026-10-18)

- `scripts/vgs_fix.py` — 양쪽 wall-face gap 확인 + 문 lateral 정렬 오버라이드.
- `scripts/paint_area_filter.py` — `extent_m` 기반 blue end-band 거부.
- `scripts/contact_recorder.py` — MJWarp nacon/contact geom 기반 eval-only 접촉 기록.
- `prereg-stageA-fix.json` / `queue-stageA-fix.json` / `stack-stageA-fix.json`
  — 동결 전 초안, `check_current_stack` admission pass.
- 단위 테스트 `tests/test_crossroom_carry.py`에 필터·접촉 recorder·queue 계약 추가.
- 다음: Stage B gate 종료 후 gcp3에서 fix preflight → 동결 커밋 → fix gate.

## 작업 순서

1. `scripts/vgs_fix.py`(서브클래스) + `scripts/paint_area_filter.py` +
   `scripts/contact_recorder.py` 모듈과 단위 테스트.
2. `queue-stageA-fix.json` + `prereg-stageA-fix.json` + `check_current_stack`.
3. Stage B 게이트 종료 후 gcp3에서 preflight(2 starts 60 s) → 자체 gate(16×180).
4. 결과는 원본 재계수(Stage A 표와 같은 형식 + fix 항목 표)로 보고하고
   Stage A와 합산하지 않는다.

## v3 addendum (2026-10-18, built from the recorded raw - not from gate outcomes)

### v3-a door gap acceptance (measured)

Stage A's 9 gap claims were all false. The wall points were recomputed offline
from the recorded frames + trace servo poses (`/tmp/vg3_analyze.py`) and the
ahead cone (|bearing| <= 20 deg, range <= 1.0 m) was measured at each claim:

| episode | front-cone points | jamb in 20-110 deg | real door? |
|---:|---:|---|---|
| e00 | 0 | no | no |
| e03 | 418 | no | no |
| e04 | 0 | no | no |
| e06 | 0 | no | no |
| e08 | 0 | no | no |
| e10 | 23 | no | no |
| e12 | 0 | no | no |
| e14 | 377 | no | no |
| e15 | 0 | no | no |

Rule v3: accept only if (a) side wall tracked >= 12 ticks, (b) ahead cone has
<= 10 wall points (an open doorway keeps the cone empty; a pickup-room wall
fills it with 377-418 points), (c) a jamb wall face exists on the followed side
in 20-110 deg within 1.3 m. Constants are between the measured classes (0/23
vs 377/418) and the authored door width 0.50 m; **all nine recorded false
claims are rejected by construction**. The true-door side is not exercised in
the recorded unloaded raw (the single GT crossing, e02, happened in `target`
stage while chasing visible paint, not through `gap_cross`), so v3's acceptance
side is a prediction to be measured by the gate, not a measured fact.

### v3-b zone-edge declaration check (own RGB)

The only recorded declaration outside zone B (fix v2 e02, t=79.9 s, GT margin
-0.0162 m) had the destination paint bbox bottom at 461/480 = **0.960** of the
frame. v3 requires the paint to reach >= 0.98 (bottom 2% band) before keeping
a declaration; otherwise it retracts and creeps forward at most 30 ticks
(3 SIM s), then force-declares with `zone_edge_force_declare`. Own RGB only;
the declared-stop GT margin remains eval-only.

### v3-c alignment

v1's two-jamb lateral estimate (tolerance 0.02 m, no forward motion while
misaligned) is kept; it is only exercised if v3-a accepts a real gap.

### Constants

`GAP_FRONT_CONE_MAX_POINTS=10`, `GAP_JAMB_RANGE_M_V3=1.3`,
`ZONE_EDGE_BOTTOM_NORM=0.98`, `ZONE_EDGE_MAX_RETRACT=30`; all justified above
from recorded raw + authored geometry, none tuned on a gate.
