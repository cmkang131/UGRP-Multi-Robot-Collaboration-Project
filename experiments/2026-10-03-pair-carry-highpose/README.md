# 높은 자세 공동 운반 후보 v96 (첫 등록 v93은 미실행 은퇴)

2026-10-03. D1의 새 학생 제어기 후보다. **MEASURED_SIM 경로는 #361 D5 계약을 통과하고 승인 목록에 오른 v92 실측 보정
이 없으면 실행을 차단한다(승인 목록은 비어 있음).** 별도 DEV_PILOT 경로는 등록된 정확한 sha256 하나만 받는
비확증 기능 시험이며 결과는 항상 FUNCTIONAL_DEV로, 확증·MEASURED_SIM 증거로 승격할 수 없다(아래 2차 대응).
기존 학생의 성공 판정은 승계하지 않는다. 렌더 수집과 P03 인수는 코디네이터가 수행한다.

현재 P03(seed 911, dock 시작 세 체크포인트)은 **기능 확인용 개발 재생(FUNCTIONAL_DEV_REPLAY)**이며
독립 표본 3개나 확증 자료가 아니다. 확증용 시작점은 별도 등록 파일에 고정했다(아래 P2-1).

## v98 통합 (2026-10-04, Claude) — 현재 상태

v98(`zone-final-pair-highpose-v98`, workflow 3.10.0)에 두 가지를 넣었다. v98 실행 기록은 이 통합 전까지 없었다.

- **자기 영상 문턱 재보정(floor_light_v1):** 별도 진단 작업(Track A)이 사용자가 고른 절차로 다시 정한 값을
  그대로 넣었다. 벽 띠 채도 상한 80→140, 벽 경계 단차 최소 10(새 검사), 프레임 대비 폭 15→1.0, 표준편차 3→0.22.
  값 파일은 `configs/calibration/own_image_gates_floor_light_v1.json`(sha256 `e71bbe4d…`)이고 v98 등록 파일과
  제공자 runtime_contract에 해시로 고정했다. 절차·합격 기준은 [보정 절차](../../docs/own_image_gate_calibration.md)에 있다.
  프레임 문턱은 4차 검토 뒤 v98 전용 모듈로 옮겼다(아래 "REVIEW_363 4차 대응"). 공용 `zone_pair_vision.py`는
  main과 바이트가 같고, 프로세스 전역 값(`use_gates`/`_CONTRAST`)은 없앴다.
  주의: 평가 분할에 이 PR의 DEV 탐침(`v96-dev-probe-raise_high-323fe3f9`) 영상이 들어 있다. v98은 DEV·승격 불가이므로
  막지는 않지만, 이 값으로 얻은 결과를 확증 자료로 쓰면 안 된다.
- **파지 시점 집게 시야 → 기록만:** 바닥 파지 자세에서 빔 점 18개 중 0개가 masterpi_v3 카메라 시야에 들어온다는
  진단에 따라(문턱이 아니라 기하 문제), 사용자의 "첫 E2E 집게 감시는 기록만" 결정 아래 코디네이터가 결정했다.
  닫기 전 준비 조건의 `grip_view_m2` 항과 닫은 뒤의 `GRIP_NOT_SEEN`을 v98에서만 기록만 한다(`applied=false`,
  등록 `grip_monitor.grasp_time_view=log_only_v98`). 파지 준비는 자기 명령 이력(닫기 명령 발행)과 고정 상태 채널로
  판단한다. 자기 위치 확인·자기 집게 열림 명령·프레임 유효성·정지 빔 간격·닫기 barrier·시간 초과와
  `GRIP_NOT_CONFIRMED`는 그대로다. 공유 동결 파일(`zone_pair_grasp.py`, `run_m2_pair.py`)은 바꾸지 않았다.
- **복구 동작은 아직 넣지 않았다**(관측기 수정이 폐루프에서 확인된 뒤).

### REVIEW_363 5차 대응 (검토 APPROVE `2745f1fb` 뒤 병합 전 후속, 2026-10-04)

- **상태(먼저 읽기):** 둘러보기의 σ 완화와 시작 상태 완화는 위치 추정 공분산이 일관적이라는 가정에 기대고 있다. 위치 추정
  일관성 수정(PF consistency)이 들어오기 전에는(8.7초 NEES r1 221, r2 741, 한도 13.8) 어떤 v98 실행도 승격할 수 없고 모든
  실행은 `FUNCTIONAL_DEV`로 남는다. 일관성 수정은 이 묶음의 마지막 커밋으로 넣는다(아래 결과 절).
- **시작 상태 완화의 진입 구멍 막기(발견 1, 조정자 규칙):** 묶음(group) 바닥값만으로는 상자 밖·여유 안에서 시작한 점이 깊이
  제한 없이 벽 상자로 들어갈 수 있었다. 검토자 측정: r2 8.7초 틱은 시작 부호 깊이 최악 -14.2 mm에서 휩쓸기 중 -18.9 mm까지
  (상자 밖에서 시작한 쌍이 들어감, 4.7 mm 더 깊음), 같은 r2 자세에서 `forward .2, left .2, turn -.3, 0.15초`는 -25.0 mm(50 mm
  벽의 가운데)까지 들어갔다. r1(`end_neg`)은 0.0 mm로 들어가지 않았다. 틱을 넘어서 쌓이는 한도는 없었다.
  새 규칙: 시작 때 벽 상자까지의 부호 거리(raw signed)가 0 이상인 쌍은 모든 휩쓸기 표본에서 0 이상이어야 한다(새로 들어가는
  것은 허용하지 않음, 여유 없음). 거부 이유는 `start_outside_pair_enters`. 상자 안에서 시작한 쌍의 "더 깊어지지 않기"(1 mm),
  묶음 바닥값, `EPS_M` = 1 mm는 그대로다. 함수 `enters()`로 분리해 돌연변이 시험(규칙을 끄면 검토자 명령이 다시 허용됨)을 둔다.
  - 결과: 검토자 명령은 거부(chassis 0 / `wall_west`, 시작 +9.64 mm → 표본 1에서 -3.9 mm). 기록된 r1 8.7초 첫 명령은 계속
    허용. **기록된 r2 8.7초 첫 명령은 이제 거부된다**(같은 쌍 +9.64 → 표본 2에서 -9.40 mm, 휩쓸기 최깊이 -18.9 mm). 새 진입이므로
    느슨하게 하지 않았다. 검토자 격자(6×5×5×3 명령, 두 자세)에서 완화가 허용한 명령 중 밖에서 시작한 쌍이 들어간 깊이는 이제
    두 자세 모두 0.0 mm다(r1 233개, r2 10개 허용).
- **빠져 있던 blind 중단 경로 시험:** `BLIND_GRIPPER_REOPENED`(`track.command`로 닫힌 집게를 다시 여는 명령),
  `BLIND_DISTANCE_EXCEEDED`(구간의 하강·수평 거리), `BLIND_TRACK_UNCERTAIN`(σ_xy·σ_yaw 한도, 오래된 기준점)을 더했다.
- **표현 정정:** `BLIND_DISTANCE_EXCEEDED`는 설정 점검(configuration sanity check)이다. 구간 거리는 고정 호버·잡기 자세에서
  계산되므로 실행 중에 바뀌지 않는다. 실제 보호는 명령 범위(envelope) 검사와 잡기 자세 정확 일치다.
- **보지 않는 구간과 짝 로봇 밀림:** `ace8b257` 폐루프에서 r1은 11.4초 동안 보지 않았고, 그동안 추적 σ_xy는 17.4 → 24.2 mm였다
  (한도 50 mm). 짝 로봇이 그 사이 빔을 밀어도 이 구간은 알지 못한다(평가 전용으로 그 구간 빔 xy 이동 0.0).
- **보정 문서:** [보정 절차](../../docs/own_image_gate_calibration.md) 5절 한계에 4차 흐림·가림 수치를 옮겼다.

### REVIEW_363 4차 대응 (검토 BLOCK 5970668877, 2026-10-04)

