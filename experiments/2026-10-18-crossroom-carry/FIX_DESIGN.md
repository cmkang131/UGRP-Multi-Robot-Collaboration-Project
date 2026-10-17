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
(VisualGoalSearch)`에서 `_follow`/`_gap_cross` 오버라이드. vendored 정책
바이트는 수정하지 않고 provenance에 기반 커밋(c390105c2)과 오버라이드
범위를 기록한다.

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
수정: 색 성분이 metric 피팅까지 성공하더라도 **피팅 면적**이
`paint_min_area_m2` 미만이면 목적지 페인트로 받지 않는다.

- 근거: zone B footprint 0.6 x 1.4 = 0.84 m². long_beam blue band는
  0.018 x 0.0205 ≈ 3.7e-4 m² (약 2,300배 차이). 임계값 후보 0.05 m²
  (beam band 대비 135배, zone 대비 6%) — 근거 없는 "보수적" 값이 아니라
  두 알려진 기하 값 사이에서 고른 값임을 prereg에 기록한다.
- 미터 피팅 record에 `area_m2`가 있으면 그것을 쓰고, 없으면 component
  픽셀수·range·fisheye ray로 계산한 footprint를 기록한다.
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

## 작업 순서

1. `scripts/vgs_fix.py`(서브클래스) + `scripts/paint_area_filter.py` +
   `scripts/contact_recorder.py` 모듈과 단위 테스트.
2. `queue-stageA-fix.json` + `prereg-stageA-fix.json` + `check_current_stack`.
3. Stage B 게이트 종료 후 gcp3에서 preflight(2 starts 60 s) → 자체 gate(16×180).
4. 결과는 원본 재계수(Stage A 표와 같은 형식 + fix 항목 표)로 보고하고
   Stage A와 합산하지 않는다.
