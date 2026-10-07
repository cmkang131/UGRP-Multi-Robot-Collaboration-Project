# egomap20 — 고정 바닥 투영으로 경기장 순회 지도 (사전 등록)

2026-10-07 사용자 요청, 시작 `cf9ed086`. egomap19 통과한 바닥 투영 경로를 고정한다.
`servo_stiffness=real_v1`, `wall_texture=tape_v1`, 원 v3 무하중 보정표,
`motion_model=s2_pulse_v122`, `odom_grid_v1`, `own_map_rbpf_v1`100,
`positive_depth_v1`, `own_submap_v1`, `inverse_sensor_v1`. 모두 기존 기본 off 보존.
시차는 주석 recall0으로 보류. detector/보정/강성/모션/정합/공분산/격자 문턱 재튜닝0.

## 취득 계획 — 결과 열람 전에 고정

- 두 녹화 각180 SIM초(+reset≤5초), seed20101/20102, 같은 v7 mesh/camera v3/SEARCH 자세.
  spawn=[3.25,.75,pi]. 고정 장면은 egomap19와 같다. 정적 지도는 **취득 경로 설계용 도면**으로만
  참조하고 제어기/자기 지도에 넣지 않는다. raw 제어 입력은 자기 RGB·발행 명령뿐, 실제 pose/관절/접촉
  등 GT는 평가/물리 실패 abort에만. 다른 로봇 지도·freeze·모델 호출0.
- 명령 경로는 자기 출발 좌표로 아래 순회1개와 그 역순. 설명용 도면 좌표 waypoint:
  시작(3.25,.75) → (3.25,−2.60) → (−.30,−2.60) → (−.30,.65) → (1.30,.65)
  → (1.30,−2.60) → (4.60,−2.60) → (4.60,.75) → 시작.
  중앙 북쪽 벽이 외곽과 붙어 있어 한 외곽 사각형은 통과 불가다. 폭1m 남쪽 통로로 두 구역을
  각각 순회하고 같은 통로를 두 번 지난다. 좁은 .5m 문은 이 취득 경로에 쓰지 않는다.
- 이동 구간은 해당 벽을 바라보며 옆이동: 중앙/서쪽/동쪽 세로 구간은 그 벽 방향,
  위쪽 수평은 북쪽, 아래쪽 수평은 남쪽. 끝점에서 다음 구간 방향을 향해 회전.
  시작 후2초 정착. 고정 v122의 지원 pulse만으로 경로를 사전 계산하고 명령표/hash를
  실행 전에 commit/push한다. 실행 중 좌표를 읽어 궤적을 보정하지 않는다.
  명령 기반 종점 허용오차≤.10m, 이동 중 heading 허용오차≤3°를 사용한다.
  모델상 전체 경로가180초 내 안 끝나면 **취득 전** 일정 한계로 기록하고 실행하지 않는다.
  실제 한 바퀴 완주 여부는 GT로 사후 waypoint 접근≤.35m/순서 및 경로 그림을 평가한다.
  물리 접촉/기울기/실행 실패는 기존 abort 그대로, 보수적 불확실성은 기록만. 실패한 물리를
  재시작하거나 설정을 맞춰 재튜닝하지 않는다. 두 번째도 같은 원인이면 중단한다.
- PR409 `a43afb7550795411f95412d200247b3cba8530ec`의 public_ros_v8을 읽기 전용 검토.
  actor.receive는 floor_xy/wall_xy와 B patch, command는 연속 twist→명령을 요구한다.
  이번 v122는 제한된 고정 pulse만 지원하므로 그대로 꽂으면 미지원 명령이다. 새 관측/제어
  어댑터 검증을 생략해 public_ros_v8 실행으로 부르지 않고 **사전 명령 취득**으로 구분한다.
  PR409 파일은 수정/병합하지 않는다. 자율 frontier 성공 주장은 하지 않는다.

## 평가와 조건부 F 내보내기

- RGB10Hz 저장, 기존5Hz 자기 접점·4m/정착/양의깊이 조건. 예측을 먼저 저장·해시 봉인하고
  GT/정답벽을 나중에 읽는다. 지도 GT 정렬은 출발 SE(2) 한 번, ICP/프레임별 보정0.
- 각 녹화 별도: 점유 P(.15m), 전체 벽 표본 recall=덮임(기존 .1m 벽 표본), 벽 RMSE,
  경로 median/P90/P95/RMSE/종료XY/yaw, scan 갱신·루프 수락/거부 이유, 시간별 덮임.
  실제 가시 벽 분모 recall은 기존 가시성 도구가 새 녹화에 적용될 때 추가한다.