- **공용 동결 파일 복구:** `harness/zone_pair_vision.py`를 origin/main 바이트 그대로 되돌렸다(sha256 `cce72504…`).
  7623c4dc는 이 파일에 프로세스 전역 대비 문턱을 넣어 이전 번들의 고정 바이트(#352/#355 검사 21개)를 깨뜨렸다.
- **v98 전용 프레임 문턱:** `harness/zone_pair_highpose_frame_gate.py`. 얼린 규칙(신선도·JPEG·크기·어안 테두리·두 어두움
  규칙)은 그대로 옮기고 대비 폭·표준편차 두 값만 등록 파일 값(1.0, 0.22)을 쓴다. `FrameGate(15, 3)`이 기록 프레임 68개와
  합성 프레임에서 얼린 판정과 모두 같고, 등록 값과의 차이는 대비 때문에 거부되던 신선한 프레임에서만 난다(시험).
  적용 위치는 v98 클래스의 얼린 메서드 코드를 그대로 쓰되 개인 builtins로 묶어 그 안의
  `from harness.zone_pair_vision import ...`/`from harness.zone_pair_admission import readiness_snapshot`만 v98 값으로
  답한다(`PairExecution.step/arm_step`, `CommandGuard.preclose_check`, `PairCommandGuard.observe_standoff`,
  `PairGraspRelook._grasp`, `HighController._wait_close`, `ZoneOwnExecutor._ack/pair_readiness`). 모듈 전역·import 훅·
  `sys.modules`는 바꾸지 않는다. 입장 검사는 원래대로 `valid_frame`(ob 아님)을 쓴다. 등록 `frame_gate.profile`
  (`zone_pair_frame_gate_floor_light_v1_v98`)과 번들 소스 해시에 고정했다. 모든 MRO를 훑어 얼린 문턱 참조가 남지 않았는지,
  얼린 문턱을 호출하면 터지는 장치 아래에서 v98 경로가 동작하는지 시험한다. `run_pair_stage_probes.py`의 `image_valid_off`
  같은 모듈 패치는 v98에 닿지 않는다(이전 번들용 도구).
- **이름:** `PROVIDER_ID`와 PF source 접두사를 `…_v98`로 바꿨다. v96 DEV 기록(`v96-dev-probe-*-323fe3f9`)은 git SHA
  `323fe3f9`에서만 재현된다.
- **시험 준비 정답 표시:** 정적 사전분포 평균(실제 생성 위치)과 HIGH 진입의 `gripped`/`lifted` 주장·HIGH 기준 영상은
  교사 준비에서 온 정답이다. 코드(`TEST_SETUP_GT`), 제어기 기록(`stage_probe_entry`), `stage_probe_staging.json`에
  `test_setup_ground_truth: true`와 "정적 DEV 단계 검사 전용, E2E·코호트·사례 결과에 쓰지 않음"을 남긴다. align 진입은
  평소 둘러보기와 짝 입장(실제 자기 카메라 추정) 뒤 첫 제어기 틱에서만 일어나며 입장 문턱은 그대로다.
- **파지 시점 범위 정정:** 기록만으로 바뀐 것은 `grip_view_m2` 두 항(닫기 전 준비 항, 닫은 뒤 `GRIP_NOT_SEEN`)뿐이다.
  프레임 유효성 검사, `preclose_check`(정지 빔 간격, `BEAM_UNCERTAIN`), `GRIP_NOT_CONFIRMED`는 계속 동작한다. 바닥 자세에서
  `beam_track.estimate`가 무엇을 내는지는 아직 확인하지 않았다(닫기에 도달한 검사가 없다).
- **알려진 한계(추가 조정 없음):** 검토자의 오프라인 측정에서 프레임 수준 문턱(대비 폭·표준편차)은 옛 값·새 값 모두
  흐림(σ3/8/16), 가로 움직임 흐림 31/81 px, 세로 41 px, 열 폭 30/50 % 가림을 100 % 통과시켰다. 이 문턱은 흐림·가림
  탐지기가 아니며 원래도 아니었다. 30 % 이상 검은 가림을 거르는 것은 바뀌지 않은 어두움 비율 규칙이다. 열 수준에서는 새
  단계 검사가 옛 규칙보다 오답이 적지만(σ3 96 대 794, σ8 409 대 2734, 가로 31 px 245 대 902, 가로 81 px 781 대 1096),
  강한 흐림에서는 새 문턱도 오답이 많다: σ8에서 남은 592열 중 409열 오답, 가로 81 px 19 %, 흐림 없음 0.4 %.
  옛 규칙과 공유하는 남은 위험으로 기록만 하고 문턱은 더 바꾸지 않는다.

### 보지 않는 마지막 접근 (blind final approach, v98 초안, 2026-10-04)

- **문제:** 바닥 잡기 자세에서는 자기 손목 카메라에 빔이 한 픽셀도 보이지 않아(아래 `3358372e` 결과) 닫기 전 빔 추정이
  구조적으로 `None`이다. 카메라 위치·시야는 바꾸지 않는다.
- **방법(보고 나서 움직이기, look-then-move):** 열린 하강을 호버 자세(서보 807/1897/2187, 공구 높이 95 mm)에서 멈추고
  0.3초 안정화한다. 그 자리에서 바꾸지 않은 `preclose_check`와 새 가로 검사(빔 띠 가로 중심이 고정 잡기 선에서 3 mm 이내)를
  한다. 통과하면 정지 빔 추적에 "보지 않는 구간"을 열고, 고정 경로(7단계 × 0.12초, 수직 71 mm, 차체 이동 없음)와 0.3초
  안정화를 큐에 넣는다. 잡기 자세에서는 구간이 유지되는 동안만 확인 때의 빔 가설을 그대로 쓴다. 구간은 다음 중 하나면
  닫힌다: 시간 22.14초 초과, 내려간 거리 0.075 m 초과·수평 0.002 m 초과, 차체 이동, 시선(pan) 변경, 경로 밖 팔 명령,
  집게 다시 열기, 모르는 명령 종류, 구간 변경, 추적 불확실성(동결 한도 30초·50 mm·3°) 초과. 거리 한도는 설정 점검이다(구간
  거리는 고정 자세에서 계산됨). 실제 보호는 명령 범위 검사와 잡기 자세 정확 일치다. 입력은 자기 RGB·자기 명령
  이력·측정된 호버 카메라 모델뿐이다. 새 모듈 `harness/zone_pair_highpose_blind_close.py`, 등록 키
  `blind_final_approach.profile = zone_pair_blind_final_approach_v98`, 번들 `timing.blind_final_approach`.
  설계 원문은 [blind_final_approach_design_ko.md](blind_final_approach_design_ko.md), 조사 전문은
  [blind_final_approach_survey.md](blind_final_approach_survey.md), 오프라인 재생 스크립트는 `blind_final_approach_replay/`.
- **조정자 결정(2026-10-04)과 적용:**
  1. 번들 ID는 초안 v98을 유지하고 DEV 기록은 SHA로 구분한다. 검토자가 동결 전에 새 번호를 요구하면 모든 브랜치를 확인해 다음 빈 번호를 쓴다.
  2. 보지 않는 구간 22.14초를 유지한다(알려진 한계 아래).
  3. 호버 가로 검사(3 mm)를 바로 적용한다. 측정값은 0.06 mm지만 표본이 하나다.
  4. 호버 확인은 정렬 단계(`aligned_streak >= 2`)처럼 **연속 2개의 서로 다른 자기 프레임**이 통과해야 한다. 실패 프레임이 오면 0으로
     되돌리고, 같은 프레임을 다시 보면 세지 않는다. 구간은 마지막 통과 프레임에서 열린다. 재시도 상한 1.0초(`HOVER_CONFIRM_MAX_S`)는
     그대로이며, 상한을 넘긴 실패 프레임에서 `PREGRASP_HOVER_*`로 멈춘다(`HOVER_CONFIRM_FRAMES = 2`, `limits()`에 기록).
  5. 모르는 명령 종류는 구간을 닫는다(fail-closed, 유지).
  6. 실패 분류: `PREGRASP_HOVER_*` 4개 → `HOVER_NOT_CONFIRMED`, `PREGRASP_BLIND_*` 10개 → `BLIND_WINDOW_CLOSED`.
     공용 `harness/pair_stage_probe.py`의 분류표는 이전 검토 기록(`tests/fixtures/review_355_legacy.json`)이 바이트 해시로 고정하고
     있어 바꾸지 않았다. 대신 v98 실행기 `scripts/run_pair_highpose.py`에 `failure_cause()`를 두어 공용 표를 그대로 쓰고 새
     이름만 더한다. 결과 `controller_outcome.<로봇>.failure_cause`에 남는다(평가 쪽 표시, 원인 증명이 아님).
  7. 더 낮은 하강 자세의 카메라 보정은 미룬다.
  8. 시간 하한 표(`zone_pair_highpose_timing._grasp_s`)는 호버 정지(0.3초와 검사 틱)를 넣지 않았다. 여전히 하한이지만 약 0.4초
     작다. 300초 상한에는 영향이 없다. 표는 바꾸지 않았다(알려진 차이로 기록).
  9. `scripts/run_ci_tests.py`에 v98 시험 목록이 있어 `tests/test_highpose_blind_close.py`를 더했다.
  10. `raise_high_align` 폐루프 재실행: 두 로봇 모두 닫고 HIGH까지 갔다(아래 절).
- **알려진 한계:**
  - 짝 로봇 밀림: 보지 않는 22.14초 동안 짝 로봇이 늦게 닿아 빔을 밀어도 이 구간은 알아채지 못한다. 짧은 상한(예: 3초)과
    호버 재확인은 대안으로만 남겼다(결정 2). `ace8b257`에서 r1은 11.4초 보지 않았고 추적 σ_xy는 17.4 → 24.2 mm(한도 50 mm)였다.
  - 호버 가로 검사 허용치(3 mm)는 정렬 허용치를 그대로 쓴 것이고, 측정 근거는 한 표본(0.06 mm)이다.
  - 닫은 뒤 자기 집게 감시는 여전히 기록만이다(`grip_loss_after_close: log-only`).

### 이어가기 단계 검사 `align_to_carry` (`d5ca2ec3`, 2026-10-04)

조정자 결정(2026-10-04): HIGH staged 진입(`high_hold_staged`, `carry_leg_staged`)은 **보류(parked)**한다. 코드는 두되 실행하지 않고
집계하지 않는다(`staging.PARKED`). 적재 자세에서 둘러보기를 넣으면 시험 준비 정답이 더 늘어나기 때문이다. 대신 raise_high_align과
같은 진입에서 HIGH 유지와 운반 구간까지 이어가는 `align_to_carry`를 더했다. 상한은 SIM 300초이고, 두 로봇이 `done` 상태에 이르면
끝난다(실행기 `terminal_state`). 운반은 제어기가 실제로 도달한 상태에서 시작하며 하네스가 넣은 적재 상태가 없다.

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, 모델 호출 0, 조정 PID 60799, 부하 8.2 → 20.3).

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 실패 | 닫기/들기/HIGH | 운반 | 배달(평가 전용) |
|---|---|---|---|---|---|---|---|
| align_to_carry | FAILED | 98.65 | 1933/2214 | r1 `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT` 99.9초, r2 `PARTNER_ABORT` | 64.7초 / 65.9초 / 84.8초 | 운반 barrier 미준비, 이동 없음 | 아니오(빔 0.115 m에 들린 채 제자리, 손가락 4개 접촉) |

- 닫기·들기·HIGH까지는 raise_high_align과 같다(호버 2프레임, 닫기 때 보지 않은 시간 r1 11.4초·r2 1.4초, 완화·거부 0).
- **새 막힘:** `wait_carry`에서 두 로봇 모두 15초 동안 `barrier_report carry ready=false, reason="HIGH edge reference pending"`만
  보냈다. 제공자의 `beam_edge.available()`이 한 번도 참이 되지 않았다(`harness/zone_pair_highpose_runtime.py` 276–282).
- **원인(자기 RGB만으로 오프라인 재생):** `harness/own_beam_edge.edge_line()`이 HIGH 자세의 모든 프레임(r1·r2 각 302장)에서
  None을 냈다. 빔 띠의 아래 경계는 r1 90열 중 85열(r2 80열)이 한 직선 위(169–171행)에 있다. 그런데 오른쪽 끝 5열(r2 10열)은
  첫 띠 구간이 79–80행에서 끝난다. 함수는 모든 열로 최소제곱 직선을 한 번 맞춘 뒤 4 px 안의 열만 남긴다. 이 이상치 열이 직선을
  기울여(기울기 −0.078) 남는 열이 25개뿐이고, 필요한 54개에 못 미친다. 남는 85열로 다시 맞추면 잔차 RMS가 0.5 px이다.
  즉 영상에는 경계가 분명하지만, 한 번만 하는 최소제곱 정리가 이상치에 약해서 실패한다.
- `own_beam_edge.py`는 v6e 공용 모듈이라 고치지 않았다. 처방과 적용 범위는 조정자 결정 사항이다. 표준 방법은 이상치에 강한 직선
  맞춤(RANSAC, 중앙값 기반 맞춤 등)이다. 또 기울기→상대 yaw 비율(`slope_to_yaw_ratio`)은 v6e 낮은 운반 자세의 기록에서 정한
  값이므로, HIGH 자세에 그대로 맞는지도 따로 확인해야 한다.
- TensorBoard: `outputs/tensorboard/1004f-v98-dev-probe-align-to-carry-d5ca2ec3`(기준선 `1004d…/raise_high_align-ace`), 보기 설정 키
  `v98_dev_probe_align_to_carry_d5ca2ec3_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-d5ca2ec3`
  (로컬 보관, 원격 백업 아님).
- raise_high(처음부터)는 위치 추정 과신 수정이 들어온 뒤 다시 돌린다(조정자 결정, guard는 그대로).

### 시작 상태 완화 뒤 단계 검사 4개 (`0865a788`, 2026-10-04)

둘러보기 수정 + 보지 않는 마지막 접근 + 시작 상태 완화(+ 거부 기록)를 모두 넣은 코드다. 조건은 앞과 같다(seed 911, before_door,
DEV_PILOT `398372ae…82f5`, floor_light_v1, weld OFF, 모델 호출 0, SIM 슬롯 4개 동시, 조정 PID 50163). 이 실행 동안 다른 작업 때문에
호스트 부하가 매우 높았다(시작 18.9–22.0, 끝 21.4–264). SIM 시간 실험이라 판정에는 쓰지 않고 기록만 한다.

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 | 닫기/들기 | 완화·거부 |
|---|---|---|---|---|---|---|---|
| raise_high(처음부터) | FAILED | 7.75 | 203/202 | 59/33 | r2 `PAIR_COLLISION_GUARD` 9.0초, r1 `PARTNER_ABORT` | 없음 | 완화 r1 4회·r2 3회(8.7–8.9초), 거부 r2 1회 |
| raise_high_align | **REACHED** | 83.55 | 1932/2213 | 200/167 | 없음 | 닫기 64.7초, 들기 65.9초, HIGH 84.8초 | 없음(0/0) |
| high_hold_staged (보류, 집계 안 함) | NOT_REACHED | 60.0 | 0/0 | 0/0 | 없음(입장 실패) | 없음 | 없음 |
| carry_leg_staged (보류, 집계 안 함) | NOT_REACHED | 150.0 | 0/0 | 0/0 | 없음(입장 실패) | 없음 | 없음 |

