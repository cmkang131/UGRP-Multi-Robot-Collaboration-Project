# 기본 접근점이 막힌 빔 교사의 지도 핸드오프

기준 `a45645200e13f2bad9fbe882e8c9c15a439457c3`, PR #484.
조정자 결정: ACT 교사 시작은 지도 코드가 넘겨줄 자세다. 정적 지도에 막힌 기본
접근점을 대체 파지 자세로 우회하지 않고 지도 코드에 되돌린다. 대체 후보의 경로·IK
feasible은 물리 파지 검증을 뜻하지 않는다. 이 분포의 새 관문과 과거 넓은 시작 관문은
합산하지 않는다.

## 구현

- `--nominal-blocked-handoff nominal_blocked_handoff_v1`(기본 OFF): 보이는 맡은 끝의
  기본 접근점이 벽·경계 여유에 걸리면 그 관측에서 즉시 `approach_blocked_handoff`.
  READY/pick 전에 검사하며 바퀴 명령은 0이다. `approach_goal_set_v1`은 설정에 남아도
  대체 후보를 고르지 않는다. OFF 비교 코드와 기존 3초 전부 차단 핸드오프는 보존한다.
- 판정은 기존 `sim.grasp_act_goal_set.nominal_goal_blocked`에 `static_map_only=True`를
  주어 재사용한다. 기존 planner의 반경·벽 여유·bounds 검사 그대로이며 화물·동료 점유는
  지도 막힘으로 바꾸지 않는다. 실행 입력은 VisibleWorld의 보이는 맡은 색 띠, 기억 중인
  보이는 벽, 자기 발행 명령 자세다. 숨은 위치·접촉·성공 정답을 전달하지 않는다.
- `--start-nominal-goal-feasible start_nominal_goal_feasible_v1`(기본 OFF): 시작 생성 시
  같은 함수로 두 맡은 끝의 기본 목표를 검사한다. 초기 배치와 정적 지도는 생성에만 쓰며
  교사 입력으로 전달하지 않는다. 전체 원래 계획과 신규 제안의 거절 수·분모·비율을
  `nominal_goal_filter`에, 에피소드별 거절 수를 계획에 남긴다.
- 새 토글을 자식 CLI·결과·관문·속도 재사용·기록모드 인수에 연결했다. 서로 다른 토글의
  속도/기록 인수는 거부한다. 깨끗한 인계는 실패 감독기에서 제외하지만 물리 성공으로
  세지 않고 완료 분모에 남긴다.

## 검증

관련 3파일 **134 passed** (`test_grasp_act_goal_set.py`, `test_grasp_act_batch.py`,
`test_grasp_act_search.py`). episode-030 허용 관측 반례는 접근·정렬·READY·탐색에서
즉시 인계하고 대체 후보 함수를 호출하지 않는다. 정상 시작의 고정 19개 판단도 유지한다.

[전체 재생 기록](nominal-handoff-replay.json): GCP a4564520 진단의 정상 시작 **6/6**,
두 로봇의 **4,664개 명령·phase·done**이 해당 기준 소스의 오프라인 재생과 정확히 같다.
저장 GCP 명령의 time/wheels/PWM/phase/done도 정확히 같고 pulse duration의 Mac/libm
차이는 최대 **1.8042e-16초**(허용 1e-12초)다. 원본 35파일과 압축 해제 해시를 확인했다.
어려운 index6(seed79030, episode-030 계열)는 **3.6 SIM초**에 r1
`approach_blocked_handoff`, r2 `peer_approach_handoff`로 끝난다. 실제 발행 바퀴 0,
집게 열림, 대체 후보·pick 없음. 이는 저장 입력 재생이며 새 물리 결과는 아니다.
새 영상 열람은 0프레임이며 조정자의 기존 영상 관찰을 독립 재검증으로 보고하지 않는다.

[새 계획](teacher-nominal-gate-plan.json): 미사용 실행 기록을 확인한 **86000–86039**를
같은 정적 조건으로 다시 뽑았다. 원래 40개 중 **1/40(2.5%)**, seed86004의 r2 목표가
막혀 거절됐다. 신규 생성에서 nominal 검사 41제안 중 1개 거절(2.439%), 모든 기존
필터를 포함한 전체 제안105개, 채택40개다. 원래 통과39개의 배치·spawn은 같다.
기존 frozen 계획은 덮어쓰지 않았다. [시드 점검](nominal-handoff-seeds.json)은 최신 fetch의
main/열린 PR 18 refs와 회수된 grasp-search 실행 계획, 조정자 미제출 보고를 확인했다.
실제 admission 직전에 운영자가 예약을 다시 확인한다.

## 다음 실행

새 SHA 대기열: 같은 진단7(정상 **6/6 물리 성공**, 어려운1은 **깨끗한
approach_blocked_handoff**) → 같은 GCP n4-highcpu-64 동시16 속도30 SIM초
(중앙 wall/SIM≤3.5) → 새 분포40회(**성공≥38/40**). 핸드오프 수·비율·인덱스와
성공 n/40, HOST_ERROR·중단·미시작을 따로 보고한다. 모든 payload에서
`--failure-stop-scope repeated_cause_v1`을 켜고 단계별 실제 통과 뒤에만 다음을 제출한다.
`ready=true`는 진단 제출 준비다. a4564520 대기열은 superseded로 바꾼다.
Mac 시뮬레이션·렌더·모델 호출·원격 제출/감시는 모두 0회다. 운영자 GCP 재검증은 남아 있다.

참고: [MoveIt Task Constructor의 접근 연결·후보 생성·IK 단계](https://moveit.github.io/moveit_task_constructor/tutorials/pick-and-place.html)를 다시 확인했다.
접근 경로와 파지 후보의 유효성을 구분하는 기존 설계의 근거이며, 이번의 기본 자세
분포·지도 핸드오프 결정은 사용자 지시다. 새로운 계획기나 고정 장치를 도입하지 않는다.
