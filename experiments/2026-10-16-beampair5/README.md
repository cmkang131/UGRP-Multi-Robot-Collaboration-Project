# beampair5 — 재관측 뒤 벽 목표 막힘

PR #522, 시작 HEAD `4625b99b` (beampair4b 마지막 실행 `d72efd13`의 후속 기록).
새 교사 버전이며 beampair1–4 / gcp1과 결과를 합치지 않는다.
장면은 beampair3의 `cargo_v7 / grasp_act_teal_blue_v1 / floor_light_v1` 그대로다.

## 수정 전 조사·분포·영상

[수정 전 거부 표](rejection_table-before.json)는 gcp2에서
[분석 스크립트](operations/analyze-before.py)로 자기 가시 측정과 자기 발행 명령을
재생해 만들었다. 평가 위치는 이 지도 재구성에 쓰지 않았다. 원본 절대경로와
SHA256·재현 명령은 표에 있다. 지도 원본은 점유 셀 확률이 아니라 관측한 벽의
사각형 기억이다. A*의 25mm 셀은 탐색 이산화일 뿐이다.

재관측 뒤 6,825개 후보 모두 `blocked_goal`: 목표 검사 통과 0, 경로 검사 진입 0.
동일 후보마다 서쪽 `memory_margin`과 북쪽 `current_geometry`가 함께 나타난다.
중복 blocker 발생을 독립 후보로 세지 않는다. 서쪽 관측은 world 2.5초 이후
갱신되지 않았고, 마지막 여유 2.030179m가 실제 기억 기하 틈 1.682755m를 넘는다.
북쪽 기억은 world 19.5초가 마지막이며 모든 자세의 차체와 겹쳐 틈 0m다.
대표 목표 `(1.580950,-0.182936)`는 탐색 셀 `(63,-8)`에 들어간다.
현재 파랑 띠에서 파생한 목표와 회전 중 누적된 이전 벽 기억이 불일치한다.
기존 `search22.update_world`는 `kind!='cargo'`를 건너뛰므로 벽에 대한 miss 광선,
빈칸 삭제, 클램핑 갱신은 모두 0이다. 시간 만료나 재관측 완료만으로 빈 공간을
확인한 것으로 취급하지 않는다.

Mac 파일 이미지로 직접 확인: 실패8318626 전체0–27.5 SIM초 2Hz56장,
마지막17.5–27.5초 10Hz101장; 성공8318604 전체0–48.6초 2Hz99장.
실패 마지막10초는 원촬영 자기 RGB를 사용한 기존 gcp2 합성물이다.
성공은 저장 qpos 재렌더이며 10Hz 원촬영으로 해석하지 않는다.
실패:0–5.2초 r1 청록 READY, r2 탐색→약17.5–20.7초 시선 변경·짧은 후퇴→
20.7–27.5초 파랑을 보며 정지. 같은 끝 쟁탈·상호 몸체 막힘은 보이지 않는다.
10Hz에서 재관측 팬과 그 뒤의 무이동이 구분된다. 성공:0–16초 탐색,
16–30초 서로 다른 끝 접근,30–41초 정렬·READY, 이후 공동 들기.
영상은 기존 gcp2 ffmpeg 산출물(3배속, 각8MB 미만)을 회수했으며
`outputs/e2e18-admin/playback/beampair5-{baseline,success}/`에 보존한다.
Mac 화면 앱은 실행하지 않았다.

## 표준 방법과 후보

기본 off `--wall-layer beampair_wall_clear_v1`. 첫 전부 목표 막힘이 확인되면
기존 벽 사각형의 점유 support를 25mm 격자로 사용한다. 프레임마다 hit/miss를
더하고 OctoMap의 기본 확률·클램핑을 그대로 쓴다. 새 관측 hit는 같은 scan의
miss보다 우선하며 관측 없는 셀은 나이로 삭제하지 않는다. 차체의 정확한 기존
형상·5mm 기하 여유를 적용한다. 기존의 수 m짜리 오도메트리 확률 팽창을 셀의
기하 경계로 다시 쓰지 않는다. 격자 양자화는 셀 사각형 전체로 둘러싼다.

