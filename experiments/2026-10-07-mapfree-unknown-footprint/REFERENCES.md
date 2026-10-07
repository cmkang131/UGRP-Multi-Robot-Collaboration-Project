# 원문·기본값과 v6→v7 줄 대조

Nav2 `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`, m-explore
`26d4183a4fe119a0f83685ce3e06370c0c4d21d9`를 고정했다.
[새 원문/해시](../../third_party/mapfree_navigation_unknown/SOURCES.json), 기존
[Nav2/RPP 원문](../../third_party/mapfree_navigation_recovery/SOURCES.json),
[explore_lite 원문](../../third_party/mapfree_navigation/SOURCES.json)을 보존한다.
Costmap/ObstacleLayer/explore_lite BSD-3-Clause 헤더, NavfnPlanner/parameter handler/RPP Apache-2.0.
원문 헤더/라이선스를 보존하며 새 ROS/venv 의존성은 없다. URL 읽기 도구의 cache miss는
직접 HTTPS 원문 다운로드로 확인했다. 잘못 추측한 navfn_parameters.cpp 경로404 후 디렉터리
목록에서 실제 parameter_handler.cpp를 찾아 확인했다(미확인 인용 없음).

|정책|원본 근거|v6 차이와 v7 적용|
|---|---|---|
|footprint 기본 true|[ObstacleLayer L90–91](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L90)|costmap.py:89–93은 일시 current clear뿐. v7은 관측층의 현재 footprint를 매 update free로 유지|
|현재 footprint 변환·갱신 순서|[L585–621](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L585)|ray clear→mark 후 polygon free. 지나온 free는 layer 상태로 남고 새 관측은 덮어쓸 수 있음|
|polygon 채움|[Costmap2D L406–548](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/src/costmap_2d.cpp#L406)|Bresenham edge + x열의 min/max y 포함 채움. unbounded tuple cell로 이식; 미래 sweep free 금지|
|planner 기본 allow_unknown true|[parameter_handler.cpp L42](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_navfn_planner/src/parameter_handler.cpp#L42), [YAML L405](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L405), [NavfnPlanner L253](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_navfn_planner/src/navfn_planner.cpp#L253)|bridge.cpp:9 false→별도 v7 ABI true. 원 NavFn setCostmap의255→COST_OBS-1 비용 그대로; 기존 bridge 불변|
|unknown은 free가 아님|[global YAML L307](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L307)|raw255 유지, actor에 숨은 지도 제공0. coverage 계산 변경0|
|follower unknown|[RPP collision_checker L170–177](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_regulated_pure_pursuit_controller/src/collision_checker.cpp#L170)|OutlineCostmap:28 무조건<254가 원인. v7은 tracking unknown255 허용·lethal254 거부. 기존 범위 밖 거부는 카메라 어댑터 제한 유지|
|frontier unknown 기본 처리|[frontier_search L50–80,172–188](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/frontier_search.cpp#L50), [기본 launch](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/launch/explore.launch)|free flood에서 unknown 이웃 군집. launch는 map/map_updates 입력이며 allow_unknown 설정 없음; 센서 지도 작성기 아님|
|unknown 목표|[explore.cpp L210–240](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp#L210)|PersistentNavigator:173–191 free standoff 강제→centroid 목표 그대로. blacklist/30초 timer/다음 frontier/없을 때만 종료 유지|

전체 Nav2 bringup 또는 ROS 서버 복제라고 하지 않는다. 카메라 관측·단일 2D costmap·고정
메카넘 명령/오도메트리 어댑터만 유지하며 이번 unknown 관련 차이만 포팅한다.
