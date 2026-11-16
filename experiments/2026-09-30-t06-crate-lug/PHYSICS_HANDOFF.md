# T06 조정자 물리 인계 — 미실행, 2 × 900 SIM초

## 현재 판정과 실행 전 차단점

이 후보는 `heavy_crate_lug_decisions_v1` **판단 로직**이다. 자기 RGB에서 얻을
lug 정렬·파지·holding·목적지·바닥 지지·해제 판정의 인터페이스와 고정 enum 동기화를
구현했다. 실제 영상 판독기와 native arm/navigation 어댑터는 아직 없다.
새 `zone_crate_dispatch.PairTeam.start`는 crate에
`CRATE_PHYSICAL_ADAPTER_UNAVAILABLE`을 반환한다. 기존 봉인된 PairTeam/연구 runner는
수정하지 않았고 opt-in facade로 자동 전환되지 않는다.
FakeM2나 긍정 fake 관측을 넣어도 이 거절은 해제되지 않는다.

따라서 **이 SHA로 실행 가능한 crate 물리 CLI는 없다. 물리 인수 준비는 차단**이다.
아래는 어댑터를 구현·검토하고 새 실행 번들에 등록한 뒤 조정자가 수행할 정확한
최소 진단이다. 기존 `probe_zone_cargo --probe pair_crate`는 GT 교사이므로 이
학생 검증의 대체 실행으로 쓰지 않는다. fake 통과를 `physical_supported=true`로
바꾸거나, 기존 beam 실행기에 crate를 넘겨 진행하지 않는다.

실행 관문:

1. own RGB 어댑터가 실제 JPEG와 자기 발행 명령만으로 `CrateEvidence`를 만든다.
   명령 발행·waypoint 도착·교사 contact로 yes를 채우지 않는다. body를 lug로
   오인하지 않고, 어둠/가림/불명은 unknown이어야 한다. 새 자료/보정 예산은 별도다.
2. native 어댑터는 `observe_lug/approach_lug/close_lug/lift_lug/carry_to_zone/lower_lugs/open_lugs`
   의미 명령을 해당 로봇의 port에만 연결한다. base 명령은 최대 0.1 SIM초로 제한하고,
   hold/abort에서 예약된 미래 동작을 취소한다. 유지 중인 arm/gripper 목표와
   실제 도달은 구분한다. 자기 명령 이력에 측정 관절/접촉을 넣지 않는다.
3. 두 actor가 독립 제출한 공개 주문·배정·정적 map 해시를 맞춘다. host가 상대 job을
   대신 만들거나 GT로 파트너/역할/우회를 정하지 않는다. 동시 GO는 동일 control-grid
   시각에 소비하고 한쪽이 놓쳤으면 다음 동작을 차단한다. 이번 역할은 r1=west,
   r2=east뿐이며 r3/대칭 배정은 T07 #323 소유다.
4. 최종 3D MasterPi 모델, `walls_v3`, 표식 0, 기존 카메라 배치/FOV,
   `cargo_noslip_v1`, weld OFF가 실제 Scene/XML/접촉 옵션과 일치해야 한다.
   P01 #305는 작업 중 `6c754f2d`로 병합됐지만 registry 등록을 이 crate의 실제 장면
   합성/접근/배송 검증으로 승계하지 않는다. 실행 시 실제 적용값을 별도로 확인한다.
5. 새 어댑터·설정·자기 기억/센서 버전·enum 의미를 네 조건에 동일하게 적용한다.
   `no_comm`에서도 동일한 고정 상태 채널을 사용한다. 조건별 제어기 override 금지.
   이번 두 셀은 dev `no_comm` + 공통 상태 채널로 고정하며 통신 효과 비교가 아니다.
6. 구현 소스를 먼저 커밋하고 신규 runnable/workflow 번호를 예약한다.
   `sim_cli`/`configs/simulation_workflows.json`의 표준 관리 경로에 연결하고,
   코드 SHA·Python source closure·환경/모델/지도·카메라 변환·관측/명령 주기·역할
   배정 해시를 고정한다. 배정 해시와 제어 코드 해시는 별도 항목이다.

## 두 셀의 고정 조건

원본 `configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json`와 지도는 수정하지
않는다. 신규 dev fixture에 출처/차이를 기록한다. 본연구 DRAFT·seed·판정을 바꾸지 않는다.

