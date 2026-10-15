# 자기 지도 → 장애물 점유 → frontier 연결 (selfmap1)

2026-10-15, `self_map_integration=natural_floor_frontier_v1`, 기본 `off`.
이 문서는 1차 구현 계약이다. 물리 성공·경기장 전체 지도 완성을 검증한 결과가 아니다.
실행 구조는 [ACT 결정 기록](act_execution_decisions.md)을 따른다.

## 1. 목적과 경계

종료 목표는 B 도착이나 시간 소진이 아니라 **자기 지도 완성**이다. 로봇이 자기 RGB와
발행 명령으로 만든 지도에서 통로·벽/장애물 점유와 구역 표시를 보존하고, 더 탐색할
관측 경계가 없음을 판단한다. 시간 제한·경로 없음·관측 실패는 미완료 사유다.

| 구성 | 허용 사전 정보 | 지도와 자기 위치 | 완료 주장의 범위 |
|---|---|---|---|
| 자기 지도만 (`self_only`, 이번 구현) | 고정 카메라 보정, 명령 변위 분포, 구역 표시의 모양/규격 | 빈 로봇 시작 좌표계, 자기 RGB+발행 명령 | 관측으로 연결된 시작점의 자유 공간 성분 |
| 정적 지도 제공 (설계만, 별도 후속 토글) | 버전·해시로 연결한 경계·고정 장애물·통로·목적 구역 | 사전 층과 자기 관측 층을 분리, 자기 위치는 RGB+명령 추정 | 알려진 조사 범위 중 실제로 다시 관측한 부분; 사전 지도를 탐색 성과로 세지 않음 |

지도 경로 예외는 정적 지도를 **허용**하지만 자기 지도 조건에 몰래 공급할 의무나 권한은 아니다.
현재 API에는 static map, world bounds, simulator pose, cargo world pose, peer map 인자가 없다.
평가용 정적 도면과 시작점 정답은 독립 `evaluate` 프로세스만 연다. 출력은 제어기로 돌려주지 않는다.
`NaturalFloorSLAM`이 사용하는 `sim.masterpi_camera_profile`은 고정 보정 상수이고,
MuJoCo 환경·state·renderer를 만들지 않는다.

LLM은 임무/경로 후보 선택을 맡고, 지도 코드는 실행 가능한 frontier·경로를 제안한다.
이번 어댑터의 `path_m`/`selected_frontier`는 제안 출력이다. 저장 재생에서는 실행하지 않는다.
주행 executor를 기본 경로로 교체하거나 GO/ACK·ACT 접근/정렬/파지/놓기를 바꾸지 않는다.
집게 닫힘은 발행 서보 명령으로 보수적으로 판단하여 RGB 위치 보정·지도 삽입을 모두 보류한다.
명령 예측은 계속하며 접촉·측정 관절·화물 세계 좌표를 읽지 않는다. 이는 ACT 대체 경로가 아니다.

## 2. 지도에 있어야 하는 것과 완료 판정

지도는 미터 단위 격자, free/occupied/unknown, 관측 frame provenance, 추정 pose/공분산,
RGB로 재관측한 구역 표시를 포함한다. 통로는 footprint가 통과 가능한 관측 자유 공간의
연결이고, 관측되지 않은 곳은 unknown이다. 점유 선분은 보이는 장애물 표면이며 물체 전체의
정답 윤곽으로 채우지 않는다. 희소 ORB 랜드마크는 위치용이고 점유 장애물로 넣지 않는다.
바닥 및 벽 ray의 free는 역센서 모델의 추론이지 바닥 픽셀 전체를 직접 보았다는 뜻이 아니다.

1차 종료 판정 `self_map_complete`는 다음을 모두 요구한다(숫자는 DEV 설계값, 성능 보장 아님).

1. 현재 pose가 시각 갱신 또는 충분한 특징으로 bootstrap됨, σxy ≤0.15 m·σyaw ≤5°.
   카메라가 안정됐고 집게는 닫힘 상태가 아니며, 과거 지도 재구성 요구가 없다.
2. 로봇 현재 칸이 관측된 free 성분에 있고 그 성분의 **필터 전** free–unknown 경계가 0개.
   footprint 필터·최소 군집 크기·blacklist로 사라진 후보를 탐색 완료로 세지 않는다.
   현재 칸 자체가 unknown이면 판정도 unknown이다. 단순히 경로 후보가 0개인 것은 완료가 아니다.
3. 입장이 허용된 RGB frame에서 free/occupied/unknown 상태가 연속 5회 이상 변하지 않음.
   이 횟수는 독립 시점 수나 독립 통계 표본 수가 아니다.
4. 이번 지도 epoch에서 자기 추정 yaw의 45° 구간 8개 모두에서 유효한 벽/바닥 관측이 존재.
   이는 완전한 가시성 증명이 아닌 최소 둘러보기 조건이다.
5. 점유 관측이 존재하며, 요구 구역 B가 기존 `FloorGoalMemoryV3`의 시간·이동·모양 관문으로
   확인됨. B를 보거나 B에 도착했다고 단독 종료하지 않는다.

