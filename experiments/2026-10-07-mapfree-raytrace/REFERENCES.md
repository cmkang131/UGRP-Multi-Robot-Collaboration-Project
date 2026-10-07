# 원본 대조와 적용 범위

Nav2 revision `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`, m-explore revision
`26d4183a4fe119a0f83685ce3e06370c0c4d21d9`. 공개 원문을 다시 확인했다. 기존 vendored source와
[SHA/라이선스](../../third_party/mapfree_navigation_persistence/SOURCES.json)를 보존한다.
Nav2 ObstacleLayer/raytrace·VoxelLayer와 explore_lite 해당 파일은 BSD-3-Clause 헤더다.
새 ROS 의존성/패키지/venv 설치는 없다.

| 단계 | 확인한 원본 | v5와의 차이 / v6 계약 |
|---|---|---|
| 센서 원점 | [ObstacleLayer L711–724](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L711) `clearing_observation.origin_` | v5 persistent.py:297은 차체 원점. v6는 관측별 명령 팔 자세의 camera XY를 전달 |
| clear-before-mark | [L501–580](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L501) clearing 관측 전체 raytrace 후 hit lethal | v5:304의 `if cell in free`가 미관측 틈을 남김. v6는 광선 통과 셀 전부 free, 그 뒤 이번 벽 endpoint 전부 hit |
| 해상도 독립 선 순회 | [raytraceLine / bresenham2D L60–144](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_util/include/nav2_util/raytrace_line_2d.hpp#L60) endpoint 포함 | 기존 검증된 `raytrace_cells`를 재사용. 좌표→cell은 해당 grid 해상도, unsigned offset만 unbounded tuple로 바꿈 |
| 과거 장애물 삭제 | [ObstacleLayer L782–788](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L782) MarkCell FREE_SPACE | 과거 hit를 지나도 멈추지 않음. 최신 clearing 측정을 반영하며 현재 hit는 마지막에 복원. 시야 밖/no-ray hit는 유지 |
| VoxelLayer 구분 | [VoxelLayer L187–189,278–418](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/voxel_layer.cpp#L278) XYZ sensor origin에서 voxel line clearing | 공통 clear→mark 원리 확인. 높이층·3D ray를 2D라고 가장하지 않음. 본 평가의 평면 기하에는 ObstacleLayer 2D를 선택 |
| frontier 소비 | [frontier_search.cpp L50–80,172–188](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/frontier_search.cpp#L50) free flood와 unknown/free 경계 | explore_lite 자체는 센서 raytrace를 하지 않고 costmap을 소비함. 원본 군집/NavFn/blacklist 설정은 변경0 |

VoxelLayer 추가 읽기 원문 SHA256:
`694b160646c46faf9df6164e5d925ad269ec7dca29ad60a405bea2dce2c3994d`.
기존 source hash 목록에 이 URL/SHA를 추가 설명한 것이며 과거 frozen vendored 파일은 수정하지 않는다.

카메라 제약의 적용: 실제 return인 벽점만 occupied endpoint로 처리한다. semantic floor return은
clearing-only이므로 바닥점 끝을 장애물로 만들지 않는다. 원 Nav2도 marking/clearing observation을
분리한다. 4m/FOV/occlusion은 고정 upstream 센서의 책임이며 v6는 받은 ray 뒤로 외삽하지 않는다.
높이 있는 실물 카메라에서 2D로 투영한 ray의 모든 바닥이 보인다는 뜻은 아니다. 이번 평가기의
무한 높이 2D 장애물·가림 가정 아래 free를 추론하며 직접 가시 coverage와 구분한다.
