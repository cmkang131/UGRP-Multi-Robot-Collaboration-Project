# S2 현실성 재검증 — 실행 전 등록 (2026-10-06)

**최종 결과:** 실행 SHA `ab27cffd8f70cfbf51ccbb0dbf5b4ced286c91f7`,
`zone-s2-realism-v114` / workflow `7.7.0`의 새 probe s1039는 집기 전
`CYAN_ALIGN_VIEW_LOST`로 실패했다. full s1029–1031은 probe 조건 미충족으로 미실행이다.
최신 지시를 반영한 v113/v114의 probe 통과 조건과 정체 감시가 아래 초기 등록보다 우선한다.
실행 이력·옛 등록은 보존하며, [최종 결과](#v114-완료-기록)를 별도로 기록한다.

## 후보·입력 경계

- origin/main `b07f33aba278fda7434acaed0974c3d38f7b9ef0` 위에 #401
  `ecd2f55d48f6380cc4e7fbd3573e94c538f96044`, #402
  `e7b229b6d9809ddf18f345dd179d60d499fce3dd`를 순서대로 merge했다(rebase 없음).
  두 merge까지 통합 SHA `56e46a35`이며, 아래 새 어댑터·사전 등록 커밋의 전체 SHA를 실행 때 고정한다.
- 메인 세션 결정으로 기존 `ugrp-wt/drive-friction`의 깨끗한 worktree를 재사용한다.
  새 worktree·상한 예외 없음. #402의 원래 브랜치/원격 SHA는 유지한다.
- 새 번들 **zone-s2-realism-v109**, workflow **7.2.0**.
  main+열린 PR 12개 조회의 최댓값 v108/7.1.0 다음 번호. [조회 원본](reservation-scan.json).
- 카메라 `masterpi-camera-user-observation-target-review-v3`, native 바퀴 구동
  `masterpi_drive_friction_v7`(출발 32.5/100, 운동 8.3333/100),
  `setdown_relook=off`, `grasp_check=pickup_site_v1`을 번들과 CLI에 명시한다.
- 기존 v106 Runtime과 #401의 자기 RGB 파지 확인을 재사용한다. 기존 파일/번들 불변.
  renderer에는 v3 위치/회전, 시각 provider에는 같은 강체변환 광선을 연결하고 실제 적용값을 검사한다.
  #402의 HysteresisWorld가 바퀴 토크만 발행한다. 차체 wrench 경로는 호출하지 않는다.
  `v98-exact-v6`의 PF/영상/일정 메모만 활성 경로에 쓰이며, legacy build_world에 연결된
  drive-kernel hook은 새 v7 factory에서 호출하지 않는다. speedups sidecar로 확인한다.
- r3, 정적 최종 v3 wide-door 지도, 단독 cyan 1개, destination B/door_1,
  cargo_noslip_v1, weld OFF, floor_light_v1+기존 nearclip/정수 clock을 유지한다.
  모델 호출 0. 제어기 입력은 자기 RGB·정적 지도·자기 명령 이력만이다.
- 기존 v102/solo-s911 명령 기반 위치 예측값은 **v7 보정값이 아니다**. 재보정/명령 증폭 없이
  현재 후보를 실행한다. 기존 CameraRobotPort의 forward≤.15/left≤.10/turn≤.15와
  v7 출발 문턱 .325의 부조화 가능성을 실행 전에 확인했다. 관측된 정체/실패도 결과다.
- fae1fc4a의 s1022–1027 및 중단 s1028은 폐기된 옛 조건이며 이번 결과와 합산하지 않는다.
  이번 표본도 DEV이며 연구 확증·실물 성공·정식 stop-ON 졸업으로 승격하지 않는다.

## seed·실행 순서 — 결과 열람 전에 커밋

[기계 판독 등록](registration.json). probe의 seed는 전체 경로와도 겹치지 않는다.
전체 경로는 기존 졸업 계획 첫 세 full-run slot 순서(P1-1/P2-1/P1-2)를 그대로 쓴다.

|순서|seed|slot|stage|용도|
|---:|---:|---|---|---|
|1|1032|P1-2|pick|집기→원래 자리 확인→HIGH 복귀 probe|
|2|1029|P1-1|place|전체 경로|
|3|1030|P2-1|place|전체 경로|
|4|1031|P1-2|place|전체 경로|

한 실행 최대 900 SIM초(+초기 reset≤5초), 10800 wall초. 실행 사이 튜닝·반복·seed 교체 없음.
각 실행은 ugrp_session → launch_dev.zsh → exclusive agent_lock → sim_cli workflow 경로다.
한 번에 하나, nice 0/NO_BG_NICE. 종료 때 자기 lock과 자식만 정리한다.
정체 watchdog으로 DEV를 일찍 중단하지 않는다. 공간 <10 GiB/ENOSPC는 HOST_ERROR로 보존한다.
실행 전 여유 54.74 GiB. raw는 primary `outputs/s2-realism-<source8>-s<seed>-<slot>-<stage>`;
기존 raw 보존, 이번 raw도 작업/열린 PR 동안 전부 보존하며 삭제하지 않는다.

## 판정·중단

- probe는 최초 HIGH 이벤트만으로 끝내지 않는다. 원래 자리 비교를 기록하고 HIGH로 복귀한
  controller carry 상태까지 확인한다. 영상 미확인은 dev_light의 would-stop으로 남긴다.
  실제 lifted(중심 z>.06 m)와 마지막 유지 여부는 별도 eval_only로 대조한다.
- full은 기존 사후 기하 심판: lifted 이력, 마지막 2초 전체 상자 B 내부(inside), 바닥·안정.
  미도달/누락은 실패/미확인으로 보존한다. 전후 cyan 면적·판정·다시 집기 횟수·SIM/wall을 기록한다.
- 보수적 가드/σ/재관측/위치 불확실 정지는 기존 dev_light에서 기록만 한다.
  별도 물리 감독은 로봇 tilt≥10° 즉시, 한 번 z>.06 m로 들린 뒤 양 손가락 접촉 중
  하나 이상이 .3초 사라지면 GRIP_LOSS, 이 상태에서 바닥 여유≤5 mm면 LOAD_DROP으로 종료한다.
  정상 최종 lowering/release와 시각 재집기의 계획된 lowering/open은 접촉 예외다.
  이 감독은 20 Hz이며 매 물리 substep의 완전한 감시가 아니다. 접촉 force/좌표를 제어기에
  반환하거나 주행·재집기를 보정하지 않고 실행 전체를 중단하는 데만 쓴다.
  robot tilt 10°/.3초와 5mm는 기존 DEV 감독을 참조한 기준이며 실물 한계가 아니다.
- 실행 오류도 종료한다. **probe 포함 같은 원인이 두 실행에서 발생하면 남은 seed를 중단**한다.
  controller timeout/error와 물리 실패는 서로 다른 분류다. 동일 would-stop tick은 실패 실행 수가 아니다.
  probe가 실패해도 반복 원인이 2회가 되기 전에는 등록한 full을 진단 목적으로 실행하고 성공을 승계하지 않는다.
- 원본 결과→요약→TensorBoard 이벤트/live API 수치를 대조한다(사용자 요청에 따라 브라우저 생략).
  새 snapshot, 4배속 own RGB mp4 1개, 로컬 raw 해시·DRAFT PR을 남기고 **병합하지 않는다**.

## 실행 전 검증과 참고 자료

카메라 변경 시험 25개 통과 후 첫 merge commit, 구동 v7 시험 4개 통과 후 두 번째 merge commit.
새 통합 시험 5개: 등록/소스 closure, 표준 장면의 v3+v7 동시 XML compile(물리 step 없음),
probe 조기 종료 방지, 물리 감독/정상 방출 경계, GT 비전달·실패 결과 보존을 검증했다.
기존 305개 runtime closure 바이트 보존 여부도 기록한다. 전체 검사는 GitHub CI에 맡긴다.

- [BehaviorTree.CPP 공식 sequence](https://www.behaviortree.dev/docs/learn-the-basics/BT_basics/)
  및 [ROS2 action server 공개 코드](https://raw.githubusercontent.com/ros2/examples/rolling/rclpy/actions/minimal_action_server/examples_rclpy_minimal_action_server/server.py):
  본문/코드 확인. 진행 이벤트와 마지막 완료를 구분하여 probe가 비교 이전 HIGH에서 끝나는 것을 막는다.
- [MuJoCo 공식 contact API](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-contactforce):
  본문 확인. 접촉 자료는 평가/외부 중단에만 사용. 기존 `probe_drive_pair_beam.StopGuard`의
  물리 중단 분리 방식과 10°/.3초/5mm를 재사용하되 30g cyan에 beam의 .5N force 문턱을 적용하지 않는다.
- [Agia 외, CoRL/PMLR 2025 Sentinel](https://proceedings.mlr.press/v270/agia25a.html):
  초록 확인. 실행 진행과 실패 감시 분리 참고, 저자 코드/실험 재현 미확인. 모델 감시기는 도입하지 않는다.
- 파지 영상 ECC·Karnopp/Schmitt 입력 이력의 출처/한계는 통합한 #401/#402 README를 그대로 보존한다.


## 초기화 실패와 v110 후속 등록 (작업 명령/영상 생성 전)

`45fbf96a`/v109 s1032는 `v3 camera not applied` HOST_ERROR다. 새 XML은 v3였으나
`MultiMasterPiProductionV2._bind_controller → _configure_measured_robot_camera`가 옛 mount를
덮어썼다. XML compile 시험만으로 런타임 적용을 증명하지 못했으며 실제 적용 검사가 이를 차단했다.
컨트롤러 초기화 이전 생성자의 내부 settle만 가능했고, 작업 reset/명령/영상/심판 행은 모두 0이다.
raw와 기존 번들·소스·등록을 바이트 그대로 남긴다. 기록은 `outputs/s2-realism-45fbf96a-s1032-P1-2-pick`.

새 **v110 / workflow 7.3.0**은 부모 파일을 수정하지 않고 생성 후 각 controller의
`_sync_real_camera_mount`와 재configure 경로에 명시적 v3 pose를 묶는다. K/D·해상도·물리·명령·시각 알고리즘은
그대로다. 실제 기존 configure 함수를 이용한 회귀 시험으로 덮어쓰기 반례와 재호출 보존을 확인한다.
MuJoCo 공식 camera/model-change API의 런타임 model 갱신과 `mj_forward`를 따르는 최소 연결 수정이다.
문서/코드 확인: [MuJoCo camera](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-camera),
[model changes](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#model-changes).

[새 사전 등록](registration-v110.json): 미사용 probe **1033/P1-2** → 기존 미사용 full
**1029/P1-1, 1030/P2-1, 1031/P1-2**. s1032는 재사용하지 않는다. 최대 횟수·중단·평가 기준은 동일하다.
초기화 오류 후보와 이번 후보의 원인을 섞지 않으며, 첫 후보를 probe 성공/실패 물리 표본으로 세지 않는다.
새 후보도 두 동일 원인 실행 뒤 멈춘다. 새 source SHA를 커밋/push한 뒤 고정한다.

호스트 시작 기록: Codex shell nice=10 상속은 launcher가 거부했다. launchd 기본 nice=0를 사용하며
프로세스 우선순위 변경은 하지 않는다. 첫 launchctl submit은 실패 재시작 기능이 있어 제거했고,
재시작은 기존 출력 보호에서 차단됐다. 이후는 **KeepAlive=false**, RunAtLoad만 있는 수동 일회성 job으로
ugrp_session을 호출한다. 주기/예약/복구 작업은 남기지 않고 끝나면 자기 job을 unload한다.


## s1033 운영 중단과 명령 출력 수정 (2026-10-06 후속 지시)

메인 세션이 v110/s1033을 중단했다. [사후 평가](s1033-abort-assessment.json):
785.4 SIM초, 최대 바퀴 입력 .178559·표본별 최대 입력 중앙값 .109594,
relay 활성 0개, 이동 최대/끝점 5.961 mm, 마지막 `search_move`다.
원인은 **COMMAND_BELOW_START_THRESHOLD / CONTROL_FAILURE**, HOST 오류가 아니다.
raw 결과·프레임은 그대로다. 외부 종료로 final result/student record가 없으며,
기존 driver의 `NO_RESULT:2`는 재시작 차단용 전송 상태이지 실제 실패 2회가 아니다.
s1033은 재사용하지 않는다. s1029–1031은 시작하지 않아 새 후보의 full seed로 유지한다.

### 실물 소스 조사와 최소 적용

- `scripts/masterpi_control.py:332–338,382–418`: 모터는 0 또는 절댓값 35 이상만 허용,
  일반 방향 35–40/옆 이동 35–70. 작은 mixed-wheel 출력을 개별 clamp한 코드는 아니다.
- `scripts/red_block/physical_state_machine_reference.py:268–282,1476–1484`: 35 속도의
  방향별 고정 패턴과 .10/.12초 짧은 회전. scalar 속도만 35–40으로 clamp한다.
- `scripts/red_block/primitive.py:25–58`: bounded pulse (.10–.80초), 옆 이동 65와 최소 .65초.
- `scripts/red_block/place.py:163–187`: 접근 때 35 최소 속도와 .10/.18/.42/.60초 구간을 사용.
- `docs/sim2real_measurement_protocol.md:28,375–381`: 실물 CLI의 35 문턱과 방향별 계측 절차.
- `docs/archive/`의 현재 3개 기록과 Git HEAD를 검색했다. 35 제한의 추가 실물 코드 근거는
  없었다. `validation_summary_20260917.md`는 교사 SIM 자료이며 실물 근거로 쓰지 않는다.
- `harness/real_odometry.py:1–6`: 실물에는 보정된 odometry가 없었다. 그 코드에서 검증된
  이동 계수를 가져왔다고 주장하지 않고, 아래 별도 v7 탐색 진단에서 비교·재추정한다.

`min_wheel_cmd=real_v1`은 위 최소 속도와 pulse 제한을 사용한다. v106의 연속 3축 요청을
실물 primitive에 연결하기 위한 최소 어댑터로, 절댓값이 가장 큰 요청 축을 한 번에 하나씩
선택한다(동률은 forward/left/turn 순서). simulator의 기존 논리 wheel basis를 사용하여
실물 보드 배선 부호를 잘못 복사하지 않는다. 실행 중 pulse 덮어쓰기를 막고, 종료 후 정지·
새 관측 구간 .10초를 둔다. 실제 발행한 명령을 자기 명령 이력/PF에 동일하게 전달한다.
기본 `off`는 기존 v106 Runtime/port 출력과 JSON bytes가 같다. 기존 원본 모듈은 수정하지 않는다.

`stagnation_watch=window120_v1`은 eval-only의 최근 120 SIM초 위치 envelope가 1 cm 미만이면
`STAGNATION_120S_LT_1CM`으로 실행 전체를 중단한다. 돌아왔다가 멈춘 동작을 정체로 잘못
세지 않도록 창 전체 위치 범위를 사용한다. 기본 off이며 pose/행동 보정·제어기 입력은 없다.
`dead_reckoning`도 기본 off이고, 새 계수 옵션은 진단 자료·해시를 고정한 뒤에만 등록한다.

### v111 탐색 사전 등록

새 `zone-s2-real-output-diag-v111` / workflow 7.4.0. main과 열린 PR 13개 중 최대
v110/7.3.0 다음 번호다. [번호 조회](reservation-scan-v111.json), [seed 조회](seed-reservation-v111.json),
[등록](registration-v111.json). 미사용 s1034 직진·s1035 회전·s1036 옆 이동 각 1회,
표준 Scene의 빈 구간에 setup-only 배치, search arm/빈 집게, v7 정상 접촉·weld OFF.
요청 .10초가 실제 출력단을 통과하여 .35/.10초, .35/.10초, .65/.65초가 된다.
이후 4초 coast를 기록한다. 기존 계수 예측 대비 축 오차 >25%, 평면 오차 >1cm 또는
각도 오차 >2도면 v7 재추정. GT는 이 탐색의 오프라인 계측/fit에만 쓰고 새 probe 제어에는
주지 않는다. s1037은 새 probe용으로 예약하며 실제 후보·계수·번들을 다시 커밋 후 실행한다.

CI 수집 오류는 [pytest 공식 missing-import 방식](https://docs.pytest.org/en/stable/how-to/skipping.html#skipping-on-a-missing-import-dependency)
및 기존 `tests/test_masterpi_drive_friction_v7.py`를 따랐다. MuJoCo가 필요한 개별 시험만
`importorskip`하고, 등록/순수 제어 시험은 오프라인 환경에서도 실행한다.

### v111 기록 오류와 v112 진단 재등록

`18c2495b`의 s1034는 첫 직진 뒤 NumPy bool JSON 직렬화에서 HOST_ERROR가 났다.
작업 종료 시 결과/궤적을 저장하던 첫 구현은 해당 자료를 남기지 못했다. raw/bundle/관리 로그는
그대로 보존하며 물리 계측 표본으로 쓰지 않는다. s1034는 재사용하지 않는다.
기본 Python bool과 NumPy scalar 차이는 [NumPy 공식 scalar 문서](https://numpy.org/doc/stable/reference/arrays.scalars.html),
JSON 변환은 [Python 공식 encoder default](https://docs.python.org/3/library/json.html#json.JSONEncoder.default)를 확인했다.
새 writer에서 scalar `.item()` 변환을 사용하고 궤적을 매 표본 즉시 flush한다.

새 `zone-s2-real-output-diag-v112`/workflow 7.5.0은 v111 소스를 수정하지 않는다.
새 미사용 직진 s1038, 아직 시작하지 않은 회전 s1035·옆 이동 s1036을 동일한 구동/판정으로
[다시 사전 등록](registration-v112.json)했다. s1037 새 probe 예약과 full 조건은 유지한다.

### v112 진단 결과와 v113 새 probe 사전 등록

진단 소스 `1b6b092188268738cc74417bec5e6d72e4b3136a`, [완료 결과/원본 해시](motion-diagnostic-results.json).
|seed/동작|기존 예측|실제 변화|판정|
|---|---:|---:|---|
|1038 직진|5.472 cm|1.664 cm|재추정 필요|
|1035 회전|2.748°|6.644°|재추정 필요|
|1036 옆 이동|46.517 cm|17.152 cm|재추정 필요|

[fit_motion.py](fit_motion.py)는 기존 `scripts/fit_loaded_gain_calibration.py`의 명령 기반 1차 응답·정지 지연과
SciPy bounded batch least-squares를 따른다. 3×3 gain, 축별 시동 지연, 공통 정지 지연을
기존 PF의 50ms 재귀식 그대로 맞췄다. `configs/s2_motion_v7_diag_v1.json`에 수치·원본 SHA를 고정했다.
같은 탐색 자료의 재생 최대 평면 오차 2.334 mm/각도 오차 .5523°, 끝점 오차는 .1mm/.05° 이하다.
이는 **training fit**이며 독립 검증이 아니다. 양의 짧은 무부하 pulse 각 1회뿐이고, 역방향·더 긴
pulse·적재 전달은 미검증이다. 새 실행의 적재도 이 고정 모델을 명시적 미검증 proxy로 쓴다.
GT 온라인 보정·자동 계수 갱신은 없다. 실제 PF unloaded/loaded 명령 예측에 새 축별 지연이
적용되고 기존 provider는 불변인 것을 포함해 새 옵션 시험 **9/9 통과**했다.

새 **zone-s2-realism-v113 / workflow7.6.0**은 camera v3/drive v7/setdown off/pickup_site_v1에
`min_wheel_cmd=real_v1`, `dead_reckoning=v7_diag_v1`, `stagnation_watch=window120_v1`을
명시적으로 켠다. 새 CLI·Runtime의 기본은 off이며, 등록 실행에서만 세 옵션을 명시한다.
이전 v109–v112 소스/번들/등록은 그대로 보존한다. [번호 확인](reservation-scan-v113.json),
[사전 등록](registration-v113.json), 새 미사용 **probe1037/P1-2**를 먼저 실행한다.
probe 통과는 집기→원래 자리 확인→HIGH 복귀, 실제 lifted 이력/마지막 z>.06m,
`confirmed_by_site_disappearance`를 모두 요구한다. 미통과면 full은 시작하지 않는다.
통과하면 아직 미사용인 **1029/P1-1 → 1030/P2-1 → 1031/P1-2**를 실행한다.
같은 원인 2회면 나머지를 중단한다. 미실행을 실패 실행 수로 만들지 않는다.
한 case 900 SIM초/10800 wall초 이내이며, 새 eval-only 120초/1cm 정체 감시가 먼저 중단할 수 있다.
코호트 동안 소스·계수·옵션을 고정한다. 이전 성공/정체/탐색 결과와 합산하지 않는다.

### v113 reset 연동 오류와 v114 새 probe 등록

`0c8eb624`/s1037은 10.7 SIM초 뒤 첫 .35 명령에서 HOST_ERROR다.
`sim/final_pair_highpose_clock.py:IntegerClock.reset`이 포트를 기본 CameraRobotPort로
다시 만들었다. 새 출력 포트의 직접 시험과 진단은 통과했으나 전체 reset lifecycle을
놓쳤다. 기존 코드의 reset 재생성 계약을 확인하여 그 뒤 명시 옵션 포트를 다시 붙인다.
실제 IntegerClock.reset 경로를 거치는 회귀 시험을 추가했다. 물리·pulse·계수는 바꾸지 않는다.

raw `/Users/changmin/projects/ugrp/outputs/s2-realism-0c8eb624-s1037-P1-2-pick`과 v113을 그대로 보존한다.
새 **v114 / workflow7.7.0**, 새 미사용 **s1039/P1-2 probe**를 [사전 등록](registration-v114.json)한다.
이전 s1037도 재사용하지 않는다. [번호/seed 조회](reservation-scan-v114.json).
통과 기준, full1029–1031 조건, 동일 원인2회/120초1cm 정체 중단, 모델·출력 옵션은 v113과 같다.

## v114 완료 기록

실행 소스는 `ab27cffd8f70cfbf51ccbb0dbf5b4ced286c91f7`으로 고정했다.
camera v3 / drive v7 / setdown_relook=off / grasp_check=pickup_site_v1,
min_wheel_cmd=real_v1 / dead_reckoning=v7_diag_v1 / stagnation_watch=window120_v1이다.
모든 추가 옵션의 기본값은 off다. 실제 reset 뒤 세 로봇 포트가 RealPrimitivePort/real_v1인
것을 `eval_only/output-option.json`에서 확인했다. 자기 명령 이동 모델은 위 탐색에서 고정한 값이며
probe를 이용한 재튜닝은 하지 않았다. [전체 완료 기록과 raw 해시 참조](completed-results.json).

|seed/slot|결과|lifted/inside|원래 자리 전후 cyan 면적|재집기|wall / SIM / wall·SIM⁻¹|
|---|---|---|---|---:|---|
|1039/P1-2 probe|CYAN_ALIGN_VIEW_LOST|false / false|미도달·미측정 / 미측정|0|386.514초 / 134.850초 / 2.8663|
|1029/P1-1 full|NOT_RUN: probe 미통과|미측정|미측정|미측정|미측정|
|1030/P2-1 full|NOT_RUN: probe 미통과|미측정|미측정|미측정|미측정|
|1031/P1-2 full|NOT_RUN: probe 미통과|미측정|미측정|미측정|미측정|

s1039 raw는 `/Users/changmin/projects/ugrp/outputs/s2-realism-ab27cffd-s1039-P1-2-pick`이다.
full 세 seed의 예정 경로는 완료 JSON에 남겼으나 실제 출력 디렉터리는 생성되지 않았다.
시작 reset 1.3초를 제외한 check SIM은 133.55초, 세션 관리 wall은 392.537초다.
명령 1,188개·모델 호출 0개. dev_light would-stop은 ARM_COLLISION_GUARD 5개,
POSE_UNCERTAIN 43개를 기록만 했다. 같은 원인 실패는 1회이며 미실행 3건을 실패 횟수에 넣지 않는다.
이번 probe의 분모는 1회(통과 0회)다. full 성공률·실물 성공·정식 졸업 판정은 없다.

### 실패 해석과 제한

s1033의 출발 문턱 미달은 **제어 출력 실패**로 유지한다. 새 s1039는 최대 바퀴 입력 .65,
운동 branch 표본 1,863개, 최종 평면 변위 1.730m로 실제 움직였다. 차체 직접 외력은 0이다.
검색 이후 정렬 단계에서 표적 영상을 잃었다. 기존 v106의 정렬 필수 시각 조건 실패이며
짐 낙하·기울기 한도 초과·HOST_ERROR로 분류하지 않는다.

[실패 구간 원본 참조](failure-window.json): 127.8 SIM초에 left=-.65 / .65초 pulse가 나갔고,
129.0초까지 차체는 17.299cm 이동했다. cyan은 같은 구간 사실상 정지했다(평면 변화 약 1.3e-12m).
127.75초 자기 영상의 full-frame cyan 면적 16,110px가 128.45초 이후 0px가 되었다.
이 수치는 **원래 자리 집기 전후 비교가 아니라 정렬 실패 구간 전체 영상 마스크**다.
집기/들기/원래 자리 확인은 도달하지 못했다. 옆 이동 직후 시야 상실이라는 시간적 근거는 있지만,
원인을 분리하는 ablation은 수행하지 않았다. 실물 primitive의 최소 옆 이동 pulse를 그대로 적용하는
것만으로 근접 정렬에 적합함을 입증하지 못했고, 양의 무부하 세 진단의 이동 모델 적합도도
역방향·적재·장거리 일반화를 입증하지 않는다. 새 seed 추가나 full 강행 없이 이 후보를 종료한다.

### 검증·전달·보존

- 최종 옵션/실제 reset lifecycle 시험 `tests/test_s2_realism_motor_options.py`: **10 passed**.
  default-off Runtime record/port 응답·wheel 출력의 byte 동등성, pulse/정체 감시 경계,
  고정 모델의 실제 PF 적용, reset 이후 포트 보존을 포함한다. 이후 변경은 완료 기록뿐이다.
- 저장된 20Hz 프레임 해시·원본 manifest·2612개 프레임 시각 간격을 대조했다.
  독립적인 상자 8꼭짓점/마지막 2초 심판은 raw lifted/inside/floor/stable/success와 일치했다.
  [검증된 raw manifest 참조](completed-results.json)는 대용량 원본 자체의 원격 백업이 아니다.
- [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-s2-realism-v114%2F#timeseries):
  새 snapshot `outputs/tensorboard/1006-s2-realism-v114`의 **8개 기록·98개 수치**를
  원본 → event → 기존 서버 live API로 대조했다. [전달 검사](delivery-verification.json).
  초기화/출력/기록 오류, 3개 탐색 진단, 최종 실패 probe는 각기 다른 run으로 유지한다.
  미실행 seed와 폐기된 fae1fc4a의 성공 결과는 변환·합산하지 않았다.
  공용 view에는 자기 `s2_realism_20261006` 키만 추가했고 기존 서버는 변경하지 않았다.
  HParams 열 존재와 pinned tag 수치를 검사했으며 브라우저는 사용자 지시대로 생략했다.
- 4배속 own-RGB MP4 1개:
  `/Users/changmin/projects/ugrp/outputs/s2-realism-ab27cffd-analysis/views/s1039-probe/execution.mp4`.
  32.65초 / 653 frames / 640×480 / 20fps, 734351 bytes;
  SHA-256 `4dd715f59db58128907f109abe47faea1e054e85e57f7318441a85c9719bd46c`.
  전체 디코딩과 첫/중간/마지막 프레임, TensorBoard manifest의 영상 등록을 확인했다.
  영상은 실제 130.6 SIM초 촬영분이며 reset/마지막 settle 전체를 담지 않는다.
- 자기 실행 세션·드라이버는 종료했고 agent_lock은 해제했다. 일회성 launchd job도 unload했다.
  raw 삭제·기존 snapshot 변경·다른 작업 프로세스 종료·모델 호출은 없었다.
  [PR #406](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/406)은
  **DRAFT 유지·미병합**이다. 최종 실행 SHA의 CI는 조회 시 24개 통과/8개 진행 중이며 전체 통과로 보고하지 않는다.


## s1039 오프라인 원인 분리와 v115 후속 사전 등록

사용자 후속 지시(2026-10-06)에 따라 저장된 프레임·명령·eval 궤적만 분석했다.
[분석 코드](analyze_alignment.py), [원본 해시와 펄스별 수치](s1039-alignment-cause.json).
물리 step/추가 렌더/제어 피드백 없이 BGR HSV mask와 기존 camera v3 광선을 사용했다.
정렬 허용 오차는 전후·좌우 각각 **±3mm**, 서로 다른 두 프레임 확인이다(변경 없음).

|펄스 시작 SIM초|명령(±1 눈금)/지속|실제 전후·좌우 이동 mm|yaw 변화 °|영상 중심 전→후 px|면적 전→후 px|
|---:|---|---|---:|---|---|
|124.80|forward +0.35 / 0.10s|+12.39, -0.21|+0.382|(321.3,363.4)→(321.1,120.6)|14171→10324|
|126.60|forward +0.35 / 0.10s|+11.38, +0.18|+0.024|(321.1,120.6)→(323.0,137.0)|10324→11115|
|126.80|forward +0.35 / 0.10s|+13.24, +0.70|+0.260|(323.0,137.0)→(329.7,159.9)|11115→12020|
|127.00|forward +0.35 / 0.10s|+12.81, +0.33|+0.125|(329.7,159.9)→(333.8,182.9)|12020→12965|
|127.20|forward +0.35 / 0.10s|+13.36, +0.15|-0.084|(333.8,182.9)→(334.9,208.1)|12965→14052|
|127.40|forward +0.35 / 0.10s|+13.57, -0.09|+0.027|(334.9,208.1)→(337.1,236.9)|14052→15104|
|127.60|forward +0.35 / 0.10s|+13.27, -0.48|-0.430|(337.1,236.9)→(332.0,265.7)|15104→16241|
|127.80|left -0.65 / 0.65s|+1.92, -172.98|+1.459|(332.0,265.7)→(없음)|16241→0|

이동은 각 명령 직전부터 다음 명령 직전까지(마지막만 종료+.55s)의 eval 채점 수치다.
구동 중간만의 이동도 JSON의 `powered_delta`에 따로 보존한다. 첫 행 이후에는 camera pose
변경이 포함돼 영상 y가 달라지므로 camera/차체 이동을 혼동하지 않는다.

- **(a) 주원인으로 지지:** 마지막 left=-.65/.65s는 좌우 172.976mm를 움직였다.
  ±3mm 허용량의 57.7배이며, 목표의 실제 좌우 위치가 -14.574→+152.070mm로 부호를 바꿨다.
  실제 바퀴 속도가 아니라 입력 눈금 .65다. 직진 .35/.10s도 한 번에 11.4–13.6mm였다.
- **(b) 이번 상실의 직접 원인에서 제외:** 마지막 펄스 전 bbox=(270,198)–(399,335),
  화면 아래 여유 144px. 128.40초에는 bbox=(21,237)–(31,281), cyan 240px이고,
  128.45초에 0px가 됐다. 즉 화면 왼쪽 유효 영역 밖으로 나갔다. 정렬 중 이미 122초 p45,
  125초 inspect로 시선을 낮춘 뒤였고, 마지막 구간의 발행 servo 값은 동일했다.
  +10° camera가 모든 근접 조건에서 충분하다는 뜻은 아니다. 원인이 (b)가 아니므로
  카메라 장착/FOV·손목 자세를 추가로 바꾸지 않는다.
- **(c) 주원인에서 제외:** 마지막 구간 yaw는 -2.097→-.638°(+1.459°).
  같은 카메라/상자 중심의 분석적 투영은 before x=329.7, actual after x=-82.9,
  yaw 고정·이동만 x=-97.4, 위치 고정·yaw만 x=348.0px이다. yaw만으로는 표적이 남고,
  관측된 yaw 변화는 오히려 왼쪽 이탈을 줄인다. 별도 진단의 -2.49°를 이 실행에 더하지 않았다.
  이는 고정된 발행 arm 외부표정에 대한 분석적 반사실이며 물리/렌더 ablation은 아니다.
- **(d):** 영상 검출은 상실 직전 중심 [249.353,-14.783]mm를 냈고 eval은
  [248.575,-14.574]mm였다. 이 프레임의 fit 오류가 173mm 과이동을 설명하지 않는다.
  v7 단일 양의 무부하 pulse로 맞춘 이동 모델의 역방향/짧은 lateral 일반화는 여전히 미검증이다.

### 실물 미세 정렬의 출처와 적용 범위

`sim/real_stack_adapter.py:241–247`의 45ms 문장은 **반복 출발·정지의 진행량 추론/적재 충격에
대한 경고**다. 현재 실제 실행 함수가 45ms 정렬을 권장하는 코드가 아니다.
`search.py:271,389`의 .045초는 정지 시 같은 표적을 재확인하는 영상 대기다.
초기 Git commit `2df57325`도 이 두 위치가 대기인 것을 확인했다.
`sim/real_stack_adapter.py:1098`와 `primitive.py:33`의 .30초는 공개 primitive 기본값이다.
옆 이동 65/.65초는 공개 helper의 별도 하한이며 미세 정렬에 그대로 맞지 않았다.

실물 `physical_state_machine_reference.py:267–283`은 35 고정·회전 .10/.12초,
`:442–450`은 35 접근의 .10/.08/.06초 단계, `:484–485,4459,4499`는
최종 전후 .06초 pulse, `:167–169,4500–4502`는 정지 뒤 .12초 camera 대기를 사용한다.
`Robot.drive`의 finally stop 뒤 새 영상을 확인한다. face 정렬 자체는 순수 strafe의 yaw/전후
누출 때문에 회전+직진 dog-leg(`:184–197`)로 바뀌었고, 마지막 x 오차는 servo6로 맞춘다
(`fine_align_horizontal`, :3858–3949). 이 제어기 전체를 이식했다고 주장하지 않는다.

새 `alignment_pulse=real_fine_v1`은 **정렬 상태에서만** 35 고정/.06초의 부호 보존 한 축
pulse와 종료 후 ≥.12초에 촬영한 새 자기 RGB를 사용한다. v106의 기존 횡 방향 요청에
이 짧은 primitive를 연결하는 부분은 명시적 DEV 어댑터이며 실물 lateral 검증은 아니다.
forward/left/yaw 축 선택·±3mm·시선·집기/자리 확인 정책은 유지한다. 바퀴 stop은 .25ms
물리 substep에서 만료되므로 .06초를 20Hz의 .10초로 반올림하지 않는다. 자기 명령/PF에도
실제로 발행한 .35/.06초만 전달한다. 원래 v7 고정 이동 모델을 유지하고 단기/lateral 전달의
미검증 범위를 기록한다. 옵션 off는 v114 출력/record bytes와 동일하다.

[Chaumette–Hutchinson 2006 튜토리얼](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf)의
영상 오차-카메라 운동 관계와 [2023 FoV/occlusion 제약 논문](https://arxiv.org/abs/2309.03476)의
초록을 확인했다. [2025 dead-zone visual servo 연구](https://doi.org/10.1177/01423312241273823)도
제목/초록 범위에서 확인했다. 복잡한 새 학습/CBF를 도입하지 않고 저장 영상으로 제약을 분리하고
기존 실물 bounded pulse→정지→재관측을 재사용한다. 논문 알고리즘 재현/새 실물 검증은 없다.

### 실행 전 등록

새 **zone-s2-realism-v115 / workflow7.8.0**, [번호/seed 조회](reservation-scan-v115.json),
[사전 등록](registration-v115.json). 새 미사용 **s1040/P1-2 probe**를 먼저 실행한다.
통과 시 아직 미사용인 **s1029/P1-1 → s1030/P2-1 → s1031/P1-2** full을 진행한다.
s1039는 재사용하지 않는다. 기존 원인 CYAN_ALIGN_VIEW_LOST 1회를 같은 원인 중단 계수에만
유지하므로 재발하면 두 번째로 멈춘다(성공률 분모에 합산하지 않음). 어떤 probe 실패도 full
통과 조건을 만족하지 않는다. 나머지 cap·dev_light·120초/1cm eval 감시·물리 실패 중단·
agent_lock·ugrp_session·nice0·출력 경로·ENOSPC HOST_ERROR·DRAFT/미병합은 동일하다.
새 코드와 이 등록을 바뀐 모듈 시험 통과 뒤 커밋/push한 SHA에서 실행한다.

변경 모듈 시험 `tests/test_s2_realism_alignment.py`: **5 passed**.
off byte 동일, s1039 실제 마지막 요청 변환, .06초 정확한 만료/잘못된 입력 거부,
정지 뒤 새 프레임 강제·정렬 외 구동 보존, 실제 IntegerClock.reset 경로, 새 등록/CLI 기본값을 확인했다.


## v115 결과와 변경 없는 v116 반복 확인 등록

소스 `57f8c174bb32648bef495a8ae9335dd1815745e3` / v115 s1040은 103.6 SIM초에
정렬→hover로 전이했다. 이때 eval 중심은 [202.554,-2.625]mm여서 목표 203.2mm와
±3mm 범위 안이었다. fine pulse 78회를 발행했으며 s1039의 CYAN_ALIGN_VIEW_LOST는
재발하지 않았다. 새 실패는 105.9초 `CYAN_HOVER_UNCONFIRMED`다.
원래 자리 기준 영상 ROI가 clipped라 저장되지 않았고, hover 자세 변화 뒤 cyan mask가
0px가 됐다(103.6초 19,867px → 104.9초 0px). 팔 이동 뒤 eval 좌우 오차는 약 -4.46mm다.
집기/들기는 시작하지 않았다. 최종 lifted/inside=false/false, 재집기0,
wall355.404초 / SIM108.9초 = 3.26358. 보수적 would-stop 13개는 기록만 했다.
full1029–1031은 probe 미통과로 미실행이며 출력 폴더도 생성되지 않았다.

같은 새 실패의 반복 여부를 확인하기 위해 **제어·물리·옵션·계수 수정 없이**
새 **v116/workflow7.9.0, 미사용 probe s1041/P1-2**를
[사전 등록](registration-v116.json)한다([번호/seed 조회](reservation-scan-v116.json)).
실행 admission/seed만 새 버전이며 `zone_solo_cyan_align_pulse.py`와 `sim/s2_align_pulse.py`는
v115와 바이트 동일하다. s1040은 재사용하지 않는다. hover 미확인이 다시 나면
같은 원인 2회로 종료한다. 다른 원인의 과거 s1039와 성공률/동일 원인을 합치지 않는다.
통과했을 때만 등록된 full1029–1031을 진행한다. 기본 off·시험 후 커밋/push·단일 잠금·
세션 관리·dev_light·외부 정체 감시·DRAFT/미병합은 이전 등록 그대로다.

후속 admission 시험 `test_v116_replication_preserves_behavior_and_counts_distinct_causes` 1개 통과. v115 실행 bundle이 참조한 소스 전체의 바이트 동일성도 재검사했다.
