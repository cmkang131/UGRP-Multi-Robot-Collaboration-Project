# 실행 경계 목록

전체 행 목록은 access-inventory.csv다. **57파일·753개 구문 위치**를 SHA별로 읽었다. MjData/native API 구문은 빔 adapter14·고정 의존성215·release36·reloc74·E2E24곳이다. 한 줄은 여러 역할을 가질 수 있고, 이 수는 제어 입력 위반 수가 아니다. CSV는 `data/d` 별칭·`.data`·native API·카메라/명령/감사 구문을 찾은 목록이다. 모든 동적 import의 완전한 의존성 폐쇄나 런타임 누출 검증으로 표현하지 않는다. 아래 표는 사람이 확인한 사용 목적이다. 파일은 source-manifest.json의 해당 SHA 기준이며 현재 다른 브랜치의 같은 파일과 줄이 다를 수 있다.

## 빔 짝 교사

실행 adapter `08f12921`, 보존 기록 `4fc42672`, 고정 교사 의존성 **26f84d0f**(PR #522). 단일 실행기를 복사해 제어 로직을 다시 작성하지 않고 scheduling yield와 backend 공급자만 주입한다.

|영역|읽기/쓰기와 위치|배치 이식 경계|
|---|---|---|
|physics/clock|의존 `scripts/run_grasp_act_teacher.py:204–214,250`의 `data.time`, `eq_active`, `_physics_step_for`; `sim/masterpi_drive_friction_v7.py:196–231`의 ctrl/qfrc·릴레이·mj_step|세계별 tick/deadline·명령 릴레이를 보존하고 공통 엔진만 advance. sleep은 선택 물리 옵션이며 LLM pause로 사용하지 않음|
|자기 카메라 가시 측정|`sim/grasp_act_visible_measurements.py:10–46`: data.geom_xpos/xmat·body pose, 자기 base를 써 상대좌표 생성. `scripts/audit_grasp_act_visibility.py:20–126`: cam_xpos/xmat·fisheye/FOV·mj_ray|시뮬 전용 완전 인식 교사 경계다. 자기 RGB에서 현재 보이는 것만 위치 측정으로 허용하며, 가시 정답을 학생/LLM에 보내면 안 됨. ray용 host 운동학은 해당 lane GPU 상태와 같은 시각이어야 함|
|held 숨김|adapter `scripts/run_beampair1.py:212–240,263–287`, `harness/beampair_teacher.py:30–72`: 닫기 명령을 latch하고 양쪽 beam/band·기억을 제거|guard를 lane별 생성. 먼저 캡처한 두 입력 중 두번째가 같은 tick 닫기 뒤 실행될 때 재정제하는 순서 유지. GPU snapshot 전체를 controller로 전달하지 않음|
|명령|의존 runner `apply:20–30,361–366`; `sim/grasp_act_port.py:71–117`의 per-wheel deadline; `sim/camera_robot_port.py:236–275`의 명령 서보 보간·clock|issued command history와 port state만 교사에 전달. `drive_input_state`, PWM, interpolation queue도 lane별. 실제 관절 읽기를 발행 이력 대신 쓰지 않음|
|카메라/기록|runner `278–285,330`; adapter `189,338–339`, `harness/failure_rgb_tail.py`|평가 top·자기RGB·학습off·last10s tail을 구분. 기록 렌더가 제어 capture/frame_id를 늘리지 않아야 함|
|평가/성공|runner `snapshot:33–57`, `scripts/cargo_formation_teacher.py:218–238`의 contact/ncon·mj_contactForce, runner `382–386`의 physical_success|body/geom 최소높이·tilt·손가락 force·qpos는 평가 전용. GPU force 공급자를 쓰고 기존 양쪽 명령완료+joint hold 성공식을 보존. 평가 원장이 교사 단계 전환의 입력이 되지 않도록 기존 통로만 유지|
|감사/회귀|`harness/grasp_act_input_audit.py`; `tests/test_beampair1.py`·2·4·5·6, 의존 visibility/visible-world/port tests|비가시·held 0/0, 실질 hidden tick>0, default off, 두 lane의 메모리/GO/ACK 오염 반례. 구현 뒤 해당 변경 범위 1–3파일만 먼저 시험|

낮은 계층 `sim/multi_masterpi_production.py`는 MjData 생성/reset, camera rendering, robot base_xyz/base_rpy, servo/ctrl·접촉/운동학 API를 소유한다. CSV의 많은 직접 접근은 이 공통 계층이다. warp2가 두번째 world 클래스를 만들어 대체할 범위가 아니다.

## release24

실행 **8b7f2f45**, 회수 기록 `0caba502`(PR #491, #522와 같은 grasp 계열). 해제 흐름은 #522의 빔 adapter와 동일한 실행 코드가 아니므로 별도 pin을 쓴다.

|영역|확인한 경계|배치 이식 시 보존|
|---|---|---|
|직접 MjData|`scripts/run_grasp_act_release.py`의 Eyes.classify/point FOV·mj_ray, own_end_world, advance, scan/band 관측, snapshot/force/inside 판정. 버전별 실제 행은 CSV release 필터 참조|prefix grasp와 release 이후를 구분. 실제 좌표로 성공을 계산하는 평가자와 보이는 상대 관측 어댑터를 분리|
|카메라|look_capture/regrasp_capture와 `sim/release24.py` 현재 setdown 축 융합, `sim/release19.py` TopCameraAudit|실제 주변 RGB를 캡처하며 자기 끝 색만 본 뒤 완료하지 않음. top control read0. 기존 RGB 해상도/epoch·setdown 관측창 불변|
|명령/동기화|PairReleaseCode, own issued odom, 두 로봇 낮추기·열기·후퇴, 재파지 barrier|세계 단위 coroutine; 같은 세계의 r1/r2 장벽을 여러 세계에 공유하지 않음. port 보간/lease를 substep마다 적용|
|감사/평가|HeldAudit.read/measurement/pick, evaluation-only snapshot·force·grip_site, prefix success·release done·최종 inside 오수용 검사|held pose 숨김·0/0, prefix 실패를 release n/N에서 숨기지 않음. GPU contact와 기존 최종 margin/angle/hold 식 사용|
|기록/테스트|`sim/failure_rgb_recording.py`, `tests/test_release24.py` 등 실제 release24·axis/current-window·top audit 시험|tail은 기록 전용. 고정 JSON 결과·원본 경로·hash, 잘못된 수용도 보존|

## reloc 정적·주행·운반

소스 **644289a7**, 실행별 과거 pin은 baseline-evidence.json(source_shas)에 따로 있다. reloc15는 gcp1의 과거 NOT_READY 기록이며 새 gcp2 성능으로 합산하지 않는다.

|흐름|직접 읽기·카메라·명령·감사·판정|배치 이식 범위|
|---|---|---|
|저장 RGB/정적 재분석|`scripts/offline_self_map.py`·`scripts/replay_ownmap_s2.py`: 저장 이미지·발행명령·고정 지도/보정. 현재 물리 상태를 진행하지 않음|MJWarp physics 경로 제외. 동일 JPEG/PNG·frame_id/RNG를 유지한 CPU 작업큐. 고정 pose를 렌더하는 변형은 mj_forward/카메라만 따로 묶고 기존 RGB 재생 결과와 분리|
|자기지도 주행|`scripts/run_self_map_diagnostic.py:267–319` capture→해시검증→RGB→InputAudit.receive→issue→eval_sample→advance_to. `sim/own_map_closed_loop.py:17–29` contact/ncon; parent `sim/final_environment_checks.py:44,106–153` clock·camera/base labels·weld|backend.capture/issue/advance_to만 공통 엔진에 연결. 5Hz 제어/10Hz 기록·SIM deadline·compute budget 유지. truth/contact는 write-only supervisor·평가에만|
|운반/회전|`scripts/run_solo_grasp_act_teacher.py`의 시간/eq_active·visible local geometry·최소높이/contact·10Hz stepping, `sim/solo_carry_to_zone.py`·CommandPose; `scripts/run_reloc10_rotation_check.py:73–100` 고정 명령 회전|입력은 자기 RGB/발행명령/허용 정적 지도. held world pose 금지. 주행오류·false correction·destination release를 따로 평가|
|고정 명령 물리재생|`scripts/replay_reloc15_carry.py:37,94–106`의 data/port ticking, overview+r1/r2 render|새 자율 성공이 아닌 진단이다. scene/source·명령 궤적 hash를 고정하고 GPU 오차를 기록|
|기록 불변|`harness/failure_rgb_buffer.py`, selfmap diagnostic:313–318|raw world.render로 tail을 남기고 control port.capture()를 추가하지 않음. reloc15에서 발견된 frame_id/RANSAC seed 변경 결함이 다시 생기면 실패|

## LLM E2E

확인한 현재 worker pin **f529e078**. `scripts/run_e2e_ownmap_live.py:655–711`은 capture→자기RGB 처리→host.step_to→transport.step→issue→advance_to(.05 SIM초)다. `harness/e2e_s4_live.py:250–258`→`harness/s4_llm_host.py:427–437`의 polling은 물리 엔진을 직접 돌리지 않는다. 응답 대기 중 세계를 정지시키는 새 모드는 현재 스케줄 의미와 별도로 구분해야 한다.

직접 MjData는 `sim/zone_s3_no_prior.py:117–140`의 nonfinite/base/cargo/contact 평가, `sim/solo_cyan_v106.py:82–94` 평가 body, `sim/final_environment_checks.py` clock·advance·camera label·weld 접촉에 모여 있다. `sim/e2e_ownmap_live.py:58–69`의 capture cache는 동일 세계·동일 SIM 시각에만 유효하다. 공유 GPU 배치의 전역 시각으로 캐시 키를 만들면 안 된다.

자기RGB/자기 명령만 robot/link/LLM에 전달하며 static map 예외는 기존 번들 규칙대로다. 평가 성공/접촉을 판단 입력에 넣지 않는다. 통신 조건별 메시지는 그 세계·그 조건 채널만 사용한다. request/response와 image hash, call_id→ledger→provider receipt를 보존한다. 정상 finish_reason이 아니면 비용을 남기고 행동/메시지를 실행하지 않는다. 모델 키·에이전트 자격 증명은 Mac 중계에만 둔다. 상세 pause/reset 설계와 검증 반례는 llm-batching.md에 있다.