- **raise_high:** 시작 상태 완화가 8.7초의 첫 접근 명령을 두 로봇 모두에 허용했다(작성자 반사실 재생과 같다). 0.3초 뒤 9.0초에
  r2의 전진 명령(forward 0.119, 0.15초)이 다시 막혔다. 완화 거부 이유는 `inside_pair_deeper`이다. r2의 추정 뒤 왼쪽 차체 모서리
  (몸체 좌표 −0.15, −0.09 m)가 `wall_west` 벽 상자 안(부호 거리 −0.17 mm)에서 시작하고, 첫 표본에서 −9.7 mm로 더 깊어진다.
  묶음 바닥값 규칙(−43.0 → −43.0 mm)은 통과했지만, "벽 상자 안에서 시작한 점은 더 깊어지면 안 된다"는 점마다 규칙에 걸렸다.
  평가 전용으로 본 9.0초의 실제 r2 위치는 (−0.8924, −0.8497), 추정은 (−0.9269, −0.8778)이다. 오차는 약 44 mm, 추정 std_xy는
  2.6 mm(약 17σ)다. 이 실패는 **알려진 위치 추정 과신 문제 때문**으로 본다. 지시대로 고치지 않았다(다른 작업자 담당).
- **raise_high_align:** `ace8b257`과 결과가 같다. 두 로봇의 자기 명령 기록(`commands.jsonl`)이 바이트까지 같다(r1 `859b2a60…`,
  r2 `18864d91…`). 이 경로에서는 완화와 거부가 한 번도 일어나지 않았다. 호버 확인 2프레임(r1 1039→1041, r2 1239→1241),
  닫기 때 보지 않은 시간 r1 11.4초·r2 1.4초, 평가 전용으로 손가락 4개 접촉·빔 높이 0.115 m·기울기 0.03°.
- **high_hold_staged / carry_leg_staged:** 앞(`b37c9270`)과 같이 짝 입장에서 막혔다. `gate_ok` 거짓 1200회/3000회, std_xy
  0.21–0.22 m, 측정 갱신 0, 명령 0. HIGH 진입은 둘러보기를 건너뛰어 측정이 없으므로 구조적으로 막힌다. 진입 방법은 조정자 결정
  대기다. 시작 빔 높이 0.115 m는 시험 준비(정답 표시 `TEST_SETUP_GT`)이며 결과가 아니다.
- 두 로봇의 위치 추정기 `localizer_stats.updates`가 0인 것도 그대로다(별도 진단 중).
- TensorBoard: `outputs/tensorboard/1004e-v98-dev-probes-0865a788`(기준선 `1004c…/raise_high-335`, `1004d…/raise_high_align-ace`),
  보기 설정 키 `v98_dev_probes_0865a788_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-0865a788`
  (로컬 보관, 원격 백업 아님).

### 짝 guard 거부 기록과 시작 상태 완화 (v98 전용, 다른 작업자 diff, 조정자 결정 2026-10-04)

- **원인(작성자 오프라인 재생, `3358372e` raise_high 8.7초):** 두 로봇이 정해진 도킹 위치에서 시작한다. 그 자리에서 이미
  일부 몸체 점·벽 쌍이 guard 여유(기본 20 + 잔차 15 + 패드 5 mm + σ 항) 안쪽에 있다. `PairSweepGuard.motion_clear`는
  움직이지 않은 첫 표본도 검사하므로, 벽에서 멀어지는 명령까지 모든 명령을 거부했다. r1은 뒤 왼쪽 차체 모서리와
  `wall_west` 사이가 -55.3 mm였고 명령은 -55 → -28 mm로 멀어지는 쪽이었다(실제 간격 34 mm, 평가 전용, 접촉 없음).
- **변경(diff `guard_veto_log_start_relief_v98.diff`, sha256 `448c92cd…`):**
  - `harness/zone_pair_highpose_guardlog.py`: 모든 짝 guard 거부를 `pair_collision_guard_veto`로 기록한다(막힌 명령,
    guard가 쓴 자기 위치·공분산, 실패한 항). 관찰만 하고 판정은 동결 guard와 비트 단위로 같다.
  - `harness/zone_pair_highpose_start_relief.py`: 동결 guard가 "막힘"이라고 한 뒤, 그리고 시작 표본에서 이미 음수인 쌍이 있을
    때만 실행한다. 시작 때 여유 밖이던 쌍은 지금처럼 모든 표본에서 0 이상이어야 한다. 시작 때 여유 안쪽이던 쌍은 바닥값보다
    나빠지면 안 된다. 벽 상자 안에서 시작한 점은 더 깊어지면 안 된다. 벽 상자 밖에서 시작한 점은 상자에 들어가면 안 된다(5차
    대응에서 추가, `start_outside_pair_enters`). 허용하면 `pair_collision_guard_start_relief`를 남긴다.
    팔·전이 검사, 여유, 패드, 이득은 그대로다. 입력은 자기 위치 추정·자기 발행 명령·정적 지도뿐이다.
- **조정자 결정:** `SCOPE='group'`(모듈 기본값), 여유 `EPS_M` = 1 mm. 바닥값은 그 (부위, 벽) 묶음의 시작 최악값 − 1 mm다.
  **글자 그대로의 "점마다 나빠지지 않기"(`'pair'`)보다 약하다.** r2는 추정 뒤 모서리가 50 mm 벽의 반대쪽 면 너머 9.6–14 mm에서
  시작한다. 이것은 위치 추정이 약 48 mm 틀려서 생긴 물리적으로 불가능한 상태다. 점마다 규칙을 쓰면 7쌍이 최대 14.2 mm
  나빠져 r2가 멈춘다. 묶음 규칙에서는 최악값이 -42.6 → -42.7 mm(0.09 mm, 회전 지렛대 항)라서 1 mm 여유 안에서 허용된다.
- **알려진 문제(여기서 고치지 않음, 다른 작업자 담당):** 위치 추정이 지나치게 자신 있다. 8.7초에 NEES(2자유도)가 r2 741,
  r1 221이다. 99.9 % 카이제곱 한도 13.8보다 훨씬 크다(평가 전용 비교). 자신 있게 틀린 추정이 벽 쪽으로 39 mm 틀리면 어떤
  여유도 소용없으므로, 이 완화는 추정을 믿지도 고치지도 않는다.
- 작성자 결과(`ace8b257`+diff): 관련 시험 323 passed, `test_review_*` 412 passed. 반사실 재생에서 8.7초의 첫 접근 명령 두 개가 모두
  허용됐다. 이 작업 트리에서 다시 돌린 결과(`0865a788`): `test_review_*` 412 passed, highpose·경계 225 passed, 둘러보기·blind·
  완화·거부 기록·CI·heldout 211 passed. 새 시험 두 파일은 CI 목록에 넣었다. 커밋 `0865a788`.

### 보지 않는 마지막 접근 폐루프 단계 검사 (`ace8b257`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT `398372ae…82f5`, floor_light_v1, weld OFF, SIM 슬롯
`sim-claude-v98-raise-high-align`, 조정 PID 41085, 시작 부하 11.8, 끝 부하 13.5). 모델 호출 0.

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 |
|---|---|---|---|---|---|
| raise_high_align | **REACHED** (두 로봇 `high_carry_pose` 84.8초) | 83.55 | 1932/2213 | 200/167 | 없음 |

| 로봇 | 호버 확인(프레임, 통과/연속) | 띠 가로 중심 | 경로 큐 | 닫기 barrier | 닫기 때 보지 않은 시간 | 최대 |
|---|---|---|---|---|---|---|
| r1 | 1039 통과(1) → 1041 통과(2) | 0.05 mm | 53.3초 | 64.7초 | 11.4초 | 11.9초(65.2초, 닫기 램프 끝) |
| r2 | 1239 통과(1) → 1241 통과(2) | 0.43 mm | 63.3초 | 64.7초 | 1.4초 | 1.9초 |

- **닫기가 일어났다.** 두 로봇 모두 호버에서 연속 2프레임 확인(허용 3 mm) 뒤 고정 7단계로 내려갔다. 잡기 자세의
  `preclose_beam_guard`는 `evidence=blind_after_hover_confirmation`으로 통과했고 거부(`PREGRASP_HOVER_*`/`PREGRASP_BLIND_*`)는
  0건이다. 이어서 lift(65.9초) → HIGH 상승(67.5초) → `high_carry_pose`(84.8초, 자기 명령 이력으로 판단)까지 갔다.
- **r1은 짝을 11.4초 동안 기다리며 보지 않았다.** r1이 먼저 내려갔고(53.3초) r2는 10초 늦게 도착했다. 상한 22.14초 안이다.
  이 구간이 결정 2의 "짝 밀림" 위험이 실제로 생기는 시간이다. 이번 실행에서는 평가 전용 기록으로 빔 수평 이동이 0.0 mm였다.
- **평가 전용 확인(제어에 쓰지 않음, `eval_only/`):** 84.8초에 손가락 4개(r1·r2 좌우)가 모두 빔에 닿아 있고, 빔 높이는
  0.115 m(시작 0.0005 m), 기울기 0.03°다. 로봇끼리 접촉 0건, `active_weld_ids` 항상 빈 목록(weld OFF).
  이것은 단계 검사 결과이며 사례 결과나 E2E 성공이 아니다.
- **같이 본 것:** 두 로봇의 위치 추정기 `localizer_stats.updates`가 0이다(`scan_updates` r1 319, r2 489). 이 값의 의미는
  별도 진단 작업이 보고 있다. 여기서는 판단하지 않는다.
- TensorBoard: `outputs/tensorboard/1004d-v98-dev-probes-ace8b257`(기준선 `1004c…/raise_high_align-335`),
  보기 설정 키 `v98_dev_probes_ace8b257_20261004`(고정 카드 8개 링크 포함). raw는
  `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-ace8b257`(로컬 보관, 원격 백업 아님).

### 둘러보기 수정 뒤 폐루프 단계 검사 (`3358372e`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, SIM 슬롯 따로, 조정 PID 24124, 시작 부하 24.6/23.0).

| 검사 | 상태 | 도달한 곳 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 |
|---|---|---|---|---|---|---|
| raise_high(접근 포함) | FAILED | 두 로봇의 둘러보기가 7.8초에 함께 끝났다(LOOKED, r1 std 0.0072 m). 합류를 통과해 7.85초에 짝 작업을 시작했고 approach에 들어갔다. | 7.45 | 200/199 | 53/27 | r1 `PAIR_COLLISION_GUARD` 8.7초(approach 0.85초째), r2 `PARTNER_ABORT` |
| raise_high_align | FAILED | 평소 둘러보기(7.8초, LOOKED)와 입장을 마쳤다. 그 뒤 자기 접근 → align → standoff(빔 9968점 관측) → 열린 하강까지 가서 54.1초에 `wait_close`에 **도달**했다. | 52.85 | 1443/1261 | 200/147 | r1 `preclose_beam_guard` `BEAM_UNCERTAIN` → `PREGRASP_NOT_READY`, r2 `PARTNER_ABORT` |

