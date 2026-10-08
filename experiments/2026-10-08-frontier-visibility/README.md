# egomap45 — frontier 이동·관측 주기 (2026-10-08 사전등록)

범위: egomap34 seed32002 오프라인 진단, 새 seed45001 **180초 DEV 1회**.
검출기/지도 egomap34 구성 동결, 매 프레임 SLAM 삽입(egomap44)은 미채택/off.
GT는 별도 봉인 후 평가만. 모델0, 다른 로봇 지도0, freeze0, 시간 연장0.
TensorBoard 생략 유지. PR405 DRAFT, S2/PR406 수정0.

## 먼저 진단한 사실

원본 `outputs/wall-segment-dev-v1/new-seed`, 891개 trace JSON bytes 재현.
첫 실행은 마지막 감사표의 초기 epoch=-inf JSON 저장에서만 실패했다. 이미 저장한
68개 costmap과 891개 일치 trace로 표를 복구했다. 물리/추정 재실행·raw 덮어쓰기 없음.
[수치](results/diagnosis.json), [그림](figures/frontier-audit.png).
68시점은 3초 간격 및 no_path 추가 표본이며 전체 891프레임 비율로 해석하지 않는다.

|가설|평가 전용 결과|
|---|---|
|(a) 왼쪽 frontier 없음|68시점 중 37시점 없음, **31시점 있음**. 최초 21.3초, 239칸 후보(11.95m frontier 길이), 중심 세계[.203,1.248]|
|(b) 크기/blacklist/비용|왼쪽 후보 42개 인스턴스, 17–610칸(최소15칸 통과), blacklist 0. 21.3초 왼쪽 rank2 비용−11.841, rank1 북쪽 외벽 밖 후보517칸 비용−25.675. 크기 항이 큰 거짓 외부 frontier를 선호|
|(c) 문/팽창 때문에 전부 불가|왼쪽 후보 **42/42 경로 있음**. 실제 문 폭 .5/1.0m, 패딩 포함 footprint .28×.24m. 63.3/80.7초 경로는 중앙 문 y=.087/.128, 103.5/107.1초는 아래 문 y=−2.592/−2.648을 가로지름. 문 통과 불가능이라는 단정은 기각|
|(d) 시간/목표 지속|frontier 선택28회, 왼쪽 내부7회(최초63.3초), 정보이득 선택18회(재방문3회), 14회 navigation reset. 소진 종료0·progress blacklist0. 실제 x최소2.2295m로 왼쪽 진입0. 마지막 왼쪽 목표171.1초 이후 남은10.2초, 180초 cap 종료|

후보 칸 합9834는 **중복된 cluster 인스턴스**이며 관측한 벽 칸 수가 아니다.
첫 왼쪽 방향 8개 선택은 경기장 북쪽 외부였다. 문에 도달하는 계획 자체는 생기지만
새 관측/3.03초 timer/10초 정보이득에 따라 경로·목표가 교체된다. 82.3초에는 같은 왼쪽
후보 경로가 중앙 문 경유에서 아래 문 우회로로 길어졌다. 이것은 표준 탐색기의 튜닝 실패라고
단정할 수 없다. 좁은 시야·오차 있는 costmap·변하는 목적지가 결합했고, frontier 도착/실패 후
전방위 관측 단계는 현재 구현에 없다. 비용 수치·inflation을 새로 맞추지 않는다.
B/재방문 temporary goal은 기존 target이 있으면 즉시 교체하지 않는 기존 어댑터 제한도 있다.
이번에는 그 목표 인식/추정/검출기를 별도로 수정하지 않는다.

## 표준 선택과 옵션 (실행 전 고정)

[Yamauchi 1997 원문 §2.3, p.148](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf)의
**한 frontier 이동을 마치거나 진전 제한에 걸린 뒤 360° 센서 sweep → 지도 갱신 → 다음 frontier**
주기를 택한다. 성공 위치는 visited, 불가 위치는 inaccessible로 남긴다.
원문 스캔을 이미지로 직접 확인했다. [원 코드/적응 내역](REFERENCES.md).

