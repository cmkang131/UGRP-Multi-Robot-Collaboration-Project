# egomap45 원문·코드 대조

- Brian Yamauchi, CIRA 1997, *A Frontier-Based Approach for Autonomous Exploration*, §2.3 p.148.
  https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf
  공개 PDF의 3페이지를 렌더해 직접 확인. 원문: 목적지 도착 후 방문 기록·전방위 관측;
  진전 실패 후 inaccessible 기록·관측·새 목적지. PDF는 raw references에 보존(논문 재배포 코드 없음).
- explore_lite 원본은 이미 vendored: `third_party/mapfree_navigation/m-explore/explore/src/explore.cpp:180–247`
  frontier search→blacklist→30초 progress→새 목적지 전송. `frontier_search.cpp:172–195`
  free 인접 unknown, 거리/크기 cost. 라이선스 BSD-3 원문 유지.
  https://github.com/hrnr/m-explore/blob/master/explore/src/explore.cpp
  https://github.com/hrnr/m-explore/blob/master/explore/src/frontier_search.cpp
  로컬 pinned 원문 SHA는 기존 third_party/mapfree_navigation/SOURCES.json, 최종 freeze에도 해시 저장.
- 기존 PR409 launch 기본값을 실행하는 `harness/public_navigation_monitor.py:17–21,101–117`:
  potential3/gain1/min.75m/planner.33Hz/progress30초. 원문 라이브러리 constructor 기본값과
  launch 적용값은 다르다. egomap45는 **실행 중인 launch 값** 그대로 두고 목표 교체 시점만 주기화.
- `harness/public_navigation_persistent.py:49–65,249–268`: Nav2 progress checker .5m/10초 및 spin .5rad/s.
  `public_navigation/follower.py:41–48`: 기존 도착 .05m. `active_wall_recovery.py:40–54`: blacklist·다음 후보.
  `public_navigation/costmap.py:14,34–45`: 로봇 .24×.20m + padding .02, inflation .5/10.
  Nav2 bringup 예시는 robot_radius .22m / inflation .7/3.0(TurtleBot 조건)이므로 MasterPi의
  물리 치수나 기존 어댑터를 바꾸는 근거로 그대로 혼용하지 않는다. 원본 공식을 재사용하며 이번 수치 변경0.

적응: 원문 Nomad의 laser-limited sonar sweep을 고정 전방 RGB/자기 추정 yaw의 몸체 회전으로 대체;
첫 관측 때도 sweep 수행. NavFn·PR409 비용 선택·기존 active-loop는 주기 경계에서 재사용,
논문의 DFS/가장 가까운 frontier 선택 자체는 이식하지 않는다. 새 라이브러리/venv 변경0.
