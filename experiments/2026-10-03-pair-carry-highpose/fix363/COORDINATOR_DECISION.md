# PR #363 결정 기록: P03 cap, 첫 E2E 집게 감시 범위, 작업 제한, DEV_PILOT

2026-10-03. REVIEW_363 2차 BLOCK 대응. 이 문서는 v96 번들의 출처 파일에 포함되어 해시로 묶인다
(`harness/zone_pair_highpose_contract.py`의 `CAP_DECISION`).

## 1. P03 사례 cap: 3×120 → 3×300 SIM초 (사전 등록 개정 v96-cap-2)

**결정 시점:** P03 자료가 하나도 없을 때 미리 정했다. 이 제어기로는 P03·stage probe·코호트를
한 번도 실행하지 않았다. `configs/zone_pair_highpose_v96.json`의 `case_cap`에
`decided_before_p03_data: true`로 기록하고, 번들 등록 검사(registry)가 이 값을 확인한다.

**유도:** 사례마다 피할 수 없는 최소 소요 시간(하한, lower bound)을 실제 제어기 상수로 계산했다
([생성기](time_lower_bounds.py), [결과](time_lower_bounds.json)). 회전·우회·barrier 대기·추가 탐색·
재접근·서보 지연은 0으로 센다. 그래서 하한은 "이보다 빨리 끝날 수 없다"는 바닥이지 완주 예측이 아니다.

| 지도 / 사례 | 거리 m | 하한 s | 120초 cap | 300초 cap |
|---|---:|---:|---|---|
| door_v3 / before_door | 0.452 | 63.83 | 가능 | 가능 |
| door_v3 / after_door | 1.948 | 104.17 | 가능 | 가능 |
| door_v3 / before_destination | 4.924 | 184.57 | **불가** | 가능 |
| door_v3 전체 운반 | 5.75 | 219.34 | 불가 | 가능 |
| two_doors_v3 전체 운반 | 5.75 | 219.34 | 불가 | 가능 |
| corridor_v3 전체 운반 | 4.471 | 190.44 | 불가 | 가능 |

전체 운반 하한 190–219초는 대부분 운반 이동 시간(거리 ÷ 등록 운반 속도 0.06 m/s)이다.
300초는 가장 큰 하한 219.34초의 약 1.37배다. 하한에 0으로 센 대기·지연을 덮을 여유를 주되,
제한이 사실상 없어지지 않을 만큼만 늘렸다. 이전 120초는 v88 학생 실행기에서 물려받은 값이었고
(`scripts/run_final_pair_v3.py`의 고정값), 중간 체크포인트를 HIGH로 유지하는 v96 운반에는 원리적으로
맞지 않았다(before_destination은 상승·정렬을 0으로 해도 121.87초).

**코드:** v96 학생 실행기(`scripts/run_pair_highpose.py`의 `student_run_case`)가
`contract.CASE_CAP_S = 300`을 쓴다. 세 사례(before_door, after_door, before_destination)를 모두
실행 대상으로 계획하며, 하한이 cap을 넘으면 `TIME_LOWER_BOUND_EXCEEDS_CASE_CAP`로 실행 전에 거부한다.
실측 지연(lag)이 승인되면 하한에 더해져 더 엄격해질 수 있다.

### 1a. 사전 등록 개정 v98-cap-3: 3×300 → 3×900 SIM초 (2026-10-04, P03 실행 전)

**결정:** 사용자(2026-10-04) "시간 상한도 늘리셈". 조정자가 v98 사례 cap을 900 SIM초로 정했다(모든 집행기 같은 값).
v98 전용이다. 은퇴한 v96 등록 파일(`configs/zone_pair_highpose_v96.json`)은 바이트 그대로 300초다.

**결정 시점:** v98로 P03을 한 번도 실행하지 않았다(지금까지 v98 실행은 DEV 단계 검사뿐이고, 결과는 SHA로 구분해 기록한다).
등록 파일 `case_cap`에 `prereg_version: v98-cap-3`, `decided_before_p03_data: true`, 사용자 말을 기록했다.

