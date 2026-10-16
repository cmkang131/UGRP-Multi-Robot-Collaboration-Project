# beampair1 지정 대기열 운영 결과

2026-10-15, GCP gcp1 / n4-highcpu-64. PR #522.
소스 `d79f04a39e3eec9d418e5c44929182e0ec79f51c`, 의존성 `26f84d0f0ada1c33473c83cca2d3415ce51bd247`.
다른 SHA·장면·호스트 결과는 합치지 않았다. 학습용 RGB·기록 승격·학습은 실행하지 않았다.

**NOT_READY: 계획40 중 성공5, 제어실패1, 감독중단1, 미제출33.**
정상 종료6회 중5성공이며, 중단한 코호트를40회 성공률 추정으로 쓰지 않는다.
cap_end0, HOST_ERROR0. 7회 모두 result+adapter 입력감사 활성, invisible_measurements=0, held_world_reads=0.

| 실행 관문 | 누적 통과 | 해당 관문 탈락/보류 |
|---|---:|---:|
| 시작 |7|33 미제출|
| 종료 결과 기록 |7|0|
| 양쪽 align |6|1 제어실패|
| 양쪽 ready |6|0|
| 양쪽 pick |6|0|
| 양쪽 command complete |5|1 감독중단|
| 12mm·10도·양집게0.5N·3초 공동 유지 |5|0|
| 입력 감사 적합 |5|0|

실패 seed8318604는 첫·중간·끝 자기 RGB12장(각 r1/r2: 0,4,8,11,15,19 SIM초)을 직접 봤다.
두 로봇이 같은 끝으로 모인 실패로 분류하지 않았다. 평가 원장192행의 same-nearest-end는0이다.
r1은 peer_prefix_wait 후 절대시각8.9→20.9초 대기 시한이 만료돼 approach_blocked_handoff,
r2는 peer_approach_handoff로 종료했다. 두 로봇 모두 align 전에 멈췄다.
정확한 기하학적 차단 물체·간격은 원본에 기록되지 않아 미확인이다.
같은 소스 seed8318606의 PID306639에 SUPERVISOR_STOP.json+SIGINT를 보냈다.
그 실행은 pick 단계에서 감독중단했으며 물리 실패와 분리했다.

| 사유 | 횟수 | 모집단 |
|---|---:|---|
| safe_prefix |8|복구 이벤트·증상|
| blocked_goal_calls |3|계획기 호출·no_path와 중복 가능|
| no_path_calls |3|계획기 호출·blocked_goal과 중복 가능|
| peer_prefix_wait |1|복구 이벤트|
| peer_wait_deadline_handoff |1|복구 종료 이벤트|
| approach_blocked_handoff |1|r1 종단 결과|
| peer_approach_handoff |1|r2 종단 결과|

위 서로 다른 모집단의 횟수를 합산하지 않는다. 후보별 원장은7회 모두0행이다.
[funnel.json](funnel.json)은 후보 원장0행의 관문표와 별도의 계획기 카운터를 구분하고,
4412 관측·로봇 쌍 → 한 점 이상 가시2819 → 5점 이상2799 → 허용 측정2799의 누적 표를 담았다.
이 관측 수는 저장 JPEG 수나 학습 프레임 수가 아니다.

first30 wall/SIM 중앙2.422(측정4회), 전체 정상종료 wall/SIM 중앙2.524(6회).
결함으로 조기 중단해16동시 속도는 검증하지 못했다.
첫2회24장, 실패12장, 감독중단12장으로 고유 자기 프레임 총48장을 직접 검토했다.
현재 소스는 실제 overview 카메라를 저장하지 않아, 실패/중단 각각6장의 평가좌표 개요를
GCP에서 별도 재구성하고 EVAL reconstruction으로 표시했다. 실제 카메라 영상과 구분한다.

실패 원본40장+중단 원본70장=110장을 Mac `outputs/gcp1-runs/<run>/raw/eval-own/{r1,r2}/`에
전부 회수하고 개별 SHA256을 대조했다. 성공 실행은 메타데이터와 요약만 회수했다.
모든7회 원본 SHA256SUMS를 GCP에서 검증했다. 원본 전체는 gcp1 영구디스크의
`/home/ugrp/ugrp-sim/runs/beampair1-gate-831860[0-6]-d79f04a3/`에 남아 있다.

운영 보고·회수 영수증·몽타주:
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/beampair1-d79f04a3-ops/`.
분석 스크립트는 같은 디렉터리와 GCP `ops-reviews/beampair1-d79f04a3/`에 보존했다.
소유 진행 프로세스·잔여 lease는0이며, 다른 작업과 유휴20분/24시간/budget-stop은 유지했다.
새 SHA로 접근 복구를 수정한 뒤 처음부터 다시 측정해야 한다. 지정 대기열 운영은 종료했다.
