# egomap63 — 자기 B 준비 + 6 seed 병렬 비교 (DEV)

## 실행 전 등록 (2026-10-10)

사용자 지시: 유효 seed60012 하나는 판단 불가. 새 seed **63001–63006** 각 1회 준비(150 SIM초), 유효한 자기 B checkpoint 전부 × baseline/a500/b/c를 각120 SIM초(기존 B접근60 + 진단 귀환60) 실행한다. 준비와 비교를 각각 한 묶음으로 제출한다. 모든 조건은 같은 seed의 같은 checkpoint/SHA에서 분기한다. oracle-x86만 사용하며 동시10개, MemAvailable 6GiB 미만은 대기 후 동일 작업 재입장. Mac 물리/녹화 재생/모델 호출0. 새 seed는 초기 위치 2종(기존 홀/짝 P1 배치)이며 6종 경기장이 아니다.

고정 조건: tape/SEARCH/강성real_v1/rotL/egomap27_wide/heading 공통 계약/기존 검출·정합 문턱. 새 `goal_preemption=nav2_goal_updated_v1`을 준비 및 모든 비교에 동일 적용. 기본 off는 원래 경로/출력 그대로. 준비 중 실패는 제외하지 않고 6회 분모, 해당 비교4슬롯은 차단으로 기록한다. HOST_ERROR/호스트 중단도 전체24슬롯 및 실행 시도 분모에 별도 표시한다. 결과 후 seed 교체·문턱 변경·준비 재시도0.

비교 옵션: baseline100 / a `particles_500_v1` / b `cartographer_window_v1`(±.1m/±20°) / c `observed_sample_v1`. b 실행 전 합성 시험에서 실제 호출과 탐색 후보 수 차이를 확인하고, 실행별 실제 호출 수·검색창·잘린 지도점·후보 수를 기록한다. 동일 posterior는 옵션 미적용과 구분한다. 원래 egomap60 통과값(과신율 상대10% 감소, 끝오차≤기준1.2배, B/귀환 열세 없음, 거짓선언0, 접촉증가 없음)을 바꾸지 않는다. 이번은 모든 유효 seed를 보고하고 최소2 유효 쌍 필요. 이후 전체 경로 물리는 이번 지시에 없으므로 실행하지 않는다.

보고 분모: 조건당 등록6, 준비 유효 n/6, 실제 단계 n/6, 프레임 >3σ n/N 및 끝시점 >3σ n/N, 종료 오차 중앙/최대, B/귀환 n/6, 접촉·거짓선언 건수. 프레임은 독립 반복이 아니다. 지도 P/R과 실제 경로1m 영역의 GT벽 표본/전체349 및 점유칸 수도 병기한다. 60초 귀환 실패를270초 전체 임무 실패로 확대하지 않는다.

예상: 준비6개 동시5–12분 + 유효 최대24단계 max10 대기열 약20–40분. 한 시간 진전 없으면 보고. 완료 결과 모두 회수/해시검증, README 및 새로운 TensorBoard snapshot, push 후 CI 대기0/PR405 DRAFT.

## 수정 전 진단 / 최소 수정

60011의 저장 own 로그741프레임 중 sensor_sweep432(58.3%), B 검출94프레임 중86(91.5%)도 sweep. 94개 중93개 회전명령, 전진1개; 누적49후보/최대8관측, 확정0. B 외형이 전혀 없는 것이 아니라 **자기 B 후보 접근목표가 회전 상태에 선점되지 못함**이다. `CycleNavigator.update`는 static_goal을 검사하기 전에 sweep을 반환하고, `PublicRecoveryNavigator.update`는 target이 이미 있으면 새 static_goal로 바꾸지 않는다. detector 문턱/150초 예산은 변경하지 않는다.

옵션은 Nav2의 새 목표가 recovery를 중단하고 다시 계획하는 규칙을 이 두 어댑터 경계에 적용한다. 자신의 현재 RGB가 만든 기존 .12m 확인 접근목표만 사용하며 후보를 확인된 B로 승격하지 않는다. 확인은 기존 v3의3관측/2초/.05m/시간·면적·연결성 기준 그대로다. 새 목표 없을 때 탐색/회복은 원래 규칙으로 복귀한다.

## 참고 자료 (원문 확인)

- [Nav2 BT XML](https://github.com/ros-navigation/navigation2/blob/main/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml), lines46–59: `ReactiveFallback/GoalUpdated`가 실행 중 recovery를 선점한다. Apache-2.0. 우리 adaptation: ROS action 대신 자기 RGB 후보의 기존 접근 waypoint를 새 목표로 전달, 초기 카메라 sweep도 중단 가능. 이동/검출 문턱 변경 없음.
- [explore_lite explore.cpp](https://github.com/hrnr/m-explore/blob/noetic-devel/explore/src/explore.cpp), lines198–228: 동일 목표 유지, 새 목표는 move_base action 제출. BSD-3-Clause. 기존 frontier 크기/비용/블랙리스트 유지.
- [Cartographer real_time_correlative_scan_matcher_2d.cc](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/scan_matching/real_time_correlative_scan_matcher_2d.cc), lines119–136: 설정한 탐색창으로 후보 생성·채점. Apache-2.0. b는 기존 egomap60 구현/값 그대로, 호출 계측만 추가한다.

## 결과

미실행. egomap60(유효1/2)의 수치를 새6seed 결과로 합산하지 않는다.

### 고정 제출 목록/명령

러너: `python -m scripts.run_own_route_particle_round --mode batch --output outputs/egomap63-batch/data`.
준비명: `egomap63-prepare-{63001,63002,63003,63004,63005,63006}`; 명령은 같은 모듈의 `--mode prepare --seed S --profile baseline --output .../prepare-S`.
비교명: `egomap63-stage-S-{baseline,a,b,c}`(S는 위6개 전부); `--mode stage --seed S --profile P --checkpoint .../prepare-S/checkpoints/<own-B-file> --output .../stage-S-P`.
전체30슬롯 `batch-plan.json`을 제출 시작에 저장하고, 준비6개 모두 종료 후 유효 seed의 모든 비교 명령을 `paired-plan.json`에 고정한 다음 max10 pool로 실행한다. 6GiB 미만은 제출 전 대기하며 조건/명령 변경 없음.
스모크 필요 시 `--mode smoke --seed 63001 --output outputs/egomap63-smoke/data` 4초 저장+4초 복원(리셋 포함 기존9.3초) 한 번만. 시간 trigger이며 자기B 관측 성공으로 세지 않는다.