| 항목 | 정상 `t06-crate-normal` | 실패 `t06-crate-east-grasp-fail` |
|---|---|---|
| 역할 | r1 west, r2 east | 동일 |
| 총 로봇 | 3대, r3는 제어기가 hold | 동일 |
| dev seed | 611 | 611 |
| crate setup pose | `(1.275, -2.15, 0)` | 동일 |
| 화물 | 원본 heavy_crate 900 g, 동일 body/lug/마찰/관절 | 동일 |
| 주문 | s2 `order-3`, `crate_1` → B | 동일 |
| 목적 영역 | B 중심 `(4.60,-2.10)`, half extent `(.30,.70)` | 동일 |
| 실제 접근 목표 | west `(1.02,-2.15,0)`, east `(1.53,-2.15,π)` | 동일 |
| 시작 base XYyaw | r1 `(-.85,-2.25,0)`, r2 `(-.85,-.85,0)`, r3 `(-.85,.55,0)` | 동일 |
| 실패 주입 | 없음 | r2의 첫 close부터 gripper를 열린 명령으로 유지하여 한쪽 실제 미파지 |
| 셀 종료 cap | staging 포함 900 SIM초 | staging 포함 900 SIM초 |

위 정류장/물체 좌표는 **장면 setup·평가용**이다. 학생의 현재 자세로 주입하거나
로봇을 정류장으로 teleport하지 않는다. spawn 할당은 원본의 shuffle 대신 고정한
dev 변경이며, reset z는 최종 모델의 정상 Scene reset 결과를 기록한다.
다른 원본 화물 배치는 유지하고 다른 배송 주문을 수행하지 않는 T06 격리 진단으로
기록한다. s2의 좁은 문 막힘 이벤트는 dev fixture에서 비활성화한다는 차이를 명시하고,
T09b의 이벤트 발견/우회 또는 원본 s2 전체 성공으로 보고하지 않는다.

실패 주입은 host의 **물리 명령 고장**으로만 실행한다. 주입 사실·GT holding·미래
시각을 학생에게 알려주거나 RGB 판정을 강제로 바꾸지 않는다. 평가에서 r2 lug 미파지가
실제로 성립했는지 확인하고, 성립하지 않았다면 `INJECTION_NOT_REALIZED`로 기록한다.
같은 파일을 덮어 재시도하지 않는다. 새 시도에는 새 run ID와 별도 예산이 필요하다.

## 단계별 확인과 판정

| 단계 | 로봇 판단 입력/동작 | 별도 평가에서 반드시 확인할 것 |
|---|---|---|
| 접근 | 자기 영상 + 정적 pickup bay/map으로 배정 lug 접근 | 실제 spawn→정류장 경로, 양쪽 접근 완료, body 파지/벽·로봇 관통 없음 |
| 파지 | 양쪽 close-ready의 최신 영상 뒤 공통 GO | 각 집게가 자기 lug를 잡음; body·반대 lug 파지와 명령만 닫힌 경우 구분 |
| 들기 | 양쪽 grasped 판정 뒤 같은 시각 lift GO | 실제 양측 lift 시작 시각, 하중/관절 한계, 과도한 기울어짐·낙하 |
| holding | 양쪽 자기 holding yes가 있어야 carry GO | 양쪽 접촉·화물 바닥 높이·미끄러짐·지속 시간과 각 RGB 판정 대조 |
| 운반 | fresh holding 상태가 계속 있어야 최대 .1초씩 전진 | 넓은 문 실제 중심선 crossing, 전체 편대와 화물의 벽 여유·접촉·낙하 |
| 배치 | 각자 목적지 영상 확인 후 lower; 지지 확인 후 open | B 내부 착지·정지·해제; 팔 명령 완료를 배송 성공으로 세지 않음 |
| 실패 | unknown/abort/heartbeat 소실/GO 누락이면 hold·중단 | 남은 예약 명령 0, 짝도 abort, 단독 운반·임의 재파지·성공 통보 없음 |

정상 셀에서는 들기 후 **운반 전 1.5 SIM초 holding**을 새 어댑터의 고정 관측 구간으로
포함한다. 이 시간은 아직 이 판단 모듈에 물리 동작으로 구현된 값이 아니다.
최저 화물 바닥 높이 ≥12 mm를 그 구간 내내 유지하고 양측 lug 접촉/미끄러짐을
평가한다. 로봇 최대 기울기 <10° 및 운반 중 화물 바닥 재접촉 0을 진단 기준으로
고정한다. 이는 과거 교사 probe의 수치를 **새 dev 판정에 명시적으로 채택한 제안**이며,
최종 v3에서 성립한다는 측정 주장이 아니다. 어댑터 등록 시 이 관측 구간과 기준도 pin한다.

