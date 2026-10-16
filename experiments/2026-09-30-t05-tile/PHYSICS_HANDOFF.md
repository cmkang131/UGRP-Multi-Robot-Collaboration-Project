# T05 물리 인수 인계 — 미실행, 정상 1 + 미파지 1

**담당: 조정자. 이 PR 작업자는 물리/렌더를 실행하지 않았다.**
후보는 `TileWestSkill` 하위 조작까지이며 native scene/navigation/전체 배송 연결은
아직 등록되지 않았다. 기존 cyan-only 실행기를 이름만 tile로 바꿔 실행하지 않는다.
아래 연결·고정 게이트가 닫히기 전에는 **물리 실행 준비 미완료**다.

## 실행 전 연결·고정 게이트

1. 이 draft의 최종 source SHA에서 독립 검토·필수 CI 결과를 확인한다. 이 문서나
   fake 통과를 병합/연구 실행 승인으로 쓰지 않는다. coordinator의 새 통합 소스는
   별도 커밋하고 현재 봉인 소스를 건드리지 않는다. 표준 `sim_cli.py` 관리 계층에
   새 adapter/workflow와 source closure를 등록한다. 이미 쓴 bundle ID를 재사용하지 않는다.
2. **같은 코드를 두 셀 동안 고정**한다. `TileWestSkill.manifest()`의 JSON hash,
   `role_assignment()` JSON hash, 두 모듈·전이/영상 helper 전체 source hash,
   map/scene/robot/camera/contact/명령 주기 hash를 따로 남긴다. 기존 성공 번들을 승계하지 않는다.
3. `sim.session_scenes.Scene`에서 최종 MasterPi v3, `zone_wide_door_geometry_v2`,
   walls_v3, landmark_detail=none(표식 0), weld OFF, `cargo_noslip_v1`을 실제 적용한다.
   모델/FOV/집게/물체/마찰을 인수에 맞춰 바꾸지 않는다. 센서는 자기 robot_cam만,
   ultrasonic OFF. TOP와 GT는 평가·영상 감사에만 저장한다.
4. 원본 s1–s6를 수정하지 않는 별도 dev fixture를 고정한다. tile_1은
   `(1.0, −.85, 0)`, dimensions .060×.040×.012 m, mass .025 kg, 목적지 **C**로 고정한다.
   공개 주문은 s3의 tile 주문 의미(order-3, fungible 1, P2/P2-2, C)를 유지한다.
   단독 기술 격리 dev이며 s3의 다른 주문/지연 사건을 검증한 것으로 세지 않는다.
5. 두 셀 모두 dev layout seed 10501, actor r2/west, 초기 base:
   r1=(−.85,−2.25,0), r2=(−.85,−.85,0), r3=(−.85,.55,0)를 **setup 전용**으로 고정한다.
   다른 두 로봇은 이 dev에서 hold한다. runtime controller에는 이 실제 pose나
   tile_1 연결을 넣지 않는다. eval/setup identity와 공개 fungible 주문을 분리한다.
   private spawn에서 자기 pose provider를 초기화하지 않는다.
6. 시작부터 자기 RGB+정적 지도+자기 명령으로 접근하고 현재 pose/history를 계속
   넘긴다. tile west는 물체 장축에 대해 서→동 정렬이다. 공개 역할을 선택했다고
   실제 정렬을 확인한 것으로 세지 않는다. 최종 근접 범위는 자기 영상 추정
   x=.176–.180 m, |y|≤.005 m, 장축 오차≤15°다. 원본 .155 m 정류장으로 teleport하거나
   probe 초기 관절을 복사하지 않는다. 근접 진입 불가/영상 가림은 실패로 남긴다.
7. native port glue는 다음 계약을 지킨다.
   - 공개 주문+role로 `TileWestSkill`을 만들고 own `initial_servo_command`와 이후
     실제 발행 명령만 `on_command`에 전달한다(각 행 `robot_id`, `t` 필수).
   - 해당 로봇 JPEG/hash/시각/ID만 `on_frame`에 준다. 실제 관절/GT/심판 입력 금지.
   - `step`의 arm/look/hold를 기존 저수준 명령 port로 보내고 실제 발행 결과를
     이력에 되돌린다. 반환값만 보고 명령을 발행했다고 가정하지 않는다.
   - `phase=holding`이고 `carry_permitted(now)`가 true일 때만 동일 own navigation의
     주행 명령을 사용한다. 이때 기본 hold 출력을 주행 뒤에 다시 덮어쓰지 않는다.
     false/terminal/하역 전이면 base 정지. 조작 중 base 명령은 실패다.
   - own navigation의 정적 C landing 목표/자기 관측 도착 믿음으로만
     `request_release(now=..., destination_zone='C')`를 호출한다.
     host의 arrived/delivered flag로 호출하지 않는다. navigation waypoint는 배송 완료가 아니다.
8. `python3 scripts/disk_report.py`, `agent_lock.py status`로 확인하고, 다른 잠금이
   없을 때 조정자 driver PID로 `acquire --owner <담당> --branch <브랜치> --purpose t05-tile-2cells
   --pid <PID> --expected-minutes <실제 운영 예약>`를 잡는다. wall 성능 비교가 아니며
   SIM cap을 wall 분으로 변환하지 않는다. `ugrp_session.py run`에서 실행하고 소유 프로세스만 정리한다.

## 정확한 두 셀과 중단 규칙

