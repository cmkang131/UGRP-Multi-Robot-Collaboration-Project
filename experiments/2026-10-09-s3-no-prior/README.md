# S3 no-prior 연결과 첫 3대 DEV 스모크

계획 고정: `6f675569` (2026-10-09). 사용자/감독 지시 `s3go`. v141 의존 merge는 `eaf02cfe`. 계획을 먼저 커밋한 뒤 단일 스모크를 수행했다. 결과는 아래 10/9 실행 결과에 기록하며 최초 계획·판정 기준은 유지한다.

최신 추가 실행(10/9 s3fix): **v147 / 0a690821** 1회 완료. DEV 가드를 기록 후 진행하여 pair 접근에 진입했고 초기 최선 위치 오차0.026/0.040/0.004m, 인증0/3·B0/2다. 기존 pair 혼합 축 명령과 S2 단일 축 보정 계약 불일치로HOST_ERROR1, 추가 물리 실행0. [고정 seed 재생·전후 표·would_stop·영상](s3fix/README.md) 참조. 앞선 [v146](s3run/README.md#v146-단일-스모크-결과)과 아래 v142 원본 결과는 보존한다.

## 선행 상태와 소스

- S2는 [stage plan](../2026-10-05-scenario-e2e-gap/README.md)의 10/9 사용자 결정으로 조건부 통과다. 감독 전달 수치(v106 prior 있음 5/5 전 구간, 1028 미완; v140 prior 없음 4/4)를 새 성공으로 합산하지 않는다.
- S3 host #394 수정: `408efe8bcdb831e3be3160b40de112b42142bb10`, 로컬 20 passed, 원격 33/33 통과 확인. #399 문 양보 수정: `d3393847f763a9b67db2789de434d47ec7ae1fdc`, 로컬 40 passed(기본 off 동결 바이트 비교 포함), push 완료. #399 첫 원격 재검사에는 shard 7 시간 초과가 남았다. CI 대기 정책은 감독의 최신 지시를 따른다.
- 시작 prior 없는 후보: `codex/s2-realism`의 v140 `e532f52e3df512e5fac8cef7654dc2ba06fa61b1`. 연결 시 회전 피드백·상한을 포함한 후속 `99d81d8c9cbc8dee1cc21462d25a1c81f65de9f5`(s2v59/v141)를 정확한 의존 소스로 고정한다. 진행 중인 s2v59 6개 결과가 나쁘면 다음 S3 실행 전에 재점검한다.
- 기존 #394/#399 후보는 유지하고 새 `codex/s3-no-prior-smoke` 브랜치에서 연결한다. 새 번들/workflow 번호는 main 및 열린 PR 전체를 확인한 뒤 별도 예약하며 v107/v108/v140/v141을 덮어쓰지 않는다.

## 연결 범위와 입력 경계

1. v107의 한 호스트 시계·세 자기 카메라 포트·고정 역할·기존 명령 경로를 재사용한다. 새 옵션을 명시한 구성에서만 prior 없는 위치 제공자와 능동 관측/자기 RGB 실제 회전 상한을 연결한다. 기존 옵션 off 파일/발행 명령/저장 출력의 바이트 비교를 유지한다.
2. 세 로봇 모두 시작 dock 좌표·자기 실제 좌표를 위치 필터에 초기화하지 않는다. 자기 RGB·자기 명령 이력·허용 정적 지도/카메라 보정만 입력한다. 다른 로봇의 위치/영상 공유, 공유 top 카메라, 모델 호출, weld를 사용하지 않는다.
3. #399의 고정 enum 예약/양보 원칙을 재사용한다. 위치 추정 준비 동작과 통로 사용 허가를 구분하며, 상대 위치나 GT로 예약을 해제하지 않는다. 각 로봇은 자기 추정과 자기 명령 종료만 사용한다.
4. 기존 혼합 구성은 r1·r2가 빔 1개→B, r3가 cyan 1개→A다. 이번 B 도착 요구에는 새 공개 주문 구성이 필요하다. 기본 연결 계획은 혼합 구성을 유지하고 cyan 목적지도 B로 지정하는 것이다. 감독이 첫 단독 cyan 3개 스모크를 뜻했다면 실행 전 별도 구성과 단독 예약 순서를 고정한다. 기존 dev_s1lite 주문/배치/성공 판정은 덮어쓰지 않는다.
5. 환경 구성·장면·카메라·접촉은 해당 버전의 표준 Scene/Backend를 재사용하고 차이는 번들에 기록한다. 물리 설정·영상 변환·관측/명령 간격·지도·소스 SHA/해시를 결과와 연결한다. 기존 성공을 새 연결 성공으로 승계하지 않는다.

## 첫 실행 전 고정할 실행 계약

- 횟수: 새 smoke 1회부터. seed/주문/초기 배치/모든 선택 옵션/정확한 source SHA를 구현 뒤 실행 전에 등록한다. 튜닝/확증/기존 S2 코호트와 분리한다.
- 예산: 기존 S3 최대 1800 SIM초, 10800 wall초 이내의 유한 DEV 실행. raw 예산은 실행 전 디스크 검사와 함께 고정하며 여유 공간 10 GiB 미만은 HOST_ERROR로 기록한다.
- 실행: 커밋·push된 자기 worktree에서 표준 sim_cli workflow 어댑터와 ugrp_session을 사용한다. agent_lock은 드라이버 PID로 소유하고 egomap53·s2v59 뒤 감독 순서를 따른다. 잠금 대기는 정상이며 다른 작업의 잠금/프로세스를 건드리지 않는다. nice=0, zsh NO_BG_NICE, nice/renice/taskpolicy 금지.
- 실패: LOCALIZATION_NOT_CONVERGED, DOOR_WAIT/DEADLOCK, COLLISION, PICK/GRASP, DROP/TILT, DELIVERY/PLACEMENT, GO_SYNC, HOST_ERROR(ENOSPC 포함)로 근거와 함께 분류한다. 첫 실패에서 임의 수정/재시도하지 않는다. 같은 원인 2회면 더 실행하지 않고 표준 방법·공개 코드 조사 후 보고한다.

## 평가 및 보고 계약

- 제어 후 `eval_only`에서 로봇별 수렴 시각과 위치 오차, 물체별 B 도착/놓기/안정성, 충돌·교착을 판정한다. 제어 입력에는 평가값을 돌려주지 않는다. 수렴 기준/충돌·교착 창/화물별 배달 기준은 실행 전에 수치·근거를 고정한다.
- r1/r2/r3 각각 성공·실패·미완료와 근거를 보고한다. 혼합 빔 주문이면 r1/r2 공동 결과와 각자의 위치/명령 상태를 구분해 기록하며 단독 배달 3건으로 합산하지 않는다.
- 필수 지표: 실패 원인별 개수, 자기 추정 수렴 시간과 평가 수렴 시간(구분), 문 대기 횟수/robot-seconds, 교착 횟수, wall/SIM, 명령 수·모델 호출0, 대표 영상 경로(4배속).
- 학생 기록·평가 로그·원본/제거 이미지 sha256·명령 궤적을 보존한다. 영상은 평가용이며 제어에 입력하지 않는다. 새 완료 결과는 실패 포함 TensorBoard 새 snapshot으로 변환·실제 로딩/표시를 검증한다.

## 남은 구현 전 확인

기존 pair에도 dock prior가 있음을 확인했다. 새 pair 생성자는 prior 호출 없이 각 로봇의 S2 위치 필터를 그대로 연결한다. 기존 v107/v108 코드와 일반 provider 등록은 수정하지 않는다. 첫 구성은 혼합 빔 1개(r1/r2)와 cyan 1개(r3), 모두 B로 고정했다. 감독이 #399와 #394를 각각 06:35/06:40 UTC에 병합한 원격 상태를 확인했으며 이 작업에서는 병합 명령을 실행하지 않았다.


## v142 실행 계약 및 구현 차이

- 새 `zone-s3-no-prior-v142` / workflow `7.35.0`: main과 열린 PR 전체의 최대 v141/7.34.0을 확인한 뒤 예약. [registration.json](registration.json)에서 **seed 14201 한 번만** 허용한다. 시나리오 카탈로그의 14202/14203은 공통 리더 순환 검증용 비활성 목록이며 추가 실행 허가는 아니다.
- 세 개의 분리된 v141 전역 필터(최대 100000 입자)가 자기 RGB로 초기 능동 pan 관측을 수행한다. 첫 주행 제안까지의 시작 관측은 문 예약 밖에서 수행하며, 그 첫 제안은 발행하지 않는다. r1/r2는 같은 필터·자기 서보 이력을 pair로 이어서 사용하고 r3는 S2 단독 운반을 이어 간다. GT나 peer pose를 필터 초기화에 쓰지 않는다.
- S2의 v7 wheel/카메라/servo stiffness/fine pulse를 재사용하되 모든 로봇이 움직이므로 idle robot freeze는 off다. 기존 pair의 v98 명령/하중 모델은 v7 빔 운반에서 **미검증**이다. 첫 smoke에서 정지/미끄러짐/파지 실패가 나면 해당 차이를 원인 후보로 보존하며 성공을 가정하지 않는다.
- raw 6 GiB, wall 10800 s, SIM 1800 s. 실행 전 최소 16 GiB(예산+10 GiB) 여유 공간, 실행 중 10 GiB 경계와 raw 예산을 검사한다. ENOSPC를 HOST_ERROR로 기록하고 원본을 삭제하지 않는다.
- 수렴은 S2의 자체 σxy≤0.05m를 재사용하고, 사후 정확성은 XY≤0.25m·yaw≤15°를 별도로 판정한다. 문 상태 불변+대기가 이어지고 예약 구간 마지막 120 s 동안 USING 소유자 모두 XY 1cm·yaw 5° 미만 이동일 때 사후 교착 후보로, 음의 robot-robot 접촉 간격을 충돌로 세며 1초 이하 간격은 같은 episode다.
- 실제 로봇 기울기는 기존 S2 한계, 한 번 0.08m 이상 오른 화물이 gripper 해제 명령 없이 0.035m 이하로 내려오면 낙하로 실행만 중단한다. 이 별도 물리 감독은 위치/목적지/행동을 제어기로 반환하지 않는다. 배달은 제어 종료 후 기존 referee로 판정한다.
- 최초 오프라인 검사에서 scenario 1-seed 리더 순환 거부와 pair 생성자 dependency/등록 wrapper 연결 오류를 발견해 수정했다. 물리 smoke 실패로 합산하지 않는다.

## 표준 방법과 확인한 출처

[Active Mobile Robot Localization (Burgard/Fox/Thrun, IJCAI 1997)](https://publications.ri.cmu.edu/storage/publications/pub_files/pub1/burgard_w_1997_1/burgard_w_1997_1.pdf)의 전역 균등 belief 및 기대 불확실성 감소 관측 선택을 구현한 기존 S2 경로를 그대로 사용한다. [OpenCV homography 문서](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html)를 확인했으며 기존 v141 자기 영상 회전 상한을 변경하지 않는다. 문 통행은 #399의 고정 enum 순서를 재사용한다. 새로운 위치 추정 알고리즘이나 GT 기반 보정은 추가하지 않는다.


## s2v59 병행 결과 재점검 (2026-10-09 15:54 KST)

완료 원본 `outputs/s2-realism-99d81d8c-s1065-v141-graduation/result.json`은 STAGE_FAILED, 미들기·미배달이다. 시작 자체 수렴 6.95 s, 그 추정의 사후 XY 오차 0.068 m·yaw 1.20°로 초기 전역 위치 추정 실패는 아니었다. 최종 search, POSE_UNCERTAIN 1003·CYAN_NOT_UNIQUELY_VISIBLE 36, 능동 회전 event 0이며 이후 검색/위치 추정 유지 문제가 남는다. s1066은 사후 배달 성공, s1067/1068은 아직 결과 없음(완료로 합산 금지). S3의 cyan도 P1-1이므로 같은 탐색 실패 위험을 명시한다. S2 전체 졸업으로 승격하지 않고, 예정된 S3 1회는 통합 실패 분류용 DEV로만 유지한다. 결과를 보고 S2/S3 파라미터를 바꾸지 않았다.

오프라인 검증: 첫 연결 후보 `79b01680`에서 변경 시험 23 passed. main `88844767`의 감독 병합 후 변경을 merge하여 연결하고 새 시험을 CI 목록에 등록한다. CI 완료는 기다리지 않고 로컬 통과·push 후 진행한다.


추가 확인: main merge 후보 `0122221a`의 3개 시험 파일은 92 passed. 실제 provider에 합성 자기 프레임을 전달해 초기 관측→pair handoff를 확인한 파일은 6 passed(위치 정확성/물리 성공 검증 아님). 초기 관측 명령 시간을 문 대기 시간에 더하지 않도록 분리했고 같은 6개 시험이 통과했다. [검증 기록](offline-verification.json).

s2v59 완료 4건까지의 추가 재점검: s1067 사후 배달 성공, s1068은 controller done이나 inside B=false(배달 실패), 운반 말기 위치 오차 3.215m다. 아직 S2 졸업 통과가 아니며 S3의 동일 위치 추정 유지/허위 완료 위험을 명시한다. 새 S3 결과와 합산하지 않는다. 단일 통합 DEV smoke 범위는 유지하며 추가 후보 튜닝이나 반복 코호트는 시작하지 않는다.


## 단일 실행 결과 (2026-10-09, v142 seed 14201)

실행 소스 **`6c6571244e33a6e9e39b00afcd38d805035aed7d`**, 계획 `6f675569`.
표준 `sim_cli workflow run zone-s3-no-prior-v142`와 `ugrp_session`으로 한 번 실행했다.
s2v59·선행 속도 측정의 잠금 해제 뒤 PID 31519, nice=0으로 자기 잠금을 취득·해제했다.
시뮬레이션 **1회**, 재시도/튜닝/추가 seed 없음. 원본 상태는 **HOST_ERROR**이며 S3 통과가 아니다.

| 로봇 | 결과 / B 도착 | 자체 σ 수렴 (제어 시작 후) | 정확한 수렴 XY≤0.25m·yaw≤15° | 문 REQUEST / 대기 |
|---|---|---|---|---|
| r1 | LOOK_RECOVERY_EXHAUSTED / 빔 미도착 | 없음 | 없음 (42.25 s 관측) | 1회 / 0.05 robot-s |
| r2 | r1 실패로 미완료 / 공동 빔 미도착 | 12.65 s, 실제 XY **2.057m** 오차 | 없음 | 1회 / 0.05 robot-s |
| r3 | r1 실패로 미완료 / cyan 미도착 | 없음 | 없음 (42.25 s 관측) | 1회 / 33.05 robot-s |

- wall **271.741248 s**, SIM **45.25 s**(제어 42.25 + 정착 3.0), wall/SIM **6.00533**. reset 1.3 SIM초는 분모에서 제외했다. 발행 명령 r1/r2/r3=1060/1182/1114, 총 **3356**(초기/최종 hold 제외), 모델/HTTP 호출 0, 모델 응답시간 합계 0.
- 세 로봇 모두 10.5 SIM초에 초기 관측 단계를 넘었지만 이는 위치 수렴이 아니다. r1의 잘못된 자기 추정에 따른 정적 벽 arm sweep guard가 막혔다. **단일 실행 내부**의 같은 SWEEP_TRANSITION_BLOCKED가 3회(20.55/31.55/42.55 SIM초), 최종 LOOK_RECOVERY_EXHAUSTED 1회(43.55 SIM초)다. 보수적 pair guard가 여전히 정지시키므로 dev_light 통합도 미완료다. 물리 충돌로 분류하지 않는다. 사용자 반복 원인 중단 규칙에 따라 추가 실행을 하지 않는다.
- 실패 개수의 분모를 분리한다: 제어 종료 원인 LOCALIZATION/LOOK 1건, 정확한 수렴 없음 3로봇, HOST_ERROR 원인 **2종**(심판 높이 계약 1건·None 기록 직렬화 1건), 기록 파일 누락 2개, B 미도착 주문 2개. 내부 재시도 3회를 독립 smoke 3회로 세지 않는다.
- robot-robot 음수 접촉 episode **0**, 활성 weld 표본 **0**. 사전 등록 120초 창의 교착 **0건**이나 실행이 그 창보다 짧고 문 통과도 없어서 교착 해소/실제 양보 통과는 미검증이다. r3 예약 대기만 관측했다. 벽/화물 모든 접촉을 포함한 무충돌 판정은 아니다.
- 원래 referee는 빔 z<0을 거부했다(첫 1.35 SIM초, 905/906 표본, 최솟값 -0.000543678m). 원본 높이를 clamp하지 않았다. **별도 eval_only**에서 기존 landing_fits로 B footprint 필요조건을 대조하니 두 화물 모두 906/906 표본에서 B 밖, XY 이동은 사실상 0이다. 완전한 referee 판정은 여전히 무효다.
- student_record/trial 저장은 `harness/zone_pair_executor.py:625`의 `carry_yaw_fallback=None`에 `.get`을 호출하며 같은 원인으로 실패했다. [traceback](record-errors.json)을 보존했다. 새 S3에 연결한 S2 provider의 optional carry 상태와 기존 pair 기록 계약이 맞지 않는다.

### 원본 보존·오프라인 복구

원본: `/Users/changmin/projects/ugrp/outputs/s3-no-prior-6c657124-s14201-v142`.
파생 복구: `/Users/changmin/projects/ugrp/outputs/s3-v142-recovery-6c657124-20261009`.
[결과](summary.json), [재생 검증](replay-verification.json), [파일 해시](postrun-artifacts.json).
원본 2561개 파일 SHA-256을 재확인했다. 저장된 자기 JPEG/발행 명령만 같은 소스에 재생해 각 846프레임·3356명령이 모두 일치했다. GT는 재생 제어기에 입력하지 않고 복구 후 정확성 평가에만 썼다. 이 재생은 MuJoCo 생성/step/렌더 없는 오프라인 계산이며 새 simulation이 아니다. 위치·문 지표는 **원본 학생 기록이 아닌 명령 일치 재생에서 복구한 값**이다.

대표 4배속 영상: `/Users/changmin/projects/ugrp/outputs/s3-v142-recovery-6c657124-20261009/s14201-mixed-4x/execution.mp4`.
[영상 검증](video-verification.json): 212프레임/20fps, 자기 카메라 3개, 원본 4프레임 간격, 전 프레임 재디코딩 통과. 마지막 3초 정착에는 촬영이 없으므로 영상에 포함하지 않는다.
TensorBoard snapshot: `/Users/changmin/projects/ugrp/outputs/tensorboard/1009-s3-v142`.
`outputs/tensorboard-view.json`의 `s3_no_prior_v142_20261009`에 해당 실행·핀·영상 링크를 추가했다. 다른 실행은 수정하지 않았다.

### 선행 S2 최종 재점검과 후속 판단

s2v59 6개는 원본별 사후 배달 **3/6**(1066/1067/1069 성공, 1065 검색 실패, 1068/1070 controller done이나 B 밖)이다. 1067 별도 직렬 재생은 이 6개 분모에 더하지 않는다. 1070은 자체 첫 수렴도 XY0.637m·yaw74.24° 오차였다. S2 조건부 진행 결정은 이력으로 유지하되 **졸업 통과로 승격하지 않는다**. 새 S3의 실패와 함께 전역 위치 가설·추정 유지·단독→pair 관측/가드 연결을 재점검해야 하며 본 결과로 S3 반복 코호트를 시작하지 않는다.

### 표준 방법 조사와 미수정 항목

- [Fox 2001 KLD sampling](https://dada.cs.washington.edu/research/tr/2001/08/UW-CSE-01-08-02.pdf)은 샘플 근사 오차를 다루므로 작은 posterior 분산만으로 실제 위치 정답을 보장하지 않는다. [Nav2 AMCL 공식 문서](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/)의 회복·센서 갱신 설정과 위 능동 위치 추정 논문을 기준으로 모호한 가설을 구별하는 관측을 검토해야 한다. 이 실행 뒤 파라미터를 튜닝하지 않았다.
- [MuJoCo 공식 soft contact 설명](https://mujoco.readthedocs.io/en/stable/computation/index.html#soft-contact-model)은 접촉의 작은 침투를 허용한다. 이번 음수 높이와 strict z≥0 계약 불일치는 별도 호스트 결함이다. 향후 높이 기준점/허용 오차 계약을 명시적으로 버전화해야 하며 사후로 원본을 보정해 성공 처리하지 않는다.
- [Python dict.get 문서](https://docs.python.org/3/library/stdtypes.html#dict.get): 기본값은 키가 없을 때 적용되므로 이미 존재하는 None에는 적용되지 않는다. optional pair 상태의 명시적 None 처리가 필요한 기록 결함으로 분류했다. 기존 frozen pair 파일은 수정하지 않았다.
- 남은 구현 차이: legacy `in_run_drop_tilt_contact_detection=false` 메타데이터는 opt-in backend의 실제 drop/tilt 중단 구현과 불일치한다. 원래 번들/소스를 보존하고 이 한계를 명시한다. 수치가 없는 학생 기록을 일괄 LOCALIZATION으로 세는 기존 평가 helper도 이번 결과에는 사용하지 않았다.

실행 뒤에는 원인 분류·원본 복구·기록만 했으며 제어기/기본 off 경로를 바꾸지 않았다. 실행 직전 변경 모듈 시험 6 passed, 그 앞 main 통합 3개 파일 92 passed. 문서/증거 최종 커밋은 JSON·해시·diff 검사 후 push하며 CI 완료를 기다리지 않는다. 독립 검토/후속 수정 전 PR #416은 draft로 유지한다.

최종 전달 확인: [TensorBoard 검증](tensorboard-verification.json)에서 27개 scalar 재로딩, 성공0·wall271.7412·명령3356·호출0을 대조했다. Chrome 강 프로필에서 새 run/핀7개·HParams 지정4열을 확인했고 S2 6개를 별도 비교한 뒤 S3 화면을 남겼다. 기존 서버는 변경하지 않았다. 영상 등록 및 원본 Range HTTP206도 확인했다.


## 10/9 s3diag — 오프라인 진단 계획과 HOST 계약 수정

감독 지시로 물리 실행은 금지한다. s14201의 원본 RGB·발행 명령만 재생하고 GT는 재생 후 평가/가림 분석에만 쓴다. 비교는 (a) 타 로봇 가림, (b) 시작 위치·yaw 가설 및 단서, (c) 관측 길이·pan 순서, (d) 지도·경기장 동일성을 분리한다. 추가로 영상에서 검출된 바닥 선의 지도 적합도를 확인한다. 문턱은 바꾸지 않으며 동일 입력/난수 기준선을 검증한 뒤 한 요인씩 바꾼다. 반복 물리 실험·CI 완료 대기는 하지 않는다.

HOST_ERROR 수정은 S3 no-prior 어댑터에 한정한다. `SlotTeam`은 S2 provider의 `carry_yaw_fallback=None`을 빈 availability 기록으로 직렬화하고 기존 통계는 보존한다. 평가 높이는 바닥에 놓인 beam의 body 원점(`xpos`) 대신 세계 좌표계 질량중심(`xipos`)을 사용하며 `height_reference=world_body_center_of_mass_v1`을 각 eval 행에 남긴다. 좌표/속도/접촉과 기존 심판 문턱은 그대로다. 음수·비유한 COM은 여전히 거부한다. 과거 원본의 beam roll/pitch/COM은 기록되지 않았으므로 원본 높이에 임의 상수를 더해 심판 완료를 복원하지 않는다.

검증: `python -m pytest -q tests/test_s3_no_prior.py` **8 passed**. 실제 3개 provider 생성, None 기록, 기존 통계 보존, 음수 body 원점/정상 COM의 회귀와 비정상 COM 거부, 기본 off 동결 바이트를 확인했다. 물리 실행은 0회다.

방법 출처: [MuJoCo xipos 정의](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html#mjdata)는 body COM의 세계 위치를 명시한다. [Fox/Burgard/Thrun 1999](https://arxiv.org/abs/1106.0222) 및 [선행 AAAI98 동적 환경 필터](https://www.ri.cmu.edu/pub_files/pub1/fox_dieter_1998_3/fox_dieter_1998_3.pdf)는 지도에 없는 장애물 관측 거부의 근거이며, 타 로봇 가림의 영향이 측정된 경우에만 적용 후보로 사용한다. 영상 마스크의 GT는 진단 oracle일 뿐 제어 입력으로 승격하지 않는다.


완료한 [s3diag 오프라인 원인별 표와 전/후 비교](s3diag/README.md): HOST 두 계약 수정, 전체3356명령 일치·직렬화 오류0, 회귀11 passed. S3의 런타임 v3 마운트 바인딩 누락(20.21mm·2.541°)을 확인했다. 기록 마운트만 맞춘 전체 재생에서 r2/r3 최종 오차0.065/0.074m이나 정확 수렴은 여전히0/3이며, r1 반대-yaw 모드가 남는다. 물리0회·문턱/원본 변경0·CI 대기0. 새 옵션은 기본 off다.

- s3next: [호스트 v3 바인딩/첫 렌더 회귀·장면 점검·수렴 잔여 원인과 재시험 사전 조건](s3next/README.md). 외부 파라미터 합성은 오프라인 진단 전용이고 물리 호스트는 이를 거부한다.
- s3fix6 (10/10): [NaN 복구·공통 PF 후보 3개/저장 4실행 비교·v151 결과](s3fix6/README.md). 변경 시험24 PASS, NaN/None 포함 sweep68건/3192명령/오류0. 후보는 실제 오차 악화로 모두 기각해 off 유지. v151 단일 smoke는 HOST_ERROR0이나 r1/r2 job LOCAL_TIMEOUT, 배송0/2; 초기 점 오차0.026/0.040/0.004m, 최종 r2 오차0.328m/σ0.0055m로 과신 미해결이다. wall3327.431/SIM924.25초(3.600), raw·4배속 영상·TensorBoard 전달 완료, 추가 물리0회.
- s3fix7 (10/10): [문 lease·자기 RGB 정렬·입자 고갈 비교와 v152 결과](s3fix7/README.md). 변경 시험34 PASS, sweep68건/3190명령·대향 문9명령 오류0. PF 후보12재생은 모두 미채택(off). 단일 v152는 r3 문 대기909.05→0.05초·교착0·HOST_ERROR0이나 RGB 정렬915/866회 뒤 hover/집기0, r3 LOCAL_TIMEOUT·배송0/2다. wall3184.674/SIM903.05초(3.527), 후반 위치/yaw 과신 미해결; raw·4배속 영상·TensorBoard 검증 완료, 추가 물리0회.

## s3fix8 단계 probe (2026-10-10)

후속 [s3fix9 관측 제안·정렬 진입 사전 등록](s3fix9/README.md)은100/500/새100의 저장 재생과 실제 align_start를 통과하는 짧은 probe를 분리한다. 결과를 보기 전 선택 규칙을 고정하며, 아래 s3fix8 결과를 새 후보의 증거로 합산하지 않는다.

[전체 기록·프레임 표·입자 조사](s3fix8/README.md): 최종 소스9a57581f, r1/r2 B/N 각60 SIM초에서 hover0, r3 B/N은6.75/7.55 SIM초로 hover→하강→닫기 도달(상승/배송 미검증). 시야 잘림/후퇴 진동으로 새 servo 후보 미채택, 전체 스모크0. 자기 지도55001 입자100→500만 늘리면 >3σ48.55→16.33%, RMSE.308→.277m, CPU1.90배; 한 입력 진단이며 S3 자동 채택 없음.

- [s3fix10 Oracle 단계 probe](s3fix10/README.md): Mac 실행 금지, v154 파생v155 정렬 B/N·r3 상승/운반을 같은 Oracle ARM/OSMesa에서 병렬 진단.
