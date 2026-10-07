# 고정 원본 대조

로컬에 이미 보존된 원본 파일과 SOURCES.json 해시를 다시 확인했다. 새 패키지/venv 변경0.
PR409 `origin/claude/mapfree-explore` **ed2fa0e9**의 아래 v3/v7/v8 파일은 PR405 사본과 diff0.
`harness/public_navigation_persistent.py`, `public_navigation_unknown.py`, `public_navigation_monitor.py`.
공개 웹의 explore.cpp도 확인. Nav2 raw URL은 웹 도구 cache miss여서 로컬 고정본을 근거로 사용한다.

|원본/라이선스|줄|현재 연결의 차이 / 적용|
|---|---|---|
|[Nav2 BT XML](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml), Apache2|12,16–40,50–58|planner1Hz/context clear1/전체retry6; 원본 clear-spin-wait-backup. 사용자 요청 backup/wait 순서만 교환 명시|
|[RoundRobin](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/plugins/control/round_robin_node.cpp), Apache2|42–93|wrap=true에서 끝 자식 뒤0으로 돌아감; 성공 시 실패수0, 모든 자식 실패 시 action 종료. 기존 v3는 wrap=false 분기|
|[RecoveryNode](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/plugins/control/recovery_node.cpp), Apache2|42–73,81–108|recovery SUCCESS만 retry수 증가, 실패/한도 소진 시 navigation action ABORTED|
|[clearEntirely](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/src/clear_costmap_service.cpp), Apache2|237–264|resetLayers/resetMap; 기존 어댑터는 플래그만 clear하고 과거 hit 재적용|
|[ObstacleLayer.reset](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp), BSD3|858–871|resetMaps, 최신 관측 buffer로 다시 갱신. 자기 장기 SLAM 지도 reset 아님|
|[explore_lite](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp), BSD3|179–225,247–280|frontier없음/전부blacklist일 때만 stop; ABORTED 목표 blacklist 후 다음 makePlan 즉시 요청|

로컬 원본은 `third_party/mapfree_navigation{,_recovery,_persistence}/`.
`PersistentNavigator.action_failed`(L96–103)는 static_mode에서 failed=True, 탐색 모드에서만 abort+reset.
`PersistentNavigator.update`(L205–224)는 관측 B 접근을 static_goal 인자로 받으면 static_mode=True로
전환한다. `ActiveMapper.receive`(L212–214)는 clear 요청을 플래그 해제로만 소비했다.
`ActiveMapper.graph`(L132–137)는 목표·복구 action 상태를 주기적으로 reset한다.
이 연결 차이만 별도 옵션으로 분리하고 원본 v3~v8는 보존한다.

새 코드 대응: `active_wall_recovery.py`의 `ExplorationRecoveryNavigator.failure/phase_result`는
RecoveryNode/RoundRobin의 반복·성공 계수, `action_failed`는 explore_lite ABORTED callback,
`RecoveryMapper.clear_navigation/_rays`는 resetMaps와 현재 관측/epoch,
`graph`는 같은 action 상태를 유지하는 자기 지도 TF 연결이다. 조상 navigator의 충돌 검사,
NavFn/frontier 및 행동 수치(1.57rad/.30m/.15m/s/5s/10s/6회)는 그대로 재사용한다.

줄 번호: 새 옵션 factory L23–26, blacklist L40–55, retry L57–67, wrap/success L69–85,
실제 reset L106–115, graph 상태/TF 보존 L121–141.