| ID | 조건 | 평가 전용 조작 | 전체 cap | 기대 확인 |
|---|---|---|---:|---|
| t05-c-normal-01 | no_comm, r2/west, 위 초기 배치 | 없음 | 900 SIM초 | 실제 spawn→자기 접근→7 mm 파지→들기→C→방출 |
| t05-c-miss-01 | 같은 controller/config/seed/배치 | 첫 close 명령부터 r2 실제 gripper를 열린 상태로 유지하는 actuator fault | 900 SIM초 | 미파지 RGB를 보고 carry/방출/배송 완료를 주장하지 않음 |

**합계 상한 2×900=1,800 SIM초.** 초기화 뒤 첫 physics tick부터 staging·팔 전이·
관측·주행·하역·실패 종료를 모두 포함한다. 조작 객체를 나중에 생성해도 episode
cap은 새로 시작하지 않는다. 각 셀은 terminal/안전 중단/900초 중 먼저 온 시점에
끝낸다. cap 도달은 실패/미도달이며 재시도·warm-up·보정 run은 이 2셀에 숨기지 않는다.
추가 시행은 새 ID·별도 예산이다. ENOSPC는 HOST_ERROR로 남기며 결과를 덮지 않는다.

실패 셀에서도 **발행 명령**은 close PWM 1500으로 남는다. adapter만 실제 gripper를
open 2000에 유지하고 fault 발생 시각·적용 상태는 eval_only에 기록한다. controller에
fault flag/접촉/held 정답/심판 알림을 주지 않는다. 첫 close까지 못 갔으면 fault 미도달
1건으로 남기며 미파지 검증 통과로 세지 않는다. 원래 영상 대신 fake RGB를 넣지 않는다.

## 관측·평가 판정

- 원래 .155 m 상대 정류장의 v3 IK는 예상 holding 영상 전체 가림 때문에 후보가
  거절한다. 새 근접 범위가 실제로 접근 가능하고, .007 m 물체에 집게가 들어가며,
  wrist 영상에서 경계가 보이는지 우선 확인한다. command FK 잔차가 작아도 실제
  손가락 지면 관통/팔 self-contact/물체 미끄러짐을 통과로 바꾸지 않는다.
- 정상 셀은 holding 양성 프레임 ID/hash, 낮추기/닫기/들기 실제 궤적, 운반 중
  held 유지, 열기 뒤 실제 해제, 물체 전체 C 포함과 착지를 분리 기록한다.
- 심판은 현재 `zone_study_referee.v2`와 source hash를 사용한다: 전체 landing
  rectangle 포함, z<.05 m, finger-held=false, speed<.01 m/s가 연속 2 SIM초.
  이 판정과 GT 궤적·접촉·높이는 eval_only에만 저장한다.
- `skill_complete`와 `Referee.orders_complete`를 다른 필드로 남긴다. local released가
  true인데 심판 배송 false면 거짓 배송으로 승격하지 말고 오차/오배송으로 감사한다.
  실패 셀에서 허위 holding·운반 진입·허위 local completion 여부를 각각 확인한다.
- 벽/바닥/로봇/하중 접촉, base 병진·회전, 실제 관절 궤적, PWM 한계 근접,
  미파지/영상 불확실/pose_uncertain/adapter 오류와 단계 미도달 원인을 보존한다.
  팔 접촉·마찰 보정이 필요하면 후보를 바꿔 새 코호트로 시작한다.
- 정상/미파지 분모는 각각 1. 두 셀을 정상 배송 성공률 2회로 섞지 않는다.
  네 조건의 동일 코드 fake 검사는 통신 효과·4조건 물리 비교가 아니다.
  C 정적 운반 길이 2.70 m는 evaluator 자료이며 실제 주행/시간이 아니다.
  B(정적 5.55 m)는 여기서 실행하지 않고 정식 별도 코호트에 남긴다.

## 원본·TensorBoard 인수

각 시도 raw는 `/Users/changmin/projects/ugrp/outputs/t05-tile/<후보SHA>/<새시도ID>/`에
배타적으로 생성한다. own JPEG/텍스트/명령 전부, 명령·관측 주기, 단계·실패 로그,
SIM초(staging 포함), eval_only, 환경/설정/source closure, 정상·실패 영상,
파일별 SHA-256 manifest를 보존한다. 새 모델 호출 예산 0이며 호출수/비용은 실제
0인 경우에만 0으로 기록한다. 시뮬레이션 성공을 실물 성능으로 표현하지 않는다.

실행이 종료·회수된 뒤 `docs/tensorboard.md`에 따라 성공/실패 둘 다 primary
`outputs/tensorboard`의 새 snapshot으로 내보낸다. 기존 manifest와 source hash를
대조해 중복 변환을 피한다. `outputs/tensorboard-view.json`을 쓰기 직전에 읽고
자기 키만 추가한다. 기존 서버 소유/PID/logdir를 확인하고 다른 작업의 서버를
중지하지 않는다. native TensorBoard에서 새 데이터·영상 등록, HParams 조건/역할/
code SHA, 성공·SIM시간·명령수·모델 호출/응답시간 카드를 원본과 대조하고 dashboard
링크를 보고한다. 해당하지 않는 응답시간은 0을 만들어 넣지 않는다.

현재: **두 셀 모두 미실행, raw/영상/TensorBoard 없음, 물리 준비 미완료.**
