현재 미실행 후보는 `zone-pair-v76-fixclock-grasp-entry`(workflow `2.12.0`)이다. v76(PR #263)은 main의 v79에 opt-in 공동 운반 정책 `b-v6c`를 더한 것이다. 번호 v76과 workflow 2.12.0은 2026-09-29 조정자가 배정했다(#256 v77/2.9.0, #257 v78/2.10.0, #249 v79/2.11.0 다음 병합). v79는 `RETIRED_BUNDLE_IDS`로 옮겼다. 2026-09-28–29 단계 probe(PR #260)에서 v6 b-only 정렬은 RecoveryLocalizer의 PF 시계와 프레임 시각이 1e-9 s 안에서 어긋나 fix 나이가 음수가 되어 막혔고, 파지 입장은 정렬 허용오차(ex ±12 mm) 중 −8…−4 mm에서만 통과했다. `b-v6c`는 PF 시계를 예측한 관측 시각에 맞추고, 파지 거리의 빔 색 모델로 standoff fit과 pre-close 부분 관측을 하며(빔 폭의 연속 단면 요구), 마지막 하강 자세를 정착시킨다. v5h·b-only·a+b·b-boot·a+b-boot의 동작은 바뀌지 않는다. v6c 단계 probe는 병합 전 v76(main v70 위)으로 돌렸다. 등록 초안 `prereg_v6c.json`은 이 병합 뒤 한 번 다시 봉인했다. [v6c 기록](../experiments/2026-09-29-pair-v6c/README.md)

이전 후보 v79의 설명:

현재 미실행 후보는 `zone-study-integration-v79-masterpi-v3`(workflow `2.11.0`)이다. v79(PR #249)는 v78에 명시적으로 버전을 붙인 MasterPi v3 장면 2종(`zone_wide_door_geometry_v3`, `zone_wide_door_geometry_v3_dock_v1`)과 v3 명령 기하를 더한 것이고, v2 장면과 연구 층은 바뀌지 않았다. v78은 `RETIRED_BUNDLE_IDS`로 옮겼다. 아래 B6 설명의 v73은 병합 전 후보 번호이고, B6가 main에 들어간 번호는 v78이다. 2026-09-28 B6(#224, PR #254 사전 등록 초안): 물리 소유자(`scripts/run_zone_study_integration.py`)에 평가 전용 심판 `harness/zone_study_referee.py`와 시나리오 숨은 사건 훅을 붙였다. 연구 층(`harness/zone_study_integration.py`의 `IntegratedTrial`)은 번호 외에 바뀌지 않았다. v70(#246)·v71(#249)·v72(#256)는 열린 PR이 예약해 다음 번호 v73을 썼고 v69는 `RETIRED_BUNDLE_IDS`에 보존한다. 2026-09-28 Kiro가 이 PR(#257, Claude)의 검토 지적 P1-G·P1-H·P1-I·P2-K·P2-M을 같은 번호 안에서 고쳤다(v73으로 기록된 실행은 없다; main과 열린 PR 전체에 v73 이후 번호 사용 없음을 확인).

## 평가 전용 심판과 숨은 사건 (v73)

- **배송 판정(물건별, 물리 청크마다 시뮬레이터 정답):** 물건의 착지 직사각형(`sim/zone_cargo.py` `landing_half_extents_m`, 색 상자는 `sim.zone_arena.BOX_HALF`)이 목적 구역 안(`zone_scenario_feasibility.landing_fits` 재사용), 바닥 위(몸체 높이 < 0.05 m), 어떤 로봇 손가락도 닿지 않음, 선속도 < 0.01 m/s가 `SETTLE_S`=2 SIM초 연속이면 확인한다. 배송 시각은 창의 시작, 확인 시각은 `confirmed_sim_s`다. 비유한 값·잘못된 형식의 정답 행은 판정하지 않고 거부한다(`ContractViolation`).
- **확인 뒤 해제(`departed`, 심판 프로필 v2):** 들림(z ≥ 0.05 m)·구역 이탈은 즉시, 파지는 `HELD_DEPART_S`=1 SIM초 이상 이어질 때만 해제한다. 부딪힘이나 손가락이 스친 짧은 접촉은 배송을 풀지 않는다. trial record의 `referee.deliveries`에는 **확인 행만** 넣는다. 지금 서 있는 물건은 모든 확인 행(바로잡은 오배송 이력 포함)을 넣고, 해제된 뒤 다시 정착하지 않은 물건은 넣지 않고 `departed_unsettled`에 따로 적는다. 그래서 이 물건은 배송도 오배송도 아니다(검토 P2-K: 전에는 zone None 행이 오배송으로 집계됐다). `departures`·`departed_unsettled_items`는 평가 블록에 따로 둔다.
- **주문 판정:** 확인 행에 `zone_study_eval.delivery_state`를 그대로 적용한다. 모든 주문이 채워지면 러너가 그 청크에서 에피소드를 멈춘다(`stop = orders_complete`). 로봇에게는 horizon 종료와 같은 일반 종료만 보이고 이유는 전달되지 않는다.
- **지표:** 저장한 trial record에 `zone_study_eval.efficiency_metrics`를 적용해 `par_makespan_sim_s`(PAR-2)·`delivery_rate`·성공과 주문별 완료 시각을 `result.json`의 `eval_only.evaluation`과 `eval_only/evaluation.json`에 쓴다. trial record의 `end_reason`은 심판이 완료를 확인했을 때만 `orders_complete`이고 `end_sim_s`는 마지막 필요 물건의 배송 시각이다. 별도 공식을 만들지 않았다. 심판이 생기기 전에 실패한 실행도 `study/trial_record.json`을 쓰며, `referee.status = not_evaluated`이고 성공이 아니다(검토 P1-G b).
- **숨은 사건(`sim/zone_hidden_events.py`, 실현 프로필 `zone_study_hidden_events.v2`):** 시나리오 `eval.hidden_events`를 SIM 시각에 한 번씩 물리에만 적용하고, 효과 행은 `eval_only/hidden_events.jsonl`에만 쓴다(`result.json`에는 파일 이름과 행 수만). 어느 것도 로봇 입력·메시지·명령 행·깨움을 만들지 않고, 로봇은 자기 카메라로만 알 수 있다.
  - `passage_blocked`·`obstruction_added`: 바닥 아래(z = −5 m)에 둔 정적(mocap) 상자를 개구부로 옮긴다. 상자는 host가 이미 받는 `scene=` 인자로 넘기는 장면 **인스턴스**의 transform을 감싸 XML에 넣는다. 그래서 `harness/zone_own_team_host.py`와 장면 계약 소스(`scripts/zone_pair_dev_contract.py`)는 main과 바이트 단위로 같다(검토 P1-G a). `TaggedZoneScene`은 host가 주입 장면으로 받지 않으므로 화물 없는 `TaggedCargoZoneScene` 쌍둥이를 만들고, 설정·재고·경계가 원래 장면과 같지 않으면 거부한다. 장애물이 없는 시나리오는 이 경로를 타지 않아 장면이 이전과 같다. `passage_cleared`는 되돌린다.
  - `item_moved`: 자유 관절을 `to_pose_m`으로 옮긴다(잡혀 있으면 효과 없음).
  - `item_dropped`(그리퍼 서보 고장): 잡고 있는 로봇의 그리퍼 위치 액추에이터 목표를 물리 스텝 안에서만 열림(PWM 2000)으로 바꾸기를 `GRIPPER_FAULT_S`=1 SIM초 동안 한다. 스텝 뒤에는 발행한 목표로 되돌리므로 포트의 발행 상태, 로봇의 `servo_command_pulses`, 명령 행에는 나타나지 않는다. 접촉·마찰·접촉 프로필은 바꾸지 않는다(검토 P1-H: 손가락 접촉 끄기는 `cargo_noslip_v1`의 명시 `<pair>` 때문에 효과가 없었고 AGENTS.md 정상 물리 원칙과도 맞지 않았다). 잡혀 있지 않으면 효과가 없다.
  - `robot_hold`(바퀴 구속): 그 로봇의 바퀴 모터 상태와 명령을 물리 스텝 안에서만 0으로 두기를 `duration_s` 동안 한다. 스텝 뒤에는 발행한 명령으로 되돌리므로 로봇이 보는 `actuator_state.motor_commands`와 명령 행은 발행한 그대로다(검토 P1-I: 전에는 `port.stop()`이 자기 명령 상태를 정지로 바꿨다).
  - 스텝 감싸기(`ActuatorFaults`)는 `robot_hold`·`item_dropped`가 있는 시나리오의 world 인스턴스 하나에만 설치한다. 사건이 없으면 아무것도 만들거나 감싸지 않는다.
- **검증:** `tests/test_zone_study_referee.py`가 네 조건에서 완료 유무·숨은 사건 유무만 바꾼 두 실행의 로봇 요청·깨움·실행 호출·메시지가 정지 시각까지 같음과, 연구 층 소스 폐포에 심판이 없음을 확인한다. `tests/test_zone_hidden_events.py`는 실제 `CameraRobotPort`와 명시 `<pair>` 파지가 있는 toy MuJoCo 모델을 실제로 스텝해 낙하·정지와 로봇이 보는 명령 상태의 불변을 확인하고, 실제 world XML이 숨은 장애물 몸체 외에는 같음을 확인한다. 두 파일 모두 `scripts/run_ci_tests.py` TEST_PATTERNS에 있다. 실제 로봇 world의 짧은 물리 프로브는 `scripts/probe_zone_hidden_events.py`(진단 전용, 아래 결과)다.
- **아직 확인하지 않은 것:** 실제 연구 에피소드에서 심판이 i1/i2 배송을 확인하고 멈추는지, s2·s3·s5 장면 전체 실행. 현재 러너의 `host_spec`은 i1(청록 상자)·i2(긴 막대) 장면만 받으므로 s1–s6 장면 실행은 별도 작업이다.

### 숨은 사건 물리 프로브 (2026-09-28, 진단 전용)

`scripts/probe_zone_hidden_events.py`, 코드 `3db43850`(작업 트리 깨끗), MuJoCo 3.12.0, `OMP_NUM_THREADS=1`, `ugrp_session.py run fix257-probe`, 부하 평균 시작 16.94/15.04/16.04 → 끝 13.91/14.77/15.92, wall 40.5 s. 모델 호출·연구 층·로봇 판단은 없다. 연구 결과가 아니다.

- 조건: 통합 prereg 첫 에피소드(`smoke-i700`, `zone_wide_door_tags_v2`, seed 700, `cargo_noslip_v1`, weld OFF)의 실제 `StudyTeamHost` 두 개를 같은 순서로 스텝했다. 두 world 모두에서 교사(정답, 평가 쪽)가 `box_00`을 r1 앞에 놓고 `scripts/zone_teacher`의 팔 순서·파지 IK로 잡아 들었다. r2에는 같은 주행 명령을 보냈다. 사건 world에만 6.6 s에 `item_dropped`(`box_00`)·`robot_hold`(r2, 2 s)·`passage_blocked`를 넣었다.
- 결과(11개 검사 모두 통과):
  - 6.2 s 두 world 모두 상자 z 0.0857 m, 손가락 접촉 r1(정상 접촉만으로 들린 상태).
  - `item_dropped`: 9.8 s 사건 world 상자 z 0.0159 m(바닥), 손가락 접촉 없음. 대조 world는 z 0.0857 m, r1 파지 유지. 그리퍼 열림은 6.6–7.6 s(4000 스텝)만.
  - `robot_hold`: r2 이동 거리는 6.9–8.6 s 사이 사건 world 0.00001 m, 대조 world 0.217 m. 해제 뒤 8.7–9.8 s에는 0.078 m 다시 움직였다.
  - 세 로봇의 명령 행, 자기 카메라 캡처마다 보이는 `actuator_state`, `servo_command_pulses`가 두 world에서 같다.
  - 장면 XML은 숨은 장애물 몸체를 빼면 같다. 장애물은 (2.2, 0.05, 0.06)으로 올라왔다.
- 원본: `/Users/changmin/projects/ugrp/outputs/fix257-hidden-events-probe-20260928-152803/`(로컬 보관, 원격 백업 아님). `probe.json` sha256 `43d7269cec42ba92c4fad826e65974a3c62f95a5b008e8293aebf7a08ff6f8ac`, `eval_only/hidden_events.jsonl` `623f21ebd2bedb30554b4b2bc51a7a31e001ae0016880a53b7eb31c99fe2638f`, `control_samples.json` `58ee47eb94150577d3abdfea5f882c36065337e1622f89db7f76ba978190e7c7`, `fault_samples.json` `64b53b6f63c8818d3175f34ac82646af6a3a82d74529348aefdd84470a986cbb`, 자기 카메라 프레임 258장.
- 범위: 교사가 잡은 상자 하나와 주행 명령 하나다. 학생 실행기의 파지·재탐색, 긴 막대 공동 운반 중 낙하, s2·s3·s5 장면 전체는 확인하지 않았다.

### 참고 자료 (검토 수정분)

- 내부 모듈 재사용: `sim/zone_own_scene_provider.own_scene`(주입 장면 검사), `sim/zone_tagged_cargo_scene.TaggedCargoZoneScene`(화물 없으면 `TaggedZoneScene`과 같은 XML), `sim/masterpi_dynamics_v2.MasterPiDynamicsV2.pulse_to_joint_targets`(PWM → 집게 닫힘), `sim/multi_masterpi_production._physics_step_for`(모터 필터·구동 힘; 감싸기만, 수정 없음), `sim/camera_robot_port.CameraRobotPort`(수정 없음), `scripts/zone_teacher`(`OPEN`/`CLOSED`, `ArmSequence`, 파지 IK 순서), `harness/visual_arm.solve_grip_ik`, `harness/zone_study_eval.delivery_state/efficiency_metrics`, `harness/zone_scenario_feasibility.landing_fits`.
- 버린 대안: 손가락 `contype/conaffinity` 0(명시 `<pair>`는 필터를 거치지 않아 효과 없음, 검토 프로브 2; 정상 물리 원칙과 충돌), 물건에 `xfrc_applied` 외란(파지가 남은 채 힘만 가해 "떨어뜨림"이 아니라 실험자 힘이 되고 힘 크기를 따로 정해야 함), `port.stop()`/주행 명령 게이트(로봇 자기 명령 상태가 바뀜, 검토 P1-I), host 파일에 XML 훅 추가(동결 장면 계약 변경, 검토 P1-G).
- 외부 라이브러리: MuJoCo 3.12.0(Apache-2.0, 기존 환경 그대로). 새 의존성 없음. 논문은 인용하지 않았다.
- 검토: `outputs/review-256-257-20260928.md`(Kiro RV256)와 PR #257 코멘트.

2026-09-29 main 병합(PR #257): main의 v77(#256 B7 실제 다회 LLM 드라이버, v75 위)에 B6 심판·숨은 사건을 합쳤다. 합성 소스가 v77과 병합 전 후보 v73 어느 쪽과도 달라 새 번호 v78을 썼다(main v77, 열린 PR 최댓값 v76 #263; #249는 v79 예약). v73은 실행 기록이 없고 main에 없었다. v77은 `RETIRED_BUNDLE_IDS`에 보존하고 `llm_driver.json`에 v78을 v77과 같은 발화 상한·드라이버 프로필로 등록했다. workflow는 main 2.9.0 다음 2.10.0이다. 러너는 #257의 `run_loop`(숨은 사건 → 물리·실행기 → 스케줄러 → 심판)에 #256의 `llm.check_trial_health`를 루프 전·매 청크 `step_to` 직후·루프 뒤(final)에 그대로 넣었고, trial record는 심판 블록을 채운 뒤 #256 규칙대로 `failure_class`·`model_usage`와 API 실패 `end_reason='api_failure'`를 적는다(평가 블록은 그 record로 계산한다).

이전 후보 v77의 설명:

현재 미실행 후보는 `zone-study-integration-v77-llm-driver`(workflow `2.9.0`)이다. 2026-09-28 B7(PR #254): 러너에 실제 다회 모델 드라이버(`--llm`, `harness/zone_study_llm_driver.py`)와 본연구 사용량 원장(`harness/zone_main_budget.py`, #222 DB와 별개)을 연결하고, 발화 상한을 번들별 등록 프로필(`configs/zone_study_integration/llm_driver.json`: v66 기본 2/6, 파일럿 10/30)로 고르게 했다. v69는 `RETIRED_BUNDLE_IDS`에 보존한다.

2026-09-28 PR #256 검토 수정: [실패·분석 규칙 보완](zone_study_llm_failure_rules.md)에 코호트 상한/응답 0 중단, API 오류 1건 이상 시행의 infra 분류, 조건 공통 pacing, 정산 실패와 덮어쓰기 거부를 고정했다. 10/30 열린 채널은 실제 상한을 반영한 프롬프트 v3, 기본 2/6·no_comm은 기존 바이트를 유지한다. v72 실행 기록이 없다는 사용자 확인에 따라 새 번들 번호를 등록하지 않았다.

2026-09-29 main 병합(PR #256): main의 v75(#261 v6b 출발 부트스트랩, v70 위)에 B7 드라이버를 합쳤다. 합성 소스가 v75와 병합 전 후보 v72 어느 쪽과도 달라 번호 규칙대로 새 번호 v77을 썼다(main v75, 열린 PR 최댓값 v76 #263 다음; v72는 실행 기록이 없고 main에 없었다). `EXECUTION_BUNDLE_ID`는 main 구조대로 `harness/zone_pair_v6_policy.py`에 두고, v75는 v6b 오프라인 재생 기록 소스로 `RETIRED_BUNDLE_IDS`에 보존한다. workflow는 main 2.8.0 다음 2.9.0이다. v6b DRAFT(`prereg_v6b.json`)는 v6와 같은 방식(#262)으로 봉인 커밋 `15793691` blob 기준 이력 기록으로 돌렸다(관리자 결정 A). main에는 현재 v6 계열 초안이 없으며 다음 초안은 v6c(#263)다.

이전 후보 v75의 설명:

현재 미실행 후보는 `zone-pair-v75-dock-prior-bootstrap`(workflow `2.8.0`, 병합 순서 #256 2.5.0 · #257 2.6.0 · #249 2.7.0 다음)이다. 2026-09-28 v6 dev 코호트(PR #259)에서 b-only·a+b가 출발 위치 부트스트랩에서 막힌 뒤, v70에 opt-in 정책 `b-boot`·`a+b-boot`(정적 지도 dock 행 AMCL식 사전분포 + 첫 움직임 전 정지 관측·belief 검사 팬 스캔)를 더했다. v5h·b-only·a+b의 동작은 바뀌지 않는다. main v70과 열린 PR 최댓값 v74(#249) 다음 번호다. v70은 v6 dev 코호트 기록 소스로 `RETIRED_BUNDLE_IDS`에 보존한다. [v6b 기록](../experiments/2026-09-28-zone-pair-v6b-boot/README.md)

이전 후보 v70의 설명:

현재 미실행 후보는 `zone-pair-v70-beam-relative-multiturn`(workflow `2.3.0`)이다. 2026-09-28 PR #246 main 병합에서 main의 v69(v66 다중 턴 스케줄러 + v67 표식 무관 pair 경로)와 #246의 v6 pair 경로(v68 빔 상대 정렬 + 검토 3)를 합쳤다. 합성 소스는 v68·v69 어느 쪽과도 달라 main과 열린 PR(#248·#249) 최댓값 v69 다음 번호를 썼다. v68은 병합 전 v6 초안으로 오프라인 재생 기록에만 남으며 v69와 함께 `RETIRED_BUNDLE_IDS`에 보존한다. 세 pair 조건(v5h/b-only/a+b)은 이 번들 안에서 `pair_policy` 하나로만 다르다. [v6 기록](../experiments/2026-09-28-zone-pair-v6/README.md)

이전 후보 v69의 설명:

현재 미실행 후보는 `zone-study-integration-v69-multiturn-landmark-agnostic`(workflow `2.2.0`, pair executor v7)이다. 2026-09-28 PR #240 main 병합 충돌 해결에서 main의 v66 다중 턴 스케줄러와 #240의 v67 표식 무관 pair 경로(v5h)를 합쳤다. 합성 소스는 v66·v67 어느 쪽과도 달라 main과 열린 PR 최댓값(v68, #246) 다음 번호를 썼다. v64·v65·v66·v67은 `RETIRED_BUNDLE_IDS`에 보존하며 dev13·dev14 기록의 v67 문자열은 바꾸지 않는다. [병합 기록](../experiments/2026-09-27-zone-pair-dev/merge-main-v69/README.md)

이전 후보 `zone-study-integration-v67-landmark-agnostic`(workflow `2.1.0`, pair executor v7)의 설명은 아래에 보존한다.
[표식 무관 자세 계약·검증 범위](../experiments/2026-09-27-zone-pair-dev/landmark_v5d.md)를 따른다.
이전 v65의 설명과 기록은 아래에 보존한다. 임계값·STATUS v5는 같으며 물리 완주 결과를 승계하지 않는다.

# 통합 러너의 PairTeam·자기 영상·인식 지연 연결

## #223 다회 결정 감사와 v66 후보 (2026-09-27)

감사 기준은 main `97f91cb040bf382973ce84b24b1ca8399e64a6fb`다. 지정한 네 파일은
GitHub main의 blob과 대조했다. **main에도 메시지 수신 재호출은 있었지만, 실행 중인
자기 작업의 경계를 기다리지는 않았다.** #238의 첫 호출 파일럿은 별도
`run_zone_study_pilot.pilot_call_policy()`가 `trigger_on_message=False`, 재질문 999초를
사용했으므로 통합 러너의 다회 동작과 다르다.

| main v64 경로 | 실제 동작과 한계 |
|---|---|
| `zone_study_protocol.Transport` → `EventScheduler._on_message` | 허용 채널에서 받아 실제 inbox에 commit한 뒤 `report`를 예약한다. `no_comm`은 채널이 닫혀 이 경로가 없다. leader는 hub-and-spoke이며 follower끼리 직접 전달하지 않는다. |
| `_on_call_start` | 로봇당 outstanding 1개, 시작 간격 2초. 사고 중 트리거는 하나로 합쳐 완료 뒤 재호출한다. **실행기 job의 BUSY 여부는 보지 않는다.** |
| `IntegratedTrial.snapshot/build_inputs` | 호출 시작 시 자기 RGB·자기 이력·이미 받은 inbox를 고정한다. 나중에 도착한 메시지가 진행 중 호출의 입력에 소급 삽입되지는 않는다. |
| `IntegratedTrial._on_action` → `executor_plan` | 비용 해제 후 그 로봇 API에 claim을 낸다. 진행 중 작업이 있으면 실행기의 `BUSY` 거절이 가능하다. idle `wait`도 10초 hold job을 만들므로 메시지에 대한 새 claim이 거절될 수 있다. |
| 상한 | 논리 호출 30/로봇, HTTP 시도 30/로봇·90/시행, outstanding 1, scheduler retry 1. `w1` 창 하나만 열며 수락 발화 2/로봇·6/창. 기존 `cap_total`은 미설정이지만 창을 재개하지 않아 사실상 시행 6발화다. horizon은 사전등록 값이다. |
| 공통 깨우기 | 시작·자기 작업 완료/실패·자기 장애 사건·자기 타이머(idle 10초, busy 60초, pending 1개). 관측 1초 tick 자체는 호출하지 않는다. 동료 작업 완료/평가 GT는 트리거가 아니다. |

#229 병합 검사의 `test_pair_and_multiple_real_adapter_calls_use_each_own_camera`는
실제 입력 builder·Gemini client·send ledger와 가짜 wire를 연결해 로봇별 여러 호출,
후속 inbox, `report`, 개별 자기 카메라 JPEG, PairTeam 연결을 검사했다.
5.3/5.4초 follower 결정 → 6.1초 leader 전달이라는 순서와 **수신 후 다른 claim의
실행기 수락**을 검증한 것은 아니다. `FixtureActor`의 선택도 받은 분배문을 이해해
주문을 바꾸는 모델이 아니다.

### v66 결정 기회와 종료

새 후보는 `zone-study-integration-v66-multiturn`이다. 원격 main/열린 PR 6개에서
RGB 최대 v63, integration 최대 v64를 확인했다. #240의 로컬 미push 작업에
`v65-pair-close`가 있어 v65를 건너뛰었다. 확인 SHA·blob·경로는
[번호 감사](../experiments/2026-09-27-zone-study-multiturn/remote-audit.json)에 있다.
v1/v2/v64 기록과 번들 JSON은 그대로 두며, #240의 v65 변경을 이 후보에 합치지 않았다.
동시 작업이므로 push/병합 전 번호와 소스의 재확인이 필요하다.
**#240 병합 후 main 반영하며 v66을 pair v5 기반 합성 버전으로 재검증**한다.
이 병합 충돌(P2)은 이번 수정 범위가 아니며, 현재 후보는 계속 pair v4다.

2026-09-28 검토 4 P1 수정의 정책은 `v64_tagged_event_inputs.v4`다.
`DecisionScheduler`는 사건 원인·자기 작업 가용 시각·예산만 설정하며, 메시지 전용
`_push`·`_on_call_start`·`_submit`·`_resume_deferred`와 대기 사전을 두지 않는다.

- **공통 사건 불변식:** 시작·자기 완료/실패·안전 사건·타이머·재시도는 v64와 같은
  queue 순서, outstanding 보류, 최소 시작 간격과 재시도 경로를 쓴다. `_deferred`는
  원인별 키를 사용해 메시지 사건이 공통 사건을 흡수하지 못한다. 같은 시각의 자기
  완료와 타이머가 v64에서 두 호출이면 여기서도 두 호출이다.
- **수신 사건:** 한 수신은 `EventInput(cause='message', tags=(수신 ID,))` 한 개다.
  자기 작업 중이면 `available_at=inf`(아직 알려지지 않은 자기 작업 경계), 경계 사건에서
  해당 시각으로 바꾼다. 이후의 대기·재개·재시도·정산은 `EventScheduler`가 처리한다.
  사건의 출처는 보존하고 같은 원인만 병합한다. 공통 snapshot이 수신 입력을 사용하면
  해당 사건을 소비하며, 그 snapshot이 0-send이면 **같은 사건**을 환불 경로에서 복원해
  최소 간격 뒤 재개한다. 새 메시지나 메시지 전용 재개 사건을 만들지 않는다.
  inbox 이력은 보존하며 이미 만든 snapshot에 미래 메시지를 넣지 않는다.
- **공통 호출 우선:** 같은 시각에는 모든 공통 시작을 먼저 처리하고 메시지 시작을
  뒤에 처리한다. 추가 호출 뒤 예측하지 못한 공통 사건이 와도 공통 시각을 지켜야 하므로
  공통/메시지의 outstanding·최소 간격 상태를 분리한다. `max_outstanding_per_actor=1`은
  각 경로에 적용한다. 이미 시작한 메시지 호출과 나중의 공통 호출은 겹칠 수 있다.
  메시지 호출은 기존 호출 뒤 최소 간격을 지키지만 공통 last-start를 변경하지 않는다.
- **재시도·타이머:** 공통 재시도는 v64 그대로다. 메시지 재시도는 기존 retry 구현을
  사용하면서 메시지 경로와 원인 ID·`retry_of`를 유지한다. 공통 호출은 보류된 메시지
  재시도도 소비할 수 있다. 메시지 추가 호출의 응답은 공통 re-ask 타이머를 예약하지 않는다.
- **no_comm 기준선:** 메시지 경로에 진입하지 않는다. idle `wait`는 기존
  `hold(10.0)`·`zone_study_action_map.v2_pair` 그대로이며, 자기 명령 이력의
  `duration_s: 10.0`, hold 종료 사건과 공통 타이머를 유지한다.
- 실제 전송 상한은 **30/로봇, 90/시행**이다. 진행 중 예약도 wire 진입을 막는 데
  포함하지만, 0-send 정산은 전액 환불한다. 증가만 하는 call ID serial을 사용하지 않는다.
  시행 상한은 `AttemptBudget`에 적용해 한 호출의 여러 HTTP 전송도 각각 센다.
  v64의 로봇별 논리 호출 상한 30과 HTTP 상한 30도 유지한다.
  수락 발화는 **2/로봇, 6/시행**이고 창은 갱신하지 않는다. 전송 ledger·HTTP/영속 예산과
  SIM 비용 정산은 두 경로가 공유한다. 예산 소진으로 전송이 중단되는 규칙은 유지한다.
  추가 호출도 같은 유한 예산을 소비하므로, 조건 간 스케줄 불변 검사는 동일한 외생 공통
  사건·공통 응답 비용과 예산이 충분한 구간에서 한다. 메시지가 바꾼 실제 행동·작업 종료
  시각이나 소진 이후까지 조건별 전체 실행 시간이 같다는 주장은 아니다.

### 종료 라벨과 종료 상태 (검토 7, 2026-09-28)

코디네이터 결정으로 `no_comm`의 동결 v64 호환을 우선한다.
**end_reason은 v64 호환 라벨이며 과거 거절 이력 기반, 실제 종료 상태는 end_state로 판단한다.**
통합층은 한 번이라도 결정 입장이 예산으로 거절됐으면 `budget_exhausted`, 아니면
`sim_horizon`을 기록한다. 현재 잔여 예산이나 작업 완료를 이 라벨로 추정하지 않는다.
평가 전용 referee가 `orders_complete`로 판정하는 기존 별도 경로는 유지한다.

네 조건 모두 `TrialResult`, 저장 `trial_record.json`, `result.json`의 study 요약과 CLI 출력에
`end_state`를 기록한다. 정산 후 작업 보유 로봇 수, 미완료/censored 호출 수, 확정 HTTP
send 수, 예약 수, 팀/로봇별 HTTP·논리 호출 잔여량, 설정 horizon 도달 여부를 포함한다.
`quiescent`는 확정 예산 소진 상태에서 작업과 미완료 호출이 모두 없는지를 뜻한다.
censored 호출은 shutdown 뒤에도 미완료 결정으로 센다. 잔여량은 스케줄러 장부 기준이며
영속 pilot/upstream provider의 별도 예산·과금 잔액이 아니다. 이 사후 기록을 모델 입력이나
제어/단계 전환에 사용하지 않는다.

예를 들어 HTTP 3회 뒤 작업 3개가 남은 8초 종료와 무작업 8초 종료는 `no_comm`에서
모두 `sim_horizon`이지만, `pending_work_count`는 3과 0, `quiescent`는 false와 true다.
90초 동안 거절을 기록한 뒤에는 작업이 남아도 라벨은 `budget_exhausted`다.
[검토 7 결정·비교 필드 감사·검증 기록](../experiments/2026-09-27-zone-study-multiturn/review7-fix.md)을 따른다.

### SIM 비용과 기록

기본 정상/invalid 시도 비용은 `1 + 0.0002×입력토큰 + 0.02×출력토큰 + 0.3×생성발화수`
초다. error의 기본항은 0.5초, timeout은 20초이며 시도별 비용을 합한 뒤 0.1초 단위로
올림한다. 입력은 기존 고정 토큰 규칙, 실제 adapter의 출력은 응답 원문 tokenizer다.
모델 wall 지연을 SIM 비용으로 대체하지 않는다. 행동·발화 해제는 `시작 + 비용`,
메시지 inbox 도착은 `해제 + 0.1초`다. 동시 호출 비용은 서로 겹치며 로봇별 합산 비용을
에피소드 경과 시간이라고 부르지 않는다. 파라미터는 잠정 모델이며 실측 속도 보정이 아니다.

`study/decision_events.jsonl`에 작업 보류·호출 시작·시행/파일럿 예산 거절과 트리거를
기록한다. 시작에는 `cause=common|message`, 실제 수신 `message_ids`, `retry_of`가 있어
공통 호출과 메시지에서 유래한 추가 호출·재시도를 구분한다. `scheduler_events.jsonl`, `inputs.jsonl`의 inbox ID, `dispatch.jsonl`, 기존
call/message cost 기록을 call ID로 연결하면 **수신 → 경계 → 결정 시작 → 비용 해제 →
새 claim 수락** 순서를 복원할 수 있다. 모델 adapter의 `wire_requests`는 독립 대사 전
`null`로 기록한다(쓰지 않은 fixture wire의 0을 실제 전송 0으로 표시하던 진단 오류 수정).
send ledger 수와 제공자 upstream 시도/과금 대조는 계속 구분한다.

가짜 전송 회귀는 4조건의 첫 결정 5.3/5.4/6.0초와 전달 6.1초를 고정한다. busy follower는
8.0초 합성 자기 작업 경계 뒤 재호출하고 13.3/13.4초 새 주문이 수락된다. idle follower는
6.1초에 시작한다(첫 행동 `continue`, 자기 job 없음). 첫 행동이 명시적 `wait`이면 r1은
15.3초 hold 종료 뒤 재결정한다. 작업 경계가 없을 때도 r1은 네 조건 모두 65.3초 timer에서
결정하고 보류 메시지를 읽는다. `no_comm`에는 메시지·inbox·report가 없다.

v64 기준 SHA `97f91cb040bf382973ce84b24b1ca8399e64a6fb`의 scheduler·offline·integration
원본은 `tests/fixtures/zone_study_multiturn/v64/`에 해시와 함께 고정했다. 시드 300개의
공통 사건·동시각·오류·timeout·재시도 사건열로 no_comm의 전체 호출 기록·입력 해시·실제
요청 해시·dispatch 바이트·censored 기록을 대조한다. 같은 사건열의 통신 3조건에서는
공통 호출 시각·횟수·순서·재시도 계보와 추가 호출의 실제 메시지 원인을 검사한다.

두 반례의 v64 기준 r1 호출은 다음과 같다.

- 6.0초 오류 종료·메시지 전달·타이머: `[0, 5.5, 7.5, 12.8]`. 재검토 당시 no_comm의
  3회 역시 잘못된 공통 병합이었다. 7.5초는 계보가 있는 재시도, 12.8초는 공통 타이머다.
- 65.3초 자기 작업 종료·타이머: `[0, 65.3, 70.6]`. 두 공통 사건을 유지한다.

**응답과 작업 경계는 fixture이며 모델 이해·통신 효과·배송 성공의 증거가 아니다.**
재검토 수정·검증 범위는 [PR #245 재검토 수정 기록](zone_study_pr245_review2.md)을 따른다.
[이전 수정 기록](zone_study_pr245_review1.md)과
[초기 작업 기록](../experiments/2026-09-27-zone-study-multiturn/README.md)은 당시 기록으로 보존한다.

### 실제 LLM 파일럿 계획 — 이번 작업에서는 명령만 기록

2026-09-27 23:27 KST에 기존 `zone-study-adapter-pilot-r10/budget.sqlite`를 `mode=ro`로
읽었다. 17 send 중 정상 16건 정산 후 **18 attempts / 409,793 tokens 차감**, 잔여는
**582 attempts / 4,590,207 tokens**다. 600/5M 상한·실패 1건의 전액 예약은 유지된다.
실제 provider total 185,007과 차감량은 다른 수치다. [DB 해시와 상태](../experiments/2026-09-27-zone-study-multiturn/budget-readonly.json)를
보존했다. 이후 다른 작업의 사용량을 포함해 실행 직전에 다시 확인한다.

현재 DB identity의 `source_root`는 `/Users/changmin/projects/ugrp-wt/kiro-study-core`,
`pipeline`은 `AdapterTrial`이다. 기존 migration은 root/pipeline 변경을 허용하지 않는다.
아래 명령은 기존 어댑터의 소스 검토·preflight 단계에 한정하며, 현재 작업 경로에서 그대로
실행하거나 DB identity를 임의 수정하면 안 된다. 다회 driver 연결 시 이 호환성도 검토한다.

소스를 검토·커밋하고 동결한 뒤 기존 같은 DB에 소스를 이관하고 전체 대사와 새 4조건
preflight를 수행한다. 새 예산 생성, 자동 정산, 설치 프록시 수정은 하지 않는다.
요청/실효 설정은 현재 DB 계약(`REQUESTED`/`EFFECTIVE`, temperature 0.0)을 따른다.
초기 #222의 temperature 0.2 제안으로 기존 예약 계약을 바꾸지 않는다.

```sh
PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PILOT_ROOT=/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10
# 아래 명령은 이 작업에서 실행하지 않는다. 모든 출력 이름은 미사용 경로여야 한다.
# 기존 DB의 source_root에서 검토된 소스를 준비한 뒤 수행하는 어댑터 점검 명령이다.
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/multiturn-budget-review-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --migrate-source \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/multiturn-source-migration-01" \
  --migration-reason '#223 reviewed multiturn integration source' \
  --from-identity-sha256 "$REVIEWED_IDENTITY_SHA" --expected-state-sha256 "$REVIEWED_STATE_SHA"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.build_proxy_log_telemetry \
  --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-log "$REVIEWED_PROXY_LOG" \
  --log-timezone Asia/Seoul --output "$PILOT_ROOT/multiturn-telemetry-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" \
  --upstream-telemetry "$PILOT_ROOT/multiturn-telemetry-01/telemetry.jsonl" \
  --output "$PILOT_ROOT/multiturn-reconcile-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.sim_cli workflow run zone-study-pilot -- \
  --execute --stage preflight --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-pid "$PROXY_PID" \
  --proxy-log "$REVIEWED_PROXY_LOG" --acknowledge-upstream-finish-limitation \
  --upstream-telemetry "$PILOT_ROOT/multiturn-telemetry-01/telemetry.jsonl" \
  --output "$PILOT_ROOT/multiturn-preflight-01"
```

위 preflight는 **기존 첫 호출 어댑터 점검**이다. 현재 `run_zone_study_pilot --stage cohort`도
`trigger_on_message=False`여서 v66 다회 검증 명령으로 쓸 수 없다. 통합 CLI는 여전히
fixture 전용이다. 실제 다회 코호트는 기존 `ModelAdapter` + `run_trial(..., model_adapter=...)`
연결점에 preflight/대사/영속 예산 driver를 연결한 뒤 별도 실행 명령을 고정해야 한다.
이 작업에서는 실제 호출 진입점을 새로 열지 않았다. 로봇별 다른 실제 자기 RGB 입력,
3회/로봇·9회/조건(4조건 최대 36 proxy POST, 재시도 포함 별도 상한), seed 11,
SIM 120초를 초기 계획으로 하고, 같은 DB의 요청별 예약 가능량을 우선한다.
통합 물리 경로를 선택한다면 별도 물리 승인·잠금과 고정 source/bundle이 필요하다.
새 모델/물리 결과가 생긴 뒤에만 기존 TensorBoard 절차로 새 snapshot을 등록한다.

---

아래는 v64까지의 통합 배경이다. 현재 결정 정책은 위 v66 절이 대체한다.

2026-09-27, PR #229의 #194 + #235 통합. `tags_temporary`는 **임시, 표식 사용, 연구 결과 아님**이다. 이 변경은 비물리 테스트로 검증하며 새 물리 성공이나 실제 LLM 코호트를 뜻하지 않는다.

## 결정과 공동 운반

`IntegratedTrial`은 #194의 입력 계약·한국어 프롬프트·메시지 bus·SIM 비용·재질문 스케줄러를 재사용한다. `claim`의 주문이 단독이면 `deliver`, 2인 `long_beam`이면 `pair_carry(order_id, zone, partner_id)`를 호출한다. `HostRobotLink.call`은 #235의 `OwnCamTeamHost.call`을 사용하므로 PairTeam의 독립 제출·짝 매칭·취소·예약 명령 정리가 실제 적용된다. 한 로봇의 claim으로 상대 작업을 자동 시작하지 않는다.

현재 #235가 지원하는 짝은 **r1=end_neg, r2=end_pos**다. 다른 역할·r3 짝·heavy_crate·3인 주문은 거절하며 단독 배송으로 바꾸지 않는다. 이 고정 역할 제한은 네 조건에 동일하다. 일반 역할 할당 연구로 확대하려면 실행기 지원 범위를 먼저 넓혀야 한다.

`zone_pair_status_v4`가 유일한 짝 상태 채널이다. `PairStatusBus`는 실제 `PairTeam.records()`의 감사 기록만 반환하며 별도의 사용되지 않는 채널을 만들지 않는다. 상태 enum과 촬영 시각·프레임 ID·유효시한만 짝 동기화에 사용한다. 모델 입력·연구 스케줄러에는 짝 상태를 넣지 않고, GT·접촉·측정 관절·동료 작업 종료로 깨우지 않는다. 모델 사고 중에는 진행 중인 자기 작업을 계속하고, 유휴 로봇만 대기한다.

`configs/zone_study_integration/i2_pair_long_beam.json`과 `pair_dev_DRAFT.json`은 2대 빔 주문의 실행 설정이다. coarse sheet는 실행 전에 고정하며 runtime 좌표에서 재생성하지 않는다. #235의 표준 `TaggedCargoZoneScene` 준비 함수를 재사용한다. 이 draft는 실행되지 않았고 source/bundle pin과 실행 예산 확정이 남아 있다. 기존 `prereg.json`과 과거 결과는 보존했다. 앞선 `zone-study-integration-v2-pair-delay`의 기록은 그대로 보존한다. 현재 후보는 `zone-study-integration-v65-pair-close`(workflow `2.0.0`)다. STATUS v5의 close READY/GO와 `zone_pair_executor_v6_dev`를 묶는다. v64의 소스·기록과 기존 사전등록은 그대로 보존하며 과거 실행의 성공을 승계하지 않는다.

## 실행 소스 고정 (PR #229 P1 수정)

번들의 `runtime_files_sha256`은 러너·지원 모델 transport의 전이 import closure에서 만든다. 함수 안의 import, 상대 import, package initializer도 읽으며 모듈을 실행하지 않는다. `student.skill_module`과 provider `factory`의 설정 선택 모듈도 시작점에 포함한다. provider 등록 파일·추가 source_files·실제 보정·지도·시나리오 해시는 함께 고정한다. `visual_arm.py`, `llm_completion.py`, `session_scenes.py`를 포함한 의존 소스 변경은 번들 해시를 바꾼다.

비-dev 실행은 물리 모듈 import·host 생성·출력 디렉터리 생성 전에 `prereg.source_sha` 또는 `--expected-source-sha`를 Git commit으로 해석하여 HEAD와 대조한다. 둘 다 있으면 모두 일치해야 한다. 누락·미해결/다른 SHA·dirty 실행 소스·번들 불일치를 거절한다. dev는 미등록 배선 진단을 허용하지만 명시한 SHA는 dev에서도 검사한다. `--bundle`은 실행 없이 현재 후보의 해시를 출력한다. 이번 작업은 미커밋이므로 DRAFT의 source/bundle pin을 확정하지 않는다.

번호는 로컬 branch/remote refs 259개에서 공통 RGB 최대 v63·통합 최대 v2를 확인해 v64를 선택했다. fetch/PR 목록 갱신은 sandbox·네트워크 제한으로 실패했으므로 원격의 최신 번호 예약 확인은 별도다. [수정·검증 기록](../experiments/2026-09-27-pr229-source-delay/README.md)에 확인 범위와 번들 후보를 보존한다.

## 실제 M2와 지연 provider의 비물리 회귀 (P2 수정)

`tests/test_zone_study_pair_delay.py`는 실제 `PairTeam`·`M2DoorStudent`·`GuardedPairApproach`·`DelayedPoseSource`·태그 검출기/PF를 가짜 물리 시계에서 연결한다. 저장된 r1/r2 자기 RGB 18장과 발행 서보 명령만 사용하며, 평가 좌표는 fixture에 넣지 않는다. 입장 시 추정과 gate도 영상에서 만든다. 열린 checkpoint부터 M2가 PF를 교체하고 재관측·파지 영상 판정·readiness·동시 GO를 수행하는 구간을 검증한다. 추정·guard·readiness를 stub으로 바꾸지 않는다.

앞선 팔 안정화 대기가 6초 남은 r1 fixture에서는 두 로봇이 새 추정과 유효 readiness를 얻고 같은 시각에 `lift_go_1`을 발행한다. 대기 차가 없는 재생에서는 먼저 준비된 r1의 자세 불확실성이 상대 대기 중 커져 중단하며, 과거 readiness로 GO하지 않는 것도 검사한다. 두 경우 모두 PF 교체 후 0.16초 이전 추정 공개 차단을 확인한다. 이는 저장 영상의 시간·인터페이스 회귀이며 실제 접근·운반·물리 성공이나 네 조건 연구 비교가 아니다.

## 자기 손목 프레임과 다회 모델 호출

각 `HostRobotLink`는 자기 포트의 `robot_cam`만 받는다. robot ID·camera·JPEG SHA-256을 검사하고 호출 시작 시점까지의 최신 자기 프레임을 snapshot한다. `build_inputs`는 이 JPEG를 `CURRENT OWN WRIST RGB`로 실어 #194의 `ModelCallTransport`와 **실제 GeminiProxyCompleter**에 보낸다. 통합 경로는 `FrameLibrary`를 읽을 수 없다. 요청 이미지 원문과 해시는 `study/request_images/`, 요청·호출·입력 기록은 `study/`에, 실행기의 전체 촬영 원본은 `own_frames/<robot>/`에 보존한다.

CLI 기본은 fixture다. 실제 모델을 붙이는 프로그램 연결점은 `ModelAdapter(client_factory, send_ledger)`와 `run_trial(..., model_adapter=...)`다. `gemini_client_factory(..., study_json=True)`와 #194의 **기존 persistent budget을 소유한 PilotSendLedger**를 시행마다 만든다. 일반 live SendLedger는 transport가 거부한다. 새 예산이나 네트워크 우회 경로를 만들지 않는다. 모델·설정 해시는 bundle/provenance에 기록하고, 실제 adapter의 출력 SIM 비용은 응답 텍스트 토큰 수로 계산한다. 이 작업에서 실제 모델을 호출하지 않았다.

통신 3조건은 실제 전달된 메시지에 의한 `report` 호출과 inbox를 사용한다. `no_comm`에는 수신/송신이 없으며 자기 작업 사건과 자기 idle/busy 타이머로 반복 결정한다. 늦게 도착한 리더 메시지가 첫 결정 뒤의 재결정에 들어가는지 네 조건을 검사한다.

## 연구 전체 접촉 프로필

#190의 `s1`–`s6` 설정은 모두 `cargo_noslip_v1`, weld OFF다. 과거 실험 JSON은 덮어쓰지 않았다. 통합 러너는 시나리오·episode 중 어느 쪽이든 이 프로필과 다르면 시작 전에 거절한다.

bundle의 `contact_profile_expected`는 base + cargo XML 변환으로 계산한 `noslip_iterations=10`, `timestep_s=0.00025`와 프로필/소스 해시를 담는다. 물리 host 생성 뒤 실제 적용값과 대조한다. **manifest의 `applied_contact_profile`은 host의 실제 model option에서 읽은 기록**이며 예상값을 복사하지 않는다. host 생성 전 실패하면 null이다. XML 검사와 실제 접촉/운반 검증은 별개다.

## tags_temporary와 #237 교체 연결점

현재 registry의 선택 항목은 `tags_temporary`뿐이다. 모든 pose provider를 `DelayedPoseSource`로 감싸며 **촬영 SIM 시각 + 0.16 s** 이전에는 새 추정을 `report()`와 `loc.estimate()/predict_to()` 어느 쪽에도 공개하지 않는다. 입력 순서를 보존하려고 자기 명령·motion profile·프레임을 같은 지연된 필터 시계에서 재생한다. 추정 시각은 지연된 시각 그대로이며 현재 시각으로 위장하지 않는다. 로봇의 실제 명령 실행이나 LLM의 원시 JPEG 전달을 0.16 s 늦추는 정책은 아니다. provider 추론 wall 시간은 `robots/<id>/inputs/pose_timing.jsonl`에 따로 기록하고 SIM 지연 값으로 쓰지 않는다.

#237 `vision_zero_tag_v1` 교체 전 필요한 조건:

- registry의 factory를 `harness.vision_pose_source:VisionPoseSource`로 등록하고 소스·worker 설정·모델·실제 보정 해시를 고정한다. runner는 student에게 실제 전달한 보정을 provider 기록에도 사용한다.
- `zone_wide_door_walls_v3_notags`와 태그 없는 표준 Scene 연결을 추가한다. 현재 tags 장면 검사를 우회하거나 태그 지도로 비전 성능을 보고하지 않는다.
- 사전 등록 episode의 `pose_priors[robot_id]`에 **자기 출발 도크**의 mean/std/source를 넣는다. `StudyTeamHost`는 provider가 `init_prior`를 지원할 때 이를 호출하고 누락을 거부한다. runtime GT로 초기화하지 않는다.
- `StudyTeamHost.close()`는 각 provider의 `close()`를 호출해 worker를 정리한다. worker 실패 때 report와 loc 양쪽의 fail-closed 동작, 고정 지연, 명령 시간 정렬을 재검증한다.
- #235의 M2 재위치 추정은 태그 PF를 교체하는 경로가 있다. 현재 adapter는 이때도 지연 인터페이스를 유지하고 reset 전 대기 관측을 버린다. 비전 provider에서는 이 교체를 거절하므로, 교체 전에 태그 필터 생성 없이 비전 필터를 재초기화하는 명시적 adapter가 필요하다.
- VIS3 게이트 FAIL과 폐루프 dev 한계를 유지한다. provider 교체는 이 변경에서 하지 않는다.

## 검증과 남은 실행

`tests/test_zone_study_integration_pair.py`는 가짜 물리 시계·응답 wire만 대체하고 실제 연구 scheduler, 입력 builder, Gemini adapter, host API, PairTeam, 짝 상태 채널을 실행한다. 모델 호출과 물리 step은 없다. 기본 통합/격리·실행기/짝 회귀도 함께 검사한다.

남은 물리 검증은 고정 소스·예산·잠금 아래 새 draft의 4조건 전체 실행, 실제 자기 프레임 감사, 0.16 s 지연에서의 위치 불확실도와 짝 readiness/heartbeat, 파지·문 통과·방출·abort·거짓 확인, 실제 적용 프로필과 weld OFF 확인이다. 실제 LLM 파일럿과 태그 0개 provider 검증도 별도다. 물리/모델 결과가 생기면 기존 지침에 따라 새 TensorBoard snapshot으로 전달한다.

## 근거

- [참고 자료](references.md): cargo profile과 재사용 모듈의 출처.
- [이슈 #222](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222), [#223 fixture/다회 결정 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/223#issuecomment-5852769695).
- [#216 고정 인식 지연 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5852229650), [#237 provider 계약과 미완료 게이트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/237).