- 신뢰도 곡선은 (a) 최종 점유 sigmoid(log-odds) 10등간 bin vs 실제 벽 .15m 정답 비율,
  (b) 삽입 weight 10등간 bin vs 해당 관측의 벽점 정답 비율을 분리한다.
  Brier/ECE는 점유 셀의 조건부 진단만, weight는 확률로 부르지 않는다. 빈 bin은 NA.
  그래프에 GT회색/지도신뢰도음영/추정·실제 경로, 녹화별 지표·분모를 함께 표시한다.
- 기존 강성 off s1042–s1047의 egomap9 RBPF100+v3+confidence+graph 결과 및 egomap19 짧은
  지도와 같은 표에 넣되 **장면/길이/명령/모션 모델/정착 표본이 다르므로 인과 비교/합산 금지**.
  강성 off 물리를 새로 돌리지 않는다. 새 녹화의 동일 관측 v122 DR 지도를 평가 기준선으로
  추가해 §17/§19 상대 기준도 그대로 보고한다(종료≤.75m/30% 개선, 경로RMSE20% 개선,
  median/P95 비증가, 지도P 비감소/R 하락≤2%p/벽RMSE20% 개선). 기존 성공을 승계하지 않는다.
- 사용자 조건 '결과가 좋으면'은 **각 완주 녹화에서 P≥.90, 전체R≥.70, 벽RMSE≤.15m,
  경로RMSE≤.25m 및 위 상대 기준**으로 미리 정한다. 모두 충족할 때만
  `wall_export=segments_confidence_v1`(기본off) 자기 벽 선분+신뢰도+출처+좌표계 함수 추가.
  DESIGN §8/§9 F에 따른 자기 LLM 입력용이며 상대에게 배열 전송/지도 merge/모델 호출0.
  미달이면 F 함수는 구현하지 않고 실패 원인을 기록한다. 결과 후 문턱 변경0.

## 실행·검증·보존

물리2건,≤370 SIM초·raw≤350MiB·wall 예산20분, 오프라인 재생 wall예산30분/건
(속도 비교 아님). agent_lock status null→ownPID acquire, ugrp_session+sim_cli 관리
workflow, nice0/NO_BG_NICE, 한 번에 하나, freeze0. ENOSPC=HOST_ERROR, 원본 보존.
초기 free42.65GiB, project52.48/58GiB. raw는
`/Users/changmin/projects/ugrp/outputs/arena-wall-map-v1/`. 실험 Git 미디어≤1MiB/파일,
총≤5MiB. 새 의존성/venv0. 변경 시험1–3파일/off 골든 통과 후 commit/push.
PR405 DRAFT·병합/force/reset0, #406/#409/다른 worktree 수정0. 기존 미추적4파일 보존.
TensorBoard 생략 지시 유지, Drive 사용0. raw 로컬 보존과 Git 원격 보존을 구분한다.

## 출처·재사용

- [egomap19](../2026-10-07-servo-stiffness/README.md), [공식 제조사/MuJoCo/v122 출처](../2026-10-07-servo-stiffness/REFERENCES.md).
- [PR409 v8 actor](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a43afb7550795411f95412d200247b3cba8530ec/harness/public_navigation_monitor.py),
  [자기 관측 인터페이스](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a43afb7550795411f95412d200247b3cba8530ec/harness/public_navigation/actor.py).
  이 코드와 명령 어휘를 실제 대조했으며 새 복사/라이선스 의존성은 없다.
- [Coulter 1992 원문 안내](https://publications.ri.cmu.edu/implementation-of-the-pure-pursuit-path-tracking-algorithm):
  실제 추종은 pose feedback이 필요하다. 이번 고정 명령 취득을 pure-pursuit/publicROS의
  실제 관측 폐루프 실행으로 부르지 않는다. 경로는 calibrated SE(2) pulse rollout으로 작성한다.

### 취득 전 명령 봉인

관련3파일10시험 통과. 정방향261 pulse/143.8초, 역방향282 pulse/149.2초에 명령 기반
8개 waypoint 도달, 각180초 종료까지 정지 관측한다. [정방향](forward-plan.json)·[역방향](reverse-plan.json).
도면 대비 명령 예측 경로 중심의 벽 최소거리 .463/.475m, 취득 설계용 보수적 원반반경
.32m를 뺀 여유 .143/.155m([기하 점검](results/planned-clearance.json)). 실제 충돌/완주의 보증은 아니다.
워크플로 `arena-wall-map`1.0.0, 번들 `egomap20-arena-tour-v1`; 기존 egomap19는 변경하지 않는다.
