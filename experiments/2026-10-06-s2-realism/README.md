# S2 현실성 재검증 — 실행 전 등록 (2026-10-06)

**최신 작업(s2v22, 2026-10-07):** s1051 오프라인 하중 운동·벽 높이 비교를 완료했다. 벽 근접 큰 옆 펄스6회가 하중 이동 오차의95.84%를 차지한다. 새 하중 보정의 국소 예측이 악화했고 벽 상단은 전부 시야 밖이어서 **사전 기준 미달·새 full DEV 없음**. 기본off 옵션·14시험·4조건 재생·7뷰41scalar를 기록했다. [결과](#s2v22-결과--ab-개별-기준-미달-full-미실행). PR406 DRAFT·병합 금지.

**이전 작업(s2v17, 2026-10-07):** 사용자는 실물 **단독 운반 중 벽·바닥이 보였고 블록 가림이 작았다**고 확인했다. s2v16의 관측 부재는 SIM/실물 불일치로 재분류한다. 현재 실물600/2200/1400과 SIM HIGH896/2035/1894의 명령 차이는 확정했으며, mount/실물 처짐은 미측정이다. 아래 s2v17 절에 근거·기준·기하 평가를 따로 기록하고 이전 수치/raw는 보존한다.

**이전 실행 완료(v121):** `f0bb26e7`의 s1045는 pick→carry→place까지 진행했지만 **lifted=true/inside=false**다. B 밖 바닥에 안정적으로 놓였고 최종 위치 추정 오차3.839m를 확인했다. 팔 가드5회·위치 불확실519회는 기록만 했다. 추가 실행 없이 종료·잠금 해제했다. [완료 기록](#v121s1045-전체-dev-완료--b-밖에-놓음), [사전 기록](#v121-전체-dev-사전-기록--s1045-2026-10-07)을 따른다.

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

### v3 외부 보정 재측정 계획 (2026-10-07, 실행 전 고정)

기존 값은 엄밀히는 pre-v3 값 그대로가 아니라 v3 장착 변환을 합성한 값이다. 다만 팔/차체
변형은 과거 짝 하중 보정에서 상속했다. 새 보정은 gate 완화 없이 **알려진 표적의 RGB 코너**로
다시 구한다. 기존 카메라 장착·K/D·FOV·gate는 그대로 두며 구 데이터와 새 결과를 합산하지 않는다.

- 표준 절차: [Zhang, A Flexible New Technique for Camera Calibration, PAMI 2000 / 원저자 기술보고서](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr98-71.pdf),
  [OpenCV calibration/corner API](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html),
  [OpenCV solvePnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html).
  이 작업은 **내부 파라미터 재추정이 아니라 고정 K/D에서 외부 파라미터 추정**이다.
  8×5 내부 코너, 알려진 칸 크기/표적 배치, `findChessboardCornersSB`, fisheye undistortPoints,
  solvePnP ITERATIVE + refineLM. 자세당 표적 2배치로 fit, 별도 1배치로 검증한다.
  fit/holdout RMS 각각 1 px 이하, 모든 점이 카메라 앞에 있어야 보정으로 채택한다.
- 실물 재현: 차체를 수평 기준 지그에 고정하고 차체 기준점/바닥 높이(이번 SIM은 32.5 mm)와
  표적 코너를 실측한다. 동일 PWM·그리퍼 하중에서 8초 정지 후 촬영한다. 표적은 위쪽 라벨을
  위로 두고 ±12° 이내로 기울인다. 실물에서는 해당 기기의 K/D를 먼저 따로 검증해야 한다.
  이번 산출물은 **SIM 고정 지그 보정**이며 실물 보정 완료 주장이 아니다. 자유 차체의
  하중/바닥 기울기·동적 흔들림은 고정 보정으로 없앨 수 없으므로 과거 실행에 별도 평가한다.
- 표적 배치에는 이전 보정/명령 FK로 대략적인 시야를 사용하지만 PnP 초기값·정답으로 쓰지 않는다.
  PNG 코너와 알려진 표적 좌표 외에는 fit에 입력하지 않는다. 카메라 실제 좌표·접촉은 별도
  `eval_only.json`에 쓰고 보정표를 동결한 뒤 평가한다. cargo weld OFF, 카메라 수정 없음.
- `s2-camera-extrinsic-capture-v1`은 표준 Scene/CLI 관리 경로의 유한 보정 촬영이다.
  무하중 21자세(검색 pan, 정렬 3자세, hover, 하강, VIA110/130, HIGH)·하중 5자세
  (바닥 닫힘, hover, VIA110/130, HIGH) = 26자세/78장. loaded 중간 하강은 정지 없이 통과하므로
  별도 loaded 관측 자세가 아니다. 선행 임무 seed1047은 장면 구성 참조일 뿐 재실행하지 않는다.
  지그 생성은 calibration setup seed0이며 증거/확증 seed가 아니다. 360 SIM s 상한, agent_lock,
  ugrp_session, 한 번에 하나, freeze ON은 S2 단독 DEV 보정에만 쓴다. 차체 고정 지그는
  임무 실행에는 절대 적용하지 않고 운반 성공으로 계산하지 않는다.
- 다음 번들은 **zone-s2-realism-v124 / workflow 7.17.0**으로 예약했다.
  main+열린 PR 15개에서 최대 v123, 새 seed1048 미사용을 확인했다
  ([예약](reservation-scan-v124.json)). full DEV seed1048의 최종 실행 등록/보정 해시는
  촬영·오프라인 검증 뒤 별도 커밋으로 고정한다. 현재는 보정 촬영만 준비했다.
촬영 전 변경 모듈 2개 시험: **22 passed**. 합성 fisheye 코너의 PnP 복원·미검출/holdout 불합격
거절·26자세 범위·비접촉 표적·CLI 계획의 비실행을 확인했다. 지그 실제 렌더/파지는 아직 미검증이다.

촬영 source `acab0c8f`는 18장 모두 표적 미검출로 자체 세션을 중단했다. 표적 없는 영상 확인 후
원인을 분리했다: 컴파일된 정적 body의 model pose 직접 변경은 이 경로에서 표시 위치를 갱신하지 않았다.
[MuJoCo 공식 runtime state 문서](https://mujoco.readthedocs.io/en/latest/programming/simulation.html)에 따라
표적만 비접촉 mocap body로 만들고 `data.mocap_pos/quat`로 알려진 배치를 준다. 로봇·카메라·하중
모델은 동일하다. 단일 자세라도 3장 모두 검출되지 않으면 즉시 촬영 오류로 종료하도록 했다.
[중단 원본·해시](calibration-capture-aborted.json), 잠금 null 및 자체 세션 stopped 확인.
두 번째 source `2b7f1892`: 무하중 21자세의 63장 모두 검출. 하중 floor 자세에서 체커보드가
하단에 걸려 3배치 중 1장만 검출되어 규정대로 종료했다([기록](calibration-capture-partial.json)).
이는 표적 위치 불일치이며 카메라를 움직이지 않는다. 표준 보정의 '표적을 시야 안으로 이동' 절차를
그대로 적용해 각 배치에서 명목 optical-down 방향의 거리 비율 0/−.15/−.30/+.15/+.30 순으로
표적만 옮긴다. RGB 전체 코너 검출만 선택 조건이며 모든 시도·실측된 표적 좌표를 보존한다.
별도 새 source로 하중 5자세만 이어서 촬영한다. 무하중 자료는 재촬영하지 않고 source별로 연결한다.

PnP 후보1은 26자세 holdout RMS 최대 0.304978 px로 표적 재투영을 통과했으나 **채택하지 않았다**.
RGB fit을 끝내고 SHA `6021770d85b670639654706c7b7fb8716805d112d065cdb503b6747eddff7e9a`를
동결한 뒤 별도 물리 평가를 열어 보니 loaded hover/VIA/HIGH에서 cyan은 바닥에 있었고 양쪽
접촉이 없었다. HIGH −29.9024°/0.193148 m는 실제로 무하중 값이다. 재투영 합격을 하중 조건
합격으로 취급하지 않는다([불채택 기록](calibration-load-rejected.json)).
수정 근거는 원래 `zone_solo_cyan_v106.py:428–442`와 s1047 발행 명령이다. 정상 S2는 닫기
0.5초+0.4초 정지 후 바로 hover로 들지만 촬영기는 바닥 닫힘을 먼저 8초 정지했다. 바닥 지지로
누르는 시간을 추가한 채 이를 동일 파지라고 가정한 것이 잘못이다. 하중 촬영은 실제 S2 순서로
hover→VIA110→VIA130→HIGH를 측정하고 마지막에 정상 lower 경로로 바닥 닫힘을 측정한다.
하중이 필요한 자세에서 접촉이 없으면 평가 측이 촬영을 중단한다(명령/보정에 GT 전달 없음).
하중 이탈 1회이며 같은 원인 반복 시 추가 촬영·full 실행을 중단한다. 후보1 원본/표는 보존한다.
추가 바닥 정지가 이탈을 일으켰다는 것은 아직 원인 후보이며, 다음 하중 촬영으로 확인한다.

### 외부 보정 결과: 하중 이탈 2회로 중단, v124 실행 미등록

두 번째 하중 촬영 source **`d6070c52`**에서도 hover에서 `CALIBRATION_GRIP_LOSS`가 발생했다.
cyan z=0.015892 m, bilateral=false였다. 앞선 하중 source `486c5cce`와 같은 이탈이므로 추가
물리 촬영과 full DEV를 중단했다. 단순히 닫힘 뒤 바닥 정지만의 문제라는 가설은 입증되지 않았다.
촬영기의 수평 차체 지그와 `_team_joint_move_servos` 연속 보간은 원래 자유 차체/0.05초 arm
발행 경로와 다르므로, 원래 S2 성공 파지를 재현했다고 볼 수 없다. 특히 기존 blind descent의
별도 정지 시간까지 동일한지 추가 감사가 필요하다. 이를 고치려는 추가 실행은 하지 않았다.

- [부분 보정표](../../configs/calibration/s2_camera_v3_extrinsic_v1.json): **무하중 21자세/63장**,
  자세당 fit 80점·holdout 40점, holdout RMS 최대 **0.304978 px**.
  HIGH/VIA110/VIA130/hover/정렬·검색 pan·하강을 포함한다. **loaded table은 빈 값**,
  `PARTIAL_NO_LOADED_CALIBRATION / load_qualified=false / admitted=false`이다.
- 별도 무하중 HIGH 값은 pitch **−29.902435°**, 높이 **0.193148 m**다. 하중인 줄 알고 촬영한
  후보1도 같은 값이 나왔으나 실제 물체는 바닥에 있었으므로 하중 보정에 쓸 수 없다.
  s1045–1047 실제 carry 약 −32.69°/0.1872 m를 이 값으로 대체하지 않았다.
- `harness/zone_solo_cyan_extrinsic.py`에 `camera_calibration=off|v3_extrinsic_v1`을 추가했다.
  기본/명시적 off는 명령·record bytes 동일. 부분 표로 on하면
  **`LOADED_CAMERA_CALIBRATION_UNAVAILABLE`**로 거절한다. 유효한 하중 표가 없어 CLI/번들
  실행 입장은 연결하지 않았다. **v124/7.17.0은 예약만**, seed1048은 미실행·미소비다.
- 요청한 s1045–1047의 **유효한 새 보정 replay와 fix 수락 비교는 미수행**이다. 잘못된 무하중
  HIGH를 적용해 fix 수가 늘어난 것을 개선으로 보고하지 않는다. 새 full DEV도 실행하지 않아
  lifted/inside 및 운반 wall/SIM의 새 결과는 없다. 이전 결과와 합산하지 않는다.
- [촬영·모든 raw 해시·정리 요약](extrinsic-calibration-summary.json),
  [첫 하중 불채택](calibration-load-rejected.json), [두 번째 이탈 중단](calibration-load-stop.json).
  raw는 `/Users/changmin/projects/ugrp/outputs/s2-calibration-<sha8>-checkerboard[-loaded]`에 보존한다.
  첫 강제 중단의 관리 manifest는 원래 `running`으로 남았지만 실제 소유 PID 종료를 확인하고
  별도 요약에서 `ABORTED`로 기록했다. 원본 manifest를 덮어쓰지 않았다.
  모든 촬영은 agent_lock/ugrp_session과 nice0, 순차 실행. 최종 lock=null, 자체 프로세스 종료.

### 보정 공유 경로와 다른 작업 영향 범위 (수정 없음)

| 소비자 | 보정 경로와 확인 범위 |
|---|---|
| S2 PF·벽 투영 | `vision_pose_source_highpose.py:73`의 `column_model_for` → `camera_record` → `floor_camera` → `measured_column_model`; provider가 잡은 calibration 사전을 제자리 갱신한다. |
| S2 벽 검출 | `OpenCVObserver`가 위 PF의 column-model factory를 매번 사용한다. K/D·임계값을 바꾸지 않는다. |
| S2 cyan·블록 투영 | `zone_solo_cyan_vision_v106.CyanVision`이 동일한 provider calibration 객체를 받는다. `extrinsics`·바닥 cuboid·hover ray projection이 같은 표를 쓴다. |
| pickup-site 재관측 | `zone_solo_cyan_scene_runtime.py:185–191`은 그 사전의 복사본으로 loaded→unloaded 조회를 구성한다. 기본 경로/픽셀 차분은 바꾸지 않았다. 이번 inhand 선택에서는 이 경로를 쓰지 않는다. |
| in-hand/flow | RGB 픽셀 증거이며 외부 보정표를 직접 소비하지 않는다. 입력 카메라는 v3 그대로다. |
| 짝/S3 | `vision_pose_source_pair_v3.py`, `zone_final_pair_vision.py`, HIGH provider를 공유하는 제어기는 각자의 카메라 profile/하중 표 조합을 점검해야 한다. 이전 장착을 유지한 실행에 같은 오류가 있다고 단정하지 않는다. 새 표는 이들에 적용하지 않았다. |
| PR405 자기 지도·벽 검출기 | 점검 ref `f3eeb6bf090f3eba2fd16a29020e7e187ed5241c`. `wall_probe.detector_bias`의 `SEED_BIAS`/선택 `sag_comp` 및 `height_free_wall`의 명령 자세 ColumnModel·horizon·바닥 역투영은 별도 보정 경로다. v3/단독 하중으로 검증되지 않으면 같은 종류의 투영 오차가 가능하다. `self_wall_memory.observe_wall`·`wall_projection_guard`는 호출자가 준 camera origin/rotation을 사용한다. PR405 파일/결과/PR은 수정하지 않았다. |

실제 PF/벽 column model과 cyan 투영이 같은 사전을 읽는 것은 **합성 하중 표를 넣은 단위 시험**으로
확인했다. 이는 유효한 loaded 보정을 획득했거나 새 운반이 성공했다는 뜻이 아니다.

최종 변경 모듈 2파일 **15 passed**: off bytes, 부분 표 on 거절, 실제 PF/벽/cyan 사전 공유,
독립 인스턴스 불변, RGB-PnP·holdout 거절을 확인했다. 촬영기/관리 경로 시험은 앞서 **23 passed**.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-extrinsic-capture-verified%2F#timeseries)
새 snapshot `1007-s2-extrinsic-capture-verified`, 촬영 기록 4건·**40 scalar 원본=event=API** 확인.
실패 포함 보정 기록이며 임무 실행 분모는 0이다. 기존 snapshot·서버·영상은 유지했다.
최초 export는 derived-view 근거 필드 누락으로 거절되어 실패 manifest를 보존했고, 새 snapshot으로
수정 export 후 검증했다([전달 검증](extrinsic-delivery-verification.json)). 브라우저는 수치 대조 요청에
따라 열지 않았다. freeze 전후 운반 wall/SIM의 새 비교값은 없다. PR #406 DRAFT, 병합 금지 유지.

### 무하중 표 + 하중 처짐 오프라인 재생: 결과 열람 전 기준 (2026-10-07)

[고정 판정 기준](unloaded-sag-criteria.json)을 먼저 커밋한다. s1045/1046/1047의 저장된
RGB와 자기 명령을 처음부터 끝까지 재생하며 새 시뮬레이션·모델 호출은 없다. 원래 motion/visual
옵션과 PF seed를 유지하고 카메라 표만 바꾼다. legacy 재생은 저장 pose와 최대 차이 1e-10 이하를
먼저 확인한다. 이미지 SHA 불일치나 baseline 불일치는 분석 오류로 간주한다.

운반은 저장 state=carry 시작부터 다음 state 전환까지다. 각 실행에서 마지막 시각 fix의 실제
갱신을 세며 1 SIM 초 이상 간격의 독립 fix가 **6개 이상**, carry 양끝을 포함한 **최장 무fix
구간 30 SIM 초 이하**여야 한다. 3개 실행 모두 충족해야 다음 full DEV를 허용한다.
이는 180초 가까운 명령 단독 이동을 허용하지 않는 개발 입장 기준이며, 표준 논문의 보편적
문턱이나 물리 성공 기준이 아니다. 기존 residual/support/rank gate는 변경하지 않는다.
운반 벽 잔차·gate 사유·GT 위치오차도 평가하되 GT를 PF/상수 추정/후보 선택에 쓰지 않는다.

고정 비교: legacy, 무하중 표를 두 상태에 복사, 무하중+PR405 고정 하중 차이,
무하중+PR405 자세별 sag의 loaded-minus-unloaded 항. PR405 ref
`f3eeb6bf090f3eba2fd16a29020e7e187ed5241c`의 `wall_probe.SEED_BIAS`는
unloaded −0.01868 rad(−1.07028°), loaded −0.04579 rad(−2.62359°)이다.
따라서 −1.07°는 하중 증가분이 아니며 고정 증가분은 **−0.02711 rad(−1.55329°)**다.
PnP 무하중 표에는 자체 처짐이 이미 포함되므로 full bias를 더하지 않는다. 자세별 모델도
같은 이유로 하중 항만 더한다. 원점/높이는 측정된 무하중 값 그대로이고 각도만 변한다.
기존 짝 하중 자료의 전이 근사임을 표시하고 실제 S2 loaded 측정값이라고 부르지 않는다.
여러 후보가 통과하면 위 순서의 가장 단순한 것을 선택한다. 사후 기준 완화/추가 튜닝은 없다.

부분 보정표와 runtime loaded 거절은 유지한다. 기준 통과 때만 별도 명시적 근사 옵션과 새
번들을 시험·커밋하고 seed 사전 등록 후 1회 실행한다. 미달이면 새 full DEV는 실행하지 않는다.
지그 하중 이탈 2건은 기존 출력만 감사하고 재시도·weld·인위적 고정은 하지 않는다.

### 지그 파지 이탈 2건: 저장 출력 감사, 재실행 없음

[오프라인 평가 수치·원본 해시](fixture-loss-offline-audit.json). `486c5cce`의 floor(t=16.94)에서는
양쪽 접촉 true, cyan z=16.094 mm지만 hover(t=26.14)에서는 접촉 false, z=15.892 mm다.
그리퍼 기준 물체 중심은 floor **[101.035, −0.327, −6.116] mm**에서 hover
**[160.077, −0.080, −30.826] mm**로 바뀌었다. 정상 s1047(t=49)의
**[92.612, −0.039, +2.348] mm**와 비교하면 처음부터 약 **8.42 mm 더 끝쪽**,
**8.46 mm 더 아래쪽**에서 닿았다. 정상 s1047은 t=52에도 이 상대 위치를 거의 유지하며
z=85.007 mm로 들었다. 지그의 양쪽 바닥 접촉만으로 안정 파지를 가정한 것이 잘못이다.
두 번째 `d6070c52`는 hover(t=16.24)부터 접촉 false, z=15.892 mm, 상대 중심
**[155.380, +21.771, −39.662] mm**였다. 닫힘 뒤 긴 바닥 정지를 제거해도 이탈하여
긴 바닥 정지만을 단독 원인으로 보는 가설은 성립하지 않는다. 모든 저장 시점 weld=0이다.

원인 후보/측정 한계: 촬영기는 매 0.00025초 step 뒤 차체 qpos를 수평 고정하고 qvel을
0으로 재설정했다. 원래 자유 차체의 반작용과 다르지만 반력·충격량·중간 가속도는 저장되지
않아 수치 확정할 수 없다. 촬영기 `_team_joint_move_servos`는 step마다 목표를 보간하며
정상 임무의 arm dispatch는 0.05초다. 하강 후 정상 `real_hover.py:102`의
`HOVER_SETTLE_S=0.3 s`가 촬영기에는 없고 hover 들기 명령도 1.2초 대 정상 기본 1.0초다.
따라서 동일 자세 숫자만으로 같은 파지를 재현했다고 할 수 없다. PNG는 표적/테두리만
보여 접촉 순간을 판독할 수 없다. 장면 XML의 집게 kp=1200 N/m·한쪽 force limit=18 N,
미끄럼 마찰 3.4는 **설정값**이다. 실제 법선력/모터 전류/관절 오차는 없으므로 힘 부족이나
급가속을 확정하지 않는다. 이 감사의 GT는 평가만이며 위치/명령 보정에는 사용하지 않았다.

표준 하중 보정 조사(실행하지 않은 실물 절차):
- [Klimchik 등, elastostatic calibration 설계](https://arxiv.org/abs/1211.6101): 알려진
  외력/모멘트와 자세별 변위를 측정하고 강성/컴플라이언스를 추정한다. 무하중 기하와
  하중 변형을 구분하는 것이 이번 무하중+하중 증가분 비교의 근거다.
- [Klimchik 등, 기하·탄성 보정 실험 §V.D/그림6](https://arxiv.org/abs/1311.6810):
  도구에 중력 하중을 적용하고 적재 전후 표식 위치를 측정한 실험이다. 이 논문의 대형
  로봇 수치/식별 계수를 MasterPi에 옮기지 않는다.
- [Universal Robots의 Payload/CoG 절차](https://www.universal-robots.com/manuals/EN/HTML/SW10_11/Content/prod-usr-man/software/PolyScopeX/polyx-application/polyx-TCP_Payload_CenterofGravity.htm):
  서로 다른 4자세에서 질량·무게중심을 추정하고, 장착 방향과 외부 당김을 통제한다.
  동일 질량만으로 충분하지 않으며 도구까지 포함한 무게중심·하중 작용점도 맞춰야 한다.
- 적용 가능한 **향후 실물 절차 제안**: 질량/무게중심을 잰 보정 추를 실제 도구에 기계적으로
  부착하여 미끄러지는 파지와 분리하고, 같은 PWM 정지 자세에서 무하중/하중 체커보드를
  촬영해 [OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html)로 각각
  외부 파라미터를 측정한다. 이는 위 표준 절차를 MasterPi에 적용한 제안이며 제조사에
  같은 전용 보정 기능이 있다는 주장이 아니다. 이번 SIM에서 추 부착·weld·새 지그 촬영은
  수행하지 않았다. PR405 계수는 과거 짝 하중의 고정 추정값 그대로이고 S2 질량에 맞춰
  재추정하거나 GT로 스케일하지 않았다.

### 무하중/sag 재생 결과: 전 조합 기준 미달, full DEV 미실행

기준 커밋 **adfd53a1** 이후 저장된 RGB/자기 명령을 3 seed×4조합으로 재생했다.
[결과/판정/원본 해시](unloaded-sag-summary.json). 기존 보정은 **13,794 / 6,500 / 5,100개**
재생 자세가 원본과 최대 차이 **0**이다. s1047 마지막 pose 1개는 새 RGB 없이 기록돼
재생 표본에서 제외했으며 carry는 모두 포함한다. 입력 JPG SHA를 재생 시 전부 대조했다.
기존 명령 고정 replay이므로 새 보정 제어의 실제 주행/inside 성공을 뜻하지 않는다.

| seed | 고정 보정 | fix/독립 fix | 최장 공백(s) | 벽 잔차 중앙(px) | carry 끝 오차(m, 평가) |
|---|---|---:|---:|---:|---:|
| 1045 | 기존 | 313/27 | 267.45 | 52.39 | 3.839 |
| 1045 | 무하중 | 1266/87 | 136.75 | 38.70 | 1.005 |
| 1045 | 무하중+고정 차이 | 1224/90 | 107.70 | 21.21 | 4.103 |
| 1045 | 무하중+자세별 sag | 900/61 | 124.30 | 19.78 | 0.706 |
| 1046 | 기존 | 104/6 | 222.70 | 52.83 | 3.348 |
| 1046 | 무하중 | 6/1 | 205.75 | 38.70 | 4.364 |
| 1046 | 무하중+고정 차이 | 228/12 | 190.70 | 21.44 | 3.542 |
| 1046 | 무하중+자세별 sag | 93/6 | 222.75 | 18.43 | 3.281 |
| 1047 | 기존 | 0/0 | 167.80 | 52.29 | 0.623 |
| 1047 | 무하중 | 68/4 | 129.85 | 38.64 | 0.732 |
| 1047 | 무하중+고정 차이 | 0/0 | 167.80 | 21.04 | 0.357 |
| 1047 | 무하중+자세별 sag | 0/0 | 167.80 | 20.55 | 0.357 |

새 조합 9건 **모두 최장 무fix 구간 30초 기준에 미달**했다. s1047 무하중 fix68개는
t=104.70–108.05의 짧은 구간이고 이후 129.85초간 끊겼다. 두 sag 근사는 s1047 fix0이다.
따라서 **selected_candidate=null / full_dev_permitted=false**, 새 seed/번들 실행 등록 및
full DEV는 하지 않았다. seed1048은 이 작업에서 소비하지 않았다. 기존 부분 표의 loaded
거절·기본 off·기존 제어 출력은 유지하며 CLI 입장 옵션을 추가하지 않는다.

잔차는 carry 시작 뒤 정수 SIM 초마다 1장(585/240/167장)에서 평가했다. GT로 투영한
실제 벽 하단이 화면 [4,470] 안에 있고 RGB 검출이 있는 표본만 위 벽 잔차에 썼다.
분모는 s1045 24–26장, s1046 148–150장, s1047 28장이다(보정에 따라 검출 열이 달라짐).
모든 검출을 포함한 잔차와 분모도 JSON에 보존했다. 실제 카메라를 **평가에만** 대입하면
이 표본 잔차는 각각 약 0.47/0.58/0.52 px다. 이는 남은 고정 보정 불일치를 확인하는
사후 진단이며 actual-camera 표를 PF에 넣거나 보정 계수를 GT로 맞추지 않았다.

HIGH pitch는 기존 −36.5917°, 무하중 −29.9024°, 고정 차이 적용 −31.4557°,
자세별 sag 적용 −35.0478°다. 자세별 PR405의 하중 항은 HIGH에서 **−5.1453°**이며
짝 하중 fit 계수를 단독 cyan에 그대로 옮긴 전이 근사다. 저장 carry 실제 중앙은
−32.73/−32.69/−32.72°, 높이 0.18718/0.18718/0.18711 m인 반면 새 근사 높이는
모두 0.193148 m여서 약 **6 mm** 높다. 카메라 각도·높이를 임의 튜닝하지 않았다.

수락 증가가 정확한 위치 복구를 보장하지도 않는다: 예컨대 s1045 고정 차이 fix1224회에도
carry 끝 오차는 4.103 m다. s1047 고정 차이/자세별 sag는 각각 gate3048개 중
posterior support<0.10이 3048개, inlier fraction<0.66이 2745/3007개였다.
잔차 감소만으로 기존 posterior와 일치하는 관측이 되지 않았고, 시야 밖 벽/바닥 패턴
오검출도 남아 있다. gate 문턱은 그대로다. GT 위치오차는 지연된 t_est에서 평가했으며
후보 선택/제어에는 사용하지 않았다.

오프라인 산출물은 `/Users/changmin/projects/ugrp/outputs/s2-unloaded-sag-replay-20261007/`의
12개 `s<seed>-<variant>.json`, `geometry-evaluation.json`, `fixture-loss-audit.json`,
`summary.json`에 보존했다. 원본·이전 TensorBoard·영상은 변경하지 않았다. 이번 물리
실행/모델 호출은 0이며, freeze 전후 wall/SIM의 새 비교값은 없다.

검증: 변경 범위 2시험 파일 **11 passed**, 세 legacy 전체 재생 최대 차이 0, 기본/명시적 off
명령·record bytes 동일 및 부분 loaded 표 거절 확인. 전체/다른 제어기 로컬 시험은 돌리지
않았다. 재생 프로세스는 모두 종료했고 agent_lock status=null이며 이번에는 물리 잠금을
획득하지 않았다. 지그 재촬영·새 렌더·SIM step·인위적 고정·모델 호출은 없다.

[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-unloaded-sag-replay-verified%2F#timeseries)
snapshot `1007-s2-unloaded-sag-replay-verified`: **12개 오프라인 비교·120 scalar**의
원본=event=live API 일치를 확인했다([전달 검증](unloaded-sag-delivery-verification.json)).
미션 실행 수는 0이며 수치만 대조했다. 최초 export는 audit schema 누락으로 12개 모두
거절돼 실패 manifest/파생 뷰를 보존했고, schema를 적은 새 파생 뷰·새 snapshot으로
검증했다. 공용 view 파일에는 자기 키만 추가했고 기존 서버/자료는 유지했다.

### AMCL likelihood-field 비교: 재생 결과 전 기준 (2026-10-07)

[사전 고정 기준](soft-mcl-criteria.json). s1045–1047은 탐색/오프라인 검증 자료이며 확증 seed가
아니다. 새 후보는 한 가지 `measurement_model=amcl_likelihood_field_v1`이고 기본 off다.
무하중+PR405 고정 loaded-minus-unloaded 표(−1.55329°)를 이전 비교 그대로 사용한다.
새 GT fit/보정표 튜닝은 없다. 카메라 v3·K/D·검출기·운동/명령/seed는 고정한다.

각 seed carry에서 (1) 관측으로 실제 가중치가 바뀐 update의 최장 공백(양끝 포함)≤30 SIM s,
1초 간격 독립 update≥6, (2) 지연 t_est 기준 xy RMSE가 **기존 원본과 동일 보정의 이전
hard-receipt 재생 모두보다 감소**, xy 오차 p90은 두 baseline 모두보다 커지지 않아야 한다.
세 seed 모두 통과해야 새 full DEV를 허용한다. GT는 이 사후 채점/입장 판정과 잔차 분해에만
사용하고 측정식·보정값·PF에 전달하지 않는다. 사후 문턱 완화나 여러 후보 튜닝은 하지 않는다.
가중치 변화 KL>1e-12는 부동소수 반올림/상수 likelihood 제외용이며 정확한 절대 위치 fix를
뜻하지 않는다. 원래 hard fix, 확률 update, 업데이트 후 위치 정확도를 구분해 보고한다.

현재 코드 감사: `zone_final_pair_scan`/`partial_fix`는 가중치 갱신 **후** residual/support/
rank로 fix receipt를 거절한다. s1045/1046이 이 방식이며 이미 hit+outlier 혼합을 쓴다.
s1047의 `visual_update=accepted_scan_v1`은 **갱신 전** 거절로 weight 변경도 막는다.
따라서 전체 과거가 순수 hard gate였다고 단정하지 않는다.

표준 근거:
- [Probabilistic Robotics, 저자 공식 사이트](https://robots.stanford.edu/probabilistic-robotics/), Ch.6/8의
  측정 mixture와 MCL: 측정 likelihood로 입자 가중치를 갱신하고 정규화/재표집한다.
- [Nav2 공식 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/):
  likelihood-field는 **hit/random** 두 성분이며 short/max는 별도 beam 모델이다.
  단안 RGB의 미검출을 lidar max-range 반환으로 해석하지 않는다.
- [고정한 Nav2 likelihood-field 구현](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp):
  endpoint에서 가장 가까운 occupied cell까지 거리 d,
  `pz=0.5*exp(-d*d/(2*0.2*0.2))+0.5/range_max`,
  `weight *= 1 + sum(pz^3)`를 그대로 따른다. residual 크기로 전체 scan을 거절하지 않는다.
  [beam 모델](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/beam_model.cpp)은
  기대 ray range 대비 short/max/hit/random을 섞는 대안이며 이번 후보에는 혼합하지 않는다.

필요한 RGB 어댑터: 검출된 wall/floor pixel을 **고정 보정표**의 ray로 바닥에 역투영하여
2D endpoint를 만든다. 아래로 향하지 않는 ray/NaN/100m 이상은 측정 없음이다.
정적 지도 장애물을 1cm occupancy grid로 만들고 표준 Euclidean distance transform,
거리 cap2m, hit sigma0.2m, hit/random0.5/0.5, max_beams60, range_max100m를 고정한다.
Nav2의 beam stride는 `(range_count−1)//(max_beams−1)`를 그대로 적용한다. 1cm는
이번 metric 지도 raster 정의이며 px 잔차에 맞춰 고른 sigma가 아니다. 독립 관측 주기는
자기 명령 오도메트리의 축별 이동>0.25m 또는 회전>0.2rad(AMCL 기본값), 최초 HIGH
관측이며 정지 시 같은 장면을 반복 곱하지 않는다. 제어 입력은 여전히 자기 RGB/명령뿐이다.
변경은 S2의 loaded HIGH 측정 업데이트에만 한정한다. 기존 motion/PF 초기화·주행·다른
제어기 및 기본 off는 유지한다. ROS AMCL 전체 이식/KLD particle 수 변경 주장은 아니다.

잔차 분해는 동일 저장 영상/열에서 K/D 역변환 수치 오차, 고정↔실제 카메라 높이/방향,
프레임별 흔들림, GT 투영↔검출 행 차이를 대조한다. 평가 로그에는 차체 tilt 크기는 있지만
roll/pitch 성분·관절 시계열은 없으므로 처짐과 차체 기울기를 유일하게 분리할 수 없으면
식별 불가와 기여 상한으로 보고한다. GT 자세를 실행용 보정표로 바꾸지 않는다.

AMCL 후보는 loaded HIGH에서 Nav2 기본 recovery alpha=0을 따른다. 이전 px likelihood의
augmented-MCL running average를 새 `1+sum(pz^3)` 값과 섞지 않으며, 그 외 구간은 기존
측정·회복을 유지한다. 예측/재표집/입자 수는 기존 S2 것을 재사용한다.

#### 잔차 원인 분해: 평가 전용 기하, 새 fit 아님

`decompose_camera_residual.py`는 carry의 1 SIM s 고정 격자에서 같은 JPEG 해시·검출 열을
비교한다. 투영 순서는 명목 표→실제 평균 높이→평균 xy→평균 회전→각 프레임 카메라→
검출 행이다. 각 열의 **부호 있는 차이 합**은 전체 잔차와 일치하지만 아래 **절대 중앙값은
합산하지 않는다**. 실제 평균/프레임 자세는 오직 평가 프로세스 내부에 있고, PF와 고정표는
변경하지 않았다. 표본마다 기여가 달라 18–21 px 전체를 독립 원인 비율로 해석할 수 없다.

| seed | 전체(px) | 평균 높이 | 평균 xy | 평균 회전 | 동적 합 | 검출·raster |
|---|---:|---:|---:|---:|---:|---:|
|1045|21.124|7.691|1.053|14.324|0.372|0.490|
|1046|21.355|7.883|0.907|13.941|0.353|0.555|
|1047|21.014|6.129|0.577|14.729|0.279|0.527|

- **내부 파라미터/렌즈:** 렌더·검출기의 K와 4개 fisheye D는 동일(최대 차이0).
  렌더 왜곡→검출기 역왜곡의 좌표장 왕복은 y 절대 중앙0.000092 px, p95 0.000244 px.
  이 수치는 좌표 변환의 수치 오차이며 실제 렌즈 보정 정확도를 뜻하지 않는다. JPEG,
  보간으로 변한 경계는 마지막 검출·raster 항에 포함된다.
- **남은 고정 외부 보정:** 명목 HIGH pitch−31.45572°, 높이0.193148m 대비 실제 carry
  pitch 중앙−32.697~−32.729°, 높이 중앙0.187119~0.187172m. 약1.24~1.27°/5.98~6.03mm의
  체계적 차이가 남는다. 평균 회전/높이 항이 주원인이며 실제 GT로 상수를 다시 fit하지 않는다.
- **운반 중 동적 처짐/흔들림:** 카메라 pitch 표준편차0.0296/0.1481/0.0320°,
  높이 표준편차0.123/0.407/0.176mm. 평균 자세 대비 프레임 변동 항 중앙0.28~0.37px.
  s1046 정지 명령 표본의 동적 항 p95=3.13px로 드문 흔들림도 있으며 평균만으로 지우지 않는다.
- **차체 기울기:** tilt 중앙0.110/0.101/0.101°. signed roll/pitch·관절 상태가 기록되지 않아
  팔 처짐과 차체 기울기의 정확한 기여는 **식별 불가**다. 기록된 tilt 크기를 x/y축 투영
  미분에 적용한 1차 민감도 envelope 중앙1.89/1.48/1.58px(p95 3.03/3.84/2.68px)는
  영향 규모 참고이며 관측된 개별 기여나 엄밀한 비선형 상한이 아니다.
- **벽 검출:** 실제 벽 하단이 화면 안에 있는 검출 열만 보면 중앙 오차0.49~0.56px이지만,
  s1047 p95=66.01px로 큰 오검출 꼬리가 있다. t149.0 원본 `02954.jpg`도 직접 확인했다:
  큰 회색 격자 경계와 화면 아래 cyan이 보인다. 검출92열 중 실제 mapped wall 하단은84열에서
  화면 밖이며 남은8열의 검출 잔차 중앙103.13px다. 표준 likelihood-field도 **올바른 경계
  대응**을 전제로 하므로, 이런 상관된 오검출을 random 성분이 반드시 해결한다고 보지 않는다.

적용 범위는 S2 별도 `zone_solo_cyan_likelihood_field.py`의 loaded HIGH, 자기 RGB의
고정 ray→바닥 endpoint→정적 wall 거리장뿐이다. 공용 camera port, 다른 제어기, PR405,
기존 K/D/검출기/gate/고정 보정표를 수정하지 않았다. 보정 `unloaded_constant_delta`는
오프라인 비교용 factory이며 기존 런타임 loaded 보정 입장 차단을 우회해 해제하지 않는다.

전체 1초 표본의 검출 열 중 mapped wall 하단이 실제 시야 밖인 비율은
**39996/42100=95.00%, 9888/16247=60.86%, 9916/10445=94.94%**다.
이는 GT를 사용한 사후 대응 감사이며 제어 입력의 유효 열을 GT로 골라내지 않았다.

#### 고정 AMCL 후보 재생 결과: 3/3 입장 실패, SIM 미실행

기준 커밋 `9a38ae45`, 후보 코드 `dc1ed79b`를 고정했다. 기본 off의 명령/record bytes 동일,
20px 잔차의 유효 가중치 갱신, 상수 out-of-map likelihood의 가짜 fix 금지, unloaded
위임, 사전 입장 판정을 시험했다. 변경 범위 2파일 **13 passed**. 새 후보 1개만 재생했고
결과를 본 뒤 sigma/mixture/주기/문턱/카메라 표를 튜닝하지 않았다.

[수치·해시 요약](soft-mcl-summary.json), 원본 파생 기록:
`/Users/changmin/projects/ugrp/outputs/s2-soft-mcl-20261007/`.
`s1045/s1046/s1047-amcl_likelihood_field_v1.json`에 각 시각의 추정·KL·가중치 범위·receipt,
`residual-decomposition.json`에 평가 전용 분해를 보존한다. 저장 영상/명령은
13,794/6,500/5,101개를 재생했으며 세 실행 모두 저장 pose의 RGB 대응 누락은0이었다.
이전 기록의 s1047 5,100개/말단 누락1 표기는 잘못됐으며 원본 manifest 재확인으로 정정한다.
이전에 재현한 legacy 기준선의 원본 pose 최대 차이는 모두0이고 source hash도 재확인했다.

|seed|soft update / 1초 독립|최장 공백(s), 기준≤30|carry RMSE(m): 원본 / 같은 보정 / AMCL|p90(m): 원본 / 같은 보정 / AMCL|판정|
|---|---:|---:|---:|---:|---|
|1045|62 / 61|184.85|1.7749 / 1.8259 / 1.6445|3.2996 / 3.9483 / 2.1281|공백 실패, 정확도 통과|
|1046|30 / 30|20.20|1.6820 / 1.9960 / 2.1327|3.4275 / 3.7915 / 3.9448|공백 통과, 정확도 실패|
|1047|21 / 21|40.00|0.3510 / 0.6071 / 0.6229|0.5713 / 0.8930 / 0.9237|둘 다 실패|

soft update는 nonconstant likelihood가 입자 가중치를 바꿨다는 뜻이며 정확한 절대 fix가
아니다. s1046은 관측 갱신이 지속돼도 위치오차가 악화됐다. **hard gate 제거만으로 문제를
해결하지 못한다**. 남은 systematic 외부 보정 편차와 벽/바닥 경계 대응 오류가 함께 남아
측정 likelihood를 올바른 위치 증거로 해석할 수 없는 구간이 있다. 특히 시야 밖 벽 경계의
상관된 오검출은 단순 uniform random 성분으로 보장되지 않는다. 현재 저장 자료만으로
차체/관절 기여를 정확히 식별할 수도 없다.

`full_dev_permitted=false`; 새로운 seed·번들·물리 실행·모델 호출은0. 기본 off 유지,
새 측정 모델은 별도 S2 Runtime/오프라인 재생 후보에만 있고 실행기/번들에는 입장시키지
않았다. freeze 전후 wall/SIM 새 비교는 없다. 이전 lifted/inside 결과·영상과 합산하지
않고 새 물리 성공을 주장하지 않는다. 기준 미달로 이 후보의 추가 시도는 종료한다.


AMCL의 odometry update 주기는 허용된 자기 명령 운동 모델을 적분해 적용했다. 실제
encoder/VO odometry가 아니므로 막힌 차체의 명령을 실제 이동으로 보증하지 않는다.
정확히 같은 검출 열은 다시 곱하지 않지만 영상 잡음이 있는 정체 장면까지 독립 관측이라고
보증하지 않으며, 그래서 receipt 수만으로 입장을 허용하지 않고 위치 정확도를 함께 채점했다.

[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-soft-mcl%2F#timeseries)
새 snapshot `1007-s2-soft-mcl`: **12개 비교/진단, 111 scalar** 원본=event=live API 일치,
HParams source/condition과 shared view의 자기 키 추가를 확인했다
([전달 검증](soft-mcl-delivery-verification.json)). 사용자 지시대로 수치만 대조했으며
브라우저 UI·기존 서버/PID52016·이전 snapshot·영상은 변경하지 않았다.
이번 재생 프로세스는 모두 정상 종료했고 물리 잠금은 미획득, 종료 확인 status=null이다.

### 사용자 실물 확인과 S2 파지 정책 고정 (2026-10-07)

[사용자 확인 원문 — PR #406 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/406#issuecomment-6028199927):
실물 MasterPi의 집기 직전 hover에서는 블록이 보이지 않았고, **미리 보이는 자세에서 관측한
뒤 마지막 접근·파지는 그 관측을 바탕으로 open-loop**였다. 사용자가 확인한 실물 절차이며
이번에 새 실물 시험을 한 결과는 아니다. 이 작업의 적용 범위는 **단독 S2 DEV**다.
코멘트의 S3 언급을 근거로 다른 제어기/PR까지 수정하지 않는다.

현행 full DEV(v121–v123, 최신 실행 번들 v123)의 옵션/실제 호출 경로를 점검했다.
이미 이 절차가 켜져 있어 새 중복 옵션이나 실행 번들을 만들 필요가 없다. 다음 full DEV도
아래 명시 조합을 유지한다. CLI/Runtime의 옵션 기본값은 off이고 기존 명령·출력은 그대로다.
**`hover_check=off`는 hover 확인을 끄는 뜻이 아니라 기존 hover 시각 게이트로 복귀한다.**

```text
hover_check=real_pregrasp_v1
hold_check=inhand_rgb_v1
site_check=off
grasp_check=pickup_site_v1   # 확장 선택용 명목 옵션; 실제 site 비교는 InhandCheck가 대체
dev_grasp_policy=log_only_v1
idle_robot_contacts=freeze_v1
```

| 확인 항목 | 현행 S2 full DEV | 남아 있는 과거 게이트/위치 |
|---|---|---|
| hover의 cyan 존재 | 요구하지 않음. `real_pregrasp → hover → blind_descent → grasp`; 이전 frame/hash/관측 시각을 전달하고 `hover_visual_confirmation=false` 기록 | `zone_solo_cyan_v106.py:414–431`의 `CYAN_HOVER_UNCONFIRMED`는 `hover_check=off`의 이전 경로에만 남음 |
| 들어 올린 뒤 in-hand | `InhandCheck.control`은 unknown에도 `GRASP_INHAND_UNCONFIRMED`/notification을 기록하고 carry 진행 | v120의 결과 판정 `INHAND_OR_LIFT_UNCONFIRMED`는 과거 probe 전용. v121–v123 full 실행기는 이 probe 판정기를 호출하지 않음 |
| 원래 자리 ROI/바닥 비교 | `hold_check=inhand_rgb_v1`이 `scene_check`를 대체하여 **실행하지 않음**. `pickup_site_status=not_evaluated_inhand_selected`, retry0. 수행하지 않은 비교를 확인 성공으로 표시하지 않음 | `zone_solo_cyan_scene_runtime.py:84`, `zone_solo_cyan_real_site.py:106`의 `CYAN_SCENE_RETRY_EXHAUSTED`와 v119 site probe 판정은 과거 별도 경로에 남음 |
| 실행 종료의 시각 성공 판정 | `run_s2_realism_v123.result_record`가 시각 상태를 보존하고 `visual_unknown_stops=false`; full 종료/실제 성공은 별도로 기록 | `dev_grasp_policy` 값 하나가 모든 과거 확인기를 바꾸는 것은 아님. 위 **전체 조합**과 실제 `InhandCheck` 선택이 필요 |

`zone_s2_realism_contract_v123.require_execution`은 현재 NEW_OPTIONS 전체를 요구하므로
hover/hold/dev 정책 중 하나가 off이거나 site 비교가 켜진 full 번들을 거절한다.
`launch_v123.zsh`에도 위 값이 명시되어 있다. 따라서 프로파일 수정 없이 이미 요청된
동작이며, 이번 변경은 이 사실을 문서화하고 회귀 시험으로 고정하는 것이다.

**미리 보는 관측**은 여전히 필요하다: 정렬 위치에서 .45초 정지 후 최대9개 새 RGB 중4회,
cyan≥500px/고유 검출/기존±3mm 정렬을 확인하고 그 이후 hover에서는 cyan을 다시 요구하지
않는다(`zone_solo_cyan_real_hover.py:52–111`). reference 부재·명령 경로 이탈·시간창 위반은
이전 관측을 사용할 수 없다는 별도 조건이다. 초기 탐색/정렬, 입력 프레임의 무결성·품질
게이트(`INVALID_OWN_IMAGE`), 자기 명령 상태 검사도 남는다. 이들은 cyan이 hover/운반
영상에 존재해야 한다는 판정과 구분한다. 이번 시험은 **cyan이 없는 유효한 RGB**를 사용하며
검거나 균일한 영상의 수용 범위까지 변경한 시험은 아니다.

실물 소스와 대조:
- `sim/real_stack_adapter.py:75–95`는 `scripts/red_block`의 실물 모듈을 직접 가져온다.
- `scripts/red_block/physical_state_machine_reference.py:250–254,4740–4758`은 정지한
  pre-grasp 자세에서 reference를 먼저 얻는다. `:4796–4832`의 `execute_pick_to_hover`는
  그 뒤 hover로 이동하고 새 시각 확인 없이 고정 descent→close→lift를 수행한다.
- 같은 파일 `verify_grasp`에는 집은 뒤 바닥 재관측 코드도 있으나, 이것이 사용자 확인의
  hover 가시성 또는 확정 파지 증거는 아니다. 현행 S2 full DEV는 그 비교 대신 in-hand
  결과를 기록만 하며, 보이지 않음을 물리 파지 실패/성공으로 바꾸지 않는다.

검증: `test_s2_real_pregrasp_policy.py`, `test_s2_real_hover.py`, `test_s2_full_dev.py`
**10 passed**. 최신 full Runtime의 모든 옵션을 켜고 합성 사전 관측4개 후 cyan0px RGB를
공급해 blind close→lift→carry, in-hand unknown 유지, would-stop 기록1회, 재집기0을
확인했다. 위치 보고/검출은 합성 fixture이며 카메라 물리·위치 정확도·파지 성공 시험이 아니다.
기존 off 명령/record byte 동일 시험도 통과했다. production 코드·설정·기존 번들·seed/raw는
변경하지 않았다. 새 SIM/렌더/모델 호출0, 새 잠금/세션 없음. 새 실험 결과가 없으므로
TensorBoard를 재변환하지 않는다. 다음 full DEV의 위치 추정 입장 기준 미달 상태를 이번
파지 정책 확인만으로 해제하지 않는다. PR #406은 DRAFT·병합 금지를 유지한다.

## s2v16 — 운반 벽 하단 visibility 사전 기준 (2026-10-07)

**재생 전 고정:** `visibility-criteria.json`의 단일 후보를 s1045–s1047 저장 명령·RGB에
적용한다. 각 seed 모두 최장 관측 갱신 공백(운반 양 끝 포함) ≤30 SIM초, 1초 간격 독립
갱신 ≥6, 운반 xy RMSE가 원래 실행·같은 보정 hard receipt·s2v14 AMCL보다 개선되어야
한다. p90은 원래 실행·같은 보정 hard receipt보다 나빠지지 않아야 한다. soft 갱신은
절대 위치 fix를 보장하지 않는다. GT는 별도 채점/가림 원인 분석만 사용한다.
미달이면 새 seed·번들·SIM을 만들지 않는다. 기존 기준을 결과에 맞춰 완화하지 않는다.

후보 `visibility_mask=command_geometry_v1`(기본 off)은 S2 loaded HIGH의 기존 AMCL
측정 앞에만 둔다. s2v14의 무하중+고정 처짐 보정·AMCL 계수·운동 모델은 유지한다.
자기 PWM FK와 v3 고정 링크 형상의 보수적 box/ray 교차, 2mm 형상 여유를 사용한다.
그리퍼는 고정 camera-to-wrist와 보정표를 연결하고, 개도는 open~명령 closure의 sweep으로
처리한다(명령을 실제 관절로 취급하지 않음). 물린 블록의 위치/각도는 명령으로 알 수
없고 전체 회전 외접구는 카메라까지 포함할 수 있어 쓸 수 없다. 블록은 허용된 자기 RGB의
기존 cyan 분할(왜곡 보정 뒤, 2px 팽창)만 제외한다. 이는 실제 블록 위치 GT 마스크가
아니며 검출 누락의 한계가 남는다. 자기 링크 형상 마스크와 색 마스크를 별도로 기록한다.
prior 입자 가중치 ≥95%에서 예측 경계가 4–470행 안이고 자기 가림 밖인 공통 열만 쓰며,
검출된 경계 자체의 광선도 마스크 밖이어야 한다. 최소6열, 나머지는 missing(가짜 원거리
측정/음의 증거로 넣지 않음). 재생 통과 전 full 실행기의 옵션으로 허용하지 않는다.

참고 절차: [ROS robot_self_filter SelfMask](https://docs.ros.org/en/noetic/api/robot_self_filter/html/classrobot__self__filter_1_1SelfMask.html)의
INSIDE/OUTSIDE/SHADOW 광선-로봇 교차를 따른다. 본 작업은 관절 TF 센서 대신 허용된
자기 명령 FK와 보수적 형상을 사용하므로 실제 가림의 확정 판정이 아닌 가림 가능성 제외다.
벽 상단·문 기둥 등 선분 특징은 [PL-SLAM 원 논문](https://arxiv.org/abs/1705.09479)의
point/line 결합과 비교 조사한다. stereo SLAM 전체를 단안 S2에 적용했다고 주장하지 않는다.
하단이 시야 밖이면 가림 마스크나 확률 가중만으로 새 관측이 생기지는 않는다.

### 가림 원인과 표준 방법 대조

분석은 운반 중 정수 SIM초에 가장 가까운 HIGH frame만 사용했다(s1045 585장,
s1046 240장, s1047 167장; 각96열). `analyze_visibility.py`는 평가용 카메라 변환과
공개 지도 벽의 **실제 하단 선분**을 직접 투영한다. 화면 경계 4–470행은 기존 정의다.
이때 위/아래 이탈을 먼저 나누고, 화면 안의 하단에 대한 블록 OBB(평가 GT), 보수적
자기 링크 box, 앞쪽 지도 벽의 ray 교차를 분리한다. 관절 및 차체의 signed roll/pitch가
저장되지 않아 자기 링크 가림은 command FK의 **가능성 상한**이며 실제 관절 측정이 아니다.

핵심 원인은 **먼 벽의 하단이 화면 위로 벗어나는 것**이다. actual HIGH 중앙 열의 바닥
가시 범위 중앙값은 로봇 기준 전방 x=0.329–0.965/0.967/0.965m이며 카메라는 약
높이0.187m, pitch−32.7°다. 위로 벗어난 벽까지 카메라 수평거리 중앙값은
s1045/46/47 각각1.701/3.230/2.797m이다. s1046의 아래 이탈은 반대로 벽에 가까운
거리 중앙값0.080m(5–95% 0.032–0.141m)에서 생겼다. +10° mount라고 해도 팔과 합친
광축은 여전히 아래를 향한다. 따라서 '운반 카메라가 위를 향해 가까운 바닥만 잃었다'는
설명으로 이 운반 자료 대부분을 설명할 수 없다. mount/FOV는 수정하지 않았다.

처음 만든 `geometry.json`은 선분의 FOV/자기 가림만 계산한 중간 산출물이다.
문 모서리의 벽끼리 가림도 넣은 `geometry-shadow.json`을 최종 기하 결과로 사용한다.
s1046에서 기존 expected_rows의 floor-trace 전환과 실제 벽 하단 선분 투영이133/23040열의
FOV 판정에서 다르며, 둘 다 화면 안인 열의 최대 차이는40.924px다. 문 모서리에서
상부 벽이 바닥을 가리는 경계는 물리적인 벽 하단 선분과 같지 않다. 기존 s2v14의
60.86%는 그 expected_rows sentinel 기준으로 보존하고 새 분해와 분모를 섞지 않는다.
s1045/47은 FOV 판정 차이0, 화면 안 투영 차이 최대0.000346/0.000149px다.

표준 방법/채택 범위:
- [ROS SelfMask](https://docs.ros.org/en/noetic/api/robot_self_filter/html/classrobot__self__filter_1_1SelfMask.html):
  센서에서 로봇 형상에 먼저 닿는 ray 뒤의 측정을 SHADOW로 제외한다. 이번 코드도 이
  교차 규칙을 사용하며, 실측 TF 대신 자기 명령 FK·고정 geometry와 개도 sweep을 쓴다.
  이 제약과 2mm 여유·box 근사 때문에 미세한 틈의 가시성은 보수적으로 제외할 수 있다.
- [ViSP 공식 구현](https://github.com/lagadic/visp/blob/master/modules/tracker/mbt/src/klt/vpMbKltTracker.cpp):
  `faces.setVisible`, clipping/scanline visibility 후 보이는 polygon 특징만 추적한다.
  이번에도 invalid 열을 missing으로 빼며, Nav2의 max-range hit나 관측 불일치 벌점으로
  넣지 않는다. prior 95% 공통 열 조건은 우리 불확실성 제약을 위한 명시적 선택이며
  ROS/ViSP의 검증된 공통 기본값이라고 주장하지 않는다. 잘못된 prior에서 재위치 추정을
  제한할 수 있고 RGB cargo 분할 누락도 남는다.
- [PL-SLAM](https://arxiv.org/abs/1705.09479): point+line 특징 결합의 공개 원 논문.
  벽 상단/문 기둥은 공개 지도의 wall 높이0.4m·벽 끝점·door_1 좌표로 예측 가능한 후보다.
  다만 현 HIGH에서 **벽 상단 가시 열0/95232**라 상단만 바꾸는 것은 해결책이 아니다.
  문 기둥 세로선은 기하상 보일 수 있는 frame이0/585,106/240,30/167이며 연속 보정을
  보장하지 않는다(4mm 간격 점 표본, 앞쪽 벽 가림 포함; 실제 edge 검출 시험은 아님).
- 바닥 체커는 `sim/masterpi_scene_v2.xml:7–8,23`의 `ground` checker texture와
  `groundmat texrepeat=14 14`로 렌더링된 고정 무늬다. **공개 지도 JSON에는 격자 간격,
  좌표 원점/위상, 방향, texture 항목이 없다.** 따라서 현재의 허용 정적 지도에 등록된
  절대 좌표 랜드마크가 아니다. 렌더링 설정을 숨겨진 세계 격자 정답으로 가져오지 않았다.
  자기 연속 RGB에서 상대 선/flow를 추적하는 것은 가능하지만, 반복 무늬의 절대 위치는
  모호하며 실제 바닥 격자를 측량해 공개 지도에 등록하는 검증과 구분해야 한다.

위 링크는 2026-10-07 공식 코드/원 논문에서 확인했다. 이번에는 대체 특징 추적기나
지도·PR405 코드를 구현/변경하지 않았다. 확률 가중은 존재하지 않는 벽 하단 관측을
만들 수 없으므로 마스크 통과 뒤에도 관측 공백과 위치 오차를 함께 판정한다.

### 운반 자세 대조 — 기하만, 자세 변경 없음

실물 스택의 현재 delivery 경로는 `scripts/red_block/pick.py:396–399`에서
`physical_state_machine_reference.py:111`의 `{3:600,4:2200,5:1400}`으로 이동하고,
`place.py:203–218`은 차체 가속 전 servo5=1400으로 되돌리고 **정지한 뒤**1550/1625의
near/close view를 선택한다. `sim/real_stack_adapter.py:75–95`는 이 스택을 직접 가져온다.
S2 HIGH `{3:896,4:2035,5:1894}`는 `zone_pair_highpose.py`가 새로 정의한 별도 자세다.
실물 코드 경로 확인이지 해당 PWM에서의 실물 하중 가시성을 새로 측정한 것은 아니다.
`poses.py`의 옛 `POSE_CARRY={960,2410,1215}` 별칭과 현재 delivery 경로도 구분한다.

아래 표는 **같은 저장 평가 궤적**에 명령 FK·고정 v3 mount만 바꿔 계산한 반사실 기하다.
실제 자세를 바꾸거나 물리/하중 안정성을 시험하지 않았고, 카메라/지도 보정표로 채택하지
않았다. 아래 loaded actual 결과와 혼합하지 않는다. 분모는 각 seed의 모든96열이며,
보이는 하단 비율(벽끼리 가림·자기 링크 가능 가림 제외)은 결과 표에 기록한다.

| 자세(servo3/4/5) | 높이 m / pitch° | 중앙열 바닥 x 범위 m | 하단 가시 비율 s1045 / 1046 / 1047 |
|---|---|---|---|
| HIGH (896/2035/1894) | 0.193 / -30.05 | 0.346–1.188 | 8.81% / 36.84% / 6.98% |
| VIA110 (891/2036/2054) | 0.154 / -44.99 | 0.272–0.523 | 1.56% / 11.15% / 0.03% |
| VIA130 (981/2152/1917) | 0.174 / -35.00 | 0.312–0.807 | 3.53% / 25.67% / 2.84% |
| REAL_DELIVERY_CARRY (600/2200/1400) | 0.227 / -27.08 | 0.326–1.736 | 41.96% / 45.18% / 19.21% |
| LEGACY_POSE_CARRY (960/2410/1215) | 0.248 / 3.07 | 0.835–∞ | 96.17% / 59.80% / 96.08% |

### 실제 HIGH 하단 가림 분해 (평가 전용)

아래는 각 표본의 **전96열** 분모다. '상부 이탈'은 실제 벽 하단이 위쪽 시야 밖,
'cargo'는 화면 안 하단 광선에 실제 블록이 먼저 닿은 수, 자기 가림은 명령 형상 상한이다.
시야 밖은 가림과 중복 집계하지 않는다.

| seed | 전체 열 | 위 밖 | 아래 밖 | 블록 가림 | 집게/팔/차체 가능 가림 | 다른 벽 가림 | 가림 없는 하단 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1045 | 56160 | 53378 | 0 | 31 | 0 | 0 | 2751 |
| 1046 | 23040 | 12784 | 2951 | 112 | 0 | 1 | 7192 |
| 1047 | 16032 | 15305 | 0 | 0 | 0 | 0 | 727 |

기존과 같은 **검출 열**만 분모로 잡으면 다음과 같다.

| seed | 검출 열 | 위 밖 | 아래 밖 | 실제 하단 화면 안·가림 없음 |
|---|---:|---:|---:|---:|
| 1045 | 42100 | 39996 (95.00%) | 0 (0.00%) | 2104 (5.00%) |
| 1046 | 16247 | 9857 (60.67%) | 65 (0.40%) | 6325 (38.93%) |
| 1047 | 10445 | 9916 (94.94%) | 0 (0.00%) | 529 (5.06%) |

검출 열에서 블록·집게·팔·차체 가림으로 분류된 하단은0이다. 전96열에서 블록 가림도
31/56160,112/23040,0/16032에 그쳤다. **이 자료의 관측 부족을 자기 가림만 제거해서
해결할 수 없다.** 가림이 존재하지 않는다는 일반 주장이나 다른 팔 자세의 보장은 아니다.

원본 육안 대조: s1045 `01734.jpg`(88.0s, 하단96열 전부 위 밖), s1046 `03554.jpg`
(179.0s, 위40/아래56열), s1045 `12014.jpg`(602.0s, 블록이 하단31열을 가림)를
직접 열었다. raw fisheye 영상의 색 경계와 undistorted 하단 좌표는 서로 다른 좌표계이며,
단순 회색 경계가 검출됐다고 실제 벽 하단이라고 보지 않는다. 모든 입력 JPEG hash를
확인했으며 원본 이미지를 편집·삭제하지 않았다.

### 고정 후보 재생 결과 — 새 full DEV 입장 불가

기준 `e2a4558c` → 구현 `79cfd27d` 순서로 커밋·push한 후, 저장 RGB13794/6500/5101장과
각 원래 명령을 전부 재생했다. 누락/남은 pose0, 모든 입력 frame hash 확인, GT filter
입력0·SIM/렌더/모델 호출0이다. AMCL 계수·보정표·구동 모델과 seed별 원래 옵션은 고정했다.
새 Runtime 인자 `visibility_mask=command_geometry_v1`은 기본 off이며 **오프라인 후보**로만
구현했다. 실행 번들/CLI는 아직 허용하지 않는다. 관련 모듈2파일 시험12개 통과(기본 off의
명령·record byte 동일, ray/box 교차, unknown 무갱신, 보이는 열의 가중 갱신, 기하 해석해).

| seed | 기존 AMCL → visibility 갱신 수 | 최장 공백 SIM초 | 운반 RMSE m | visibility p90 m | 판정 |
|---|---:|---:|---:|---:|---|
| 1045 | 62 → 67 | 184.85 → 253.30 | 1.644 → 1.685 | 2.234 | 미달 |
| 1046 | 30 → 7 | 20.20 → 62.75 | 2.133 → 2.099 | 3.942 | 미달 |
| 1047 | 21 → 3 | 40.00 → 117.30 | 0.623 → 0.658 | 0.893 | 미달 |

원래 실행 RMSE1.775/1.682/0.351m, 같은 보정 hard receipt1.826/1.996/0.607m도
함께 기록했다. s1046은 AMCL 대비 RMSE만 약간 줄었지만 원래 실행보다 나쁘며, 세 seed
모두 공백≤30초 조건을 실패했다. 업데이트 수는 absolute fix나 옳은 위치의 보장이 아니다.
visibility attempt 중6열 미만은5538/5605,3355/3362,2344/2347회였다. 시도 횟수는
실행별20Hz 후보 검사 횟수이며 독립 관측 수가 아니다. mask 단계에서 검출 열 자체가
자기 형상/cyan 영역에 닿아 제외된 수는 모두0이었고, 주로 prior에서 하단의 FOV
가시성이 확인되지 않아 열을 제외했다. 이 점도 '마스크가 새 관측을 회복했다'고 해석하지 않는다.

결론: **visibility는 유효하지 않은 측정을 모름으로 다루지만, 하단 자체가 없는 긴 구간을
채우지 못했다.** 단일 후보 평가를 여기서 마치고 새 seed·번들·full DEV를 실행하지 않는다.
관측 부재를 gate/잡음/visibility threshold 완화로 다시 튜닝하지 않았다. 원본 구동·팔 자세·
카메라 mount/FOV·공용 `sim/camera_robot_port.py`·다른 제어기·PR405는 변경하지 않았다.
다음 후보에는 실제 시야에 들어오는 특징/정지 재관측의 별도 근거와 검증이 필요하다.

재현 산출물: `/Users/changmin/projects/ugrp/outputs/s2-visibility-20261007/`의
`s1045/1046/1047-command_geometry_v1.json`, `geometry-shadow.json`,
`feature-geometry.json`, `summary.json`; 커밋용 `visibility-summary.json`은 summary와
바이트가 같다. 중간 `geometry.json`/로그도 보존했다. `replay_visibility.py`는 평가 raw를
읽지 않으며 `analyze_visibility.py`/`feature_visibility.py`/`summarize_visibility.py`만 별도
평가 GT를 읽는다. 각 source raw·코드·criteria SHA256은 summary/개별 replay에 기록했다.
실행 명령을 고정한 오프라인 비교이며 폐루프 운반 성공이나 실제 실물 보정으로 승격하지 않는다.

잠금은 읽기 전용 status가 null임을 확인했다. 새 SIM/렌더를 띄우지 않았으므로 acquire/
release 및 새 ugrp_session은 없다. 기존 다른 작업 세션/서버/잠금은 건드리지 않았다.
새 영상은 없고 기존 S2 대표 영상/원본을 보존한다. PR #406 DRAFT·병합 금지를 유지한다.

TensorBoard: 새 snapshot `1007-s2-visibility`, 15뷰·132스칼라의 원본→event→live API
수치 일치, HParams/source SHA 확인. 사용자 수치 대조 범위대로 브라우저는 열지 않았다.
[저장된 수치 보기](http://127.0.0.1:6006/?runFilter=%5E1007-s2-visibility%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_update_gap_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_xy_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_xy_p90_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmeasurement_receipts%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Ffull_dev_runs%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) / `visibility-delivery-verification.json`.
기존 서버 PID52016·공용 logdir 유지, 공용 view 파일은 쓰기 직전 다시 읽고 자기 키
`s2_visibility_20261007`만 추가했다. 기존 snapshot은 바꾸지 않았다.
구현 SHA79cfd27d의 CI preflight27초 통과·나머지 일부 실행 중을 확인했으며 CI 완료/병합으로
보고하지 않는다. 로컬 시험은 변경 모듈2파일의12개만 수행했다.

## s2v17 — 사용자 실물 단독 운반 확인과 팔 자세 일치 (2026-10-07)

**사용자 확인:** 실물 MasterPi로 혼자 블록을 옮길 때 카메라에 벽과 바닥이 보였고,
블록이 시야를 크게 가리지 않았다. 함께 운반하는 경우에는 적용하지 않는다.
따라서 위 s2v16의 검출 열61–95%에서 하단이 시야 밖인 결과는 **SIM/실물 불일치**로
분류한다. 실물 단독 운반의 본질적 관측 한계로 일반화하지 않는다. s2v16 raw와 수치는
그대로 보존한다. 다만 사용자 관찰은 실물 장면의 거리·벽 하단 열별 비율·mount 각도
실측치는 아니므로 불일치 전체를 한 원인의 확정 효과로 수치화하지 않는다.

### 결과 전 고정 기준

`real-carry-criteria.json`을 새 계산 전에 커밋한다. 후보는 실물 현재 코드와9월2일 기록의
`carry_pose=real_delivery_v1` 하나(기본 off)이며 S2 단독 DEV에만 적용한다.
기존 HIGH와600/2200/1400 자세를 고정 v3 mount로 비교하고, 이전에 고정한
처짐−0.02711 rad를 각각 더한 민감도만 함께 계산한다. mount/FOV/내부 보정은 바꾸지 않는다.
저장 운반 RGB의 **모든 시각**에서 평가 궤적을 이용해 기하상 관측 기회(6열 이상)의
최장 공백≤30 SIM초를 확인한다. 실제 영상 갱신/fix나 위치 정확도로 바꾸어 부르지 않는다.
저장 HIGH RGB에는 새 운반 자세에서 새로 보일 픽셀이 없으므로, 명령·보정만 바꿔
재생한 fix/RMSE는 유효한 비교가 아니다. 실제 새 자세 영상의 fix 공백≤30초·운반 RMSE
개선까지 입증된 경우에만 새 seed full DEV를 허용한다. 기하만 통과해도 충분하지 않다.
미달/입증 불가이면 새 시뮬레이션·seed 예약 없이 보고한다. GT는 별도 기하 평가에만 쓴다.

### 확정한 불일치와 아직 측정하지 못한 항목

`real-carry-evidence.json`에 ZIP 전체/선택 member와 코드의 SHA256을 남겼다.
원본 `/Users/changmin/projects/ugrp/outputs/experiment-archives-20260907/real_traces-20260907.zip`
(SHA256 `22fba4801d67464203c5607259e0aae31bac99730e9e9d3233f130ca0ffd949c`)을
읽기 전용으로 검증했다. 원본을 다시 풀거나 변경하지 않았다.

| 항목 | SIM / 실물 근거 | 판정 |
|---|---|---|
| 운반 servo3/4/5 | HIGH=896/2035/1894, 현재 실물 delivery=600/2200/1400; 실물−SIM=-296/+165/-494 PWM | **발행 자세 차이 확정** |
| 고정 기하의 카메라 높이/optical pitch | 같은 v3 mount에서 HIGH=0.193199 m/-30.05°, 실물 명령=0.227007 m/-27.08° | 명령 차이 효과 +33.808 mm/+2.97°; 실물 각도 실측 아님 |
| v3 mount | 공구축 위+10°, 렌즈 위치(52.982,0,28.152)mm, 기존 K/D 그대로 | +10°는 사용자 가시성 목표 후보, **실측 장착각 아님**; 실물과의 차이는 미확정 |
| 하중/기구 처짐 | HIGH 무하중 PnP 약-29.90°/0.19315m 대비 저장 loaded HIGH 약-32.7°/0.1872m | 총 차이 약-2.8°/-6mm; 실물 처짐 측정 없고 관절/차체 분리 불가 |
| 벽까지 거리 | s2v16 위쪽 이탈 열의 벽 하단 거리 중앙값1.701/3.230/2.797m, 실제 HIGH 중앙열 바닥 최대 약0.965m | SIM 먼 벽 하단이 위 밖; 실물 같은 거리/장면의 대조 자료 없음 |

실물 근거는 `sim/real_stack_adapter.py:75–95`가 직접 가져오는 스택이다.
`pick.py:396–399` → `physical_state_machine_reference.py:111`의
`DELIVERY_CARRY_POSE={1:1500,3:600,4:2200,5:1400}`;
`place.py:203–218`도 차체 이동 전에 servo5=1400으로 되돌린다. `robot.py:209–212`의
`move_pose`는 `poses.py:64–80`의 `servo_steps` 순서/시간을 쓰며, `move_servo`는
이동 시간+0.15초 기다린다. adapter가 HIGH로 운반 명령을 바꾸는 경로는 없다.
`poses.py`의 옛 POSE_CARRY=960/2410/1215는 현재 delivery 호출의 목표가 아니다.
`docs/archive`에서는 이를 대체할 실측 carry PWM/장착각 기록을 찾지 못했다.

- 2026-09-02 `real-19bb30fd/pick-b5f9a960` event65: 마지막 JPEG는
  `{1:1500,3:600,4:2200,5:1900,6:1667}`. event67: servo5 **1900→1400,0.625초**,
  event68: 발행 상태600/2200/1400 확인. member SHA256
  `0386e4fc17272d14a2017f710559cf1ba662cd8f39ae6e937bc370bdd5aa4424`.
- 2026-08-31 `real-d4872c04/pick-b99f23a8` event73: 마지막 JPEG의servo5=1900;
  event75: **1900→1500,0.5초**. member SHA256
  `a30ca75bfb74c9f4da77ba607eb87f9f81f0b2119dc973773eac1bf3a51ec2f5`.
  더 옛1500 후보를 결과를 본 뒤 선택하지 않는다. 최신1400 기록+현재 코드를 고정한다.
- 9월2일 `real-da601e70/pick-255314b9`는 집게를 다시 여는 실패 경로로, 운반 근거에서 제외한다.

이 ZIP의 해당 pick span에는 최종 운반 명령 **이후** JPEG가 없다. 앞서 v3 검토에서 비교한
실물 집기 뒤 영상의1900 자세와 SIM HIGH도 서로 다른 자세였다. 그 영상의 블록 면적은
실물 **운반 자세**의 mount 보정값이 될 수 없다. 사용자의 이번 실제 단독 운반 관찰은
독립적인 정성 근거로 기록하고, 발행 PWM을 실제 관절각/물리 성공으로 부르지 않는다.
실물 기록의 pan1667을 S2 세계 방향에 복사하지 않고, 기존 S2 neutral pan1500을 유지한다.

### 적용 방법·참고 자료와 범위

보정 문제는 고정 장착 변환과 팔 자세 변환을 구분하는 eye-in-hand 절차로 다룬다.
[OpenCV calibrateHandEye 공식 문서](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)처럼
고정 표적의 여러 자세2D–3D 대응(PnP)과 그리퍼→베이스 변환을 결합해야 장착 변환을
식별할 수 있다. 블록이 조금 보인다는 한 시야로 장착각·관절 처짐·파지 깊이를 함께
추정하지 않는다. 이 작업에서는 그런 실측 자료가 없으므로 **mount/FOV/K/D는 그대로**다.
현재 real stack의 명령 순서/시간을 그대로 재사용하는 것이 확인된 자세 차이를 고치는
최소 수정이다. 웹 표준 절차를 수행한 실제 보정 결과라고 주장하지 않는다.

`harness/zone_solo_cyan_real_carry.py`의 `carry_pose=real_delivery_v1`(기본 off)은
S2 Runtime 후보로 구현했다. 기존 lift/in-hand 기록 뒤에 실물 순차 서보 명령으로
운반 자세에 들어가고, 운반 도착 뒤 HIGH로 되돌린 다음 기존 하강 경로를 따른다.
**전체 실물 pick/place 궤적 복제는 아니며**, 운반 목표 자세와 그 전환 순서/시간만
현재 실물 코드에 일치한다. 실제 파지 유지·충돌·속도 성능은 미검증이다. gripper1500은
닫힘 명령일 뿐 접촉 증거가 아니고, dev_light 시각 unknown 기록 정책도 그대로다.
기본 off는 이전 Runtime의 명령·record JSON byte 동일 시험으로 고정했다.

새 자세를 HIGH인 것처럼 가장하지 않는다. 현재 공용 provider의 loaded 관측은 HIGH만
보정되어 있어 새 자세는 predict-only다. 새 자세의 고정 카메라 보정, loaded 운동 모델,
HIGH 전용 LK 정체 감시 역시 별도 검증이 필요하다. 이를 누락한 채 full에 넣지 않도록
v123 번들 검증기는 non-off carry_pose를 명시적으로 거절한다. 새 CLI/실행 번들/번호는
등록하지 않았다. S2 외 제어기, 공용 camera_robot_port, paired HIGH, PR405는 수정하지 않았다.

기준 커밋`fb147a91` → 후보 커밋`6e4c7bb7` 순서로 push한 뒤 계산한다.
시험 `test_s2_real_carry.py`+`test_s2_real_pregrasp_policy.py` **8개 통과**:
기본 off byte 동일, 실물 목표/순서/시간, 실제 Runtime의 carry 전환·HIGH 복귀·하강,
명령 상태 오류, v123 미허용, 새 자세에 HIGH 보정 미적용, 기하 공백 집계,
기존 real_pregrasp+unknown 기록 후 carry 진행. 첫 시험의 fixture camera_profile 누락과
추가 옵션을 v123 검증기가 무시하는 문제를 각각 고쳐 통과 후에만 커밋했다.

### 전체 저장 시각의 기하 평가 — full DEV 미실행

s1045/46/47의 운반 구간 **11690/4807/3356 frame**, 총19853시각을 계산했다.
분모는 각각1122240/461472/322176열(프레임당96열)이다. 원래 HIGH 명령인 것을
매 frame 확인했다. 두 자세 모두 같은 저장 평가 궤적·지도·K/D·mount를 사용했고,
새 자세의 블록 위치를 옛 GT로 옮겨 놓지 않았다. 새 cargo 가림·실제 픽셀 검출·prior
오차를 무시한 **낙관적 기하 관측 기회**이며 제어 입력이나 보정 fitting에 GT를 쓰지 않았다.
명령 기반 자기 형상 가림을 더해도 이 하단 가시 열 집계는 같았다.

| seed | HIGH nominal 가시율 / 공백 초 | REAL nominal 가시율 / 공백 초 | HIGH+고정 처짐 가시율 / 공백 초 | REAL+고정 처짐 가시율 / 공백 초 |
|---|---|---|---|---|
| 1045 | 8.85% / 481.05 | 42.06% / 104.80 | 6.90% / 483.25 | 24.91% / 316.65 |
| 1046 | 36.88% / 41.45 | 45.31% / 40.35 | 33.81% / 44.80 | 40.53% / 40.00 |
| 1047 | 6.95% / 87.85 | 19.33% / 73.45 | 5.58% / 87.85 | 11.14% / 85.40 |

공백은 **6열 이상 실제 하단이 기하상 보일 기회** 사이의 최장 시간이며, carry 시작/끝도
포함했다. 문맥상 fix라고 부르지 않는다. 1열만 요구한 더 낙관적인 REAL nominal 공백도
98.55/39.75/71.35초로 모두30초를 넘는다. 따라서 보정/게이트를 완벽하게 가정해도
이 저장 경로·고정 mount·지정 자세 조합의 관측 기회가 기준에 미달한다. 새 폐루프 경로가
같을 것이라는 주장은 아니며, 이 경로를 보정 학습/확증 seed로 재사용하지 않는다.

nominal HIGH→REAL의 중앙열 바닥 범위는0.346–1.188m→0.326–1.736m다.
이전 고정 처짐−1.5533°를 더하면 REAL의 최대거리는1.472m, HIGH는1.062m로 줄어든다.
이 처짐은 새 실물 자세의 측정값이 아니며 민감도 비교일 뿐이다. 명령 차이만 고쳐도
하단 가시 비율은 개선되지만 실물 관찰과의 전체 불일치가 해소됐다고 확정할 수 없다.
특히 mount 각도와 실제 loaded 자세·파지 위치의 대응 자료가 남아 있다.

**판정: 기준 미달, full DEV 0회.** 새 자세의 실제 fix 공백/운반 RMSE는 null(미측정)로
기록했다. HIGH JPEG에 새 자세 보정만 대입한 허위 재생은 하지 않았다. 현재 보정표21자세에
600/2200/1400은 무하중/하중 모두 없으며 기존 provider도 loaded HIGH 밖에서는 관측을
쓰지 않는다. 새 옵션을 실행 번들에 허용하지 않고 기본 off 상태의 S2 후보로 남긴다.
추가 자세/mount 후보 탐색, 물리·정지 렌더, 새 seed·번들·영상 생성은 모두0이다.

raw/파생 기록: `/Users/changmin/projects/ugrp/outputs/s2-real-carry-20261007/`의
`geometry.json`, `rows.jsonl`, `geometry.log`; `real-carry-summary.json`은 geometry.json과
byte 동일하다. `archive-evidence-v2.json`은 ZIP에서 읽은 선택 사건의 파생본이고, 최초
`archive-evidence.json`은 event 키를 잘못 조회해 선택 명령이 비었던 중간 기록으로 보존했다.
최종 검증 근거는 커밋한`real-carry-evidence.json`의 kind/명령·pose·is_robot=true/dry_run=false다.
원본 실행/프레임/ZIP과 과거 결과는 그대로 보존했다.

계산은 오프라인이며 agent_lock status=null을 확인했고 acquire/release·새 ugrp_session은
필요하지 않았다. 물리·학습·wall/SIM 비교를 실행하지 않아 새 wall/SIM 수치는 없다.
기존 TensorBoard 서버/다른 작업의 프로세스·잠금은 변경하지 않았다. PR #406 DRAFT 유지,
병합하지 않는다. 후보6e4c7bb7의 ci-preflight는 통과했고 전체 CI 일부는 실행 중이다.

TensorBoard 새 snapshot `1007-s2-real-carry`: **12뷰·108스칼라**의 원본→event→live API
수치 일치 및 HParams/source SHA를 확인했다. 실제 fix/RMSE/물리 성공을 생성하지 않고
`GEOMETRY_NOT_FIX`로 표시한다. 사용자 수치 대조 범위대로 브라우저는 열지 않았다.
[새 기하 수치 보기](http://127.0.0.1:6006/?runFilter=%5E1007-s2-real-carry%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fvisible_bottom_fraction%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_opportunity_gap_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Ffull_dev_runs%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) / `real-carry-delivery-verification.json`.
공용 view 파일은 쓰기 직전 다시 읽고 자기`s2_real_carry_20261007`키만 추가했고, 기존
snapshot/서버PID52016과 과거 영상은 보존했다. 자료는 로컬이며 raw 원격 백업으로
보고하지 않는다. 소스·요약·README는 GitHub PR #406에 보존한다.

## s2v18 — 사용자 승인 새 자세 full DEV 1회 (실행 전, 2026-10-07)

사용자는 옛 HIGH 궤적의 기하 공백을 새 자세의 실제 fix 예측/실행 거절 근거로 쓰지
말고 dev_light로 실제 한 번 운반하라고 지시했다. 이 결정은 s2v17의 full 입장 제한을
**이번 S2 탐색 DEV 1회에 한해 대체**한다. 이전 자료·기준·실패 판정은 바꾸지 않는다.
새 seed **1049**, slot **P1-2**, 목적지B/door_1, stage place를 실행 전에 등록한다.
main+열린 PR16개 전체 번호/seed 조회: `reservation-scan-v124-full.json`.
이 브랜치의 미사용 예약 **zone-s2-realism-v124 / workflow7.17.0**을 등록한다.
1048은 과거 번호 예약만 있었으며 사용하지 않는다. 다른 seed의 결과와 합산하지 않는다.

조합: freeze_v1, carry_pose=real_delivery_v1, 무하중 RGB-PnP 표+고정 처짐−0.02711rad,
visibility_mask=command_geometry_v1, 기존 AMCL likelihood-field 측정,
v7_pulse_cal_v1, accepted_scan_v1 관측 격리, lk_pulse_v1 RGB 정체 기록,
real_pregrasp_v1 blind 파지/inhand_rgb_v1 확인은 log_only_v1, setdown_relook=off.
새 옵션은 기본 off, 구 번들/제어기는 그대로 둔다. 관측 부재·unknown·σ·가드류는
멈췄을 곳만 기록한다. 실제 낙하/집게 이탈/기울기/실행 오류 및 유한 시간 상한은 중단한다.
평가 전용120초/1cm 정체 감시 유지. case1800초/기존 Runtime900초/wall10800초 유한 상한,
ENOSPC는 HOST_ERROR, raw 보존·seed 재사용 없음. 이번 실행 뒤 원인 하나를 지목하고 수정하지 않는다.

무하중 표에 없는600/2200/1400 자세만 기존 정지 체커보드2fit+1holdout 절차로
보충한다(`--pose-set real_carry_v1 --states unloaded`). agent_lock/ugrp_session으로
짧게 capture하고 기존21자세 표는 보존한다. 하중 파지 지그 재시도·weld 없음.
고정 표적 기하+검출 RGB corner의 solvePnP, 재투영 RMS≤1px 기준은 기존 그대로다.
[OpenCV 공식 PnP 절차](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html)를 따른다.
새 보정 자세의 처짐은 실측이 아닌 이전 고정 근사로 명시하고 mount/FOV/K/D는 유지한다.
새 운반 자세를 provider/LF/가림 mask/LK에서 명령으로 인식하도록 S2 인스턴스에만 연결한다.
GT는 별도 결과 평가에만 사용한다. 단독 DEV freeze 제한과 no-model 조건은 유지한다.

실행 전 연결 완료: 무하중 추가 보정은 source`b6a54e3e`,
`outputs/s2-real-carry-cal-b6a54e3e-20261007/`에서3/3장 검출,
fit RMS0.1225px·holdout0.1894px, SIM10.5초/wall38.397초였다. 새 immutable 표
`configs/calibration/s2_camera_v3_unloaded_sag_v1.json`은 기존21자세를 그대로 두고
실물 carry1자세를 더한다. loaded는 무하중 표 복사+고정 광학 right-axis 회전−0.02711rad,
높이 보정0이며 실측 loaded 보정이 아니다. PF·벽 투영·CyanVision은 같은 인스턴스 표를
사용한다. 새 pose의 own-command8초 settle 뒤 관측이 활성화되고 HIGH/새 carry 외
loaded transit은 predict-only다. 기존 pulse 모델은 HIGH에서 새 자세로 전달한 근사임을
bundle/result에 명시한다. 공유 camera_robot_port와 다른 제어기는 바꾸지 않았다.

가시성은 이전 고정 AMCL 후보의 측정 입구에 적용한다. 가시성/자기/cargo mask에서
모름인 열은 PF 가중을 바꾸지 않으며 loaded valid view의 잔차 hard veto 대신 기존
AMCL hit/random soft weight를 사용한다. `accepted_scan_v1` 표시는 이 조합에서
기존 hard gate와 동일한 채택 건수를 뜻하지 않고, 실제 적용 순서를 bundle/record에
명시한다. LK도 real carry 명령을 인식하며 정체 의심은 기록만 한다.
시험3파일(`test_s2_real_carry_dev`, `test_s2_likelihood_field`, `test_s2_visual_fix`)
**17 passed**: off 명령/record byte 동일, 표/처짐 provenance, 인스턴스 격리, 새 pose의
실제 provider 관측·가시성 mask·soft update·LK 호출, 예전 seed/불완전옵션/S3·짝·연구 거절.

실행 환경 기록: 도구 셸이 nice=10을 상속해 첫 calibration launcher는 SIM 시작 전에
정상 우선순위 검사에서 종료했다. launchd를 통해 세션·드라이버·실행기 nice=0을 확인하고
보정1회 완료했다. `launchctl submit`의 재시작 속성으로 뒤따른3회 시작 시도는
기존 output 거절로 SIM 없이 끝났으며 해당 job을 제거했다(원본 유지). full DEV에는
**RunAtLoad=true/KeepAlive=false**인 한 번만 실행하는 명시적 plist를 쓰며 완료 후
bootout한다. renice/nice/taskpolicy는 사용하지 않는다. agent_lock와ugrp_session은
기존 launcher가 관리한다. 보정 종료 후 lock=null·세션 stopped를 확인했다.

실행 후 평가 규칙: 운반 pose RMSE는 지연된 t_est에 평가 궤적을 보간해 계산한다. 실제
벽 하단 가시율은 운반 중1 SIM초 간격, 실제 카메라/블록 평가 기하와 정적 벽·자기 명령
형상 경계로 집계하고 전96열/검출열 분모를 둘 다 기록한다. GT는 Runtime이 닫힌 뒤
posthoc evaluator만 읽고 result/eval_only에 저장한다. AMCL 갱신 수를 절대3-DOF fix
보장으로 부르지 않는다. B 남은 거리는 cyan 중심→B 구역 경계 및B 중심을 구분한다.

실행 전 최종 검증: 같은 관련3시험17개가31.83초에 통과했다. 새 posthoc evaluator는
보존된s1047을 읽기만 하여167개1Hz프레임 hash/실제 투영과RMSE를 계산하는 경로를
확인했다(`outputs/s2-real-carry-evaluator-check-20261007.json`). 이는 evaluator 검증이며
새 운반 자세의 실행 결과가 아니다. 이전 raw/결과는 수정하지 않았다.

### s1049 결과 — 집기 전 탐색에서 종료, 새 운반 자세는 미검증

실행 SHA **a8ab38b81c87ff5645c2db1443fdfe619f03f0d6**, 번들 **zone-s2-realism-v124**,
workflow7.17.0, seed1049/P1-2/place. 옵션21개는 원본 bundle/result와
`full-real-carry-summary.json`에 전부 기록했다. source_changed_during_run=false,
단독 DEV freeze ON, model_calls=0, 재실행0. PR #406은 DRAFT/미병합이다.

| 항목 | 실제 기록 |
|---|---:|
| 종료 | STAGE_FAILED / CYAN_NOT_UNIQUELY_VISIBLE (제어74.10초) |
| lifted / inside B | false / false |
| floor / stable | true / true — 블록은 원래 바닥에 그대로, 내려놓기 성공 아님 |
| 운반 진입 / 운반 시각 가중 갱신 | 0 / 0 |
| 운반 최장 fix 공백·RMSE·실제 벽 하단 가시율 | N/A — 운반 표본 없음, 0이나 실패 임곗값으로 대체하지 않음 |
| cyan 중심→B 구역 경계 / B 중심 | 4.21107m / 4.64630m |
| 재파지 / 집기 확인 | 0 / 미도달(unconfirmed) |
| wall / SIM / wall÷SIM | 164.91719초 / 77.10초 / 2.13900 |
| 명령 / 모델 호출 | 1556 / 0 |
| 멈췄을 지점 기록 | ARM_COLLISION_GUARD 7, REOBSERVATION_NO_FIX 1, POSE_UNCERTAIN 29 |

**요청 대비 실행 경로 결함:** 위 보수적 가드는 계속 진행했으나, 기존
`harness/zone_solo_cyan_v106.py:364`의 두 탐색 시점 소진 분기는
CYAN_NOT_UNIQUELY_VISIBLE을 실제 terminal로 만들었다. 낙하·집게 이탈·기울기 같은
물리 실패가 아니다. `result.visual_unknown_stops=false`는 기존 파지 확인 옵션의
기록일 뿐 모든 시각 종료 분기를 감사한 보장이 아님을 이번 실행이 드러냈다.
raw 상태/판정을 덮어쓰지 않고 이 dev_light 미적용 분기를 별도 요약과TensorBoard에
actual_nonphysical_terminal=1로 명시했다. 최초 유효 파지 관측도 없이 좌표를 지어내
blind 파지했다고 보고하지 않는다. 사용자 지시대로1회 뒤 멈췄으며 수정/추가 실행은 없다.

남은 가장 큰 관측 원인 하나는 **무하중 초기 스캔의 잘못된 위치 수렴**이다.
첫 바퀴 명령12.00초 전 차체의 실제 최대 변위는 **1.086mm**였는데, 추정은
11.80초에 실제(-0.89735,-0.85066) 대신(-0.87028,1.15691)로 가서
**2.00775m / yaw27.2528°** 오차였다. 실제로 이동하기 전 발생했으므로 이 구간의
오차를 v7 구동 미끄러짐으로 설명할 수 없다. 이후 고정된 오위치에서 경로를 만들었고,
마지막74.10초에는 위치오차1.35620m/yaw38.1656°인데 보고σ는0.02046m였다.
마지막 fix_t=12.05초, 초기 partial fix9회(11.65–12.05초) 뒤 갱신 공백62.05초다.
이것은 **운반 fix 공백이 아니라 집기 전 전체 위치 추정**의 진단이다.

두 실제 탐색 state의198개 입력은 cyan0px였다. 이동 중45.10초에는4358px가
보였으나`robots/r3/rgb/00876.jpg`에서 화면 아래로 잘린 부분 블록이며,
이를 유효 정렬/파지 관측으로 간주하지 않는다. 새 보정표의 잔차와 벽 특징 모호성 중
무엇이 초기 오수렴을 만들었는지는 이번 기록만으로 확정하지 않았고 다음 조사 과제로
남긴다. 새 carry 자세의 가시성/AMCL/실제 운반 효과를 실패 또는 성공으로 판정하지 않는다.

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-a8ab38b8-s1049-P1-2-place/`.
관리 기록은 같은 경로의`-managed/manifest.json`, 추가 평가 요약은
`outputs/s2-realism-a8ab38b8-s1049-summary.json`이다. 원본 result·record·궤적·입력목록·
카메라·bundle의sha256은 커밋한`full-real-carry-summary.json`에 있다.
`analyze_full_real_carry.py`를 실제1457프레임에서 실행해 모든sha256과수치를 검증했다.
추정오차의GT는 종료 후 평가에서만 읽었고 제어/성공 전환에 전달하지 않았다.

4배속 자기RGB 영상:
`/Users/changmin/projects/ugrp/outputs/s2-realism-a8ab38b8-analysis/views/s1049-full/execution.mp4`.
SIM1.30–74.10초,640×480/20fps,18.35초(고정 출력fps에 따른 끝 padding 포함),
마지막 정착3초에는 저장RGB가 없어 영상으로 만들지 않았다. 전체decode와HTTP Range,
TensorBoard 영상등록을 확인했다. SHA는`full-real-carry-delivery-verification.json`.

TensorBoard 새 snapshot `1007-s2-real-carry-full-v124`: 새 full 시도1개와 무하중
보정1개, **24 scalar**의 source→event→실제 live API 일치 및 HParams를 확인했다.
기존 s1045 조건은 별도 baseline 링크로 보존하며 성공률 합산/속도 개선을 주장하지
않는다(s1045 freeze ON wall/SIM1.95975, 이번2.13900; 경로·종료 지점이 다름).
공용view는 직전 재조회 뒤 자기`s2_real_carry_full_20261007`키만 더했다. 사용자 요청대로
수치만 대조했고 브라우저 재개방은 생략했다. 기존 서버PID52016/전체logdir는 유지했다.

정리: own session`s2-realism-v124-s1049` stopped, pgid89217/89234 잔여0,
one-shot launchd job bootout, **agent_lock=null**. 다른 세션/프로세스는 건드리지 않았다.
실행 소스 관련17시험 통과 후 커밋·push, 원격ci-preflight24초 통과; 전체 CI 일부는
진행 중이었다. 데이터/영상은 로컬이며 원격 raw 백업으로 보고하지 않는다.

[새 실행과 별도 baseline 수치 보기](http://127.0.0.1:6006/?runFilter=%5E%281007-s2-real-carry-full-v124%7C1007-s2-realism-full-v121-verified%29%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Flifted%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Finside%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fstationary_max_position_error_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fremaining_to_b_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fwall_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fsim_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fcommands%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries).

## s2v19 — 정지 스캔 이탈 원인과 ROS AMCL 절차 (사전 기준, 2026-10-07)

물리 실행 없이 s1047/s1049의1.30–12.00초215개 자기RGB·명령을 그대로 재생한다.
`saved` 두 조건은 저장 pose와 최대차이0(기준1e-9 이내)를 확인했다. 평가GT는 Runtime
종료 후에만 읽는다. option OFAT와 PF RNG seed 교환을 분리하며 이 자료는 탐색 전용이다.
full 1.54338/1.94347m → camera_calibration off0.01050/0.02675m(스캔 끝오차).
carry_pose/visibility_mask/visual_update를 각각 끄면 full과 pose가 동일하다. AMCL off는
의존성상 mask-off 상태에서만 가능하므로 mask-off→measurement-off 한 항목 차이로
비교했으며 역시 동일하다. 모두 unloaded라 기존 세 후보 측정 훅 범위 밖이다.
RNG1047↔1049 교환은 크기를 바꾸지만 두 기록 모두 새 보정표에서 이탈한다.
즉 통합 변화의 트리거는 새 외부 보정표이며, 그 표를 받는 기존 unloaded 측정 경로를
조사한다. old 표가 물리적으로 옳다는 결론이나 보정 옵션을 끄는 수정으로 대체하지 않는다.

Nav2 원본을 commit235fc5ce55bdf94d9be360fdbca39d89dc0e4f74에 고정해 읽었다.
- [amcl_node.cpp](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/amcl_node.cpp): 첫 유효 센서 갱신은 허용하고 이후 odom dx/dy>0.25m 또는 yaw>0.2rad일 때만 센서 갱신·주기 resample. 포즈/명령 토큰 변경만으로 재허용하지 않는다.
- [기본 likelihood_field](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): hit/random 혼합,1+sum(pz^3), beam skip 없음.
- [likelihood_field_prob](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model_prob.cpp): product likelihood, converged 후만 beam skip, 지나친 skip이면 전체빔 복구. beam skip이 모든 AMCL 모델의 기본 기능은 아니다.
- [pf.c](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf.c): CDF 재표본화, 평균에서 모든 입자가 x/y0.5m 이내일 때 converged. 원본 SHA/로컬 보존본은stationary-amcl-sources.json.

현재 unloaded는 정지 스캔215프레임 중50회 관측 가중,46회 반복 가중,5/6회 resample
(s1049/1047),4개 명령 자세의 새 view를 센서 재갱신으로 취급한다. 새 표 이전도
95회/88반복/5resample이어서 ROS의 정지 갱신 차단과 다르다. 현재 consistency rho=.5,
command-token 재허용·roughening은 이번 새 옵션에서 원본 ROS 절차로 대체할 대상이다.
단일 이상 관측/초기 전역 prior는 ROS도 정답을 보장하지 않으므로, 무조건 성공으로
가정하지 않고 아래 기준을 구현/후보 재생 **전에** 고정한다.

`stationary-amcl-criteria.json`: 두 seed 모두 전체 정지 구간 최대오차≤0.50m,
끝오차≤0.30m, 문턱 미만 정지에서 최초 관측 외 반복 갱신/resample0.
고정 Nav2 기본모델ros_motion_v1을 우선, beam-skip 모델ros_motion_prob_v1은 별도
고정 비교 후보로만 둔다. 계수 튜닝/기준 완화 없음. 둘 다 미달이면 full DEV를 실행하지
않는다. 센서는RGB 지면 교차점, odom은 자기 발행 고정 펄스 모델, N=2000은 기존 latent
plant 크기를 보존하는 차이만 허용한다. 실행 중GT/추가 센서/카메라 변경 없음.
CYAN_NOT_UNIQUELY_VISIBLE은 새 default-off 옵션으로 기존 두 시점 탐색을 다시 하고
멈췄을 곳만 기록한다. 관측하지 못한 target을 발명하거나 파지 성공을 알리지 않는다.
전역 유한 시간 상한/실제 물리 실패 정지는 유지한다. PR #406 DRAFT·병합 금지.


새 full 사전 등록: main+열린 PR16개, 총17 refs의 최대 ID124 다음 **zone-s2-realism-v125 /
workflow7.18.0**, 미사용 **seed1050/P1-2/B/place**를 예약한다. 전체 ref의seed1050
검색 hit0, 원본 실행 폴더0. `reservation-scan-v125.json`에 ref/SHA/ID를 보존한다.
full은 ros_motion_v1의 재생 통과를 검증하는 번들에서만1회 허용한다. 새 보정표와
carry_pose·freeze·visibility·pulse·RGB LK·blind 파지/log-only 기존 조합을 유지한다.
`dev_search=repeat_views_v1`은 초기·재집기 검색 소진 및 정렬 중 cyan소실을
기존 두 시점 검색으로 되돌려 기록만 한다. source code/옵션은 실행 전에 commit/push,
agent_lock·ugrp_session·한 번씩·정상 우선순위, ENOSPC HOST_ERROR, 유한 상한 유지.


후보 재생 판정(기준commit e8e383a1 이후): 기본 ros_motion_v1의 s1047/1049 정지
최대오차0.15944/0.15438m, 끝0.15915/0.15335m, 최초 관측1회·resample1회,
이후 정지 반복 갱신0으로 두 seed 모두 통과했다. `ros_motion_prob_v1`은 최초 product
관측 한 번부터3.04705/2.64664m 이탈하여 미달이다. 아직 converged가 아니므로 원본
조건대로 beam skip이 비활성이며, beam skip이 초기 모호한 관측의 만능 해결책은 아니다.
숫자/각 replay 해시/선택 정책은stationary-amcl-summary.json, 전체raw는
`outputs/s2-stationary-audit-20261007/`. 표준모델의 계수는 튜닝하지 않았다.
최종 후보 파일 해시로 primary/secondary 둘 다 재생했고 앞 재생과 수치가 같았다.
기본 ROS field만 채택한다. 초기 정상 s1047 끝0.0105m보다는 덜 정확하지만 사전
0.30m 이내이며 반복 가중으로 얻은 과신과 구분한다. 실주행은 아직 미검증이다.

새 옵션 `amcl_update`는 기본off이며 `ros_motion_v1`/`ros_motion_prob_v1` 중 고정
표준모델을 선택한다. loaded·unloaded 모두 같은 update 문턱을 사용하고, 이동 문턱
미달에는 기존update(None)도 호출하지 않아 은닉 resample/roughening을 막는다.
기존 frozen PF·공용 camera_robot_port·타 제어기는 수정하지 않았다. 원본 ROS와 다른
RGB/명령odom/고정N 경계를 기록하고 전체 AMCL ROS/KLD 재현이라고 주장하지 않는다.

실행 전 시험: 새test_s2_amcl_update의8개와 변경 없는real_carry_dev4개·likelihood_field6개를 확인했다. 중간 실패는 각도0.2rad 경계의 modulo 반올림(ROS atan2 정규화로 수정), 새 테스트의 fixture 배치 오류(시험만 수정)였다. 최종 후보 재생4개는최종 AMCL파일sha와일치하며 기본off·정지불변·beam fallback·재탐색·실제명령상태실패·새번들/seed거절을검증했다.

### s1050 결과 — 정지 이탈 해소, 들기·내려놓기 도달, B 밖

실행/사전 등록 SHA **97fcb5d2be8cf714d0866e7b53ed461e1c59ccbf**, 번들
**zone-s2-realism-v125**, workflow7.18.0, seed1050/P1-2/place. freeze ON의
단독 S2 DEV 1회다. 옵션23개를 원본 result/bundle과 `full-amcl-summary.json`에
보존했다. 실행 중 소스/입력 변경 false, 모델 호출0, 추가 물리 실행0.
이전 cohort와 합산하지 않는다. default-off 및 기존 출력 byte 동일 시험은 위와 같다.

| 항목 | 결과 |
|---|---:|
| 종료 | STAGE_REACHED_UNQUALIFIED, controller done, failure=null |
| lifted / inside B / floor / stable | true / false / true / true |
| 초기 정지 스캔 실제 최대 이동 / 추정 최대·끝 오차 | 0.691mm / 0.08876m · 0.08639m |
| 초기 정지 센서 갱신 / 재샘플링 | 최초1회 / 1회, 반복0 |
| 운반 구간 | 71.00–236.80 SIM초 |
| 운반 시각 가중 갱신 / 최장 공백 | 0회 / 165.80초 |
| 운반 위치 RMSE / 끝 오차 | 2.19094m / 4.06164m, 평가 전용 |
| 실제 벽 하단 가시율, 전체96열 / 검출 열 | 37.186% / 71.869%, 1Hz 166프레임 |
| cyan 중심→B 구역 경계 / 중심 | 3.54802m / 4.28841m |
| 파지 확인 / 재파지 | probable_held_inhand_rgb / 0회 |
| 원래 자리 확인 | not_evaluated_inhand_selected (실물 blind 파지 + 기록용 in-hand 선택) |
| 멈췄을 지점 | ARM_COLLISION_GUARD 7, POSE_UNCERTAIN 349, VISUAL_STALL_SUSPECTED 3 |
| wall / SIM / wall÷SIM | 674.33213초 / 260.10초 / 2.59259 |
| 발행 명령 / 모델 호출 | 3798 / 0 |

**남은 가장 큰 원인 하나: 가시성 마스크의 사전 확률 조건이 운반 관측을 전부 차단한다.**
`command_geometry_v1`은 자기 가림 외에 PF 입자의 예측 벽 하단이 화면 안일 확률을
95% 이상 요구한다(`harness/zone_solo_cyan_visibility.py:apply`). 운반 중3129회,
검출133331열 중 유지0열이다. 벽이 검출된1900프레임 **전부**에서
prior_view_columns=0이고 검출점의 자기 가림/짐 가림 제거는 모두0이다.
나머지1229프레임은 검출0이며, 사전 시야 조건을 만족하는 열이 생기는239프레임은
모두 검출0프레임에 속한다. 따라서 이번 미갱신은 정지 motion 문턱이 아니라
관측 전에 적용한 prior 가시성 조건에서 직접 발생했다.
실제 카메라/짐의 저장 기하로는 검출7195열 중5171열의 실제 벽 하단이 보였다.
이 가시율은 평가용 기하와 보수적 명령 기반 차체 bound의1Hz 표본이며, 모든
검출이 올바른 벽 경계라는 뜻이나 실제 관절 가림의 정밀 실측은 아니다.

전체 시각 갱신은2.25/19.70/28.25/38.15초의4회뿐이다. 운반 진입 오차0.09872m가
운반 끝4.06164m로 증가했고 마지막 추정(4.3724,-2.0966)m과 실제
(2.0945,1.1922)m이 달랐다. 마지막σ=0.51944m다. 제어기가 B 도착으로 판단해
내렸지만 실제 cyan은(2.10994,1.39143)m에 놓였다. 벽 하단이 실제 보이는데도
사전 위치 분포 때문에 관측을 잃는 문제를 다음 단계로 남긴다. 이번에는 mask 조건
완화·추가 구현·두 번째 실행을 하지 않았다. ROS 기본 field 선택은 초기 정지 이탈을
해소했으나 전체 위치 추정/배송을 해결했다는 주장이 아니다.

`dev_search=repeat_views_v1`의 로그 후 재탐색 분기는 관련 시험에서 확인했다.
새 full은 첫 search에서 cyan을 찾았으므로 해당 재시도 분기의 실주행 발동은0회다.
기록된 보수적 정지359회를 통과해 내려놓기까지 진행했고 실제 물리 실패 종료는 없었다.
표준 cubic field는 beam skip을 사용하지 않으며, product/beam-skip 비교 후보는
오프라인 기준 미달로 실행하지 않았다. 시각 가중 갱신 횟수를 완전한 절대 pose fix
횟수로 해석하지 않는다.

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-97fcb5d2-s1050-P1-2-place/`.
`analyze_amcl_full.py`는 종료된 기록만 읽어5117 입력 프레임의sha256, 초기 오차,
운반 RMSE와 마스크 제거 횟수를 대조했다. 관리manifest·result·평가·record의 원본은
그대로 두고 별도 `full-amcl-summary.json`에 출처 해시를 기록했다.
4배속 자기RGB 영상은
`/Users/changmin/projects/ugrp/outputs/s2-amcl-v125-analysis/views/s1050-full/execution.mp4`
(640×480/20fps/64.10초). SIM1.30–257.10초 입력이며 마지막 정착3초는 저장RGB가
없다. 전체 decode·등록·HTTP Range 검증을 기록한다.

wall/SIM 비교는 조건별 기술 통계만 한다: freeze ON s1045=1.95975,
s1049=2.13900, s1050=2.59259. 경로·종료 단계·추정기 부하가 달라 가속/퇴행의
통제 비교가 아니다. freeze OFF 이전 조건과 결과/성공률을 합산하지 않는다.
own session `s2-realism-v125-s1050` stopped, PID852/853/863/874 잔여0,
one-shot launchd job bootout, **agent_lock=null**을 확인했다.

전달: TensorBoard 새 snapshot `1007-s2-amcl-v125`, 오프라인22뷰와 full1뷰의
**182 scalar**를 source→event→실제 live API까지 대조했다. HParams와 MP4
등록/HTTP206/전체 decode도 통과했다(`amcl-delivery-verification.json`). 기존
서버PID52016/공용logdir를 유지했고, 공용view를 다시 읽어 자기
`s2_amcl_update_20261007`키만 추가했다. 사용자 수치 대조 범위대로 브라우저 UI는
재개방하지 않았다(NUMERIC_ONLY). 기존 baseline은 별도 필터로 남겼다.
[새 수치 보기](http://127.0.0.1:6006/?runFilter=1007-s2-amcl-v125&smoothing=0#timeseries)
(전체 pin 링크는 전달 검증 JSON/dashboard_url).

CI 보충: 실행 SHA의 ci-preflight는 통과했지만
[offline shard4](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37563839425/job/112607188262)는
840.77초에1 failed/1571 passed/13 skipped였다. 시간 초과가 아니라
`test_real_pose_rgb_measurement_visibility_and_lk_are_live`의 고정 XML 형상 builder가
`sim.masterpi_dynamics_v2`를 통해 미설치 MuJoCo를 import한 문제다.
[pytest 공식 선택 의존성 절차](https://docs.pytest.org/en/stable/how-to/skipping.html#skipping-on-a-missing-import-dependency)와
기존 sim 선택시험처럼 이 시험만 importorskip으로 선언하고, MuJoCo가 설치되는
ubuntu-simulation-runtime CI 목록에 해당 파일을 명시해 실제 검증을 유지한다.
제어기/실행 번들은 바꾸지 않았다. 설치 환경4시험 통과와 MuJoCo import를 차단한
단일 시험의 의도된1 skip을 따로 확인한다. 수정 뒤 원격 CI 결과는 아직 확정하지 않는다.

## s2v20 — 예측 가시성 차단 제거 (사전 등록, 2026-10-07)

Nav2 commit `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`의 원본3파일을 다시
내려받아 `observed-amcl-sources.json`에 해시를 고정했다.
[기본 likelihood field](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp)는
센서의 NaN/최대 range만 제외하고 각 입자에서 관측 endpoint의 최근접 벽 거리를
hit/random 혼합으로 가중한다. 예측 벽 하단의 시야 내 확률95% 같은 선행 조건은 없다.
기본 field는 `1+sum(pz^3)`이며 max/short 성분이나 beam skip을 쓰지 않는다.
[beam model](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/beam_model.cpp)은
hit/short/max/random 혼합이다. RGB 검출 부재를 laser max return으로 만들 수 없어
이번에 채택하지 않는다. [prob 모델](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model_prob.cpp)의
beam skip은 수렴 후 빔별 입자 지지를 계산하고 과도한 skip이면 전체빔으로 복귀한다.
표준 기본 field를 유지하며 s2v19에서 실패한 product 모델로 바꾸지 않는다.

기존 `Visibility.apply`는 `weights @ (in_view & clear & cargo_clear) >= .95`
조건을 likelihood 전에 적용한다. 새 default-off `visibility_policy=nav2_observed_v1`은
이 입자 사전분포 조건을 **제거**한다(95% 수치 완화 아님). 자기 명령 고정 형상과 자기
RGB cyan으로 실제 검출 픽셀의 자기 가림만 전처리하고 나머지는 기존 고정 Nav2 혼합
우도에 맡긴다. 전처리는 로봇 장착 센서 adapter 차이이며 ROS 자체의 RGB 알고리즘은
아니다. 최소6열 차단도 새 경로에는 두지 않고 실제 유효 endpoint가 있으면 원본 field가
처리한다. 운동/카메라 보정/공용 제어기는 수정하지 않는다.

후보 구현·재생 **전** `observed-amcl-criteria.json`을 커밋한다. 같은 전체5117프레임·
명령·RNG를 재생하여 off는 저장 pose와1e-9 이내 일치해야 한다. 새 옵션은 운반 가중
갱신>0회 및 RMSE<2.1909388707m, 초기 정지 최대오차≤0.50m이면1회 DEV를 허용한다.
최장 갱신 공백은 보고한다. 이번 사용자 지시의 갱신/RMSE 개선 기준에 따르며 옛30초는
참고 기준이다. 계수 조정·실시간GT·결과를 본 뒤 판정 변경은 없다. 통과 시에만 신규
ID/seed 예약·선커밋 후 freeze ON/agent_lock/ugrp_session full1회; 미달이면 SIM을
실행하지 않는다. 이 저장 재생은 탐색이며 새 확증 자료가 아니다.

PR #405 `5ba7dd29`의 wall-floor-boundary 결과는 수동 접점 투영에도 중앙
0.457–0.665m 편향이 남았다고 보고한다(기존 검출 pixel precision94.3–98.8%).
이번에는 s1050의1Hz 운반 표본에서 고정 보정/저장 실제 카메라를 같은 픽셀에 적용해
접점·거리·pitch 차이를 **평가만** 한다. 다른 녹화 수치를 합산하거나 PR405를 수정하지
않으며 투영 보정은 별도 작업으로 남긴다. 이 단계 물리·렌더·모델 호출0회.

### s2v20 재생 결과 — 갱신 교착 해소, RMSE 미개선으로 새 DEV 미실행

기준 `3b8fc1df` → 구현 `ee0b1a86`. `visibility_policy=nav2_observed_v1`은 기본 off이며
기존 경로는 그대로다. 관련2파일11시험 통과: 기본/명시적 off record bytes, PF 입자·
가중치·예측에 접근할 수 없는 객체에서도 검출 처리, 실제 픽셀의 자기/짐 가림,
1열 허용·빈 관측 missing·비호환 옵션 거절, 기존 정지 motion 문턱/재표본화 등을 확인했다.
기존 s1050 전체5117프레임·3798명령 재생은 저장 pose x/y/yaw와 **최대차이0.0**이다.
GT는 두 Runtime 종료 뒤 별도 채점 프로세스에서만 읽었다.

| s1050 저장 영상·명령 재생 | off | nav2_observed_v1 |
|---|---:|---:|
| 초기 정지 최대 위치오차 m | 0.088755 | 0.088755 |
| 운반 시각 가중 갱신 | 0 | 18 |
| 운반 최대 갱신 공백 SIM초 | 165.80 | 39.25 |
| 운반 XY RMSE m | 2.190939 | 2.199598 |
| 운반 끝 오차 m | 4.061638 | 3.875910 |
| 운반 오차 P90 m | 3.893916 | 3.749419 |
| 사전 기준 | 비교 기준 | **FAIL** |

갱신 수/공백과 끝 오차는 개선했지만 RMSE는 **+0.008659m(+0.395%)**로 악화했다.
끝 오차 개선으로 전체 RMSE 기준을 대체하지 않는다. 운반24번 sensor weighting 중
18번만 KL>1e-12로 실제 비상수 가중 갱신이며, 6번은 상수 우도다. 마지막 유효 갱신은
197.55초, 운반 끝236.80초까지39.25초 공백이다. 최장 공백도 과거30초 참고 기준보다 길다.
관측 전 예측 가시성 교착은 제거했지만, 혼합 우도만으로 위치 정확도가 회복됐다는
근거는 없다. 계수/문턱을 튜닝하거나 다른 모델을 사후 추가 선택하지 않았다.

**사전 기준 미달로 신규 full DEV·seed 예약·번들 등록·영상 생성은0회다.** ID 조회만
main+열린 PR16개에서 수행했으며 당시 최대125, 새 ID를 사용하지 않았다. 이번의
lifted/inside·B 거리·실행 wall/SIM·실주행 would-stop은 **N/A**다. 기존 s1050의
lifted=true/inside=false와 wall/SIM2.59259를 이번 새 실행 결과로 승계하지 않는다.
잠금 acquire/새 ugrp_session은 없으며 agent_lock status=null을 확인했다.

### s1050 투영 편향 독립 평가 (수정 없음)

저장 carry71.0–236.8초의1Hz **166프레임**, 기존 검출7195열을 모두 평가했다.
고정 보정표로 검출한 동일 픽셀에 (a) 고정 카메라 + GT 차체 yaw/xy,
(b) 저장 실제 카메라를 적용한다. 실제 보이는 벽 하단 픽셀을 고정 보정으로 투영한
항목은 카메라 변환 오차를, 검출 픽셀을 실제 카메라로 투영한 항목은 픽셀 오차를
분리한다. 각 벡터 오차 크기는 합산 가능한 성분이 아니다.

| 평가 항목 | 수치 |
|---|---:|
| 실제 벽 하단이 보이는 검출 열 | 5171/7195 = 71.869% |
| 위 가시 부분에서 검출 행 오차≤3px | 98.859%, 행 잔차 중앙−0.407px |
| 고정 보정+검출 픽셀의 접점 오차 중앙 / RMSE | 0.015293 / 0.021103m |
| 실제 하단 픽셀+고정 보정: 변환만의 오차 중앙 | 0.013484m |
| 검출 픽셀+실제 카메라: 픽셀만의 오차 중앙 | 0.001624m |
| 실제 하단 픽셀+실제 카메라: 기하 일관성 RMSE | 4.16e-15m |
| 가시 접점이 있는75프레임의 프레임 중앙 오차 중앙 | 0.021991m |
| 고정−실제 pitch / 카메라 높이 차이 중앙 | +0.23721° / +0.002990m |
| 전체7195 검출의 최근접 지도 벽 오차 중앙 / RMSE | 0.016324 / 0.411985m |
| 실제 하단 비가시2024열의 최근접 벽 오차 중앙 / RMSE | 0.910229 / 0.776451m |

**실제 보이는 접점에서는 PR405의0.457–0.665m 편향이 재현되지 않았다.** 실물식
운반 자세·보정표·자료가 다른 비교이며, 수동 주석 precision과 여기의 조건부 행 일치를
같은 지표로 합산하지 않는다. 전체 검출에서28.131%는 실제 벽 하단이 안 보이는 열이고
이 부분의 접점이 지도 벽에서 크게 벗어난다. 이것이 남은 우선 점검 대상 하나다.
이 수치만으로 RMSE 악화 전체의 인과를 확정하거나 beam skip 효과를 주장하지 않는다.
실제 차체/카메라 GT는 평가에만 썼고, 카메라·처짐·검출·지도 보정은 변경하지 않았다.

`observed-amcl-summary.json`, `s1050-projection-summary.json`에 수치/원본 해시,
`replay_observed_amcl.py`, `score_observed_amcl.py`, `audit_s1050_projection.py`에
재현 경로를 보존한다. 모든 raw는
`/Users/changmin/projects/ugrp/outputs/s2-observed-amcl-20261007/`에 있다.
PR #406 DRAFT/병합 금지, PR #405 및 다른 worktree 변경0, 모델/물리/렌더 호출0.

전달 검증: 새 TensorBoard `1007-s2-observed-amcl`의3뷰26 scalar와 HParams를
source→event→실제 live API까지 대조했다(`observed-amcl-delivery-verification.json`).
기존 서버PID52016/공용logdir·기존 영상은 유지했다. 공용view 직전 재조회 후 자기
`s2_observed_amcl_20261007`키만 추가, 사용자 수치 대조 범위대로 UI 재개방은 생략했다.
[오프라인 비교](http://127.0.0.1:6006/?runFilter=1007-s2-observed-amcl&smoothing=0#timeseries).
새 물리 실행이 없어 새 영상·wall/SIM·성공 지표를 생성하지 않았다.
입력 해시·발행3798명령+초기 서보 기록1행 전체 반영·후보/재생기 해시·기하 일관성·
판정 계산을 추가 검증했다. 검증기에서 최초에는3799 record행을 발행3798개와 직접
비교해 assertion이 났고, 초기 서보1행을 별도로 세어 대조했다. 재생/수치는 변경하지 않았다.
off exact 재생은 구현 인수검사로 기준3b8fc1df의 작업 트리에서 수행했고, 그 후보/재생기
파일은 후속 커밋ee0b1a86과 해시가 같다. 옵션 on 재생은 ee0b1a86에서 수행했다.
두 기록 모두 탐색/시험 자료이며 새 확증 실행으로 이름을 바꾸지 않는다.


## s2v21 접점 의미 분해·바닥 외형 제외 — 사전 등록 (2026-10-07)

사용자 최신 요청: s1050 운반 접점 의미와18회 갱신 방향을 평가 전용으로 분해하고,
가장 큰 오분류 하나만 표준 방법으로 제거한다. 사전 기준은
`contact-filter-criteria.json`: 고정 명령/자기RGB5117프레임, carry71–236.8초,
**운반 RMSE <2.1909388706847515m**(원래 v125보다 개선, 관측 기반 후보2.199598m도
개선), informative 갱신≥1, 초기 정지 최대오차≤0.5m, off 재생 오차0이다.
30초 공백은 이전 목표로 따로 보고하며 이번 사용자 요청의 RMSE 관문에 추가하지 않는다.
기준 미달이면 새 seed/full을 실행하지 않는다. 아직 후보 재생 결과는 보지 않았다.

1Hz166프레임 중 접점이 있는104프레임7195열을 평가한다. 71–109초의 실제 하단
비가시2024열은 영상에서 체커/파란 바닥의 색 경계다. 원시 기하의25개 경계 부근
분류는 확대 영상으로 따로 확인하고, 단순 픽셀 문턱을 의미 정답으로 확정하지 않는다.
분류별 중앙값은 가산할 수 없으므로 전체 접점 MAE 기여와 제곱오차 점유율을 함께 낸다.
입자 기록은 우도 적용 직전/직후/재샘플 뒤의 전체 가중 평균과 실제 보고 pose를
따로 저장한다. GT는 종료된 예측 파일을 별도 채점할 때만 읽는다.

### 참고 자료와 선택 범위

[Ulrich & Nourbakhsh, AAAI 2000, §§4–6](https://cdn.aaai.org/AAAI/2000/AAAI00-133.pdf)의
HSI hue/intensity histogram, Gaussian5×5, 평활화와 count60/80 판정,
여러 참조의 OR 및 고정 regular mode를 적용한다. PR405의 단일 현재 프레임 방식은
바닥 표본이 부족해 실패했다. 이번은 자기RGB의 수동 확인 바닥 표본(71/98초,
undistorted x20:620,y80:420)을 사전에 고정해 저장한다. 논문의 주행 통과 참조 queue는
명령 이동이 실제 이동을 보장하지 않는 우리 조건에서 쓰지 않는다. 수동 참조 선택은
[OpenCV histogram backprojection 공식 절차](https://docs.opencv.org/4.x/dc/df6/tutorial_py_histogram_backprojection.html)와
같은 입력 준비 방식이다. 참조 생성에는 GT 좌표/마스크를 쓰지 않는다.

bins256·histogram평활5·최저 intensity10/255·saturation0.1은 논문 미명시 공학 상수이며
PR405 구현과 같은 값으로 고정한다. 기존 벽 검출 접점의 위/아래3행×5열이 모두
학습된 바닥 외형이면 그 접점만 모름 처리한다. 새 접점은 만들지 않는다.
옵션 `contact_filter=floor_appearance_v1`, 기본 off. S2 loaded+관측 기반 AMCL에만
적용하고, 공유 검출기/다른 제어기·PF 수식·카메라·구동은 바꾸지 않는다.

이는 이미 본 s1050으로 바닥 외형을 준비하는 **탐색 자료 내 재생**이다. 학습/평가
분리나 새 확증 결과로 주장하지 않는다. 통과 시만 새 seed에 고정 표를 적용한
S2 full DEV1회를 한다. 실물은 현장 카메라의 바닥 표본으로 다시 준비해야 한다.
같은 색의 벽을 놓칠 수 있는 원 방법의 한계를 보존하며 결과 뒤 문턱을 조정하지 않는다.


### 재생 통과와 새 full 사전 등록

기준 `3621b05d`, 구현 `e89883e3`의 full5117frame 재생: contact_filter off는
이전 nav2_observed의 poses/amcl/visibility와 **전체 동일**. on은 RMSE2.125893m
(원래 mask의2.190939m, observed의2.199598m보다 개선), informative20회,
최장공백39.25초, 초기 정지최대8.876cm로 등록4조건을 통과했다.
30초 공백 목표는 여전히 미달이다. 수치를 보고 문턱·상수·참조를 바꾸지 않았다.
1Hz 분류 접점에서는 바닥727/2024(35.92%)와 진짜벽13/5168(0.252%)를 제거했다.
부분 개선이며 남은 바닥 오검출1297열을 해결했다고 주장하지 않는다.

main+열린PR16refs의 RUNNABLE_ID와 별도 BUNDLE_ID를 모두 조사한 최댓값125 다음
**zone-s2-realism-v126 / workflow7.19.0 / 미사용seed1051 / P1-2→B / place**를
예약한다(`registration-v126.json`). 단순 검색의 DOI `s10514`는 seed1051이 아니며
정확한 토큰·raw경로 일치는0이다. 기존1050 이하 seed는 재사용하지 않는다.
freeze ON은 S2 단독 DEV에만 한정(S3·짝 운반·본 연구·본 연구 사전등록 코호트 금지).
이 문단의 seed 사전 기록은 DEV 실행 계획이며 본 연구 승인이 아니다.
기존 v125의23개 옵션 전부와 `visibility_policy=nav2_observed_v1`,
`contact_filter=floor_appearance_v1`를 명시해 result/bundle에 보존한다.
실물식 blind 파지, v3 무하중 보정+고정 sag, real_delivery_v1, pulse 보정,
관측 격리·RGB 정체 감시, eval120초/1cm 감시를 유지한다.
unknown·불확실성은 dev_light 기록만, 실제 물리 실패/오류/유한cap만 종료한다.
1회만 실행, 모델0, 원본 합산0. ENOSPC는 HOST_ERROR로 남기고 seed를 재사용하지 않는다.
원시 출력은 primary outputs/s2-realism-<실행SHA8>-s1051-P1-2-place에 둔다.


### s1050 접점 분류·갱신별 실제 효과 (평가 전용)

앞선0.91m 지표와 같은1Hz166프레임·96열 진단 격자(u8–631)에서 검출이 있는104프레임7195열 전부를 고정 카메라로 검출하고, 저장된 실제 카메라·차체/짐·정적 벽 기하로 평가했다. 전체104개 겹침 영상과 기하상 경계 근처25개 확대 crop을 직접 확인했다. 그중22개는 기울어진 벽 하단/모서리의 strip 오차로 정정했고, 벽면의3개 artifact는 미확정으로 남겼다. 기하 자동 분류 초안2035 floor/5146 wall을 최종 의미 비율로 사용하지 않는다. 객체/그림자의 조밀한 semantic GT는 없으므로 표의0은 이 표본 검출 접점에서 관찰되지 않았다는 뜻이다.

|분류|접점 수·비율|최근접 벽 오차 중앙 / RMS(m)|전체 MSE 점유율|전체 MAE 기여(m)|
|---|---:|---:|---:|---:|
|진짜 벽 하단|5168 / 71.8277%|0.007891 / 0.013772|0.08026%|0.008225|
|바닥 색·체커 경계|2024 / 28.1306%|0.910229 / 0.776451|99.91832%|0.194834|
|물체·다른 로봇|0 / 0.0000%|N/A|0.00000%|0.000000|
|문틀·기둥|0 / 0.0000%|N/A|0.00000%|0.000000|
|자기 몸·그림자|0 / 0.0000%|N/A|0.00000%|0.000000|
|기타/미확정: 벽면 artifact|3 / 0.0417%|0.073430 / 0.075898|0.00142%|0.000032|

이전 **0.910229m는 비가시2024열의 중앙값**이지 전체 RMSE가 아니다. 이2024열 모두 바닥 색 경계이며 해당 부분의 오차를 설명한다. 분류별 중앙값은 합할 수 없고 위 MSE 점유율·가중 MAE만 가산 가능하다. 바닥 종류는 pickup 파란 overlay/체커에서 발생했으며 B 바닥이나 테이프라고 일괄 부르지 않는다. 실제 관측만으로 이를 알 수 있다고 주장하지 않는다.

18회 갱신은 아래와 같다. Δx/y는 우도 적용 후 전체 가중 평균의 변화(m), cos는 그 변화와 실제 오차를 줄이는 방향의 내적 정규화다. 감소량은 양수일 때 개선. 전체 평균과 실제 보고 pose(모드 선택 가능)는 JSON에서 별도로 보존한다.

|SIM s|바닥/벽/모호 열|가중 Δx, Δy(m)|방향 cos|오차 전→가중 후→재샘플 후(m)|가중 후 감소(m)|
|---:|---:|---:|---:|---:|---:|
|80.35|53/0/0|+0.0001, +0.0312|+0.659|0.1527→0.1342→0.1440|+0.0185|
|81.95|57/0/0|-0.0062, +0.1007|+0.923|0.2963→0.2069→0.1977|+0.0894|
|83.25|66/0/0|-0.0223, +0.1817|+0.974|0.4384→0.2634→0.2301|+0.1751|
|84.85|68/0/0|-0.0373, +0.1788|+0.996|0.6054→0.4237→0.3708|+0.1817|
|86.15|80/0/0|-0.0826, +0.2484|+1.000|0.6573→0.3957→0.4000|+0.2616|
|87.80|81/0/0|+0.0111, +0.0061|+0.205|1.0765→1.0740→1.0855|+0.0025|
|89.15|67/0/0|+0.0487, -0.0155|-0.577|1.2948→1.3250→1.3211|-0.0301|
|90.80|57/0/0|+0.1570, -0.0190|-0.444|1.4731→1.5499→1.5536|-0.0768|
|98.65|26/0/0|-0.0593, +0.0761|+0.971|1.6461→1.5527→1.5399|+0.0934|
|107.10|48/5/0|-0.0604, -0.0070|+0.264|1.6179→1.6029→1.5792|+0.0150|
|115.85|0/83/0|-0.0865, +0.0896|+0.908|1.6494→1.5371→1.5478|+0.1123|
|124.20|0/95/0|-0.1287, +0.1525|+0.919|1.5884→1.4072→1.4132|+0.1812|
|141.85|0/94/0|-0.1469, +0.1376|+0.842|1.3642→1.1997→1.2076|+0.1645|
|149.55|0/90/0|-0.0693, +0.0974|+0.894|1.1780→1.0726→1.0643|+0.1055|
|157.45|0/3/0|-0.0041, +0.0166|+0.992|1.0451→1.0282→1.0326|+0.0169|
|194.50|0/62/0|+0.0000, -0.0000|-0.951|2.9027→2.9027→2.9045|-0.0000|
|195.90|0/62/1|-0.0001, -0.0004|-0.877|3.1729→3.1733→3.1762|-0.0004|
|197.55|0/61/0|-0.0082, -0.0244|-0.784|3.4553→3.4755→3.4740|-0.0202|

가중 후13/18, 재샘플 후12/18회는 오차를 줄였다. 하지만80.35–98.65초 첫9회는 **사용한 접점이 전부 바닥**이고107.10초도48/53이 바닥이다. 잘못된 대응이 우연히 현재 xy 오차를 줄인 것을 올바른 벽 fix라고 세지 않는다. 89.15/90.80초는 오차를0.0301/0.0768m 늘리고 yaw 오차도−11.27→−12.65°/−13.15→−16.65°로 악화시켰다.

115.85–157.45초의 벽 갱신5회는 모두 개선했지만, 마지막194.50–197.55초는 실제 벽을 보고도 이미 위치 오차2.90–3.46m, yaw 오차 약−68~−63°인 상태여서 가중 이동이0~2.58cm이고 세 번 모두 악화했다. informative는 KL>1e−12라는 뜻이며 크기·대응 정확성 보증이 아니다. 전체 갱신 직후 오차 감소 합1.372609m보다 갱신 사이 증가 합4.693842m가 컸다. 이는 시간축 분해이며 바닥 오인만이 나머지 증가의 원인이라는 인과 증명은 아니다.

고정 floor 참조는727/2024 바닥 접점을 제거했지만1297개는 남았고 진짜벽13/5168도 빠졌다. 원 논문의 외형 겹침·참조 범위 한계다. 문턱을 튜닝하거나 다른 방법을 추가하지 않았다. 재생의 early(71–110)/wall(110–158)/late(158–236.8) RMSE는1.1935→1.0853 / 1.3645→1.1847 / 2.8881→2.8410m다.

관련 시험은6개, 번들/실행 연결 추가 후3파일15개 통과. 최초 합성 시험에서 학습하지 않은 Gaussian 중간 색까지 바닥으로 기대해 실패했고, 원 방법의 unknown 동작을 보존하는 기대값과 경계 포함 참조 사례로 고쳤다. 구현 상수는 바꾸지 않았다. 최종 e89883e3의 default-off 전체 재생도 이전 poses/amcl/visibility와 동일하다. 최초 진단용 audit는3621b05d 이전 작업 트리에서 실행했고, 최종 인수 off/on은 둘 다e89883e3에서 실행했다.

기준·분류·갱신 JSON과 고정 외형 표는 Git에, 접점 전수/이미지와 재생 raw는 `/Users/changmin/projects/ugrp/outputs/s2-contact-audit-20261007/`에 보존한다. raw는 로컬 보관이며 원격 백업이라고 표현하지 않는다. 논문은 web PDF로 내용을 확인했으며 별도 urllib 원문 다운로드는HTTP403으로 미완료다. 이 실패를 인용 미확인으로 바꾸지 않는다.

실제 PF 격자는 `vl.column_positions(96,2)`(u10–629)다. 위7195열은 기존 투영 진단의 동일 분모를 유지한 것이며 실제 모든 제어 tick의 접점 수가 아니다. 갱신별18회 표는 실제 PF에 들어간 endpoint를 직접 기록했으므로 이 격자 차이를 포함하지 않는다.


### v126 · s1051 full DEV 결과 — 1회 종료

실행 소스 **c26e9afd5454e41d7192311924853dc00147b0d7**, v126/7.19.0,
seed1051/P1-2/B/place. 입력·실행 소스 변경false, 관리 exit0, controller done이지만
**STAGE_REACHED_UNQUALIFIED / lifted=true / inside=false / floor=true / stable=true**다.
실제 낙하·이탈·기울기/실행 오류는 없었고 B 밖에 안정 배치했다. 성공률을 승계하지 않는다.

|항목|값|
|---|---:|
|운반 구간|87.00–241.05 SIM s|
|informative 시각 갱신 / 최장 공백|27 / 33.85 s|
|운반 RMSE / 종료 위치 오차(평가)|2.023583 / 2.592097 m|
|실제 벽 하단 가시율(1Hz, 모든96열 / 검출열)|32.7218% / 54.3706%|
|cyan에서 B 영역 / B 중심까지|2.178372 / 2.649795 m|
|would-stop: ARM_COLLISION_GUARD / POSE_UNCERTAIN / VISUAL_STALL_SUSPECTED|7 / 341 / 1 (합349)|
|hold / 원래 자리 비교 / 재집기|probable_held_inhand_rgb / not_evaluated_inhand_selected / 0|
|wall / total SIM / wall÷SIM|347.865758 s / 264.35 s / 1.315929|
|발행 명령 / 입력 프레임 / 모델 호출|3818 / 5202 / 0|

가장 큰 남은 관측 문제는 **바닥 색 경계가 필터를 통과함**이다. 실제27회 갱신의
접점을 동일한 자기RGB·고정 표로 재구성해 기록된 열 수와27회 모두 일치시켰다.
1459개 중553개(37.9027%)가 바닥 색 경계,848개는 벽 하단,58개는 경계 부근 모호다.
첫8회 갱신은 입력 접점 전부가 바닥이었다. 겹침 영상27개를 직접 확인했다.
새 seed에서도 같은 오분류가 남았으므로 여기서 중단한다. 잔차 문턱·참조 색·펄스
등을 추가 조정하거나 두 번째 full을 하지 않는다. 바닥 오인이 RMSE 전체의 유일한
원인이라는 인과 주장은 하지 않는다.

새 full의 자세·명령 궤적은 s1050과 달라 RMSE2.190939→2.023583m나 B 거리
3.548017→2.178372m를 통제된 성능 개선으로 해석하지 않는다. 확증/본 연구 결과가 아니다.
freeze 비교도 wall/SIM만 기술적으로 기록한다: OFF s1042=2.587649,
ON s1050=2.592588, ON s1051=1.315929. seed·길이·부하·코드가 달라 인과 가속률은 아니다.

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-c26e9afd-s1051-P1-2-place/`.
분석: `/Users/changmin/projects/ugrp/outputs/s2-contact-audit-20261007/`.
`result.json.options`와bundle의25옵션이 같고 새2옵션·freeze ON을 확인했다.
5202프레임sha256, 발행3818명령+초기서보1행, 원본 결과/trace 해시를 대조했다.
full 후처리 첫 인수는 이전 진단 격자u8–631로 실제97.95초30열을29열로 재구성해
실패했고, 실제 `column_positions(96,2)`를 사용해27회 전부 일치시켰다. 제어·결과·후보는
변경하지 않았고, 진단7195열의 원본 분모도 유지했다.

4배속 MP4: `/Users/changmin/projects/ugrp/outputs/s2-contact-audit-20261007/views/s1051-full/execution.mp4`
(640×480,20fps,65.05초). 입력 SIM1.30–261.35초를 담고 마지막3초 정착에는 저장RGB가 없다.
전체 decode, 등록된 media ID, HTTP206/원본 바이트 일치를 확인했다.
TensorBoard **1007-s2-floor-contact**의5뷰53scalar·HParams를 source→event→live API로
대조했다(`contact-delivery-verification.json`). 기존 서버PID52016·공용logdir는 유지하고
공용view를 쓰기 직전에 다시 읽어 자기키만 추가했다. 사용자 수치대조 범위대로 UI는
재개방하지 않았다(NUMERIC_ONLY).
[새 결과·오프라인 대조](http://127.0.0.1:6006/?runFilter=1007-s2-floor-contact&smoothing=0#timeseries).

전용 ugrp_session stopped, PID34247/34251/34261/34267 잔여0, one-shot launchd job bootout,
**agent_lock=null** 확인. 다른 작업/PR/프로세스 수정·종료0, 모델 호출0. PR #406 DRAFT,
병합 금지 유지. CI 전체 완료는 별도 상태이며 로컬 시험/재생/물리 결과와 합치지 않는다.


## s2v22 하중 운동·벽 높이 일관성 — 재생 전 고정 (2026-10-07)

[사전 기준](load-height-criteria.json)을 후보 보정/재생 전에 커밋한다. A를 먼저 처리한다.
v122는 하중 전진·회전·큰 옆 이동을 s1045에서 따로 fit했다. 무하중 전용이라는
가설은 사실이 아니며, loaded fine strafe는 실측0개의 전이 모델이다. 이번 보정은
**s1050만** 사용한다. 자기 명령으로 하중을 나누고, 기존 응답시간을 온전히 가진
단일축 펄스 전부를 사용한다(최소3개). GT에 따른 충돌/나쁜 표본 제거는 없다.
프로파일별 평균곡선 최소제곱과 잔차의 하중별 Nav2 Omni α1–5 NNLS를 고정한다.
미관측 항목은 기존 평균을 유지하고 표시한다. s1051은 새 계수에 사용하지 않는다.

A의 평가: s1051 하중 펄스 endpoint xy RMSE 감소·yaw RMSE 비악화. B는 기존 외형
필터를 **대체**하는 `wall_height_v1`이며 둘을 중첩하지 않는다. 바닥 접점에서
정적지도 벽 높이0.40m의 상단을 투영하고, 독립 Canny(100/200, Gaussian5) edge가
반경3px에 있는지 확인한다. 상단이 밖/미검출이면 모름이다. 이는 95% 입자 사전
가시성 문턱이 아니며 자기RGB+고정카메라+지도 높이만 쓴다. 반경3px은 구현 고정값,
논문의 보편 임계값이 아니다. 기존 검출기도 높이를 가정한 band를 찾으므로 그
예측값을 독립 상단 관측으로 재사용하지 않는다.

baseline/A/B/AB 네 조건 전체5202 frame·고정 명령 재생을 한다. A·B·AB 각각
운반 RMSE<2.023582776m, informative 갱신≥1, 초기 정지 오차≤0.5m를 요구한다.
B는 기존27회 입력 접점에서 바닥 비율 감소와 진짜벽≥90% 보존도 요구한다.
기본off 동일·A 국소 운동 기준까지 모두 통과한 경우만 새 seed full DEV1회.
30초 fix공백은 기존 목표로 별도 보고한다. 결과 뒤 후보/계수/문턱 튜닝·재시도는 없다.
s1050/51은 이미 관찰한 DEV자료이며 독립 확증/본 연구라고 부르지 않는다.

표준 대조: [Nav2 OmniMotionModel](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/motion_model/omni_motion_model.cpp)의 이동방향/직교방향/회전 분산을 α1–5로
분리한다. α는 평균 바이어스를 고치지 않으므로 응답 평균을 별도로 식별한다.
메카넘에는 differential α1–4보다 Omni α5가 적합하다. 원본의 입력은 측정 odom,
여기는 고정 명령 응답이라는 차이는 남는다. [SciPy NNLS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.nnls.html)로 비음수 계수를 맞춘다.
[Criminisi·Reid·Zisserman, Single View Metrology §2.1](https://www-2.cs.cmu.edu/~ph/869/papers/Criminisi99.pdf)의 바닥·수직 대응/높이 기하를
이미 있는 외부 보정으로 사용한다. [OpenCV Canny](https://docs.opencv.org/4.x/da/d22/tutorial_py_canny.html)는 관측 edge 검출이다.
기하가 증명하는 것은 대응점의 높이이며 같은 픽셀 근처의 임의 edge가 진짜 벽 상단인지
의미적으로 보장하지 않는다. 원문2000판 PDF 다운로드는 timeout, 저자 페이지와1999
논문 원문은 확인했다. 실시간 GT 입력·공용 카메라 포트·다른 제어기 변경은 없다.


### s2v22 결과 — A·B 개별 기준 미달, full 미실행

기준 **b0f5cf74** → 구현 **e178f2ef**. 기본 off 명령·record 바이트 시험 및 기존 pulse/floor 시험 **14 passed / 25.98초**, 실제 Runtime 네 조합 생성 통과. 전체5202 frame 재생 네 조건을 같은 커밋으로 완료했고 baseline은 원본 poses/amcl/visibility/contact와 완전히 같다. 원본 hash·보정/평가 분리·수식 분해 일관성은 [검증](load-height-verification.json)에 보존한다.

#### A: 하중 자체보다 막힘에 따른 응답 변화가 큼

v122는 loaded forward(+35/100ms)70, coarse left(−/+65/650ms)188/195, turn(−/+35/100ms)7/9개를 s1045에서 이미 학습했다. loaded fine(35/60ms)은0개로 무하중 전이였다. 따라서 “무하중만 보정했다”는 가설은 기각한다. [보정 출처·모든 프로파일 수치](load-motion-summary.json).

완료 s1051에서 구간의 자기 명령 LoadState로 나눈 endpoint 오차는 무하중161펄스 xy **0.946mm / yaw0.300°**, 운반 하중277펄스 **24.132mm / 1.192°**다. 기존 프로파일의 종료+정지 꼬리(100/140ms) 시점끼리 비교했으며 늦은 잔류 이동도 raw에 따로 남겼다. 다음 표의 실제 값은 같은 horizon의 평균이고, 단위는 cm·도다.

|하중·명령|n|예측 Δ전진/옆/yaw|실제 평균 Δ전진/옆/yaw|xy RMS mm / yaw RMS°|
|---|---:|---:|---:|---:|
|0:forward:0.35:0.06|65|0.756 / 0.001 / -0.004|0.753 / 0.002 / -0.029|0.556 / 0.343|
|0:forward:0.35:0.10|26|1.292 / -0.040 / -0.017|1.175 / 0.005 / -0.034|1.491 / 0.161|
|0:left:-0.35:0.06|36|0.006 / -0.732 / -0.026|0.008 / -0.732 / 0.036|0.826 / 0.196|
|0:left:0.35:0.06|33|0.004 / 0.692 / -0.081|-0.004 / 0.690 / -0.091|1.023 / 0.351|
|0:turn:0.35:0.10|1|0.013 / -0.282 / 5.369|-0.132 / -0.060 / 6.226|2.648 / 0.857|
|1:forward:-0.35:0.10|11|-1.294 / -0.008 / -0.001|-1.203 / -0.009 / -0.021|1.112 / 0.211|
|1:forward:0.35:0.10|179|1.294 / 0.008 / 0.001|0.890 / -0.003 / -0.035|5.613 / 0.318|
|1:left:-0.35:0.06|5|0.006 / -0.728 / -0.062|-0.042 / -0.653 / 0.182|1.499 / 0.324|
|1:left:-0.65:0.65|16|0.067 / -16.695 / 1.499|0.205 / -16.955 / 1.146|3.134 / 0.499|
|1:left:0.35:0.06|32|0.004 / 0.686 / -0.221|-0.087 / 0.380 / -0.781|3.800 / 0.772|
|1:left:0.65:0.65|19|0.084 / 16.720 / -1.520|0.141 / 11.762 / -0.792|90.281 / 4.138|
|1:turn:-0.35:0.10|4|0.019 / 0.105 / -4.752|-0.092 / 0.129 / -4.492|1.372 / 0.556|
|1:turn:0.35:0.10|11|-0.007 / -0.096 / 5.007|0.124 / -0.412 / 3.573|3.730 / 1.503|

**기여도 순서:** 각 명령 horizon의 world 이동 증분 오차를 `R_true*(예측−실제body)`와 `(R_est−R_true)*예측`으로 정확히 나누고 교차항을 반씩 배분하면, 명령 응답/미끄러짐 **68.42%**, 방향 추정 **31.58%**다. 이는 증분 제곱오차의 기술적 분해이며 글로벌 위치 RMSE의 인과 기여율이 아니다. 기존4.69/1.37m는 s1050의 갱신 간/직후 분해이므로 s1051 수치로 재사용하지 않는다.

운반 xy endpoint 제곱오차의 **95.84%가 +65/650ms 옆 이동6회**(107.35–113.70초)에 집중된다. 예상16.720cm에 실제 이동거리는 **0.083–2.374cm**; 차체 중심부터 최근접 벽까지7.47–9.30cm다. RGB6장에서도 근접한 벽과 거의 같은 바닥이 보인다. 접촉 힘 로그는 없으므로 접촉 임펄스 원인을 확정하지 않고 **벽 근접·진행 부족**으로 기록한다. 같은 명령의 나머지 정상 구간은 약17cm여서 단일 하중 gain으로 설명할 수 없다. [기여 분해](load-drift-summary.json), raw `drift-decomposition.json`, `motion-wall-frames.jpg`.

사전 고정 s1050만 OLS 평균곡선/하중별 Nav2 Omni α1–5 NNLS에 사용했다. 기존 응답시간은 유지하고, 관측3개 미만은 기존 평균을 유지했다. α는 이동방향·직교방향·yaw 분산 공식 그대로이며 기존 S2 시간 예측에 독립 증분으로 나누는 것은 명시적 어댑터 차이다. Nav2 자체에 하중별 bias 학습기가 있다는 주장은 아니다. 학습 입력의 실제 좌표는 고정 보정 때만 사용하고 Runtime에는 고정 상수/자기 명령만 전달한다.

새 평균으로 s1051 하중 endpoint xy RMS는 **24.132→43.161mm**, yaw **1.192→1.608°**로 악화하여 A 기준 실패. 특히 s1050의 −65/650ms는 평균−2.075cm인데 s1051은−16.955cm다. 벽 막힘이 섞인 응답 평균을 자유 이동의 하중 gain으로 옮긴 문제다. 결과 뒤 GT로 충돌 표본을 빼거나 다시 fit하지 않았다. 새 표는 미채택 탐색 자산으로 보존한다.

#### B: 벽 상단이 안 보이므로 높이 증거 자체가 없음

`contact_geometry=wall_height_v1`(기본off)은 기존 `contact_filter=floor_appearance_v1`와 동시에 켜면 오류다. 검출 접점+지도 높이0.40m의 상단을 고정 외부 보정으로 투영한 뒤 **독립 RGB edge**만 찾는다. 기존 검출기의 높이 가정으로 만든 `t_lo`를 증거로 되먹이지 않는다.

기존27회 갱신의1459접점에서 상단 투영은 **모두 화면 위 밖**이다. 진짜 벽848열의 상단 v는 **−1559.09~−260.21px(중앙−343.84)**, 바닥 오인553열은−654.89~−243.69px(중앙−269.89). 이전 분류의 모호58열도 밖이다. [기하 수치](height-observability.json). 기존27개 겹침 영상3장을 전수 확인했다. 정확히 같은1459접점 중 보존0/진짜벽 보존0%로 B 기준 실패이며, 바닥 비율은 분모0이어서 **N/A**, 0% 개선으로 표시하지 않는다.

이 방법은 상·하단 대응을 필요로 하는 단일 영상 높이 측정이다. 벽의 중간 면만 보여도 동작하는 일반 수직면 분류기라고 주장하지 않는다. 카메라 mount/FOV/운반 자세나 Canny/허용오차를 바꾸지 않았다. 사용 불가능한 높이 증거를 게이트로 요구하면 갱신 교착이 다시 생긴다는 한계를 확인했다.

#### 고정 명령 재생과 실행 결정

|조건|운반 RMSE m|갱신|최장 공백 s|초기 정지 최대 m|
|---|---:|---:|---:|---:|
|baseline|2.023583|27|33.85|0.105661|
|load_only|1.640675|23|43.70|0.105661|
|height_only|1.051437|0|154.05|0.105661|
|load_height|1.311830|0|154.05|0.105661|

[전체 판정](load-height-summary.json): RMSE만은 세 후보 모두 기존보다 낮다. 하지만 A의 독립 endpoint 예측은 악화했고, B/AB는 운반 갱신0·벽 보존0%여서 **전체 관문 실패**다. B의 낮은 RMSE는 이 고정 궤적에서 오관측을 전부 차단한 dead-reckoning 결과이지 위치 보정 성공이 아니다. 특히 A 단독보다 기존 운동+B의 RMSE가 작다는 관찰도 단일 하중 보정을 주원인 해결로 확정하지 못하게 한다.

**새 full DEV·물리·렌더·모델 호출0**, 새 seed/번들 예약0. lifted/inside·실제 가시율·B 거리·would-stop·wall/SIM은 새 실행이 없으므로 N/A다. 이전 s1051의 lifted=true/inside=false·wall/SIM1.315929를 새 옵션 성능으로 승계하지 않는다. A/B 옵션은 기본off 미채택 상태로만 남기고 이번 작업에서 추가 후보나 반복 실행은 하지 않는다.

raw `/Users/changmin/projects/ugrp/outputs/s2-load-height-20261007/`는 로컬 보관이며 원격 백업이 아니다. 기존 raw·번들·영상은 보존했다. TensorBoard **1007-s2-load-height / 7뷰41scalar** source→event→live API와 HParams를 대조하고 기존PID52016/logdir를 유지했다. 수치 대조만 했고 새 영상은 없다. [대시보드](http://127.0.0.1:6006/?runFilter=1007-s2-load-height&smoothing=0#timeseries), [전달 검증](load-height-delivery-verification.json). 공용view는 직전 다시 읽어 자기 키만 추가했다.

오프라인 ugrp_session `s2-load-height-offline` stopped; 물리 잠금은 획득할 실행이 없었고 **status=null** 확인. 다른 프로세스·PR·worktree 변경0, Google Drive 사용0. PR406 DRAFT·병합 금지, CI 전체 상태는 로컬 시험/재생과 별도다. 출처 원문과 다운로드 해시는 [참고 자료](load-height-sources.json), Nav2 pin `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`다.


## s2v23 — 북쪽 벽 막힘 6회, 자기 RGB 운동 불확실성 후보 사전 등록

2026-10-07 사용자 요청. 기존 s1051의 하중 xy 제곱오차95.84%를 만든6회만 접촉/영상/분기부터 분해한다. 이전 기록의 “힘 로그 없음”은 맞지만 **접촉 geom/dist 로그는 존재**한다. 따라서 접촉 유무는 이번에 평가 전용으로 확정하고 힘·실제 바퀴 회전/미끄럼 속도는 미측정으로 남긴다.

[고정 기준](blocked-pulse-criteria.json)을 후보 평가 전에 커밋한다. `visual_progress=ground_flow_noise_v1` 기본off. 자기RGB의 바닥 특징을 LK로 추적하고 고정 카메라 보정으로 지면에 투영한 뒤 RANSAC 강체운동으로 병진/yaw를 분리한다. 명령 응답과 RGB 운동의 innovation으로 **해당 펄스의 운동 공분산만 증가**시키고 평균 이동·명령·벽 관측은 바꾸지 않는다. 부족한 바닥 특징은 unknown이며 정지로 간주하지 않는다. 시각 확인/기존 RGB 정체 알림은 dev_light 기록만 유지한다.

표준: [Seegmiller 등 IROS2011 §§II-C–F](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf)의 LK→평면 역투영→RANSAC/SVD 강체운동을 사용한다. 원문의 별도 그림자 분할 대신 기존 고정 바닥 색 표·자기 기하/블록 마스크를 쓰는 입력 어댑터 차이는 남긴다. [Popescu 등 2026 §4.1 식13–15](https://arxiv.org/html/2608.02316v1#S4.SS1.SSS1)의 innovation 공분산 대비 nominal Q scaling을 적용한다. 원문은 다족 InEKF이며 여기는 **펄스별 M=1 상대 SE2·입자 공분산 증가**로 제한한 어댑터다. 실시간 평균 재학습이나 GT 접촉 분류를 사용하지 않는다.

[Nav2 collision_monitor 원본](https://github.com/ros-navigation/navigation2/blob/main/nav2_collision_monitor/src/collision_monitor_node.cpp)은 자기 센서 obstacle points와 stop/slowdown polygon을 사용한다. 현재 단안 벽 접점에는 바닥 오인이 남으므로 이를 신뢰 가능한 거리 센서처럼 취급해 정지 명령을 만들지는 않는다. [공식 설정](https://ros-navigation.github.io/mkdocs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/)과 대조했다.

채택 기준: off 명령/기록·5202 frame pose 동일; 하중 endpoint 평균 xy/yaw 오차 비악화와 Gaussian NLL 개선; 문제6회 xy 3σ 범위 포함≥5/6, 나머지 하중 펄스의 과도한 공분산 증가 비율≤10%; 운반 RMSE<2.023583m·갱신≥27·공백≤33.85s·정지오차≤0.5m; RGB 원본 해시·벽 필터 동일·공통 관측 열100% 보존. 30초는 기존 목표로 별도 보고한다. 이 후보는 bias 자체를 고치지 않으므로 RMSE만 좋아도 나머지 기준이 실패하면 미채택한다. 사후 문턱/특징수 조정·다른 후보 재시도 없이, 전체 통과 때만 새 seed S2 full DEV1회. 사전 등록 본 연구가 아닌 DEV이며 freeze ON은 S2 solo DEV 한정이다.

### 6회 분기·물리 원인 확정 (평가 전용)

기준 커밋 **e1fa6bc8**, 먼저 pulse 시험6 passed/17.19초. 아래6회는 모두 **carry → drive → select_pulse**, `left=+0.65, 0.65초`, 예측 옆16.720cm/yaw−1.520°다. 목표는 문 앞 `[1.65,0.05]`(문 자체는 x2.2)이며 재정렬/회복/문 통과 중이 아니다. 전진·옆·yaw 비용을 비교해 각각 감소한다고 판단해 발행됐다. 실제 위치는 x0.178–0.193/y1.332–1.350으로 **북쪽 외벽 안쪽 y1.425**에 붙어 있었다.

|SIM s|실제 시작 x,y m|당시 추정 x,y m|추정 목표 옆 오차 cm|실제 이동거리 cm|실제 yaw°|벽–바퀴 표본; 최소 dist mm|
|---:|---|---|---:|---:|---:|---|
|107.35|0.178, 1.335|0.937, -0.544|89.84|1.706|+10.016|13/16; -0.922|
|108.30|0.185, 1.350|1.083, -0.462|75.31|0.089|+0.171|13/16; -0.386|
|109.25|0.186, 1.350|1.188, -0.380|62.65|0.127|+0.295|13/16; -0.486|
|110.20|0.188, 1.350|1.404, -0.374|47.51|0.083|-0.111|13/16; -0.585|
|111.15|0.187, 1.350|1.528, -0.296|32.86|0.135|+0.473|13/16; -0.489|
|113.70|0.193, 1.332|1.766, -0.277|22.50|2.374|-14.106|13/16; -0.862|

6회 모두 북쪽벽–앞왼쪽/뒤왼쪽 롤러 접촉. 블록–벽0, 문틀/분리벽–로봇/블록0, 기타 팔/차체–북쪽벽0. 양손가락 접촉은96/96 표본, 최대 차체 기울기0.3054°, weld0. 양 끝 영상12장을 직접 대조했다. 접촉이 생긴 동안 wheel command는 유지되지만 **실제 휠 회전속도/접촉 힘은 저장되지 않아 slip 속도나 힘의 방향은 미확정**이다. 평가용 접촉으로 제어를 정지시키지 않는다. [전수 표·영상 해시](blocked-six-audit.json), raw `six-pulses.json`/`six-before-after.jpg`.

발행 이유: [carry 분기](../../harness/zone_solo_cyan_v106.py#L447), [펄스 선택](../../harness/zone_solo_cyan_pulse_cal.py#L102). 경로는95초 추정 위치에서1회 생성됐고, [drive](../../harness/zone_solo_cyan_pulse_cal.py#L162)는 목적지가 같으면 A*를 다시 하지 않는다. 펄스별 현재 RGB 장애물/진행 부족 제약은 없고 위치 불확실은 dev_light 기록이다. ARM_COLLISION_GUARD는 [팔 자세 전환](../../harness/zone_solo_cyan_v106.py#L215)의 가드여서 이 옆 이동을 검사한 증거가 아니다. 기존 LK 알림은6회 중1회(110.20초)만 stationary; 3회 texture unknown,2회 changed로 놓쳤다.

새 후보는 S2 Runtime 한 파일과 오프라인 어댑터에만 추가했다. `ground_flow_noise_v1`는 완료된 큰 병진 펄스의 자기 RGB만 처리하며, 160ms 기존 지연 큐 **안쪽**의 capture clock에서 동작한다. 동일 RGB를 기존 벽 관측 경로에 그대로 전달한다. 기본off wire/record, 합성 강체/회전/오점, 관측 지연/unknown, 기존 pulse/floor **15 passed/27.04초**. 결과 전 고정된3px/95% 등 기존 관측 gate는 변경하지 않았다.

### s2v23 결과 — 벽 막힘은 확정, 공분산 증가만으로 해결하지 못함

고정 실행 소스 **7038d90a**로 baseline/candidate 각각5202frame 완료. baseline은 poses/amcl/visibility/contact 원본과 정확히 같고, 원본 입력 해시·커밋된 후보 해시·평가 분리를 [검증](blocked-pulse-verification.json)했다. [판정](blocked-pulse-summary.json)의13개 기준 중10개 통과, **6회 coverage·운반 RMSE·갱신 수** 실패다. 결과 뒤 파라미터/특징수/문턱 변경이나 두 번째 후보 재생은 하지 않았다.

|조건|하중 endpoint xy/yaw RMS|평균 Gaussian NLL↓|운반 RMSE m|운반 informative 갱신|최장 공백 s|
|---|---|---:|---:|---:|---:|
|baseline|24.132mm / 1.192°|59.9262|2.023583|27|33.85|
|ground_flow_noise_v1|24.132mm / 1.192°|44.5762|2.051483|26|33.85|

평균 응답은 의도대로 동일하다. NLL은 **완료 펄스의 RGB를 읽은 뒤**의 조건부 공분산 적합도이며, 펄스 전 예측 정확도나 미래 성공으로 해석하지 않는다. 정상/기타271펄스의 공분산 증가는0; 다만 큰 병진35회 중 VO 측정은3회, texture unknown29·rigid consensus unknown2·spatial support unknown1이다. 작은 병진/회전242회는 등록 범위 밖으로 변경하지 않았다. 이 때문에 “나머지 펄스를 정확히 판독했다”는 뜻은 아니다.

|문제 펄스 s|자기 RGB 결과|tracks/inliers|측정 병진 크기 mm|측정 yaw°|증가 뒤 옆 3σ cm|실제 옆 예측오차 크기 cm|
|---:|---|---|---:|---:|---:|---:|
|107.35|spatial support unknown|14/11|N/A|N/A|0.921|15.055|
|108.30|measured|23/18|1.136|0.297|4.588|16.669|
|109.25|measured|25/23|1.931|0.352|4.589|16.630|
|110.20|measured|23/23|1.893|0.002|4.561|16.639|
|111.15|rigid consensus unknown|24/0|N/A|N/A|0.921|16.604|
|113.70|texture unknown|0/0|N/A|N/A|0.921|14.534|

GT 평가로 measured3회의 VO 병진 오차는1.921–3.058mm, yaw0.057–0.126°다. 따라서 **자기 영상에서 진행 부족을 읽을 수 있는 경우는 있었으나**, nominal Q에 원문 sqrt(alpha) scaling을 적용한 3σ 폭4.56–4.59cm는16.63–16.67cm 평균 bias보다 작다. 2D Mahalanobis `d²≤9`에 들어간 문제 펄스는 **0/6(기준≥5/6)**. 나머지3회는 unknown을 정지로 바꾸지 않고 기존 분산을 그대로 썼다. 평균16.72cm를 유지한 채 분산만 키우는 이번 후보는 이 벽 막힘의 해결책으로 **미채택**한다.

관측 보존은 통과: 전체31개 AMCL 후보 시각과 입력 local endpoint 배열, visibility/floor filter audit가 **모두 동일**하다(운반 후보27개). 192.75초의66접점도 삭제되지 않았다. 다만 PF 분포가 달라지면서 KL이1.24e−8→4.57e−16으로 줄어 informative 갱신 하나가 사라졌다. 즉 이번 갱신27→26은 새 gate가 영상을 거절해서 생긴 손실은 아니다. 초기 정지 최대0.105661m는 두 조건 동일. 30초 공백 목표도 여전히 미달이다.

**새 full DEV/시뮬레이션/렌더/모델 호출0**, seed/번들 예약0. 후보는 기본off이며 새 실행 번들에 채택하지 않았다. 새 lifted/inside·운반 실제 가시율·B 거리·would-stop 목록·wall/SIM은 N/A다. 마지막 물리 s1051(v126)의 lifted=true/inside=false·B까지2.178m·wall/SIM1.315929와 합산하지 않는다. 오프라인 두 재생 wall143.50초는 시뮬레이션 wall/SIM 속도가 아니다.

raw `/Users/changmin/projects/ugrp/outputs/s2-blocked-pulse-20261007/`의 `result.json`에 원본25옵션+후보 옵션을 보존했다. `six-pulses.json`, `motion-score.json`, 전체 재생2개·검증·참고 원문/해시는 로컬 보관이며 원격 백업이라고 하지 않는다. 원본은 변경/삭제하지 않았다. [참고 자료 다운로드 검증](blocked-pulse-sources.json).

영상은 **새 실행이 아닌 저장된 s1051의95–115초** 자기 RGB401프레임을 4배속80fps/H.264로 묶었다: `/Users/changmin/projects/ugrp/outputs/s2-blocked-pulse-20261007/s1051-north-wall-4x.mp4`(5.0125초). [영상](http://127.0.0.1:6007/video/262b0aa5172ea4ce95c4), 원본 프레임 SHA와 ffprobe는 raw `video-provenance.json`에 있다.

TensorBoard **1007-s2-blocked-pulse-v2 / 5뷰36scalar**를 source→event→live API/HParams와 대조했고, 등록 영상은 HTTP 전체 재다운로드 SHA까지 일치했다. [대시보드](http://127.0.0.1:6006/?runFilter=1007-s2-blocked-pulse-v2&smoothing=0#timeseries), [전달 검증](blocked-pulse-delivery-verification.json). 수치 대조만 했으며 PID52016/공용logdir/다른view키는 유지했다. 첫 비공개 snapshot은 SSE 비율을 수기로 옮긴 불필요한 scalar를 제거한 v2로 대체했다(95.837803→정확95.837822%; raw `delivery-correction.json`). 이전 snapshot/원본을 보존했고, 최종 기본 보기는 v2만 가리킨다.

`ugrp_session s2-blocked-pulse-offline` **stopped**, 물리 실행 없이 **agent_lock=null**. 다른 프로세스 종료/다른 PR·worktree 수정0. 전체 GitHub CI는 진행 중으로, 로컬15시험·재생 완료와 구분한다. PR406 DRAFT·병합 금지 유지.

## s2v24 — RGB 실변위 융합·진행 부족 회피 사전 등록 (2026-10-07)

명령 오도메트리는 센서 측정이 아니다. `visual_odometry=ground_flow_ekf_v1`,
`stall_recovery=nav2_progress_v1` 두 옵션(기본 off)을 S2에만 구현한다.
[사전 기준](flow-fusion-criteria.json)의 상수·판정은 s1051 후보 재생 전에 고정한다.
문제 6회 중 5회 이상 RGB 구간 coverage ≥80%, 변위 오차 ≤3.5 cm, 중앙 오차 ≤1 cm,
yaw RMSE 비악화, 전체 하중 변위 RMSE 개선·비문제 구간 비악화를 요구한다.
운반 시각 갱신 ≥27회, 최장 공백 ≤33.85초, 운반 RMSE <2.0235827759 m,
정지 스캔 최대 오차 ≤0.5 m, 같은 시각 측정 열 100% 보존도 모두 통과해야 한다.
진행 부족은 2개 연속 유효 펄스·1.5초·95% 변위 상한 3.5 cm 기준으로 판단한다.
4번째 문제 명령 전 해당 방향 차단이 재생에서 확인되어야 한다.
미달이면 새 물리 실행·seed·번들 없이 결과를 보존한다. 본 연구 확증이 아니다.

방법: Seegmiller 2011 II-C–F의 LK/바닥 평면/RANSAC SE2를 연속 프레임에 적용하고,
robot_localization EKF의 differential velocity 관측·Kalman gain·Joseph 공분산을 사용한다.
바닥 텍스처 미관측은 정지가 아니다. 명령과 광류 변위를 이중 합산하지 않도록
완료 펄스(최대 0.75초)를 지연 처리하고 원래 벽 관측은 시간순으로 한 번만 처리한다.
이는 ROS 전체 노드 이식이 아니라 S2의 유한 펄스·기존 160 ms 지연 인터페이스 어댑터다.
종전 임의의 2차원 점 분산 조건 대신 SE2 Jacobian의 실제 rank를 검사한다.
사용자 지적 pitch 0.9–2.8°를 사전 고정 nuisance 범위로 두고 광류 스케일 민감도를
공분산에 전파한다. 저장된 실제 카메라 자세는 사후 평가에만 쓴다.

Nav2 진행 검사와 거리·시간 한정 BackUp/DriveOnHeading을 따른다.
옆 이동 반대 방향 회피는 mecanum에 필요한 확장이고, 명령 방향의 장애물 실측은 아니다.
기존 자기 위치 추정·정적 지도의 충돌 검사로 회피를 제한한다.
저장 명령 재생에서 반사실 회피 성공은 평가할 수 없으므로 차단·회피 분기는 shadow로,
발행 경로는 합성 관측 시험으로 분리한다. 실제 회피는 위 기준 통과 후 새 DEV에서만 검증한다.
공용 camera_robot_port·다른 제어기·카메라 mount/FOV는 변경하지 않는다.

출처(원문 확인):
- [Seegmiller 2011](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf), II-C–F.
- [robot_localization EKF](https://github.com/cra-ros-pkg/robot_localization/blob/ros2/src/ekf.cpp), [설정](https://github.com/cra-ros-pkg/robot_localization/blob/ros2/params/ekf.yaml): 명령은 control, VO는 측정; 기본 vx/vy/vyaw Q=.025/.025/.02.
- [Nav2 SimpleProgressChecker](https://github.com/ros-navigation/navigation2/blob/main/nav2_controller/plugins/simple_progress_checker.cpp), [DriveOnHeading](https://github.com/ros-navigation/navigation2/blob/main/nav2_behaviors/include/nav2_behaviors/plugins/drive_on_heading.hpp): 거리·시간 검사, 회피 거리/시간 제한과 충돌 검사.

### s2v24 결과 — 기준 실패, 새 full 미실행
사전 등록 `0ef95343` → 구현 `5c984bd5` → NumPy 불리언 저장 수정 `f73a4ede`.
`visual_odometry=ground_flow_ekf_v1`와 `stall_recovery=nav2_progress_v1`는 기본 off 탐색 옵션으로만 보존한다.
기존 v126 번들과 실행은 그대로이고 새 번들·seed·시뮬레이션·렌더·모델 호출은 0이다.
|시각 SIM s|실제 이동 cm|RGB coverage|광류 직접 누적 오차 cm (사후 분해)|EKF 오차 cm|XY σ cm|진행 상한 cm|
|---:|---:|---:|---:|---:|---:|---:|
|107.35|1.706|93.3%|1.087|16.009|15.50|46.28|
|108.30|0.089|100.0%|0.097|2.555|17.19|36.87|
|109.25|0.127|100.0%|0.333|9.679|15.89|41.37|
|110.20|0.083|100.0%|0.320|0.849|15.56|31.95|
|111.15|0.135|100.0%|0.347|3.824|17.29|38.34|
|113.70|2.374|60.0%|4.059|4.501|12.03|30.83|

문제 6회 중 coverage≥80%는 5회지만, **등록한 EKF 변위 오차≤3.5 cm는 2/6**(필요 5/6),
중앙 오차 4.162 cm(기준≤1 cm)다. yaw RMS는 7.113→4.742°로 개선됐다.
전체 하중 277펄스의 변위 RMS는 2.413→1.658 cm지만, 문제 6회를 제외한 271펄스는
0.498→1.167 cm로 악화해 정상 이동 보존도 실패했다.
|조건|운반 RMSE m|유효 시각 갱신|최장 공백 SIM s|집기 전 정지 최대 오차 m|
|---|---:|---:|---:|---:|
|baseline|2.023583|27|33.85|0.105661|
|candidate|1.719476|26|33.15|0.105661|

운반 RMSE는 15.0% 개선됐지만 갱신 수 기준(≥27)에 1회 미달한다.
명령 odometry에서 측정 odometry로 바뀌면서 AMCL 운동 trigger 시각도 달라졌다.
공통 후보 시각은 4개이고 해당 접점 배열은 100% 동일하다. 모든 5,202 원본 RGB 해시를
확인했고 지연한 525프레임을 순서대로 전달했다. 벽 영상 삭제·마스크 변경은 없다.
이것을 모든 31개 관측이 같은 시각에 수락됐다는 뜻으로 해석하지 않는다.
**가장 큰 남은 문제는 광류 자체보다 현재 EKF 융합 단계의 오차 증폭**이다.
같은 측정·fallback을 직접 누적한 사후 분해는 첫 펄스 1.087 cm, EKF 후 16.009 cm다.
109.25초도 0.333→9.679 cm다. 큰 pitch nuisance 공분산 아래 constant-velocity 평활과
축간 공분산 결합이 잘못된 속도를 유지하는 설정 문제로 해석한다.
robot_localization 원문도 속도 상수 예측의 수렴 지연을 설명한다. ROS 전체 15상태 필터를
복제한 것은 아니고, S2의 3축 differential velocity/Joseph update 어댑터임을 명시한다.
광류 직접 누적은 5/6이 3.5 cm 이내지만 **사후 원인 분해이며 새 채택 후보가 아니다**.
이번 결과를 보고 Q/R·기준·covariance를 재튜닝하거나 full로 넘어가지 않는다.
회피의 실제 입력은 진행량 평균+2σ다. 6회 상한 30.83–46.28 cm가 3.5 cm보다 커서
shadow 방향 차단 0회, 4번째 명령 전 차단 기준도 실패했다. 무관측을 0으로 만들거나
신뢰구간을 사후 축소하지 않았다. 합성 관측에서는 2개 연속 유효 부족→방향 억제→
−35/60 ms 반대 옆 펄스·거리/시간 한정→재계획 분기를 시험했다. 실제 회피는 미검증이다.
실제 escape 중 미세 펄스는 RGB 진행량을 추가 측정하되 기존 미세 펄스의 PF 예측은 유지한다.
관측된 이동 10 cm 또는 20펄스/10초 한도 뒤 재계획하고 실패 방향은 억제한다.
**pitch/스케일:** 사전 입력 범위 ±0.9°, ±2.8°를 유지했다. 1 mm 이상 측정 161구간의
중앙 스케일 비는 −0.9°=0.9519, +0.9°=1.0531, −2.8°=0.8634, +2.8°=1.1799다.
전체 범위는 각각 0.707–1.246 / 0.755–1.395 / 0.355–1.761 / 0.295–2.741이고,
작은 움직임/회전 혼합에서 비율이 불안정하므로 중앙값만으로 정확도를 주장하지 않는다.
이 범위를 유한차분 Jacobian으로 R에 전파하고 프레임 공유·공통 pitch가 평균화되지 않게
펄스 공분산을 보수적으로 합산했다. 그 결과 6회 XY σ=12.03–17.29 cm다.
GT는 재생 종료 뒤에만 사용했다. 저장된 s1051 coarse 구간 카메라와 고정 보정
(pitch −28.662°) 차이는 −0.503∼−0.171°이고, 이전에 언급된 0.9–2.8°와
같은 수치라고 간주하지 않는다. 실제 카메라 기하로만 평가한 스케일 비 중앙 1.027,
고정/실제 기하의 프레임 변위 차이 중앙 1.907 mm다. 이를 제어 보정으로 다시 넣지 않았다.
**검증·보존:** 관련 3파일 17 passed/17.75초; 직렬화 수정 후 해당 파일 6 passed/0.67초.
off 명령/record 바이트 동일, full 5,202프레임의 poses/amcl/visibility/contact는 기존과 정확히 같다.
raw 해시·실행 당시 커밋 소스 해시·사전 기준 해시를 다시 확인했다.
첫 후보 계산은 JSON 저장 불리언 오류로 결과 파일을 만들지 못해, 같은 수치 알고리즘으로
수정 후 1회 재생했다. 첫 채점의 같은 직렬화 실패와 빈 summary는 보존하고
완료 채점은 `scoring-v2/`에 별도로 썼다. 이는 물리 실패나 추가 후보 튜닝이 아니다.
초기 TensorBoard offline-audit 경로의 schema 거부 스냅샷도 보존했고, 표준 generic 변환으로
새 `1007-s2-flow-fusion-v2` 4뷰/29 scalar를 만들었다. 원본·event·live API·HParams 숫자 검증 완료.
브라우저 UI 확인 주장은 하지 않는다(사용자 수치 대조 범위).
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-flow-fusion-v2%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_updates%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_gap_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fsix_error_pass_count%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fnonblocked_new_xy_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fadmission_pass%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) · [기존 s1051 4배속 영상](http://127.0.0.1:6007/video/262b0aa5172ea4ce95c4).
새 lifted/inside·실제 벽 하단 가시율·B 거리·would-stop·wall/SIM은 **N/A**다.
이전 full s1051의 lifted=true/inside=false, wall/SIM=1.315929를 이 후보 결과에 승계하지 않는다.
두 offline ugrp_session은 stopped. agent_lock은 획득하지 않았으며 종료 확인 시 null.
다른 PR/프로세스/worktree와 원본 이미지·로그는 수정/종료/삭제하지 않았다.
로컬 raw: `/Users/changmin/projects/ugrp/outputs/s2-flow-fusion-20261007/`.
[분석·6회 표](flow-fusion-analysis.json), [result/options](flow-fusion-result.json),
[원문 출처·해시](flow-fusion-sources.json), [채점기](score_flow_fusion.py),
[층별 분해 재현](analyze_flow_layers.py), [TensorBoard 수치 검증](flow-fusion-delivery-verification.json).
로컬 보존은 원격 raw 백업이 아니다. PR #406 DRAFT·병합 금지를 유지한다.

## s2v25 — slip 판정 구간만 시각 변위 대체 (2026-10-07 사전 등록)

[기준](slip-detect-criteria.json)을 후보 재생 전에 커밋한다. 새 옵션
`slip_detection=slip_detect_v1` 기본 off, 이전 EKF/운동 노이즈 옵션 off.
문제 6회 중 ≥5회 대체·오차≤3.5 cm, 중앙오차≤1 cm, yaw RMS 비악화,
전체 하중 변위 RMS 개선·정상 271펄스 비악화·비대체 profile 바이트 동일을 요구한다.
운반 갱신≥27, 최장 공백≤33.85초, RMSE<2.0235827759 m, 정지 오차≤0.5 m,
동일 시각 벽 측정 열 100% 보존, 4번째 문제 명령 전 shadow 방향 억제도 요구한다.
모두 통과할 때만 새 번들/seed 사전 등록 후 S2 full 1회. 미달이면 v122 이후 비교표를
만들고 종료하며, 문턱/공분산/관측 조건 재튜닝은 하지 않는다.

### 먼저 확인한 EKF 입력 — 명령 평균을 믿었다는 가설은 해당 구현과 다름

107.35초 펄스의 전체 수치와 15구간 입력/P/R/K/출력을 [감사 JSON](slip-ekf-input-audit.json)에
저장했고 기존 산출물과 1e-14 이내 재현했다. 16.01 cm는 출력 이동량이 아니라 평가 오차다.
명령 평균 `[0.0008384, 0.1672000, -0.0265373]`(m,m,rad), 공분산 대각
`[2.01944e-6, 9.42189e-6, 3.57534e-5]`다. 유효 광류 구간에 명령의 EKF 가중치는 **0**.
107.45초 unknown 1구간만 필터 밖에서 명령 예측을 썼다. 광류+그 fallback 누적은
`[-0.0025800, 0.0255168, 0.1315296]`, EKF 누적은
`[-0.1501988, -0.0273944, 0.2409037]`이다. 명령 옆 +16.72 cm와 다른 방향이다.

107.55초에서 이전 **시각 속도** prior는 `[0.002830,0.085100,0.846665]`,
현재 광류 속도는 `[-0.107165,0.075149,0.955319]`(m/s,m/s,rad/s).
P 대각 `[0.211852,0.008862,0.061188]`, R 대각 `[0.556158,0.028902,0.097088]`이며
칼만 이득은 아래와 같다(전체 공분산은 JSON 참조).
```text
K = [[-0.391457, -3.420692, -2.979358],
     [-0.109025, -0.174097, -0.421714],
     [ 0.359626,  1.838342,  1.932201]]
```
회전 innovation이 x 보정에 −0.323719 m/s를 기여해, 관측 x=−0.107165보다 큰
출력 x=−0.243792 m/s를 만들었다. 즉 명령/광류 가중 비율 문제 대신
큰 상관 R/P를 가진 시각 속도 필터의 축간 결합·시간 평활이 직접 관찰된 원인이다.
이전 README의 'EKF 단계 증폭'은 이 벡터/행렬을 의미한다.

### 문헌과 적용 차이

- [Maimone et al. 2007](https://robotics.jpl.nasa.gov/media/documents/rob-06-0081.R4.pdf), pp1,17: 유효 VO로 초기 wheel estimate를 보정하고 실패하면 원래 추정을 유지; 명령40 cm 대비 시각진행20 cm 미만을 50% 초과 slip으로 본 예. 이번 후보 문턱0.5는 이 예를 고정 적용하며 보편 상수로 주장하지 않는다.
- [Kilic et al. 2022](https://arxiv.org/pdf/2207.13629), Eq1: kinematic/body 진행 비율로 slip 정의. 이 논문의 IMU 필터를 가져오는 것은 아니다.
- [Reina et al. 2006](https://www.vagostudio.com/giulio/wp-content/uploads/2013/11/TM06.pdf): encoder/gyro/current 사이의 결정론적 불일치 검사. 현재 S2 입력에는 이 측정이 없어 직접 구현이라고 부르지 않는다.
- [Ojeda et al. 2006 저자 저장소 초록](https://iris.poliba.it/handle/11589/262359): 전류 기반·지형 정보가 필요하고 옆 slip에는 한계. 초록 확인, 전문 미확인. 구현에 전류/GT를 추가하지 않는다.

양의 명령 방향으로 투영한 순수 광류 변위/고정 명령 변위가 0.5 미만일 때만
해당 pulse curve를 광류로 대체한다. 이때 measured XY 방향과 yaw를 그대로 둔다.
연속 프레임 LK가 실패하면 마지막 유효 keyframe과 최대0.15초까지만 다시 매칭한다.
펄스 끝까지 연결되지 않으면 unknown이며 명령값을 유지한다(0이나 command fill을 VO로 위장하지 않음).
정상 펄스의 기존 평균·공분산은 변경하지 않는다. 바퀴 속도 센서가 없으므로 엄밀히는
명령 대비 실행 부족 판정이며 벽 막힘/바퀴 마찰을 센서만으로 구별했다고 주장하지 않는다.

pitch ±2.8° 공통 보정 스케일 민감도는 크기에만 rank-one XY 공분산으로 더하고,
새 S2 profile에서 full covariance를 유지해 방향/yaw 공분산으로 임의 분산시키지 않는다.
동적 손목 회전이 순수 스케일이라는 주장은 하지 않으며 그 잔차는 이번 후보의 한계다.
기존 Nav2형 연속 진행 검사/방향 회피는 선택 옵션으로 유지하고 재생은 shadow만 검증한다.
모든 runtime 입력은 자기 RGB/명령/고정보정, GT는 재생 종료 후 별도 평가다.

### s2v25 결과 — 국소 slip 대체 통과, 갱신/공백 실패로 종료

사전 기준 **a598929a** → 구현/재생 **adab260b**. 관련3파일 **17 passed / 17.43초**,
기본 off 명령/record 바이트 동일, off 전체5202 frame의 poses/amcl/visibility/contact도
원본과 정확히 일치한다. 두 재생은 ugrp_session으로 완료했고 GT는 그 후 채점에만 읽었다.
[판정](slip-detect-summary.json), [검증](slip-detect-verification.json), [result/options](slip-detect-result.json).

|문제 펄스 SIM s|시각/명령 진행 비율|판정|적용 Δ전진/옆 cm|변위 오차 cm|pitch 크기 σ mm|
|---:|---:|---|---:|---:|---:|
|107.35|0.09585|대체|-0.732 / 1.606|1.105|1.190|
|108.30|0.00784|대체|0.128 / 0.130|0.097|0.226|
|109.25|0.01207|대체|-0.223 / 0.203|0.333|0.467|
|110.20|-0.00283|대체|-0.277 / -0.046|0.320|0.436|
|111.15|-0.01280|대체|0.173 / -0.215|0.347|0.469|
|113.70|unknown|기존 유지|0.084 / 16.720|14.569|N/A|

5/6 대체, 오차≤3.5cm **5/6**, 중앙오차 **0.340cm**, yaw RMS **7.113→5.140°**로
해당 기준은 통과했다. 첫 펄스는 직접 VO로 Δ전진−0.732/옆1.606cm이며 이전 EKF의
Δ전진−15.020/옆−2.739cm와 다르다. 113.70초는 시작 후3프레임 모두 texture unknown,
0.15초 연결 한도를 넘겨 끝까지 유효 VO를 만들지 못했다. 명령값을 그대로 유지해
오차14.569cm가 남았다. 결과를 본 뒤 연결 한도/비율 문턱을 바꾸거나 부분값을 채우지 않았다.

전체 하중277펄스 RMS **24.132→10.071mm**, 그 외271펄스 RMS **4.977mm로 정확히 동일**.
대체5개 외 profile은 변경0이다. 큰 병진35개 중 측정 정상1·slip5·unknown29이며,
나머지242개는 범위 밖이다. 정상 이동을 유지했다는 말은 나머지를 모두 시각 측정했다는 뜻이 아니다.
pitch ±2.8°의 σ는5개에서 **0.226–1.190mm**, 측정 방향의 크기 공분산에만 더했다.
feature fit의 위치/yaw 공분산은 별도 유지한다. 알려진 동적 자세오차까지 없어졌다고 보장하지 않는다.

|조건|운반 RMSE m|informative 갱신|최장 공백 s|초기 정지 최대 오차 m|
|---|---:|---:|---:|---:|
|baseline|2.023583|27|33.85|0.105661|
|slip_detect_v1|1.785303|23|43.50|0.105661|

**15개 기준 중13개 통과, 갱신 수·최장 공백 실패**다. 마지막 유효 갱신197.55초 이후
201.20/209.90초의96/10열 우도는 상수(KL 약1.09e−17/−1.14e−16)여서 보정하지 못했다.
운반 끝241.05초까지43.50초 공백이다. 광류로 이동량을 바꾸면서 AMCL 이동 trigger와
입자 분포가 바뀌었으며, 전체 측정 후보31→29개·공통8시각의 접점 배열은100% 동일하다.
원본 RGB5202장 해시 확인, 지연525 frame 순서 보존·벽 영상 누락0이다. 상수 우도가
정보를 못 주는 원인을 새 gate/재샘플링 설정으로 추측해 고치지 않았다.
[갱신/unknown 진단](slip-detect-diagnostics.json).

기존 진행 검사 shadow는 **110.00초 방향 억제**, 네 번째 문제 명령110.20초부터 차단해
사전 기준을 통과했다(고정 명령 중35회가 차단 대상). 실제 기록 명령은 변경하지 않았고
실물/새 시뮬레이션 회피 성공이 아니다. 실제 회피의 도착/충돌 성능은 미검증이다.

**미채택: 새 full·물리·렌더·모델 호출·seed·번들 예약0.** 기본off 탐색 후보로만 보존한다.
실행기/번들에는 입장시키지 않는다. [v122 이후 위치 추정 시도 한 표](localization-attempts-v122.md)로
전체 이력을 정리하고 이번 시도를 종료한다. 새로운 lifted/inside·벽 하단 가시율·B 거리·
would-stop·wall/SIM은 N/A. 마지막 실제 s1051의 true/false, B까지2.178m,
wall/SIM1.315929를 후보 결과에 승계하지 않는다. offline wall147.943초는 wall/SIM이 아니다.

원본과 새 raw는 로컬 보존: `/Users/changmin/projects/ugrp/outputs/s2-slip-detect-20261007/`.
새 TensorBoard **1007-s2-slip-detect / 3뷰22scalar**, source→event→live API/HParams 수치 대조 완료.
[대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-slip-detect%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_updates%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_gap_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fsix_error_pass_count%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fnonblocked_new_xy_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fadmission_pass%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) · [검증](slip-detect-delivery-verification.json).

기존 s1051 4배속 영상은 등록/HTTP 재다운로드 SHA까지 재확인했다. 새 영상/실행 증거가 아니다.
사용자 수치 대조 범위로 브라우저 UI 확인은 주장하지 않는다. 기존 viewer PID52016/logdir와
다른 view 키/PR/worktree/process는 유지했다. session stopped, 물리 잠금 미획득·status=null.
PR406 DRAFT·병합 금지. 재튜닝/추가 후보/추가 재생 없이 종료한다.

## s2v26 / v127 — 사전 기준 대비 의도적 이탈 (관리자 승인, 2026-10-07)

**s2v25 재생 FAIL은 그대로 유지한다.** 갱신27→23·공백33.85→43.50초는 등록 기준
실패다. 관리자는 고정 명령 열린 루프에서 추정 자세가 바뀌어도 다음 행동이 바뀌지 않는
한계가 갱신 저하에 기여했을 가능성을 제시하고 **닫힌 루프 S2 full DEV 딱1회**를 승인했다.
가능성은 검증할 가설이지 확정 원인이 아니다. 이번1회에만 기존 전 기준 통과 요구에서
의도적으로 이탈하며 재생 결과를 소급 PASS로 바꾸지 않는다.
[기계 판독 사전 등록](registration-v127.json).

**새 seed1052 / P1-2 → door_1 → B/place / zone-s2-realism-v127 / workflow7.20.0**.
main+열린15PR의 최대126/7.19.0과 seed 미사용을 확인했다
([번호](v127-number-reservation.json), [seed](v127-seed-audit.json)).
s1051의25개 채택 옵션 + `slip_detection=slip_detect_v1`만 켠다. freeze ON,
nav2_observed_v1·고정 바닥 외형·실물 운반/blind 파지·무하중+sag·펄스 보정·관측 격리·
RGB 정체 기록·dev_light 유지. `stall_recovery=off`, 이전 EKF/잡음/하중 재보정 off.
slip 구현과 문턱/공분산은 adab260b에서 바꾸지 않는다. 옵션 기본 off, 새 번들 명시 on.

lifted/inside, 운반 informative 갱신·공백, GT 평가 RMSE·실제 하단 가시율·B 거리,
would-stop 목록, wall/SIM을 s1051과 나란히 보고한다. 성공률·인과 개선·연구 확증으로 합산하지 않는다.
옆 펄스는 종료+정지 꼬리 horizon의 예측/실제 이동 합계비와 펄스별 분포를
하중/profile/slip 대체 여부로 평가한다. 실제0은 별도 보고. PR405 egomap15
1.54/0.69m(약2.23배)는 사용자 제공 참고이며 보정/합산에 쓰지 않는다. GT는 종료 후 평가만.

시험 통과→이 문서/seed 먼저 커밋→실행 연결 시험/소스 커밋·push→lock acquire→
ugrp_session 단일 실행. SIM900초·wall10800초 cap. 불확실/보수 가드는 기록만;
실제 낙하·집게 이탈·기울기·오류·eval 정체120초/1cm에서 중단한다.
ENOSPC는 HOST_ERROR·부분raw 보존. 어떤 결과든1회 뒤 종료, 추가 튜닝/재실행 없음.
PR406 DRAFT·병합 금지. 시뮬레이션은 아직 시작하지 않았다.

사전 등록 커밋 **e8bff34f** 이후 v127 연결을 구현했다. 관련2파일 **8 passed / 20.64초**;
기본off 동일, 새seed/정확옵션/관리자이탈/failed판정 유지, 실제 Runtime 생성과
물리 없는 HOST_ERROR 결과 보존, 표준workflow 등록을 확인했다. [검증](v127-local-verification.json).

### v127 / s1052 닫힌 루프 1회 결과 — 집기 전 도크 행 미식별, LOCAL_TIMEOUT

실행 소스 **18e5e42ed6ade8727d39b8a6f8d2b8cf0aab4daf**, v127/7.20.0,
seed1052/P1-2/B/place. 사전 이탈·seed 커밋 e8bff34f 이후1회 실행했다.
**STAGE_FAILED / LOCAL_TIMEOUT / lifted=false / inside=false**. 블록은 원래 바닥에
남았으므로 floor=true/stable=true를 내려놓기 성공으로 해석하지 않는다.
SIM900초 case 상한으로 종료(total SIM901.30초, reset 포함). 모델 호출0, 새 물리1회,
추가 실행0. 기존 s2v25 재생의 FAIL은 그대로다. [완료 요약](slip-full-summary.json).

|지표|s1051 / v126 (기존)|s1052 / v127 (이번)|
|---|---:|---:|
|lifted / inside|true / false|false / false|
|종료|STAGE_REACHED_UNQUALIFIED|STAGE_FAILED / LOCAL_TIMEOUT|
|운반 구간|87.00–241.05 s|미도달|
|운반 informative 갱신 / 최장 공백|27 / 33.85 s|N/A / N/A|
|운반 XY RMSE (평가)|2.023583 m|N/A|
|벽 하단 실제 가시율: 전체열 / 검출열 (운반1Hz)|32.7218% / 54.3706%|N/A / N/A|
|cyan→B 영역 경계 / 중심|2.178372 / 2.649795 m|4.211072 / 4.646302 m|
|would-stop: ARM_COLLISION_GUARD|7|7|
|would-stop: POSE_UNCERTAIN|341|1074|
|would-stop: VISUAL_STALL_SUSPECTED|1|0|
|would-stop: CYAN_NOT_UNIQUELY_VISIBLE|0|37|
|wall / total SIM / wall÷SIM|347.865758 / 264.35 / 1.315929|1095.577661 / 901.30 / 1.215553|
|명령 / own RGB / 모델 호출|3818 / 5202 / 0|37014 / 18001 / 0|
|slip 측정·대체 펄스|옵션off|0 / 0 (하중 미도달)|

원본 posthoc의 visual_updates=0은 carry_window=null에서 나온 값이므로 표와 새 TB는
**운반 미측정**으로 처리하고0회인 운반 실행으로 세지 않는다. seed·초기 행·경로·길이가
다르므로 시간 비율이나 성공률을 합산하거나 slip의 속도/성능 효과로 해석하지 않는다.
두 실행 모두 freeze ON이며, 이전 freeze OFF s1042의2.587649 wall/SIM과도 조건이 다르다.

**가장 큰 남은 원인 하나: 초기 도크 행을 식별하지 못한 상태에서 prior 평균으로 이동.**
표준 Scene은 seed별 로봇 도크 행 배치를 섞는다(`sim/zone_arena.py:356`,
`sim/solo_cyan_v106.py:28`). s1051 실제 r3 y=−0.849995m, 이번은 **−2.249995m**다.
기존 제어 prior는 공개 시작영역 mean `[−0.8982,−0.85,0]`, std `[0.15,2.8,0.174533]`로
실제 행을 모른다는 계약이다(`harness/zone_solo_cyan_v106.py:103`).
이를 실제 위치와 같다고 가정하거나 평가 좌표로 초기화하지 않았다.

첫 바퀴 명령12.00초 전 실제 최대 이동은 **0.958mm**, 추정 최대 오차 **1.428671m**.
11.95초 보고 mean `[−0.817525,−0.824242]`, σxy **1.221919m**, 마지막 갱신2.25초다.
이미 넓고 행이 미식별인 prior의 평균이 틀린 것이며, 정지 동안1.429m가 새로 이동했다는
뜻이 아니다. 2.25초 정지 관측은52열·KL0.02931인1회뿐으로 행을 구분하지 못했다.
dev_light는 POSE_UNCERTAIN을 기록하고 진행했다.
첫 탐색 도착22.80초에 추정 `[−0.483973,−0.876279]` 대 실제
`[−0.598909,−2.241701]`(오차 **1.370252m**)로, cyan이 있는 행에 도착하지 않았다.
탐색 관측74회·확인 불가37회가 반복됐으며 최종 위치오차 **1.255420m**다.
전체 집기 전 informative 갱신은3회(2.25/19.70/34.50초), 이후866.80초 공백이다.
이 값을 운반 fix 공백으로 쓰지 않는다. [상세/코드 근거](slip-full-search-diagnosis.json).

**PR405 egomap15 참고와 옆 펄스 평가:** GT는 종료 후에만 읽었고 재보정하지 않았다.
고정 프로파일의 종료+정지 꼬리 horizon에서 body-frame XY 변위 크기를 펄스마다 합산했다
(전체 궤적 길이 또는 net 이동과 다른 정의). 이번 무하중 옆23펄스는 명령 **0.159127m** /
실제 **0.156787m** = **1.014924배**, 순수 옆 성분 합계비 **1.020895배**다.
펄스별 XY 비율 중앙1.029901, p95 1.393091, 최대1.483435; 0변위0개, XY RMS1.304mm.
이 무하중 표본에서2배 과대는 없지만 **하중 옆 표본0개**라 운반 중 같은 현상을 배제할 수 없다.
s1051의 운반 옆72개 합계비는6.104085/5.112716=1.193903배(벽 막힘6회 포함),
최대 펄스비201.94배로 합계비가 막힘을 숨긴다. 사용자 제공 egomap15 1.54/0.69≈2.23배는
프로토콜/하중/경로가 다른 참고이며 합산하지 않는다. 모든 profile/load별 분포는 요약과
raw `s1051/1052-pulse-evaluation.json`에 있다. **slip 닫힌 루프 운반 효과는 이번에 검증하지 못했다.**

**검증/운영:** 관련8시험 통과 뒤 실행 소스를 커밋·push했다. 입력27옵션/bundle/result 일치,
source/inputs 실행중 변경false, 원본 manifest·source closure·RGB18001장 해시를 확인했다.
최초 직접 셸은 상속 nice5 검사에서 물리 시작 전에 거부됐다(raw 생성/lock 획득0).
기존 one-shot launchd 방식으로 driver/session/runner nice0을 확인한 후 실제1회만 실행했다.
renice/상시서비스/재실행 없음. session stopped, 자체 PID61789/61797/61812/61818 종료,
launchd 항목 제거, own lock release 및 종료 후 null 확인. 다른 작업의 잠금/프로세스는 건드리지 않았다.
[검증/분석 소스 해시](slip-full-verification.json).

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-18e5e42e-s1052-P1-2-place/`.
분석: `/Users/changmin/projects/ugrp/outputs/s2-slip-full-analysis-20261007/`.
4배속 MP4: `/Users/changmin/projects/ugrp/outputs/s2-slip-full-analysis-20261007/views/s1052-full/execution.mp4`
(640×480,20fps,4501frame,225.05초; 원본18001장을4칸 간격 선택; 전체decode 통과).
SHA256 `851d556f5ca1c080a23da6e36248cd3db8bab1ad91ff029d452aed655caaeb5f`.
TensorBoard **1007-s2-slip-full-v127 / 2뷰26scalar** 원본=event=live API/HParams 일치,
영상 등록·HTTP 재다운로드 SHA 확인. 기존 s1051은 참고뷰이며 새 실행으로 중복 계산하지 않는다.
[대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-slip-full-v127%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Flifted%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Finside%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_updates%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_update_gap_sim_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fremaining_to_b_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fwall_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fsim_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fcommands%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) · [전달 검증](slip-full-delivery-verification.json).

사용자 지시대로 수치만 대조했고 UI 확인은 주장하지 않는다. raw는 로컬 보존이며 원격 백업이 아니다.
**이번1회로 종료, 추가 후보/튜닝/물리 실행 없음. PR406 DRAFT·병합 금지 유지.**


## s2v27 — s1051 동일 seed·동일 구성 slip 단일변수 DEV (2026-10-07 사전 등록)

사용자가 **s1051 seed를 의도적으로 재사용한 동일 조건1회**를 지시했다. 이전 새 seed 규칙의
이번 실행 한정 명시적 예외다. 새 확증 표본/성공률 분모로 세거나 기존 결과와 합산하지 않는다.
기존 slip 재생 갱신/공백 기준 FAIL은 유지한다. s1052는 시작 행이 달라 운반 미도달이었다.
기준 s1051/c26e9afd/v126/P1-2→B/place, 후보 **v128/7.21.0/seed1051**.
유일한 행동 차이는 **slip_detection=slip_detect_v1**. 기존25옵션 동일, 추가 stall_recovery=off.
초기 prior·재위치추정은 변경하지 않는다. 공용303소스 중302개 해시 동일; pulse predictor만
명시적 측정 공분산/미사용 noise 옵션 분기가 추가됐고 기존 else는 동일하다. 기준 소스와
기존 프로파일 출력 동등성을 시험한다. [등록](registration-v128.json), [번호 감사](v128-number-reservation.json).
새 raw: outputs/s2-realism-<sha8>-s1051-P1-2-place-slip-matched. 이전 번들/원본 불변.

lifted/inside, 운반 informative 갱신/공백, XY RMSE(평가), 벽 하단 실제 가시율(전체/검출열),
B 영역/중심 거리, would-stop 종류별 수, wall/SIM, slip measured/replaced/unknown,
옆펄스 명령/실제 비율을 나란히 보고한다. 초기 Scene과 slip 적용 전 명령/RGB 동등성을
확인하고 차이가 있으면 단일변수 비교 한계로 기록한다. 결과와 무관하게1회 뒤 종료한다.
freeze ON/dev_light, agent_lock+ugrp_session, nice0, 모델0. 물리 실패/오류/정체 감시 및
900SIM초 상한은 유지. ENOSPC=HOST_ERROR·부분raw 보존. 추가 실행/튜닝 없음.

도크 정보 분석·새 기본-off 초기화 옵션은 이번 실행과 분리하고 **물리 실행 전후에만** 한다.
과제 명세·실물 운영 기록을 먼저 확인하며, 근거 없이 seed/GT 행을 사전정보로 넣지 않는다.
s1052는 탐색/재생 자료다. PR405의2.2배가 v122 미사용 때문이라는 사용자 추정은
여기서 별도 검증하지 않은 참고로 기록한다. PR406 DRAFT·병합 금지.

사전 등록 **b69de99b** 뒤 v128 연결 완료: 관련2파일 **8 passed /20.08s**.
기준 c26e9afd pulse predictor와 현재 predictor를 고정18프로파일×512입자에서 비교해
px/logw/vel 바이트 및 RNG state 동일. [검증](v128-local-verification.json).


### 시작 도크 정보 조사·전역 초기화 재생 사전 기준 (물리 실행 종료 뒤)

**현재 입력 계약에서는 자기 도크 행을 모른다.** `sim/zone_arena.py:356–361`의
행 배치는 setup_only이고 `actor_task:365–381`는 정적 지도/임무만 전달한다.
`harness/zone_solo_cyan_v106.py:103–108`도 seeded row assignment unknown으로 명시한다.
`docs/report/02-experiment-design.md:72–84`의 초기 위치는 **물품 pickup slot**이며 로봇
자기 행 정보가 아니다. `docs/known_map_navigation.md:15`도 실제 시작 위치를 제외한다.
옛 `docs/l1_l2_l3_task_spec.md:1–22`는 TBD 골격, `docs/archive/roadmap_2026-08-13_prekickoff_conflict_copy.md:95–108`는
초기 상태 명세를 작성하라는 TODO여서 도크가 알려졌다는 근거로 쓰지 않는다.

실물 `scripts/red_block/search.py:1–6,88–129,735–750`는 자기 영상으로 머리를 쓸어보고
없으면 바퀴35의 제한된 회전으로 다음 구역을 본다. 자기 전역 도크 좌표를 받지 않는다.
`sim/real_stack_adapter.py:1–5,83–102`는 이 실물 검색 코드를 import한다.
`harness/real_odometry.py:1–6`은 보정 odometry 없음, `docs/real_trace_system.md:92–98`은
명령 서보값/이동 명령과 실제 상태를 구분한다. real_traces 원위치 placeholder가 가리키는
intact archive 경로는 현재 없지만 **기존 ZIP을 직접 읽어**344개 run/result/analysis metadata를 확인했다.
32개 초기 world_state, 27개 commanded pose 기록에는 dock/행 입력이 없고, 11개의 pose는
서보1/3/4/5/6 키(나머지 null), pose_semantics는 commanded_pose_only_no_joint_encoder_feedback다.
initial_pose_age_s/stable는 전역 차체 pose가 아니다. 보관된 표본 범위의 결과이며 모든 실물
운영자가 시작점을 몰랐다는 주장은 아니다. raw audit 해시를 최종 기록한다.

표준 대조: [Nav2 AMCL 원본](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/amcl_node.cpp)
`uniformPoseGenerator/globalLocalizationCallback`은 자유 공간 균일 XY와 ±π 균일 yaw,
동일 가중치로 시작하며 `getMaxWeightHyp`는 전역 평균 대신 최대 가중치 군집을 보고한다.
[Spin](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/bt_plugins/actions/Spin/)은
정해진 각도 제자리 회전이다. [Fox/Burgard/Thrun 1998 저자 초록](https://www.cs.cmu.edu/~dfox/abstracts/active-ras-special.abstract.html)은
동작/시선 선택으로 불확실성을 줄이는 능동 위치추정을 설명한다. 이번은 **Nav2 균일 초기화+
최대 군집+유한 Spin**을 적용하고 Fox의 기대 엔트로피 최적화 전체를 구현했다고 주장하지 않는다.

새 후보 `start_localization=amcl_global_active_v1`(기본off), S2 Runtime에만 적용.
기존2000입자·지도 clearance free-space·측정 혼합 우도 유지, 전체 지도/yaw 균일 초기화,
Nav20.5m/10° 인접 bin 군집의 최대 질량 pose. 수렴은 기존 Nav2 전체 입자0.5m 조건으로
판정해 한 군집의 작은 공분산만으로 다른 모드를 숨기지 않는다. 기존 정지 pan 스캔 뒤
미수렴이면 고정 v122 turn35/.10초 펄스·정지 관측으로 최대4×1.57rad 섹터를 본다.
실제 회전을 안다고 주장하지 않고 command DR 목표/상한을 기록한다.120초 active 예산 뒤
미해결은 dev_light would-stop으로 남기고 원래 경로를 계속한다. 지도 충돌 가드도 동일하게 기록한다.

[재생 사전 기준](dock-global-criteria.json): s1052 첫 이동 전 **1.3≤t<12.0초**,
최종 위치오차≤0.25m·최대≤0.5m·RMSE 개선·잘못된 수렴0·off 출력 동일.
한 후보만 평가하며 미달이면 미채택·기본off 보존. 원본에는 새 body spin 영상이 없으므로
고정 명령 재생은 **초기화/기존 정지 관측만** 평가하고 능동 회전 효과는 미검증으로 남긴다.
새 행동의 shadow 명령은 별도 시험하고 원본 영상이 새 회전 뒤 영상인 것처럼 사용하지 않는다.
물리/렌더/모델 호출0. 이 후보는 이미 완료한 v128 동일seed 비교에는 포함하지 않았다.

### v128 / s1051 matched full 결과 — slip 국소 이동 개선, B 밖 내려놓기

사전 등록 **b69de99b**, 실행 소스 **45b0c173d34f53c2016e2560cdc70c9a908a8325**,
**zone-s2-realism-v128 / 7.21.0 / seed1051 / P1-2→B/place**. 사용자 요청대로 기존
s1051과 같은 seed·25옵션에 slip만 ON(`stall_recovery=off`)으로 실제1회 실행했다.
**STAGE_REACHED_UNQUALIFIED / lifted=true / inside=false / floor=true / stable=true**.
실제 낙하/집게 이탈 종료는 없었지만 B 밖에 놓여 임무 성공은 아니다. 재시도·모델 호출0.
기존 s2v25 열린 루프 재생의 FAIL은 유지하며 같은 seed를 새 확증 분모로 세지 않는다.
[전체 옵션·평가·원본 해시](slip-matched-summary.json).

|지표|s1051 / v126, slip OFF|s1051 / v128, slip ON|
|---|---:|---:|
|lifted / inside|true / false|true / false|
|운반 구간|87.00–241.05 s|87.00–735.65 s|
|운반 informative 갱신 / 최장 공백|27 / 33.85 s|41 / 133.50 s|
|운반 XY RMSE / 끝 위치오차 (평가)|2.023583 / 2.592097 m|1.887833 / 1.059998 m|
|벽 하단 실제 가시율: 전체열 / 검출열 (운반1Hz)|32.7218% / 54.3706%|23.7593% / 28.8262%|
|cyan→B 영역 경계 / 중심|2.178372 / 2.649795 m|0.536406 / 1.149410 m|
|would-stop: ARM_COLLISION_GUARD|7|7|
|would-stop: POSE_UNCERTAIN|341|912|
|would-stop: VISUAL_STALL_SUSPECTED|1|113|
|would-stop: CYAN_NOT_UNIQUELY_VISIBLE|0|0|
|wall / total SIM / wall÷SIM|347.865758 / 264.35 / 1.315929|2056.663955 / 758.95 / 2.709881|
|명령 / own RGB / 모델 호출|3818 / 5202 / 0|4960 / 15094 / 0|
|slip 대체 / 정상 유지 / unknown 유지|off|470 / 2 / 47|
|집기 확인 / 다시 집기|probable_held_inhand_rgb / 0|probable_held_inhand_rgb / 0|

두 조건 모두 freeze ON이다. 닫힌 루프에서 길이·관측·행동이 달라진 전체 실행 결과이며,
시간비를 freeze 전후 효과로 해석하지 않는다. 갱신41회는 정확한 절대 fix41회의 보장이 아니다.
운반 시간이154.05→648.65초로 늘어 갱신 횟수 증가는 빈도 개선을 뜻하지 않으며,
최장 공백133.50초는194.45–327.95초였다. 벽 가시율은 저장된 실제 카메라/화물 기하와
고정 벽·보수적 자기 몸 경계를 이용한 **사후 평가**이며 제어 입력으로 전달하지 않았다.

**동일 조건 확인:** 초기 Scene 동일, 첫2197명령과112.10초까지 RGB2217장 SHA 동일.
최초 명령 차이는112.10초(기준 turn35/.10초, 후보 left65/.65초), RGB 차이는112.15초다.
첫 slip 대체는107.35–108.10초, 광류/명령 진행비0.0958473이다. 다만 추정 pose 자체는
slip 버퍼의 t_est95.00 대 기준95.04 때문에95.20초부터 작은 차이가 있어, 대체 직전까지
모든 내부 상태가 같다고 주장하지 않는다. 기준18프로파일×512입자 predictor의
px/logw/vel/RNG 동등성은 앞선 시험으로 확인했다. [동등성](slip-matched-equivalence.json).

**가장 큰 남은 원인: 진행 부족을 측정해도 그 방향 명령을 계속 내보냄.**
slip 대체470펄스 중 **469회 실제 이동<1cm**. 이470회의 XY 예측 RMS는 명령 모델
**166.750→3.148mm**로 개선돼 국소 변위 대체는 작동했다. 그러나 단일변수 조건의
`stall_recovery=off`이므로 방향 차단/탈출 행동은 없고 진행 부족 명령을 반복했다.
모든 접촉 원인을 새로 확정한 주장은 아니다(새 접촉 렌더 없음). 끝 위치오차1.060m와
B 밖 내려놓기도 남았다. [국소 효과](slip-matched-effect.json). 수정·추가 실행 없이 기록한다.

운반 옆579펄스의 동일 종료+정지 꼬리 horizon에서, 명령 예측합87.186595m /
실제합7.963245m = **10.948627배**, slip 적용합9.795362m / 실제 = **1.230072배**다.
전체 운반 옆 예측 RMS는150.920→14.622mm. 대체470개만의 이동합 비율은3.81953배로
실제 이동이 매우 작은 구간에서 광류 오차도 여전히 남는다. 무하중69옆펄스는 기준과
동일하며 명령/실제0.998182배, RMS0.925mm. s1052의1.014924배와 같이 v122의 무하중
모델에서2배 과대는 관측되지 않았다. PR405가 v122를 쓰지 않아2.2배였다는 해석은
사용자 제공 가설로 남기며 다른 PR 코드/결과를 이번에 검증하거나 합산하지 않았다.

**검증/운영:** 실행 전 관련8시험 통과 후 소스 커밋·push. 정확한27옵션 bundle/result,
원본 manifest/source closure/RGB15094장 SHA, 실행중 소스·입력 불변 확인.
agent_lock driver68682로 acquire 후 `ugrp_session s2-slip-matched-s1051` 단일 실행.
시작 load3.25/3.79/3.42, 여유43.52GiB; 일회성 launchd nice0, renice 없음.
자체 session/driver/managed/runner 종료, session stopped, launchd 제거, own lock release 및
status=null 확인. 도크 분석은 물리 종료 뒤 시작했다. [검증](slip-matched-verification.json).

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-45b0c173-s1051-P1-2-place-slip-matched/`.
분석: `/Users/changmin/projects/ugrp/outputs/s2-slip-matched-analysis-20261007/`.
4배속 영상: `/Users/changmin/projects/ugrp/outputs/s2-slip-matched-analysis-20261007/views/s1051-slip/execution.mp4`
(640×480,20fps,3774frame,188.70초; RGB15094장에서 stride4; 전체decode 통과).
SHA256 `7695eebcb317904e939269f57a2cd1ffb83f1f7007dfcfc6ad5709c61cec824e`.

### s1052 도크 후보 재생 결과 — 기준 미달, 기본 off·실험 후보만 보존

사전 기준 **b506c16f**, 옵션 구현 **6fd34da9**. `start_localization=amcl_global_active_v1`은
새 S2 Runtime의 명시적 기본-off 옵션이다. 완성 실행 번들에는 입장시키지 않았고,
위 v128에는 적용하지 않았다. off일 때 기존 출력 동일과 균일 초기화·군집·유한 회전
분기·dev_light 가드를 포함한 관련2파일 **8 passed /25.36s** 후 커밋·push했다.

|s1052 첫 이동 전1.30–11.95초 / 214 RGB|기존 off|전역 초기화 후보|
|---|---:|---:|
|informative 갱신|1|1|
|최종 / 최대 XY 오차|1.428663 / 1.428671 m|3.317731 / 3.332278 m|
|XY RMSE|1.422832 m|3.319475 m|
|잘못된 수렴 / 수렴 frame|0 / 0|0 / 0|
|기존 pose 최대 차이(off 동등성)|0|비교 대상 아님|
|사전 위치 기준|기준 자료|**3항목 FAIL**|

넓은 전역 초기 분포를 기존 정지 관측1회만으로 식별하지 못했다. 마지막11군집,
최대 군집 질량0.9885이나 전체 σxy2.214m·Nav2 전체 입자 수렴false라, 큰 군집 질량만으로
자기 위치를 안다고 선언하지 않았다. 최종≤0.25m·최대≤0.5m·RMSE 개선은 모두 실패했다.
전체 지도 균일화는 기존 서쪽 시작영역 prior보다 더 넓다는 차이도 있다.
원본에는 새 body spin RGB가 없으므로 **능동 회전 후 식별 효과는 미검증**이다.
새 시야를 합성하거나 기존 정지 영상을 회전 뒤 관측으로 쓰지 않았다. 미달 후보를 채택하지
않고 추가 튜닝/물리 실행 없이 보존한다. [판정](dock-global-summary.json), [검증](dock-global-verification.json).

원본 비교는 RGB·명령만으로 예측 파일을 먼저 완성하고 GT는 별도 점수 계산에만 읽었다.
물리/렌더/모델 호출0. `s2-global-start-offline`·`s2-global-start-candidate` session stopped.
Nav2 원본은 위 고정 commit의 `amcl_node.cpp`, `pf.c`, `pf_kdtree.c`, `spin.cpp`를 확인했고
URL/해시는 검증 JSON에 보존했다. 레이저 대신 기존 RGB 측정, 고정2000입자, 정적 clearance
free-space, 명령 DR 기반 유한 펄스가 우리 어댑터 차이이며 encoder feedback을 주장하지 않는다.
[실물 archive metadata 감사](dock-real-archive-audit.json)는 기존 ZIP을 읽기만 했다.

**전달:** TensorBoard **1007-s2-slip-matched-v128 / 4뷰44scalar**, 원본→event→live API와
HParams 수치 일치. 새4배속 영상 등록·HTTP206/전체 재다운로드 SHA도 확인했다.
[대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-slip-matched-v128%2F&smoothing=0#timeseries),
[핀 링크·검증](slip-matched-delivery-verification.json). 기존 s1051은 참고뷰이며 새 분모가 아니다.
사용자 요청대로 수치만 대조했고 UI 확인을 주장하지 않는다. viewer PID52016 유지,
공유 view 설정의 자기 키만 추가했다. raw는 로컬 보존으로 원격 백업과 구분한다.
**전체 물리1회로 종료, 잠금 해제, PR406 DRAFT·병합 금지 유지.**


## s2v28 — slip 진행 실패 → 반대 이동 → 재계획 (2026-10-07 사전 등록)

사용자 지시: 도크 행 미지는 보류하고, v128/s1051에서 **slip_recovery=slip_recovery_v1**만
추가한 full DEV 최대1회를 재생 통과 뒤 실행한다. 기본off, 기존 원본/번들/FAIL 보존.
[사전 기준](slip-recovery-criteria.json). 새 seed 표본이 아닌 명시적 동일 seed 반복이다.

표준 [Nav2 SimpleProgressChecker](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_controller/plugins/simple_progress_checker.cpp)는
반경0.5m·시간10초이고 고정 연속 N회 기본값은 **없다**. 동일 방향의 완전한 slip 측정이
이어지는 동안 이 시간/진행 조건을 적용하고 문턱에 도달한 실제 N을 보고한다. 정상·unknown·
방향 변경은 연속 slip 증거를 끊는다. 명령 기반 PF가 갱신으로 점프해도 진행으로 세지 않고
완료된 own RGB 변위의 SE2 합성만 진행 판정에 쓴다.

[기본 BT](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml)는
6 retries, Spin1.57rad·Wait5s·BackUp0.30m/0.15m/s를 사용한다.
[BackUp 기본 port](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/include/nav2_behavior_tree/plugins/action/back_up_action.hpp)의
time_allowance는10초다. 이번은 사용자 순서대로 **정지→BackUp→재계획**을 적용한다.
원본 BT 전체 순서/laser costmap/encoder feedback을 그대로 구현했다고 주장하지 않는다.
메카넘에서는 막힌 발행 방향 반대의 후진/옆이동, 이미 보정된35 fine pulse와 정지 꼬리로
속도≤0.15m/s·최대0.30m 또는10초까지만 시도한다. 더 큰 회전은 추가하지 않는다.
회복 성공은 명령 합이 아니라 완전한 RGB 변위로 확인하고 unknown은 성공으로 채우지 않는다.
static map+자기 추정 기반 가드는 dev_light 기록, 실제 낙하/이탈/기울기/오류 감시는 그대로다.
팔·집게 명령과 운반 자세는 바꾸지 않는다. 실패 방향은 실제 벽 법선을 안다는 뜻이 아니며
자기 추정의 국소 실패지점만 경로 keepout으로 쓰고 관측 지도/PF 벽으로 넣지 않는다.

재생은 s1051-slip의 저장된 own RGB 유래 slip·명령·추정 pose만 읽고 GT는 쓰지 않는다.
각 연속 구간은 **첫 다른 명령까지** 독립 prefix로 평가한다. 통과 기준: 적격 구간≥1,
모든 적격 구간에서 시간 문턱 뒤 즉시 기존 막힌 이동 차단·반대 bounded pulse, 정상/unknown
오발동0, off 출력 동일, 팔 명령 변경0, 회복 timeout/완료 뒤 재계획 시험 통과.
그 뒤 원본 RGB를 새 회복 행동 뒤 영상으로 재사용하지 않으며 재생으로 물리 탈출·fix·RMSE
개선을 주장하지 않는다. 통과 시에만 동일1051/P1-2/B/place full1회, freeze ON/dev_light,
agent_lock·ugrp_session·모델0. SIM900s/wall10800s, ENOSPC=HOST_ERROR·부분raw 보존.
이전 s1051·s1051-slip과3조건 표, 모든 실패·would-stop·wall/SIM을 그대로 기록한다.

사전 기준 커밋 **6306b26d** 후 재생: 적격3구간 모두 **11회 연속 slip**,
117.60 /359.85 /470.05초에서10.25초 진행 부족으로 정지→반대35 fine pulse를 제안했다.
기존 방향 다음 이동0/3, 반대·bounded3/3. 정상/unknown·기본off·회복 완료/timeout 재계획
관련 **11 passed /0.91s**. [재생 PASS](slip-recovery-replay.json)는 첫 변경 명령까지만의
정책 검증으로 물리 탈출/위치 개선이 아니다. 새 회복 영상을 원본으로 대체하지 않았다.

main+열린15PR 최대128/7.21.0 확인 후 **v129/7.22.0** 예약
([번호](v129-number-reservation.json)). **seed1051/P1-2→B/place**를 위 기준에 따라 다시
등록한다([정확한28옵션](registration-v129.json)). 이전v128의27옵션 모두 동일하고
`slip_recovery=slip_recovery_v1`만 추가, 도크 전역 초기화는 포함하지 않는다.
연결 시험 통과 후 실행 소스 커밋·push→잠금→full DEV1회. 아직 새 물리는 시작하지 않았다.

실행 연결·기본off·freeze 제한·HOST_ERROR 보존 포함 **9 passed /28.14s**.
위임 검증의 v128 ID/v129 schema 불일치를 wrapper에서 바로잡았으며 freeze 가드는 유지했다.
[로컬 검증](v129-local-verification.json). 물리 실행 소스는 다음 커밋으로 고정한다.

### v129 / s1051 recovery full 결과 — 반복 명령 차단 후 경로 추종 교착

실행 소스 **d4fee717587ecc3b549aff948252b156b6c05d83**, 기준 사전 등록6306b26d,
v129/7.22.0/seed1051/P1-2→B/place. 28옵션은 v128의27옵션+`slip_recovery`만 다르다.
**PHYSICAL_FAILURE / STAGNATION_120S_LT_1CM / lifted=true / inside=false**.
낙하/집게 이탈을 관측해 중단한 것이 아니라 등록된 eval 정체 감시로 종료했다.
운반 중 종료되어 floor=false·stable=true이며 내려놓기에는 도달하지 못했다.
실제1회·추가 실행0·모델0. [3조건 완료 요약](slip-recovery-full-summary.json).

|지표|s1051 / v126 원본|s1051-slip / v128|s1051-recovery / v129|
|---|---:|---:|---:|
|lifted / inside|true / false|true / false|true / false|
|종료|B 밖 내려놓기|B 밖 내려놓기|운반 중 eval 정체 중단|
|운반 구간|87.00–241.05s|87.00–735.65s|87.00–252.20s|
|운반 informative 갱신 / 최장 공백|27 /33.85s|41 /133.50s|10 /123.05s|
|운반 XY RMSE / 끝 위치오차 (평가)|2.023583 /2.592097m|1.887833 /1.059998m|1.997254 /2.142861m|
|실제 벽 하단 가시율: 전체열 / 검출열 (운반1Hz)|32.7218% /54.3706%|23.7593% /28.8262%|27.8865% /62.3707%|
|cyan→B 영역 경계 / 중심|2.178372 /2.649795m|0.536406 /1.149410m|4.894993 /5.554584m|
|would-stop ARM_COLLISION_GUARD|7|7|7|
|would-stop POSE_UNCERTAIN (raw 호출 수)|341|912|2487|
|would-stop VISUAL_STALL_SUSPECTED|1|113|2|
|would-stop PULSE_RESOLUTION_LIMIT|0|0|1194|
|would-stop CYAN_NOT_UNIQUELY_VISIBLE|0|0|0|
|wall / total SIM / wall÷SIM|347.865758 /264.35 /1.315929|2056.663955 /758.95 /2.709881|381.992106 /252.20 /1.514640|
|명령 / own RGB / 모델 호출|3818 /5202 /0|4960 /15094 /0|3475 /5018 /0|
|slip 대체 / 그중 실제 이동<1cm|off|470 /469|11 /10|
|집기 확인 / 다시 집기|probable_held_inhand_rgb /0|동일 /0|동일 /0|

동일 seed의 진단 반복이며 독립 확증이나 성공률 분모로 합산하지 않는다. 세 조건 모두
freeze ON이다. 이번 wall/SIM이 낮아도 조기 정체 종료/다른 행동·영상 길이의 영향을 포함하며
속도 개선으로 결론내리지 않는다. 운반 말기 대부분이 정지라 갱신 빈도도 직접 비교하지 않는다.
이번 POSE_UNCERTAIN raw 수에는 차단 전 제안과 차단 후 selector 재호출에서 중복 기록된
호출이 포함돼 독립적인2487회 불확실 사건이라는 뜻이 아니다. raw 수는 그대로 보존했다.

**실제 동작:** 연속11개 slip·RGB 진행2.75cm가10.25초 지속된 뒤117.80초에 hold,
117.90–127.50초에 반대옆 −35/.06초25펄스를 냈다.127.90초에10초 회복 예산이 끝났고
RGB 진행은 **0.154431m**, 실제 GT 평가의 순이동은 **0.182144m**(원래 body 옆 −0.182063m)다.
목표0.30m 미도달이라 회복 measured_success=false·timeout=true 그대로다. 순이동 GT는
종료 후 점수에만 썼으며, 실제 이동을 성공 신호/방향 선택에 넘기지 않았다.
같은 시각 A*는 경유점 `[1.0375,−0.5875] → [1.65,0.05]`를 반환했다.

**가장 큰 남은 원인: 방향 차단과 단조 비용 감소 selector 사이의 교착.**
마지막 추정 `[1.039110,−0.630318]`, 다음 경유점 거리 **0.042848m**로 경유점 통과 허용
0.035m 밖이다. 유일하게 비용을0.0018915→0.0013941로 줄이는 +35 fine 옆 펄스의
실패 방향 내적은 **0.956733>0.95**, 실패 위치와 거리 **0.296956<0.5m**여서 차단됐다.
남은 보정 프로파일 중 비용을 줄이는 것이 없어 selector는 hold를 반환했다.
차단 제안1197회, PULSE_RESOLUTION_LIMIT1194회, 재계획1회. 마지막 이동132.45초 뒤
132.85–252.20초 실제 순이동은 **0.661mm**,252.20초에 등록 정체 감시가 종료했다.
129.15초 이후123.05초 시각 갱신 공백은 이 hold 구간을 포함한다.

막힌 옆 펄스를 계속 실행하던 문제는 끊었으나, **대체 펄스 없음이 회복 실패로 전파되어
다음 회복/재계획을 부르는 Nav2식 상태 전이까지 이 어댑터가 연결하지 못했다.**
차단 후 hold에는 새 slip 측정이 없어서 회복도 재발동하지 않았다. 이는 새 후보의 한계이며
가시성 문턱/모션 보정 문제로 돌리지 않는다. 사전 prefix PASS는 첫 차단·반대 명령만의
검증이었고 재계획 후 지속 진행을 보장하지 않았다. full 결과는 **FAIL·미채택**, 기본off
실험 후보로 남기며 이 실행을 근거로 문턱을 바꾸거나 추가 실행하지 않는다.
[상세 수치·평가 근거](slip-recovery-diagnosis.json).

**동일 조건/보존:** v128과 초기 Scene 동일, 첫2209명령 동일.117.80초에 최초로 기존
left65/.65 대신 hold가 나갔다.117.80초까지 RGB2331장 SHA 동일,117.85초부터 차이.
팔/그리퍼/운반 자세는 변경하지 않았으며 낙하·기울기·이탈 감시도 유지했다.
도크 행 미지/전역 초기화는 이번 소스·번들에서 바꾸지 않았고 사용자 확인 대기다.

**운영:** 관련9시험 통과 뒤 소스 commit·push, source/inputs 실행중 변경false,
manifest/source closure/RGB5018장 SHA 확인. agent_lock driver82237, 시작 load3.14/3.79/4.13,
여유43.30GiB, nice0 일회성 launchd, `ugrp_session s2-slip-recovery-s1051` 단일 실행.
종료 뒤 자체 PID82233/82237/82248/82254 종료, session stopped, launchd 제거,
own lock release·status=null 확인. [검증](slip-recovery-full-verification.json).

raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-d4fee717-s1051-P1-2-place-slip-recovery/`.
분석: `/Users/changmin/projects/ugrp/outputs/s2-slip-recovery-20261007/`.
4배속 영상: `/Users/changmin/projects/ugrp/outputs/s2-slip-recovery-20261007/views/s1051-recovery/execution.mp4`
(640×480,20fps,1255frame,62.75초,5018 RGB에서 stride4; 전체decode 통과).
SHA256 `889bf700a3b8a83a0a2413c658dac51b02718b24fc0209126373e1d181240117`.
raw는 로컬 보존이며 원격 백업이 아니다. 이전 번들/원본/재생 판정은 변경하지 않았다.

TensorBoard **1007-s2-slip-recovery-v129 /4뷰50scalar**: 3조건 실행과 prefix 재생을 분리,
source→event→live API/HParams 수치 일치. 새 영상 등록·HTTP206/재다운로드 SHA도 확인했다.
[대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-slip-recovery-v129%2F&smoothing=0&pinnedCards=%5B%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Flifted%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Finside%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_updates%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fmax_update_gap_sim_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fcarry_rmse_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22offline%2Fremaining_to_b_m%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fwall_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fsim_s%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fcommands%22%7D%2C+%7B%22plugin%22%3A+%22scalars%22%2C+%22tag%22%3A+%22result%2Fmodel_calls%22%7D%5D#timeseries) · [전달 검증](slip-recovery-delivery-verification.json).
사용자 지시대로 수치만 대조했고 브라우저 UI 확인을 주장하지 않는다. 기존 viewer PID52016 유지,
공유 view의 자기 키만 추가했다. **추가 실행/튜닝 없음, PR406 DRAFT·병합 금지 유지.**

## s2v29 — 시작 행 미지: Augmented MCL·다중 가설·능동 시선 (2026-10-07 사전 등록)

**사용자 확인:** 실물 로봇은 시작 도크/행을 모른다. 시작 도크를 사전정보로 주는 방법은 금지한다.
s2v28 slip 회복은 실패·기본off로 보존하며, 이번 작업은 도크 위치추정에만 한정한다.
6fd34da9 후보의 s1052 오차 1.429→3.318m FAIL은 그대로 둔다.
오프라인 감사에서 전역 2000입자 중 정답 25cm·15° 주변은 처음 **1개→2.25초 재샘플링 뒤 0개**였다.
행별 질량은 여러 행에 남아 있었으며, 최대 연결군집98.85%를 단일 행의 확률로 해석하면 안 된다.
3.75/5.25/6.75초 다른 정지 pan에는 각각38/36/18개 경계 접점이 있었지만 차체 운동 gate가 제외했다.

[사전 기준](dock-augmented-criteria.json)을 구현·후보 평가 전에 고정한다. 기존 정확도 기준(마지막≤.25m,
최대≤.5m, baseline RMSE 개선)을 유지하고 정답 근처 입자 생존·잘못된 확정 금지·off 동일성을 추가한다.
통과할 때만 **seed1052 full DEV 1회**를 허용한다. 미달이면 물리 실행하지 않는다.
탐색 재생으로 이미 본 s1052를 새 확증 표본으로 세지 않는다. GT는 예측 파일 완성 뒤 별도 평가만.

**표준 원본과 필요한 RGB 어댑터:**
- [Nav2 pf.c 고정 소스](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf.c)의
  정규화 전 평균 우도, slow/fast EMA, `max(0,1-fast/slow)` 전역 무작위 주입과 주입 후 EMA 초기화를 따른다
  (Probabilistic Robotics Table8.3/p258). [공식 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/)의
  예시 alpha=.001/.1을 쓴다. 원본 기본0과 예시값을 구분한다. RGB hit/random 측정식은 바꾸지 않는다.
- [ROS AMCL pf.c](https://github.com/ros-planning/navigation/blob/f44bb1fc2810399165115cc98b530fe4b9397c18/amcl/src/amcl/pf/pf.c)의
  선택 재샘플링(ESS>N/2이면 전체 가중 분포 복사)을 적용한다. 행별 강제 할당·정답 주변 재주입은 없다.
  전역 수렴 전 여러 가설을 유지하고, 최대 연결군집을 확정 위치로 채택하지 않는다.
- [Fox/Burgard/Thrun 1998 원문](https://www.cs.cmu.edu/~dfox/postscripts/ras-active.ps.gz)
  §4.3 식13의 기대 엔트로피 감소로 센서 방향을 선택한다. 비용이 같은 정지 pan5개 중 선택하며,
  기존 카메라·고정 지도·기존 sigma로 중앙 경계 한 광선의 이산 관측 분포를 계산한다.
  레이저와 달리 카메라는 팔에 달렸으므로, 전역 탐색 중 **새 정지 명령 자세당 1회**만 관측한다.
  같은 자세 반복으로 가중치를 계속 곱하지 않는다. 차체 운동 gate·기존 하중/운반 경로는 유지한다.
  녹화되지 않은 새 시선의 효과는 주장하지 않는다. 선택 순서의 그림자 계산은 실제 관측과 별개다.

새 `global_localization=augmented_active_v1`은 기본off S2 오버레이로만 구현한다.
실패한 구 옵션·기존 번들·공용 camera_robot_port·다른 제어기·카메라 mount/FOV는 이번 범위 밖이다.

### s2v29 결과 — 기준 미달, 물리 실행하지 않음

구현 `dff991e5`, 기록 메타데이터 교정 `218fc06d`; [결과](dock-augmented-summary.json),
[평가 전용 기하/입자 감사](dock-augmented-geometry.json), [출처·원문 해시](dock-augmented-sources.json).
모든 후보는 **1.30–11.95초 자기 RGB214장·같은 발행 명령**을 쓴 정지 구간 재생이다.
실제 최대 이동은 **0.958mm**. 이전 원본·FAIL은 덮어쓰지 않았다. 다음 표는 같은 시각의 GT로
동일 채점한 값이며, 이전 문서의 시간 보간 RMSE와 수µm 차이는 원본을 고치지 않고 남긴다.

| 항목 | s1052 기존 off | 6fd34da9 전역 후보 | augmented_active_v1 |
|---|---:|---:|---:|
| 마지막 위치 오차(m) | 1.428663 | 3.317731 | **3.357254** |
| 정지 구간 RMSE(m) | 1.422841 | 3.319469 | **3.288994** |
| informative 갱신 / 재샘플링 | 1 / 1 | 1 / 1 | **5 / 1** |
| 정답25cm·15° 근처 입자 | 평가표 별도 | 1→0(2.25s) | **1→1→1→8→8→8** |
| 잘못된 수렴 확정 | 해당 없음 | 0 | **0** |
| 채택/새 full | 기존 실패 참고 | FAIL / 없음 | **FAIL / 없음** |

8개는 **처음 살아남은 한 입자의 복제**이며 독립 가설8개를 복구한 것이 아니다.
구 후보의 남/중/북 최근접 행 질량은 2.25초 뒤 **36.75/31.40/31.85%**였다.
98.85% 최대 연결군집은 서로 연결된 전역 입자망이며 한 행 수렴이 아니었다(전체XY표준편차2.213m).
새 후보도 최종 **37.862/32.322/29.817%**, XY표준편차2.054m·yaw표준편차130.75°·점유bin781개다.
최대 개별bin 질량은2.072%에 불과하다. 최종 평균(2.1991,−.9536)은 **미해결 분포의 요약값**이며
위치를 알아냈다는 주장이 아니다. 도크/행 목록은 이 평가 표에서만 사용했고 제어기에는 주지 않았다.

**결핍 복구/갱신 감사:** 첫 관측 ESS1714.4/2000, 두 번째1287.6이므로 ROS 선택 재샘플링은
분포를 그대로 보존했다. 5.25초 ESS624.3에서만 재샘플링했다. slow/fast EMA는 마지막
.000631450/.000671549로 `fast > slow`; 주입 확률·실제 주입은 **모든 갱신에서0**이다.
표준 Augmented MCL은 우도가 악화되지 않는 대칭·약정보 상황에서 무조건 입자를 넣지 않는다.
그 동작을 문턱 변경으로 바꾸지 않았다. 기준7개 중 off 동일·입자 생존·오확정 금지·반복 뷰 금지는
통과했으나 **마지막≤.25m·최대≤.5m·RMSE 개선 3개는 실패**했다.

| 정지 시각/pan | 검출 접점/96열 | 구 motion gate | 새 관측 | 화면/기하상 구분 정보 |
|---|---:|---|---|---|
|2.25/1500|52|수락|수락|정면 벽·모서리; 남/중 가설 경계 중앙 차이0px|
|3.75/1230|38|거절|수락|옆 벽·모서리; 남/중 가설 차이34.66px|
|5.25/970|36|거절|수락|옆 벽; 남/중84.87px, 남/북104.07px|
|6.75/1770|18|거절|수락|문이 왼쪽에 보이나 문틀 세로 구조는 현 측정값이 아님|
|8.25/2030|0|거절|접점 없음|문이 중앙 오른쪽에 보임; 최초 밴드 검출에서96/96열 후보 없음|
|11.60/1500(search)|62|거절|수락|다른 pitch의 정지 뷰; 첫 차체 이동 전까지 초기 정책 적용|

위 가설 비교는 **평가에서만 GT x/yaw를 고정**하고 행 y를 바꾼 기하 비교이며 전역 유일성 증명이 아니다.
화면에 행 구분 단서는 있었지만 현재 측정은 회색 벽 하단 접점뿐이다. 실제 행의 접점 잔차도
중앙14.87–16.41px(정지search10.53px) 남아 있다. 현재 metric likelihood field에서
3.75/5.25/6.75초 실제 행 대 다른 행 최대 우도 비율은 **1.00000087 / .99999999 / 1.00000138**로
거의 같다. 이 감사에서 카메라/검출기/우도 상수를 추가 조정하지 않았다.

| 환경/관측 | 대칭·모호성 | 구분할 관측 / 이번 기록 |
|---|---|---|
|균일한 긴 벽 일부|벽에 평행한 위치 이동을 구분 못함|벽 끝/모서리까지 함께 볼 때 거리·방향 차이; 3.75/5.25초 단서 있음|
|사각 외벽만|회전·반사 가설이 남을 수 있음|분리벽 문 배치까지 관측 필요. 외곽 y중심−.85와 문 중심+.05는 .90m 어긋나므로 전체 지도는 정확한 남북 대칭이 아님|
|문·분리벽|벽 하단 일부만 쓰면 문 정보가 사라짐|문 opening y[−.20,+.30], 세로 양쪽 기둥·주변 벽 조합. 6.75/8.25초 실제 RGB에 보임; 현 우도는 문 형상을 직접 안 씀|
|B 바닥색/형상|색만으로 다른 파란 바닥과 단정 불가|정적 지도 `zone_B` 중심(4.6,−2.1), 반폭(.3,.7), 색+구획의 조합. 이 정지6뷰에서는 B가 확인되지 않음|
|바닥 체커|반복 무늬는 절대 행을 식별하지 못함|`sim/masterpi_scene.xml`의 checker/texrepeat14 렌더 자산. map JSON에 격자 절대 phase/크기 계약은 없으므로 절대 위치 신호로 추가하지 않음|
|cyan|이동 물체이며 고정 벽 지도 특징 아님|8.25초 화면에 보이나 이번 전역 측정식에는 넣지 않음|

능동 시선은 식13의 **예측 정보량**만 검증했다. 2.45초 분포에서 pan1500/1230/2030/1770/970은
.95989/.95475/.94980/.94884/.94475nats이다. 실행 시 이미 쓴 방향을 제외하고 남은 방향을 재정렬한다.
고정 명령 재생으로 새 순서의 실제 효용을 입증할 수 없으며, 이를 실제 능동 위치추정 성공으로 세지 않는다.
초기 정책은 정지search 뷰까지 허용하고 **첫 0 아닌 차체 명령에서 종료**, 이후 원래 추적 갱신으로 돌아간다.
미해결은 `GLOBAL_START_UNRESOLVED` 기록만 남기는 DEV 규칙을 유지한다. 본 연구·일반 제어기에는 적용하지 않는다.

**검증/범위:** 기존 AMCL 파일의 해시 고정 시험이 초기 hook 수정안을 거절하여 그 파일은 원래 바이트로
복구하고 새 S2 오버레이에만 update를 격리했다. 관련20시험 및 메타데이터/단계 경계 후속 시험 통과.
214프레임의 off x/y/yaw/std 차이 **0**. 초기 audit의 alpha0 표기만 .001/.1로 교정한 재생은
[pose·입자·관측·시선순위가 모두 동일](dock-augmented-metadata-equivalence.json)했다. 후보 재튜닝은 없다.
GT는 모든 예측 완성 뒤 별도 채점에만 썼다. 물리0·모델0·새 번들0, 기존 v129와 PR406 DRAFT 유지.
raw/소스/검증은 `/Users/changmin/projects/ugrp/outputs/s2-dock-augmented-20261007/`에 보존한다.
따라서 lifted/inside·운반 fix/공백·운반 RMSE·벽 가시율·B거리·wall/SIM·정지 목록의 **새 물리 수치는 없다**.

**전달/종료:** 최종 관련 **21시험/9.20s PASS**. TensorBoard
[1007-s2-dock-augmented-v2](http://127.0.0.1:6006/?runFilter=%5E1007-s2-dock-augmented-v2%2F&smoothing=0#timeseries)
3뷰31scalar를 원본→event→live API와 HParams까지 수치 대조했다.
[검증·핀 링크](dock-augmented-delivery-verification.json). 최초 변환은 파생 뷰 schema 누락으로 실패해
그 snapshot을 보존하고 새 뷰/새 snapshot으로 고쳤다. 브라우저 UI 확인·새 영상·물리 시간 비교는 없다.
기존 viewer PID52016을 재사용했다. 오프라인 세션2개 stopped, 이번 작업 물리 잠금 미획득·현재null.

## s2v30 사전 등록 — 회복 차단 해제와 ground VO (2026-10-07)

중단된 조사 재개: 2710a477 작업 트리 clean, 미커밋 변경 없음, 잠금 null.
[고정 기준·출처·PR405 읽기 전용 복사 해시](ground-vo-criteria.json)를 재생 전에 커밋한다.
기존 s1051 자료는 강성 **off**다. 이를 강성 on 자료로 바꾸어 해석하지 않는다.
회복 종료(성공/시간초과/지원 역펄스 없음)→일시 방향 차단 삭제→정적 지도 재계획;
새 slip 증거만 다시 차단한다. 차단 개수와 회복 시도 횟수는 분리(최대6회).
Nav2 원본은 RoundRobin의 ClearLocal/Global, Spin, Wait, BackUp 순서이고,
각 planner/controller 실패에도 clear→retry가 있다. 항상 BackUp→clear인 원본이라고
인용하지 않는다. 사용자가 지시한 S2의 회복 완료→clear→replan 적용이다.

VO는 고정 K/왜곡/카메라 높이·pitch로 바닥을 역투영하는 평면 호모그래피와
LK 대응점의 강건 SE(2) 정합(Seegmiller 2011 II-C–F)을 사용한다. 매 지원 펄스에
실측 변위를 한 번 전파하며 명령은 누락/가림/완전 동일 RGB 시 예측 대체에만 쓴다.
robot_localization의 예측/측정 분리를 따른 S2 PF 어댑터이며 EKF 재현이라고 부르지 않는다.
픽셀 정합 공분산 + pitch 스케일의 방사 방향 공분산, 바닥/블록 면적·fallback 사유 기록.
정상 펄스 RMS 비악화(수치허용1e-10m), 운반 RMSE 엄격 개선, RGB/벽 관측 보존,
회복 교착 해소를 판정한다. 이전 s1051 재생은 탐색/회귀 검사이며 확증으로 재명명하지 않는다.

PR405 강성 on pitch 중앙: SEARCH −0.119°, HIGH −0.141°, hover −0.125°,
하중 HIGH −0.249°. 그러나 S2 21자세/하중 real_delivery 외부 보정, 정착시간/파지 안전,
하중·자세별 v7 평균/공분산은 별도 재보정 대상이다. 이 조건과 해당 plant의 재생 근거가
없으면 **NOT_EVALUABLE**, full DEV 금지. 기존 off 영상의 카메라 숫자만 바꾸지 않는다.
GT는 재생 종료 뒤 채점만; #405 원본 수정0, 카메라 mount/FOV 변경0, 모델0.
자료/기준 미달시 새 번들·seed를 예약하거나 물리 실행하지 않는다. ENOSPC는 HOST_ERROR.

s2v30 구현 검증 중 HIGH/real_delivery 전용 기존 `visual_pose_supported`를 VO까지
공유한 범위 누락을 발견했다. 첫 후보 재생은 `replay-candidate.json`에 보존한다.
최종 VO는 고정 camera_models의 모든 자세 키와 기존 servo settle 시간으로 지원을
판단한다. AMCL의 벽 관측 자세 범위는 바꾸지 않는다. 이는 파라미터 재튜닝이 아니라
요청한 매 펄스 범위 수정이며 최종 재생은 `replay-candidate-allposes.json`으로 분리한다.

## s2v30 결과 — 회복 차단 수정 통과, VO는 정상 펄스 기준 미달

사전 기준 `a4db20e6`, 회복 수정/VO `fb6294ad`, 모든 보정 자세 지원 수정·최종 재생
`69e83487`. [결과·옵션·출처·전체 산출물 해시](ground-vo-result.json),
[재생](replay_ground_vo.py), [GT 분리 채점](score_ground_vo.py),
[스케일 평가 전용](score_ground_vo_scale.py). 모든 runtime GT 입력0·새 물리0·모델0.

**회복 버그:** 최대6회 제한을 차단 목록 길이에서 별도 횟수로 분리했다.
성공·timeout·지원 역펄스 없음 이후 retry에서 방향 차단 clear→정적 지도 재계획,
이전 slip 행 재소비 금지, 새 연속 slip만 재차단.
저장된 상태별 차단 제안 **1,197→0**, 기존 PULSE_RESOLUTION_LIMIT1,194회 구간의
마지막 상태에서 선택 불가→`left=0.35, 60ms`; 비용 .00189152→.00139407.
회복은 실제로 .15443m 관측 뒤 timeout이었으며 성공으로 바꾸지 않았다.
이는 독립 저장 상태에서 다음 명령 가능성 검사다. 이후 영상·경로·탈출을 만들어낸
닫힌 루프 성공이 아니다. v129 frozen 등록/번들/기록은 그대로이며 새 소스 실행을
그 번들이 거절하는 시험도 통과했다. 새 실행에는 새 등록이 필요하다.

**VO:** `odom_source=ground_vo_v1` 기본 off. 보정표에 있는 정착 자세의 무하중/하중,
전진/옆/회전/미세 펄스에서 LK+바닥 역투영 호모그래피+강건 SE2. 완전한 자기 영상
변위를 PF에 한 번 적용한다. 명령은 누락/가림/동일 RGB의 fallback 예측이고, 측정으로
다시 융합하지 않는다. 스케일 공분산은 측정 이동 방향의 크기에만 더하며 EKF는 없다.
기존 off **5,202프레임 pose/AMCL/visibility/contact 정확 일치**, command/record byte 시험 통과.
표적 카메라/FOV·공용 camera_robot_port·다른 제어기 변경0.

|s1051 고정 명령 재생(강성 off)|기존 v122|slip-only 기존 재생|ground_vo_v1 최종|
|---|---:|---:|---:|
|운반 RMSE m|2.02358|1.78530|1.68237|
|운반 시각 갱신|27|23|21|
|최장 fix 공백 s|33.85|43.50|51.25|
|정상 하중271펄스 RMS mm|4.977|4.977|7.253 **FAIL**|
|무하중161펄스 RMS mm|.946|기존 범위 밖|3.091 **FAIL**|
|문제6펄스 오차≤3.5cm|0/6|5/6|5/6|

137/438펄스에서 완전 VO(하중118·무하중19), 301/438은 명령 fallback.
interval 상태: measured700, texture 부족698, 시간/누락511, rigid consensus 실패225,
분산 부족3. RGB 입력 해시 동일·벽 프레임 삭제0. 관측 불가를 0변위로 만들지 않는다.
cyan 이미지 점유율 중앙 **6.012%**, 최대7.329%; 바닥 외형 선택 면적 중앙64.863%.
이는 이미지 마스크 비율이며 숨겨진 바닥 전체의 정확한 가림률/GT 분할이라고 하지 않는다.
기존 ±2.8° nuisance 가정의 스케일 σ 중앙14.45%, P95 24.96%;
방사 이동 σ 중앙.556mm/P95 2.191mm. 이는 실제 측정 pitch 오차가 아니다.
GT 카메라로 **평가만** 다시 투영한 같은 inlier의 고정/평가 기하 이동 크기 비율 중앙은
무하중.724·하중1.015, 기하 차이 중앙2.040/1.770mm. 1mm 이상 구간의 비율이며
실제 운동의 스케일 오차와 같지 않다(프레임별 카메라 움직임 포함, 큰 꼬리는 JSON 보존).
보정값 재추정·GT 피드백은 하지 않았다.

**판정:** 운반 RMSE 개선만 통과하고 정상 RMS 비악화는 실패했다. 따라서 미채택·기본 off.
강성 on에서의 같은 조건 재생은 **NOT_EVALUABLE**: #405 `7d109118` 정적/짧은 SEARCH
자료를 읽기 전용 복사했으나 S2 21자세·하중 real_delivery·정착/파지·v7 재보정과
그 plant의 s1051 운반 영상이 없다. 강성 off 결과를 on 실패/성공으로 옮기지 않는다.
PR405가 부른 절은 egomap19이며 사용자 명칭19b의 근거를 위 commit에 고정했다.
남은 큰 문제는 정상 펄스에서 VO 측정이 이미 정확한 v122 예측보다 거칠다는 점과
완전 측정 가능 비율31.3%다. 여기서 문턱/공분산 재튜닝하지 않았다.

새 full DEV·seed·번들 등록 없음. lifted/inside·벽 하단 가시율·B 거리·정지 목록·wall/SIM은
새 물리 결과가 없어 N/A, 과거 s1051 성공/실패를 승계하지 않음.
`ugrp_session` 오프라인 세션3개 정상 종료, 물리 잠금 취득0.
출력: `/Users/changmin/projects/ugrp/outputs/s2-ground-vo-20261007/`.
기존 영상은 그대로 보존하며 새 물리 영상은 없다.
TensorBoard `1007-s2-ground-vo-v30` 3뷰·21 scalar 원본/이벤트/live API 대조, HParams 로드 통과.
[수치 대시보드](http://127.0.0.1:6006/?runFilter=%5E1007-s2-ground-vo-v30%2F#timeseries).
기존 사용자 범위대로 수치만 확인했으며 UI 표시/핀 실증은 주장하지 않는다.

참고 원문: [Nav2 pinned recovery BT](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml),
[Seegmiller·Wettergreen 2011, II-C–F·식5–9](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf),
[OpenCV 평면 호모그래피](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html),
[robot_localization Moore·Stouch](https://docs.ros.org/en/kinetic/api/robot_localization/html/_downloads/robot_localization_ias13_revised.pdf).
기존에 확보·확인한 원문을 재사용했고 재개 후 새 웹 검색0회다. 논문의 별도 그림자 엣지
분할 전체를 재현한 것은 아니며 기존 S2 바닥 외형·cyan·자기 기하 마스크를 쓴다.
최종 변경 모듈 시험은 **13 passed (1.02s)**이며 앞선 3파일15시험과 범위가 다르다.

## s2v31 진단·재생 확인 사전 기록 — 시작 관측 (2026-10-07)

s2v30 보고 뒤 작업 트리 clean `26d53052`에서 시작했다. 새로 본 진단 수치는 탐색 결과이며
[이 기준](start-view-criteria.json)의 사전 결과로 포장하지 않는다. 이 커밋 뒤 s1052의 기존
214프레임을 기존 off/`augmented_active_v1`로 다시 재생하고 **s2v29 기준을 그대로** 채점한다.
이미 본 DEV 자료의 회귀 확인이며 새 확증 표본·새 보정 후보가 아니다.

8.25초 자세는 SEARCH가 아니라 LOOK_P20이다. 실제 벽 하단96/96열이 영상 안에 있으므로
사용자 조건인 “원인이 시선이면”은 현재 증거에서 성립하지 않는다. 평가용 pitch만 바꾸면
검출0→92열로 회복되어, 추가 능동 회전/시선 정책이나 문턱 완화를 도입하지 않는다.
기존 Fox1998 기대 엔트로피 감소 + Augmented MCL 옵션은 **기본off 그대로**다.
시작 도크/행 사전정보·GT 기반 제어 보정은 넣지 않는다.

강성 비교는 #405 `7d109118`의 정지 SEARCH 실측 카메라 변환을 같은 s1052 위치에
투영하는 **평가 전용 기하 비교**다. 서로 다른 장면의 RGB를 같은 장면이라고 부르지 않으며,
LOOK_P20 강성on 실제 영상·보정은 아직 없다. 기존off 영상을 on 영상으로 변환하지 않는다.
#405의 S2 재보정 목록(21자세·하중 real_delivery·정착/파지·하중별 v7·RGB 관문)을 유지한다.
재생 통과와 새 plant 보정이 모두 충족될 때만 seed1052 full1회(freezeON, 강성ON, agent_lock).
미달이면 물리0, 새 번들0, lifted/inside·운반 지표·wall/SIM은 새 값 없음으로 기록한다.

### s2v31 결과 — 관측 부재는 시야가 아니라 pitch 보정 불일치

[감사 코드](audit_start_view.py), [결과·원본 해시](start-view-result.json).
8.25초는 **LOOK_P20(1072/2400/1482/pan2030)**, SEARCH는11.60초다.
원본을 직접 확인했고, GT는 아래 원인 분해와 별도 채점에만 썼다.

|원인 검사|8.25초 수치|판정|
|벽 하단이 화면 밖인가|96/96열, undistorted y117.20–145.91px/480px|시야 밖 아님|
|바닥 외형 필터|무하중 시작 구간 적용0|필터가 지운 것 아님|
|빛/대비|실제 하단 대비30.78–100.67, 기준6|하단 대비 충분|
|거리|실제3.12–6.42m, 6m 초과5/96열|모든 열 소실의 설명 아님|
|고정표/실제 pitch|−9.96761°/−11.29597°, 차이1.32836°|벽 띠/상단 검사 기하 불일치|
|평가용 위치·높이만 교체|0→0열|높이 단독 원인 아님|
|평가용 pitch만 교체|0→92열|지배적인 원인|
|평가용 전체 카메라 교체|0→93열|검출 회복; 제어에는 사용하지 않음|

전체 후보 행에서 geometry96열→균일도29열→상단 대비0열이다. 실제 하단 행만
검사하면 geometry30→균일도26→상단 대비0열(나머지는 이미 기하 거절)이다.
전체 실제 하단에서 계산한 띠 표준편차 중앙17.20은 기하에서 거절된 행도 포함한다.
평가용 실제 기하에서는1.90으로 줄지만, 이를 실물 사용 가능한 새 보정으로 채택하지 않았다.
보정 지그의 당시 실제 pitch−9.97915°는 PnP표와0.01154° 차이뿐이다.
따라서 낮은 지그 reprojection RMS가 실제 실행 자세까지 검증한 것은 아니며,
**지그→실행 간 평형/자세 전이**를 별도 확인해야 한다. 관절/차체 기여는 현재 로그만으로 확정하지 않음.

|t(s)|기존 최종 검출열|평가용 실제 기하 검출열|
|2.25|52|42|
|3.75|38|96|
|5.25|36|43|
|6.75|18|95|
|8.25|0|93|
|11.60 SEARCH|62|62|

#405 실측 SEARCH 변환을 동일 s1052 시작 위치에 투영하면 강성off/on 모두 **100%**
가시, 하단 행56.48–98.72→66.13–108.59px다. 이 pitch는 yaw-floor 좌표 기준
−19.05542→−18.24201°이고, #405가 보고한 body-relative 처짐 −.93214→−.11887°와 구분한다.
LOOK_P20 명령FK의 이상적인 강체 기하도96/96열 가시이나 **강성on 실측 영상이 아니다**.
카메라 mount/FOV 변경0. 새로운 시선 동작은 조건이 성립하지 않아 넣지 않았으며,
기존 `global_localization=augmented_active_v1`(기본off)의 pan 정보량 선택은 유지했다.

사전 기록0c7e6c89 뒤 같은214프레임을 재생: off 마지막1.428663m/RMSE1.422841m,
Augmented 마지막3.357254m/RMSE3.288994m·갱신5회. 기존 실패 재현, off pose 차이0.
새 영상/보정 없이 알고리즘 반복으로 관측 문제를 해결했다고 하지 않는다.
강성on 재생은 아직 NOT_EVALUABLE, **기준 미달로 full 없음**. 도크/행 사전정보0·모델0.
출력 `/Users/changmin/projects/ugrp/outputs/s2-start-view-20261007/`.
새 lifted/inside·운반 fix/공백·RMSE·B거리·정지 목록·wall/SIM·영상은 N/A.
오프라인 session2개 stopped, 물리 잠금 미획득/null.

출처는 이미 확인한 [Fox1998 §4.3 식13](https://www.cs.cmu.edu/~dfox/postscripts/ras-active.ps.gz),
[Nav2 pf.c](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf.c),
[dock 원문 해시](dock-augmented-sources.json), #405 `7d109118` 정적 측정/재보정 목록을 재사용했다.
새 웹 검색0·#405 수정0. 이어지는 사용자 요청의 강성on 재보정은 이 미완료 조건을 처리하는 별도 작업이다.

완료 검증: 관련2파일 **16시험/1.60s 통과**, [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-start-view-v31%2F#timeseries) 2뷰11scalar·HParams 원본/event/live API 수치 일치. [전달 기록](start-view-delivery.json). UI 확인·새 영상 없음.

## s2v32 — CI 의존성 분리와 강성on 카메라 재보정 (2026-10-07)

CI run37616106371의 실패8건: MuJoCo 없는 offline shard의 엔진 import6건,
hover 감사 float의 끝자리(최대2.8e−17m) exact 비교1건, workflow plan 표본 v124–129
누락1건이다. 해당 엔진 의존 시험만 `pytest.importorskip`으로 표시하고, MuJoCo가 설치된
기존 Ubuntu runtime job에 파일5개를 명시하여 누락 없이 검증한다. 순수 시험은 계속 offline에서 돈다.
저장된 projection의 정수/가시율/결론은 exact, 계산 float 두 필드만 기존1e−10 허용 범위에 포함했다.
실행기/물리/번들/과거 원본은 바꾸지 않는다. 로컬 전체 suite 대신 실패 관련 파일만 확인한다.

CI 수정 로컬 검증: 관련7파일44시험/73.93s PASS; 엔진 import를 차단한 offline 환경은 관련5파일의 의존성 분기만 별도 확인. 원격 전체 완료는 별도 기록한다.

### 강성on 재보정 사전 등록

[기준](stiff-camera-criteria.json): #405 `7d109118`의 강성 XML 변환을 바이트 그대로
S2 파일로 복사한다(원본 수정0). 모든 무하중 정착 자세22개(LOOK_P20 pan들, SEARCH,
HIGH/VIA/hover/descent/real_delivery)를 기존 공개 명령 port로 움직여6초 정착한다.
구 지그의 차체 qpos/속도 재설정은 사용하지 않는다. 바닥 기준 위치·자세를 아는 평면 표적
두 장 fit/한 장 holdout의 RGB 코너로 OpenCV solvePnP+LM, fixed K/D 그대로.
[OpenCV Demo1](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html)을 확인했다.
측정한 ground normal(pitch/roll)·높이만 적용하며 XY offset/yaw는 기존 고정 기하 유지.
보정 입력은 표적 기하와 RGB뿐이고, 관절·차체·카메라 GT는 별도 평가에만 남긴다.
새 `camera_pitch=stiff_target_v1` 기본off; 잘못된 plant/누락 자세는 거부한다.

무하중표를 하중에 적용하는 경우 **강체 근사**이며 하중 보정 성공으로 표시하지 않는다.
두 번 실패한 하중 지그 재시도0·weld0. 다음 관문은 강성on 시작12초 이하 고정 명령 영상,
8.25초 검출≥6열, 기존 s2v29 위치 기준, 그리고 VO 정상 RMS 비악화·운반 RMSE 개선이다.
기존off s1052 영상을 새 강성on 영상으로 부르지 않는다. #405의 이미 있는 on 자료와
새 on 기록만 새 plant 판정에 쓰며, 자료 부족도 NOT_EVALUABLE로 남긴다.
모든 조건 통과 때만 seed1052 full DEV1회, freezeON·관측 격리·RGB감시·dev_light·agent_lock.
정적 표적 획득180SIM초/시작12SIM초, 한 번에 하나. 미달이면 full 없음.

보정 취득 `bcefa435`: 22/22 PASS, 133.30SIM초/58.16wall초, holdout RMS 최대.2043px. GT 평가 pitch 차이 최대.2256°(보정에 미사용). 새 고정표 `s2_camera_stiff_target_v1.json`을 다음 시작 녹화 전에 봉인한다. 시작 녹화는 seed1052의 기존 정지 명령214프레임을 그대로 재발행하는12초 미만 진단이며, PF·도크 prior·주행·full 임무가 없다.

### s2v32 결과 — 시작 검출 회복, 전역 가설 미해결·VO 인수 미달

[기준](stiff-camera-criteria.json), [결과/원본 해시](stiff-camera-result.json),
[22자세 고정표](../../configs/calibration/s2_camera_stiff_target_v1.json),
[GT 없는 시작 재생](replay_stiff_start.py), [VO 재생](replay_stiff_vo.py),
[평가 전용 채점](score_stiff_checks.py). 실행 소스: 표적 `bcefa435`, 시작 `8386e299`,
최종 VO `9b51c11c`. VO 초기 탐색 출력도 보존하고 같은 코드를 커밋 뒤 별도 final 출력에 재생했다.

**보정:** 강성 real_v1 + freezeON, 새 자유 차체·정상 서보 명령·정지 표적22/22 성공.
새 옵션 `camera_pitch=stiff_target_v1` 기본off. 기존 K/D/mount/FOV 불변,
카메라 ground normal과 높이만 RGB PnP로 측정하고 고정 XY offset/yaw는 유지했다.
두 표적 fit/독립 표적 holdout; holdout RMS 최대 **.204284px**, 실제 카메라와
pitch 차이 최대 **.225573°**(후자 GT 검증 전용, fit 입력0).
LOOK_P20 pan2030은 보정−10.11212°/실제−10.16688°; SEARCH −18.27205/−18.22068°,
real_delivery −27.23625/−27.23236°. 차체 clamp/qpos 재설정·하중 지그 재시도·weld0.
무하중표의 하중 사용은 **강체 근사**, 하중 보정이나 정확도 입증으로 승계하지 않는다.
PF·벽 검출/투영·cyan 투영·ground VO가 같은 instance calibration dict를 사용한다.
공용 camera_robot_port·다른 제어기·#405 수정0. default/explicit off byte 시험 통과.

**시작 검출 효과 분리:** 기존 s1052는 강성off이다. 다음 두 열은 **새 강성on 동일214장**이며
보정 옵션만 다르다. 과거0열→85열은 plant 변경 효과가 포함되고, 85→91열이 같은 영상의 보정 효과다.
시작 도크/행 prior0; 표준 seed1052 Scene 초기화는 평가/설정 경계에만 있고 PF는 전역 균일 초기화다.

|지표|기존 s2v29(off plant)|새 on plant + 기존 보정|새 on plant + 새 보정|
|---|---:|---:|---:|
|8.25초 검출/96열|0|85|**91**|
|정지 갱신|5|6|6|
|최종 위치 오차(m)|3.357254|2.963104|3.181034|
|정지 RMSE(m)|3.288994|3.186049|3.315506|
|full 인수|FAIL|참고|**FAIL**|

새 보정의 6뷰 검출:2.25/3.75/5.25/6.75/8.25/11.60초에38/95/44/90/91/49열.
관측 빈칸은 해소됐지만 최종 전역 가설은 **미해결**이다. 정답25cm·15° 근처 입자는
1→11→57개(복제 포함), 질량 .05%→7.189%; 가장 큰 다른 bin19.320%, 점유bin506,
전체XY σ2.271m. 큰 평균 위치 오차는 미해결 다중 분포의 요약값이며 자신 있게 잘못 확정한 것이 아니다.
GT 위치로 군집을 선택하거나 prior를 넣지 않았다. 남은 가장 큰 원인은 가설을 구분할 측정의 부족이다.
이번 범위에서 추가 시선/벽 특징/우도 상수 변경은 하지 않는다.

**VO 재평가:** 새 보정 + ground_vo_v1을 #405 강성on `stiff-north/south`의 무하중
SEARCH16펄스에 적용했다. 이 자료는10Hz·다른 도장/정지로봇 조건이므로 S2 운반 증거와 합산하지 않는다.
완전 VO **0/16**, 모두 명령 fallback; 정상 RMS **1.635867→1.635867mm**로 수치상 비악화이나
실측 VO 성공이 아니다. 0.75초 예측 종료점이 모든0.1초 프레임격자 사이에 있어 끝 영상이 없다.
또112 interval 중 measured4/texture부족10/rigid consensus실패6/chain 단절후unknown92였다.
따라서 종료점 누락만 고치면 된다고도 단정하지 않는다. 임의 프레임 보간/재튜닝은 없다.
강성on S2 운반 영상은 없으므로 운반 RMSE 개선은 **NOT_EVALUABLE**.
기존 s2v30의 off-plant 정상RMS 실패는 그대로 보존하고 새 보정으로 통과 처리하지 않았다.

**판정/자원:** 시작 검출 관문만 통과, 시작 위치 관문 FAIL·VO 운반 관문 미평가 → **full DEV 없음**.
새 full seed/번들0, lifted/inside·운반 fix/공백·가시율·B거리·정지목록·wall/SIM은 N/A.
정적 보정133.30SIM/58.16wall초, 정지 시작11.95SIM/9.72wall초; 성능 코호트 비교가 아니다.
두 획득 모두 agent_lock+ugrp_session, 순차1개씩 종료·release/null 확인. 모델0·낙하 실험0.
raw `/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007/`, 원본 PNG/JPG/실패·명령 보존.
로컬/원격 백업을 혼동하지 않으며 새 full 영상은 없다.

CI 수정 `e17a27a5`: 로컬 실패 관련44시험 통과, 엔진 없는 조건15통과/6제외,
해당6건은 Ubuntu runtime job에 재배치했다. 최종 변경 범위27시험/4.16s 통과.
실행 코드 `8386e299`의 [원격 CI 기록](stiff-camera-ci.json): offline shard8/8·집계·Ubuntu runtime SUCCESS. 별도 multi-object-scenes는 CANCELLED여서 전체 CI green으로 표시하지 않는다. 후속 기록/재생 스크립트 커밋의 CI 상태는 별도다.
PR406 DRAFT/병합 금지 유지. 최신 실행 지침·실패 기록을 갱신했고 기본 동작은 변경하지 않았다.

전달: [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-stiff-cal-v32%2F#timeseries) 4뷰18scalar·HParams를 원본/event/live API 대조했다. [전달 검증](stiff-camera-delivery.json). 수치만 확인, UI 표시 실증은 주장하지 않음. 기존 viewer 유지.

### s2v32 원인 한정 감사 — 저장 결과만, 새 물리 실행 0

[평가 스크립트](diagnose_stiff_causes.py), [결과·입력 해시](stiff-causes-result.json).
원본 `s2-stiff-cal-20261007/replay-start-on.json`과 `replay-stiff-vo-final.json`을 읽었다.
새 영상/필터 갱신/물리/모델 호출0. GT는 저장 입자·고정 가설의 사후 우도 질의에만 쓰고,
입자 선택·초기화·보정·제어에 넣지 않았다. 아래 분석은 탐색 진단이며 새 확증이 아니다.

**1. 검출91열·갱신6회인데 평균 오차3.181m인 이유**

정답25cm·15° 안의 입자는 초기1개(.05%)에서 최종57개(7.189%)로 증가했다.
그러나 모두 **동일한 한 자세의 복제**: 정답에서19.14cm·약6° 떨어져 있고,
초기10cm·5° 안은 **0/2000개**다. 재표본화2회·무작위 주입0회이며,
`w_fast > w_slow`로 관측 점수가 좋아져 Augmented MCL의 복구 주입이 발동하지 않았다.
정답 가설 소멸이 아니라 전역 표본의 해상도 부족과 경쟁 가설 잔존이다.

|최종 가설 bin(0.5m·10°)|가중치|위치 오차(m, 평가)|저장6뷰 우도 곱/정확한 GT 우도 곱|
|---|---:|---:|---:|
|[2,−4,9] (yaw≈90.6°)|19.320%|2.293|0.1300|
|[10,1,−18] (yaw≈−171.2°)|12.706%|6.755|0.0673|
|[−2,−5,−1] (정답 주변)|7.189%|0.191|0.0938|
|[0,0,−10]|7.147%|2.607|0.0655|
|[3,−5,−1]|6.524%|2.842|0.0578|

bin은 연결 군집이 아닌 서로 겹치지 않는 요약이며 우도는 각 bin의 가중 평균 자세에서 계산했다.
우도 곱 비교는 고정 가설 진단값이며, 재표본화와 사전 질량이 반영된 posterior odds가 아니다.
정확한 GT의 우도 곱은 초기2000개 중 최고보다 **7.69배** 높고,
정답 주변 유일 표본은 초기 표본들의 6뷰 우도 순위 **2위**였다.
GT에서 검출 벽 하단 잔차의 뷰별 중앙값은 **0.42–1.19px**다.
따라서 검출/투영이 통째로 잘못돼 정답을 거절한 결과는 아니다.

**완전한 경기장 대칭이라고도 할 수 없다.** 경쟁 가설은 다른 행뿐 아니라 약90°/180° 회전도 포함한다.
정적 외벽의 y중심은−.85m, 분리벽 문 개구의 y중심은+.05m여서 같은 남북 대칭이 아니다.
GT에서 지도상 보이는 모든 열의 벽 하단을 정확히 질의한 평가 반사실에서는 최고 오답/GT 우도비가
.1300→.00920(즉 GT 우세108.65배)로 더 작아진다. 이 이상적 접점은 PF에 입력하지 않았다.
실제 부분 관측과 endpoint-only의 완만한 `1+Σp³` 우도가 국소 벽 모양의 별칭을 충분히
구분하지 못하는 기여는 남지만, **정답을 표현하는 정밀 표본이 없는 다봉 미수렴**이 직접 원인이다.
전체 평균3.181m를 확정한 단일 행의 위치 오차로 해석하면 안 된다(`resolved=false`, XY σ2.271m).

제안만: 다중 가설을 유지하고 평균 위치를 확정하지 않은 상태에서,
[Fox·Burgard·Thrun1998 §4.3 식13](https://www.cs.cmu.edu/~dfox/postscripts/ras-active.ps.gz)의
기대 엔트로피 감소로 가설을 구분할 시선/짧은 이동을 선택한다. 문 위치·분리벽 끝처럼
후보마다 예상이 다른 관측을 확보하고, 이동 예측에서 국소 입자 해상도를 회복해야 한다.
현재 단일 중앙열 pan 점수만으로 구별이 충분하다고 보장할 수 없다.
이미 저장·해시 확인한 [원문/AMCL 출처](dock-augmented-sources.json)를 재사용했으며 새 웹 검색0.
도크 prior, GT 가설 선택, gate/우도 튜닝, 능동 행동 구현은 이번에 하지 않았다.

**2. ground_vo_v1 완전 측정 0/16의 단계별 탈락**

|검사 단계|입력→통과/탈락|판정|
|---|---|---|
|기존 재생의 시작 영상·고정 보정/프로필|16→16|직접 `observed_pulse` 호출; GroundBuffer 상위 admission은 미실행|
|종료 전 interval의 RGB 존재|112→112|실제 영상 누락0|
|마지막 **성공** 영상부터 간격≤.15초|112→20, 탈락92|첫 추적 실패 뒤 다음 간격.20초로 chain 단절; 이후 `unknown_frame`|
|바닥/광류/거리/자기 가림 처리 뒤 ≥6 track·≥2 cell|20→10, 탈락10|`unknown_texture`: 남은 track1–5개; 1건은 cell도1개|
|rigid RANSAC ≥6 inlier·비율≥.6·오차<5mm|10→4, 탈락6|`unknown_rigid_consensus`: 입력 track6–12개·cell3–6개|
|추가 공간 지지·정보행렬 및 interval 측정|4→4|성공4 interval은 서로 다른4펄스의 첫 구간뿐|
|전체 chain + 종료 시각 일치|16→0|모든 펄스에서 추적 단절, 별도로 정확한 종료 영상도16개 모두 없음|

10펄스의 첫 실패는 track 부족, 6펄스는 rigid 합의 실패다. 따라서92건은 누락 영상도
독립적인92회 광류 실패도 아닌 **앞선16회 실패의 후속 차단**이다.
시도한 영상의 사용 가능 바닥 비율31.25–75.57%, cyan 최대0.00098%로,
이 무하중 SEARCH 자료에서는 블록 가림이 주원인이 아니다. `texture` 이름만으로
원본에 무늬가 없다고 단정하지 않는다(카운트는 LK·바닥·거리·가림 검사 후 track 수).
0.75초 프로필 종료가10Hz 영상격자 사이에 있어 양쪽 영상은±.05초, 정확한 끝 영상은 없다.
현재 계약은 끝 뒤 영상을 사용하지 않고 `abs(last_t−end)<1e−7`을 요구한다.
이는 이10Hz 자료와 완전 측정 계약의 불일치이며, 끝 정렬만 처리해도 추적 실패16회는 남는다.
임의 보간·부분구간을 완전 측정으로 승격하거나 단절을0이동으로 처리하지 않았다.

제어의 확정 버그는 확인하지 못했으므로 옵션/기본 동작 수정0, 결과는 계속 미통과다.
관련2파일 **14시험/0.99s 통과**. raw는 `outputs/s2-v32-causes-20261007/`,
첫 진단 result와 최종 추가 집계 final-result를 각각 보존했다. PR406 DRAFT·병합 금지 유지.

전달: [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-v32-causes%2F#timeseries)
2뷰12scalar의 원본/event/live API 수치 일치, [검증 기록](stiff-causes-delivery.json).
기존 viewer 유지·UI 표시 미검증. 물리 잠금 미획득, status=null 확인.

## s2v33 — KLD 전역 입자 예산, 오프라인 1후보 사전 등록

[사전 기준·출처 해시](kld-start-criteria.json). `particle_sampling=kld_global_v1`, 기본off.
[Fox2001 식7/Table1](https://papers.neurips.cc/paper/1998-kld-sampling-adaptive-particle-filters.pdf)과
[Nav2 pf.c](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf.c)의
`pf_init_model`(최대 입자로 균일 전역 초기화), `pf_resample_limit`, 다항 재표본화를 사용한다.
기존 입자 복제만으로 없는 자세를 만들 수 없으므로 **첫 관측 전에** 최대 예산을 확보한다.
bin=.5m/.5m/10°, 최대100000은 논문 설정; 최소2000은 기존 예산,
epsilon=.05·confidence=.99(z=Φ⁻¹(.99))를 결과 전에 선택했다. cap에 닿으면 이론적 오차 보장을 주장하지 않는다.
Nav2의 k≤1 처리·표본수>limit 종료를 따른다. 현재의 ESS≤N/2 선택적 재표본화,
Augmented 복구 EMA·관측 우도·6뷰·카메라 표는 유지한다. 이는 Fox의 예측 전 샘플링이 아닌
공개 Nav2의 관측 후 KLD 재표본화 경로다. KDE/sensor resetting은 함께 넣지 않는다.
기존 운동 잠재변수는 기존 prior에서 독립 재표본화하고, 첫 차체 이동 때 가중2000개로
인계하여 이후 추적은 고정 예산을 쓴다. 이번은 정지 재생만이므로 인계는 단위시험 범위다.

새 강성on s1052의 동일214 RGB·동일 명령에 off/on 각1회. 재생 소스를 먼저 커밋한다.
off pose/입자 바이트 동일, 최종 평균 위치 오차≤.25m 및 off보다 개선,
정답25cm·15° 질량 증가·소멸 없음·거짓 resolved 없음이 통과 기준이다.
10cm·5° 질량/개수, 입자수, unresolved 여부, 초기화+프레임 처리 wall/CPU도 함께 보고한다.
기존 행/도크 prior와 GT 가설 선택은 금지; GT는 두 예측 파일 종료 뒤 평가에만 읽는다.
계산 시간 비교는 agent_lock 하에 직렬 실행, 조건당300초 제한, 출력 직렬화·평가 시간 제외.
명령 고정 재생이므로 행동 선택용 shadow pan 순위 계산은 양쪽 모두 제외한다.
결과 후 문턱·예산 변경/추가 후보0. 기존 자료의 탐색 비교이며 새 확증·물리 성공이 아니다.
**새 물리0, 통과해도 full DEV는 제안만**, 새 번들/seed 예약 없음. PR406 DRAFT 유지.

### s2v33 결과 — 표본 공백 해소, 전역 위치 기준 미달

기준·실행 소스 `75ccac4f`, [결과](kld-start-result.json), [재생](replay_kld_start.py).
동일 보정 s1052 정지214프레임, off/on 각1회, 새 물리/모델 호출0.
GT는 두 예측 파일 저장을 마친 뒤 채점에서만 읽었다. 관련2파일14시험/1.54s 통과 뒤
커밋·push한 소스로 실행했으며, 결과 후 코드/문턱/예산 변경0이다.

|지표|off(기존2000)|on(KLD)|
|---|---:|---:|
|초기 정답10cm·5° 내 입자|0|4|
|최종 정답25cm·15° 질량|7.1890%|11.7527%|
|최종 정답10cm·5° 질량|0%|7.0820%|
|최종 평균 위치 오차(m)|3.181034|3.090308|
|전체 정지 RMSE(m)|3.315506|3.330363|
|최종 XY σ(m)|2.271122|2.356887|
|관측 갱신/재표본화|6/2|6/3|
|입자수 변화|2000 유지|100000→45977→38221→21025|
|계산 wall / CPU(초)|2.7910 / 3.3814|43.6867 / 44.0425|
|전역 resolved|false|false|

off의 pose JSON 및 입자/가중치 배열은 기존 보정on 재생과 바이트 동일이다.
새 스냅샷 `t`는 처리 프레임 시각(예:2.45초), 관측 시각은 AMCL 행(2.25초)으로 남긴다.
초기 정답25cm·15° 내 표본44개, 마지막2471개(복제 포함); 정답 주변은 소멸하지 않았다.
KLD의 정답 주변 가장 큰 bin 질량11.239%이지만 다른 가설이 여전히 많다.
정답 가까운 표본의 부재는 해소됐어도 동일6뷰의 전체 posterior는 수렴하지 않았으며,
GT로 가장 좋은 bin을 골라 오차를 대신 보고하지 않았다. RMSE도 소폭 악화됐다.

**판정 FAIL:** 질량 증가·off 동일·정답 가설 생존·거짓 확정 없음은 통과,
최종 평균 오차≤.25m는 실패(3.090m). 표본 수 확대만으로 충분하다는 가설은 지지되지 않는다.
추가 튜닝·재실행0, **full DEV 제안/실행 보류**. 입력 자료는 탐색 자료 그대로이며 새 확증 아님.
계산 시간은 초기화와 영상 읽기/처리 포함, 파일 직렬화·GT 채점 제외, 단일 off→on 순서다.
호스트 잠금 아래 순차 측정했으나 반복 통계/일반 속도 성능으로 해석하지 않는다.
`ugrp_session s2-kld-v33` 정상 종료, 계산 시간용 `agent_lock` release/status=null 확인.
raw `/Users/changmin/projects/ugrp/outputs/s2-kld-start-20261007/replay/`:
off/on 예측 JSON·입자 npz·결과·잠금 기록을 원본과 별도로 보존했다.

전달: [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1007-s2-kld-v33%2F#timeseries)
2뷰18scalar의 원본/event/live API 수치 일치, [전달 검증](kld-start-delivery.json).
기존 viewer 유지·UI 표시 미검증. 새 영상 없음. PR406 DRAFT·병합 금지 유지.

## s2v34 — 능동 시작 위치추정, 물리 1회 사전 등록 (2026-10-08)

[고정 기준](active-markov-criteria.json), `start_localization=active_markov_v1` 기본off.
기본off의 명령/기록 바이트는 이전 KLD Runtime과 같아야 한다.
[Fox·Burgard·Thrun1998 §4.1 식4–8](https://www.cs.cmu.edu/~dfox/postscripts/ras-active.ps.gz)의
`H(현재 믿음) − E[행동·관측 후 믿음의 H]` 최대 행동을 선택한다(요청한 단순화: 비용 가중0).
미래 관측은 정적 벽 지도·고정 카메라·자기 명령 운동 모델로 예측하며 GT를 입력하지 않는다.
공개 원문/해시는 앞선 기록을 재사용했다. 원 논문 전체 레이저 모델의 동일 구현이라는 주장은 하지 않는다.
수치 근사: KLD 믿음의 결정적 systematic 대표512개, 고정 펄스 공분산의6점 cubature,
기존 .5m/10° 상태 bin 및 중앙 카메라1열·8px 범주+unknown·hit/random 측정 모형.
관측 불확실성과 이동 후 분포의 퍼짐을 조건부 엔트로피 계산에 포함한다.

후보8개: 제자리 ±45/90/180°와 좌우 fine10펄스(약7cm).
회전은 이미 측정된±.35/.10초 펄스를 반올림 횟수만큼 반복하므로 목표각과 차이가 난다.
각 펄스는 .20초 응답 꼬리까지 기다린다. 새 모션 보정·상수 튜닝 없음.
팔은 보정된 LOOK_P20 중앙으로 설정 후2초 정착한다. 행동 종료 뒤 .4초 정착하고,
새 자기 RGB로 재관측한다. 이동 중 RGB는 위치 예측만 하고, 행동 끝의 새 정착 관측1회에
기존 seen-view 표식을 지운다(짧은 옆이동이 기존25cm motion gate 아래여도 재관측 가능).
능동 시작 동안에는 최초 차체 이동으로 KLD를 종료하지 않는다. 이후 운반 이관은 이번 범위 밖이다.

**seed1052 시작 구간1회**, v3·v7·freezeON·강성real_v1·stiff_target_v1·KLD ON,
기존 표준 Scene/reset 재사용, 운반·집기·모델 호출0, 자기 도크/행 prior0.
종료는 새 관측 후 전체 위치σ≤10cm AND 방향σ≤5° 또는 초기 명령부터 **30 SIM초**(팔 정착 포함).
최종 전체 평균 위치 오차≤25cm면 다음 full DEV **제안만**; 결과 후 문턱 변경·추가 물리 재시도0.
GT 위치/접촉은 별도 평가·기존 실제 물리 실패 중단에만 사용한다. 예측 충돌/관측 unknown은 dev_light 기록만.
실제 획득은 `s2-active-markov-start-v1` 표준 workflow와 `ugrp_session`으로 실행한다.
숫자형 full 번들을 새로 만들지 않으며, 기존 불변 setup_bundle은 장면 구성용으로만 보존한다.
별도 `run-configuration.json`에 새 옵션·소스·기준·보정표 해시를 봉인하고 기존 full 성공을 승계하지 않는다.
agent_lock이 비어야 acquire한다. 자기 지도 등 다른 물리 작업과 겹치지 않고, 종료 뒤 release한다.
결과는 종료 오차·SIM/wall·선택/완료 행동 수·펄스 수·σ·정지 사유를 모두 기록한다.
raw는 기본 체크아웃 outputs의 새 SHA/seed 경로. ENOSPC/실행 오류는 HOST_ERROR로 남기며 자동 재시도하지 않는다.

### s2v34 현재 상태 — 원격 보존 오류, 물리 미실행

로컬 코드/사전 등록 `715a43da`, 관련3파일 **33시험/6.60s PASS**,
실제 Runtime 생성·100000입자·초기 팔/중앙 pan 명령의 무물리 점검 PASS.
시행 전 시험에서 고정표 상수 이름 오기와 중앙 pan 명시 누락을 수정했으며,
아직 물리 결과가 없고 사전 문턱은 바꾸지 않았다.

HTTPS push가4회 `remote: Internal Server Error`로 실패했다(원격 이전 주소와 확인된 현재 주소 모두).
SSH는 host key verification 실패로 사용하지 않았으며 신뢰 설정/remote 설정을 바꾸지 않았다.
PR406 읽기는 OPEN/DRAFT·원격954b4ebe로 확인했으나 코멘트 쓰기도 실패했다.
[오류·검증 기록](active-markov-publish-block.json), 로컬 PR 사전 기록 문안은
`outputs/s2-active-markov-v34-prereg.md`에 보존했다.

**NOT_RUN_REMOTE_PUBLISH_ERROR: 새 물리0**, 잠금 미획득/status=null.
AGENTS.md의 DEV 실행 소스는 “커밋·push한 브랜치 SHA”라는 규칙에 따라 실행을 보류했다.
종료 위치 오차·SIM 시간·행동 수는 N/A이며 성공/실패 물리 판정이나 TensorBoard 완료 이벤트를 만들지 않는다.
남은 작업은 원격 보존 완료 후 잠금이 비었을 때 고정된 기준으로 seed1052 시작 구간1회 실행이다.
25cm 통과 때만 full DEV 제안. 추가 물리 허가를 소모한 것으로 세지 않으며 자동 연구/운반은 하지 않는다.

### s2v35 재개 — 사용자 원격 장애 예외 (2026-10-08)

사용자/감독 지시로 push 대기 로컬 커밋에서 DEV 실행을 허용한다. 사전 기준은 그대로다.
ba21e386 실행은 결과 dict의 schema/full_dev 중복 키로 backend 생성 **이전** HOST_ERROR.
raw `outputs/s2-active-markov-ba21e386-s1052-start-managed/console.log` 보존, 물리0·잠금 해제.
JSON 구성 병합 버그만 수정하고 동일 사전 등록의 시작 물리1회를 진행한다.

### s2v35 시작 물리 완료 — 25cm 기준 FAIL

소스73d53def, seed1052 시작만1회. 종료 오차 **3.3750m**,
30.00 SIM초/207.35 wall초, 선택10·완료10행동,
87바퀴 펄스, 갱신8회. 종료 `TIME_CAP`.
[결과](active-markov-result.json), raw `/Users/changmin/projects/ugrp/outputs/s2-active-markov-73d53def-s1052-start`.
GT는 종료 평가만, 시작 도크 prior0·운반0·모델0. 잠금 해제, 세션 종료.
사용자 감독 예외에 따라 로컬 SHA 실행·push 대기. 25cm 미달로 이 위치찾기 옵션의 full DEV는 제안하지 않는다.
다음 s2v36은 별도 사용자 허가된 하중/벽 접촉 ablation이며 이 결과를 운반 성공에 합산하지 않는다.

## s2v36 사전 등록 — 하중·팔 자세·벽 접촉 분리, 단독 운반 시선 올리기

사용자 지적: 상자는30g이며 하중 오차로 묶인6회가 실제 하중 효과인지 다시 분리한다.
기존 95.84%·10.37배는 벽 접촉과 하중이 섞인 상관이며 질량 효과로 해석하지 않는다.
[고정 설계/기준](load-wall-criteria.json): SEARCH 무상자, HIGH/real_delivery/look_ahead 유·무상자 × far/near =14조건.
문제6회와 같은 .65 옆 명령/.65초, 간격도 그대로. setup 진단 seed1051이며 학생 임무 실행 아님.
강성real_v1·freezeON·v7 mesh롤러·v3 mount/FOV 유지. 원래 자료/번들 불변.
단1회 초기 HIGH 집게 사이 수동 배치 뒤 정상 접촉만; 지그 clamp/weld/실시간 GT 보정 없음.
실제 파지 이탈/낙하는 그 조건 종료, 같은 물리 원인2회면 전체 중단. HOST 실패는 별도 기록.

`carry_pose=look_ahead_v1` 기본off 후보: HIGH에서 손목3만896→1050. 집게1500 유지,
실물 servo_steps의 순서·기간을 재사용하며 내려놓기 전 HIGH로 복귀한다. 실물 정확 PWM 측정값이라는 주장은 하지 않는다.
근거는 사용자의 “단독 운반 때 고개를 들어 벽·바닥이 보인다”는 관찰이다.
보정은 [OpenCV solvePnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html)의 알려진 표적+RGB 코너와 고정K/D;
강성ON free chassis에서 unloaded/loaded 새 자세를 각각 측정하고 holdout≤1px. GT는 검증에만.
[MuJoCo mj_contactForce](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-contactforce)로
손가락/상자/차체/롤러–벽 및 바닥 접촉 wrench·질량중심·기울기를 write-only 평가한다.
[제조사 MasterPi](https://www.hiwonder.com/products/masterpi) 본체1.1kg, 기존65mm 휠 도면 근거를 보존한다.
부품별 질량 분포는 미측정이라 임의로 재분배하지 않는다.

free 동일자세 하중 차이≤10%, yaw차≤1°; near/free 진행≤20%면 막힘.
새 자세 파지≥99%, pitch하중차≤.5°, 벽하단 가시율+10%p를 고정 비교한다.
이 짧은 고정명령 진단의 가시 기회와 실제 전체 경로 PF fix 공백은 구분한다.
안전·보정 통과 시에만 별도 등록 후 seed1051 full DEV를 고려한다. 결과 후 문턱 변경 없음.
사용자 감독 예외로 push 대기 로컬 커밋 실행 허용. PR406 DRAFT·병합 금지.

실행34ceb0d5: 첫 SEARCH setup의 평가 기록에서 `base_rpy()` tuple에 tolist 호출 오류.
HOST_ERROR, 이동 펄스0·유효 조건0; 원본 `outputs/s2-load-wall-34ceb0d5` 보존.
표준 Robot API의 tuple 그대로 list 변환하고 테스트로 고정, 설계/문턱은 변경하지 않는다.

중간 b161a388: far SEARCH/HIGH empty/HIGH loaded/look_ahead empty의 4조건 완료.
다음 look_ahead loaded는 팔 raw action에 허용하지 않는 duration_s를 넣어 HOST_ERROR(이동 펄스0).
표준 port의 `arm/look` 필드만 발행하도록 수정; 기간은 기존 제어기처럼 명령 간 대기로 유지.
완료4조건은 재실행하지 않고 `--resume-from`으로 원본·SHA를 연결, 미완료10조건만 실행한다.
추가 평가 버그: ray가 RGB에서 숨기는 group5 카메라 렌즈를 장애물로 셌다.
새 ray는 RGB와 동일한 group4/5 제외. 이전4조건 clear 수치는 무효로 표시하고,
보존 RGB·실제 카메라 투영을 오프라인으로 평가한다. 이동/접촉 결과는 영향을 받지 않는다.

### s2v36 ablation 완료 및 full DEV 사전 등록

[14조건 결과](load-wall-result.json): far 옆 펄스 평균 SEARCH170.112mm, HIGH empty/loaded169.827/169.119mm,
look_ahead169.787/168.984mm, real_delivery169.984/169.055mm. 하중 차이는0.42–0.55%, yaw차0.10–0.38°.
near는 모든 자세/하중에서0.300–0.744mm; **무상자도 막힌다**.
벽 접촉은7조건 모두 wheel만(평균 법선력2.53–2.99N), finger/cargo/body–wall0.
단독 상자0.03kg/로봇1.1kg. 이것은 벽으로 계속 미는 제어 문제이며, 하중 보정값을 새로 맞추지 않는다.
팔 질량 분포/롤러 결함을 이 실험에서 확인하지 못했으므로 sim 질량/기하/마찰 수정0.

파지6조건 모두 양쪽 접촉100%·낙하0·weld0. 새 자세 보정은 empty/loaded −16.433/−16.514°,
차0.081°, holdout0.243/0.215px. [새 고정표](../../configs/calibration/s2_camera_look_ahead_v1.json).
near loaded 벽하단 실제 가시율 real_delivery21.46%→look_ahead78.54%, far0%→100%.
이전4조건의 ray clear는 숨겨진 camera group5 포함 오류로 무효이며 in_view만 유효;
loaded real_delivery/look_ahead 비교는 수정된 동일 ray/RGB 그룹의 새 기록이다.
이는 짧은7.15초 진단이며 운반 fix 공백133초와 직접 같은 지표가 아니다.

표준 catalog `zone-s2-realism-v130`/7.23.0 예약: main+열린 PR 전체 원격의 contract 최댓값129/7.22.0 확인.
[실행 사전 등록](registration-v130.json): **seed1051 P1-2→B full DEV1회**, 결과 뒤 문턱 변경/재실행0.
강성ON+기존22자세stiff_target_v1+새 loaded/unloaded look_ahead PnP표, carry_pose=look_ahead_v1.
채택한 s1051 옵션들(nav2_observed, floor_appearance, pulse, isolation, RGB stall, blind grasp, freeze),
slip_detect_v1·회복 후 차단 해제 수정ON. KLD/active-start/ground_vo/하중 재학습OFF.
초기 도크 정보0. 기존모델은 그대로 두며 GT는 평가에만, 모든 확인류 dev_light 기록만.
고정 보정표는 PF 벽열 모델·관측 자기 가림·광류·블록 투영이 공유하는 instance calibration에 적용한다.
목적은 B 진입 실측이며 이 새 조건의 결과를 앞선 s1051 성공률과 합산하지 않는다.

### v130 seed1051 결과 — 운반 전 비물리 종료, 재실행0

소스f10a5f9d, `outputs/s2-realism-f10a5f9d-s1051-P1-2-lookahead`,
[결과](look-ahead-full-result.json): lifted=false/inside=false, B까지4.211m.
49.65 SIM초/81.397 wall초, wall/SIM1.639. arm guard7·POSE_UNCERTAIN33회는 기록만.
그러나 `REAL_PREGRASP_UNCONFIRMED`가 **잘못된 필수 종료 분기**로 남아46.65초에 멈췄다.
RGB cyan19370px/6프레임, 단일 검출 중심 전진 오차3.04156mm·옆0.77605mm;
고정 확인 문턱3mm를0.04156mm 넘었다. 실제 낙하·집게 이탈 실패가 아니다.
운반 상태 미진입이므로 운반 fix수/공백/RMSE/실제 경로 벽가시율은 **N/A**.
이번 시작/팔 강성 조건도 달라 이전full wall/SIM1.32와 속도 향상/악화로 단정하지 않는다.

필수 분기를 고치는 새 `pregrasp_policy=log_only_v1`(기본off)을 추가했다.
기존 마지막 접근 RGB anchor/명령 이력을 유지, 확인 실패는 would-stop으로 기록하고 blind 파지 진행.
accepted=false·visual_confirmed=false·visual_confirmed_at_s=null을 보존하며 성공 증거를 만들어내지 않는다.
타임스탬프는 명령 창의 시작일 뿐 새 시각 확인이 아니다. 기존 기본/off 출력 바이트 동일 및
확인0회에서 파지 도달·허위 성공 없음 **관련2파일9시험 PASS/19.75초**.
등록한 full1회는 실패로 보존, 이 사후 수정으로 추가 물리는 돌리지 않았다. v130 옵션/원본도 소급 수정하지 않는다.
남은 작업은 새 번들에서 이 DEV 옵션을 명시한 전체 운반 검증이다. 잠금 해제·세션 종료·모델0.

전달: TensorBoard `1008-s2-v36-verified`에16뷰·89수치를 source/event/live API와 대조했다(UI 미검증, 사용자 수치 확인 범위).
첫 변환의 공통 분석SHA 라벨은 실행별SHA로 바로잡은 새 snapshot을 만들고 이전 snapshot은 보존했다.
영상 `outputs/s2-realism-f10a5f9d-s1051-P1-2-lookahead-4x.mp4` (908프레임,80fps,11.35초),
native TensorBoard `1008-s2-v36-video`에 등록. [검증](look-ahead-delivery.json).
raw는 로컬 보존이며 GitHub raw백업이라고 주장하지 않는다.

### 원격 보존 마무리 (2026-10-08)

종료 시 정상 push 성공: 원격954b4ebe→bd046020, 이전 대기 커밋 전체 포함.
PR406 본문에 v130/7.23.0 예약·14조건·full 실패·사후 DEV 옵션 수정·출처를 갱신, OPEN/DRAFT 확인.
잠금status=null, 자신이 시작한 시작/ablation/full 세션 모두 종료.
최종 물리 source f10a5f9d와 사후 수정 bd046020을 구분하며, 후자의 새로운 파지 경로 물리 검증은 남아 있다.

## s2v36 후속 사전 등록 — v131 재실행과 공통 관측 우도 진단

사용자 2026-10-08 지시: 기준1267949b의 seed1051 full DEV를 **새로1회** 허용.
[v131 등록](registration-v131.json), workflow7.24.0: 기존v130 옵션/보정/900초 한도 동일,
`pregrasp_policy=log_only_v1`만 명시적으로 추가. 기본off 유지. slip_detect·회복 후 방향 차단 해제ON.
look_ahead·stiff_target·freezeON, 확인 불확실은 기록만. 이전v130 실패는 그대로 보존·합산하지 않는다.
별도 write-only20Hz 평가 로그에 벽 접촉을 저장: 접촉 표본수·접촉 geom pair수와
연속 표본을 한 번으로 센 접촉 episode수를 구별한다. 제어기에는 전달하지 않는다.
agent_lock status=null일 때만 내부 acquire 후 ugrp_session 실행, 종료 release. ENOSPC는 HOST_ERROR.

B는 물리0/모델0의 평가 전용 진단이다. 기존 stiff s1052의 여섯 관측(2.25,3.75,5.25,6.75,8.25,11.6초)을 고정.
정적 지도 bounds의10cm XY격자 ×5도 yaw격자 및 정확한 GT yaw 절편을 평가한다.
벽으로부터 기존 로봇 clearance 이상인 자유공간만 비교하며 정확한 GT 자세는 별도 질의한다.
동일 Nav2 `1+sum(pz^3)`/기존σ0.2m 그대로, 관측별 값과 여섯 log합을 보존.
GT 인접25cm·15도 밖의 최대 봉우리, 정답 점수 대비 배수·위치/방향을 기록한다.
4px 이내 실제 벽하단, ±4px 양쪽 지면이며 실제하단과10px 초과면 바닥 후보(기존 감사 정의),
나머지 unknown으로 평가만 분류한다. 실제 카메라 투영·이상적인 벽하단·8열 간격 thinning은
원인 분리용 반사실 평가이며 제어기 입력/보정/추가 실행 채택이 아니다. 결과 후 기준 변경 없음.
[Thrun/Burgard/Fox 원문 ch6 §6.1,6.3,6.4,6.7](https://roboticsjtu.github.io/CS7355/Probabilistic-Robotics-en.pdf),
[저자 공식 페이지](https://robots.stanford.edu/probabilistic-robotics/),
[고정 Nav2 원문](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp)을 대조한다.
검사 항목: map↔scene 벽/문 연결, 평면 endpoint 전제, nearest-wall가 가림·높이를 무시하는 한계,
열/시점 상관, 곱 우도 대신 Nav2 cubic 가산을 쓰는 실제 구현. 원인이 확실해도 이번 A 조건은 변경하지 않는다.

### 공통 관측 우도 격자 결과 (오프라인, 물리0)

[결과](start-likelihood-result.json), raw `outputs/s2-start-likelihood-208f10f1-final`,
`likelihood-grid.png`/`grid.npz`/`observations.jpg` 저장·영상6장 확인.
21만9960격자 중 기존 clearance prior의 자유공간19만8072개. 원래 관측407접점 중
실제 벽하단402(98.77%), 바닥후보0, unknown5. 벽/문6기하의 map↔저장scene XML 차이0m,
벽높이0.4m·문폭0.5m 동일. 보정 pitch 차이−0.0293~+0.0571°, 실제 카메라 재투영 차이
시점별 중앙0.20~5.34cm; 첫 시점 기준 전체 정지 변위≤1.91mm(평가만).

| 평가 조건 | 격자 최대점 위치 오차 | GT 밖 최고점/GT 우도 | GT 근처 질량 | 전체 평균 위치 오차 |
|---|---:|---:|---:|---:|
| 저장된407접점 | 0.0516m | 0.6895 | 9.04% | 3.242m |
| 평가용 실제 카메라 | 0.0516m | 0.7393 | 9.47% | 3.254m |
| 평가용 진짜벽402점만 | 0.0516m | 0.6926 | 9.07% | 3.243m |
| 8열 간격54점 | 0.0516m | 0.8163 | 0.28% | 3.352m |
| 평가용 이상적 벽하단576점 | 0.0484m | 0.8185 | 17.31% | 3.104m |

GT 근처는 사전 정의25cm·15도. 표 질량/평균은 균일 격자 prior에 여섯 점수를 곱한 진단이며,
과거 입자 재샘플링 결과와 동일한 posterior라는 뜻이 아니다. 원자료 최대점은GT의1.092배지만
5.16cm 안이며, 먼 오답 봉우리가GT보다 높다는 가설은 이 격자에서 **기각**.
전체 평균은[2.048,−0.897]m, 실제[-0.898,−2.250]m. `belief_report`는 다봉을 보존하면서
전체 가중 평균을 pose로 보고한다. 따라서3m 평균 오차를 “하나의 오답 행에 확정 수렴”으로
해석하면 안 된다. 실제 카메라/진짜 벽만/이상적 관측에서도 평균은3.10~3.25m여서
남은 공통 제한은 약한 구별력·다봉 분포/전역 평균의 해석이며 단순 투영/검출 버그로 확정하지 않는다.

Thrun ch6 대조(문턱/모델 변경0):
- §6.2 지도 가정: 벽/문 XML 일치, 이번 자료에서 지도 불일치 증거0.
- §6.3/6.4 range endpoint 가정: 이번 시작 자료98.77%는 진짜 하단, 바닥 오인은 주원인 아님.
- §6.4 nearest occupied endpoint는 자유공간·가림·높이를 점수에 넣지 않는다. 오답[-0.15,0.05,−90°]도
  첫5시점 중4시점의 하단잔차 중앙0.20~0.69px로 벽 모서리 배치를 잘 흉내 낸다.
  문이 보이는8.25초는GT1.185px/오답15.985px지만 점수7.427/6.284에 그쳐 구별 신호가 약하다.
- §6.1/6.7 열·시점 상관을 독립 관측처럼 다룰 위험은 존재한다. 실제 코드는 빔 확률의 곱이 아니라
  Nav2의 `1+sum(pz^3)`이므로 “96독립 빔 곱 때문에 폭주”라고 진단할 수 없다. thinning은
  오히려 오답/GT0.69→0.82, 정답 질량9.04→0.28%; 상관 제거만으로 해결된다는 증거 없음.
- 이상적 접점도 평균 오차3.104m. 관측 우도와 active planner의 예측 모델을 일치시키고
  서로 다른 장소/특징을 보는 관측이 필요한지 다음 단계에서 검증할 사항이며 이번에는 수정하지 않는다.

저장 코드의 첫 실행은 XML geom의 `zone_` 접두사 누락으로 최종 저장 전 HOST_ERROR_OFFLINE,
두 번째는 plotting 의존성 미설치. 두 진단 중간산출물을 보존하고 접두사 수정·기존환경의
cached matplotlib 설치 후 동일 격자/문턱 재계산 완료. 모델/물리 실행 실패에 합산하지 않는다.
출력 스코어 동일성/좌표 변환 시험1개 PASS, A 관련11시험 PASS. B 제어 수정0.

### v131 seed1051 full DEV 결과 — 물리 파지/내려놓기, B 밖

소스 **b5fbe149**, 번들 `zone-s2-realism-v131`/7.24.0,
raw `/Users/changmin/projects/ugrp/outputs/s2-realism-b5fbe149-s1051-P1-2-lookahead`.
[전체 결과](look-ahead-dev-result.json): `lifted=true`, `inside=false`, floor/stable=true.
상태기계는done(`STAGE_REACHED_UNQUALIFIED`)이나 **목적지 성공은false**. B 경계까지 **2.336m**.
총271.25 SIM초/479.144 wall초, wall/SIM **1.766**. 모델호출0·재집기0, 실제 낙하/파지이탈 판정0.
파지 확인 `REAL_PREGRASP_UNCONFIRMED`는1회 기록하고 실제 blind 파지→운반→내려놓기까지 진행했다.
옵션 전부 raw result/options·사전 등록에 저장; 기준1267949b에서 제어 옵션 차이는pregrasp policy 하나.

운반71.85~249.25초: 시각 가중치 갱신19회, 최장공백 **45.00초**, XY RMSE **1.154m**,
종료 오차 **2.710m**. 이는 AMCL 비상수 우도 갱신이며 완전한 absolute fix19회라는 주장은 아니다.
실제카메라/상자+정적벽+명령 자기몸 기하의1Hz 평가178프레임: 전체17088열 중
벽하단 clear10421(**60.98%**), 아래밖6546(38.31%), 벽가림121(0.71%).
검출열3888개 중 clear3831(**98.53%**); 자기몸 가림은 보수적 명령기하 경계이며 정확 관절 GT가 아니다.
이전real_delivery의24%/133초보다 가시 기회/공백이 좋아졌지만 자세·강성·닫힌 경로가 달라 인과효과로 합산하지 않는다.

| 벽 접촉(운반 구간, 양의 법선력만) | 연속 episode | 20Hz 표본 | 표본시간 합 | 최대 법선력 합 |
|---|---:|---:|---:|---:|
| 바퀴–분리벽1 | 54 | 188 | 9.40초 | 8.733N |
| 손가락–분리벽1 | 20 | 123 | 6.15초 | 1.064N |
| 상자–분리벽1/2 | 35 | 707 | 35.35초 | 3.628N |
| 차체–벽 | 0 | 0 | 0초 | 0N |

episode는 인접20Hz 양의접촉 표본만 연결하며 하나의 충돌 시도 수가 아니다. 바퀴 contact manifold geom-pair 표본은1581개.
write-only `eval_only/wall-contacts.jsonl`·`wall-contact-summary.json` 보존, 제어/정지/전환 입력0.
would-stop 전부: **ARM_COLLISION_GUARD7, POSE_UNCERTAIN381, REAL_PREGRASP_UNCONFIRMED1, VISUAL_STALL_SUSPECTED3**.

남은 가장 큰 증거: 내려놓기 직전 추정[4.389,−2.110]m인데 실제 경로 오차2.710m로 B 도착을 잘못 판단했다.
슬립 진단 coarse28펄스 중 **27 unknown_preserved /1 slip_replaced**, 회복 동작0.
unknown27의 첫 탈락은 texture22/rigid consensus5. 후속unknown_frame308개는 마지막 성공 추적부터의
시간 공백으로 연쇄 발생할 수 있어 “RGB 파일308개 누락”으로 읽지 않는다. 따라서 벽 접촉에도 명령 예측을
유지한 구간이 많았다는 증거이며, 새 자세에서 광류가 왜 부족한지는 추가 분해 전 원인을 확정하지 않는다.
이번 결과 뒤 제어/문턱 수정0·추가 물리0. 등록한1회만 종료했고 agent_lock release/status=null·세션 정리 확인.

[전달 검증](look-ahead-dev-delivery.json): TensorBoard **22수치** source/event/live API 일치(UI 미검증, 수치 확인 범위),
`1008-s2-v36-likelihood`·`1008-s2-v36-full-v131`·`1008-s2-v36-v131-video` 신규 snapshot.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-v36-%28likelihood%7Cfull-v131%7Cv131-video%29%2F#timeseries).
4배속 영상 `outputs/s2-realism-b5fbe149-s1051-P1-2-lookahead-4x.mp4`: 5340프레임/80fps/66.75초,
native media 등록·HTTP raw range206 검증. 이전raw·bundle·snapshot 불변, 원본 GitHub 백업 주장은 하지 않는다.
관련 실행11시험 + 오프라인 점수/접촉2시험 PASS. 결과 후 문턱 변경 없음.

후속 CI 원인/최소 수정: 실행SHA b5fbe149의 run37650297077에서 preflight SUCCESS,
`offline-regression-checks`는 duration coverage477/533<90%로 실패,
`ubuntu-simulation-runtime`은 v128/v129의 현재 shared carry 소스 해시 불일치를 옛 시험이
실행 가능/`recovery differs`로 기대해4개 실패했다. 옛 번들/등록/생산 해시 가드는 **변경하지 않는다**.
시험은 현재 소스에서 정확히 `shared behavior changed ... zone_solo_cyan_real_carry`로 실행 전
거절·원본 결과 생성0을 검증하도록 갱신했다. Runtime 자체 wiring 검사는 그대로 유지한다.
완료된 원격 JUnit artifact만 받아 기존 측정과 파일별 max로 duration표를 보완했다:
현재491/534(91.95%) coverage, 새로 측정된16파일. 추정 시간을 만들어 넣지 않았다.
[출처/변경표](ci-v131-duration-refresh.json), raw `outputs/s2-v36-followup-delivery/ci-durations-37650297077`.
로컬은 변경 시험3파일만 검증하며, 원격 전체 CI 완료/물리 성공과 구분한다. 병합0.
CI 수정 검증: `test_s2_slip_matched.py`, `test_s2_slip_recovery_full.py`, `test_ci_sharding.py`
**74 PASS/59.14초**. 실행 관련13시험과 별도이며, 원격 전체 CI 재완료는 아직 확인하지 않았다.

## s2v37 — AMCL 최대 군집 pose 추출, 재생 전 사전 등록 (2026-10-08)

사용자 판단: s2v36 시작 우도 최대점은 정답에서5.2cm인데 전체 가중평균은3m 이상이다.
`pose_estimate=amcl_best_cluster_v1`(기본off)으로 Nav2의 최대 **군집 질량** 평균을
보고/경로 계획의 PoseReport에 연결한다. 최고우도 개별 입자를 고르거나 GT 근처 군집을 고르지 않는다.
[사전 기준](best-cluster-criteria.json), [검증한 원본/해시](best-cluster-sources.json).

- Nav2 고정소스 `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`:
  [pf_kdtree.c 77–79,118–120,349–439행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf_kdtree.c#L349):
  0.5m/10° floor bin, 27이웃 연결 군집. yaw seam wrap·작은 가중치 bin 제거 없음.
  NumPy dense-grid 연결 성분은 같은 partition; 극단적으로 큰 격자는 기존 dictionary 구현.
  정확히 같은 군집 질량의 tie도 kd-tree leaf split 할당/역순 방문 순서를 재현한다.
- [pf.c 459–590,625–641행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/pf/pf.c#L625):
  군집 질량·XY 평균·원형 yaw, `pf_get_cluster_stats` 반환.
  [amcl_node.cpp 598–610,781–862행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/amcl_node.cpp#L781):
  최대 질량 가설 선택→`publishAmclPose`; **평균은 선택 군집, 공분산은 전체 필터**.
  `handleMapMessage`(1300–1322행)는 지도/자유공간 갱신이며 pose 선택 함수가 아니다.
- 출력 어댑터는 `FailClosedLoc.estimate`→`VisionPoseSource.report`→지연 PoseReport→
  `Runtime.last_report`/`OwnPose`/경로 계획에 적용. PF prediction·measurement·resampling·RNG는 불변.
  Active Markov의 직접 PF 호출은 전체 σ 종료 검사/입자 기반 행동 순위뿐이라 변경하지 않는다.
  군집≥2/최대질량<0.5는 `POSE_CLUSTER_UNCERTAIN` 기록만; 이 과반수 표시는 S2 진단 규칙이며
  Nav2 기본 파라미터라고 주장하지 않는다. 전체 공분산의 기존 `POSE_UNCERTAIN`도 유지한다.

결과를 보기 전 고정: s1052 강성 보정 정지 RGB214장(기존 KLD on, Augmented on)과
v131 seed1051 전체 녹화를 각각off/on 1회 재생한다. own RGB·자기 명령만 입력하며 GT는 파일 저장 후 채점한다.
입자 궤적 바이트/AMCL 갱신 동일, off가 기존 기록을1e-9 이내 재현해야 하며,
**s1052 시작 최종 오차≤0.25m**일 때만 seed1052 시작 구간 물리1회를 허용한다.
그 물리도≤0.25m일 때만 v131+새옵션 seed1051 full DEV1회. 모두 agent_lock/ugrp_session, freeze ON.
운반71.85≤t<249.25의 RMSE/내려놓기 직전 오차는 보고하되 새로운 관문을 사후 추가하지 않는다.
실패하면 물리0회, 문턱/군집 격자/우도 변경 없음. default off 바이트 동일성과 제어 pose 연결 포함
관련2시험 파일 통과 후 이 사전 등록/구현을 먼저 커밋한다.

§6.4 우도 구별력 비교(기록만): 우리 `sigma_hit=0.2m`, `z_hit=0.5`, `z_rand=0.5`는
위 Nav2 `amcl_node.cpp`988,993,995행 기본값과 같다. Nav2 likelihood_field_model.cpp
70–140행처럼 `1+sum(pz³)`를 쓴다. RGB 접점의 1.2px/16px 잔차는 직접 σ 단위가 아니고
바닥 투영→최근접 점유 셀 거리(m)로 변환된다. 우리 고정 range_max100m는 z_rand/100=0.005,
Nav2는 해당 LaserScan의 range_max로 나눈다. 벽 선을 따라 평행한 오답도 최근접 거리가 작을 수 있다.
기존 점수7.427/6.284=1.182배 구별력은 그대로 기록하며 sigma/z_rand/문 모델은 이번에 수정하지 않는다.

### 최대 군집 재생 결과 — 시작 관문 FAIL, 새 물리 0회

사전 등록/실행 소스 **9b87378b6624651878fecb2da24b191401b5b475**, 관련2시험 파일 **14 PASS**.
raw `/Users/changmin/projects/ugrp/outputs/s2-best-cluster-9b87378b-replay`;
[전체 판정/군집 질량](best-cluster-result.json). off/on 각각 s1052 214프레임,
v131 s1051 5340프레임을 처리했다. 두 off가 해당 기존 pose 기록을 **차이0**으로 재현했고,
off/on 전체 입자·가중치 궤적 바이트 해시와 AMCL 갱신 audit가 동일하다.
GT는 네 예측 파일을 저장·닫은 뒤 채점기에만 열었다. 다른 물리의 wall 시간 비교에 이 재생을 사용하지 않는다.

| 고정 녹화/지표 | pose off | 최대 군집 on |
|---|---:|---:|
| s1052 시작 최종 XY 오차 | 3.090308m | 3.089585m |
| s1052 정답25cm/15° 근처 질량 | 11.752675% | 11.752675% |
| s1052 시각 갱신 | 6 | 6 |
| v131 s1051 운반 XY RMSE | 1.154243m | 1.154243m |
| v131 내려놓기 직전 XY 오차 | 2.709823m | 2.709823m |
| v131 운반 시각 갱신 / 최장 공백 | 19 / 45.00초 | 19 / 45.00초 |

수치로 확인한 한계: s1052 최종21025입자는 연결 군집15개지만,
**최대 군집21006개/질량99.9096%**가 XY폭6.260×4.410m를 차지한다.
정답 근처2471개/질량11.7527%도 **전부 이 큰 군집 안**에 있다. 따라서 최고우도 지점이
정답5.2cm 옆이라는 사실과, 최대 **연결 군집**의 평균이 정답을 가리킨다는 주장은 다르다.
0.5m/10° 이웃 연결에서는 넓은 입자 지지집합이 한 군집으로 이어져 있으며 작은 입자/빈을
잘라 봉우리들을 나누지 않았다. 시작214보고 중210개는 군집1개, 마지막4개만15개다.
on의 최종 전체 σXY=2.356887m; 최대 질량이 높다는 이유로 수렴/확신을 선언하지 않는다.
v131 운반3548보고는 모두 군집1개이므로 평균 변경 효과가 없다.
`POSE_CLUSTER_UNCERTAIN` 조건(<0.5)은 이번 재생에0회이며 기존 σ 불확실성 신호는 보존된다.

시작≤25cm 관문 **FAIL**을 그대로 유지한다. 물리 seed1052 시작/seed1051 full 모두 **미실행**,
새 실행 번들 등록/인수0, agent_lock 획득·해제0(다른 egomap29 잠금을 건드리지 않음).
군집 폭·가중치·우도 문턱의 사후 변경0, 모델 호출0. 후속 해결책 튜닝을 이번 결과에 섞지 않는다.
이 증거에서는 pose 추출 변경만으로 시작/운반 오차가 해결되지 않았다.

[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-best-cluster-v37%2F#timeseries)
off/on 4개 새 snapshot의 **34수치 source/event/live API 일치**를 확인했다
([전달 검증](best-cluster-delivery.json), UI 미검증/수치 검증 범위). 기존 raw·snapshot 불변.
기록에 실행 중 CPU 경과시간은 있지만, 공용 잠금 없는 오프라인 처리이며 성능 비교/물리 wall/SIM 주장은 하지 않는다.

## s2v38 — 원본 AMCL likelihood_field 선택자, 재생 전 사전 등록 (2026-10-08)

사용자 가설은 넓은 posterior와 약한 우도 구별력이다. 먼저 실제 코드를 대조했으며,
기존 `measurement_model=amcl_likelihood_field_v1`/`amcl_update=ros_motion_v1` 경로가
이미 같은 hit/random·cubic 점수식을 사용함을 확인했다. 이번 명시적 옵션
`sensor_model=amcl_likelihood_field_v1`(기본off)은 독립 원본 순서 커널을 선택한다.
점수를 날카롭게 만들거나 likelihood_field_prob(로그 곱/ceil stride)로 바꾸지 않는다.
[사전 기준](amcl-sensor-criteria.json), [원본 해시/행](amcl-sensor-sources.json).

검증한 원본:
[ROS navigation f44bb1fc AMCLLaser::LikelihoodFieldModel 215–302행](https://github.com/ros-planning/navigation/blob/f44bb1fc2810399165115cc98b530fe4b9397c18/amcl/src/amcl/sensors/amcl_laser.cpp#L215),
[Nav2 235fc5ce sensorFunction 50–139행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp#L50),
[Nav2 기본값 963·973·988·993·995행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/amcl_node.cpp#L963).
ROS 생성 API 페이지는 접근 거절되어 고정 commit의 GitHub raw를 직접 읽고 보존했다.
Nav2 재다운로드 SHA256은 이전 보존본과 동일하다.

| 항목 | 원본 Nav2 / ROS 행 | 기존 S2 경로 | 새 sensor_model on / 차이 |
|---|---|---|---|
| 기본값 | node963,973,988,993,995 | likelihood_field.py19–21: σ=0.2m, z_hit/z_rand=0.5/0.5, max_beams60, max거리2m | 모두 동일; 튜닝0 |
| 빔 stride | Nav2 68–73 / ROS246–250: 정수 `(count-1)/(max_beams-1)`, 최소1 | endpoints59–60 동일 | 같은 규칙. **96열은 stride1→96개**, 60개 강제 상한이 아님 |
| 유효성 | Nav2 91–99 / ROS257–263: max-range·NaN 건너뜀 | 미검출·가림은 결측, 자기 RGB→지면 투영의 유한/전방 접점만 허용 | 동일 RGB 어댑터; 불명확한 열에 가짜 max-range를 만들지 않음 |
| 거리/좌표 | Nav2 82–117 / ROS237–281: 센서 외부 보정, 최근접 점유 셀 거리; 지도 밖2m | Field24–50: 정적 벽 1cm 격자 EDT; 카메라 외부 보정 포함 차체 좌표 접점 | 같은 고정 지도·접점; 레이저를 RGB로 바꾼 부분은 계속 명시 |
| 빔 점수 | Nav2 65–66,121–123 / ROS243–244,284–286 | likelihood77: `pz=.5*exp(-d²/(2*.2²))+.5/100` | 원본 그대로, range_max100m 유지 |
| 빔 합산 | Nav2 85,132 / ROS240,295: `p=1; p+=pz³` | likelihood78: `1+numpy.sum(pz³)` | 빔 순서대로 `p+=pz³`; 입자 축만 벡터화, 반올림 순서만 차이 |
| 입자 가중치 | Nav2135 / ROS298: `weight*=p` | amcl_update103–106,119 / augmented_start75–78,91: prior×score를 로그 공간에서 정규화 | 같은 상태/갱신 함수를 유지; prior×p와 수치 시험 대조 |
| random 분모 | Nav2 66 / ROS244: 메시지의 range_max | RGB 어댑터 고정100m, .5/100=.005 | 동일. 원본의 센서별 range_max를 100m라는 RGB 어댑터 값으로 정한 차이는 남음 |

max_beams=60을 “96개 중60개 선택”으로 바꾸면 원본 default 모델과 달라지므로 그렇게 하지 않는다.
원본의 d는 **미터 단위 최근접 지도 벽 거리**, 화면 row 잔차1.2px/16px 자체가 아니다.
새 옵션은 private `bind`로 해당 PF의 endpoint/likelihood 함수만 연결하며 기존 전역 함수·봉인 소스·
관측 가드·마스크·바닥 외형 필터·모션/리샘플링 정책을 변경하지 않는다. 기본off command/record는 바이트 동일.
원본 scalar loop/가중치 곱·stride·invalid 건너뜀·instance 격리 포함 관련2파일 **12 PASS**.

**결과 전 고정:** s1052 강성 보정 정지 영상214장(KLD/augmented on)과 v131 s1051 전체5340장을
sensor off/on 각1회 재생한다. **best_cluster는 양쪽 모두on**으로 고정하며 off는 s2v37 on 녹화
재생 pose를1e-9 이내 재현해야 한다. GT25cm/15° 근처 질량, 시작 최종 XY 오차,
운반71.85≤t<249.25 RMSE/내려놓기 직전 오차를 보고한다.
GT/오답 우도비는 기존 `s2-start-likelihood-208f10f1-final`의 같은6개 접점 집합,
첫 시점 GT 가설과 기존 고정 오답[-0.15,0.05,−π/2]를 평가에만 사용한다.
on마다 새로운 오답 최고점을 고르지 않으며 정답은 runtime 입력에 전달하지 않는다.
시작 오차 **≤25cm**와 off 재현을 통과할 때만 seed1052 시작 물리1회→그 결과도≤25cm일 때만
seed1051 v131+best_cluster+sensor full DEV1회, 모두 agent_lock/ugrp_session·freeze ON·dev_light.
미달이면 물리0·새 번들 인수0. 결과 후 σ·z_rand·stride·관문 변경 금지.

### s2v38 결과 — 기존 점수식과 수치상 동등, 시작 관문 FAIL

소스 **78c716819a8d46c8bbb0e2f9b401339608011e33**, [결과](amcl-sensor-result.json),
raw `/Users/changmin/projects/ugrp/outputs/s2-amcl-sensor-78c71681-replay`.
214+5340프레임을 조건별1회 재생 완료. best_cluster는 양쪽on, 다른 옵션/명령/영상 동일.
off가 s2v37 on을 두 녹화 모두 pose 차이0으로 재현했다.

| 지표 | sensor off | 원본 순서 sensor on |
|---|---:|---:|
| s1052 정답25cm/15° 근처 질량 | 11.752675% (2471개) | 11.752675% (2471개) |
| s1052 시작 최종 오차 | 3.089585m | 3.089585m |
| 8.25초 문 장면 GT/오답 우도 | 7.427104/6.284149 | 7.427104/6.284149 |
| 문 장면 GT/오답 우도비 | 1.181879배 | 1.181879배 |
| 같은6시점 누적 GT/오답 우도비 | 1.450229배 | 1.450229배 |
| v131 운반 RMSE / 내려놓기 직전 오차 | 1.154243 / 2.709823m | 1.154243 / 2.709823m |
| v131 운반 갱신 / 최장공백 | 19회 / 45.00초 | 19회 / 45.00초 |

on 커널은 실제로 s1052 6회, v131 전체29회 호출됐다(정보가 있는 갱신은23회). 96열에서 선택 전96개,
s1052 유효 빔38/95/44/90/91/49개: 60개 cap을 새로 만들지 않았다.
v131 endpoint 선택 검사는103회이며 유효 접점이 있는29회에 커널을 호출했다. 이 중6회는 상수 우도로 정보 갱신이 아니다.
off/on pose 최대차는 시작1.11e-15, 운반0. 시작 입자·가중치 **전체 바이트 해시는 다르다**:
저장 입자 좌표 최대차0, 가중치 최대차3.25e-19인 합산 순서 반올림이다. 운반 전체 궤적 바이트는 동일.
따라서 기존 점수식과 새 원본 순서 구현이 사실상 동등하며, 새로운 관측 정보/우도 구별력은 생기지 않았다.
문 시점 최근접 벽 거리 중앙값은 GT0.09m/오답0.25m(각각σ의0.45/1.25배);
화면 row1.2px/16px를 σ=0.2m에 직접 대입한 모델이 아니다. 이 추가 수치는 평가에만 기록했다.

**시작≤25cm FAIL**, 사전 판정 그대로 유지. 새 물리/번들 인수/잠금 획득·해제0, 모델0.
σ·z_hit·z_rand·range_max·부분 표본 규칙·판정 문턱의 사후 변경0.
“원본 점수식으로 교체하면 해결된다”는 가설은 이번 재생에서 지지되지 않았다.
기존과 다른 점수식을 만들거나 관측 모델을 다시 튜닝하는 작업은 수행하지 않았다.

[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-amcl-sensor-v38%2F#timeseries)
off/on 4 snapshot의 **34수치 source/event/live API 일치**를 확인했다
([전달 검증/커널 호출 수](amcl-sensor-delivery.json)); UI는 미검증이다.
raw 결과/이전 snapshot을 보존하며 연구·실물 성공 또는 wall/SIM 개선으로 합산하지 않는다.

## s2v39 사전 등록 — 색 구역 경계·문 랜드마크 (2026-10-08)

사용자/감독 결정: v38 점수식은 이미 원본 AMCL과 같았으며 문 장면 GT/오답 우도비1.18만으로
벽 하단의 perceptual aliasing을 해소하지 못했다. 새 `sensor_landmarks=floor_zones_doors_v1`
(기본off)만 비교한다. off/on 모두 best-cluster·명시 AMCL 센서ON, 나머지는 v38 재생 그대로다.
도크/행 prior, 새 지도, live GT, #405/#408 수정, 카메라 mount/FOV 변경은 없다.

- 기준은 [landmarks-criteria.json](landmarks-criteria.json)에 고정: s1052 시작 최종오차≤.25m,
  off 기준재현 pose차≤1e-9m/rad. 정답25cm·15° 질량, 기존 고정 GT/오답 후보 우도비,
  v131 s1051 운반71.85–249.25초 RMSE·내려놓기 직전오차를 보고한다. 결과 후 문턱 변경0.
- 입력은 기존 자기 RGB/발행 명령/고정 보정표/허용된 static map뿐. 모든 예측 파일을 닫은 뒤 GT 평가.
  시작6시점의 같은 오답 후보를 유지한다. 사전 등록 자료는 DEV 탐색 재생이며 새 확증으로 부르지 않는다.
- 통과할 때만 seed1052 시작-only1회(agent_lock·ugrp_session), 다시25cm를 통과하면 seed1051
  fullDEV1회. freeze/look_ahead/강성·보정/slip/회복/dev_light 유지. ENOSPC는HOST_ERROR.
  미달이면 새 물리0. 실행 번들은 통과 뒤 번호 예약/등록하며 기존 번들·원본을 덮어쓰지 않는다.

정적 지도 `zone_wide_door_geometry_v3` regions는 pickup(.12,.36,.70,.14), A(.95,.45,.10,.30),
B(.20,.40,.95,.30), C(.70,.20,.85,.30)와 중심·직사각형 변을 공개한다.
`sim/zone_arena.py:411–413`은 바로 이 rgba/기하를 렌더한다(새 상태 입력 아님).
문은 passages.door_1 중심(2.2,.05), 폭.5m. pickup/B는 파랑 signature가 겹치므로 후보를 모두 유지한다.
#408 동결 `floor_goal_v2/v3`를 읽기만 했으며, B 전용 H109–115/S77 조건을 전체 네 색에 무단 적용하지 않았다.

### 표준과 RGB 어댑터의 구분

[Thrun·Burgard·Fox, Probabilistic Robotics §6.6, pp177–180/Table6.4, §7.5](https://cs.pomona.edu/~ajc/other/Thrun%20et%20al_2005_Probabilistic%20robotics.pdf)
의 특징별 Gaussian 거리·방위·signature와 미지 대응의 최대우도 선택을 따른다.
문은 양쪽 바닥 접점으로 얻은 중심의 거리·방위·폭; 부분 바닥선은 중점을 지도 모서리로 날조하지 않고
법선거리·방위와 유한 선분 범위를 쓴다. [Arras/Siegwart 선 특징](https://www.cs.cmu.edu/~motionplanning/papers/sbp_papers/integrated2/arras_feature_extract.pdf)
은 선의 법선거리·각도 표현 근거이며, 해당 논문의 range 분할/공분산 학습 전체를 이식했다는 주장은 하지 않는다.
[OpenCV HSV](https://docs.opencv.org/4.x/da/d97/tutorial_threshold_inRange.html),
[HoughLinesP](https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html)를 색 분할/직선 추출에 쓴다.

카메라 어댑터 수치는 표준 기본값이 아니라 결과 전 고정한 후보값이다: HSV 색차12(0–179),
S20–150/V≥35, 성분300px, 선40px·양쪽 지지80%, 바닥평면 직선 잔차3cm, 길이12cm,
동일선 중복제거·최대4개. 고정 자기 기하 그림자/own RGB cyan mask와 하향6m 이내 교차만 사용.
문은 깊이차25cm·양쪽 유효 접점·중간의 더 먼 floor 반환·두 수직 엣지 지지45%를 모두 요구한다.
바닥선σ=.1m/5°, 문σ=.2m/3°/.1m, 거짓 관측 random혼합5%를 고정한다.
직접 관측한 특징만 곱하며 불검출은 부정 증거로 쓰지 않는다. RGB 어댑터·독립성 가정은 미검증 후보다.
측정 시점/정착/AMCL 이동 trigger·KLD 정책은 그대로 유지한다. 바닥 외형 필터가 벽 관측을 모두
지우더라도 독립 색 경계는 측정 가능하게 빈 벽 packet을 유지하며, 가짜 벽 endpoint는 만들지 않는다.
공용 camera_robot_port·다른 제어기는 수정하지 않는다. off는 이전 명령/record byte 동일 시험으로 고정한다.

### v39 재생 결과 및 조건부 물리 사전 등록

예측 소스`da3d2eb8`, [원본 판정](landmarks-result.json), raw
`/Users/changmin/projects/ugrp/outputs/s2-landmarks-da3d2eb8-replay`.

| 고정 녹화 지표 | off | on |
|---|---:|---:|
| s1052 시작 최종 위치오차 m | 3.089585 | **.069680** |
| 정답25cm·15° 입자 질량 | .117527 | **.961074** |
| 문 장면8.25초 GT/동일 오답 우도비 | 1.181879 | 175125.013651 |
| v131 s1051 운반 RMSE m | 1.154243 | 1.180939 |
| 내려놓기 직전 오차 m | 2.709823 | 2.778084 |
| 운반 갱신 / 최장 공백 s | 19 /45 | 20 /33.25 |

시작 색 경계23개/6갱신, 문 검출0개다. 큰 우도비 증가는 **색 경계**의 추가 Gaussian에서 나왔다.
문 개구부가 보이는 것과 현재 검출기가 문을 측정하는 것은 다르다. 문 추가 기여는0으로 기록한다.
운반은 색 경계90개/특징 포함 갱신25회(전체 녹화), 문0개다. off pose·입자 궤적은 v38과 동일.
시작 기준PASS, 운반 RMSE는2.31% 악화이며 숨기지 않는다. 운반 개선은 사전 필수 게이트가 아니므로
사용자 순서대로 시작 물리만 먼저 허용한다. 결과 후 검출/우도/성공 문턱 변경0.

[물리 등록](landmarks-physical-registration.json): origin/main과 열린15PR 참조의 최대131/7.24.0을
[예약표](landmarks-reservation.json)에 확인했다. 시작`zone-s2-realism-v132 /7.25.0`,
조건부 full`zone-s2-realism-v133 /7.26.0`; 각각 seed1052/1051 1회만 예약한다.
시작은 재생과 같은 augmented/KLD + 보정된 일반 정지 wrist scan(추가 active-Markov 회전OFF)이다.
마지막 SEARCH 관측 뒤 첫 nonzero 주행 명령 또는 pickup 탐색 전환을 **발행하기 전** 종료,
상한30SIM초. 종료 조건은 명령/제어 상태만 보고 GT는 종료 후25cm 평가에만 쓴다.
시작 물리가25cm 이내이고 정상 종료한 원본result 해시가 있어야 같은 소스의 full이 열린다.
full은 v131 옵션 + best-cluster/명시 AMCL/새랜드마크만, 전역KLD·새 시작prior 추가0.
freeze ON은 S2 단독 DEV 한정이고 S3·짝 운반·본 연구/정식 사전등록 코호트에는 금지한다.
새 full은 해당 게이트 통과 뒤에만 실행하며 source/options/hash는 result에 보존한다.

재생 전달: TensorBoard `1008-s2-landmarks-v39` 4뷰/32수치를 원본→event→live API로 대조했다
([검증](landmarks-delivery.json)); UI 화면 검증은 하지 않았다. raw의
`start-landmark-observations.png`는 own RGB 위 후보를 표시한다. 일부 벽-바닥 선도 색 경계 후보에
남아 있으므로 23개는 정답 확인된 랜드마크 개수가 아닌 **검출 후보 개수**다. 문 미검출·운반 악화와 함께
미검증 한계로 보존하고, 재생 이후 검출 파라미터는 바꾸지 않았다.
freeze 공통 검증에는 새 start-only DEV의 명시적 사용자 승인·S2/solo/DEV·옵션 조합만 허용하는
좁은 분기를 추가했다. 사전 등록 사실은 true로 보존하며 본 연구 제한을 우회하지 않는다.

### v39 물리 완료 — 시작25cm PASS, S2 단독 full DEV inside=true

실행 소스`b2de2b30e2a0191d6b911125a9cc8ddb697614bb`,
[전체 결과·해시](landmarks-physical-result.json). 시작`v132`/seed1052와 full`v133`/seed1051을
각1회 순차 실행했다. 새 seed 대체/재시도0, 모델 호출0, GT 제어0, 결과 후 문턱 변경0.
표준 `sim_cli workflow run`을 `ugrp_session run`으로 감싸고 각 드라이버가 agent_lock을
acquire/finally release했다. 두 세션 종료와 각 lock.json의 status_after=null을 확인했다.

시작: **최종7.6877cm**,6시각갱신,13.50 totalSIM/24.789wall초,wall/SIM1.83624.
nonzero wheel 명령0·운반0. would-stop은 ARM_COLLISION_GUARD6/GLOBAL_START_UNRESOLVED1/
POSE_UNCERTAIN1. 이 완료result의 SHA256을 full 번들 start_proof에 묶어 조건부 실행을 열었다.

| seed1051 실시간 DEV 지표 | 기존 v131 | 새 v133 |
|---|---:|---:|
| lifted / inside / stable | true / false / true | **true / true / true** |
| B 구역까지 상자 잔여거리 m | 2.336 | **0** |
| 운반 갱신 수 / 최장 공백 s | 19 /45.00 | **28 /23.30** |
| 운반 XY RMSE m (GT 평가만) | 1.154243 | **.217977** |
| 내려놓기 직전 오차 m | 2.709823 | .139466 |
| 실제 벽 하단 가시율 (1Hz·96열) | 60.98% | **99.42%** |
| 바퀴-벽 접촉 연속구간 / 표본 | 54 /188 | **0 /0** |
| wall / totalSIM s | 479.144 /271.25 | 612.940 /311.10 |
| wall/SIM | 1.76643 | 1.97023 |

새 full의 운반 창은81.85–289.10SIM초. B 중심까지 .138275m, 상자는 floor/stable 판정도 통과했다.
wheel/body/finger/cargo–wall 양의 접촉력 표본 모두0이다. would-stop은
**POSE_UNCERTAIN293·ARM_COLLISION_GUARD7**(기록만); 물리 실패0·regrasp0.
시각 집기 확인은 `probable_held_inhand_rgb`; 원래 자리 차분은 effective verifier가 inhand이므로
실행하지 않았고 `pickup_site_comparison=false`를 그대로 보존한다. 판단을 물리 성공으로 바꿔 쓰지 않았다.

두 full 모두 freeze ON이다. 이 표의 시간 차이를 freeze 전/후 효과라고 해석하지 않는다.
실제 운반 경로도 달라 단일 DEV 비교이며 이전 폐기 조건·연구 성공률과 합산하지 않는다.
남은 한계: 운반 색 경계 **112후보**, 문 **0관측**. 시작 aliasing 해소는 색 경계가 기여했고,
문 특징의 실녹화 유효성은 아직 확보하지 못했다. 일부 벽/바닥 접점이 색 경계로 남는 문제와
POSE_UNCERTAIN293도 보존한다. 이번 결과 뒤에는 추가 수정·추가 물리를 하지 않았다.

- 시작 raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-b2de2b30-s1052-landmark-start`
- full raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-b2de2b30-s1051-landmark-full`
- 4배속 own RGB 영상: 위 full의 `execution.mp4` (640×480,20fps,76.7s,1,495,364bytes).
  원본6137장/20Hz를80Hz 입력→20fps로 내보냈다. ffprobe·전체 디코딩·SHA256·native영상Range206 확인.
- [TensorBoard](http://127.0.0.1:6006): `1008-s2-landmarks-v39` 재생32수치,
  `1008-s2-landmarks-dev` 시작/full/v131 비교47수치 및 full-media 영상 등록.
  원본/event/live API **79수치 일치**, UI 화면 확인은 미수행.
  [전달 검증](landmarks-physical-delivery.json); shared viewer는 새 자기 키만 추가했다.
- 관련 시험: landmarks/AMCL14 PASS, 실행허용/freeze/workflow37 PASS.
  새 workflow plan 예시와 기존 v131 누락을 보완했다. 전체 CI 통과/본 연구·실물 성능 주장은 하지 않는다.
  PR #406 DRAFT 유지·병합0, 원본 보존, 공용 camera_robot_port/#405/#408 수정0.


## s2v40 사전 등록 — v133 첫 DEV 성공의 새 seed 재현 (2026-10-08)

사용자 요청: **설정·문턱·제어 코드 변경0**, 새 미사용 seed **1053 →1054**를 각1회 full DEV.
[seed 확인](reproduction-seed-audit.json): origin/main/열린15PR의 seed 기록과 공용 outputs 실행명을
확인해 두 번호의 기존 사용0. P1-2/r3/B/door_1·상한900SIM초·dev_light·freeze ON을 그대로 둔다.
[등록](reproduction-registration.json). 실패는 원인만 기록하며 수정·재시도·대체 seed0.
ENOSPC는 HOST_ERROR이며 성공 문턱은 기존 lifted/inside/floor/stable 평가 그대로다.

고정 제어/물리 소스 **027c567c45ec05968d7243212fbce1b4aa4d2d59**와 번들 **v133/7.26.0**.
실제 첫 성공 실행 SHA는 b2de2b30이며 027c567c는 그 결과 문서만 더한 커밋이다.
성공 raw bundle의 **436개 의존 파일 SHA256**을 현 파일 및027c567c git blob과 대조한다.
옵션·6개 보정/모델 표·주기·cap·평가·실행 loop는 모두 기존 byte를 쓴다.
기존 seed1051 전용 admission은 보존하고, 새 `zone-s2-v133-reproduction` 관리 어댑터가
등록한 두 seed만 허용한다. 새 동작/새 제어 번들이 아니며 **v133 프로필을 재사용**한다.
원래 start proof는 b2de2b30 source에 대해 원래 validator로 검증한다.
새 번들 인스턴스 해시는 seed/provenance 때문에 다르므로 예전 해시와 같다고 주장하지 않는다.
추가한 것은 새 seed 허가/출처 기록뿐이며 실행 소스 SHA와 사전등록 어댑터 SHA를 구분한다.

출발 조건도 기존과 동일: `zone_solo_cyan_v106.py:103–108`의 공통 경기장 시작영역 prior
(x=공통 시작x, y=모든 행 평균/행 범위 σ, yaw=0의 분포)는 유지한다.
**자신의 도크/행 배정·GT 위치·seed→행 조회는 제어기에 주지 않는다**.
경기장 전체 균일 초기화 또는 KLD 옵션으로 변경하지 않는다(기존 v133 full에는 없음).
첫 nonzero base 명령 시각 이하 마지막 pose를 pose.t_est 시각의 저장된 eval 궤적과 비교해
출발 오차를 계산한다. 주행을 못 한 경우 마지막 pose 및 endpoint를 명시한다. GT는 종료 후만 읽는다.
운반 RMSE/최장 갱신 공백/벽 가시율은 기존 사후 평가기 그대로, 접촉은20Hz 양의 접촉력의
wheel/body/finger/cargo–wall 표본·연속구간, B 거리는 상자→B **중심** 거리다.
would-stop 목록과 실제 실패를 따로 보존하고 own RGB 영상 각1개를4배속으로 outputs에 남긴다.

agent_lock이 null일 때 acquire → ugrp_session + 표준 sim_cli 관리 → finally release,
두 실행은 순차 진행한다. 현재 ego-map 물리가 잠금을 보유하므로 물리는 시작하지 않았다.
freeze는 S2 단독 DEV만이며 S3/짝 운반/본 연구에는 금지; 폐기된 조건과 합산0.
raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-027c567c-s{1053,1054}-v133-reproduction`.
사전등록 이후 결과에 따라 문턱/옵션/기준 변경0. PR #406 DRAFT·병합0.


### v40 재현 완료 — 두 새 seed 모두 S2 DEV 성공

사전등록/행정 어댑터 SHA **ebb24028e13c45115bdcdd116f76fce92be5c968**, 실행 프로필 소스
**027c567c/v133**, [전체 결과·옵션·해시](reproduction-result.json).
성공 당시 b2de2b30와027c567c의 차이는 결과 문서뿐이며, 두 새 실행 모두 원본 bundle의
436개 의존 파일이 현 파일·027c567c git blob과 동일했다. 원본 옵션 전체·6보정표·제어/물리
loop·문턱을 유지하고 seed와 실행 provenance만 변경했다. 물리2회/재시도0/모델0/수정0.

| 개별 DEV 지표 | s1053 | s1054 |
|---|---:|---:|
| 첫 주행 직전 위치 오차 m (GT 평가만) | .060119 | .031858 |
| lifted / inside / floor / stable | true / true / true / true | true / true / true / true |
| 상자→B 중심 거리 m | .120569 | .244974 |
| 운반 XY RMSE m | .111519 | .215839 |
| 운반 갱신 / 최장 공백 s | 28 /20.65 | 28 /24.25 |
| 내려놓기 직전 위치오차 m | .105331 | .191110 |
| 벽 하단 실제 가시율 (1Hz·96열) | 99.8589% | 99.9446% |
| 바퀴/차체/집게/상자–벽 접촉 구간·표본 | 모두0 | 모두0 |
| wall / totalSIM s | 545.351848 /308.25 | 717.083562 /432.30 |
| wall/SIM | 1.769187 | 1.658764 |
| 발행 명령 / 모델 호출 | 3958 /0 | 8920 /0 |

s1053 would-stop: **ARM_COLLISION_GUARD7, POSE_UNCERTAIN200, GRASP_INHAND_UNCONFIRMED1**.
s1054 would-stop: **ARM_COLLISION_GUARD7, POSE_UNCERTAIN312, CYAN_NOT_UNIQUELY_VISIBLE5**.
이 판정은 dev_light로 기록만 했으며 시각 불확실성을 성공 확인으로 바꾸지 않았다.
실제 물리 실패·실행 오류0. 두 실행은 기존 posthoc DEV 판정으로 성공했으며 실물/정식 연구
졸업 성공률로 확장하지 않는다. 폐기한 조건과 합산하지 않는다. S2 solo DEV freeze 범위 그대로다.

s1054의 탐색이 길었다. 운반 진입은 s1053 **94.8** 대 s1054 **203.7** SIM초이며,
운반 창은 각각94.8–286.25 /203.7–410.3초. 시작 오차가 작은 것과 집기 대상을 빨리 찾는 것은
별도 결과다. 두 성공 뒤 추가 진단 물리·튜닝·보완 수정은 하지 않았다.

각각 `ugrp_session`의 s2v40-s1053/s2v40-s1054가 종료됐고 driver PID65383/68425가
agent_lock을 acquire/finally release, 각 lock.json의 status_after=null이다. 다음 실행 전에도
null을 확인했으며 다른 작업과 물리 동시 실행0. 단계 사이 감독 파일은 지시 없음이었다.

- s1053 raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-027c567c-s1053-v133-reproduction`
- s1054 raw: `/Users/changmin/projects/ugrp/outputs/s2-realism-027c567c-s1054-v133-reproduction`
- 각 raw의 `execution.mp4`: own RGB4배속/640×480/20fps, **76.0초·1,382,679bytes** /
  **107.0초·1,856,004bytes**. 입력 프레임20Hz 연속성·ffprobe·전체 디코딩·SHA256 확인.
  원본 프레임/로그/과거 번들 모두 보존. raw 로컬 보관이며 원격 백업으로 표현하지 않는다.
- 관련 시험 **5 PASS**(재현 profile/변경 차단/기존 admission/start 경계), 실행 전 통과 후 등록 커밋.
  결과 후에는 원본/options/436file 해시·평가 정의·잠금·영상 불변식을 다시 확인했다.

- TensorBoard `1008-s2-v133-reproduction`: 새 두 실행 **40수치**를 원본→event→live API로 대조,
  기존 s1051 snapshot은 재변환 없이 비교 링크에 포함했다. 영상 페이지200/MP4 Range206 각각 확인.
  [전달 검증](reproduction-delivery.json), [TensorBoard](http://127.0.0.1:6006). UI 화면 확인은 미수행.
  공유 viewer는 새 자기 키만 추가했다. 관리 workflow의 read-only plan 시험 예시1개도 추가해
  해당 시험1 PASS(총 관련6 PASS); 실행/제어 코드는 사전등록 뒤 수정0.

## s2v41 — 정식 실행 전 would-stop 감사 (오프라인만, 2026-10-08)

대상은 v133 DEV 성공 s1051/s1053/s1054의 기존 raw뿐이다. 새 물리0, 제어·문턱·번들 변경0.
`scripts/audit_s2_formal_stops.py`는 저장 명령/상태/PoseReport와 별도 eval 궤적·접촉을 읽는다.
`soft()` 이벤트는1,51,101…회만 저장되므로 이벤트 행을 총횟수로 세지 않는다.
펄스 선택 기록 + 도착 checkpoint/search 전환으로 drive 호출을 복원해 총 counter와 모든
희소 occurrence/time을 일치시킨 뒤 분류한다. GT는 pose.t_est에 보간해 평가만 한다.

집계 전 고정한 **보고 기준**: XY오차≤25cm는 이전 시작 진단 예산 이내, >25cm는 예산 초과.
5cm·10cm도 모두 병기하고 yaw오차5° 초과를 별도 기록한다. 25cm 이내를 정식 주행 안전으로
부르지 않는다. 현재 제어 조건은 σXY>5cm OR σyaw>5° OR last_fix_t 없음 그대로다.
다봉/갱신 공백은 원인 설명 변수로 기록하되 실제 분기에 없는 조건을 추가했다고 쓰지 않는다.
NEES는 단일 군집이며 저장 군집XY 공분산 trace와 보고된 전체σ²가 일치할 때만 계산한다.
χ²₂(95%)=5.9914645는 기술통계 참고선이며, 상관된 펄스들을 독립 시행으로 세지 않는다.
다봉을 하나의 Gaussian으로 둔 χ² 검정을 확정 판정/실시간 GT gate로 제안하지 않는다.
새 감사 시험2 PASS 후 소스를 먼저 커밋하며, 최종 결과 후 문턱 변경0을 유지한다.

### v41 결과 — 경고를 줄이기 전에 공분산의 정확성부터 검증해야 함

감사 사전기록/소스 커밋 **2c5b4bc2**. [집계·출처](formal-stop-result.json),
행별 원본 `/Users/changmin/projects/ugrp/outputs/s2-formal-stop-v41-20261008/s{1051,1053,1054}.json`.
기존 성공3회의 후향 감사이며 새 물리0·명령 변경0·문턱 변경0이다. 아래 회수는 서로 독립인
실패 시행 수가 아니라 같은 실행 안에서 반복된 **주행 결정 시점**의 수다.

| POSE_UNCERTAIN 분해 | s1051 | s1053 | s1054 |
|---|---:|---:|---:|
| 합계 (counter·희소 occurrence 시각 일치) | 293 | 200 | 312 |
| 출발→집기 접근 / 집기 / 운반 / 내려놓기 | 58 /0 /235 /0 | 96 /0 /104 /0 | 48 /0 /264 /0 |
| XY σ만 / XY+yaw σ / yaw σ만 / fix 없음 | 288 /5 /0 /0 | 200 /0 /0 /0 | 297 /13 /2 /0 |
| 경고 당시 σXY 중앙값 cm | 6.49 | 5.79 | 5.97 |
| GT XY오차 중앙 /최대 cm | 26.81 /47.71 | 6.82 /17.99 | 20.86 /26.35 |
| XY오차≤25cm / >25cm | 108 /185 | 200 /0 | 299 /13 |
| ≤25cm 비율 (진단 예산 기준의 거짓 경보 후보) | 36.86% | 100% | 95.83% |
| ≤5cm /≤10cm (민감도) | 0 /0 | 16 /125 | 21 /39 |
| XY≤25cm이고 yaw≤5° | 106 | 166 | 237 |
| fix 나이 중앙 /최대 s (pose.t_est 기준) | 4.99 /48.39 | 5.69 /47.34 | 4.92 /156.64 |
| fix 나이>30s인 경고 수 | 2 | 1 | 2 |
| 저질량 다봉 불확실 판정 | 0 | 0 | 0 |
| NEES XY 중앙값 /χ²₂(95%) 초과 | 119.47 /293/293 | 5.80 /92/200 | 34.87 /264/297 |
| 무경고인데 XY>25cm (누락) | 44/200 | 0/286 | 0/326 |

실제 분기는 `zone_solo_cyan_pulse_cal.py:161–168`의 **σXY>0.05m OR σyaw>5° OR
last_fix_t 없음**이다. σXY는 XY 공분산 trace의 제곱근이며 최대 고유축의 표준편차가 아니다
(`zone_solo_cyan_best_cluster.py:75–89`). fix 나이/다봉 자체는 이 분기의 조건이 아니다.
805회 중 XY σ 초과803회, yaw σ 초과20회(중복18), fix 없음0회이다. s1054의15회만
2군집이지만 최대 군집 질량99.9%; 나머지는 모두1군집이다. 별도 저질량 다봉 경고0회.
집기·내려놓기0회는 그때 정확했다는 뜻이 아니라 이 **drive 판정이 적용되는 단계가 아님**을 뜻한다.

25cm 예산 기준으로 **607/805=75.40%가 예산 이내,198/805=24.60%가 초과**한다.
그러나 5cm 기준은37/805=4.60%,10cm는164/805=20.37%만 이내이고, XY25cm·yaw5°를
함께 요구하면509/805=63.23%다. 따라서75.4%를 정식 안전성에 대한 확정 거짓 경보율로
해석하거나 현5cm σ 문턱 완화 근거로 사용할 수 없다. 출발/운반별25cm 이내 수는
s1051 0/58·108/235, s1053 96/96·104/104, s1054 48/48·251/264이다.

단일 군집·저장 공분산 일치790회에 대한 `eXYᵀ PXY⁻¹ eXY`는 **649/790=82.15%**가
χ²₂(95%)=5.991을 넘었다. 다봉15회는 제외했다. 무경고812회에도 실제25cm 초과44회가
있다(모두s1051, 최대31.99cm). 즉 이 자료는 **불확실성이 지나치게 커서 생긴 경고만이 아니라
추정 편향/공분산 과신과 누락도 함께 존재**함을 보인다. 이 수치는 PF의 Gaussian 근사와
시간 상관이 있는 후향 진단이며 독립 시행에 대한 정식 χ² 유의성 검정은 아니다.

### v41 ARM_COLLISION_GUARD — 7곳이 아니라 같은 출발 스캔 7명령

세 실행 모두 **1.4/2.9/4.4/5.9/7.4/8.9/10.4 SIM초**의 같은 명령 순서:
LOOK_P20 pan1500→1230→970→1770→2030→1500, 마지막 SEARCH 복귀이다.
주행 전이며21회 모두 `wall_west`가 제한 벽이다. `zone_own_guards.py`의 보수적 구체
스윕에 고정 여유20+15mm와 **2σXY + 2σyaw×lever**(각각0.15m/0.20rad cap)를 더한다.

| 7명령의 제한 여유 mm | s1051 | s1053 | s1054 |
|---|---:|---:|---:|
| 추정 자세, 팽창 전 거리 범위 | 209.00–304.09 | 136.29–212.45 | 149.25–207.19 |
| σ 포함 팽창 여유 범위 | 336.30–351.80 | 297.72–352.16 | 337.24–352.03 |
| 최종 최소 여유 (음수→guard) | −142.80 | −161.43 | −187.99 |
| 같은 추정 자세, σ항만0인 최소 여유 (반사실 평가) | 170.35 | 101.29 | 114.25 |
| GT 차체 자세, σ항만0인 최소 여유 (평가 전용) | 91.39 | 91.39 | 86.10 |
| 기록된 양의 힘 벽 접촉 표본 | 0 | 0 | 0 |

고정 여유는 남겨 둔 반사실 비교다. 실제 실행의 바퀴·차체·집게·상자–벽 접촉도 모두0.
**초기 위치 불확실성 팽창으로 정지 관측 동작 자체를 막는 반복 경고**로 분류한다.
GT 여유86.10–96.45mm는 저장 명령 FK/동일 보수 구체 기준이며 실제 관절 mesh의 전 구간
최소 거리나 자기/다른 로봇 충돌까지 인증한 것은 아니다. 초기 관측을 얻어야 불확실성을
줄일 수 있는 구조를 정식 실행 전에 검증해야 하며, 이번에 guard를 끄거나 문턱을 바꾸지 않았다.

### v41 나머지 시각 판정의 원인

| 항목 | s1051 /s1053 /s1054 | 관측으로 확인한 원인 |
|---|---|---|
| 문 랜드마크 | 0 /0 /0 | 측정에 사용된33/104/87프레임에서 저장 접점을 재투영: 좌우 점프44쌍→간격20→폭7→개구부 내부 깊이 조건0. 원 함수가 요구하는 내부 유효점≥2와 문설주보다≥25cm 먼 median 조건을 동시에 만족하지 못함. |
| CYAN_NOT_UNIQUELY_VISIBLE | 0 /0 /5 | s1054 탐색 소진62.7/85.3/107.9/130.5/153.1초 모두 cyan0px·성분0·3D fit0·slot 후보0. 여러 cyan 충돌이나 slot gate 거절이 아니라 당시 탐색 시야에서 검출 자체가 없음. |
| GRASP_INHAND_UNCONFIRMED | 0 /1 /0 | s1053 VIA110/HIGH 각9프레임 모두 cyan0px(총18), hits0/9+0/9. 관측 근거 부재로 unknown이며 실제 파지 실패를 뜻하지 않음. |

문 분석은 **저장된 필터 통과 접점**을 고정 보정으로 역/정투영한 것으로 오차<10⁻⁶px,
96열 손실0을 확인했다. 원 `door_features`의 단계만 추적했고, 가림 마스크를 모두 clear로
둔 낙관적 상한에서도 내부 조건 뒤0개였다. 따라서0검출을 화면에 문이 없다는 증거로 쓰지
않는다. 가림/수직 edge 이전의 필수 기하 조건이 원인이다. 문턱/함수 변경0.
재현 코드 [audit_formal_vision.py](audit_formal_vision.py), 단계·프레임 해시는 raw의
`vision-diagnostics.json`에 있다. s1054 `01228.jpg`는 바닥만 보였고, s1053 `01548.jpg`와
`01708.jpg`는 cyan 없는 회색 면만 보임을 직접 확인했다. 다른 seed의 in-hand 검사는 양 자세
각9/9였으나 이것을 s1053의 unknown을 소급 승인하는 근거로 쓰지 않는다.

### 정식 실행 전 남은 일 — 표준 대조·제안만, 이번 변경0

1. Nav2 AMCL은 최대 질량 군집 pose와 **전체 필터 공분산**을 발행한다. 고정 커밋
   `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`의
   [getMaxWeightHyp 781–817 / publishAmclPose 822–862](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/amcl_node.cpp#L822)
   를 대조했다(로컬 원문 SHA256 `7c2e9ab56c61197d9bbc877fe4a706403f4e3ac80376a83d3394e48825dcb4ad`).
   우리의5cm 정지 예산은 이 publish 함수의 AMCL 기본 정지 문턱이 아니다.
2. [Huang·Mourikis·Roumeliotis, ICRA2008](https://people.csail.mit.edu/ghuang/paper/Huang2008ICRA.pdf)의
   consistency/NEES 절차에 따라 먼저 별도 자료로 편향·공분산 coverage를 검증할 것을 제안한다.
   다봉에는 단일 Gaussian χ²를 그대로 적용하지 않는다
   ([Gaussian mixture consistency, 2023](https://arxiv.org/abs/2312.17420)). GT는 오프라인 평가만.
3. 공분산이 검증된 뒤 `sqrt(χ²₂,0.95 × λmax(PXY))`인 위치 신뢰영역과 yaw 불확실성·
   로봇 외형을 통로 여유에 대조해 작업 안전 예산을 정한다. 수치 문턱은 **선정/변경하지 않음**.
   이번3성공 로그는 탐색 근거이며 새 holdout 또는 정식 E2E 결과가 아니다.
4. 출발의 정지 스캔은 알려지지 않은 위치에서도 관측을 얻을 수 있는 안전 동작 범위를 따로
   검증해야 한다. 문 특징0·대상 미검출·in-hand unknown은 정식 정책에서 어떻게 처리할지
   미완료 항목으로 남긴다. DEV3/3 성공을 정식 보수 정지가 켜진 E2E 통과로 승계하지 않는다.

검증: 감사 시험 **2 PASS**, 시각 감사 CLI 재실행 출력이 첫 결과와 **byte 동일**, 원본 raw
5종×3실행 해시 불변을 확인했다. TensorBoard 새 스냅샷 `1008-s2-formal-stops-v41`에 감사
3개를 등록해 **57수치**를 결과→event→live API로 대조했다. 기존 물리 snapshot/영상은
재변환하지 않았고 새 물리·영상0이다. [전달 검증·pin 링크](formal-stop-delivery.json),
[native TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-formal-stops-v41%2F#timeseries).
공유 viewer는 자기 키만 추가, 기존 서버/프로세스/잠금 변경0. UI 화면 확인은 하지 않았다.

## s2v42 — egomap33 좌회전 고정 보정 이식·재생 사전기록 (2026-10-08)

출처는 PR #405 **762a952f0786cb56e9ab88c8a2bf34ca2f346b87**의
`harness/self_pulse_rotation.py`·`harness/data/s2_pulse_v122_rotL_v1.json`이다.
[읽기 전용 복사/해시](rotation-left-sources.json), [원본 방법·사전기록](references/egomap33_rotation_README.md).
egomap32의 SEARCH·강성real_v1·무하중·v7에서 반복1–3으로 적합한 **1.1049453391322106**을
그대로 사용한다. 반복4–5 확인 yaw RMS .434668→.209624°였으나 같은 자료 재사용이고 S2
확증 결과는 아니다. 표준 근거는 [UMBmark §3.2–3.4](https://www.cs.columbia.edu/~allen/F17/NOTES/borenstein.pdf)의
방향별 평균/산포 분리와 원점 통과 최소제곱이며, 완전 사각 UMBmark 실험의 이식은 아니다.

S2 옵션은 **`rotation_calibration=s2_pulse_v122_rotL_v1`**, 기본off다. 기존 S2의
`motion_model` 인자는 v7 초기 보정 dict이므로 이름을 덮어쓰지 않는다. 최종 v133 runtime에
연결해 PF 예측·펄스 선택이 같은 보정 profile을 사용한다. 적용 조건은 자기 발행 팔 명령
`{1:2000,3:740,4:2320,5:1320,6:1500}` + 명령 기반 무하중 + 명시적 강성real_v1,
profile `0:turn:0.35:0.10`만이다. yaw mean curve와 endpoint만 원본과 같은 연산으로 곱한다.
우회전/XY/분산/다른 자세/**하중 look_ahead 운반은 v122 그대로**다. 실시간 GT·관절·접촉
입력0, 물리 파라미터 변경0, #405 worktree 파일 변경0, 현재 v133/과거 성공 번들 변경0.

세 녹화의 명령 목록에서 적용 가능한 좌회전은 s1051 **1회**, s1053 **2회**, s1054 **0회**다.
이 노출 수는 결과 전 확인한 적용 범위이며 운반 회전까지 근거를 확대하지 않는다.
[고정 재생 기준](rotation-left-criteria.json): off/on에 같은 자기 RGB·발행 명령을 재생하고
기존 주행 결정 시점에서 σ5cm/yaw5°/fix없음 판정을 그대로 계산한다. 예측6개를 봉인한 뒤
GT 평가만 수행한다. yaw는 명령 응답 잔차와 펄스 후 보고 yaw 오차를 좌/우·하중별로 분리,
운반 RMSE·단일군집 NEES 초과율·POSE_UNCERTAIN·무경고25cm초과를 모두 기록한다.

물리 관문은 사전에 다음으로 고정한다: off pose 차이≤10⁻⁹, 미노출s1054 입자 궤적 byte 동일,
세 실행 합산의 적용 CCW 잔차 RMS 감소·POSE 경고 수 감소·NEES 초과율 감소,
무경고25cm초과 수 비증가·운반 프레임수 가중 RMSE 비증가. **모두 통과할 때만** 새 미사용
seed를 별도 사전 커밋하고 새 번들의 full DEV1회(agent_lock/ugrp_session/freeze ON)를 실행한다.
미달이면 물리0으로 보고하며 결과 후 문턱·기준을 바꾸지 않는다. 개별 seed 결과도 병기하고
명령 고정 재생을 폐루프 성공으로 보고하지 않는다. 기존 would-stop·시각/충돌 문턱 변경0.

### v42 SEARCH 적용 재생 결과 — full DEV 관문 미통과

실행/사전기록 **9fb8e46f**, 시험9 PASS·시작300프레임 인수 재생 통과 후 커밋·push.
모든 off 녹화20,778프레임의 pose/time/σ/fix가 원본과 차이0, 기존 실행436파일 해시 불변.
[결과/해시](rotation-left-result.json), raw `outputs/s2-rotation-left-v42-20261008/replay`.

| 지표 off→on | s1051 | s1053 | s1054 |
|---|---:|---:|---:|
| 보정 적용 SEARCH 좌회전 |1 (20.15s)|2 (41.30/52.10s)|0|
| 운반 RMSE m |.217977→.217966|.111519→.114444|.215839→.215839|
| POSE_UNCERTAIN |293→289|200→326|312→312|
| NEES 참고선 초과/유효 경고 |293/293→289/289|92/200→180/326|264/297→264/297|
| 무경고 XY>25cm |44→47|0→0|0→0|

적용3펄스의 명령 yaw 응답 잔차 RMS **.492639→.165201°**. 반면 합산 경고805→927,
무경고25cm초과44→47, 운반 프레임 가중 RMSE .190008→.190552m로 악화했다.
NEES 비율82.15→80.37%는 경고 분모790→912가 바뀐 값이며 초과 수649→733도 함께
보고한다. 이를 전체 과신 해결로 해석하지 않는다. s1054는 off/on **입자 궤적 byte 동일**,
s1051/1053의 slip 판정도 동일. 기존 사전 물리 관문 **4/7, 실패 그대로 유지**, full DEV0.
경고 여부와 무관한 같은 유효 주행 결정1,602시점을 보면 NEES 초과는 **1,283→1,340회
(80.09→83.65%)로 악화**한다. s1051 445→443/493, s1053 248→307/486,
s1054 590→590/623이다. 바뀐 경고 집합의 분모 효과를 숨기지 않고 두 분모를 모두 기록한다.

### v42 감독 후속 사전기록 — 하중 look_ahead 회전 측정 (새 확증 운반 아님)

감독 파일 **[04:57]**: SEARCH 보정 효과가 작으면 full DEV 대신 상자를 쥔 look_ahead에서
egomap32와 같은 좌/우 단발·연속 회전을 약60초 측정하고, 처음3회 적합/마지막2회 확인 후
같은 세 녹화로 재생하라는 지시를 확인했다. 위 SEARCH 실패 관문을 완화하거나 성공으로
바꾸지 않는다. 이 후속은 별도 하중 측정이며 S2 성공률에 합산하지 않는다.

계획: 기존 s2v36에서 검증한 **자유 차체의 일회 초기 HIGH 집게 사이 수동 배치 → 정상
접촉으로 파지 → 실물 순서의 look_ahead 전환**만 재사용한다. 과거 실패한 차체 고정 지그·
연속 위치 보정·weld는 사용하지 않는다. v133의 강성real_v1/v7/v3/freeze ON/30g 블록,
벽에서 먼 (3,−1)m, yaw0, setup seed1051을 고정한다. 새 task seed가 아니라 보정 scene seed다.
차체·물체 GT는 초기 scene 배치 및 쓰기 전용 평가/물리 실패 중단에만 쓰고 명령 선택에는
사용하지 않는다. 측정 명령은 사전 시계열로 고정한다.

egomap32 schedule 그대로: 각 반복1–5마다 단발좌/우와10연속좌/우(짝수 반복 역순),
±.35/0.10s, 주기.20s, 블록 사이1.8s, 초기2s → **20블록·110펄스·60초**(파지 준비 별도).
평가20Hz, RGB5Hz, 고정60초 또는 낙하/그립 이탈/기울기/벽 접촉/실행 오류에서 종료.
양측 그립 이탈 .3초·cargo z<.06m·차체 tilt15°는 이전 진단 안전 조건을 유지한다.
추가 반복/조건 탐색은 하지 않는다. agent_lock null 확인 후 단독 acquire/release,
ugrp_session·종료15분 상한·디스크10GiB/ENOSPC=HOST_ERROR, 다른 작업 프로세스 변경0.

적합은 egomap32와 같은 per-pulse 정규화 원점 통과 최소제곱, 반복1–3을 독립 cluster로
한 t(2) 95%CI, 반복4–5의 확인 RMS를 쓴다. **방향별** gain CI가1을 제외하고, 단발/연속
gain 차이≤5%, 확인 RMS가 줄 때만 그 방향의 하중 look_ahead yaw 평균을 고정 옵션으로
허용한다. 미통과 방향은v122 그대로. XY/분산/문턱 변경0, 두 방향 모두 불충분하면 재생용
하중 옵션/추가 물리 없이 보고한다. 무하중 SEARCH 보정은 별도 off 상태의 v133을 기준으로
하중 옵션 하나만 비교한다(효과를 섞지 않음). 적합 가능 시 같은 세 녹화의 경고·NEES·무경고
25cm·운반 RMSE 및 해당 방향 yaw RMS를 위와 같은 비교 기준으로 평가한 뒤 full DEV 판단.

### v42 펄스별 yaw 잔차 (고정 녹화 평가)

[전체 방향별 수치](rotation-yaw-summary.json). 명령 모델 잔차는 예측−실제 회전량이고,
보고 yaw 잔차는 해당 펄스 horizon 직후 공개된 지연 pose와 그 **t_est의 GT** 차이다.
전자는 한 펄스 응답, 후자는 그전 누적오차/영상 갱신까지 포함하므로 혼동하지 않는다.

| 펄스 종류 | n | 명령 응답 RMS ° off→on | 펄스 후 보고 yaw RMS ° off→on |
|---|---:|---:|---:|
| 무하중 SEARCH CCW |3|.492639→.165201|6.369927→6.666627|
| 무하중 SEARCH CW |0|미관측|미관측|
| 하중 look_ahead CCW |11|.278525→.278525|1.910304→2.057279|
| 하중 look_ahead CW |14|.198301→.198301|2.558167→2.371341|

무하중 좌회전의 국소 응답은 개선됐지만 전체 yaw/위치 편향 해결로 이어지지 않았다.
회전 분산·관측·재표본·문턱은 변경하지 않았고, 이후 관측 수락 시점이 달라질 수 있는
명령 고정 재생의 결과다. 변경된 경고 집합에서의 NEES 비율만으로 개선을 확정하지 않는다.

### v42 하중 측정 완료 — 방향별 gain 근거 미달, 하중 보정 미채택

사전기록/측정 소스 **d2be4313bb0ad297d1e901dbfc7872673e8f06e7**, 관련14시험 통과 후
커밋·push. 새 진단 ID `s2-loaded-rotation-v1`은 main/열린 PR에 중복 없음을 예약 기록으로
확인했다. `ugrp_session s2v42-loaded-rotation` → 관리 workflow → driver PID80754가
agent_lock을 acquire/finally release, 종료 후 status=null·세션 stopped를 확인했다.
감독 파일을 커밋 직후/물리 직전/판정 전에 다시 읽었다.

- **60.0초·20블록·110펄스**, 평가1,201표본·own RGB301프레임(5Hz), 추가 측정0.
  파지 준비 포함64.65 SIM초 /72.0594 wall초(wall/totalSIM1.1146, 속도 비교 실험 아님).
- 30g 블록 양측 파지 유지 **100%**, 최소 중심 높이165.56mm, 최대 차체 tilt .15882°,
  벽 접촉0·weld0·낙하0. 제어/명령 선택에 GT 사용0, 고정 시계열 그대로 실행했다.
- [봉인 원본 이후 적합/확인 결과](loaded-rotation-result.json), 원본은
  `/Users/changmin/projects/ugrp/outputs/s2-loaded-rotation-v42-20261008`.

| 하중 회전 응답,5반복 | v122 °/펄스 | 실제 평균±SD °/펄스 |
|---|---:|---:|
| CW 단발 |−4.752267|−4.824717±.244995|
| CW 10연속/10 |−4.752267|−5.064975±.068362|
| CCW 단발 |5.007368|4.885147±.310771|
| CCW 10연속/10 |5.007368|5.004454±.065706|

| 처음3반복 적합·마지막2확인 | CCW | CW |
|---|---:|---:|
| gain /95%CI (독립 반복n=3) |.993893 /[.938119,1.049666]|1.034242 /[.960099,1.108385]|
| 단발/연속 gain 차이 |1.915%|5.940%|
| 확인 RMS °/펄스 off→가상 보정 |.290662→.280461|.272346→.152983|
| gain CI가1 제외 /차이≤5% /확인 개선 |FAIL /PASS /PASS|FAIL /FAIL /PASS|

**두 방향 모두 사전 관문 미달**이다. 하중 look_ahead의 기존 v122는 학습 표본CCW9/CW7을
사용하며, 무하중 SEARCH의 방향당1표본과 다른 profile이다. 현재 자료에서 하중도 좌회전
10% 과소라는 근거는 얻지 못했다. 하중용 gain 옵션/후속 세 녹화 재생/full DEV는 **미실행**,
SEARCH 옵션도 기본off·미채택 상태를 유지한다. 결과 후 문턱·표본·확인 분할 변경0.
다음에 gain을 조정하려면 새 근거가 필요하며 이번 결과를 좋게 만들기 위한 재측정은 하지 않았다.

4배속 영상 `outputs/s2-loaded-rotation-v42-20261008/rotation-4x.mp4`: 640×480/20fps,
301프레임/15.05초/294,909bytes. 첫/마지막 RGB·ffprobe·전체 디코딩을 확인했고 원본은 보존했다.

TensorBoard 새 스냅샷 `1008-s2-rotation-v42`에 여섯 off/on 재생과 하중 진단을 분리 등록했다.
[수치 대조 기록](rotation-delivery.json): 원자료↔event↔실제 API **145개 수치 일치**,
물리 원본309파일 해시 불변. 별도 native 영상 등록은 HTTP206/MP4를 확인했다.
공용 뷰에는 자기 키 `s2_rotation_v42_20261008`만 추가했고 기존 값은 보존했다.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-rotation-v42%2F#timeseries),
[4배속 영상](http://127.0.0.1:6007/video/df3da970eed438fefa7a).
숫자·데이터 로딩만 대조했으며 UI 화면/열 배치 확인은 하지 않았다. 기존 서버는 변경하지 않았다.

## s2v44 — 위치 일관성 분해·holdout 사전등록 (2026-10-08)

기준은 채택된 v133(회전 보정off)의 세 성공 녹화이며 기존 봉인 v42 예측을 재사용한다.
47건은 미채택 rotL-on 재생, 원래off는44건이므로 두 조건을 혼합하지 않는다. 제어 변경 없이
고정1,602 단일군집·공분산 일치 주행 결정의 x/y/yaw 평균·분산과 NEES를 계산한다.
단계 SEARCH/접근/운반/배치, 최근1초 내 자기 회전/전진/옆 명령, 실제 수락된 RGB
랜드마크 이후0–1/1–5/5–15/15–30/30초 이상으로 분해한다. 주행 결정이 없는 단계는n=0으로
남기고 프레임 수를 결정 수로 만들지 않는다. 시간 상관이 있으므로 독립 시행 검정이 아니다.

[고정 기준](consistency-criteria.json): XY bias²/MSE≥50%면 평균 편향 기여가 과반,
평균 제거 후 XY NEES χ²₂95% 초과가20%보다 크면 잔여 불일치도 있다고 분류한다.
평균 제거는 사후 설명이며 실제 pose 보정값으로 쓰지 않는다. 무하중 회전 보정은 미채택off.
수정 방식은 진단 뒤 표준 출처와 함께 별도 등록하되 **fit에 GT를 사용하지 않는다**.
두 녹화 적합/나머지 확인을 세 번 순환하고, 매 holdout에서 NEES 초과율≤20%,
무경고 XY>25cm=0, 운반 RMSE 증가≤10⁻⁹m, off pose 직렬화 동일을 모두 요구한다.
GT는 평가만, 결과 후 문턱 변경0. 세 holdout 모두 통과할 때만 감독 파일 재확인 후
새 seed를 별도 사전등록하고 lock/session 하에 full DEV1회. 미달이면 물리0이다.

### v44 1차 진단·표준 후보 선택 (적합/holdout 결과 전)

기준off 1,602시점의 평균 오차는 x +9.724cm /y −3.387cm /yaw −1.294°다.
XY 평균편향²은 MSE의28.27%; 평균 제거 전/후 NEES 초과율80.09/73.03%이며,
x 잔여분산 .009444m² 대 보고 .000790m²(11.96배)다. seed별 평균 제거 후에도
73.23/50.62/69.98%다. 따라서 **편향도 있고 잔여 공분산 불일치도 있다**. 평균 제거 뒤
남은 시간변동 편향/모델 오차와 순수 확률 잡음을 NEES 하나로 식별할 수는 없다.
47건(on)은 s1051 운반187.25–205.65초,44건(off)은187.25–204.45초에 모였다.
on 재생에는 특징 packet이 저장되지 않아 랜드마크 경과시간을 재구성하지 않는다.
전체 fix 나이는 따로 기록하며 off의 feature 기록을 on에 섞지 않는다.

표준 대조: [Nav2 OmniMotionModel,59–85행](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl/src/motion_model/omni_motion_model.cpp#L59)은
이동²/회전²의 α1–5로 전진·옆·yaw 분산을 만든다. 기존 최대군집 pose/전체 공분산 보고
자체는 AMCL 방식이며 이번에 임의 σ 배수나 GT 평균 빼기를 추가하지 않는다.
[Censi et al.2013](https://www.diag.uniroma1.it/~labrob/pub/papers/TRO13.pdf)은 외부GT 없이
자기 센서 이동과 구동 자료의 MLE 및 식별 가능성 검사를 제시한다. 여기서는 그 원칙과
Gaussian likelihood를 쓰며 논문의 차동구동 wheel-radius/외부 보정 동시 알고리즘을
그대로 구현했다고 주장하지 않는다. [출처·원본 해시](consistency-sources.json).

[적합 고정 절차](consistency-fit-criteria.json): 후보 `motion_noise=nav2_omni_mle_v1`,
기본off. 각 펄스의 **첫 measured RGB 구간 하나**만 선택해 공유 영상 중복을 피한다.
측정 공분산+기존±2.8° 공통 pitch의 radial 전파를 R로 두고,
Σ=Q(α)+R의 logdet+Mahalanobis Gaussian 음의 로그우도를 최소화한다. 잔차 평균을
빼거나 GT로 잡음을 늘리지 않는다. S2 기존 pulse 시간곡선의 구간/전체 시간 비율로 Q를
배분하는 방식은 그대로다. rank5·수치 수렴이 없으면 미식별로 거절한다.
자기 로그의 대상은 하중 큰 옆이동뿐이라 **그 profile만 적용**한다. 전진/회전/무하중/
fine에는 측정 근거가 없으며 v122 유지. 정상 평균·slip 대체·관측·정지 문턱 변경0.
2개 적합/1개 확인3fold 모두 기존 관문을 통과해야 물리로 간다. 부분 RGB 자료의 선택
편향·공통 카메라 오차 가능성은 남고, α 증가가 편향 원인을 고쳤다는 뜻은 아니다.

### v44 자기 RGB 적합 봉인 (holdout 재생 전)

펄스당 첫 구간만 사용해 s1051/1053/1054에서5/6/5구간, fold당11/10/11구간을 얻었다.
세 적합은 rank5·optimizer 수렴이며, [고정 계수](consistency-rgb-fit.json)에 저장했다.
각 fold의 α4/α5는0 경계해다. RGB의 R가 잔차를 설명하면 추가 운동 분산의 MLE가0이
될 수 있으므로 임의 하한으로 바꾸지 않는다. 이 자료로 x축 과신이 고쳐졌다고 주장하지
않으며, 확인 재생을 그대로 수행한다. 감독 [06:05]의 보정용GT 예외는 확인했지만
RGB 적합이 성립했으므로 이번 후보는 GT를 적합에 쓰지 않는다.

### v44 분해 상세·확인 결과 — 미채택, 새 물리0

[성분별 전체 JSON](consistency-diagnosis.json). 아래 NEES 평균 제거는 사후 평가이며 제어에 넣지 않았다.

| seed | bias x/y cm·yaw ° | 잔여 분산 x/y cm²·yaw °² | 보고 분산 x/y cm²·yaw °² | XY NEES 전→평균 제거 후 |
|---|---:|---:|---:|---:|
|1051|16.717/8.027/-1.126|87.90/129.91/8.34|5.91/229.79/6.37|90.26→73.23%|
|1053|5.915/2.387/-0.186|53.07/3.40/9.13|7.39/26.90/4.39|51.03→50.62%|
|1054|7.162/-16.924/-2.292|75.31/31.07/25.02|9.87/18.65/8.19|94.70→69.98%|

| 구분 | n | bias x/y cm·yaw ° | XY NEES 전→구간 평균 제거 후 |
|---|---:|---:|---:|
|phase/SEARCH|0|해당 결정 없음|미정의|
|phase/approach|345|0.824/-3.852/-4.135|66.67→72.17%|
|phase/carry|1257|12.167/-3.259/-0.515|83.77→74.22%|
|phase/place|0|해당 결정 없음|미정의|
|motion/turn|28|12.375/-1.500/-0.260|85.71→64.29%|
|motion/forward|1235|9.403/-3.891/-1.248|80.89→74.49%|
|motion/lateral|318|11.060/-1.198/-1.497|75.47→67.92%|
|motion/stationary|21|4.868/-9.428/-2.349|95.24→95.24%|
|age_bin/none|0|해당 결정 없음|미정의|
|age_bin/0-1|168|10.222/-3.391/-0.717|76.79→77.98%|
|age_bin/1-5|543|11.234/-3.165/-0.799|81.58→77.16%|
|age_bin/5-15|557|11.900/-1.556/-1.022|80.25→69.66%|
|age_bin/15-30|131|10.638/-4.240/-2.474|91.60→38.17%|
|age_bin/30+|203|-1.284/-8.451/-3.085|70.94→100.00%|

SEARCH/배치는 원래 drive의 POSE_UNCERTAIN 판정 기회가0이다. `motion`은 실제 운동 중
판정이 아니라 **결정 직전1초 내 자기 펄스 종류**이며, 대개 정착 후 다음 명령을 고르는
시점이다. 물리 상태로 분류하지 않는다. 전체1,617결정 중 단일군집 공분산을 검증할 수 있는
고정1,602시점만 NEES에 사용하고, 전체 경고/누락 수는1,617시점도 별도로 기록했다.
원래v133 경고805 중 유효 NEES경고790, 미포함15개는s1054 다봉 기록이다.

[누락 원인](consistency-miss-cause.json): off44건은 모두 s1051 운반187.25–204.45초,
x오차29.38–31.96cm/y오차−.56–1.79cm이다. 마지막 **랜드마크** 이후 .09–9.69초이고,
해당 운반81.85–204.45초에 벽 접촉0이다. 전진220펄스 예상2.84652m 대 같은 응답시간
실제2.57690m, 다음 명령까지 잔류운동을 포함해도2.54053m다(각 펄스 시작 body x 합).
그 기간 x오차 증가는19.38cm = 갱신 전후 감소11.48cm + 갱신 사이 증가30.85cm다.
즉 벽 접촉/랜드마크 공백보다는 **전진 과대예측 누적과 좁아진 사후 분포**가 누락 경고와
맞는다. 이것만으로 모터·마찰의 어떤 물리 파라미터가 원인인지까지 확정하지 않는다.

[전체 전진 펄스 평가](consistency-pulse-bias.json): s1051/1053/1054의 하중 전진
357/330/332펄스에서 평균 과대예측1.246/1.207/1.199mm, 평균을 제거한 산포σ는
.398/.418/.394mm다. 기존 모델σ .504mm보다 무작위 산포는 작다. 따라서 **NEES 잔여
불일치를 곧바로 백색 운동 잡음 alpha 과소로 동일시하면 안 된다**. 시간에 따라 누적되는
평균 모델 오차는 전 구간 상수 평균을 한 번 뺀 평가에서도 남는다. 이번 측정값은 평가만이며
새 전진 gain·GT 평균 보정으로 제어에 적용하지 않았다.

| 고정 holdout off→on | s1051 (fit1053/54) | s1053 (fit1051/54) | s1054 (fit1051/53) |
|---|---:|---:|---:|
| XY NEES 초과율 |90.26→84.58%|51.03→51.65%|94.70→94.70%|
| 운반 RMSE m |.217977→.218726|.111519→.108627|.215839→.197466|
| POSE_UNCERTAIN 전체 |293→375|200→363|312→328|
| 무경고 XY>25cm |44→40|0→0|0→0|
| 공분산 사용 가능/고정 시점 |493/493|486/486|623/623|
| NEES≤20% /누락0 /RMSE 비악화 |FAIL/FAIL/FAIL|FAIL/PASS/PASS|FAIL/PASS/PASS|

[확인 결과](consistency-result.json): 세fold 모두 미달. 동일1,602시점 NEES1,283→1,258건
(80.09→78.53%), 경고805→1,066, 누락44→40. 후보기본off·번들v133 변경0·신규seed0·물리0.
GT 없는 RGB 잡음 fit은 성립했지만 대상이 큰 옆 펄스뿐이라 주된 전진 편향을 고치지 못했다.
결과를 본 뒤 GT fit이나 다른 문턱으로 갈아타지 않았다. 감독[06:05] 보정용GT 예외는 이번에
사용하지 않았으며, 다음 평균 운동 모델 보정은 별도 근거/사전등록으로 다뤄야 한다.

소스/사전등록899e49b7 → 후보6e18bdb9 → fit봉인/재생97d737e2. 관련11시험 PASS,
off300프레임 pose 직렬화와 입자 궤적 byte 동일, 기존 v133 실행 소스 불변.
재생은 `ugrp_session s2v44-offline-replay`로 종료했고 물리 잠금은 획득하지 않았다.
raw `/Users/changmin/projects/ugrp/outputs/s2-consistency-v44-20261008`에 모든 예측·GT평가·
적합 입력·원본해시를 분리 보존했다. 새 영상 없음, 이전 성공 영상을 재변환하지 않았다.

전달: [수치 검증](consistency-delivery.json), native TensorBoard 새 `1008-s2-consistency-v44`
및 `1008-s2-consistency-diagnosis-v44`에서 원자료/event/live API **112수치 일치**,
v133 source436파일 해시 불변. 진단 HParams가 없는 태그를 참조한 최초2개 변환 오류는
보존하고 메타데이터를 고쳐 별도 snapshot으로 성공시켰다(성공6개 재변환0).
공용 뷰에는 자기 키만 추가, UI 확인은 하지 않았다.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1008-s2-consistency%28-diagnosis%29%3F-v44%2F#timeseries).
결과 문서화 단계의 해당 시험5 PASS, 별도 경로에서 후향 평가기3개의 수치를 재현했다.
잠금 status=null·자기 세션 stopped 확인. GT 보정용 예외 미사용·실시간GT 사용0.

## s2v45 — 전진 이득과 관측 과신 분리 사전등록 (2026-10-08)

[고정 기준](bias-tempering-criteria.json): v44의 **NEES 초과≤20%, 무경고25cm초과0,
운반RMSE 비악화**를 그대로 사용한다. 동일한1602결정/전체1617경고 기회를 유지하고,
새 공분산 누락을 분모에서 빼지 않는다. scale/temper/combined 세 조건을 각2적합/1확인으로
비교하며 결과 후 문턱·α를 바꾸지 않는다. 이전 실패 후보와 성공 v133을 합산하지 않는다.

[Borenstein/Feng UMBmark §3.3 식5·§4](https://www.cs.columbia.edu/~allen/F17/NOTES/borenstein.pdf)는
계통 중심 오차와 비계통 산포를 분리한다. 여기서는 정방형 UMBmark를 수행했다고 주장하지
않고, 기존 펄스 물리 측정에 같은 분리 원칙을 적용한다. **보정용 GT 사용**: 사용자 s2v45와
감독06:05 허용에 따라 적합2녹화의 펄스 실제 dx만 상수 이득으로 적합한다. 실행 중 GT0.
자기 명령의 팔 자세·하중 추론·속도·시간별 독립 상수, 두 적합녹화 모두 존재하고 합계20펄스
이상인 그룹만 허용한다. 팔 전환·겹친 주행·벽 접촉 보정 표본은 제외, 미측정 자세로 전이0.
평균 전진x곡선/끝점만 scale하고 횡방향·yaw·잡음·가드는 유지한다.

[Thrun/Burgard/Fox 원문 §6.3.4 p167, §6.7 p183](https://cs.pomona.edu/~ajc/other/Thrun%20et%20al_2005_Probabilistic%20robotics.pdf)
확인: 인접/반복 관측의 독립 가정 위반을 줄이는 방법으로 `p(z|x)^α`, `α<1`을 명시한다.
원문 방식 그대로 기존 벽×랜드마크 우도를 감쇠한다. **α=0.5는 사전 고정한 반정보 비교값이며
책의 기본값이나 GT 적합값이 아니다.** 관측 후보는 학습상수 없이 각 적합2개에서 ESS·공분산
수축을 진단하고 나머지1개에서 확인한다(α sweep0). scale만 두 녹화로 수치 적합한다.
재샘플링 뒤 ESS=N은 복구 증거가 아니므로 직전 가중 ESS와 직후 고유 표본 수도 함께 기록한다.
새 옵션은 기본off, 원본 모듈/번들436파일을 유지하며 off pose·입자열 바이트 동일성을 검사한다.
미통과면 새 물리0; 통과 조건만 새seed 사전등록 후 잠금하 DEV1회를 허용한다.

### v45 적합 봉인·구현 (holdout 재생 전)

[보정 상수](bias-tempering-fit.json): 양의 전진35·0.10초만 측정됨. holdout1051/1053/1054의
운반 look_ahead 이득0.907038/0.905443/0.905150(n662/689/687), SEARCH 이득
0.927754/0.923195/0.922417(n131/126/59). 운반 적합 오차1.203–1.227mm,
SEARCH0.933–1.002mm로 자세를 합치지 않는다. HIGH/다른속도·후진은 미측정 그대로.
적합에 사용한 GT 경로·SHA와 제외 표본은 raw `s2-bias-tempering-v45-20261008/fit/`.
새 `forward_scale_v1` / `pr_likelihood_half_v1` 옵션은 독립·기본off, PF와 planner가
동일 상수를 쓴다. 검사12개 통과, off300프레임 pose직렬화와 입자열SHA 기존과 동일.

### v45 관측 전후 진단 (세 후보 확인 재생 전)

[감사 결과](bias-tempering-diagnosis.json): 전체105관측 중89회 XY공분산 수축,
62회 관측 직후 NEES 악화. 운반84관측 중73회 수축·52회NEES악화.
1051/1053/1054 운반의 공분산 trace 후/전 중앙값0.772/0.872/0.899,
가중 ESS 중앙값1177/1576/1746(총N2000). 첫관측 ESS는19.78/10.37/10.30,
재샘플링 직후 고유자세67/49/49. 이후 ESS=N은 균등 가중치 때문이며 회복으로 세지 않는다.
벽/랜드마크 log우도의 입자방향 상관 중앙값0.280/0.460/0.320은 정보 중복을 시사하나,
실제 잡음의 상관계수를 측정한 것은 아니다. 공분산 축소가 오차 개선을 과장하는 관측 과신과
초기 입자 손실은 확인됐지만, 원인을 관측 상관 하나로 확정하지 않는다.
원문 감쇠 후보를 비교할 근거가 있어 사전고정α0.5를 진행한다. 세 off20778프레임 모두
pose 직렬화·입자열SHA가 기존과 동일. 이 진단과 후보평가는 GT로 사후 채점만 한다.