- **둘러보기 수정은 폐루프에서 확인했다.** 7623c4dc에서는 r2가 끝나지 않아 `PAIR_RENDEZVOUS_TIMEOUT`이 났다. 이번에는 두 로봇이 같은 시각(7.8초)에 끝났고 합류를 통과했다. 5초 합류 시계는 바꾸지 않았다.
- **raise_high의 새 막힘:** approach 0.85초째에 명령 guard가 `PAIR_COLLISION_GUARD`로 멈췄다. 이 guard는 막은 명령을 기록하지 않아(`zone_pair_guards.py` 772–789) 팔·시선 계획과 이동 간격 중 어느 쪽인지 raw로는 가릴 수 없다. 이 검사 경로가 실행된 것은 v98에서 처음이다(앞 실행은 합류 전에 끝났다). 새 둘러보기 guard는 둘러보기 틱 밖에서는 부모와 같이 계산한다(hint 없음 → `PairArmGuard`). 원인 진단은 아직 하지 않았다.
- **raise_high_align의 닫기 거부(조정자 지시 4번 조건에 해당, 여기서 멈춤):** 닫기 시점의 r1 상태를 자기 RGB와 자기 명령 이력만으로 오프라인 재생했다(`replay_preclose_3358372e.py`, 검사 출력의 frames·commands).
  - 빔 추적의 불확실성은 한도 안이었다: std 0.019 m(한도 0.05), 0.024 rad(한도 0.052), 나이 2.3초(한도 30).
  - 바닥 파지 자세(서보 3/4/5 = 1269/2052/2494)의 자기 영상(frame 1057)에는 빔 색 점이 **0개**였다(필요 60). 영상 전체가 바닥이고, `close_grip_view`도 빔 비율 0이었다.
  - 그래서 `beam_track.estimate`는 "보이는 조각 일치 검사"에서 None을 냈다. 직전 standoff 영상(frame 1011)에서는 9911점이 보였다.
  - 즉 `preclose_check`는 바닥 파지 자세에서 구조적으로 통과할 수 없다(카메라 기하, 문턱 문제 아님). 지시대로 고치지 않았다. 조사와 v98 전용 설계("보일 때 확인 후 자기 명령으로 마지막 접근")는 조정자가 다른 작업자에게 맡겼다. `PAIR_COLLISION_GUARD` 진단(막은 명령 기록 포함)은 Track A가 맡는다.
- 닫기에 도달하지 못해 P03 3×300은 시작하지 않았다. TensorBoard: `outputs/tensorboard/1004c-v98-dev-probes-3358372e`(기준선 7623c4dc raise_high), 보기 설정 키 `v98_dev_probes_3358372e_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-3358372e`(로컬 보관)이다.

### r2 늦은 둘러보기 수정 (Track A, v98 전용, 조정자 승인 2026-10-04)

- **원인(7623c4dc raise_high):** r2의 시작 둘러보기는 1.95–8.2초 동안 팔을 움직이지 못했다. 공용 팔 guard가 위치 불확실성을 방향 없이 `std_xy = √(trace Σ)`(2.0초에 0.47 m, 거의 모두 y축)로 계산해 `wall_west`와의 간격에서 뺐기 때문이다. 동쪽을 보는 r2는 y를 관측하지 못하지만, 이 벽의 법선은 x이고 그 방향 σ는 0.048 m였다. 기다리는 틱마다 `hold`가 두 번 나가는 문제도 있었다(`[hold] + [hold]`).
- **수정:** `harness/zone_pair_highpose_lookaround.py`.
  - `LookAroundGuard(PairArmGuard)`는 팔 간격의 위치 항을 장애물 법선 방향 σ로 계산한다: `min(std_xy, √2·√(nᵀΣn))`. Σ는 그 틱의 자기 추정 공분산이다.
  - 둘러보기 틱의 첫 `hold` 중복을 없앤다.
  - 공용 `zone_own_executor.py`·`zone_own_guards.py`·`zone_final_pair_guards.py`는 바꾸지 않았다. `adopt_v98_frame_gate`가 행위자 클래스와 guard 클래스를 바꾸고, `record()['own_image_gates']['look_around']`에 남긴다.
- **guard 의미 변경(명시):** 둥근 추정과 법선 방향으로 긴 추정은 공용 guard와 비트 단위로 같게 계산한다. 법선을 가로지르는 방향으로 긴 타원일 때만 여유를 덜 뺀다. 공용 guard보다 더 빼는 경우는 없다. yaw 항, 기본 여유, residual, 0.15 m 상한, 차체 간격, 후진 이동 검사는 그대로다. 조정자는 이것을 표준 기회 제약 여유로 보고 승인했다(사용자 9/29 guard 완화 허용). 정답 위치는 쓰지 않는다.
- **오프라인 확인(Track A, 폐루프 아님):** 기록된 r1/r2 추정을 지연 제공자로 재생했다.
  - 공용 guard는 r1을 2.00–2.05초(2틱), r2를 1.95–8.20초(126틱) 동안 막았다.
  - 새 guard는 1.95–9.0초의 모든 틱을 통과시켰다. 최소 여유 포함 간격은 r1 28 mm, r2 20 mm이다.
- 5초 합류 시계는 바꾸지 않았다. 폐루프 확인은 `raise_high` 재실행으로 한다.

### v98 DEV 단계 검사 재실행 (`b37c9270`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, SIM 슬롯 따로, 조정 PID 16310, 시작 부하 18.6/15.1). 둘러보기 합류에 기대지 않는 두 HIGH 검사만 돌렸다. `raise_high`·`raise_high_align`은 Track A의 r2 둘러보기 수정을 기다린다.

| 검사 | 상태 | 멈춘 곳·이유 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 입장 거부 r1/r2 |
|---|---|---|---|---|---|---|
| high_hold_staged | NOT_REACHED | 제공자 실패가 사라졌다(`own_history` 18행, 두 로봇 `loaded_by_rule=true`). 그러나 짝 입장이 끝까지 `gate_ok=false`다(std_xy 0.21–0.22 > 0.05). | 60.0 | 0/0 | 0/0 | 1200/1200 |
| carry_leg_staged | NOT_REACHED | 위와 같다. | 150.0 | 0/0 | 0/0 | 3000/3000 |

- **적재 상태 수정은 동작했다.** 7623c4dc의 `UNMEASURED_V3_CAMERA_POSTURE unloaded` 실패가 없어졌다.
- **HIGH 진입도 바닥 진입과 같은 이유로 입장에서 구조적으로 막힌다.** 시작 사전분포 std 0.15 m를 쓰고, 빔을 든 팔을 움직이지 않으려고 둘러보기를 생략한다. HIGH 자세에서는 벽이 보이지 않아 측정 갱신이 0이다. 입장 문턱(std ≤ 0.05)을 완화하지 않는 한 넘을 수 없다. 어떻게 진입할지는 조정자가 정한다. 예를 들어 HIGH 진입도 폐기하고 `raise_high_align` 연속 실행으로 대신할 수 있다. 문턱은 바꾸지 않았다.
- 닫기에 도달한 검사가 없어 `preclose_beam_guard`·`beam_track.estimate` 기록은 아직 없다.
- TensorBoard: `outputs/tensorboard/1004b-v98-dev-probes-b37c9270`(2개 실행, 기준선은 같은 검사의 7623c4dc 실행), 보기 설정 키 `v98_dev_probes_b37c9270_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-b37c9270`(로컬 보관, 원격 백업 아님)이다.

### v98 DEV 단계 검사 결과 (`7623c4dc`, 2026-10-04)

조건은 seed 911, `zone_wide_door_geometry_v3` before_door, DEV_PILOT, floor_light_v1, weld OFF이며 SIM 슬롯을 따로 썼다(조정 PID 94817). 다섯 개 모두 단계에 도달하지 못했다. 단계 검사 결과는 사례 결과가 아니다.

| 검사 | 상태 | 멈춘 곳·이유 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 집게 기록 |
|---|---|---|---|---|---|---|
| raise_high(접근 포함) | FAILED | r1이 8.3초에 둘러보기를 끝냈다(LOOKED, std 0.0066 m). r2의 둘러보기는 1.95–8초에 정지 명령만 두 배 속도로 내다가 약 6초 늦게 패닝을 시작했고 끝나지 않았다. r1은 13.35초에 `PAIR_RENDEZVOUS_TIMEOUT`으로 끝났다. | 12.1 | 303/417 | **139/23** (323fe3f9: 0/4) | 파지 전이라 없음 |
| raise_high_staged | NOT_REACHED | 짝 작업 입장에서 `gate_ok=false`가 50 ms마다 1800번 나왔다. 시작 사전분포 std 0.15 > 0.05이고, 둘러보기를 생략했으며, 바닥 자세에서 측정이 0이다. 명령 0. | 90.0 | 0/0 | 0/0 | 없음 |
| raise_high_closed | NOT_REACHED | 위와 같다. | 90.0 | 0/0 | 0/0 | 없음 |
| high_hold_staged | NOT_REACHED | 33.5초에 제공자가 `UNMEASURED_V3_CAMERA_POSTURE unloaded:896,2035,1894,1500`로 실패했다. 정적 준비가 적재 상태를 넣지 않았다(시험 준비 누락). 입장 `gate_ok=false`도 함께 나왔다. | 60.0 | 0/0 | 0/0 | 없음 |
| carry_leg_staged | NOT_REACHED | 위와 같다. | 150.0 | 0/0 | 0/0 | 없음 |

