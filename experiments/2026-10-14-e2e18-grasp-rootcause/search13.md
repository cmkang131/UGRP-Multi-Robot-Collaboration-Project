# search13 — 진행·일시 점유·시야 상실을 분리한 교사 복구

2026-10-15, PR #484. 부모/A 원본 SHA `c3d700e5d44a50a2e7044fc3eeef2e2124486f93`.
실행 SHA는 새 `outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<SHA8>.json`에 고정한다.
기반은 A: `approach_coordination=off`, `handoff_observation=visible_handoff_v1`, 나머지는
86367b4b 프로필이다. **새 GCP 물리 결과는 0/0, NOT_STARTED**다.
Mac에서는 저장 입력 재생·경로 계산·기존 JPEG 열람만 했다. 물리·새 렌더·원격 접속·모델 호출은 없다.

## 원본 확인과 운영 요약 정정

[전체 26개 결과·원본 해시·판정](search13-summary.json), [프레임 열람 기록](search13-frame-review.json),
[저장 입력 재생](search13-replay.json). A/B 각각 완료13/13, 성공6/13, 정상6/6,
옛 실패0/6, hard0/1, approach handoff6/13, timeout1/13, HOST_ERROR/중단0이다.
A의 계획·결과·두 교사 원장·평가 원장 해시와 압축 해제 해시를 검증하고 **7,254/7,254 저장 명령**을 재현했다.
B는 13개 결과 파일의 해시·분모·입력 감사를 확인했으며 B 명령 재생을 했다는 뜻은 아니다.

실패6개는 진단 idx7–12, 옛 관문 idx3/7/8/14/17/32다. 아래 시각은 초기 안정화 뒤 경과 SIM초다.
마지막3초의 수치이며, 정답 실제 변위는 **평가 전용으로 별도 계산**했다. 제어 입력에는 전달하지 않는다.
`목표 거리`는 자기 발행 좌표계의 관측된 파지 자리까지 거리다. 괄호 안은 자기 위치 적분의 변위다.

|진단 / 옛 관문 / 로봇|판정 시각|판정 직전 거절 근거|목표 거리 m|3초 목표 거리 감소 m|3초 실제 변위 mm (발행 적분 mm)|분류|
|---|---:|---|---:|---:|---:|---|
|7 / 3 / r1|12.9|화물 여유 −5.050mm; 근접 상대 없음|0.965738|+0.000008|0.030 (0)|정지 명령 지속, 화물로 목표 한 점 거절|
|8 / 7 / r1|59.9 직전, 60 timeout|handoff 없음; 이전에 본 끝을 잃은 search|0.160643, 기억값|0, 기억값|0.195 (0)|시야 상실; 목표 거리 진척 판정 불가|
|9 / 8 / r2|10.8|마지막 계획10.0초: 상대가 목표 여유11.470mm 침범, 자기와는0.947m; 판정 때 기억 만료|0.751942|−0.000008|0.012 (0)|정지 명령 지속; 재계획 전 타이머 종료|
|10 / 14 / r2|19.4|상대 목표 여유−62.067mm, 자기와0.418m, 당시 새 관측 아님|0.434936|−0.000005|0.011 (0)|정지 명령 지속; 상대가 다른 끝으로 지나감|
|11 / 17 / r2|6.6|벽 목표 여유−1.466mm; 상대 없음|0.539452|+0.278166|292.381 (387.028)|진행 중 단일 목표의 벽 여유로 즉시 종료|
|12 / 32 / r2|15.6|상대 목표 여유−97.089mm, 자기와0.449m, 새 관측|0.462932|+0.000000|0.014 (0)|정지 명령 지속; 상대가 다른 끝으로 지나감|

