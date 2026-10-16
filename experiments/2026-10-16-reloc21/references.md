# reloc21 방법과 수치 근거

수정 전 gcp2 원본 16시도의 종료 관문표를 생성했다(`analyze_prior.py`, `prior-gate-table.md`, 압축 원장).
원본 HOST_ERROR 7 = 위치 재추정 소진 6 + 이미 reloc20에서 수정한 지도 선언 설정 오류 1.
운반 제어 시작은 실제 9/10이고 0/9는 place다. 전체 계획 재검사는 실행 전 검사가 아닌 오프라인 기하 재검사였다.

2026-10-16 열람한 공식 자료:

- [Nav2 consistent replanning / invalid path](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/trees/nav_to_pose_with_consistent_replanning_and_if_path_becomes_invalid/): 유효 경로를 유지하고 유효하지 않을 때 재계획하는 구조를 참고. Nav2 자체를 설치하거나 동일 성능을 주장하지 않는다.
- [Nav2 FeasiblePathHandler](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/feasible_path_handler/): 경로 진행에 따른 앞부분 제거를 참고. 이번 후보는 단조 cursor와 엄격한 직선 가시성 경로 단순화다.
- [SimpleProgressChecker](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/): 이동 진행과 시간 예산을 분리한다. 여기서는 wall 시간 대신 기존 SIM 1초 계획 기회를 사용한다.

## 유지·신규 수치

- 도착 위치 .025m, yaw .04rad, 전진 .08m/s·회전 .1rad/s, gain .9/.6, 내려놓기 전진 .15m·후퇴 .15m, slot 5개·가장자리 .20m는 기존 코드 그대로다.
- 변화 없는 동일 선택 제거 횟수 3은 이번 사용자 지시다. 무진행 거리는 새 허용 오차를 만들지 않고 기존 도착 반경 .025m를 쓴다. 재시도는 기존 재계획 주기 1 SIM초다. 물체나 장애물 정보를 삭제하지 않고 해당 slot 후보만 제외한다.
- 경로의 모든 단순화 연결·실제 명령은 reloc20 strict sweep·하중 enclosure·기존 노드 40,000 한도를 유지한다. 경로 비용 `길이/.08 + 회전량/.1`은 기존 명령 상한에 따른 계획값이며 실제 속도·성공 판정이 아니다.
- 1라운드 전체 cap 300 SIM초·운반 phase 180 SIM초 유지. R3 초기 완전 경로 93266 7.668–8.668m, 93315 4.602–5.602m(격자 원경로)라 직진 최고 속도만으로도 95.9–108.4초·57.5–70.0초가 필요하다. 회전과 관측 시간이 추가된다. 동등한 gcp2 전체 운반 성공은 reloc18–20에 0이므로 이전 성공의 SIM 시간을 현재 성공 기준으로 가져오지 않는다. 상한 연장만으로 성공을 만들지 않는다.
- 첫 R3 후보의 회전 명령 시간은 93266 56.4/180.1, 93315 52.9/180.1 SIM초. density의 무명령은138.6/180.1·127.9/180.1초. 이는 명령/예측 분류이고 실제 운동 관측과 다르다.

모든 새 동작은 기본 off `reloc21_route_progress_v1`, `reloc21_complete_plan_v1`. 자기지도 HOST_ERROR→CONTROLLER_FAILURE 분류 수정은 제어 경로·명령·종료 시각을 바꾸지 않는다.

## 선행 통로·반복 재생

`replay_routes.py`를 gcp2에서 실행했다. R3 각 후보의 끝60 SIM초를5초 간격13개 상태로 재생했고 두 시드 모두13/13 경로가 있었다. 같은 경로 계열3연속 재생 중 남은 길이가 기존 도착 반경 .025m 미만으로 줄거나 늘어난 구간이 각각6개였다(겹치는 창, 독립 실패횟수 아님). 실제 저장 경로 바이트가 같았다는 뜻은 아니다.

R3 첫 운반 상태5개 slot×4조건의 완전 기하 검사20/20 통과. 최소 틈 min/p50/p95는 .0000447/.0003927/.0017527m다. 이는 전체 경로·명령 화물 외접원 여유이며 실제 통로 폭이나 접촉 여유가 아니다. 경로가 없는 문제가 아니라 매우 작은 계획 여유와 추정/진행 불일치가 남아 있다. [사유 표](prior-route-table.md)와 `prior-route-replay.json`에 물체별 거부·최소 틈을 보존했다.

## R1 뒤 비물리 반복 제거 수정

`partial-93266-rejection-table.json`을 먼저 생성하고 두 실패 전체/종료10Hz를 직접 읽은 뒤 수정했다. 실행 소스6acde414a에서 시작 enclosure 겹침1765건이 같은 slot을42회 이상 제거한 것으로 다시 기록됐다. 선택 실패가 실제 검사한 각 slot이 아닌 이전 선택에 계속 붙고, 10Hz 루프마다 재검색되는 결함이었다. 후속 수정은 각 slot별 기존1 SIM초·3회 한도를 적용하고 전 후보 소진을 실행 실패로 반환한다. geometry 허용 오차나 cap을 바꾸지 않는다. 오래된 경로 잔여량은 null/시각으로 구분한다. 관련41개 비물리 회귀가 통과했지만 이 수정으로 새 CPU 물리를 실행하지 않았다. MJWarp 인수는 별도다.