기존 perfect-visible 교사 지각 경계 안에서 현재 자기 카메라의 가시 광선만
만든다. 원 pinhole·raw fisheye 양쪽 안에 있고 실제 첫 교차가 확인된 광선만
사용한다. 25mm 간격과 기존 local visual range 2m를 재사용한다. 빈/누락/가림
광선은 miss가 아니다. 출력은 카메라 상대 가시 표면 위치이고, 지도 변환은
자기 발행 PWM의 카메라 FK와 발행 바퀴 이력뿐이다. 실제 측정 관절·자기 정답
위치나 벽 정답 위치를 계획기로 전달하지 않는다. 이 perfect surface 지각은
교사용이며 RGB 인식 성능이나 학생 센서로 주장하지 않는다. held 구간은 모든
광선 생성을 중지한다. 광선 원장과 hit/miss/clear 셀 수를 별도 기록한다.

목표를 빈 칸으로 강제 선언하거나 성공 허용 오차를 늘리지 않는다. 기존
inverse reachability의 전체 IK/집게 인증 자세를 재표본하고, 각 후보의 목표,
후퇴, 경로, 시야, 팔 sweep을 그대로 검사한다. 이는 navfn의 근처 가능한 목표
선택을 파지의 기존 유효 자세 집합에 제한한 것이다. 임의의 goal tolerance
반경·새 성공 상수는 넣지 않는다. 계산량 예산 search24/25 on,
held_object_hidden_v1·weld OFF·카메라·성공 판정·60SIM초 상한은 유지한다.
마지막10SIM초10Hz 자기 카메라 링은 기록전용으로 유지한다.

## 시험 계획

8318626→8318620 직렬 먼저, 성공8318600/04/11/31 네 개를 이후 실행한다.
최대3라운드. 확인된 같은 결함은 즉시 자기 실행/미시작 목록을 중지한다.
시간 상한 종료는 cap_end로 별도 집계한다. 6/6일 때만 gate40을 생성하며
`HOLD_SCENE`, 미승인·미제출,8318620/26 먼저·16동시·학습off와 절대경로
`rejection_table`을 넣는다. 결과는 실행 뒤 갱신한다.

## 참고 자료

- Thrun/Burgard/Fox, [Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/), 9장 occupancy mapping.
  출판사 서지와 [Thrun의 occupancy grid 원 논문](https://robots.stanford.edu/papers/thrun.iros01-occmap.pdf)을 확인했다. 책 전문은 미열람.
- [OctoMap log-odds 기본값](https://github.com/OctoMap/octomap/blob/devel/octomap/src/AbstractOccupancyOcTree.cpp#L37-L45): hit .7/miss .4, clamp .1192/.971, threshold .5.
- [OctoMap inverse ray update](https://github.com/OctoMap/octomap/blob/devel/octomap/include/octomap/OccupancyOcTreeBase.hxx): 광선 안 free, 끝 occupied, 같은 scan hit 우선, clamp.
- [ROS costmap_2d ObstacleLayer](https://github.com/ros-planning/navigation/blob/noetic-devel/costmap_2d/plugins/obstacle_layer.cpp): clearing/marking 관측을 나누고 raytraceFreespace 후 mark한다. ROS 문서 미러는 접근 차단되어 공식 저장소 소스를 확인했다.
- [ROS navfn goal tolerance](https://github.com/ros-planning/navigation/blob/noetic-devel/navfn/src/navfn_ros.cpp#L249-L274): tolerance 영역에서 유한 potential인 가장 가까운 목표를 선택한다.
- [ROS global_planner](https://github.com/ros-planning/navigation/blob/noetic-devel/global_planner/src/planner_core.cpp): tolerance 인자는 있으나 noetic 구현의 목표 탐색 동작은 navfn과 같지 않다. 이름만으로 동일 기능을 가정하지 않았다.