배송 판정은 기존 `zone_study_referee.v2`를 평가 영역에서 적용한다.
crate landing half extent `(.12,.05)` 전체가 B 내부에 있고, body z <.05 m,
held=false, 속도 <.01 m/s 조건이 연속 2 SIM초 유지되어야 한다.
최종 지지/관절/접촉 판정은 `eval_only/`에 남기며 학생 단계 전환에는 사용하지 않는다.
`sequence_complete_unconfirmed`와 referee 배송 완료를 별개로 기록한다.

이번 편대 정적 경로 길이 **3.35 m**는 P09의 평가 계산이다. 학생에게 P09 inventory,
숨은 위치 또는 계산된 평가 경로를 전달하지 않는다. 경로 존재는 실제 주행·holding
가능성의 증명이 아니다. 하중·관절·마찰·양측 영상 인식 한계가 드러나면
**DESIGN_BLOCKED**로 보고하고 질량 감소, lug 확대, 마찰 증가, weld 또는 교사 보정을
몰래 넣지 않는다. 실패 셀의 안전 중단을 배송 성공 분자에 넣지 않는다.

## 실행·보존·보고

- 최소 예산은 정상1+파지실패1, 총 **2 × 900 = 1,800 SIM초**다. staging, 탐색, 팔 이동,
  holding, 대기, 실패 정리까지 포함한다. 각 cap은 실패/미도달이며 성공으로 대체하지 않는다.
  새 모델 호출 예산 0; wall 시간/처리량 환산과 4조건 확증은 범위 밖이다.
- 물리 작업은 조정자 worktree에서 실행한다. `scripts/disk_report.py`로 여유 공간을 확인하고
  드라이버 PID를 얻은 뒤 `scripts/agent_lock.py acquire --owner <실제 소유자> --branch
  <실행 브랜치> --purpose T06-crate-physics --pid <드라이버 PID> --expected-minutes <예상 분>`을
  수행한다. `ugrp_session.py run`으로 자식을 관리하고 종료 시 자기 세션과 잠금만 정리한다.
- raw는 `/Users/changmin/projects/ugrp/outputs/t06-crate-lug/<candidate-sha>/<cell>/`에
  새로 저장한다. 실행 SHA/입력/설정/모델/환경 해시, 전체 명령·원본 자기 RGB·판독 결과,
  송수신/거절된 enum, GO 시각, 단계 SIM초, referee trace, 실패/관통/낙하·하중/관절/마찰
  진단, 정상 분모1·실패 주입 분모1, 명령 수·모델 호출0·비용0을 남긴다.
- ENOSPC·렌더/워커 오류는 HOST_ERROR로 남기고 로봇 실패/설계 불가와 구분한다.
  raw 원본과 과거 결과를 덮거나 지우지 않는다. 원본 파일별 SHA-256과 존재/크기를 검증한다.
- 완료/실패 결과를 **새 native TensorBoard snapshot**으로 변환한다. 공용 primary
  `outputs/tensorboard`, `outputs/tensorboard-view.json`의 실제 logdir/소유 PID를 확인하고
  자기 키만 추가한다. 관련 baseline과 cohort를 분리하고 실제 event loading, 원본 해시,
  영상 등록, HParams 열, success/SIM초/명령 수/model calls/response time의 존재하는 값을
  화면과 대조한다. 없는 metric을 0으로 꾸미지 않는다. dashboard 링크와 미완료 검사를 보고한다.
- 현재 인계에서는 물리/렌더/모델 실행 0, 새 물리 TensorBoard snapshot 없음이다.
  실험 결과 수집 뒤에만 해당 workflow를 수행한다. 테스트 pass 수를 물리 성공 지표로 만들지 않는다.

참고: [P09 요구](../2026-09-30-scenario-capabilities/REQUIREMENTS.md),
[T06 원문](../2026-09-30-scenario-capabilities/TASKS.md),
[실행 버전](../../docs/execution_versioning.md), [TensorBoard](../../docs/tensorboard.md).