**진척0에 해당하는 handoff는4/5**(실제 변위<0.1mm, 마지막3초 바퀴 명령 전부0),
**진행 중 handoff는1/5**(ep11, 벽)다. 진행 중인데 상대가 보여서 종료된 것으로 확인된 것은 **0/5**다.
4개의 정지는 명령 자체가0이므로 접촉 때문에 모터 명령을 실행하지 못한 물리적 교착으로 확정할 수 없다.
목표 영역의 점유를 현재 접근 전체의 불가능으로 처리한 정책 정지다. 상대 몸체의 실제 여유를 없애지 않는다.
원래 `ApproachProgress`도 이미1cm/3초 감시→한 번 재계획→다시3초 뒤 handoff였다.
따라서 “가까운 상대가 보이면 즉시 handoff”라는 운영 요약을 그대로 원인으로 채택하지 않았다.

ep8은 “처음부터 끝을 못 찾음”도 아니다. r1은 +2.6초15/15, +12.4초5/15 등의 가시 관측이 있다.
마지막3초의 실제 회전도 평가로 확인하지 않았으므로 작은 평면 이동만으로 카메라 정지를 단정하지 않는다.
기존 코드는 `ever_seen=True`이면 원래의 유한 body scan으로 돌아가지 않고 반복 pan/회전을 계속했다.

직접 본 시각(각 overview/r1/r2, 실패6개 총108장): ep7 **0/2/5/7/10/12**,
ep8 **0/12/24/35/47/59**, ep9 **0/2/4/6/8/10**, ep10 **0/4/8/11/15/19**,
ep11 **0/1/2/4/5/6**, ep12 **0/3/6/9/12/15**초. 모두 처음·중간·끝을 포함한다.
로봇은 서로 다른 끝을 맡았고, ep9/10/12에서는 이동하는 상대와 멈춘 로봇의 관계를 먼저 확인했다.
hard ep6은 저장된0/1/2/3초4시각12장만 별도 확인했다. 실패6개의6시각 요건과 혼동하지 않는다.

## 참고 자료 — 구현 전에 확인한 원문과 적용 범위

- [Nav2 SimpleProgressChecker](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/),
  [PoseProgressChecker](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/pose_progress_checker/):
  이동/회전과 허용 시간 창을 함께 감시한다. 새 `GoalProgress`는 이 시간 창을 사용하되,
  왕복 흔들림을 진행으로 인정하지 않도록 현재 관측 목표까지 거리·정렬 오차의 개선을 계산한다.
  이는 ROS 플러그인의 그대로인 복제가 아니라 허용 입력에 맞춘 적응이다. 발행 명령만으로 실제 이동을 확정하지 않는다.
- [Nav2 목표 근처 장애물 대기](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/trees/nav_to_pose_and_pause_near_goal_obstacle/nav_to_pose_and_pause_near_goal_obstacle/):
  일시 장애물 앞에서 멈추고, 해소 여부를 확인한 뒤 재계획하는 절차를 적용했다.
  기존 `safe_prefix`로 모든 장애물 검사를 통과하는 경로 구간까지만 접근한다. 이 구현은 목표까지의 성공 경로 보장이 아니다.
