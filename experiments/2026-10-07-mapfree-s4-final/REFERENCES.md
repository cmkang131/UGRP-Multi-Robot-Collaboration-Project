# 원본 코드 대조

고정된 원본/라이선스는 `third_party/mapfree_navigation*`에 보존돼 있다. 이번 확인은
새 ROS 설치/실행이 아니라 원문과 어댑터의 대응 검사다. web 도구의 raw URL cache miss 뒤
공식 GitHub HTTPS 원문을 직접 받아 [references.json](references.json)에 SHA256을 기록했다.

| 원본 | 어댑터 | 판정 |
|---|---|---|
| [explore.cpp L190–208](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp#L190): frontier 없음/전부 blacklist일 때 stop | `public_navigation_persistent.py:170–203` | 동일: 다음 nonblacklist 후보를 모두 시도한 뒤 finished |
| 같은 파일 L218–233: progress timeout→blacklist→makePlan | `public_navigation_persistent.py:176–184` | 동일. 타임아웃30s 유지 |
| 같은 파일 L265–285: ABORTED→blacklist→다음 makePlan | `public_navigation_persistent.py:96–103` + `PublicNavigator.abort` | frontier 모드에서 failed로 종료하지 않고 다음 목표. 새 단위시험으로 다음 후보/소진을 검증 |
| [RoundRobin L46–60,87–92](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/plugins/control/round_robin_node.cpp#L46): 마지막 child에서 wrap=false이면 break→FAILURE | `public_navigation_persistent.py:140–151` | 동일. static B action의 실패이며 frontier 탐색 전체 종료 분기가 아님 |
| [Nav2 bringup YAML L252,306](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L252): local/global resolution0.05 | 새 `public_navigation_resolution.py:12` | v5만0.05, 원 library Costmap2DROS 기본은0.1(L388 이후)임을 구분 |
| [StaticLayer L225–248,256–262](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/static_layer.cpp#L225): 입력 지도 resolution으로 resize, occupancy 해석 | `authored_inputs` + 기존 `Costmap(...grid.resolution)` | 처음부터0.05m 지도를 생성.0.1m lethal cell을 복제/보간해 세분화하는 것이 아님 |
| [StaticLayer L298–315](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/static_layer.cpp#L298): lethal/unknown 변환 | 기존 costmap0/254/255 유지 | 실제 벽/unknown을 임의 free로 바꾸지 않음 |

## 우리 입력 때문에 필요한 어댑터

Nav2는 OccupancyGrid를 소비하며 벡터 장면을 직접 rasterize하지 않는다. 기존 `run_grid.py:116–137`의
**authored 정적 지도**→자기 초기 좌표 격자 변환만 새 모듈에 보존하고, 명시된 해상도0.05 및
cell-half 여유0.025로 일관되게 계산한다. 이것은 Nav2 원문 함수라고 주장하지 않는다.
동적 물체 정답/현재 GT 자세는 넘기지 않는다. static baseline의 고정 지도와 초기 정렬 예외는 기존과 같다.

v4 0.1m 셀2개는 실제 wall_divider_1/wall_corridor_1의 일부와 겹친다. 그러므로 단순 반올림 버그나
완전히 허구인 벽으로 지우면 안 된다. 사각 footprint의 연속 기하 여유가 있음에도 해당 셀 전체가
lethal인 이산화 차이를 원 bringup 해상도 한 값으로 비교한다. 새 몸체 축소/문 확대/guard 해제 없음.
기존 `.05m` static raster 여유는0.1m의 절반이었으며 v5는0.05m의 절반을 쓴다. 실제 벽 두께는 불변.

`ResolutionActor`는 v4의 NavFn/outline/follower/recovery를 그대로 합성한다. 내부 dispatch는v4,
사용자 선택 및 실행 provenance는v5이고 grid/costmap만0.05m다. frontier 원본 규칙과 RoundRobin은
수정하지 않는다. 기존 runner의 grid 메타데이터 literal0.1만 **첫 저장 전에**0.05로 기록하는 어댑터를
두었으며 raw를 저장한 뒤 고치거나 cells를 재색인하지 않는다.

기존 BSD/Apache 라이선스·저작권 고지를 유지한다. 외부 라이브러리/venv 변경0, native core bytes 불변.