- **관측기 수정의 폐루프 효과:** 접근을 포함한 실행에서 r1 측정 갱신이 0에서 139로 늘었고, 두 로봇 모두 둘러보기 결과가 LOOKED_POSE_UNCERTAIN에서 LOOKED로 바뀌었다. 새 막힘은 r2 둘러보기의 늦은 시작이다(Track A 영역이라 손대지 않았다).
- **정적 진입 검사는 구조적으로 막혀 있다.** 시작 사전분포 정의, 둘러보기 생략, 입장 완화 금지를 함께 지키면 입장 문턱(std ≤ 0.05)을 넘을 수 없다. HIGH 진입은 적재 상태도 넣어야 한다. 어느 쪽으로 바꿀지는 조정자가 정한다.
- 차단 실패가 있어 P03 3×300은 시작하지 않았다. TensorBoard는 `outputs/tensorboard/1004-v98-dev-probes`(5개 실행, 기준선 v96 raise_high)에 넣었다. raw 위치는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-7623c4dc`(로컬 보관, 원격 백업 아님)이고 파생 뷰는 `outputs/v98-dev-probe-tbviews-1004/gen_views.py`다.

### 단계 검사 설계 수정 (조정자 결정 2026-10-04, 시험 준비만)

- **바닥 진입 2개 폐기(`DROPPED`):** `raise_high_staged`와 `raise_high_closed`는 시작 사전분포 std 0.15 m, 둘러보기 생략, 바닥 자세 측정 0 때문에 짝 입장(std ≤ 0.05)을 끝까지 넘지 못했다(`7623c4dc`, 각 1800번 거부). 입장을 완화하지 않고 진입점을 버렸다.
- **새 `raise_high_align`:** 계획의 전위치(pre-station, 파지 위치에서 0.30 m 뒤)에 세우고, 평소의 시작 둘러보기를 그대로 둔다. 진입 상태는 실제 접근이 도착할 때 들어가는 `wait_approach`다. 자기 PF 추정으로 `at_prestation`을 기록하고 사전 동작은 없다. 그다음은 제어기 자신의 접근 barrier → align → 열린 하강 → 닫기 barrier → 파지 → 낮은 lift → HIGH로 이어진다. 둘러보기가 끝나는 시점을 맞춰야 하므로 Track A의 r2 수정 뒤에 돌린다.
- **HIGH 진입의 적재 상태:** 정적 사전 동작을 제어기의 자기 명령 이력으로 차례대로 넘긴다. 먼저 닫기 전 자세를 `initial_servo_command`로 넣고, 이어서 닫기·들기 행을 넣는다. 그러면 LoadState가 실제 닫기 뒤와 같은 규칙(파지 높이에서 집게 닫기 명령)으로 `loaded`를 켠다. 이전 방식(최종 펄스 한 줄)은 `loaded=false`로 남아 HIGH 자세에서 `UNMEASURED_V3_CAMERA_POSTURE unloaded`가 났다. 규칙으로 계산한 값을 `staging.own_history`에 기록한다. HIGH 진입은 빔을 든 팔을 움직이지 않도록 시작 둘러보기를 계속 생략하고, 이를 기록한다.

## REVIEW_363 2차 대응 (2026-10-03, Claude) — 이력

2차 BLOCK(리뷰 코멘트 5967979217)과 코디네이터·사용자 결정을 반영했다. 결정 근거와 출처는
[COORDINATOR_DECISION.md](fix363/COORDINATOR_DECISION.md)에 있다.

- **P1-2 시간 → 해소:** P03 사례 cap을 사전 등록 개정(v96-cap-2)으로 3×300 SIM초로 바꿨다. P03 자료 전에 정했고,
  세 사례(before_door, after_door, before_destination)를 모두 실행 대상으로 계획한다. 하한 63.8/104.2/184.6초,
  전체 운반 190–219초([생성기](fix363/time_lower_bounds.py)). 부모 실행기가 넣던 집행기 작업 제한
  `job_sim_limit_s=120`도 300초로 맞추고 번들 timing에 기록했다.
- **P1-4 이동 중 grip 감시 → 사용자 범위 결정으로 해소:** 첫 E2E에서 집게 감시는 **기록만** 한다
  (사용자: "ㅇㅇ 그렇게 하자"). 단계 진행·barrier 준비는 자기 명령 이력 + 고정 상태 채널로만 판단한다.
  이 버전은 빔을 떨어뜨려도 실행 중 감지·통보하지 않는다. 자기 집게 감지 + 조건별 신호(사용자: "상대가 놓치면,
  놓쳤다고 신호를 보내면 되잖아 llm을 통하던지 실험 조건에 따라서")는 첫 E2E 뒤로 미뤘다.
  `relation()`은 실제 렌더에서 정상 상승·하강 대부분을 실패하고 상대가 놓친 쪽을 통과시킨다([점수](fix363/relation_zero_check.json)).
- **비순환 테스트:** `tests/test_highpose_transit.py`는 합성 영상 대신 실제 렌더 손목 영상
  ([fixture](../../tests/fixtures/highpose_recorded_frames/manifest.json), 68장, sha256 확인)으로 상태 기계를 돌린다.
  정상 완주, 집게 열림 영상도 기록만 됨, 감시값을 적대적으로 바꿔도 제어 궤적이 비트 단위로 같음(쓰기 전용 기록기),
  중간 HIGH 체크포인트 재개·재관측 시간 초과 시 상대가 상태로 멈춤을 확인한다.
- **DEV_PILOT:** v92 조립이 PARTIAL이라 MEASURED_SIM 승인이 비어 있다. 코디네이터 결정으로 정확한 sha256 하나만
  받는 DEV_PILOT 입장 경로를 추가했다(`--admission dev-pilot`). 결과·체크포인트 기록에 `FUNCTIONAL_DEV`,
  전용 코호트·TensorBoard 코호트, `promotable:false`가 붙고 확증 진입(`starts.qualify_run`)이 거부한다.
- **기록 위치:** 렌더 영상 raw `/Users/changmin/projects/ugrp/outputs/pr363-render-frames-20261003`,
  `...-seed912-20261003`, `...-seed913-20261003`(로컬 보관, 원격 백업 아님). 1차 진단 스크립트
  (`fix363/headless_grip_monitor.py`)는 기록된 SHA에서만 재현된다(`check_source`로 고정, 이후 감시 API 변경).

## REVIEW_363 1차 대응 (2026-10-03, Claude, 이력)

리뷰([REVIEW_363.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/review-363/REVIEW_363.md),
[PR 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5966787118))의
P1-1~P2-1을 한 묶음으로 고쳤다. Codex 작업 중 파일(WIP)은 검토 뒤 맞는 부분만 남겼다.

- **#361 의존:** 파일 복사 대신 `origin/codex/v92-loaded-schedule`을 병합 커밋으로 가져왔다(2d441ebe,
  ab180f2d로 재병합). #361이 main에 병합된 뒤(00eafd63) `origin/main`을 병합했으며(18b45f89), 이제 D5 로더·조립기는
  main에서만 오고 이 PR 차이에는 남지 않는다.
- **번호:** 바이트가 바뀌어 새 번호 **`zone-final-pair-highpose-v96` / 3.8.0**을 쓴다. v93/3.5.0은 실행
  기록이 없어 등록·계약 파일을 바이트 그대로 은퇴 보존한다. #365(criterion-B)는 v95만 사용한다(v94는 미사용 예약).
  [조회 원본](fix363/reservation_scan_v96.json): main과 열린 PR 8개에서 v96·3.8.0은 이 PR만 쓴다.
- **P1-1 실측 보정 관문:** `harness/zone_pair_highpose_contract.py`. 실행 CLI와 `run_case()` 직접 호출 모두
  #361 로더(`ugrp.final_environment_measured_calibration.v92`, `loader_contract_version=2`)를 통과하고,
  일정·B″·조립기 hash가 등록과 같으며, [승인 목록](../../configs/calibration/zone_pair_highpose_d5_admission.json)의
  `calibration_sha256`·source·manifest·수집 기록이 일치하고, 옆의 `input_manifest.json`·`fit_report.json`
  hash와 수집 감사 PASS를 확인해야 한다. 레지스트리와 번들 `runnable:false`도 존중한다.
  synthetic 보정은 테스트 전용 승인 행으로만 쓴다(CLI 우회 옵션 없음). 실측 params에는 PF 기본값이 없어
  `student_calibration()`이 `harness/owncam_localizer.py` 정적 기본값에 실측값을 덮어쓰고 그 hash를 기록한다.
- **P1-2 시간:** 중간 체크포인트에서 HIGH 유지(정지·재관측만), 마지막에만 하강. 사례별 시간 하한 자동 검사.
  before_destination과 전체 운반은 120초 안에 원리적으로 불가 → 2차에서 cap 300초로 개정(위).
- **P1-3 자세별 기준:** HIGH 기준(anchor)과 바닥 기준을 자세·epoch별로 따로 두고, 하강 뒤 바닥 복귀 영상을
  원래 바닥 기준과 비교(IoU≥0.70, 최대 3초)해야 open으로 간다. 합성 영상 회귀에서는 정상 하강이 통과하고
  하강 중 미끄러짐이 `FLOOR_RETURN_GRIP_CHANGED`로 멈춘다(BARRIER_OPEN_TIMEOUT으로 끝나지 않음).
  **실제 기하·RGB에서의 검증은 아직 없다**(무렌더 대역 영상은 집게·바닥을 그리지 않아 IoU 값이 의미 없음).
- **P1-4 이동 중 grip 감시 — 1차 당시 해결 못 함(2차에서 사용자 범위 결정으로 log-only):** `harness/zone_pair_highpose_grip.py`의 감시 틀
  (자기 명령 일치, 새 프레임, 상대 상태, 상승 끝 2초 안정 창, 중단 사유)은 넣었다. 그러나 핵심인
  빔 관계 검사(`relation()`, 명령 기하로 예상한 빔 위치 vs 빔 색 마스크)가 **실제 물리 기하에서 정상
  표본을 100% 실패**한다. 이대로면 정상 상승도 첫 표본(10.0초)에서 중단된다. 원인과 두 번의 수정 시도는
  아래 "fix363 무렌더 진단" 절에 있다. 규칙(같은 문제 두 번 → 멈춤)에 따라 시도를 되돌리고 재설계 결정으로 넘긴다.
- **P2-1 개발/확증 분리:** [확증 시작점](../../configs/zone_pair_highpose_confirmation_v96.json) 3개(seed 9301001–3)를
  고정했다. 이전 시작점 36개와 최소 0.127 m, 서로 최소 0.054 m 떨어진다(기준 0.05 m, 로봇 id·지도·seed와 무관).
  수집 뒤에는 `harness/kinematic_overlap.py`(#365 12c1e58c와 바이트 동일)로 t·위치·회전을 비교해 겹치면 거부한다.
  파일 바이트가 아니라 운동 내용으로 비교한다(#219 코멘트 5966536405·5966843527). 이전 궤적 목록이 아직
  없어 확증 자격 판정은 `PRIOR_KINEMATIC_INVENTORY_REQUIRED`로 거부된다.

## fix363 무렌더 진단 (P1-4)

리뷰어의 무렌더 3조건(정상, 한쪽 2초 지연, 상승 중 한쪽 집게 열림; 52 SIM초, 렌더·모델 0, weld OFF)을
소스 `255a4401`로 다시 돌렸다. 0.1초마다 실제 카메라 위치와 실제 빔 상자로 만든 **기하 대역 영상**(조명·질감·
JPEG·집게 가림 없음)을 v96 판단 코드에 자기 발행 PWM과 함께 넣었다. RGB 검출기 검증이 아니며 학생 실행·P03도 아니다.
[집계](fix363/headless_grip_monitor_results.json), [구동 코드](fix363/headless_grip_monitor.py), [기하 비교](fix363/projection_check.py).

| 조건 | r1 관계 통과 (상승/HIGH/하강) | r2 관계 통과 | 첫 중단 시각 | 빔 최대 기울기 |
|---|---|---|---|---|
| 정상 | 0/172, 0/68, 0/136 | 0/172, 0/68, 0/136 | 10.0초 (둘 다) | 0.016° |
| r2 2초 지연 | 0/172, 0/68, 0/136 | 0/172, 0/68, 0/136 | 10.0 / 12.0초 | 1.68° |
| r2 집게 열림 | **98/172, 68/68**, — | 1/172, 0/68 | 10.0초 (둘 다) | 11.47° |

정상에서 전부 실패하고, 오히려 상대가 빔을 놓친 r1은 HIGH에서 68/68 통과한다. 즉 지금 검사는
"보수적"이 아니라 실제 기하에서는 거꾸로에 가깝다. 정상과 grip 손실을 구분하지 못하므로 감지 시각은 의미가 없다.

원인(같은 정상 물리에서 제어기 모델과 실제 MuJoCo 카메라·집게 위치를 로봇 바닥 좌표로 비교):

- 짐을 든 팔은 명령 기하보다 낮은 lift에서 약 11 mm, HIGH에서 약 14 mm 낮고(0.136 vs 0.150 m),
  카메라는 5–8° 더 숙여진다(처짐, sag). 명령 기하만으로는 화면 예측이 틀린다.
- HIGH에서 보이는 빔은 **집게 앞 1.5–3.1 cm뿐**이다. 렌즈 아래 12–16 mm, 근접 절단면(near plane 2.2 cm)
  근처라서 몇 mm 차이로 화면 넓은 영역이 바뀐다. 실제 빔 중심은 집게 기준 4.6 mm 아래로 카탈로그 값 8 mm와 3.4 mm 다르다.
- 시도 1: D5 실측 적재 카메라(여기서는 실제 카메라를 이상적 측정으로 사용)로 투영하고 집게를 카메라에 강체로 붙임 →
  집게 위치는 0.1 mm까지 맞지만 HIGH coverage 0.38→0.50(기준 0.65)으로 여전히 실패.
- 시도 2: 미리 정한 먼 영역(집게 0.06 m 너머)만 사용 → 그런 영역이 화면에 아예 없어 support 0.
- 두 시도 모두 되돌렸다. 재설계 방향(결정 필요): 투영 대신 같은 자세의 자기 기준 영상과 비교하는
  기존 검증 방식(hold IoU, 가장자리 추적)으로 바꾸고, 상승 중 보이지 않는 구간은 "관측 불가"로 명시하며,
  실제 렌더 RGB로 정상/지연/집게 열림을 다시 검증해야 한다.

(1차 당시) 번들은 `runnable:false`이고 실측 보정 승인도 비어 있어 실제 실행은 막혀 있었다. 2차에서는 감시를 기록 전용으로 바꿔 이 검사가 진행을 막지 않는다.
raw: `/Users/changmin/projects/ugrp/outputs/pr363-fix-grip-monitor-20261003`,
`/Users/changmin/projects/ugrp/outputs/pr363-fix-projection-check-20261003` (로컬 보관, 원격 백업 아님).


## 변경과 입력 경계

기존 `zone-final-pair-v88`의 `zone_final_pair_skill.Team/Execution`과 b-v6g/b-v6h1 계열
beam-relative 제어기, 빔 추적기(BeamEdgeTracker), 정적 경로, 가드, 상태 통신, P03의 동일 PF·
0.16 SIM초 지연을 재사용한다. `scripts/run_camera_pair_transport.py`는 이전 LLM 두 로봇
경로이며, 현재 최종 v3 학생의 기반은 v88 어댑터다. 이를 새 LLM 제어기로 대체하지 않는다.

바닥 파지→기존 낮은 lift의 자기 RGB 확인→110/130 mm 경유→150 mm 높은 자세(HIGH)→
운반→역순 경유 하강→바닥 내려놓기→release 순서다. 높은 자세 PWM(3·4·5·6)은
`896,2035,1894,1500`으로 PR #361과 같다. 경유마다 1.2초 보간·2.8초 대기,
HIGH 도착 뒤 8초 대기를 둔다. 실제 발행에는 기존 ArmSequence와 0.05초 격자를 사용한다.
새 높은 영상에서 가장자리가 보인 뒤 유지 기준 영상을 갱신하고, 지연된 자기 영상의
가장자리 기준이 생겨야 운반 준비를 보고한다. HIGH 밖의 적재 base 명령은 거부한다.

10/3 사용자 결정에 따라 위치 추정은 OpenCV다. 기존 markerless probe의 왜곡 보정·
명암/색차·균일 벽 띠 검출을 재사용해, 모호한 여러 띠와 유채색 가림은 버리고 정적 지도
PF에 벽 경계를 전달한다. 기존 PF 수명·운동·관측 품질 검사는 유지하며 학습 분할망이나
체크포인트를 생성·호출하지 않는다. 새 OpenCV 경로의 실제 RGB 정확도는 인수 대상이다.

제어 입력은 자기 RGB·공개 정적 지도·자기 발행 명령과 기존 상태 메시지뿐이다. 현재 좌표,
측정 관절, 접촉, 성공 판정은 제어기에 전달하지 않는다. 카메라 배치/FOV, 로봇·화물 외관,
`masterpi_v3`, `floor_light_v1`, `cargo_noslip_v1`, weld OFF, 초음파 OFF를 유지한다.

## 첫 등록 v93 기록 (은퇴, 이력 보존)

아래 절과 "검증 기록"은 v93 시점 기록이며 현재 v96 관문을 설명하지 않는다.


- 기준 소스: `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`, 브랜치 `codex/pair-carry-highpose`.
- 새 번들·실행 경로: **`zone-final-pair-highpose-v93`**, 버전 **3.5.0**.
- main+열린 PR 9개 총 10 refs를 조회해 v92/3.4.0 최댓값과 원격 HEAD 일치를 확인했다.
  [조회 원본](reservation_scan.json)을 보존한다. 게시 직전 main+열린 PR 7개 총 8 refs를
  [다시 조회](reservation_scan_final.json)했고 최댓값 v92/3.4.0과 v93 미사용을 재확인했다.
- 새 [등록](../../configs/zone_pair_highpose_v93.json)과 [보정 계약](../../configs/calibration/zone_pair_highpose_v93_contract.json).
  v88/v90/v91 등록과 동결 B/B′/r4/r5는 수정하지 않는다. v91 held-out raw는 읽지 않는다.

새 로더는 schema `ugrp.final_pair_highpose_measured_calibration.v1`, `status=MEASURED_SIM`,
새 계약 hash, 세 지도 hash, `loaded_measurement_bundle_id=zone-final-pair-v92`,
`loaded_pose_id=masterpi-v3-pair-high-150mm-minus40-v1`, `loaded_camera_scope=high_only`를 요구한다.
source SHA, 실측 manifest·v92 일정·기준·조립기 SHA-256도 필수다. 이전 params/pair_model/
camera_models 형식은 재사용한다. loaded 카메라 키는 HIGH 하나이며 바닥/낮은 자세는 요구하지 않는다.
닫기부터 HIGH 정착 전, 하강 중에는 자기 영상의 grip/hold 검사만 유지하고 절대 위치 관측은
건너뛴다. 발행 명령 기반 예측과 불확실성은 유지한다. 이 구간에 임의 카메라 보정값을 채우지 않는다.

이 계약은 D1의 임시 소비자 인터페이스다. D5 담당자는 별도
`ugrp.final_environment_measured_calibration` 계열 HIGH 계약을 만들고 있어 **최종 D5
산출물과의 schema/필드/hash 호환 확인이 남았다**. 정확한 D5 원격 소스가 공개되면 새
로더에 연결하고 관련 회귀를 다시 검증해야 한다. 현재 로더의 synthetic 보정 수락 검사는
D5 호환 완료가 아니다. 실제 보정 파일·기준 B″·조립기 승인이나 v92 측정 완료를 만들지 않는다.

## 코디네이터 인수 계획

1. D2–D5의 기준·일정·조립기 고정 및 v92 수집/적합/독립 검토를 마친다. 해당 실측 파일과
   새 학생 후보 SHA·번들/소스 hash·환경을 고정한다. 아래 계획 출력의 실행 가능 조건을 먼저 검사한다.
2. 기존 stage probe의 구조로 최종 v3 장면에서 **단계별 준비 상태(staged state)**를 만든다.
   정렬 시작, 바닥 파지 직전, 낮은 lift 직후, HIGH 유지, 목적지 HIGH 상태에서 각각
   정렬→파지/lift→HIGH 상승→한 leg 운반→역순 하강/release를 검사한다. staging의 정답은
   평가 소유자만 사용한다. 학생에 전달하는 것은 동일 자기 RGB·발행 명령 이력뿐이며,
   준비 상태의 평가 좌표를 PF 현재 위치로 주입하지 않는다. staged 결과는 E2E/P03와 별도 분모다.
3. 각 단계에서 실제 RGB 가장자리 열/검출/기준 획득, 관절 제한, 빔 상승·기울기·네 집게 접촉,
   외부 지지/weld 없음, 명령·가드 중단을 평가 전용 출력으로 확인한다. 낮은/높은 영상 사이 IoU를
   같은 자세 유지 점수로 해석하지 않는다. 명령 이후의 실제 접촉·관절·카메라 응답을 독립 검토한다.
4. 단계 인수 뒤 **`zone_wide_door_geometry_v3` P03 3×300 SIM초**(사전 등록 개정 v96-cap-2)를 수행한다. 세 사례는
   지도 수가 아니라 문 앞·문 뒤·목적지 전 체크포인트다. 각 사례는 dock 독립 reset에서 시작하며
   실제 이전 leg를 거친다. 중간 체크포인트에서는 HIGH를 유지한 채 정지·재관측만 하고(lower/open/재상승 없음),
   같은 PF로 이어야 한다. 세 사례 모두 하한이 300초 안이라 실행 대상이다(하한이 cap을 넘으면 실행 전 거부).
   GT 재배치/PF 교체 없이 실행하며 미도달도 분모 3에 포함한다. reset은 회당 최대
   5초로 별도 기록한다(총 900+최대15 SIM초). MEASURED_SIM 보정이 없으면 DEV_PILOT(FUNCTIONAL_DEV, 승격 불가)로만 돈다. stage 준비 상태를 P03 성공으로 합산하지 않는다.
5. `SEQUENCE_OBSERVED_UNQUALIFIED`는 순서 관측일 뿐이다. 별도 실제 오차·접촉·운반·방출 판정,
   가림/edge 실패·시간 초과·미시도·HOST_ERROR/ENOSPC를 전부 보존한다. 세 지도 전체 carry,
   일반화, 실물 성공은 별도이며 이번 P03로 확대하지 않는다.
6. raw는 기본 체크아웃 `outputs/` 새 절대 경로에 보존한다. 모델 입력·자기 JPEG/명령·평가 기록과
   SHA-256, source/calibration/bundle/environment를 회수하고 TensorBoard 새 스냅샷에 표시·검증한다.
   자기 세션·자식·잠금만 정리한다. Google Drive는 사용하지 않는다.

계획 확인(물리·렌더 시작 없음):

```bash
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
"$PY" -m scripts.run_pair_highpose --check p03 --expected-source-sha "$FINAL_SHA" \
  --output /Users/changmin/projects/ugrp/outputs/pair-highpose-P03-NEW