- [OMPL GoalStates](https://ompl.kavrakilab.org/classompl_1_1base_1_1GoalStates.html):
  하나의 목표 대신 가능한 목표 집합을 검사하는 표준 표현을 적용한다. 기존 `AXIAL_CHOICES`의
  196/198/203/208/210mm만 검사하며 IK가210mm를 거절하면 그대로 제외한다. 각도는0, 맡은 끝과 접촉 방식은 유지한다.
- [Nav2 복구 순서](https://docs.nav2.org/jazzy/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough/),
  [Forssén et al., Informed Visual Search, ICRA 2008](https://www.cs.ubc.ca/~lowe/papers/08icra.pdf):
  유한 회전 복구와 유망한 이전 시점 재방문을 확인했다. 새 경로는 마지막으로 끝을 보았을 때의 **발행 팬/팔 PWM·발행 yaw**를 복원한 뒤
  기존 근거리 pitch 우선 회전 스캔을 재사용한다. 논문의 시각 분류기·지도 탐색 또는 정보 이득 최적화를 구현했다는 주장은 하지 않는다.
- [ORCA 공식 프로젝트](https://gamma-web.iacs.umd.edu/ORCA/): 상호 회피 책임과 속도 공간 최적화 원문을 확인했다.
  현재 가시 입력에는 신뢰할 상대 속도 추정이 없어 이번에는 ORCA나 그 충돌 회피 보장을 도입하지 않았다.
  공동 파지 전용의 보편적인 ‘상대 근접 허용 반경’은 **미확인**이며 그런 인용이나 여유 축소를 만들지 않았다.

## 기본 off 토글과 보존 경계

새 선택값은 `--approach-recovery progress_view_recovery_v3`다. 기본값은 계속off이며
순차 접근은off다. 기존 v1/v2도 원본 재현용으로 남는다. CLI→자식 실행→결과/속도 재사용→기록 허가의 기존
`approach_recovery` 필드로 구별되므로 과거 속도·관문 결과를 승계하지 않는다.

1. 현재 관측한 목표 거리1cm 또는 정렬 오차0.05rad의 개선을3초 창으로 확인한다. 같은 오차로 왕복하는 것은 개선으로 세지 않는다.
   목표를 못 보는 시간은 진척 미확인으로 처리한다. 새 상대가 보이거나 목표가 잠시 점유된 것만으로 복구를 켜지 않는다.
   상대가 목표 영역을 막고 실제 목표 오차 개선도3초간 없을 때 기존 안전한 경로 구간 접근·대기를 켠다.
2. 대기 중 자기 목표 진척과 현재 보이는 상대의 이동을 따로 본다. 둘 다6초간 없으면 handoff,
   상대가 계속 움직여도 한 번의 점유 대기는 최대12초다. 상대 기억 만료는 통로 해소의 증거가 아니다.
   새 상대 관측과 목표 여유 확인이0.3초 이어져야 원래 경로로 돌아간다. 학습/물리 성공 판정과 분리한다.
3. 화물/벽이 기본203mm 자리를 막으면 기존 축방향 후보 집합의 IK·모든 장애물 여유·전체 경로 선분 검사를 통과하는 자리만 쓴다.
   ep7은196mm, ep11은198mm가 선택된다. 가상 통로/반대 끝 예약 원·벽/화물/상대 제거·반경 축소는 없다.
   모든 축방향 후보가 막힌 hard ep6은 안전한 handoff 대상으로 남고 성공을 약속하지 않는다.
4. 한 번 본 목표를14.4초 이상 잃으면 이전 발행 카메라 자세·yaw로 복귀(최대8초), 이어 근거리 pitch부터 유한 회전한다.
   14.4초는 기존 pan/pitch 주기7.2초의2주기다. 이 보수적 발동 조건은 정상 재생 보존을 위해 선택했으며 확증 데이터로 정한 상수가 아니다.
   회복 예산40초/에피소드58초는 잠깐 보였다 사라지는 깜빡임으로 초기화하지 않는다. 집기 시작 뒤 완료 명령은 취소하지 않는다.

첫 초안은 일시 점유에도 즉시 경로 구간 접근을 켜고3.2초 시야 상실부터 복구해 정상3개에서108명령이 달랐다.
이를 채택하지 않고 위 진척 창·긴 시야 상실 조건으로 제한했다. 초안 기록도 로컬 압축 원장으로 보존한다.

## 저장 입력 검증

정상6개는 **명령4,664/4,664·done·phase·outcome 전부 동일**, OFF도 모든13개에서 차이0이다.
시간·바퀴·PWM은 원장과 같고 duration에만 플랫폼 수학 오차≤1e-12초를 허용했다.
입력 감사 `invisible_measurements=0`, `held_world_reads=0`이며 실제 GCP 입력 감사도26/26에서0/0이다.

|옛 실패 진단 idx|첫 다른 출력(경과 SIM초)|첫 분기|이후 shadow 변경 명령 수|
|---|---:|---|---:|
|7|6.8|화물 피하는 동일 축196mm 자리로 명령 변경|60|
|8|26.9|마지막 관측 시점의 발행 카메라 방향 복귀|185|
|9|7.8|3초 진척 없음 후 안전한 경로 구간 접근|27|
|10|17.5|목표 점유·진척 창 뒤 안전한 경로 구간 접근|20|
|11|6.6|벽을 피하는 동일 축198mm 자리로 명령 변경|1|
|12|12.6|목표 점유·진척 창 뒤 안전한 경로 구간 접근|31|

**첫 분기 이후는 A의 영상·발행 이력을 계속 넣은 shadow**다. ep7/8에서는 그 옛 정지·시야 상실 입력이 계속되므로
shadow도 handoff를 낸다. 원본13개 길이에서 shadow handoff가2/13이라고 세어도 물리 개선율이 아니다.
hard의 원본은3.6초에 끝나 후보 handoff 시한까지 없고, ep11도 분기1명령 뒤 끝난다.
새 시점·충돌·파지 성공은 GCP에서만 판단한다.

축방향 후보 거절은 전체 재생 **12/20(60%)**, 옛 실패6개에서는 **7/15(46.7%)**다.
이것은 후보 기하 검사 횟수이며 실행 표본을 분모에서 지운 횟수가 아니다. 기존 진단13개의 추가 제외는0이다.
신규 seed205000–205005는6개 채택/30개 배치 제안, 배치 거절 **24/30(80%)**
(로봇 겹침3·다른 화물4·벽8·빔/화물6·기본 자리1·시선2). 기존 정적 시작 조건을 그대로 사용했다.
새6개는 새 진단이며 정식 관문·학습 자료로 바꾸지 않는다. 원격 seed 예약은 운영자가 제출 직전 확인한다.

시험은 `test_grasp_act_recovery.py`, `test_grasp_act_progress.py`, `test_grasp_act_batch.py` **46 passed**.
진척 중 미발동, 일시/지속 상대 점유, 관측 만료, 목표 상대거리가 그대로인 발행 이동, 회전/왕복 오차,
정답 없는 시야 복원·시한, 축방향 안전 여유·IK와 자식 프로필 전달을 확인했다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.diagnose_grasp_act_search13 --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-a-gcp-c3d700e5 --out /private/tmp/search13-diagnosis
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_search13 --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-a-gcp-c3d700e5 --out /private/tmp/search13-replay.json
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_recovery.py tests/test_grasp_act_progress.py tests/test_grasp_act_batch.py
```

## 다음 운영 단계

새 SHA 진단13(정상6+옛 실패6+hard1) → 회수·검토 → 신규 seed 진단6 순서다.
통과 기준은 **정상6/6, 옛 실패≥5/6, 신규6/6**, handoff는 실패다. hard1은 별도 보고하며
새 HOST_ERROR·중단·감사 위반을 통과로 넘기지 않는다. 동시 수는각13/6, cap60 SIM초,
`repeated_cause_v1`, 모델0·weld off·학습 RGB off, gcp1/n4-highcpu-64를 고정한다.

기존 c3d700e5 대기열은 사본·SHA 보존 후 `superseded`, 모든 `ready=false`로 바꾼다.
새 대기열은 커밋·push·원격 SHA 대조 후 운영자용으로 발행한다. 속도16·관문40은 모두
`ready=false`, 명령null, **`gate_promotion_authorized_if_all_conditions_pass=false`**,
새 SHA/프로필에 대한 조정자 승인이 필요하다. 진단 통과만으로 승격하지 않는다.

원본은 이미 Mac에 있어 추가 원격 회수 요청은 필요 없었다. 새 진단에서는 결과/계획/압축 원장/전체 해시와
실패별6시각·대표 성공 영상만 fetch-lite로 회수하며 전체 raw 복사는 하지 않는다. 비용 정지·8시간 상한·20분 유휴·
통합 동시 수·저장 admission은 운영자가 유지한다. 미시작·중단도 기록하고 공통 결함 확인 시 해당 작업을 즉시 멈춘다.
