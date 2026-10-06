# S2 현실성 재검증 — 실행 전 등록 (2026-10-06)

**최신 완료(v121):** `f0bb26e7`의 s1045는 pick→carry→place까지 진행했지만 **lifted=true/inside=false**다. B 밖 바닥에 안정적으로 놓였고 최종 위치 추정 오차3.839m를 확인했다. 팔 가드5회·위치 불확실519회는 기록만 했다. 추가 실행 없이 종료·잠금 해제했다. [완료 기록](#v121s1045-전체-dev-완료--b-밖에-놓음), [사전 기록](#v121-전체-dev-사전-기록--s1045-2026-10-07)을 따른다.

**이전 완료(v120):** 문헌 조사와 s1042·1043 오프라인 비교 뒤 새 s1044를 1회 실행했다. `97c05e41`에서 lifted=true였지만 두 들기 자세의 cyan이 각각 0/9로 **hold unknown·probe 미통과**다. 추가 실행·튜닝 없이 중단했고 잠금·세션·일회 실행기를 정리했다. [v120 완료](#v120s1044-완료--추가-실행-중단), [조사·사전 등록](#v120-레퍼런스-조사사전-등록--s1044-실행-전)을 따른다.

**이전 완료(v119):** `f6cb04b3` / s1043은 **lifted=true,inside=false,원래 자리 unknown,probe 미통과**다. 확대 여백 오류를 피하는 실물식 확인 옵션을 넣었지만 새 seed에서는 기준 cyan 자체가 렌즈 경계에 닿아 사후 확인을 시작하지 못했다. 경계에서 기준 확보 실패가 재발해 추가 SIM을 중단했다. [결과와 중단 근거](#v119s1043-완료--추가-sim-중단)를 따른다. freeze 사용 및 DEV seed 사전 기록은 후속 사용자 지시이며 본 연구 예외가 아니다.

**v117 당시:** v117 `ef820ab2`의 s1042는 hover·하강·SIM lifted=true에 도달했지만 pickup-site ROI clipped/unknown으로 probe gate 미통과다. [v117 완료](#v117s1042-완료-실행-sha-ef820ab2d367b1a25e14b0cc4df6be4b3e58bb3d)를 따른다. 이후 사용자 결정으로 #407을 병합하고 다음 **탐색 S2 DEV 전용** v118 freeze 프로필을 준비했다. [당시 제한과 미실행 상태](#2026-10-06-사용자-결정-idle-robot-contacts). 아래 v116 이전 요약·사전 등록은 당시 기록이다.

**후속 완료:** s1039의 직접 원인은 (a) 173mm 옆 이동에 의한 정렬/시야 초과다.
35/.06초 정렬 옵션을 적용한 v115 `57f8c174` s1040과 동일 동작 v116 `46b8e7af` s1041은
둘 다 정렬에 도달했으나 **CYAN_HOVER_UNCONFIRMED 2회**로 종료했다. full1029–1031은
미실행이며 추가 실행을 중단했다. [최신 완료 기록](#v115v116-최신-완료-기록)을 따른다.

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

## v115/v116 최신 완료 기록

두 새 probe는 동일한 제어/물리/옵션/계수로 실행했다. 버전 차이는 seed admission이며,
v115 소스 `57f8c174bb32648bef495a8ae9335dd1815745e3`, v116 소스
`46b8e7af8151f3d54f5fd098f85e0a1ad50b8f97`이다. 첫 실행 뒤 튜닝하지 않았다.
[v115 결과](completed-v115.json), [v116 결과](completed-v116.json),
[원본 기반 펄스·hover 비교](fine-hover-comparison.json), [그 분석 코드](audit_fine_hover.py).

|seed/slot|판정|lifted/inside|원래 자리 전후 cyan 면적|재집기|wall / SIM 초|wall/SIM|
|---|---|---|---|---:|---:|---:|
|1040/P1-2 probe|CYAN_HOVER_UNCONFIRMED|false/false|미측정/미측정|0|355.40354 / 108.900|3.26358|
|1041/P1-2 probe|CYAN_HOVER_UNCONFIRMED|false/false|미측정/미측정|0|255.55864 / 89.150|2.86661|
|1029/P1-1 full|NOT_RUN, probe 미통과|미측정|미측정|미측정|미측정|미측정|
|1030/P2-1 full|NOT_RUN, probe 미통과|미측정|미측정|미측정|미측정|미측정|
|1031/P1-2 full|NOT_RUN, probe 미통과|미측정|미측정|미측정|미측정|미측정|

raw는 각각 `/Users/changmin/projects/ugrp/outputs/s2-realism-57f8c174-s1040-P1-2-pick`,
`/Users/changmin/projects/ugrp/outputs/s2-realism-46b8e7af-s1041-P1-2-pick`이다.
full 예정 경로는 cohort JSON에 있으나 실제 디렉터리는 없다. wall 시간은 reset/cleanup 포함,
SIM 시간은 reset 1.3초 포함이다. seed와 호스트 부하가 달라 시간 차이를 성능 개선으로 해석하지 않는다.
모델 호출은 모두0, 명령 수 1276/1216, would-stop 13/50개는 기록만 했다.

정렬→hover 전이는 103.6/83.75 SIM초이며 당시 eval 오차는 각각 전후 −.646mm/−1.875mm,
좌우 −2.625mm/+1.134mm로 ±3mm 안이었다. fine pulse는 78/73회.
s1040의 한 펄스 평면 이동 중앙값은 forward7.470mm, lateral7.034mm였다.
이는 s1039의 마지막 lateral172.986mm보다 작지만, 매 pulse가 3mm 이하라는 주장은 아니다.
기존 영상 피드백으로 허용 구간에 들어간 결과이며 정식 정렬 일반화/실물 검증은 아니다.

두 번 모두 정렬 최종 영상은 cyan19,867/19,846px였으나 ROI 확장 영역이 lens edge에 걸려
`pickup-site comparison region is clipped`였다. hover 팔 자세로 바뀐 뒤 cyan0px,
모든 hover support=false여서 닫기/들기에 진입하지 않았다. 이 **정렬 영상→hover 영상 변화**는
원래 자리 집기 전후 비교 수치가 아니다. 같은 원인 CYAN_HOVER_UNCONFIRMED 2회로
중단했다. 과거 s1039의 횡방향 시야 이탈 1회와 합쳐서 동일 원인으로 세지 않는다.
새 probe 통과0/2·정렬 도달2/2이며 full 성공률은 없다. 정지 기준·hover 확인·ROI 가드를 완화하지 않았다.

실물에는 `physical_state_machine_reference.py:1517–1548`의 pan/tilt 추적과
`:4287–4348`의 고정 close pose 이동 후 같은 표적 재확인,
`search.py:281–299`의 아래 시야가 부족할 때 close near-look 전환이 있다.
그러나 실물 `Robot.drive`는 lateral을 65/.65초로 올리는 별도 정책도 갖는다
(`scripts/red_block/robot.py:252–292`). 이번 35/.06초 lateral 연결은 명시한 DEV 어댑터다.
기존 실물 전후 creep의 재사용과 실물 정렬 전체의 동일성을 구분한다.
새 hover/기준 ROI 문제는 남았고, 이를 해결하려고 카메라 mount/FOV나 파지 확인을 바꾸지 않았다.

### 전달과 종료 검증

- 새 동작 모듈5개 사례와 후속 admission1개 사례가 각각 통과했다. 같은 시험을 추가로 반복하지 않았다.
  사후 분석 스크립트는 실제 두 raw에 실행해 이미지 해시와 사건 시각을 대조했다.
- [완료 기록 검사](fine-record-verification.json): raw 파일 **3,839개**를 다시 해시했고,
  두 실행의 소스 closure는 그대로다. 독립 기하 심판·20Hz 프레임 시간·미실행 폴더 부재도 확인했다.
- [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-s2-realism-fine-v116%2F#timeseries)
  새 snapshot `outputs/tensorboard/1006-s2-realism-fine-v116`의 **3개 기록·48개 수치**가
  원본→event→기존 서버 live API에서 일치했다([전달 검사](fine-delivery-verification.json)).
  이 중 1개는 s1039 오프라인 원인 분석이며 추가 실행이 아니다. 이전 8개 기록의 snapshot은 보존했다.
  자기 view key `s2_realism_fine_20261006`만 추가했다. HParams 열/pinned tag/영상 등록을
  검사했고, 브라우저는 사용자 지시에 따라 생략했다. 변환 시 dirty 표시는 사후 기록/분석 파일이며
  실행 closure와 변환기 자체는 변경되지 않았다.
- 대표 4배속 MP4는 s1040(P1-2, 두 실패 중 첫 실행)을 선택했다. 새 seed 지시 때문에 옛 s1039와
  paired seed 비교가 아니다. `/Users/changmin/projects/ugrp/outputs/s2-realism-57f8c174-analysis/views/s1040-probe/execution.mp4`,
  26.15초/523frames/640×480/20fps/575008bytes,
  SHA256 `384ad6944cf42b44e0238cb3650b82af413c75b97f87cebc72d20c220915c84c`.
  전체 decode, 첫/중간/정렬 끝/마지막 프레임, TensorBoard manifest 등록을 확인했다.
- 자기 세션/드라이버 종료·잠금 해제·일회성 launchd job unload를 확인했다.
  다른 작업의 잠금은 해제될 때까지 기다렸다. 원격 push 일시 실패는 일반 push 재시도로 해결했다.
  강제 변경·raw 삭제·다른 작업 종료는 없었다. PR #406 DRAFT 유지·미병합이다.
  v116 실행 SHA의 CI는 확인 시25개 통과/7개 진행 중이며 전체 통과로 보고하지 않는다.

## 2026-10-06 hover 오프라인 분리와 v117/s1042 사전 등록

사용자 후속 범위: s1040/1041 hover 실패2회를 **시뮬레이션 없이 먼저** 분석하고, v3가 원인이면 카메라를 수정하지 않는다. 다른 원인을 고칠 수 있을 때만 새 probe1회를 실행한다. PR #406 DRAFT·병합 금지 유지. 이번 등록에는 full1029–1031을 넣지 않으며 기존 두 실패를 지우거나 성공률에 합산하지 않는다.

### 저장 영상과 기하 판정 (새 물리 실행 아님)

`analyze_hover_projection.py`와 `hover-projection.json`은 저장 RGB·명령 자세·eval 전용 블록 좌표/회전·로봇 xy/yaw만 사용한다. MuJoCo world/step/render를 만들지 않았다. 각 사진의 SHA-256을 확인했고 카메라 기록을 같은 블록에 바꿔 적용했다. `cv2.fisheye.projectPoints`의 8개 모서리 좌표와 모든640×480 pixel ray–cuboid 교차를 계산했다. **사각 이미지 범위와 실제 raw_fisheye_remap의 유효 영역을 따로 판정**했다. 렌즈의 x≈287 유효 하단은 row463이다.

|seed|정렬→중간→소실 cyan 면적(px)|첫0px SIM시각|이전 hover 모서리 y범위(px)|v3 hover 모서리 y범위(px)|이전 사각/유효 픽셀|v3 사각/유효 픽셀|
|---|---|---|---|---|---|---|
|1040|19,867(103.60)→11,498(104.00)→0|104.20|461.94–736.33|546.80–834.23|3,566 / **0**|0 / **0**|
|1041|19,846(83.75)→10,287(84.15)→0|84.35|476.01–778.31|558.56–883.89|54 / **0**|0 / **0**|

두 contact sheet를 직접 확인했다. cyan 상단이 아래로 내려가 렌즈 하단으로 사라지며 집게/팔이 가리는 패턴은 없다. 이전 카메라의 이미지 사각형 교차만 보고 '보인다'고 판정하면 틀린다. 둘 다 유효 영역에서는0px다. v3는 하단 이탈을 약83–85px 더 키우지만 **v3만의 회귀가 아니라 작은 cyan에도 hover 가시성을 요구하는 제어 정책의 불일치**다. 따라서 각도 변경 없이 실물의 pre-grasp 확인 방식을 옵션으로 옮긴다. +10°는 v3의 tool 상대 절대 각도이며 이전 카메라 대비10° 증가라는 뜻이 아니다. 카메라 mount/각도의 실물 타당성은 이번 계산으로 확정하지 않는다.

hover 카메라 원점(x,y,z; floor-heading,m): 이전[.205223,.000000,.115322], v3[.212001,.000000,.134357]. 광축(x,y,z): 이전[.558204,−.000000,−.829704], v3[.594437,−.000000,−.804142]. 두 seed의 블록 중심은 각각[.203915,−.004457,.015892]/[.201402,.000734,.015892]. 전체 회전행렬·모서리·명령 자세는 JSON에 있다. 정렬 시점 v3 예측 bbox는 관측과 최대2px 차이다. 카메라 위치/방향은 **기존 정지 명령별 SIM 보정 + mount 강체 변환**이며 각 프레임의 실제 관절·roll/pitch는 저장되지 않았다. 이 한계와 장면 occlusion을 계산하지 않았음을 남긴다. 이전 카메라 재실행 성공이나 실물 성공을 주장하지 않는다.

Raw는 원래 s1040/s1041 폴더 그대로다. contact sheet는 `/Users/changmin/projects/ugrp/outputs/s2-realism-hover-offline-20261006/s1040-hover-contact-sheet.png`, `s1041-hover-contact-sheet.png`다.

### 실물 근거와 명시 옵션

- `scripts/red_block/physical_state_machine_reference.py:250–254`:9장 중4hit,정지.45초; `track.py:45`:최소500px.
- 같은 파일`:4740–4758,4796–4832`:정렬한 정지 자세에서 기준 영상을 먼저 확보한다. hover가 바닥 블록 시야를 벗어나0/9였다는 주석 뒤, hover 이동→시각 재확인 없이 고정 경로 하강→닫기→들기를 수행한다. `:4760–4793`는 들어올린 뒤 기준 자세로 복귀해 floor-compatible 물체를 비교하며 PROBABLE_HELD로 한정한다. 파일의 해당 줄은 저장소 shallow 경계 `2df57325`에 이미 존재한다(그보다 앞의 작성 이력은 미확인).
- `scripts/red_block/pick.py:364–390`의 실제 near-field pick도 위 함수를 호출한다. `sim/real_stack_adapter.py:1175–1183`는 이 real pick 호출 후에만 별도 물리 평가를 한다. `:755–848`의SIM reach/픽셀/빠른 카메라 override는 실물 원본값과 구별했다. adapter는 hover 시각 재확인을 추가하지 않는다.
- 실물 `:4287–4348`에는 capture 자세로 시선을 바꾸고 새 영상 확인이 있지만 **hover에서 손목을 내려 추가 확인하는 동작은 위 집기 경로에 없다**. docs/archive의3개 추적 문서를 hover/blind/camera/집기 검색했으며 이 분기를 대체하는 실물 구현은 발견하지 못했다.
- [OpenCV fisheye 식](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html)을 확인해 그대로 계산했다. 기존 연구 근거의 look-then-move와 실제 공개 저장소 구현을 따르고, 새 카메라 최적화나 논문 알고리즘을 도입하지 않았다.

새 `hover_check=real_pregrasp_v1`(기본off): 기존2프레임 정렬 완료 후 팔을 움직이기 전에.45초 정지,최대9개 새 영상에서4회500px/고유 cyan/기존±3mm를 확인한다. 시각 anchor의 frame/hash/시각을 기록하고 hover 시각확인은 요구하지 않는다. 기존 고정 하강·닫기 명령 경계와30초 anchor 상한은 유지하며 자기 주행·pan·팔 경로 이탈 시 무효다. blind command window 시작 시각을 과거 시각확인 시각과 구분한다. 실물 확인 방식만 옮겼고 실제 arm 시간·IK·카메라·구동·pickup_site_v1 ROI 조건은 바꾸지 않았다. 따라서 **pickup-site clipped ROI는 별도 미해결 사항**이며 시각 파지 성공으로 대체하지 않는다.

### 실행 전 등록: s1042 한 번

main+열린 PR14개 및 raw에서 seed1042 사용 없음, bundle 최대116/workflow7.9.0 확인(`reservation-scan-v117.json`). 새 **zone-s2-realism-v117 / workflow7.10.0**, seed**1042/P1-2/pick**1개를 탐색적 수정 probe로 등록했다. s1040/1041은 원인 분석 자료이며 확증 분모에 넣지 않는다. `registration-v117.json`은 기존 실패2회를 별도 보존하고 사용자 지시의 수정 후1회만 허용한다. 자동 재시도/full 실행 없음, 결과와 무관하게 이 probe 뒤 종료한다. ENOSPC=HOST_ERROR,eval-only120SIM초1cm 미만 정체 중단,dev_light,agent_lock/ugrp_session,모델 호출0을 유지한다.

출력 예정 `/Users/changmin/projects/ugrp/outputs/s2-realism-<실행SHA8>-s1042-P1-2-pick`. 소스·이 README·사전 등록을 **시험 통과→commit→push한 뒤** 고정 SHA로 실행한다. `hover-preservation.json`: v115/v116 각각332개 실행 소스의 바이트를 유지했다. 변경 모듈 시험5개는 off 명령/기록 바이트 동일,실제 align/hover 기본 실패 경로 동일,실물 pre-grasp 확인→0px hover 하강/닫기,stale/미확인/주행 이탈 거부,저장 투영 재현 및 새 admission을 검사한다. 물리 probe의 결과는 아래 완료 기록으로 따로 보고한다.

### v117/s1042 완료 (실행 SHA `ef820ab2d367b1a25e14b0cc4df6be4b3e58bb3d`)

**hover 실패는 해소됐고 실제 SIM 블록도 올라갔다. 전체 probe gate는 원래 자리 확인 불가로 미통과**다. 94.65초 정렬 뒤95.15/95.25/95.35/95.45초의 서로 다른4개 frame에서 cyan19,782/19,778/19,771/19,774px를 확인했다. 96.75초 hover에서 이전 시각 anchor를 고정 명령 구간으로 넘겨 하강·닫기·들기를 진행했다. `CYAN_HOVER_UNCONFIRMED` 신규0회, 재집기0회다. 과거 s1040/1041 실패2회는 그대로 보존한다.

|seed|bundle / 실행 SHA|lifted / inside|원래 자리 확인 / 전후 면적|wall / SIM / wall·SIM비|
|---|---|---|---|---|
|1042/P1-2/pick|v117 / ef820ab2|true / false|unknown / 미측정|363.176558s / 140.350000s / 2.587649|

최대 block z=.140170675m, 상태`STAGE_REACHED_UNQUALIFIED`, 마지막 carry/HIGH. 순수 기하 판정을 별도로 재계산해 lifted/inside/floor/stable/success와 대조했다. 이는 정상 접촉 SIM 개발 증거이며 실제 하드웨어 성공·full 배송 성공이 아니다. 동작2613개, 모델 호출0개, fine pulse75회, saved RGB2722개다. dev_light would-stop은 ARM_COLLISION_GUARD3/POSE_UNCERTAIN12/GRASP_SCENE_UNCONFIRMED1을 기록만 했다.

95.45초 `pickup-site comparison region is clipped`로 기준 ROI를 만들지 못했으며120.15초 원래 자리 판정은before=null/samples=[]/unknown이다. pre-grasp4회 면적은 **집기 전후 면적 비교가 아니다**. 따라서 driver의 `PROBE_SITE_OR_LIFT_GATE_FAILED`는 이번에는 **site 확인 실패만**을 뜻한다(lifted=true). 사용자 지시대로 이1회 뒤 종료했으며 full1029–1031·추가 seed·재시도는 실행하지 않았다. 카메라 각도 및 ROI 조건도 수정하지 않았다.

- raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-ef820ab2-s1042-P1-2-pick`
- 사후 요약/해시: `/Users/changmin/projects/ugrp/outputs/s2-realism-ef820ab2-analysis/`; Git의 `completed-v117.json`, `hover-record-verification.json`에 연결했다. 원본과 이전 snapshot은 보존했고 자기 세션/드라이버 종료·잠금 해제·일회성 launchd unload를 확인했다.
- 4배속 영상: `/Users/changmin/projects/ugrp/outputs/s2-realism-ef820ab2-analysis/views/s1042-probe/execution.mp4`,34.05초/681frames/640×480/20fps/579138bytes, SHA256 `5ed6f0714aaab173ece3a9630964dfcb76252969e6f08fdd0ec35b0425ad2041`. 전체681frame decode 및 첫/hover/하강/마지막 프레임을 확인했다. 출력 프레임 양자화로 원본시간/4와25ms 차이(1frame 이내)다.
- TensorBoard 새 snapshot `1006-s2-realism-hover-v117`: **완료 probe1개 + 새 오프라인 투영2개 =3기록/41scalar**. 세 개를 시행3회로 합산하지 않는다. 원본→event→기존live6006 API 수치가 모두 일치하고 영상 등록/HParams 열/핀 태그를 확인했다. 공용 view의 자기 새 키`s2_realism_hover_20261006`만 추가했고 기존 서버PID52016/logdir와 다른 키를 보존했다. 사용자 지시대로 browser UI 검증은 생략했다. [TensorBoard 수치](http://127.0.0.1:6006/?runFilter=%5E1006-s2-realism-hover-v117%2F#timeseries), 상세`hover-delivery-verification.json`.

로컬 시험5개 통과 뒤에만 실행 소스가 커밋·push됐다. 사후에는 실행 코드를 바꾸지 않고 raw/source closure·등록 수치·영상만 검증했다. 최종 기록도 별도 commit/push하고 PR #406은 DRAFT·미병합으로 유지한다. 남은 문제는 pickup-site ROI이며 이 후속 요청에서 새 시야/ROI 방식이나 추가 실행은 도입하지 않았다.

## 2026-10-06 사용자 결정: idle robot contacts

사용자는 PR #407의 `idle_robot_contacts=freeze_v1`을 **혼자 cyan을 나르는 S2 DEV에만** 허용했다. `origin/claude/v7-roller-approx`의 `2d3ab0591ce5e3619a2ff735a9d9893b1199c1c2`를 현재 `codex/s2-realism`에 rebase 없이 병합했다. merge commit은 `e7e4e6cb`(부모 `e57814c8`, `2d3ab059`)다. 원격 두 PR은 DRAFT 그대로이고 main에는 병합하지 않았다. 충돌 없이 `--no-commit` 병합 후 변경 모듈 시험3파일27개 통과(2.19s)를 확인한 뒤 merge commit/push했다.

### 근거와 범위

[PR #407](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/407)의 [동등성 표](../2026-10-06-v7-roller-approx/README.md#동등성-표), `results-summary.json`, `work-record.json`을 확인했다. mesh+freeze는 **9/10 항목 통과**다. 단독 주행·cyan·옆 이동·접촉 깨움 항목은 통과했지만 **짝 빔1건은 실패**했다(y−16.85%, yaw차−.844°, 두 로봇 진행차+24.03%). 이 항목 수는 임무 성공률이 아니며 S2 전체 경로 동등성/실물 성공으로 확대하지 않는다. 이 근거는 #407의 다른 실행 자료이고 우리 S2 seed 분모에 합산하지 않는다. #407이 전체 후보를 미채택한 원래 기록은 그대로 보존하며, 이후의 사용자 결정만 이 절에 별도로 기록한다.

- 허용: **S2 / solo / cyan / dev-pilot / FUNCTIONAL_DEV / dev_light**, active robot1대의 탐색 DEV.
- 금지: **S3, 짝 운반, 본 연구, 사전 등록 실행**. `research_result=false`, `confirmation_sample=false`, `preregistered_run=false`를 모두 명시해야 한다. 누락/모순된 scope, 다른 bundle ID/schema, 추가 robot/pair task, sphere6 병용도 오류다.
- `harness/idle_robot_contacts_contract.py`의 공용 번들 검증을 새 계약·실행기·physics backend가 호출한다. on 상태의 S2 외 번들은 world 생성 전에 `IDLE_CONTACTS_S2_SOLO_EXPLORATORY_DEV_ONLY`로 거부한다. off/미지정은 기존 동작/기록을 건드리지 않는다. PR #407의 과거 저수준 물리 진단 실행기는 근거 재현용으로 보존하며 연구 실행 admission으로 사용하지 않는다.
- 전역 기본값은 **idle off / roller mesh** 그대로다. 새 S2 DEV 프로필에서만 freeze를 명시한다. `sphere6_v1`은 채택하지 않는다. 잠든 로봇의 정적/내부 접촉 readout이 사라지는 한계도 그대로 기록한다. 제어 입력·카메라·구동 계수·접촉 평가 기준을 변경하지 않는다.
- on/off 결과는 별도 조건으로 보존하고 성공·실패·학습 자료를 합산하지 않는다. **비교 지표는 wall/SIM만**이다. 짝/연구의 동등성으로 확장하지 않으며 seed·경로·관측 수·호스트 부하가 다르면 인과적인 가속률로 표현하지 않는다.

### 다음 번들과 현재 상태

main+열린 PR14개에서 최대v117/7.10.0을 확인하고 **zone-s2-realism-v118 / workflow7.11.0**을 예약했다(`reservation-scan-v118.json`). `dev-profile-v118.json`은 **실행 seed/코호트 사전 등록이 아닌 다음 탐색 DEV의 설정 프로필**이다. `dev_runs=[]`이므로 이번 작업에서 새 seed를 예약하거나 probe를 승인/실행하지 않았다. 과거 사전 등록된 full1029–1031과 소비된1032–1042는 v118에서 거부한다. 다음 probe는 hover/ROI 후속 판단에 맞는 새 탐색 DEV 설정·미사용 seed·소스를 먼저 고정할 때 연결한다. 사전 등록된 본 실험을 이 프로필로 옮기지 않는다.

v118 실행에는 기존 다섯 옵션과 함께 **`--idle-robot-contacts freeze_v1`을 명시해야 한다**. 옵션 누락/off는 execute 거부다. preview와 공용 구현의 기본값은 off이며, 실제 프로필은 on을 요청한다. 아직 새 seed가 없으므로 아래는 실행하지 않는 설정 점검이다.

```sh
.venv-sim-worker-mac/bin/python -m scripts.run_s2_realism_v118 \
  --expected-source-sha <commit-SHA> --output /absolute/primary/outputs/next-s2-dev \
  --stage-probe pick --min-wheel-cmd real_v1 --dead-reckoning v7_diag_v1 \
  --stagnation-watch window120_v1 --alignment-pulse real_fine_v1 \
  --hover-check real_pregrasp_v1 --idle-robot-contacts freeze_v1
```

새 backend는 world 생성에 `roller_collision=mesh, idle_robot_contacts=freeze_v1`을 실제 전달하고 적용된 world 기록을 검사한다. 생성 실패에도 임시 factory 연결을 복구한다. reset 후에는 `eval_only/idle-contacts-option.json`에 정책·적용값을 남긴다. `bundle.json`과 **`result.json.options.idle_robot_contacts`**에 freeze를 기록하며 결과에는 `result_condition=S2_DEV_idle_contacts_freeze_v1`, `pool_with_previous_s2=false`, `comparison_metrics=[wall_per_sim]`을 쓴다. result 원본 작성 경로를 재사용해 결과/manifest 해시도 일치한다. 오류 경로의 기록 전달까지 합성 테스트로 확인했다(실험 HOST_ERROR로 집계하지 않음).

|조건|실행/비교 상태|wall/SIM|
|---|---|---:|
|off: v117/s1042/ef820ab2|기존 단독 probe,363.176558wall초/140.35SIM초|2.587649|
|freeze: v118|**미실행**,다음 탐색 DEV부터 적용|미측정|

#407의 0.819→0.362는 물리 timer,1.070→.647은 계측 포함 고정 input50 진단이다. S2 전체 실행과 분모가 달라 위 표에 직접 섞거나 S2 가속률로 사용하지 않는다. #407 결과는 이미 기존 TensorBoard `1006-v7-roller-84e62dd1`에 있고 이번에 중복 변환하지 않았다. 기존 S2 snapshot도 유지했다.

`tests/test_s2_idle_contacts.py`는 scope 거부·기본off·세계 생성 전달/복구·reset 기록·result.json 옵션/조건·현재 admission없음·workflow 등록을 검사하며 **17개 통과(4.94s)**했다. CLI preview에서도 freeze 명시·seed 없음·허용 실행0개를 확인했다. [통합 검증 기록](idle-contacts-integration.json)을 남겼다. 실제 S2 SIM,새 wall 측정,모델 호출은 하지 않았다. 기존 v109–v117 계약/등록/raw는 수정하지 않았다. 공유 v7 소스는 #407 병합으로 바뀌었으므로 과거 재현은 원래 실행 SHA를 사용해야 한다. PR #406 DRAFT·미병합과 다른 작업 프로세스/자료를 유지한다.

## s1042 ROI 오프라인 원인과 s1043 실행 전 기록

`analyze_site_roi.py` / [수치 원본](s1042-site-roi.json)은 s1042 RGB·발행 자세·eval 전용 궤적만 읽었다. MuJoCo 생성/step/render 없이 저장된 camera calibration과 OpenCV fisheye 투영을 사용했다. 95.45초/프레임1884의 cyan은 **19,774px**, bbox **[218,319,148,142]**였고 전부 유효 렌즈 안에 있었다(가장 가까운 렌즈 경계까지4px). 하지만 `SiteMemory`가 반 bbox만큼 사방 확장한 ROI는 **[144,248,440,532]**,84,064px이었다. 아래52행15,392px이480행 영상 밖이고, 영상 안5,336px도 렌즈 검은 가장자리다. 총 **20,728px(24.66%)**이 보이지 않는 임의 여백이어서 **집기 전 기준 생성부터 실패**했다. 집기 후120.15초에는 `before=null,samples=[]`로 끝나 동일 자세 재관측을 시도하지 않았다.

정렬 발행 자세는 servo3/4/5/6=508/2432/1320/1500이다. eval 블록 중심은 차체 앞201.657mm·왼쪽−1.236mm·높이15.892mm였다. 이전 카메라 원점은[118.269,0,171.020]mm·광축pitch−52.301°,v3는[123.781,0,190.459]mm·−49.760°다. v3와 블록 중심 거리는191.154mm(이전176.124mm)다. v3의 투영하단460.434px은 이전396.488px보다63.946px 아래다. v3(+10° tool-relative 절대 mount)가 여유를 줄이지만 **이전 카메라도 같은 확장 규칙이면 렌즈 밖4,913px**을 요구한다. 따라서 카메라만의 회귀로 보지 않으며 mount/FOV/arm 정렬 자세를 바꾸지 않는다. 실제 관절·roll/pitch는 프레임별로 저장되지 않아 발행 자세의 기존 정지 보정값을 썼다.

120.15초 HIGH 발행 자세896/2035/1894/1500에서는 원래 바닥 자리의 가상 블록 투영이 v3 y711.704–1261.901px(이전651.148–1097.067px)로 두 카메라 모두 유효0px이다. 실제 사진의 cyan7,959px은 들고 있는 블록의 하단 strip이며 원래 자리 면적이 아니다. 실제 집기 후 **원래 관찰 자세** 사진은 이 실행에 없으므로 새 옵션의 사후 확인을 s1042 성공으로 소급하지 않는다. 사전 배경의 ECC std도 **.430826 < 기존 기준2.0**이므로 여백 자르기만으로는 등록/비교가 성립하지 않는다.

### 실물 근거와 최소 선택 옵션

- `scripts/red_block/physical_state_machine_reference.py:4643–4793`: 정지한 집기 전 관찰 자세를 저장하고 집기 뒤 복귀한다. .45초 정지 후 최신 snapshot 최대9개에서 **바닥 기하와 맞는 색 물체가1회 이하**면 `FLOOR_CLEAR_PROBABLE`이다. 원래 자리만 좁게 맞추는 과거 방식 대신 전체 프레임의 바닥 물체를 보므로 옆으로 밀린 실패도 찾는다. 힘/전류 센서가 없어 **PROBABLE_HELD이며 확정 파지가 아니다**. apparent-size fallback은 바닥 증거에서 제외한다.
- `scripts/red_block/pick.py:364–393`가 이 경로를 호출한다. `sim/real_stack_adapter.py:1151–1187`의 bilateral contact/z 검사는 **그 뒤 별도 SIM 평가**이며 실물 제어기가 받은 성공 증거가 아니다. docs/archive의 검증 요약은 과거 SIM 기록이며 다른 실물 확인 구현을 근거로 사용하지 않았다.
- 새 `site_check=real_floor_v1`은 같은 자세·차체 정지·9개 고유 fresh frame·.45초 settle·1회 이하 기준·최대1회 재집기를 따른다. 기존 보정된 자기 fisheye RGB의 **floor-cuboid fit(`range_class=near`)**을 재사용한다. SDK의 pinhole/floor-ray 식을 SIM 보정 대신 넣지 않고 기존 학생 기하를 유지하는 차이가 있다. 큰 ROI/ECC·카메라 재배치·정답 좌표 입력·측정 관절·접촉 피드백은 없다.
- 빈 바닥은 저대비이므로 사후 색 검사에 한해 기존 `CONTENT_ONLY` 중 fresh/JPEG/shape 검사를 통과하고 dark_fraction<.25인 영상을 사용한다. 위치 추정 게이트는 그대로다. black/stale/hash 오류·발행 차체 이동·관찰 자세 불일치는 unknown이다. 기준 cyan 자체가 렌즈 경계에서 잘리면 여전히 거부한다. 전체 바닥 fit과 별개로 **원래 bbox의 전후 cyan 면적**도 기록하지만 들고 있는 strip은 면적에 포함될 수 있어 판정식으로 쓰지 않는다.
- 새 상태는 `probable_held_floor_clear`; 기존 `visual_grasp_confirmed`를 true로 만들지 않는다. `result.json`에 `probe_gate_passed`, `probe_failure`, `grasp_claim`과 두 옵션을 기록한다. DEV probe gate는 이 제한적인 RGB 확인과 독립 eval `lifted=true`를 모두 요구하며 inside/정식운반/실물 성공과 구분한다.
- 기본 off는 이전 Runtime/SceneCheck를 그대로 사용한다. 기존 v109–v118 실행기·계약·raw를 수정하지 않았다. `idle_robot_contacts_contract`에는 **후속 사용자 지시의 seed 사전 기록 S2 DEV probe만** 명시적 예외를 추가했다(`registration_kind=s2-dev-probe`,사용자 지시ID,stage=pick,site_check 필요). S3·짝·연구·본 연구 사전 등록은 계속 거부한다. 과거 v118의 등록 없는 미실행 상태를 덮어쓰지 않는다.

표준 방법 조사: [OpenCV fisheye](https://docs.opencv.org/4.13.0/db/d58/group__calib3d__fisheye.html)의 고정 K/D 투영과 [ECC 공식 설명](https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html)의 영상 등록을 확인했다. [시야/가림 제약을 다루는 공개 IBVS 논문](https://arxiv.org/abs/2309.03476)은 특징을 시야에 유지하도록 제어를 바꾸는 방법이다. 이번에는 실물의 동일 자세 바닥 확인을 재사용하므로 새 제어 법칙·학습·FOV 튜닝을 도입하지 않는다. 논문 결과를 우리 성공 증거로 사용하지 않는다.

### s1043 실행 전 기록 (커밋 이전, 아직 미실행)

main+열린 PR14개의 ID/버전과 명시적 seed 필드·이름·CLI 및 공용 raw를 확인해 **v119 / workflow7.12.0 / s1043**을 예약했다(`reservation-scan-v119.json`). 숫자 일부가 같은 파일해시·프레임번호·기하 수치는 seed 사용으로 세지 않았다. **seed1043,r3,P1-2→B/door_1,pick probe1회**만 허용한다. 사후 튜닝에 사용한 s1042는 재사용하지 않는다. 이 새 seed DEV 검증을 통계적 본 연구 확증으로 승격하지 않는다.

실행 옵션은 camera v3,drive v7,setdown_relook=off,grasp_check=pickup_site_v1,min_wheel_cmd=real_v1,dead_reckoning=v7_diag_v1,stagnation_watch=window120_v1,alignment_pulse=real_fine_v1,hover_check=real_pregrasp_v1,**idle_robot_contacts=freeze_v1,site_check=real_floor_v1**이다. 모든 새 옵션의 전역 기본값은 off다. [registration-v119.json](registration-v119.json)과 README를 **관련 시험 통과→Co-Authored-By: Codex 커밋→push 후** 고정 SHA로 실행한다.

변경 시험 `tests/test_s2_real_site.py`와 `tests/test_s2_idle_contacts.py` **22개 통과(10.74s)**. 저장 JPEG의 기존 ROI 실패/새 기준 수용, off 명령·기록 바이트,9fresh/정지/동일자세/밝은 저대비/검은영상·중복·이동 거부,바닥 검출 실패·재집기 한도,범위·등록 seed·result 옵션을 확인했다. 실제 사후 RGB 확인은 아직 실행 전이다. 시험 중 발견한 저대비 색 확인 경로를 고친 뒤 전부 재통과했으며 이 시험을 물리 성공으로 세지 않는다.

raw 예정 `/Users/changmin/projects/ugrp/outputs/s2-realism-<SHA8>-s1043-P1-2-pick`. `ugrp_session run`→`launch_v119.zsh`→표준`sim_cli workflow run`이며 실행기 PID의 agent_lock을 acquire하고 finally/EXIT에서 release한다. 한 번에1개·nice0·dev_light·120SIM초/1cm 정체 eval 중단·실제 물리 실패 중단을 유지한다. case cap1800SIM초,wall cap10800초,시작 시 여유51.26GiB를 확인했다. ENOSPC는HOST_ERROR이고 부분 raw도 보존한다. 같은 원인이2회면 중단한다(기존 ROI 확인불가 s1042=1회; 동일 원인 재발이면 추가 seed 없음). 이 probe1회 뒤에는 결과에 관계없이 이번 실행을 끝내고 기록하며 full1029–1031은 이 등록에 포함하지 않는다.

freeze 전후 결과는 합산하지 않는다. off s1042 wall/SIM=**2.587649**와 새 실행의 wall/SIM만 기술적으로 나란히 기록하며, seed·확인 동작이 달라 인과적인 가속률로 해석하지 않는다. 결과·전후 면적·재집기·시간·영상·TensorBoard는 종료 후 실제 값으로 기록한다. PR #406은 DRAFT·미병합으로 유지한다.

## v119/s1043 완료 — 추가 SIM 중단

실행·수정·seed 사전 기록 SHA **`f6cb04b360363edde2683fa50941d377d20f5758`**, bundle **zone-s2-realism-v119**, workflow7.12.0이다. 변경 모듈 시험22개 통과 뒤 `Co-Authored-By: Codex <codex@openai.com>`으로 커밋·push하고 실행했다. 실행 중 소스는 고정됐고 종료 뒤 bundle source346파일·raw2,198파일 및 원래 manifest 해시를 대조했다. 상세 [완료 결과](completed-v119.json), [새 기준 실패](s1043-site-reference-failure.json), [전달 검증](site-delivery-verification.json).

|seed/조건|probe / lifted / inside|원래 자리 확인|wall초 / SIM초 / wall·SIM비|
|---|---|---|---|
|s1042/off/v117|미통과 / true / false|expanded ROI clipped,unknown|363.176558 /140.35 /2.587649|
|**s1043/freeze/v119**|**미통과 / true / false**|**target at lens edge,unknown**|**165.725440 /112.90 /1.467896**|

두 행은 wall/SIM만 나란히 기록하며 결과 분모·성공률을 합산하지 않는다. 확인 정책·seed·이동 펄스 수·호스트 부하도 달라 **freeze 인과 가속률로 해석하지 않는다**. 새 실행 명령2,520개,정렬 펄스66회,재집기0회,모델 호출0개,최대 cyan 높이.139680m이다. dev_light 기록은 ARM7/POSE60/GRASP_SCENE1이며 기록만 하고 종료 시점까지 진행했다. full1029–1031은 미실행이다.

새 원인:68.10초 기준 사진1337에서 bbox **[213,322,148,142]**, cyan **19,854px**이었다. 이제 확장 여백을 요구하지 않지만, 실제 cyan support가 **유효 렌즈 밖47px·1pixel 렌즈 경계170px**과 겹쳐 `real floor reference is clipped or unsupported`로 거부됐다. bbox하단463px,경계 여유0px이다. eval 전용 기하 투영도 하단465.045px이고 사각형19,785px 중 유효19,581px(204px 제외)로 경계 이탈을 지지한다. mask의47px과 기하204px은 JPEG/정지보정/면 투영 차이가 있으므로 동일 측정으로 취급하지 않는다. 원래 s1042보다 eval target이1.210mm 더 가까워 시야 여유가 줄었다. 카메라 각도를 변경하거나 이 새 seed에 맞춰 임계값을 완화하지 않았다.

사후92.70초 체크는 다시 **before=null,samples=[]**였다. 앞의19,854px은 실패 직전 이미지의 진단 면적일 뿐 **집기 전후 비교 면적은 미측정**이다. 바닥 검출0/9나 성공 확인으로 바꾸지 않는다. `visual_grasp_confirmed=false`, `probe_gate_passed=false`, `probe_failure=SITE_OR_LIFT_UNCONFIRMED`를 raw result/student 기록 그대로 유지한다. lifted=true는 별도 eval 판정이다. 새 `PROBABLE_HELD` 확인 경로는 이 probe에서 실제 도달/검증되지 않았다.

중단 기준은 보수적으로 **원래 자리 기준을 렌즈 경계에서 확보하지 못하는 문제**의2회(s1042,s1043)로 묶었다. 세부 원인은 s1042=확장 여백,s1043=cyan 자체의 경계 접촉으로 구별했다. 따라서 새 seed·추가 튜닝·물리 실행 없이 중단한다. 남은 문제는 정렬 허용 위치에서 재관측 기준 전체가 보일 만큼의 시야 여유 확보이며, 카메라 하드웨어 각도는 사용자 실물 확인 대상이다.

- raw `/Users/changmin/projects/ugrp/outputs/s2-realism-f6cb04b3-s1043-P1-2-pick`; managed 기록은 같은 경로 뒤`-managed/manifest.json`이다.
- 4배속 own-RGB 영상 `/Users/changmin/projects/ugrp/outputs/s2-realism-f6cb04b3-analysis/views/s1043-probe/execution.mp4`:27.15초/543frames/20fps/414,990bytes,전체 decode통과,sha256 `32e44a41e9c76a2bd54a55fd64435cfebfa28d1e7e4918a303da8c1ae0fa0776`.
- [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-s2-realism-site-v119%2F#timeseries): **실패 probe1건+오프라인 ROI 분석1건/29scalar**,원본→event→기존live6006 API 수치 일치. 두 기록을 실행2회로 세지 않는다. 영상 등록과 HParams/핀 설정을 확인하고 공용 view에 자기 키`s2_realism_site_20261006`만 추가했다. PID52016/logdir 및 과거 snapshot은 보존했다. 사용자 지시대로 browser UI 대신 수치만 대조했다.
- 첫 도구 셸 실행은 inherited nice10 검사에서 **SIM·seed 사용 전에 거부**됐다. 로그를 보존하고 기존 일회성 launchd(KeepAlive=false)→ugrp_session 경로로 nice0 실행1회만 시작했다. **agent_lock release·세션 stopped·launchd unload·자식 종료**를 확인했다. 다른 작업 프로세스/자료는 건드리지 않았다.
- eval idle 옵션 sidecar는 #407 기본 정책 문구를 유지하고, 실행 bundle에는 후속 사용자 지시의 DEV seed 사전 기록 예외가 별도로 명시돼 있다. 실제 옵션 적용값은 둘 다 freeze_v1이다. 본 연구 예외나 S3/짝 실행으로 해석하지 않는다.

사후에는 제어 코드/번들/원본 결과를 바꾸지 않고 이 실패 기록과 전달 증거만 별도 커밋한다. raw/영상은 로컬 보존이며 GitHub 원격 raw 백업으로 표현하지 않는다. PR #406은 **DRAFT·미병합**이다.


## v120 레퍼런스 조사·사전 등록 — s1044, 실행 전

2026-10-06 후속 사용자 지시: 같은 시야 경계 실패 뒤 표준 방법을 조사하고,
저장 자료와 분리한 **새 seed1044 / r3 / P1-2 / pick 1회**만 실행한다.
성공·unknown·실패 어느 결과든 이 실행으로 끝내며 full1029–1031은 실행하지 않는다.
PR #406은 DRAFT, 병합 금지. 번호는 main+열린 PR14개에서 최대119/7.12.0을
확인해 **zone-s2-realism-v120 / 7.13.0**으로 예약했다
([예약](reservation-scan-v120.json), [실행 사전 기록](registration-v120.json)).
1042·1043은 탐색 자료이며 새 실행의 확증 자료로 재사용하거나 합산하지 않는다.

### 조사 결과와 출처

| 방법 | 원문에서 확인한 판정 | 현재 S2/MasterPi에서의 채택 여부 |
|---|---|---|
| 개도·힘 피드백 | [Levine et al. 2018, IJRR](https://journals.sagepub.com/doi/10.1177/0278364917710318)의 [공개 선행 원문 §5.2](https://arxiv.org/pdf/1603.02199)은 실제 개도 >1cm와 얇은 물체용 drop 전후 영상 비교를 사용. [Pinto & Gupta 2016 §III-A](https://arxiv.org/pdf/1509.06825)는 20cm 들어 올린 뒤 Baxter 그리퍼 force sensor로 라벨링. | 현재 MasterPi에는 이 측정 스트림이 없어 미채택. 발행 PWM을 개도 측정으로 바꾸어 부르지 않는다. 전류만으로 이 세 논문을 한데 분류하지 않는다. |
| QT-Opt 성공 라벨 | [Kalashnikov et al. 2018 §5, Appendix D.3](https://arxiv.org/html/1806.10293v3)은 팔을 장면에서 치우고 drop 전후 배경 차분으로 라벨링. gripper open/closed는 정책 상태에 포함되지만 성공 라벨이 전류 센서라는 근거는 없다. | 운반 중 물체를 놓는 drop test는 이번 조건과 맞지 않아 미채택. 모델 훈련·호출 없음. |
| in-hand RGB | [Nair et al. 2020 §V](https://arxiv.org/html/2003.10167v1)은 손이 보이는 카메라 영상의 grasped/not-grasped 분류. [Amargant et al. 2025](https://arxiv.org/html/2505.03046v1) 및 [공개 코드/자료](https://github.com/pauamargant/HSR-GraspSynth)는 gripper 검출 후 물체 유무 분류. | 측정 방법을 채택. 카메라를 옮기거나 학습 분류기를 이식하지 않는다. 단일 알려진 cyan·모델 호출 금지 제약 때문에 기존 HSV와 두 들기 자세의 지속성을 쓰는 **DEV 한정 적응**이다. 원 논문 알고리즘/정확도의 재현이나 검증된 범용 분류기라고 주장하지 않는다. |
| 능동 재관측 | [Morrison et al. 2019 Multi-View Picking](https://arxiv.org/abs/1809.08564)은 불확실성을 줄이는 시점 이동. [Terashima et al. 2025](https://alife-robotics.co.jp/members2025/icarob/data/html/data/OS/OS17/OS17-6.pdf)은 손·물체 이외 배경을 depth로 가린 뒤 차분하며, 배경/가림을 통제하지 않은 차분의 한계를 보인다. | 원래 자리로 시선을 돌리거나 후진하는 원리는 타당하지만, 위 논문들이 이 MasterPi의 5cm 후진을 검증한 것은 아니다. 두 raw에 해당 후진 영상이 없고 깊이 센서도 없으므로 계산상 시야 확보와 실제 확인을 구분한다. 이번 probe에는 추가 후진을 넣지 않는다. |

실물 구현 근거: `scripts/masterpi_control.py:74–78`은 PWM servo에 위치
피드백이 없고 `load_pose_state`가 마지막 **명령**이라고 명시한다.
`ServoTransport:349–363`은 write만 제공한다. `scripts/red_block/robot.py:192–207`도
I2C write·대기 뒤 `self.pose`에 목표 PWM을 저장한다. 배터리 전압 판독은 서보 전류가 아니다.
[Hiwonder 공식 제품 자료](https://www.hiwonder.com/products/masterpi)는 PWM 서보를 명시한다.
다른 Hiwonder bus servo의 encoder API나 새 보드의 PWM pulse readback을 이 로봇의
실측 관절 피드백으로 대체할 수 없다. 하드웨어에 새 센서를 연결하거나 읽지 않았다.

`physical_state_machine_reference.py:4740–4793`, `pick.py:364–393`은 집기 전
신뢰 자세를 저장하고 집은 뒤 같은 자세에서 바닥색을 최대9 fresh frame으로 확인한다.
바닥에 해당하는 검출 <=1이면 **FLOOR_CLEAR_PROBABLE**, 힘·전류 없는
positive hold proof는 아님을 원 코드가 명시한다. `sim/real_stack_adapter.py:1151–1187`
의 bilateral contact/z 검사는 별도 SIM 후조건이며 이번 제어 입력으로 쓰지 않는다.
기존 s1042·1043 기록은 이 구분을 그대로 보존한다.

### 저장 자료 후보 비교 (실행·튜닝 자료, GT는 아래 평가 열에만)

[재현 코드](compare_grasp_verifiers.py), [전체 수치·이미지 해시](grasp-verifier-comparison.json).
이미지 hash와 own RGB/발행 명령을 사용한 판정 뒤 별도 평가 결과를 읽는다.

| 후보 | s1042 | s1043 |
|---|---|---|
| 실측 개도/전류 | 자료 각각0개 → unavailable | 자료 각각0개 → unavailable |
| 기존 원래 자리 | unknown, 실제 비교 sample0 | unknown, 실제 비교 sample0 |
| in-hand 두 자세 | VIA110 9/9, HIGH 9/9; mask IoU **0.991401**, 중심 이동 **0.237625px** → probable | VIA110 0/9, HIGH 0/9 → **unknown** |
| 첫 lift부터 기존 check까지 모든 RGB | 425프레임, cyan **7959–8064px**, 중앙8010 | 425프레임, cyan **0px** |
| 5cm 후진 뒤 같은 팔 자세의 가상 원래 자리 | 바닥 가설 bbox 아래행460→326, valid15967px | 아래행463→330, valid16122px |
| 별도 GT 평가 | lifted=true / inside=false | lifted=true / inside=false |

후진 계산은 RGB가 추정한 중심·정적 물체 치수·발행 이동 가정만 쓴 순수 기하이다.
손/화물 가림과 실제 이동을 포함하지 않으며 두 실행 모두 counterfactual 판정은
**unknown**이다. in-hand 후보도 s1043의 실제 lifted를 읽고 성공으로 바꾸지 않는다.
v3의 5.63%는 특정 카메라 검토 장면 값이며 모든 파지의 최소 가시 면적이 아니다.

### 선택한 명시 옵션과 고정 판정

`hold_check=off|inhand_rgb_v1` (기본 off). off는 v119의 명령·record를 그대로 위임한다.
on은 기존 들어 올리기(VIA110→HIGH)의 정지 구간에서만 각각 fresh9장,
0.45s 자세 안정 대기, cyan90px 이상8/9장, 두 majority mask IoU>=0.90,
중심 이동<=12px일 때 **probable_held_inhand_rgb**를 기록한다. 보이지 않음·오래된
영상·digest 오류·흑영상·개방/차체 명령·불완전 관찰은 성공 근거로 쓰지 않는다.
카메라/그리퍼/들기 경로를 수정하지 않고, 원래 자리 ROI 검사를 느슨하게 하지 않는다.
기존9장/0.45s/90px/12px는 실물·기존 비교 코드의 수치를 재사용하며, 8/9와
IoU0.90은 새로 고정한 DEV 판정 선택이다. 두 양성 실행만으로 false-positive
비율이나 파지력을 검증할 수 없고, 발행 팔 이동이 실제로 이행됐다는 보장도 없다.
이 한계를 기록한 **시각적 probable**만 채택하며 force/contact 확인이라고 부르지 않는다.

실행 options는 v3, v7, setdown_relook=off, grasp_check=pickup_site_v1,
min_wheel_cmd=real_v1, dead_reckoning=v7_diag_v1, stagnation_watch=window120_v1,
alignment_pulse=real_fine_v1, hover_check=real_pregrasp_v1,
idle_robot_contacts=freeze_v1, site_check=off, hold_check=inhand_rgb_v1이다.
`grasp_check`는 기존 확장 진입점이며 **effective verifier는 inhand**이다.
result의 `pickup_site_status=not_evaluated_inhand_selected`와 `hold_status`를 분리한다.
probe pass는 stage reached + 시각 probable + 별도 eval lifted 모두 필요하다.
원래 자리 비교에 성공했다고 보고하지 않는다.

freeze는 사용자 승인 **S2 단독 DEV**에서만 사용. S3·짝 운반·본 연구·본 연구 사전 등록 금지,
현재 사용자 지시의 새 seed DEV 사전 기록만 명시적 예외이다. 옵션 off/on 결과 합산 금지,
wall/SIM만 비교하며 서로 다른 seed/경로의 인과 속도 비교라고 주장하지 않는다.
실행은 시험 통과→이 README와 소스 커밋·push→잠금 status null 확인→acquire→
ugrp_session으로 1개만 수행한다. PR405 잠금 강제 해제/다른 프로세스 종료 금지.
120 SIM초에1cm 미만 정체는 기존 eval 감시를 유지한다. ENOSPC는 HOST_ERROR,
partial raw와 seed를 보존하며 재사용하지 않는다. 실패/unknown이면 추가 실행 없이 중단한다.

실행 전 검증: `tests/test_s2_inhand.py`, `tests/test_s2_real_site.py`,
`tests/test_s2_idle_contacts.py` **26 passed /16.80s**. 저장 양성·가림, 움직이는
cyan 음성 대조, close 명령만 있음/영상 없음, stale·hash 오류, off 명령/record bytes,
seed·S2 freeze 범위·오류 result를 검사했다. 추가 로컬 전체 시험/모델 호출은 하지 않았다.


## v120/s1044 완료 — 추가 실행 중단

실행 소스 **97c05e4105f2eef98e53ad310b81f92549ac761f**, 번들 **zone-s2-realism-v120**.
이 SHA에 seed1044 사전 등록·제어 소스·고정 기준을 함께 커밋하고 push한 뒤 실행했다.
PR405의 잠금이 실제 `null`이 된 뒤만 acquire했다. 기존 tool process의 nice10을
변경하지 않고, RunAtLoad=true/KeepAlive=false인 수동 일회 launchd 경로로
`ugrp_session run s2-inhand-s1044 -- zsh launch_v120.zsh ...`를 실행했다.
드라이버 PID/PGID15180·nice0 확인. agent_lock으로 단독 실행했다.

- **probe_gate_passed=false / hold_status=unknown**, `INHAND_OR_LIFT_UNCONFIRMED`.
  VIA110 **0/9**, HIGH **0/9**, 실제 샘플18장 모두 cyan **0px**.
  fresh 관찰18장은 완결됐으나 물체가 안 보여 mask IoU/중심 이동은 미측정(null)이다.
  HIGH 원본 `robots/r3/rgb/01978.jpg`도 직접 확인했다. 소실을 empty/실패로 단정하지 않았다.
- 평가 전용 **lifted=true, inside=false, floor=false, stable=true, delivery success=false**.
  제어에는 GT를 쓰지 않았고 독립 궤적 채점과 기존 평가의5개 bool이 모두 같다.
  시각 판정과 물리 상승을 합쳐 성공으로 바꾸지 않는다. raw의 `grasp_claim`은 방법의
  주장 상한이며, 실제 판정은 `hold_status=unknown`이다.
- `pickup_site_status=not_evaluated_inhand_selected`: 원래 자리 전후 비교는 수행하지 않았다.
  따라서 전후 비교 면적은 null. pregrasp 면적이나 held 영상 면적을 site-after로 넣지 않는다.
- 재집기0, 명령2039, 모델 호출0, RGB2129장. wall **177.457465s**, total SIM **110.7s**,
  check SIM109.4s, wall/SIM **1.603048**. 출력:
  `/Users/changmin/projects/ugrp/outputs/s2-realism-97c05e41-s1044-P1-2-pick`.
- freeze 전 s1042 **2.587649**, freeze 후 s1043 **1.467896**, 이번 s1044 **1.603048**.
  wall/SIM만 나란히 기록한다. seed·경로·검사 시간이 다르므로 인과 속도 개선 주장이 아니며
  성공률/결과를 합산하지 않는다.
- 사용자 지시대로 **새 probe1회 후 중단**. 1044 재사용·추가 seed·full1029–1031 없음.
  기본값 off, 카메라 각도·물리·그리퍼·판정 문턱을 이 실패 뒤 조정하지 않았다.
  현 시야에서 cyan이 보이지 않는 경우 이 옵션으로 성공을 확인할 수 없다.
- **agent_lock 해제, session stopped, PGID15180 잔여 프로세스0, 일회 launchd unload 확인**.
  다른 작업/PR/프로세스는 수정·종료하지 않았다. raw와 이전 결과는 보존했다.

[완료 수치·옵션·원본 해시](completed-v120.json),
[TensorBoard 수치·HParams·영상·정리 검증](inhand-delivery-verification.json).
실행 bundle source closure **349파일**과 raw manifest/프레임 hash를 대조했다.
4배속 MP4(26.6s,532frames)는
`/Users/changmin/projects/ugrp/outputs/s2-realism-97c05e41-analysis/views/s1044-probe/execution.mp4`,
SHA256 `0a45916aa7917022bf98d22fe14413f80644faebe1022385c7b7a0498571a15b`;
ffprobe 및 전체 decode 통과, TensorBoard video id `0df1674a7a870162f501` 등록.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-s2-realism-inhand-v120%2F#timeseries)의
새 snapshot `1006-s2-realism-inhand-v120`은 **실행1 + 오프라인 재분석2**, 시험3회가 아니다.
30개 scalar를 source→event→실제6006 API에서 대조했다. 사용자 수치만 비교 지시로
브라우저는 열지 않았다. 기존 TB PID52016/logdir를 유지했고 공용 view에는 자기 새 키만 추가했다.

후속 기록 과정에서 CI glob이 `test_s2_realism*.py`만 포함하던 누락을 발견해
`test_s2_*.py`로 수정했다. 새 inhand/기존 real-site/freeze 시험도 원격 CI에 포함된다.
이 변경은 실행 source closure 밖의 CI 목록뿐이며 제어 소스는97c05e41 그대로다.
목록/분할 검사 `tests/test_ci_sharding.py` **68 passed /1.62s**;
실행 전 관련 모듈26시험 통과와 별개로 기록한다. 전체 CI를 로컬에서 돌리지 않았고,
PR #406은 DRAFT·미병합으로 유지한다. 로컬 raw 보관을 원격 백업으로 표현하지 않는다.

## v121 전체 DEV 사전 기록 — s1045, 2026-10-07

최신 사용자 결정은 **시각 unknown을 DEV 정지 조건에서 제외**하고 전체 경로 1회를 수행하는 것이다.
이 결정은 위 v120의 probe gate/추가 실행 중단 지시를 대체한다. 기존 실행 결과는 그대로 보존한다.
main+열린 PR 14개(15 refs)의 최댓값 v120/7.13.0을 확인하여 **zone-s2-realism-v121 /7.14.0**을 예약했다.
seed1045 등록/실행 흔적과 primary outputs가 없는 것을 확인했다([예약 조회](reservation-scan-v121.json)).
**새 seed1045, r3, P1-2, destination B, door_1, stage=place, 전체 DEV 단 1회**를 실행 전에 기록한다.
1029–1031 또는 1042–1044를 재사용하지 않는다. [기계 판독 등록](registration-v121.json).

오프라인 [비교 코드](compare_carry_views.py)와 [수치·원본 해시](carry-view-comparison.json)는
기존 RGB·발행 팔 명령·평가 전용 궤적만 읽었으며 새 시뮬레이션을 만들지 않았다.
carry 진입 직전 마지막0.5초의 HIGH11장(유효 렌즈 마스크 적용)에서 cyan은
s1042 **7599–7600px(중앙7600)**, s1043·s1044 **0px**이다. 이전 ~8000px는
들기 구간·전체 영상 마스크의 수치이므로 표본과 유효 영역을 혼동하지 않는다.
세 실행의 carry 팔 명령은 **1/3/4/5/6=1500/896/2035/1894/1500**으로 완전히 같다.
GT를 차체 yaw 좌표로만 변환한 블록 중심은 s1042 기준 s1043 **1.577mm**,
s1044 **1.350mm** 차이, 상대 회전 차이는 **0.745°/0.683°**이다.
그리퍼 실측 자세가 저장되지 않아 이를 손 안의 상대 이동으로 확정하지 않는다.

명령 HIGH의 보관 보정값으로 계산한 v3 광축 pitch는 모두 **−36.592°**(아래),
가림 없는 블록 광선 투영은 **74545/55055/57180px**다. 이전 카메라의 명목 pitch는
−39.132°다. 실제 영상 7600/0/0과 크게 달라 **이 명령 보정만으로 실제 시야를 설명할 수 없다**.
s1044 01978.jpg는 벽/천장처럼 보이며 회색 영역을 cyan 가림이라고 판단했던 이전 표현은
검증되지 않았다. 과거 raw에는 실제 관절·그리퍼·카메라 pose/sleep 상태가 없다.
따라서 팔 명령 차이는 배제되지만, 실제 카메라 방향·렌더 상태·손의 가림 중 최종 원인은
**미분리**다. 블록의 작은 차이만으로 설명했다고 보고하지 않는다. 시작 위치/seed/freeze도
다르므로 freeze의 인과 효과라고 단정하지 않는다. 카메라 각도는 변경하지 않는다.

실물 출처: `scripts/red_block/physical_state_machine_reference.py:103–111`은 옛
CARRY_POSE(700/2200/780)가 바닥 위를 향해 자율 배송에 부적절하다고 기록하고,
**DELIVERY_CARRY_POSE={1:1500,3:600,4:2200,5:1400}**으로 아래 시야를 유지한다.
`scripts/red_block/pick.py:393–400`은 바닥 비움 probable 확인 뒤 그 자세를 발행한다.
`scripts/red_block/poses.py:12–20`의 별도 observe/carry960/2410/1215와도 구분한다.
S2의 HIGH는 이 실물 delivery 자세와 같지 않다. 이번 요청은 전체 실패 수집이므로
아직 검증하지 않은 실물 carry 자세 이식을 추가하지 않는다.
기하 계산은 [OpenCV fisheye 공식 수식](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html)을 사용한다.

v121은 v120 제어 명령/판정 문턱을 그대로 사용하고 종료 목표만 place까지 확장한다.
`dev_grasp_policy=log_only_v1`은 full DEV admission의 명시 옵션(기본 off)이다.
기존 inhand 제어기는 unknown일 때 `GRASP_INHAND_UNCONFIRMED`를 soft 기록하고 이미
carry로 넘어갔다. 앞선 실행은 pick probe 종료 조건으로 끝났으며 물리 실패 중단이 아니었다.
새 result에는 hold_status와 `dev_light_would_stop` 전체 횟수·시각을 보존한다.
unknown은 성공으로 바꾸지 않고 eval lifted/inside/floor/stable/success를 별도로 기록한다.
`eval_camera_trace=pose_v1`(기본 off)은 capture 뒤 camera cached pose와 body+mount pose,
그리퍼 pose·tree sleep을 **eval_only/camera-pose.jsonl**에만 쓴다. forward/step/제어 입력 없음.
이 기록은 과거 원인을 소급 확정하지 않으며 이번 실행의 불일치 진단용이다.

나머지 옵션은 v120과 동일: v3, v7, setdown_relook=off, grasp_check=pickup_site_v1,
min_wheel_cmd=real_v1, dead_reckoning=v7_diag_v1, stagnation_watch=window120_v1,
alignment_pulse=real_fine_v1, hover_check=real_pregrasp_v1, **idle_robot_contacts=freeze_v1**,
site_check=off, hold_check=inhand_rgb_v1. 원래 자리 전후 비교는 미실행으로 기록한다.
freeze는 S2 단독 DEV에서만 허용하며 S3·짝 운반·본 연구/연구 사전등록은 여전히 오류다.
이번 사용자 승인 full DEV seed 사전 기록만 좁게 추가 허용한다. 과거 결과와 합산하지 않는다.
실제 낙하·그립 이탈·기울기·실행 오류는 중단, 120 SIM초<1cm 정체 감시/1800 SIM초 유한 상한은 유지한다.
보수적 확인·위치 불확실은 기록만 한다. 한 실행 뒤 원인과 반복 여부를 보고하며 추가 seed는 돌리지 않는다.
ENOSPC는 HOST_ERROR이고 partial raw/seed를 보존한다. 모델 호출0, GT는 평가/외부 중단에만 쓴다.

실행 전 시험 `test_s2_full_dev.py`, `test_s2_idle_contacts.py`, `test_s2_inhand.py`:
**24 passed /20.88s**. unknown→carry 연속성, 실패를 성공으로 바꾸지 않는 result,
trace-off 바이트 동일/trace-on 상태 불변, seed·freeze 범위, 기존 off 명령/record bytes를 확인했다.
README·소스 커밋/push 뒤만 agent_lock status null→acquire, ugrp_session 단독 실행한다.
raw `/Users/changmin/projects/ugrp/outputs/s2-realism-<sha8>-s1045-P1-2-place`.
PR #406 DRAFT 유지, 병합 금지. 실행 전 가용 공간 약49GiB.

## v121/s1045 전체 DEV 완료 — B 밖에 놓음

실행 소스 **f0bb26e70ae42210823007c1c617cc4e45a65347**, bundle **zone-s2-realism-v121**.
seed1045 사전 기록/옵션/소스를 커밋·push한 뒤, 잠금 null을 확인하고
`ugrp_session run s2-full-s1045 -- zsh launch_v121.zsh ... place 1045 P1-2`로 1회 실행했다.
PID/PGID19865 nice0, freeze ON, 모델 호출0. 실행 소스352파일을 종료까지 고정했다.

- **lifted=true, inside=false, floor=true, stable=true(2s), success=false**.
  제어기 상태 done/`STAGE_REACHED_UNQUALIFIED`는 명령 경로 완료이며 임무 성공이 아니다.
  마지막 cyan 중심은 **(0.790556, −1.960510, 0.015892)m**로 B 중심(4.6,−2.1) 밖이다.
  정상 내려놓기를 낙하로 분류하지 않았다. 실제 낙하/그립 이탈/기울기 중단, HOST_ERROR 없음.
- 이번 시각 판정은 **probable_held_inhand_rgb**. VIA110/HIGH 각각9/9,
  cyan39099–39110/39012px, mask IoU0.997596, 중심차0.074985px였다.
  이전 세 실행의 unknown을 성공으로 소급 변경하지 않는다. unknown 자체의 계속 진행은
  실행 전 단위 시험으로 확인했고, 이번 새 표본에서는 unknown이 발생하지 않았다.
  원래 자리 비교는 `not_evaluated_inhand_selected`, 전후 비교 면적null, 재집기0.
- **멈췄을 지점 전체:** `ARM_COLLISION_GUARD` **5회**(첫1.40s),
  `POSE_UNCERTAIN` **519회**(첫89.55s). 모두 계속 진행했다.
  result/student_record에 전체 횟수와 50회 간격 이벤트 시각을 보존했다.
  실제 물리 중단0, 시각 확인 정지0, 정체 중단0. `failure=null`은 제어기 예외 없음이지 성공이 아니다.
- **벽시계1359.968446s / total SIM693.95s / wall/SIM1.959750**, check SIM692.65s,
  명령5023, 프레임13794. 기존 제어기 내부 상한900s와 외부 case cap1800s 이전에
  place 시퀀스가 자연 종료했다. 상한을 늘리거나 실행 중 제어를 바꾸지 않았다.
  출력 `/Users/changmin/projects/ugrp/outputs/s2-realism-f0bb26e7-s1045-P1-2-place`.
- freeze 비교는 wall/SIM만: s1042 OFF **2.587649**, s1043 ON **1.467896**,
  s1044 ON **1.603048**, s1045 ON **1.959750**. 서로 다른 seed·probe/full 경로이며
  속도 인과 효과/성공률로 합산하지 않는다. 이번 read-only eval trace 비용도 포함한다.

### 시야 소실 원인 추가 분리 — 실행 후 오프라인

v121의 실제 HIGH camera pitch **−32.687°**, 높이0.187244m/차체 전방0.196704m였다.
기존 명령 보정 pitch−36.592°와 **3.904°**, 높이는 약7.35mm 다르다.
전체 capture에서 cached camera와 body+mount의 차이는 위치 최대2.24e−16m,
회전6.39e−6°로 일치한다. **이번 실행에는 upward camera나 pose cache 불일치 근거가 없다.**
이것을 과거 freeze OFF/ON 인과 판정으로 확장하지 않는다.

실측 HIGH로 이번 블록을 투영하면 **38608px**, 실제 RGB는38980px(첫 carry 프레임)다.
같은 실측 시선을 과거 s1042·1043·1044의 평가용 블록 상대 자세에 공통 적용하면
**7607/0/0px**, 과거 관측은 **7600/0/0px**다([조건부 비교](shared-camera-sensitivity.json)).
따라서 **1.35–1.58mm의 블록 상대 위치 차이만으로 하단 렌즈 경계를 넘어 사라지는 현상**을
공통 시선 가정에서 수치로 재현했다. 팔 명령 변경이나 위를 향한 카메라를 가정할 필요가 없다.
다만 과거 실제 카메라/그리퍼 pose가 저장되지 않았으므로, 이것은 강한 기하적 설명이지
과거 프레임의 카메라 각도를 실측한 결과가 아니다. 투영은 손/장면 가림을 모델링하지 않는다.
카메라 각도·팔 자세·시각 임계값은 이 분석 후에도 수정하지 않았다.

### B 미도달과 반복 주행 — 조사 후 추가 실행 중단

[명령·추정 위치·GT 대조](s1045-navigation.json): carry 진입 때 위치 오차 **0.458m**,
100s **1.152m**, 최종 **3.839m**. 마지막 보고 추정 **(4.422789,−2.089974)m**,
같은 추정 시각의 실제 차체 **(0.586001,−1.954691)m**였다.
300s에는 실제 오차1.235m인데 보고 std_xy는0.0106m로 과신했다.
시각 fix 시각이 갱신됐다는 사실도 정확한 위치의 증거가 아니었다.
B 밖 배치의 직접 관찰은 **잘못된 자기 위치로 목적지에 도착했다고 판단한 것**이다.
명령 이동 모델·시각 보정·보정 외재값 중 각각의 인과 기여는 이 1회로 분리되지 않았다.

운반 구간 발행 펄스994회 중 옆 이동672회, 연속 옆 이동 부호 반전538회.
`65/0.65s` 펄스 실제 이동 **151.2–160.7mm, 중앙153.3mm**로 경로점 pop 허용35mm의
4.38배, 체크포인트 허용30mm의5.11배다. 이 긴 펄스/작은 허용치 부조화는
s1039 집기 정렬에서 본 계열이며, 당시 수정은 align에만 적용돼 carry에는 남아 있다.
단, 반복 횟수 전체를 이 요인 하나로 귀속하지 않는다(위치 추정 오차도 함께 존재).

실물 표준 동작은 `scripts/red_block/place.py:144–185`에서 운반 중 회전/전진을
정지 후 재측정하고 남은 거리에 따라 **35, 0.60→0.42→0.18→0.10s**로 줄인다.
`sim/real_stack_adapter.py:993–1002`도 운반용 wrist1400 복귀→drive→stop→관측 자세 복원을 따른다.
현재 S2의 모든 옆 이동을65/0.65로 바꾸는 경로는 이 배송용 거리별 조절과 다르다.
참고한 고전/후속 문헌:
[Fox et al. 1999 MCL, 운동 모델과 관측 모델 분리](https://www.cs.cmu.edu/~thrun/papers/fox.aaai99.pdf),
[Thrun et al. 2001 mixture-MCL, 일반 PF의 실패와 복구](https://publications.ri.cmu.edu/robust-monte-carlo-localization-for-mobile-robots),
[Akai 2022 Reliable MCL, 신뢰도 평가·실패 감지·재위치 추정](https://arxiv.org/abs/2205.04769).
후속 두 문헌은 공식 초록 범위까지 확인했으며 코드 이식/재현 완료로 주장하지 않는다.
작은 공분산이나 새 fix만으로 위치가 맞다고 판정하지 않는 문제를 다음 조사 항목으로 남긴다.
사용자 지시대로 이번 **full1회 후 중단**, 추가 seed/펄스 조정/재실행은 하지 않았다.

### 보존·TensorBoard·정리

[완료 결과](completed-v121.json), [검증 기록](full-delivery-verification.json).
실행 source closure352파일, raw artifact manifest, 모든 RGB sha256을 대조했고,
독립 궤적 채점의 lifted/inside/floor/stable/success가 원래 result와 일치한다.
4배속 영상(172.45s,3449frames,640×480,20fps):
`/Users/changmin/projects/ugrp/outputs/s2-realism-f0bb26e7-analysis/views/s1045-full/execution.mp4`,
sha256 `241adc738fa3d932530a4d27c9f9eb7bb254de74ac5b611f2e3585eb9d238c4d`.
ffprobe·전체 decode 통과, TensorBoard video id `23a311153dfa35b93ce4` 등록.

[TensorBoard 수치 보기](http://127.0.0.1:6006/?runFilter=%5E1007-s2-realism-full-v121-verified%2F#timeseries),
새 snapshot `1007-s2-realism-full-v121-verified`: **실행1+과거 오프라인 비교3**, 새 실행4회가 아니다.
**31 scalar**를 source→event→실제6006 API로 대조하고 HParams 필드를 확인했다.
첫 export는 대문자 scalar tag로 full1건이 거부돼 offline3건만 변환됐다. 부분 snapshot
`1007-s2-realism-full-v121`은 보존하고, 태그를 소문자로 고친 새 완전 snapshot만 기본 보기 키에 등록했다.
raw는 수정하지 않았다. 기존 TB PID52016/logdir 유지, 공유 view에는 자기 새 키만 추가했다.
사용자 지시대로 수치만 비교하고 브라우저는 열지 않았다.

agent_lock 해제(null), ugrp_session stopped, PGID19865 잔여0, 일회 launchd unload 확인.
실행 후 변경은 기록뿐이며 제어/물리는 f0bb26e7 그대로다. 실행 전 관련24시험 통과;
원격 CI run37485044909는 preflight가 **2분 시간 초과로 cancelled**, 후속 시험이 skip돼
전체 CI 통과를 주장하지 않는다. PR #406 DRAFT·미병합 유지. raw 로컬 보존은 원격 백업이 아니다.

## v122 — v7 펄스 보정과 전체 DEV 1회 (2026-10-07, 실행 전 등록)

사용자 지시: s1042–1045를 탐색 자료로만 재분석하고 **새 seed1046 / P1-2 / place / r3→B / door_1**, `zone-s2-realism-v122` (workflow7.15.0)를 전체 DEV 한 번 실행한다. 이 문서와 [등록](registration-v122.json)은 실행 전에 커밋한다. main+열린 PR14개와 원본 출력에서 seed 및 번호를 [확인](reservation-scan-v122.json)했다. 기존 seed1029–1031과 소비된1042–1045는 사용하지 않는다. 이번 실행 뒤 추가 SIM은 없다. 같은 원인의 기존 실패s1045와 반복되면 원인을 기록하고 중단한다.

조건: camera v3, drive v7, `setdown_relook=off`, `grasp_check=pickup_site_v1`(명목 옵션; 실제 검증은 `hold_check=inhand_rgb_v1`, site 비교 없음), `min_wheel_cmd=real_v1`, `dead_reckoning=v7_diag_v1`(새 옵션 ON에서는 superseded), `pulse_motion_model=v7_pulse_cal_v1`, `alignment_pulse=real_fine_v1`, `hover_check=real_pregrasp_v1`, `idle_robot_contacts=freeze_v1`, `dev_grasp_policy=log_only_v1`, `eval_camera_trace=pose_v1`, `stagnation_watch=window120_v1`. freeze는 사용자 승인 **S2 단독 DEV**에만 사용한다. S3·짝 운반·본 연구·연구 사전 등록에 금지한다. 이전 조건과 성공률을 합산하지 않고 wall/SIM만 별도 비교한다.

### 오프라인 원인과 보정 범위

실제 v121 Runtime 생성과 PF 경로 감사 결과, 1.56 공통 이득이 활성인 것은 아니었다. `v7_diag_v1` gain diag=[1.403796,0.415429,2.336931], 축별 tau=[0.318027,0.085276,0.021913]가 양 하중 상태에 적용된다. 문제는 이 보정이 양의 펄스 각1회뿐이고 loaded/reverse가 미확증인 점이다. [실제 경로·분리검사](v122-model-audit.json)에 저장했다.

아래는 저장된 20Hz eval 궤적을 펄스 시작 body 좌표로 바꾼 값이다. 명령 종료 후 최대0.20초(다음 펄스 전까지)의 이동을 포함한다. GT는 이 완료 기록의 보정·채점에만 사용했다. 요청된35–40 중36–40 자료는 **0건**이며, 실제 coarse lateral65도 빠짐없이 별도 기재한다. 개별 raw는 수정하지 않았다. 원본 해시·5/50/95분위와 전체 분포는 [pulse-groups](v122-pulse-groups.json), 개별 펄스는 `/Users/changmin/projects/ugrp/outputs/s2-pulse-cal-20261007/offline/pulses.jsonl`.

| 하중 | 축·출력·초 | n | Δ전진 중앙(cm) | Δ옆 중앙(cm) | Δyaw 중앙(°) |
|---|---|---:|---:|---:|---:|
| 0 | forward -35 / 0.06 | 2 | -0.705 | 0.033 | 0.143 |
| 0 | forward 35 / 0.06 | 236 | 0.760 | 0.005 | -0.004 |
| 0 | forward 35 / 0.10 | 115 | 1.285 | -0.008 | -0.029 |
| 0 | left -35 / 0.06 | 24 | 0.013 | -0.707 | 0.095 |
| 0 | left -65 / 0.65 | 110 | 0.065 | -16.681 | 0.568 |
| 0 | left 35 / 0.06 | 18 | 0.026 | 0.689 | -0.100 |
| 0 | left 65 / 0.65 | 110 | 0.067 | 16.794 | -0.539 |
| 0 | turn -35 / 0.10 | 1 | -0.030 | -0.181 | -5.935 |
| 0 | turn 35 / 0.10 | 2 | -0.024 | -0.251 | 5.688 |
| 1 | forward -35 / 0.10 | 88 | -1.290 | 0.006 | -0.039 |
| 1 | forward 35 / 0.10 | 196 | 1.296 | -0.001 | -0.016 |
| 1 | left -65 / 0.65 | 339 | 0.059 | -16.548 | 1.523 |
| 1 | left 65 / 0.65 | 333 | 0.080 | 16.552 | -1.509 |
| 1 | turn -35 / 0.10 | 20 | 0.017 | 0.080 | -4.867 |
| 1 | turn 35 / 0.10 | 18 | -0.020 | -0.052 | 5.049 |

0/1 하중은 자기 집게·팔 명령으로 얻은 `LoadState` 분류이며 실제 접촉을 제어기에 전달하지 않는다. s1045 옆 펄스672회, 방향 반전538회 중 **527회**는 같은 경유점/새 fix 없음에서 오차 부호가 뒤집혔고, **525회**는 그때 실제 이동이 초기 남은 오차보다 컸다. 실제 during 이동 중앙15.33cm, coast 포함16.55cm 대 경유점 허용3.5cm. 운반 회전35/0.10초는 약4.9° 대 기존허용1.43°. 시각 오보정과 모델 오차가 공존하므로 3.839m 전체를 한 원인으로 단정하지 않는다.

표준 방법 조사: [Borenstein & Feng UMBmark (1994 report, §§2–3,6)](https://websites.umich.edu/~ykoren/uploads/Umbmark.pdf)는 양방향 측정으로 체계 오차와 산포를 분리한다. 원 논문은 차동구동/엔코더이므로 메카넘에 휠직경 식을 이식하지 않았다. 양·음 방향과 하중을 분리해 자기 명령→정지 응답을 batch 식별했다. 실제 UMBmark 사각 주행은 수행하지 않았다.

[Thrun, Burgard & Fox (2005), ch5 §§5.3–5.4](https://cs.pomona.edu/~ajc/other/Thrun%20et%20al_2005_Probabilistic%20robotics.pdf)와 [저자 페이지](https://robots.stanford.edu/probabilistic-robotics/): 명령과 실제 운동을 구분하고 운동량에 따른 분산을 둔다. 책의 비홀로노믹 v/ω 식은 메카넘을 제외하므로, [Nav2 공식 OmniMotionModel](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/motion_model/omni_motion_model.cpp)과 같이 옆 이동도 분리한다. 여기서는 펄스별 dx/dy/dyaw 평균곡선 최소제곱, Gaussian 잔차 분산, `variance_j=alpha_j,trans*(dx²+dy²)+alpha_j,rot*dyaw²` 비음수 최소제곱을 사용했다. 원 AMCL 구현/엔코더 오도메트리를 재현했다는 주장은 아니다. 고정 α·분산·곡선은 [보정값](../../configs/s2_motion_v7_pulse_cal_v1.json)에 있다.

실물 근거: `scripts/masterpi_control.py`는 비영 출력35 미만을 거부한다. `scripts/red_block/place.py:144–185`는 35로 멀 때 긴 펄스, 가까울 때0.10/0.12초 후 정지·재관측한다. `physical_state_machine_reference.py`의35/60ms +120ms 관측과 기존 FinePulsePort를 재사용한다. 원 실물 미세 정렬이 메카넘 옆 이동이었다고 주장하지 않는다. [Fox et al. 1997](https://publications.ri.cmu.edu/storage/publications/pub_files/pub1/fox_dieter_1997_1/fox_dieter_1997_1.pdf)의 유한 후보 운동 예측을 참고해, 기존 A* 경유점에 대해 예상 오차를 줄이는 펄스 하나를 고른다. 전체 DWA 충돌 회피 구현은 아니다.

새 옵션(기본off)은 **S2 인스턴스**의 PF 예측·navigation만 같은 고정 응답표로 연결한다. coarse65/0.65초는 남은 옆 거리가 예상 이동+3.5cm보다 클 때만 허용하고, 가까우면35/60ms(~7mm)로 바꾼다. 위치 허용3cm/경유점3.5cm는 유지하며, 회전허용은 최소 회전의 절반 이상인0.06rad(3.44°)로 둔다. 다음 명령은 정지 꼬리와160ms 추정 지연을 포함한 fresh pose를 기다린다. `sim/camera_robot_port.py`, 다른 제어기, 카메라/팔 자세는 변경하지 않는다. 옵션off는 기존 명령·record 바이트 일치 시험으로 고정한다.

학습/보류 분할: unloaded는1042/43/45로 fit,1044 보류; loaded는1045 t<400초 fit, 이후 보류. 이미 본 자료의 사후 분할이므로 독립 확증이 아니다. loaded 양전진 endpoint x RMSE 2.157→0.543mm, loaded 좌우 yaw RMSE 1.13/1.12→0.319/0.315°. 일부 희소 unloaded 항목은 개선되지 않았다(예: +turn yaw 0.111→0.637°). loaded fine strafe는 **0개 관측**이므로 unloaded fine에 loaded/unloaded coarse 비율을 적용한 미확증 전이이며 분산 하한5mm/1°를 둔다. reverse는 양방향 대칭 전이 후 보류 자료로 따로 평가한다. 20Hz 궤적의10ms 보간은 새 고속 계측이 아니며, 정지 후100/140ms 이후의 꼬리는 미식별이다.

### CI와 실행 경계

[CI run37485044909](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37485044909)의 preflight fetch145.086초가2분 제한을 초과했다. 뒤의 경로시험10개는0.211초로 통과했고 full_suite=true였지만 job은 시간 제한 cancelled였다. [증거](v122-ci-timeout.json). [actions/checkout v4 공식 설정](https://github.com/actions/checkout/blob/v4/action.yml)에 따라 preflight에만 `filter: blob:none`을 추가해 과거 blob 전송을 줄이고, merge-base 비교용 전체 commit 이력은 유지하며 상한을5분으로 변경했다.

실행은 시험 통과→source/seed 커밋·push→lock null 확인→agent_lock acquire→ugrp_session 순서다. freezeON/dev_light에서는 unknown·위치 불확실·보수적 가드를 기록만 한다. 낙하/이탈/기울기/실행 오류·120SIM초1cm미만 정체 및 유한 cap에서 중단한다. ENOSPC는 HOST_ERROR로 기록하고 부분raw를 보존한다. 모델 호출0. PR406은 DRAFT 유지·병합 금지. 새 seed 결과로 보정값을 다시 맞추거나 이번 실행을 재사용하지 않는다.

실행 전 검증: 바뀐 범위3개 시험 파일에서 **19 passed, 280 subtests passed / 29.48초**. 기본off 명령·record 바이트 일치, 실제 PF 경로의 load 양 상태, 펄스 정지 꼬리/도착 해상도, fresh estimate 대기, 신규 seed/번들·freeze 제한, 실패 결과 저장 및 CI gate를 확인했다. [검증 기록](v122-local-verification.json). 여유48.15GiB, 사전 확인 잠금null.

### v122 완료: 양자화 진동 감소, B 배치 실패 — 추가 실행 중단

실행 소스 **`e619ee571ea6d03ad33f92793e91492d968f4d30`**, s1046/P1-2/full 1회. source/seed 등록 커밋·push 후 lock acquire, `ugrp_session run s2-pulse-s1046`로 실행했다(실행 프로세스 모두 nice0). **lifted=true, inside=false, floor=true, stable=true**, 독립 기하 판정도 동일하다. 제어기는 done/`STAGE_REACHED_UNQUALIFIED`, raw `failure=null`이지만 물리 임무 성공은 **false**다. cyan 최종 `[2.079624,0.535995,0.015892]`m로 B 중심`[4.6,-2.1]`에 도착하지 않았다. in-hand=`probable_held_inhand_rgb`, 원래 자리 비교는 선택하지 않아 전후 면적null, 다시 집기0, 모델 호출0.

| 지표 | s1045 (기존) | s1046 (새 DEV) |
|---|---:|---:|
| 운반 옆 펄스 / 방향 반전 | 672 / 538 | 143 / **3** |
| 마지막 자기 위치 오차 (평가 전용) | 3.839m | **3.346m** |
| 마지막 방향 오차 (평가 전용) | 별도 과거 기록 | **95.74°** |
| POSE_UNCERTAIN 기록 | 519 | **278** |
| ARM_COLLISION_GUARD 기록 | 5 | **7** |
| wall / SIM / wall÷SIM | 1359.97 / 693.95 / 1.95975 | **618.427 / 329.25 / 1.87829** |

이 표는 서로 다른 DEV seed/명령 조건의 관측값이며 성공률이나 인과 효과를 합산하지 않는다. freeze 이전 s1042 OFF=2.58765, 이후 s1043=1.46790, s1044=1.60305, s1045=1.95975, s1046=1.87829 wall/SIM만 별도 기록한다(단계·seed·모델이 달라 freeze 자체의 가속률은 아님).

남은 원인은 [새 seed 실패 분석](s1046-failure-analysis.json)과 [새 펄스 분포](s1046-navigation.json)에 구분했다. (1) 문 서쪽의 하중 +전진151회는 예측보다 평균1.250mm 짧았다. (2) **미확증 하중 fine 음의 옆 이동**70회는 yaw 평균 잔차+0.5205°/회, RMSE0.6974°로 전이가 맞지 않았다. (3) 연속 전진의 정지 간격도 보정 자료0.10초(n154)→새 실행0.30초(n124)로 달랐고 이동 중앙1.306→1.166cm였다. 이 초기 구동 상태/정지 간격 전이를 충분히 검증하지 못했다. 간격만의 인과 효과를 증명한 것은 아니다([간격 분석](s1046-stop-intervals.json)). 이 새 seed로 상수를 다시 맞추지 않았다.

시각 위치 보정의 마지막 시각은32.85초인데, 문 동쪽 도착 선언209.60초에도 갱신되지 않았다. 그때 추정`[2.73785,0.02448]` 대 실제`[1.97873,-0.11034]`, 오차0.771m였다. 이후217.6/218.55/219.5초 옆 펄스의 실제 yaw 변화는16.21/33.81/29.25°(예측 약1.50°)이고, 이어진 coarse 음의 옆 펄스15회 전체 이동 중앙은0.625mm였다. 문/분리벽 부근에서 차체가 막혀 회전·미끄러진 정황이며 **벽 접촉 impulse는 저장하지 않아 접촉 원인은 기하 추론**이다. 명령만으로 실제 이동·막힘을 알 수 없다는 표준 운동 모델의 한계와, stale/과신한 위치 추정이 남아 있다. 정지 후 관측을 기다린 것이 실제 유효한 fix를 보장하지 않는다. 보정표만으로 B 배치 문제를 해결했다고 보고하지 않는다.

dev_light에 따라 보수적 정지 지점은 위 두 종류를 기록만 했고, 낙하/집게 이탈/기울기/정체/실행 오류 중단은 없었다. B 배치·위치 추정 실패가 반복되어 **이번 1회로 종료**, 추가 시뮬레이션·seed 재사용·후속 재보정 없음. source closure 전체, raw manifest, RGB6500개 해시와 독립 기하 판정을 검증했다([완료 기록](completed-v122.json)). 원본 result/trace는 수정하지 않았다.

출력: `/Users/changmin/projects/ugrp/outputs/s2-realism-e619ee57-s1046-P1-2-place`.
4배속 MP4: `/Users/changmin/projects/ugrp/outputs/s2-realism-e619ee57-analysis/views/s1046-full/execution.mp4` (640×480,20fps,81.25초, SHA256`34a95ea928fc5872017886e0184d51d4df22b5d33b944654b39d178236b066da`). 전체 decode 및 등록된 원본 HTTP206 바이트 대조 통과.
TensorBoard 새 snapshot `1007-s2-realism-pulse-v122`: 완료 실행1+오프라인 보정감사1, **26개 scalar 원본/event/live API 일치**, 기존 viewer PID52016/logdir 유지. [대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-realism-pulse-v122%2F#timeseries), [영상](http://127.0.0.1:6007/video/286cb3ea73aabecc1c6a), [검증](pulse-delivery-verification.json). 사용자 요청대로 숫자만 대조하고 브라우저는 열지 않았다. 공유 view에는 자기 키만 추가했다.

CI preflight는 [새 실행37493154746](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37493154746)에서 **24초 success**로 시간초과 수정 확인. 전체 CI는 기록 시 진행 중이며 미완료를 통과로 표현하지 않는다([조회](v122-ci-readback.json)). 세션 stopped, 소유PID32708/32712/32722/32728 모두 종료, one-shot launchd 해제, **agent_lock=null**. PR406 DRAFT 유지·병합 금지.

## v123 — s1045/1046 visual-fix 감사와 S2 전용 관측 격리 (2026-10-07)

**물리 실행 전 원인 분리.** `last_fix_t`는 합격 영수증이지 모든 시각 가중치 갱신 횟수가 아니다.
기존 `zone_final_pair_scan`/`zone_pair_highpose_partial_fix`는 불합격 영수증을 되돌려도
`vision_pf.apply_scan`의 가중치·분산 변화는 유지한다. 따라서 s1046이 32.85초 뒤 “명령만으로”
갔다는 표현은 엄밀하지 않다. 문 앞/뒤 추정 체크포인트(162.65/209.6 s)까지 새 합격 fix는 0이지만
부적합 벽 관측은 계속 PF에 들어갔다. 이후에는 새 fix가 있으며 마지막은 295.95 s다.

| 기록 | HIGH 운반 구간 | 기록된 scan gate | 합격 fix / 초 | inlier 중앙 / support 중앙 |
|---|---|---:|---:|---:|
| 구 카메라 s1022 | 84.6–106.7, 165.7–189, 248–288.4, 347.5–349.2 s | 0 / 0 / 0 / 0 | 모두 0 | 관측 없음 |
| v3 s1045 | 87.95–672.45 s | 10,977 | 313 / 0.5355 Hz | 0.01136 / 0 |
| v3 s1046 | 67.5–307.85 s | 4,699 | 104 / 0.4327 Hz | 0 / 0 |

구 카메라 s1022는 든 cyan으로 HIGH 시야가 가려졌고, 내려놓고 다시 본 구간에서 fix를 얻었다
(다음 HIGH 진입 직전 영수증 134.35/219.85/314.45 s). 구 구동 결과는 폐기된 물리 baseline이며
여기서는 **fix 빈도·재관측 동작 비교에만** 쓴다. 성공률을 합산하지 않는다.
현재 `setdown_relook=off`는 그대로 유지한다. PR #405의 자기 지도/pose graph는 별도 오프라인 작업으로,
이번 S2 공개 지도 PF 수정에 복사하거나 그 결과를 합산하지 않는다.

- 관측은 벽–바닥 **96개 열 경계**뿐이다. 바닥 무늬·표식·학습 모델은 위치 랜드마크로 쓰지 않는다.
  s1046 67.5–209.6 s에는 gate 2,734건, 합격 0. 67.5–162.65 s의 inlier 최댓값 0.538 < 0.66,
  support 최댓값 0 < 0.10. 전체 HIGH에서는 fraction/support/rank 거절 4,583/4,595/3,563건
  (중복 원인). 영상 도착 6,496, worker 5,523, 거절 frame 0; 미안정 구간 973회는 별도다.
- **v3 변환은 적용됐다.** `camera_v3_derivation`의 rigid composition과 실제 column-model closure를 확인했다.
  하지만 원래 짝 HIGH 보정 자세를 상속한 `RIGID_COMPOSITION_UNQUALIFIED`다. HIGH 예측 pitch −36.59168°,
  s1046 실제 평가 카메라 약 −32.7°. 160 s에 예측 카메라 높이 0.179896 m, 평가 높이 0.187288 m.
  관측 벽 경계와 공개 지도 투영의 중앙 절대 잔차는 **52.315 px**; 평가 카메라로만 투영하면 **0.550 px**,
  inlier 0 → 0.9783. 224/290/296 s에도 51.52/52.76/53.41 px → 0.462/0.559/0.613 px.
  이 GT 카메라 대입은 **원인 채점 전용**이며 제어기 보정값으로 저장·전달하지 않는다.
- 다른 구간은 시야/검출 문제도 있다. s1046 68 s 검출 86열, 관측 중앙 row 105인데 실제 기하에서 벽 바닥은
  row −105.90(위쪽 밖). 이때 바닥 구역의 색/음영 경계가 벽 후보로 검출된다. 평가 카메라로 바꿔도
  잔차 211.54 px, inlier 0이다. 160 s처럼 실제 벽이 보이는 구간과 구분한다. v3 각도만의 영향과
  v7/하중 자세 영향을 분리한 물리 ablation은 하지 않았다. 카메라 장착 각도를 바꾸지 않는다.

### 표준 방법·실물 근거 (직접 확인한 출처)

1. [robot_localization EKF 공개 코드](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/ros2/src/ekf.cpp)
   `correct`는 innovation 검사를 통과한 경우에만 상태·공분산을 갱신한다. 이를 PF에 필요한 범위로 적용:
   이미 등록된 잔차/support/rank 기준을 **측정 가중치 갱신 앞**에 놓는다. Mahalanobis EKF 자체를 복사하거나
   기존 문턱을 낮추지 않는다. 희박한 prior에서 회복을 늦출 수 있으므로 S2 loaded HIGH에만 한정한다.
2. [Maimone·Cheng·Matthies, JFR 2007 원문](https://www-robotics.jpl.nasa.gov/media/documents/rob-06-0081.R4.pdf),
   [JPL Curiosity 설명](https://robotics.jpl.nasa.gov/what-we-do/flight-projects/mars-science-laboratory/surface-system-software-and-rover-navigation/):
   주행 전후 지형 특징을 비교하는 VO로 명령과 실제 영상 이동의 불일치를 감지한다. 여기에는 stereo/IMU/encoder를
   추가하지 않고 단안 RGB의 **정체 의심**만 적용한다. 절대 위치·미터 이동량·slip 비율을 주장하지 않는다.
3. [CMU Lemus 2013](https://publications.ri.cmu.edu/slip-control-during-slope-descent-for-a-rover-with-plowing-capability):
   단안 optical flow를 쓰는 slip 추정 연구. 성능 수치를 S2로 승계하지 않는다.
4. [OpenCV LK 설명](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html),
   [공식 forward/backward 예제](https://raw.githubusercontent.com/opencv/opencv/4.x/samples/python/lk_track.py):
   Shi–Tomasi 특징 → pyramidal LK → 역추적 오차 <1 px. RGB에서 이미지 테두리·가까운 하단·고채도 화물을 제외하고
   6개 이상 추적점/2개 이상 공간 셀을 요구한다. 부족하면 `unknown_texture`다.
5. [OpenCV pinhole/extrinsic](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html):
   외부 보정 오차와 영상 잔차를 분리한다. 실물 근거는 `scripts/red_block/place.py:8,144–185`의 정지 후
   새 영상 측정 및 `sim/real_stack_adapter.py:993–1002`의 운반 자세 복원→펄스→정지→관측 자세 복원이다.
   이 실물 코드는 현재 S2 HIGH 카메라의 절대 pose 정확도나 optical-flow 막힘 검출을 보증하지 않는다.

### 새 옵션과 실행 전 등록

`visual_update=accepted_scan_v1`, `visual_stall=lk_pulse_v1`을 새 S2 wrapper에 추가한다. 둘 다 기본 off이고,
공용 `sim/camera_robot_port.py`, 기존 제어기/번들, 카메라 각도·보정·measurement σ는 바꾸지 않는다.
첫 옵션은 loaded HIGH 불합격 관측을 predict-only로 돌리고, 둘째는 자기 명령의 고정 펄스 모델로
순이동 5 cm 또는 yaw 0.05 rad가 쌓인 정지 영상 쌍을 비교한다. 순 SE(2)를 합성해 방향 반전의
경로 길이를 이동으로 세지 않는다. LK 중앙 ≤1 px·p90 ≤2 px이면 `VISUAL_STALL_SUSPECTED`를 기록한다.
DEV에서는 이것도 기록만 하며, 위치 보정·이동 0 강제·성공 판정에 넣지 않는다.
이 수치는 탐색 s1045/1046의 한계(1 cm 펄스가 <1 px일 수 있음)를 보고 정한 DEV 값이며 새 seed로 검증한다.
**이 수정은 거절 관측의 오염을 막는 후보이지, 잘못된 HIGH 외부 보정을 복구한 방법이 아니다.**
관측 불일치가 계속되면 새 물리 실행을 반복하지 않고 보정/관측 획득이 남은 문제로 보고한다.

- 예약: main 및 열린 PR 15개 브랜치의 최대 v122 다음 **zone-s2-realism-v123 / workflow 7.16.0**.
  [reservation-scan-v123.json](reservation-scan-v123.json)에 SHA·번호·seed 검사, 기존 번들 불변.
- **새 seed1047 / r3 / P1-2 / B / door_1 / place 1회**, source를 커밋·push하고 이 등록을 고정한 뒤 실행.
  탐색 자료 s1042–1046과 분리하며 seed 재사용·추가 진단 SIM 없음. 실패하더라도 이 1회 뒤 종료한다.
- freeze ON, S2 solo DEV만. S3/짝/본 연구/본 연구 사전등록에서 오류. 이전 결과와 합산하지 않고 wall/SIM만 비교.
  `dev_light`, unknown/불확실성/정체 의심은 would-stop 기록. 실제 낙하/이탈/기울기/실행 오류,
  eval 외부 120 s/1 cm 정체 및 유한 상한은 기존 hard stop. ENOSPC는 HOST_ERROR로 raw 보존.
- agent_lock acquire/release, `ugrp_session`, 낮추지 않은 우선순위, 한 번에 하나.
  PR #406 DRAFT 유지·병합 금지. 옵션은 registration·bundle·result에 모두 보존한다.

실행 전 검증: 관련 3파일 **16 passed**. 기본/명시적 off 명령·record bytes 일치, 실제 PF의 거절 scan이
무관측 예측과 동일하고 합격 scan은 정상 갱신하는 시험, 영상/명령 window·옵션·seed/S2 입장 시험 통과.
s1046 전체 자기 입력/명령 고정 재생에서 off 위치 **6,500개 모두 차이 0**. on은 HIGH 후보 4,705개를
모두 차단하고 새 fix 0; 종료 평가 위치 오차 3.345608 → 3.702346 m.
이는 과거 명령을 그대로 쓴 재생으로, 위치 개선을 입증하지 못했다. 새 제어 명령으로 닫힌 루프를 돌린 결과와 구분한다.
RGB window 재생: s1045 757개(unknown743/changed14/정체0), s1046 134개(unknown86/changed45/정체3).
s1046 정체 의심 221.4–222.15, 222.35–223.1, 267.2–269.55 s의 평가 이동은 0.108/0.070/1.303 mm,
yaw 0.015/−0.026/0.146°. 이 채점값은 검출 후에만 결합했다. 무늬 부족으로 검출하지 못한 구간은 숨기지 않는다.
근거: [gate 감사](v123-gates-audit.json), [카메라 투영](v123-geometry-audit.json),
[flow 감사](v123-flow-summary.json), [고정 입력 재생](v123-replay-summary.json), [시험](v123-local-verification.json).

### v123 s1047 전체 DEV 결과 — B 밖 내려놓기, 추가 실행 중단

실행 SHA **`1a2dbf5e306732163a5019a1d52589e0ce3b2e22`**, 번들 **zone-s2-realism-v123**.
`lifted=true / inside=false / floor=true / stable=true / success=false`, 상태 `STAGE_REACHED_UNQUALIFIED`,
제어기 `done`, 실행 오류 `failure=null`. 이것은 정상 종료한 **임무 실패**다. 짐 낙하·집게 이탈·기울기·
120초 정체 중단은 없었다. r3가 문을 통과한 뒤 cyan 중심 (3.999989, −2.277317, 0.015892)m에
내려놓았다. B의 x 범위 4.3–4.9m에 못 미쳤다. GT는 종료 후 독립 기하 채점에만 사용했다.

- 최종 추정 (4.379715, −2.081092)m, 실제 (3.796074, −2.289609)m: **0.619772m 오차**.
  s1046의 3.345608m보다 작지만 seed/제어 궤적이 달라 옵션만의 인과 효과로 단정하지 않는다.
- 마지막 fix **34.45s**, HIGH 후보 **3,048건 모두 거절**, carry fix **0**. 최종 추정 시각 256.14s의
  fix age는 **221.69s**. 거절 관측은 이제 HIGH PF 가중치에 넣지 않지만 카메라 외부 보정·거짓 경계
  문제가 남았고 명령 기반 오차를 보정하지 못했다. 정체가 아니라 **B까지의 위치 오차**로 실패했다.
- would-stop: `ARM_COLLISION_GUARD=7`, `POSE_UNCERTAIN=348`; 모두 기록 후 계속했다.
  flow window 103개: `changed_view=26`, `unknown_texture=77`, 정체 의심 0.
  이는 정체가 없었다는 완전한 검출 증명이 아니다. 특징 부족 구간 74.8%는 판정 불가다.
- 집기 확인 `probable_held_inhand_rgb`, 재집기 0. pickup-site before/after 면적은
  `not_evaluated_inhand_selected`/null이며 unknown을 성공으로 바꾸지 않았다. 모델 호출 **0**.
- **wall 410.407985s / SIM 259.30s = 1.582754 wall/SIM**, 명령 3,679, own RGB 5,100장.
  freeze OFF s1042 **2.587649**, ON s1046 **1.878291**, ON s1047 **1.582754**.
  seed/단계/코드가 달라 wall/SIM 참고 비교만 하며 결과를 합산하거나 가속 인과 효과를 주장하지 않는다.
- 원본: `/Users/changmin/projects/ugrp/outputs/s2-realism-1a2dbf5e-s1047-P1-2-place`.
  [전체 결과](completed-v123.json), [위치](s1047-navigation.json), [체크포인트 채점](s1047-checkpoint-evaluation.json).
  source closure **362파일**, raw manifest, RGB 전체 SHA와 독립 기하 판정 일치. 원본 보존.
- 4배속 영상: `/Users/changmin/projects/ugrp/outputs/s2-realism-1a2dbf5e-analysis/views/s1047-full/execution.mp4`
  (640×480, 20fps, 63.75s, sha256 `4ce34a1ae8cc2f43eb06f25c7e15659895a8a296f59d651f8bfcd5770ad246aa`).
  [TensorBoard](http://127.0.0.1:6006/) snapshot `1007-s2-realism-visual-v123`: full 1건/오프라인 감사 1건,
  **29개 scalar** 원본=event=API 확인. 사용자 요청대로 수치만 대조하고 브라우저는 열지 않았다.
  [검증](visual-delivery-verification.json), [영상 등록 확인](v123-media-readback.json).
- `ugrp_session` stopped, 자체 PID 41828/41832/41842/41848 종료, 일회성 launchd 항목 제거,
  잠금 **null** 확인. 다른 세션/TensorBoard 서버는 변경하지 않았다. **추가 SIM 없음.**

남은 문제는 HIGH 자세별 카메라 외부 보정의 실물 가능한 측정과 실제 벽 관측의 획득/식별이다.
카메라 장착 각도·σ·gate 문턱을 임의 조정하지 않았으며, 기본 옵션을 켜거나 성공 cohort로 승격하지 않는다.

### CI 실패 분리와 시험 설정 수정 (실행 종료 후)

실행 소스 CI preflight는 통과했다. 전체 CI에서는 offline shard1의 MuJoCo 미설치/새 S2 workflow
시험 샘플 누락, shard3의 Mac/Linux corner projection 차이(약 6×10⁻¹⁴ px)로 실패했다.
생산 제어 코드는 바꾸지 않았다. MuJoCo binding 시험은 [pytest 공식 방식](https://docs.pytest.org/en/stable/how-to/skipping.html#skipping-on-a-missing-import-dependency)으로
해당 의존성이 없을 때만 skip하고, 의존성을 설치하는 Ubuntu simulation CI에도 명시적으로 배치했다.
S2 보존 버전 15개의 계획 입력을 추가했고, corner float 두 필드만 [NumPy assert_allclose](https://numpy.org/doc/stable/reference/generated/numpy.testing.assert_allclose.html)
`rtol=0, atol=1e-10 px`로 대조한다. lens coverage·정수 bbox·나머지 필드는 exact 유지한다.
변경된 3시험 파일 **40 passed**, 의도적 MuJoCo 부재 fixture **1 skipped**, CI YAML 구문·배치 검증 통과.
실제 시뮬레이션 0, 실행 source closure **362파일은 그대로**다. 원격 재실행 결과는 아직 미확인으로 남긴다.
[CI 원인과 로컬 검증](v123-ci-diagnosis.json).
