# 원본 대조와 치수 출처

- [Hiwonder MasterPi 공식 제품 사양](https://www.hiwonder.com/products/masterpi?variant=39783006961751):
  185×162×343mm. 저장소 `sim/masterpi_geometry_v3.py:63–79` 및 공식 dimension drawing과 일치한다.
  이 제품 envelope는 움직이는 팔/짐의 모든 자세에서 안전한 footprint라는 뜻이 아니다.
  이번 기존 2D 평가의 빈손 사각은240×200mm, padding20mm씩으로280×240mm다. 실제 운반 footprint는 미검증.
- [Nav2 inflation 기본 소스](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/inflation_layer.cpp#L95):
  radius0.55m, scaling10.0. [costmap defaults](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/src/costmap_2d_ros.cpp#L388):
  footprint_padding0.01m, resolution0.1m. 현재 pinned bringup YAML은 별도 예시0.7m/scaling3/resolution0.05m이므로
  라이브러리 기본값과 혼동하지 않는다. 이전 어댑터는0.5m/10/0.1m/0.02m다.
- [공식 inflation 설명](https://ros-navigation.github.io/mkdocs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/):
  inscribed radius 안과 외부 지수 감쇠 비용을 구분한다. 기존 `costmap.py:34–38`은253/254만 lethal,
  나머지 양수 비용은 NavFn이 허용한다. **문 폭에서2×inflation_radius를 빼서 불가능이라 판정하면 안 된다.**
- [Nav2 footprint 검사](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/src/footprint_collision_checker.cpp#L59):
  worldToMap→사각 외곽 LineIterator→최대 비용이다. 현재 어댑터는 raw grid에 fillConvexPoly한 사각
  전체를 검사한다. grid cell 좌표 양자화/정적 벽 .05m raster padding도 실제 연속 벽과 구분한다.
  어느 판정이 원인인지는 정지 snapshot으로 확인하며 알고리즘을 성공 후 맞추지 않는다.
- [RoundRobin cpp L46–60/87–92](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/plugins/control/round_robin_node.cpp#L46):
  마지막 child가 끝나면 `wrap_around=false`에서 SUCCESS 처리 이전에 break하여 FAILURE 반환.
  [header L93](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behavior_tree/include/nav2_behavior_tree/plugins/control/round_robin_node.hpp#L93)의 기본값도 false.
  어댑터 `public_navigation_persistent.py:140–151`과 동일. s4 backup 성공 뒤 abort는 이 pinned 분기다.
- [explore_lite explore.cpp L218–233/265–285](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp#L218):
  progress timeout 또는 ABORTED로 frontier blacklist, 다음 makePlan을 즉시 예약.
  어댑터 `public_navigation_persistent.py:96–103,170–203`은 frontier 조건에서 이 동작을 수행한다.
  **정적 B 목적지 Nav2 action은 exploration manager가 아니다.** B를 blacklist하고 다른 frontier로
  바꾸는 것은 원본 포트의 누락 수정이 아니라 baseline 임무 변경이다. 이번에는 하지 않는다.

코드 원본은 기존 third_party의 revision/hash와 비교하고, 추가 Nav24파일은 로컬 raw references에
보관했다. [출처 해시](references.json). Apache-2.0/BSD 저작권은 원문에 있으며 이번 진단은 runtime
원본을 새로 복사/변경하지 않는다. 첫 web URL404/cache miss 이후 HTTPS 원문/정상 공식 문서로 확인했다.

경로 존재 진단은 평가용 C-space 외접원 거리와 기존 A*를 사용한다. 원보다 사각이 작기 때문에
원 경로가 양의 여유를 갖는 것은 사각 통과의 충분조건이다. .025m 격자·.002m 이하 선분 표본,
거리함수의1-Lipschitz 성질로 `min sampled clearance − max spacing/2`를 연속 여유 하한으로 저장한다.
경로 없음/원 시작 충돌은 사각 불가능의 필요충분조건이 아니다. 실제 환경이나 actor에 쓰지 않는다.