**유도:** 사용자 정정(2026-10-04 "끝까지 옮기는 게 E2E지. 짐작해서 가는 게 맞아. 근데 어느정도 모르겠으면, 짐을 두고 주변을
둘러보면 되는 거잖아")에 따라 E2E는 배달까지의 전체 경로다. 운반은 추측 항법(dead reckoning)으로 가고, σ가 예산을 넘으면
(`HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED`) 짐을 내려놓고 둘러본 뒤 다시 든다. 이 재고정을 넣은 전체 경로는 351–517초로
추정된다(재고정 1회 하한 약 41.4초, 오프라인 DR 예산 분석). 900초는 위 추정의 약 1.75배로, 재고정·재둘러보기가 더 생길 여유를
둔다. **목표가 아니라 DEV 상한이다.** 하한 자동 검사(`TIME_LOWER_BOUND_EXCEEDS_CASE_CAP`)는 그대로다.

**코드(v98만):** `contract.CASE_CAP_S = 900`(`CAP_PREREG_VERSION = 'v98-cap-3'`); 같은 값을 쓰는 집행기 작업 제한
(`Runtime`·`StagedRuntime`의 `job_sim_limit_s`, 번들 `timing.executor_job_sim_limit_s`); 단계 검사 `align_to_carry` cap
300 → 900; 등록 파일 `configs/zone_pair_highpose_v98.json`의 `case_cap`; 작업 흐름 설명(3×900). 기록 전용 경계 맞춤 행 상한
`FIT_ROWS_MAX` 5000 → 15000(900초에서 잘리지 않게). 다른 단계 검사 cap(150·60초)은 바꾸지 않았다.

## 2. 집게 감시(grip monitor): 첫 E2E에서는 기록만 한다 (리뷰 P1-4)

### 사용자 결정

1. 사용자(2026-10-03): "상대가 놓치면, 놓쳤다고 신호를 보내면 되잖아 llm을 통하던지 실험 조건에 따라서"
   → 각 로봇은 **자기 카메라로 자기 집게만** 감시하고, 놓치면 실험 조건의 통신 경로로 상대에게 알린다.
2. 사용자(2026-10-03 약 19:20): "ㅇㅇ 그렇게 하자"
   → 첫 E2E 범위를 줄인다. **v96은 집게 감시를 기록만 하고(log-only), 어떤 단계도 막거나 중단하지 않는다.**
   1번의 자기 집게 감지·상대 신호·사건 기록은 첫 E2E 뒤로 미룬다.

따라서 리뷰 P1-4는 감시기를 고쳐서가 아니라 **사용자의 명시적 범위 결정(log-only)**으로 해소한다.

### v96에서 실제로 하는 것

- **진행·barrier 준비 판단:** 자기 명령 이력(이번 파지 회차에 집게 닫힘 명령을 냈고 지금도 닫힘 명령 상태,
  큐에 넣은 자세 경로를 다 진행함)과 기존 고정 열거형 상대 상태(`zone_pair_status_v5`)만 쓴다.
  정답 좌표·측정 관절·접촉 판정은 쓰지 않는다.
- **남은 중단(abort) 경로 (영상 판단 아님):** 자기 명령 불일치(`TRANSIT_COMMAND_DESYNC`,
  `TRANSIT_GRIP_OPEN_COMMAND`), 상대 상태 불일치(`TRANSIT_PARTNER_DESYNC`), 상대 abort 수신
  (`PARTNER_ABORT`), 체크포인트 위치 재확인 시간 초과(`HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`, 내비게이션용 재관측이라 유지),
  명령 자세 불일치(`HIGH_POSE_NOT_COMMANDED`, `FLOOR_POSE_NOT_COMMANDED`).
- **기록만 하는 값:** 낮은 들기 동시 움직임 IoU(옛 `LOAD_NOT_HELD_AFTER_LIFT`), 이동 중 `relation()`·화면 안정도·
  프레임 신선도, HIGH 가장자리 선과 기준 마스크, 운반·체크포인트 유지 IoU(옛 `LOAD_CHANGED_IN_CARRY`,
  `HIGH_CHECKPOINT_GRIP_CHANGED`), 바닥 복귀 IoU(옛 `FLOOR_RETURN_GRIP_CHANGED`).
  값은 쓰기 전용 기록기(`GripMonitorLog`)에 쌓이고 평가 출력의 `grip_monitor`로만 나간다. 제어기는 읽지 않는다.
- **바뀌지 않은 파지 시점 검사:** `GRIP_NOT_CONFIRMED`(닫힘 명령 + 새 프레임)와 `GRIP_NOT_SEEN`(닫은 뒤 자기 집게 영상,
  v88/v92부터 쓰던 검사)은 그대로 둔다. `relation()`/`hold_state`가 아니라 파지 성립 검사라서다.
  이것도 기록 전용으로 바꿔야 한다면 별도 결정이 필요하다.
- **결과 판정:** 성공 여부는 예전처럼 별도 평가 출력으로만 판단한다. **이 버전의 제어기는 집게 놓침을 감시하지 않으므로,
  빔을 떨어뜨려도 실행 중에 감지하거나 상대에게 알리지 않는다.**

### 근거 (기록 전용으로 둔 이유)

실제 렌더 영상(floor_light_v1, 렌더러 켬, 제어기 없음, 시드 911)에서 측정했다
([점수 스크립트](relation_zero_check.py), [결과](relation_zero_check.json)).

| 조건 / 로봇 / 구간 | relation() 통과 | 비고 |
|---|---:|---|
| 정상 r1 / HIGH | 13/13 | coverage 0.657, 기준 0.65를 겨우 넘김 |
| 정상 r2 / HIGH | 13/13 | coverage 0.681 |
| 정상 r1·r2 / 상승 | 9/35, 14/35 | 정상인데 대부분 실패 |
| 정상 r1·r2 / 하강 | 3/28, 4/28 | 정상인데 대부분 실패 |
| r2 집게 열림 / r2 HIGH | 0/13 | 자기 놓침은 잡음 |
| r2 집게 열림 / r1 HIGH | 13/13 | 상대가 놓쳤는데 통과(거짓 정상) |

또 바닥 파지 자세의 손목 카메라에는 빔이 보이지 않는다(모든 조건에서 `hold_view_mask` 0픽셀). 옛 바닥 복귀 검사는
이 상태에서 정상 하강도 항상 거부했을 것이다(테스트
`test_recorded_nominal_run_releases_with_command_history_readiness`가 기록값으로 확인).

### 미룬 작업 (첫 E2E 뒤)

1. 각 로봇이 자기 카메라로 자기 집게 놓침을 감지한다. 상대 놓침은 영상으로 판단하지 않는다.
2. 놓치면 조건별 통로로 알린다. 자연어 조건은 LLM 메시지, 구조화 조건은 기존 고정 상태 채널을 쓴다
   (값 추가가 필요할 때만 추가하고 버전을 올린다). 무통신 조건에서는 상대가 이 메시지를 받지 않는다는 점을 명시한다.
   - **충돌 주의:** 현재 `zone_pair_status_v5`는 "네 통신 조건 모두 같음"으로 정의되어 무통신 조건에도 abort 상태가 간다.
     미룬 작업에서 무통신 조건의 처리와 이 계약을 함께 정해야 한다.
   - 자연어 조건의 대화 계층은 v96 범위 밖이다.
3. 상대는 받은 메시지 내용만으로 멈춤·유지·안전 중단한다.
4. 평가·감사 출력에만 남긴다: 자기 놓침 감지 시각, 메시지 발신 시각과 통로, 상대 수신 시각, 상대 반응 시각, 최종 결과.
5. 참고용 탐색 결과(연결하지 않음): 자기 HIGH 기준 영상과의 마스크 정규화 상관(masked ZNCC)과 ECC 이동량.
   제어기 대기 구간(상승 큐 끝 2초 + 최대 3초)에서 정상 3시드·2초 지연은 오탐 0, r2 자기 집게 열림은 10/10 감지
   (집게 열림 12초 → 첫 감지 25.5초). 시드 912/913은 911과 거의 같은 영상이라 독립 증거로 약하다
   ([deferred_own_grip/own_grip_eval.json](deferred_own_grip/own_grip_eval.json)). 이 수치는 HIGH 정착 시간 8초에 기대므로,
   정착 시간을 줄이면 다시 검증해야 한다. 운반 중(차체 이동) 영상은 아직 없다.

## 3. 집행기 작업 제한(job_sim_limit_s) 120 → 300초

(2026-10-04 v98-cap-3: 같은 정렬 규칙으로 900초가 된다. 1a절.)

부모 실행기(`harness/zone_final_pair_runtime.py:36`)는 모든 로봇 집행기에 `job_sim_limit_s=120.`을 고정으로 넣는다.
v96은 이 부모 생성자를 그대로 써서 120초를 물려받았고, 그대로면 `expire_if_due`가 120 SIM초에 공동 작업을
`LOCAL_TIMEOUT`으로 끝낸다(하한 184.6초·190–219초와 모순). v96 `Runtime`이 부모 생성 직후, 작업이 생기기 전에
모든 집행기 제한을 `CASE_CAP_S = 300`으로 맞춘다. 값은 번들 `timing.executor_job_sim_limit_s`(번들 hash에 포함)와
실행 기록 `executor_job_sim_limit_s`에 남는다. 테스트: 가장 큰 하한(219.34초)과 300초 시점에는 만료되지 않고
300.1초에 만료된다(`tests/test_highpose_dev_pilot.py::test_runtime_job_limit_matches_case_cap_under_dev_pilot`).

## 4. DEV_PILOT 입장 경로 (코디네이터 결정 2026-10-03)

v92 조립이 PARTIAL(77/108)이라 MEASURED_SIM 승인 목록은 비어 있고 그 경로는 바꾸지 않았다. 비확증 기능 시험을 위해
별도 경로를 추가했다.

- **입장:** `configs/zone_pair_highpose_v96.json`의 `dev_pilot.admitted_calibration_sha256`에 있는 **정확한 sha256 하나**만 받는다.
  현재 `398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5`
  (`/Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/result/calibration_dev_pilot.json`, PR #369).
  CLI는 `--admission dev-pilot`을 명시해야 한다. 없으면 MEASURED_SIM 경로로 가서 거부된다.
- **파일 요구(검사기 `dev_pilot_calibration`):** v92 로더 v2 구조(schema·계약·지도·loaded/fine 운동·pair 모델·카메라·pan),
  `status: DEV_PILOT`, `dev_rule: DEV_PILOT_C0_ZERO_v1`, `confirmatory: false`, `params.motion_loaded.deadband.c0 == [0,0,0]`,
  `u1 > 0`, 옆 파일 `input_manifest_dev.json`(schema `ugrp.v92_dev_pilot_inputs.v1`, 깨끗한 작업 트리, 같은 source SHA, 스크립트 hash)과
  `dev_manifest_sha256` 일치, `measured_parent.status == PARTIAL`. `missing`은 아래 10개 무적재 필드만 허용한다.
  구조 검사는 바꾸지 않은 v92 로더를 status만 바꾼 복사본에 돌린다. 측정 출처 칸에는 DEV 매니페스트·스크립트 hash를 넣는다(지어낸 값 없음).
- **무적재 운동 10개 필드(`params.motion.*`):** 승인된 무적재 3축 프로필이 없다.
  - 선택지 1(r4/r5 축별 정지 시간 상수 0.0890/0.0885/0.0374초)은 쓸 수 없다. `harness/owncam_localizer.py` `predict_to`의
    정지 시간 상수가 스칼라(`math.exp`)라 축별 값을 받지 못한다.
  - 선택지 2의 전제(main의 v88 실행기가 쓰는 무적재 프로필)는 성립하지 않는다. 가장 최근 고정된 v88 보정
    (`7ad491338ef32dc94c6a73bc4e02f50f92a1324c48ab083ab02194d342c40843`)도 PARTIAL이고 `params.motion`이 전부 null이다.
  - 그래서 **실행 코드가 실측값이 없을 때 쓰는 고정 기본값**을 DEV로 표시해 쓴다. 출처는 `harness/owncam_localizer.py`
    `DEFAULT_PARAMS["motion"]`(파일 sha256 `9793f74b008b96d4b6659a5251bde7374c697ac7d4bbb23758d5433098402347`)이다.
    `tau_stop_s`는 예측기가 값이 없을 때 쓰는 것과 같은 `tau_s`(0.12초)로 채운다. `tau_axis_s`·`use_scale`·`rest_noise`는 넣지 않아
    코드 기본값(스칼라 상승 지연, True, True)이 쓰인다. null을 그대로 두면 `use_scale`·`rest_noise`가 꺼지므로 지운다.
    축 정지 시간 상수를 평균 내지 않았다.
  - 등록값은 `dev_pilot.unloaded_motion_fill`, 실행 번들 `dev_pilot_unloaded_motion_fill`, 보정 반환값 `dev_pilot_fill`에 출처·hash와 함께 남는다.
  - P03은 dock에서 짐 없이 출발하므로 무적재 운동을 실제로 쓴다(필드를 비워 둘 수 없다). 코디네이터가 다른 값을 원하면
    이 등록 블록만 바꾸면 된다(번들 hash가 바뀐다).
- **결과 표시:** 모든 사례 결과·체크포인트 기록·묶음 결과에 `admission_mode: DEV_PILOT`, `run_status: FUNCTIONAL_DEV`,
  `cohort_role: DEV_PILOT_FUNCTIONAL_DEV`, `tensorboard_cohort: v96-dev-pilot-functional`, `confirmation_sample: false`,
  `promotable: false`, `measured_sim_evidence: false`가 붙는다.
- **승격 불가:** 확증 진입 `harness/zone_pair_highpose_starts.qualify_run`은 먼저 `contract.require_promotable`을 부른다.
  DEV 표시가 하나라도 있으면(묶음 안 사례·체크포인트까지) `DEV_PILOT_RESULT_NOT_PROMOTABLE`로 거부한다.
  DEV 파일 sha를 MEASURED_SIM 승인 목록에 넣어도 v92 로더가 status로 거부하고, DEV 번들의 표시를 지워 다시 실행해도 번들·보정 검사에서 거부된다(테스트).
- **전체 무렌더 재생 테스트:** `test_headless_nominal_replay_with_c0_zero_carry_leg`. 리뷰어 정상 일정(상승·HIGH·하강·열기)을
  무렌더 MuJoCo로 돌리고 HIGH 유지 중 4초 운반 구간을 넣는다. 운반 명령은 DEV 보정의 `motor_command`(c0 = 0)로 만들고
  `validate_raw_action`을 통과해야 하며, 같은 자기 명령을 실제 HIGH 위치 추정기(PF, c0 = 0 데드밴드)에 넣어 적재 중·해제 뒤 추정이 유한한지 본다.
  두 로봇 모두 5 cm 넘게 움직였다(평가 전용). 이 재생은 렌더가 없어 자기 영상 정렬·파지와 Runtime/Team 전체 연결은 확인하지 않는다.
  집게 검사가 진행을 막지 않음은 실제 렌더 영상 테스트(`tests/test_highpose_transit.py`)가 맡는다. 실행 시간은 약 100초.
- **번들 번호:** 이 경로를 쓴 실행 기록이 아직 없어 v96을 유지하고 번들 hash만 갱신한다.

## 5. 기술 층 인터페이스 (나중에 LLM 결정 층이 도구로 부를 부분, 이번에는 만들지 않음)

C-규칙 기준선은 이 제어기다. LLM 층은 별도 작업이며 아래 경계만 문서로 고정한다.

| 단계(state) | 상대에게 보내는 고정 상태 | 다음으로 가는 조건 | 실패 사유(예) |
|---|---|---|---|
| `align` / `align_start` | `aligning` | 자기 영상 정렬 | `ALIGN_TIMEOUT` |
| `grasp` / `wait_lift` | `ready` | 닫힘 명령 + 집게 영상, lift barrier GO | `GRIP_NOT_CONFIRMED`, `GRIP_NOT_SEEN`, `BARRIER_LIFT_*` |
| `lift`(낮은 들기 → HIGH 상승) | `lift` | 자기 명령 경로 완료 + 상대 상태 `lift` | `TRANSIT_COMMAND_DESYNC`, `TRANSIT_PARTNER_DESYNC`, `HIGH_POSE_NOT_COMMANDED` |
| `wait_carry` | `lift` | carry barrier GO(준비 = 자기 명령 이력), 체크포인트 재관측 | `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`, `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT` |
| `carry` | `carry` | 정해진 leg 명령 끝 | (집게 검사로는 중단 안 함) |
| `wait_lower` | `carry` | lower barrier GO: 중간이면 HIGH 정지 체크포인트, 마지막이면 하강 | `BARRIER_LOWER_*` |
| `lower` / `wait_open` | `put_down` | 자기 명령 하강 완료, open barrier GO | `FLOOR_POSE_NOT_COMMANDED`, `FINAL_FLOOR_RELEASE_REQUIRED` |
| `failed` | `abort` | 상대는 `abort`를 받으면 멈추고 `PARTNER_ABORT`로 끝냄 | |

- 상태 채널은 `zone_pair_status_v5`(고정 열거형, 자유 텍스트 없음). barrier 보고는 `report(key, obs, now, ready, reason)`.
- 집게 감시값은 `grip_monitor`(평가 출력)에만 있고 제어 입력이 아니다.

## 6. 참고 자료 (조사 요약, 2026-10-03)

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