|옵션|기본|on 동작|
|---|---|---|
|`frontier_observation=yamauchi_cycle_v1`|off: 기존 factory/출력 그대로|이동 중 선택 목표 유지, 도착/진전 실패 뒤 360° 관측, 완료 후 새 후보 선택|
|초기 관측|기존 off 불변|좁은 FOV 카메라이므로 시작에도 1회 360° sweep, 기존 180초 안에서 수행|
|도착/실패|기존 값 재사용|도착 .05m, Nav2 progress checker .5m/10초, 기존 회복 소진. 실패 목표 blacklist|
|sweep|새 학습/튜닝 없음|기존 spin 요청 .5rad/s → v122_rotL 유한 pulse. 자기 추정 yaw 누적 2π−.02rad, 상한 기존 progress_timeout 30초. 완료/미완료 별도 기록|
|후보/계획|수치 불변|기존 public_ros_v8 cost3/1, min .75m, NavFn, .05m grid, footprint/inflation/unknown/clearing 그대로|
|능동 loop|기존 on 유지|주기 사이에서만 기존 information_gain_v1 선택; 이동·sweep 중 목표 덮어쓰기 보류|

Yamauchi 전체 탐색기/DFS로 갈아끼우는 것이 아니라 **관측/목표 생명주기만** 적용한다.
논문 수치 미명시는 기존 어댑터 값을 유지한다. 센서가 고정 전방 카메라여서 몸체 회전이 필요하다.
회전 중 RGB→navigation 및 기존 관문을 통과한 RBPF 삽입은 계속한다. 매 프레임 SLAM 삽입은 아님.
도착한 목표의 visited 거리 판정은 기존 blacklist의 5셀 허용 범위를 재사용한다.
회전 중 추정 yaw는 자기 센서/명령만; GT yaw로 종료·보정하지 않는다.

## 실행 전 판정·순서

1. 사전등록 커밋 → 변경 모듈 시험(기본off 바이트, 도착/진전실패/회전 wrap/시간제한/TF 유지,
   seed·옵션만 차이) → 소스 동결 커밋/push → agent_lock null 확인·원자 acquire.
2. `seed45001`, 180초, tape_v1/SEARCH/강성 real_v1/rotL/RBPF100/graph/switchable/
   selective+insertion+Manhattan+20deg/recovery/public_ros_v8는 egomap34 그대로.
   단일 DEV, dev_light, ugrp_session + 등록 workflow. S2와 동시 실행 금지. 잠금은 물리 동안만.
3. **운용 판정 5개**: 180초 정상 기록, GT평가 문 통과≥1, 실제 시야 벽 표본>146/329,
   전체 벽 덮음>213/329, 벽·로봇 접촉0. 표본1쌍(seed가 다름), 원인 개선 확증 아님.
   기존 egomap20 품질 기준은 egomap41 사용자 목표 변경으로 채택 관문이 아니며 수치 그대로 보고.
4. 지도 영역 P/R, 전체 P/R·덮음, 점유칸/분모, 벽 RMSE, 이동·면적·hold,
   문 통과·B 도착·접촉·삽입과 거부 사유를 baseline과 나란히. 목표 B는 자기 RGB 관측 후보만;
   미관측이면 별도 표시. GT 문/왼쪽 구역 좌표는 평가기에만 존재.
5. 문 통과: 차체 중심 경로가 divider x=2.2의 실제 개구부에서 오른쪽→왼쪽으로 횡단,
   이후 중심 x<2.175가 확인된 사건. footprint 전체 여유도 별도 기록. 판정/문턱 사후 변경0.
6. 영상은 시간에 맞는 online-map snapshot + 자기 RGB/추정·GT 경로(평가 표식)의 4배속.
   실행 후 추가 seed/재튜닝0, 실패 그대로 기록. 부하·소스·raw 해시 보존.

raw `/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1/`, 예산 1GiB,
여유10GiB 이상, 물리 wall 상한30분. ENOSPC=HOST_ERROR. push 서버 오류는 로컬 SHA 진행 후 재시도.