```

실측 보정 뒤 코디네이터는 자기 worktree의 고정 SHA·깨끗한 tree·10 GiB 여유·소유 잠금을
확인하고 `ugrp_session.py run <새 세션> -- "$PY" -m scripts.sim_cli workflow run
zone-final-pair-highpose-v96 -- --check p03 --expected-source-sha "$FINAL_SHA"
--calibration <실측 파일> --calibration-sha256 <실측 SHA256> --lock-owner <소유자>
--output <새 절대 raw 경로> --execute`로 실행한다. 보정 부재의 차단을 해제하는 별도 우회 옵션은 없다.

## 검증 기록

관련 5개 파일의 최종 통과 줄은 **`138 passed, 1 deselected in 70.08s (0:01:10)`**이다.
새 후보 검사 20개, 기존 v3·카메라 계약·가장자리 추적·P03 수명주기 회귀를 포함한다.
과거 v6e 재생용 로컬 JPEG `r2/00025.jpg`가 없어 해당 검사 1개는 실행 목록에서 제외했다.
첫 실행의 `138 passed / 1 failed`와 원본 오류도 보존한다. 실제 RGB 재생 통과로 바꾸지 않는다.
[검증 명령·환경·로그/JUnit hash](validation.json), [기존 30개 파일 보존 hash](preservation.json)를 따른다.
컴파일, `git diff --check`, 고정 CI 자료 3개, 표준 workflow 계획 출력도 확인했다.
이는 로컬 결과이며 원격 CI·독립 검토·렌더/P03 인수는 별도다.

추가 workflow 카탈로그 검사는 **`17 passed, 1 deselected in 1.00s`**다.
전체 파일의 첫 실행은 17 pass/1 fail이며, 프로세스 정리 검사의 `/bin/ps`가 샌드박스에서
거부되어 그 검사만 제외했다. 로컬 프로세스 정리 검증 완료로 보고하지 않는다.

[고정 진단 명령](probe_headless.py)을 커밋 **`a19e232a3a2576832a145a0435e9450da017f759`**로
고정하고 52 SIM초 실행했다. teacher station 시작에서 실제 학생의 ArmSequence 상승/하강
경로를 재사용했다. [전체 집계](headless_check.json)와 [집계 코드](summarize_headless.py)를 보존한다.

| 구간/검사 | 실제 결과 |
|---|---|
| 낮은 lift 정착 [8,10)초 | 40/40 표본 상승·네 집게 접촉·외부 지지 없음 |
| HIGH 상승 [10,27.2)초 | 344/344 같은 조건 |
| HIGH 유지 [27.2,34)초 | 136/136 같은 조건, 빔 바닥 최소 114.849 mm |
| 하강 [34,47.6)초 | 257 lifted / 15 not_lifted; 전부 보존 |
| 전체 1,041표본 | 849 lifted / 192 not_lifted; 초기·바닥·release 포함 |
| 목표 관절 2,352개 | 제한 위반 0, 팔 최소 여유 0.2992 rad, 집게 0 m |
| HIGH 순기구학 | 높이 149.857 mm, pitch −40.05° |
| 자기 카메라 기하 | 낮은 자세 양쪽 0열, HIGH 30/32초 양쪽 90열 |
| 비용/환경 | 1,948명령, 모델 호출 0, weld OFF, 렌더 0 |

`lifted`는 빔 바닥≥10 mm·네 집게 접촉·외부 지지 없음·weld 없음의 평가 전용 판정이다.
기하 가시성은 RGB 검출 성공이 아니다. 이 결과는 운반 base 주행·자기 RGB 학생·v92 보정·
P03 인수를 포함하지 않는다. raw manifest의 모든 파일 hash를 대조했으며 원본 위치는
`/Users/changmin/projects/ugrp/outputs/pair-highpose-offline-20261003/headless-a19e232a`다.
원본은 로컬 보관이며 원격 백업으로 표현하지 않는다.

첫 관리 세션은 샌드박스 `/bin/ps` 거부로 물리 시작 전에 종료되었다. 별도 자식/렌더가 없는
고정 종료 진단을 직접 실행했고 종료 코드 0·소유 잠금 해제를 확인했다. 시작/끝 부하 평균은
집계 JSON에 보존했다. 다른 작업의 세션/서버는 변경하지 않았다.

TensorBoard 새 스냅샷 `1003-pair-highpose-v93/high-hold`에 같은 진단의 low 0열/HIGH 90열,
유지 136/136, 상승 344/344, SIM 52초·명령 1,948·모델 호출 0을 등록했다. 이벤트와
서버 API를 원본과 대조했다. 새 영상 등록은 0개이며 없는 wall/model 지연·임무 성공을
0으로 채우지 않는다. [대시보드 검증과 고정 링크](tensorboard_verification.json)를 따른다.

## 참고 자료

### HIGH 운반 빔 경계 맞춤 (v98, 처방 제안의 출처)

- Fischler, Bolles, "Random Sample Consensus: A Paradigm for Model Fitting with Applications to Image Analysis and Automated
  Cartography", CACM 24(6), 1981. 이상치가 섞인 자료에서 직선 등 모델을 맞추는 RANSAC. **미확인**(이번 작업에서 원문을 다시 읽지 않음).
- OpenCV `cv::fitLine`(M-estimator 거리 `DIST_HUBER` 등). **미확인**(문서를 이번 작업에서 다시 읽지 않음).
- 이 출처는 조정자 결정용 제안이며 코드에는 넣지 않았다.

### 짝 guard 시작 상태 완화 (v98, 작성자 모듈 설명의 출처)

- Bar-Shalom, Li, Kirubarajan, *Estimation with Applications to Tracking and Navigation*, Wiley 2001. NEES/ANEES 일관성 검사:
  NEES가 카이제곱 한도보다 크면 필터가 지나치게 자신 있다는 뜻이다. 공분산 부풀리기·과정 잡음 추가·적응 잡음 추정이 표준 처방이다.
  **미확인**(작성자 인용, 이 작업에서 본문을 다시 읽지 않음).
- Thrun, Burgard, Fox, *Probabilistic Robotics*, MIT Press 2005. 입자 필터의 무작위 입자 주입(위치 추정 복구). **미확인**(같은 이유).
- 우리 적용: 위 두 출처는 남은 문제(과신)의 처방 근거이고 이번 diff에는 넣지 않았다. 시작 상태 완화 규칙 자체(동결 거부 뒤
  "나빠지지 않으면 허용")는 출처 없이 조정자가 고른 선택지 2다(사용자 9/29 "guard 완화 허용").

### 보지 않는 마지막 접근 (v98, 설계 작업자 조사, 출처 표기 그대로)

"확인"은 해당 절이나 코드를 직접 읽었다는 뜻이고 "미확인"은 초록이나 2차 언급만 봤다는 뜻이다. 조사 전문은
[blind_final_approach_survey.md](blind_final_approach_survey.md).

- Hutchinson, Hager, Corke, "A tutorial on visual servo control", IEEE T-RA 12(5), 1996. 확인. 보고 나서 움직이기와 끝점 개루프·폐루프 구분.
- Chaumette, Hutchinson, "Visual servo control Part I/II", IEEE RAM 2006/2007. 확인. 시야 유지 기법.
- Kragic, Christensen, "Survey on visual servoing for manipulation", KTH/CVAP 2002. 확인. "정렬 뒤 수직으로 몇 cm 내려가 잡기" 사례.
- Folio, Cadenat, "A sensor-based controller able to treat total image loss", IROS 2008 (hal-00603686). 확인. 마지막 측정과 자기 속도 명령으로 특징 예측.
- Morrison, Corke, Leitner, "Closing the loop for robotic grasping" (GG-CNN), RSS 2018, arXiv 1804.05172. 확인(IJRR 2020판 미확인). 코드 github.com/dougsm/ggcnn_kinova_grasping: 150 mm보다 가까우면 목표 고정 후 약 70 mm 개루프, 3샘플 평균.
- Haviland, Dayoub, Corke, "Control of the final-phase of closed-loop visual grasping using IBVS", arXiv 2001.05650. 확인.
- Viereck, ten Pas, Saenko, Platt, CoRL 2017, arXiv 1706.04652. 확인. 14 cm 안에서는 정해진 동작으로 닫음.
- Levine 외, "Learning hand-eye coordination for robotic grasping", IJRR 2018, arXiv 1603.02199. 확인.
- Kalashnikov 외, "QT-Opt", CoRL 2018, arXiv 1806.10293. 확인.
- Burgess-Limerick, Lehnert, Leitner, Corke, "DGBench", arXiv 2204.13879. 확인. 마지막 단계 개루프가 일반적.
- Burgess-Limerick 외, "An architecture for reactive mobile manipulation on-the-move", ICRA 2023, arXiv 2212.06991. 확인.
- hello-robot/stretch_ros(`stretch_demos/nodes/grasp_object`), hello-robot/stretch_visual_servoing. 확인(코드). 한 번 관찰 뒤 고정 접근(반례: 잡기 확인 없음).
- HomeRobot/OVMM arXiv 2306.11565, OK-Robot arXiv 2401.12202. 확인. 개루프 경유점 접근, 오류 감지·재시도 없음을 한계로 적음.
- Boston Dynamics Spot SDK `manipulation_api.proto`. 확인(proto 주석). 내부 제어기는 비공개.
- Will, Grossman, "An experimental system for computer controlled mechanical assembly", IEEE Trans. Computers C-24(9), 1975. 확인. 경계 이동(guarded move).
- 미확인(초록만): Mezouar·Chaumette 2002 (inria-00352101), Garcia-Aracil 외 2005 (hal-04654343), Cherubini·Chaumette 2013 (hal-00750623).
- 우리 적용: 정렬 단계의 연속 2프레임 규칙과 GG-CNN의 "가까우면 목표 고정 후 짧은 개루프"를 따르고, 개루프 구간을 자기 명령 범위·시간·거리로 묶었다(경계 이동). 카메라 기하 때문에 확인 위치를 측정된 호버 자세로 정한 것만 바꿨다.

### r2 둘러보기 guard 여유 (v98, Track A)

- Blackmore, Ono, Williams, "Chance-Constrained Optimal Path Planning With Obstacles", IEEE Transactions on Robotics 27(6), 2011. 가우시안 위치 오차에 대한 선형 기회 제약에서 여유를 `k·√(nᵀΣn)`(장애물 법선 n 방향 표준편차)로 줄이는 방법이다. **미확인:** 본문을 아직 읽지 않았다(조정자 지시). 우리 적용: k = 1(`PairArmGuard`)을 쓰고, `std_xy` 척도(√2 배)를 유지하며, 공용 값보다 커지지 않게 했다.

### 자기 영상 문턱 재보정 조사 (v98, Track A, 출처 표기 그대로)

2026-10-03 조사, 모든 문제에 고전·최신 해결법 조사 선행 규칙.

표시: [F] 원문/소스를 열어 읽음, [S] 검색 요약만 확인, [K] 배경지식(재확인 안 함). 접근이 막혀 못 읽은 곳은 아래 "한계"에 적었다.

#### 가. 길을 잃었을 때: 멈춰서 둘러보기, 복구, 측정이 안 들어올 때
- ROS move_base `rotate_recovery` (`ros-planning/navigation` noetic-devel `rotate_recovery.cpp`, `move_base.cpp`) [F 소스]: 계획이 실패하면 값싼 복구(지도 초기화) 뒤에 360도 회전, 충돌 위험이면 중단. 가져온 것: "실패 시 한 바퀴 둘러보기, 충돌 위험이면 중단". 안 가져온 것: 위치 추정이 좋아졌는지 확인하지 않는다.
- Nav2 `Spin`/기본 행동 트리 (`nav2_behaviors/plugins/spin.cpp`, 문서 api.nav2.org) [F 문서·소스, 기본 time_allowance 10 s는 S]: 90도(1.57 rad) 회전 → 5 s 대기 → 후진 0.30 m, 재시도 6회. 가져온 것: 짧은 회전, 시간 제한, 재시도 전 대기. 안 가져온 것: 맹목 회전.
- Burgard, Fox, Thrun, "Active Mobile Robot Localization", IJCAI-97 [F]: 센서 방향과 움직임을 기대 엔트로피 감소로 고른다. 가져온 것: 지도를 아니 팬 각도별 정보량을 점수로 고를 수 있다는 점(후속 과제). 안 가져온 것: 격자 신념, 초음파.
- Fox, Burgard, Thrun, "Active Markov Localization for Mobile Robots", Robotics and Autonomous Systems 25(3-4):195-207, 1998 [S].
- Fox, Burgard, Thrun, Cremers, "Position Estimation for Mobile Robots in Dynamic Environments", AAAI-98 [F]: 엔트로피 문턱은 "현재 신념을 맞든 틀리든 확인하려는" 경향이 있다. **이번 사고와 직접 같은 구조**: 믿음이 틀리면 증거를 받는 문이 닫힌다. 그래서 "측정이 한 번도 안 들어오는 상태"를 별도 복구 시작 조건으로 둔다.
- Fox, Burgard, Thrun, "Markov Localization for Mobile Robots in Dynamic Environments", JAIR 11:391-427, 1999 [F]: 평평한 사전분포에서 전역 재위치 추정이 받아들여진 마지막 수단.
- Thrun, Burgard, Fox, Probabilistic Robotics (MIT Press, 2005) 증강 MCL(표 8.3, 약 218쪽) [S]/[K], Nav2 AMCL 소스의 `recovery_alpha_fast/slow` 기본값 0 [F 소스]: 단기/장기 평균 가중치 비율로 입자를 주입. 안 가져온 것: 이 방식은 **측정이 0개이면 아무 신호도 못 본다**(우리 사고와 같다). 그래서 "T초 동안 받아들인 갱신 없음"을 따로 시작 조건으로 둔다.
- Thrun, Fox, Burgard, Dellaert, "Robust Monte Carlo Localization for Mobile Robots", Artificial Intelligence 128 (2001) [F]: 센서가 너무 정확하다고 가정하면 입자 필터가 쉽게 길을 잃는다. 처방은 잡음 가정을 키우기, 균일 입자, 혼합. 가져온 것: 입자 주입 전에 잡음부터 키운다.
- Davison, Murray, "Simultaneous Localization and Map-Building Using Active Vision", IEEE TPAMI 24(7):865-880, 2002 [F]: 머리 회전 시간을 비용으로 세어 가장 불확실성을 줄이는 곳을 본다. 가져온 것: 둘러보기 시간을 비용으로 기록.
- Chaplot, Parisotto, Salakhutdinov, "Active Neural Localization", ICLR 2018 [F]: 신념 최대값/엔트로피를 종료 기준, 단계 수를 예산으로. 학습 기반이라 가져오지 않음.
- Mur-Artal, Montiel, Tardós, "ORB-SLAM", IEEE T-RO 2015 [F]: "추적 상실"을 명시적 상태로 두고, 후보 생성은 싸게 검증은 엄격하게, 복구 뒤에는 20프레임 동안 새 키프레임을 막는 완충. 가져온 것: 상실 상태, 복구 뒤 완충. 폴백으로 검출 문턱을 몰래 낮추는 방식은 가져오지 않음.
- 최근 연구(2022~2026): ActLoc, Li 외, arXiv 2508.20981 [F 초록] / "When to Localize? A POMDP Approach", Williams 외, SSRR 2024, arXiv 2411.08281 [F 초록] / Active Particle Filter Networks, Honerkamp 외, arXiv 2209.09646 [F 초록] / F3Loc, Chen 외, CVPR 2024, arXiv 2403.03370 [F 초록] / Semantic Rays, Grader, Averbuch-Elor, ICCV 2025, arXiv 2507.09291 [F 초록] / Sparse Feasible Hypothesis Sampling, Zhang 외, arXiv 2511.01219 [F 초록] / GALoc, Han 외, arXiv 2609.08385 [F 초록만, 2026-09 논문이라 인용 전 재확인 필요]. 가져온 것: 시점별 정보량이 다르다(요에 따라 다름), 실현 가능한 위치만 후보로 주입, 거친 것에서 세밀한 것으로. 모두 학습 깊이/LiDAR가 필요해 그대로는 못 쓴다.
- Boniardi 외, "Robot Localization in Floor Plans Using a Room Layout Edge Extraction Network", IROS 2019, arXiv 1903.01804 [F]: 열마다 **잘라낸(saturated) 잔차**를 쓰고 쓴 열 수로 나눈다. 측정을 다 거절하는 우도에 대한 가장 직접적인 처방 패턴(후속 과제).

#### 나. 멈춤 후 안정화, 번짐 게이트
- Canon, "Robot with camera", US8352076B2 [F 특허]: 옛 방식은 약 1초 고정 안정화 대기, 새 방식은 위치 오차와 속도가 모두 문턱 아래일 때 촬영. 우리는 관절 속도를 못 쓰므로 마지막 자기 명령 뒤 0.2 s 고정 대기를 유지(MuJoCo 렌더는 움직임 번짐이 없다).
- Intrinsic, "Reducing motion blur for robot-mounted cameras", US11472036B2 [F 특허]: 프레임을 팔 움직임 자료와 맞춰 번짐을 본다.
- Pertuz, Puig, Garcia, Pattern Recognition 46(5):1415-1432, 2013 [서지 F, 내용 K]: 라플라시안 분산 등 초점 측정은 상대 비교용이다. Pech-Pacheco 외, ICPR 2000 [S]. Unblur-SLAM, arXiv 2603.26810 [S]. LOVON, arXiv 2507.06747 [S]. 가져온 것: 번짐 점수는 같은 시퀀스의 백분위로 판정(우리 렌더에는 번짐이 없어 쓰지 않음).

#### 다. 광도 강건성과 문턱 재정
- Engel, Usenko, Cremers, "A Photometrically Calibrated Benchmark for Monocular Visual Odometry", arXiv 1607.02555 [F 초록]: 광도 보정을 한 번 하고 문서화.
- Engel, Koltun, Cremers, "Direct Sparse Odometry", arXiv 1607.02565, TPAMI 2018 [F 본문]: 블록별 문턱 = 중앙값 기울기 + 상수. 가져온 것: 문턱을 지역/대상 자료 기준선에 상대화.
- Ulrich, Nourbakhsh, "Appearance-Based Obstacle Detection with Monocular Color Vision", AAAI-2000 [F]: 바닥 기준 영역 분포를 배워 그 분포 대비 이탈로 판정, 조명이 바뀌면 정적 모델은 거짓 양성이 늘고 적응 모델이 줄인다. 가져온 것: 문턱을 대상 프로파일의 기준 프레임 분포에서 정하는 방식.
- Horswill, "Polly: A Vision-Based Artificial Agent", AAAI-93 [F]: 질감 없는 바닥에서는 기울기 문턱 에지 검출이면 충분, 그림자와 약한 바닥-벽 경계가 실패 원인. 가져온 것: 경계에 실제 단차가 있어야 한다는 검사(그림자 그라데이션 거르기).
- Maddern 외, "Illumination Invariant Imaging", ICRA 2014 Workshop on Visual Place Recognition in Changing Environments [F]: 로그 색 조합. 햇빛 가정이라 MuJoCo 렌더와 푸른 바닥 채도 문제에는 안 맞는다. 채도 절대 문턱은 후보가 아니라는 근거로만 사용.
- Lorigo, Brooks, Grimson, IROS 1997:373-379 [S, 2차 인용만]; Lenser, Veloso, IROS 2003:886-891 [S]; OpenCV Canny/CLAHE 튜토리얼(`opencv/opencv` markdown) [F]; Rosebrock, PyImageSearch 2015 자동 Canny [F, 블로그]; Zhang, Forster, Scaramuzza, ICRA 2017 [F 본문]; Shim, Lee, Kweon, IROS 2014 [F 일부]; Tobin 외, IROS 2017, arXiv 1703.06907 [F 일부, 간접 근거]; ORB-SLAM 문턱 기본값 20→7 [S].

#### 라. 우리에게 적용한 것과 바꾼 것
- 적용: (1) 문턱을 조명에 맞춰 **대상 프로파일 기준 프레임의 백분위 + 명시한 여유폭**으로 다시 정함(Ulrich의 기준 영역 학습, DSO의 중앙값+여유폭의 취지). 정확한 이식이 아니라 취지만 빌렸다. (2) 벽 경계 후보에 **단차 검사** 추가(Horswill, Canny의 취지). (3) 문턱을 몰래 낮추는 폴백은 쓰지 않았고 값과 근거를 번들에 고정했다(ORB-SLAM의 폴백을 일부러 안 씀).
- 바꾼 것: 우리는 관절 속도를 못 쓰므로 Canon 특허의 위치/속도 문턱 대신 0.2 s 고정 대기를 유지. 복구 동작은 "T초 동안 받아들인 갱신 없음"을 따로 시작 조건으로 둔다(Fox 1998의 경고, 증강 MCL이 침묵한 필터를 못 보는 점).
- 한계: 렌더 조명이 바뀔 때 고정 광도 문턱이 실패함을 직접 보이고 대상 프레임 보정을 권하는 논문은 찾지 못했다(Tobin 2017은 간접 근거). Pertuz(내용), Lorigo(원문), Horswill 박사논문, Lenser는 원문을 읽지 못했으니 인용 전 확인이 필요하다. wiki.ros.org(봇 차단), Probabilistic Robotics PDF(링크 끊김), ScienceDirect/SAGE(403)는 열지 못했다.

### 집게 감시 조사 (2차 대응, 출처 표기 그대로)

표기: [F] 페이지를 열어 읽음, [S] 검색 결과 요약만 봄, [K] 배경 지식(이번에 재확인 안 함).
[S] 표기 자료는 최종 보고서에 인용하기 전에 원문을 확인해야 한다.

- 기준 영상 + 마스크 정렬(ECC/ZNCC)이 1순위 추천. 같은 카메라·장착·실제 파지에서 얻은 기준 영상을 쓰면 일정한
  투영·보정 오차가 상쇄된다(목표 영상을 계산하지 않고 기록하는 teach-by-showing 시각 서보와 같은 논리).
  - G. D. Evangelidis, E. Z. Psarakis, "Parametric Image Alignment Using Enhanced Correlation Coefficient Maximization," IEEE TPAMI 30(10), 2008. http://xanthippi.ceid.upatras.gr/people/psarakis/publications/PAMI.pdf [S]
  - OpenCV `findTransformECC` / `findTransformECCWithMask` 문서 https://docs.opencv.org/4.x/dc/d6b/group__video__track.html , 마스크 PR https://github.com/opencv/opencv/pull/22997 , https://github.com/opencv/opencv/pull/3845 [S]
  - S. Baker, I. Matthews, "Lucas-Kanade 20 Years On: A Unifying Framework," IJCV 56, 2004, doi:10.1023/B:VISI.0000011205.11775.fd [S]
  - B. Espiau, F. Chaumette, P. Rives, "A New Approach to Visual Servoing in Robotics," IEEE T-RA 8(3):313-326, 1992 [S]. F. Chaumette, S. Hutchinson, "Visual Servo Control, Part I: Basic Approaches," IEEE RAM 13(4), 2006 [S]
- 집게 카메라 기준 물체 상대 움직임(광류 + 앞뒤 오차 검사).
  - L. Marx, A. A. Palsdottir, L. N. S. Andreasen Struijk, "Frame-Based Slip Detection for an Underactuated Robotic Gripper for Assistance of Users with Disabilities," 2023. https://research.utwente.nl/en/publications/frame-based-slip-detection-for-an-underactuated-robotic-gripper-f [F]
  - Z. Kalal, K. Mikolajczyk, J. Matas, "Forward-Backward Error: Automatic Detection of Tracking Failures," ICPR 2010 [S]
  - Reinold et al., "Combined Physics and Event Camera Simulator for Slip Detection," WACV Workshops 2025. https://arxiv.org/abs/2503.04838 [S]
- 기준 영상 차분(image differencing): "Slip Detection with Combined Tactile and Visual Information," ICRA 2018 (authors not checked), https://arxiv.org/abs/1802.10153 [S]
- 학습 기반 파지 확인(상한 참고용, 우리 제약 밖): Nair, Pakdaman, Ploeger, IROS 2020, https://arxiv.org/abs/2003.10167 [F]; Amargant, Honig, Vincze, 2025, https://arxiv.org/abs/2505.03046 [F]
- 다중 로봇 협동 운반(관련성 낮음): Tuci, Alkilabi, Akanyeti, Frontiers in Robotics and AI 5:59, 2018 [S]; Zhang et al., "Image-Based Visual Servoing for Enhanced Cooperation of Dual-Arm Manipulation," IEEE RA-L 2025, https://arxiv.org/abs/2410.19432 [F]; "Robust Cooperative Manipulation without Force/Torque Measurements," https://arxiv.org/abs/1710.11088 [S], authors not checked

### 기존 참고 자료

- REVIEW_363: [리뷰 문서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/review-363/REVIEW_363.md),
  [PR 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5966787118)
- D5 로더·조립기: [PR #361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361) (병합 의존)
- 운동 내용 중복 판정: [PR #365](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/365)의
  `harness/kinematic_overlap.py`(12c1e58c, 바이트 동일 사본), [#219 코멘트 5966536405](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966536405),
  [5966843527](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966843527)
- 기존 자기 기준 유지 검사(재설계 후보): [hold IoU](../../harness/owncam_pair_hold_v3.py), [가장자리 추적](../../harness/own_beam_edge.py)

- [D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)
- [높은 자세 후보 PR #361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361),
  [소스 고정 설계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a9481446d9c7c503bdbc53941d3538cd5ec5ee12/experiments/2026-10-03-v92-loaded-schedule/README.md)
- [현재 v3 학생](../../harness/zone_final_pair_skill.py), [기존 운반·빔 추적](../2026-09-29-pair-v6e-carry/README.md),
  [b-v6h1 범위](../2026-09-30-pair-v6h-carry/README.md)
- [P01](../2026-09-30-e2e-p01-env/README.md), [P03](../2026-09-30-e2e-p03-provider/README.md),
  [물리 인계](../../PHYSICS_HANDOFF.md), [실행 버전 관리](../../docs/execution_versioning.md)
- [재사용 OpenCV 검출기](../2026-09-26-markerless-probe/markerless_probe.py),
  [새 관측 어댑터](../../harness/opencv_wall_observation.py), [새 제어기](../../harness/zone_pair_highpose_runtime.py)