유한한 자기 관측만으로 아직 보이지 않은 문 너머 공간의 존재를 부정할 수 없다.
따라서 이 종료는 **관측으로 연결된 영역에 대한 운용 선언**이다. 평가에서 전체 지도의
누락과 조기 선언을 별도로 계산해야 한다. 전체 경기장 완료로 승격하려면 별도 사전 등록한
평가 관문이 필요하다. 평가 지표 임계값은 아직 정하지 않았고 이번 결과로 소급 튜닝하지 않는다.

현재 검출기는 바닥과 접하는 벽/표면 관측 및 기존 B 표시만 지원한다. 낮은 화물, 돌출 장애물,
동적 로봇, 다른 구역 종류를 모두 식별한 지도라는 주장은 불가하다. A 등 미지원 구역 요구는
설정 단계에서 거부한다. 관측된 점유만으로 장애물 종류·높이·하중 통과 성능을 단정하지 않는다.

## 3. 데이터 흐름과 재사용

```text
자기 발행 명령 ── calibrated PulseOdometry ── Δpose, Q ─┐
자기 RGB ── ORB/floor projection ─────────────────────┤
                                      PR496 NaturalFloorSLAM
                                             ↓ 추정 pose, covariance
자기 RGB ── active_wall_vision ── body-frame segments/floor rays
                                             ↓
                       OdomGrid.insert + finite floor clearing
                                             ↓
                  ObservedGrid → frontier_candidates + A* path
                                             ↓
                   선택 후보 / observation_required / self_map_complete
```

| 재사용 소스 | 이번 사용 | 변경 여부 |
|---|---|---|
| PR #496 `harness/natural_floor_slam.py` | ORB·SE(2) RANSAC·재관측 pose | SHA `69eb200ae4a80d53cd7adea9846832426ffef674`의 코드/시험/문서 바이트 그대로 가져옴 |
| `self_odom_grid.OdomGrid.insert`, `ray_cells`, `transform` | log odds·hit/miss·ray traversal | 원본 수정 없음 |
| `self_pulse_odom`, `self_pulse_rotation` | 발행 명령의 보정 평균/분산 누적 | 원본 수정 없음, 재생에 모델을 명시 |
| `own_map_navigation.ObservedGrid/frontier_candidates` | footprint 여유, unknown 차단, A*, frontier 점수 | 원본 수정 없음 |
| `active_wall_vision`, `active_camera`, `floor_goal_v3` | RGB 표면/바닥·고정 카메라·B 재관측 | 원본/동결 선택값 유지 |
| `active_wall_mapping`, `active_frontier_cycle` | 기존 RGB→body 관측 및 후보→주행 연결 형태 참고 | 기존 RBPF·graph·cycle 실행기 수정 없음; 이번 후보 소비 지점은 별도 factory |
| PR #437 egomap70, #440 pose continuity | 자기 지도/자세 연속성 경계 참고 | 코드/실험 수정 없음, 과거 물리 결과 승계 없음 |

정확한 수입 파일 SHA-256은 [dependency.json](../experiments/2026-10-15-self-map/dependency.json).
#496/#437/#440에 작업 전 3줄 범위를 알렸다. 의존 PR 변경은 자동 추종하지 않는다.

`PoseGrid`는 같은 frame/cell에 hit/miss를 한 번씩만 적용하고 hit가 floor clearing보다 우선한다.
OdomGrid의 log odds 상한·하한과 hit=.7/miss=.4를 재사용한다. 관측 최대 거리는 기존 4 m다.
자유 공간 밖 경로는 기존 보수적 A*가 거부하며 관측 요청으로 남긴다. 로봇 footprint를
관측 커버리지에 더하거나 보이지 않는 공간을 free로 초기화하지 않는다.

PR496은 과거 모든 frame의 수정 pose를 제공하지 않는다. 현재 시각 보정이 1 cell 또는 5°를
넘으면 이전 점유를 임의로 평행 이동하지 않고 `pose_revision_requires_rebuild`로 삽입/경로
제안을 보류한다. 원본 지도와 frame provenance는 남는다. 후속 pose graph가 과거 pose를
제공하면 gmapping/slam_toolbox처럼 해당 관측을 다시 삽입해 격자를 재구성할 수 있다.
현재 버전은 이 재구성을 구현한 것으로 보고하지 않는다.

## 4. 오프라인 평가 계약

`scripts/offline_self_map.py replay`는 RGB manifest·JPEG SHA-256·자기 command 원장만 읽는다.
`actuator_state`는 전달하지 않고, manifest의 `commanded_servo`는 명령 이력과 일치하는지만
검사한다. 같은 시각에는 capture가 새 주행 명령보다 먼저이며 시작 서보 설정만 예외다.
누락 JPEG는 명시적으로 세고, 나머지 명령 구간을 건너뛰지 않는다. 최신 실행의 RGB가
부분 회수됐으면 그 부분 재생일 뿐 전체 실행 재현/통계 코호트가 아니다.

별도 `evaluate`가 동결 `map.json`을 읽은 뒤에만 정적 장애물 도면과 평가 전용 초기 로봇
pose를 연다. SE(2) 정렬은 초기 pose 1회로 고정하며 ICP/정답 궤적 fitting은 하지 않는다.
runtime `stop_reason`은 이 지표에 접근하지 않는다.

| 지표 | 정의와 분모 |
|---|---|
| 점유 IoU | P=예측 occupied, G=정적 직사각형과 셀 내부가 겹치는 occupied; \|P∩G\|/\|P∪G\|. 경기장 밖 예측도 FP에 포함, unknown은 정답으로 세지 않음 |
| 벽 위치 오차 | 모든 예측 occupied 셀 중심에서 GT 벽 표면까지 최단 거리의 RMSE. N 명시, 예측 0개면 null |
| 벽 누락 진단 | 전체 GT 벽을 1 cell 이하 간격으로 표본화하여 예측 occupied까지 거리 p95. 벽이 없거나 예측이 없으면 null |
| 탐색 free 커버리지 | 예측 free∩GT free / 전체 GT free. 추가로 시작점과 4-connectivity로 연결된 GT free의 n/N도 보고(점 로봇 기준, 실제 통과 증거 아님) |
| known 커버리지 | 관측 occupied/free가 있는 영역 / 전체 도면 셀 수. footprint support 제외 |
| 종료 판정 | 전체 RGB n/N, 지도 삽입·후보 출력·완료 선언 수, 선언 시각·blockers; 물리 성공 수로 변환하지 않음 |

GT에는 저장 정적 장애물만 들어간다. 동적 화물/로봇 정답 점유는 합산하지 않는다.
셀 중심 좌표 변환의 양자화와 벽 두께를 포함한 고정 raster 정의라 기존 egomap 벽 덮음 수치와
같은 지표가 아니다. 센서가 본 표면만으로 두꺼운 장애물 내부를 채우지 않아 IoU가 낮을 수 있다.
벽 오차에는 비벽 점유도 포함되므로 장애물 종류별 벽 정확도와 구별한다.

## 5. 사용·실행 범위

```python
from harness.self_map_integration import Options, make_mapper
mapper = make_mapper(legacy_controller)  # off: 같은 객체 그대로
mapper = make_mapper(robot_id='r2', start_time=1.3,
    options=Options(self_map_integration='natural_floor_frontier_v1'))
mapper.command(issued_command)
proposal = mapper.receive(robot_id='r2', t=t, frame_id=frame_id, rgb=own_rgb, sha256=sha)
```

```sh
PYTHONPATH=. python -m scripts.offline_self_map replay \
  --raw <저장-원장-raw> --images <저장-JPEG-raw> --robot r2 --output <새-출력> \
  --motion-model s2_pulse_v122_rotL_v1 --self-map-integration natural_floor_frontier_v1
PYTHONPATH=. python -m scripts.offline_self_map evaluate \
  --replay-dir <새-출력> --raw <저장-원장-raw> --output <평가전용-json>
```

토글 생략 시 replay도 DISABLED이며 읽기/출력 생성이 없다. 실제 주행 executor 편입과
등록된 시뮬레이션 workflow/번들은 후속이다. 이번 도구는 저장 파일의 오프라인 분석기다.
새 물리 검증이 필요하면 조정자 승인 대기 JSON만 쓰며 직접 제출/접속/실행하지 않는다.

## 참고 자료

- [Moravec & Elfes, High Resolution Maps from Wide Angle Sonar, ICRA 1985](https://publications.ri.cmu.edu/high-resolution-maps-from-wide-angle-sonar): CMU 초록·서지 확인. 다중 관측의 empty/occupied/unknown 확률 결합 개념을 참고. sonar 센서를 추가한 것은 아님.
- [Elfes, Occupancy Grids, UAI 1990](https://arxiv.org/abs/1304.1098): 저자 공개 초록 확인(2013 업로드, 연구 발표는 1990). 불확실 점유와 사전 지도 구분. 1989 IEEE 논문 전문은 이번에 확인하지 않음.
- [Yamauchi 1997, A Frontier-Based Approach for Autonomous Exploration](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf): 원문 공개 PDF와 기존 egomap45 원문 검토 기록 확인. free–unknown 경계 탐색을 재사용. 전체 탐색기의 수치/성능 복제 주장은 아님.
- [ROS gmapping 원본](https://raw.githubusercontent.com/ros-perception/slam_gmapping/melodic-devel/gmapping/src/slam_gmapping.cpp): 코드 열람. odometry/scan과 지도 출력을 분리하는 개념 참고; 레이저/ROS 런타임을 도입하지 않음.
- [slam_toolbox README](https://github.com/SteveMacenski/slam_toolbox): Process Data/Mapping와 pose graph 저장 설명 열람. pose와 관측을 보존하고 수정 pose에서 지도를 재구성하는 경계 참고; 이 구현에 pose graph 최적화가 있다고 주장하지 않음.
