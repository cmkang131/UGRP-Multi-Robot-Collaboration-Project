# 원문 확인 및 줄 대조

Nav2는 기존 v7과 동일 commit `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`,
m-explore `26d4183a4fe119a0f83685ce3e06370c0c4d21d9` 고정.
새 원본9파일은 `third_party/mapfree_navigation_monitor/SOURCES.json`에 URL/SHA256,
Apache-2.0 전문과 저작권 보존. 기존 ROS navigation/m-explore BSD-3 원본도 유지.
새 venv/의존성 설치 없음. 문서의 rolling값 대신 아래 commit의 코드·배포 설정을 적용한다.

|원본 고정 링크/줄|기존 어댑터와 차이/적용|
|---|---|
|[nav2_params.yaml L514–546](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L514)|FootprintApproach, 동적 published_footprint,1.2s/.1s/6점,timeout1s. 예제의 PolygonStop를 기본 다각형으로 오인하지 않음. v7에는 별도 monitor 없음.|
|[polygon.cpp L339–389](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/polygon.cpp#L339)|현재 내부점 먼저 검사, Euler projectState로 이동, `time=0;time<=1.2;time+=.1` 원 루프의 time 반환 그대로. TTC off-by-one도 임의 수정하지 않음.|
|[kinematics.cpp L22–65](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/kinematics.cpp#L22)|pose+=velocity*dt, velocity 회전 후 점의 역변환. GT 상태 사용 없음.|
|[collision_monitor_node.cpp L454–465,608–638](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/collision_monitor_node.cpp#L454)|유효하지 않은 source는 STOP. APPROACH는 TTC/1.2로 속도 조정.|
|[source.cpp L179–199](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/source.cpp#L179)|나이>1s만 invalid. no-return(빈 점들)의 유효 프레임과 누락 구분.|
|[BT L16–34](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml#L16)|1Hz replan은 `harness/public_navigation_persistent.py:250`에 이미 있음. 유지.|
|[nav2_params.yaml L245,301](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L245)|local5Hz/global1Hz. 기존 단일지도10Hz→local5Hz, 별도 global 복제는 생략. 입력 센서3s 주기는 변경하지 않음.|
|[explore.launch L7–13](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/launch/explore.launch#L7)|planner.33,progress30,potential3,gain1,min.75. 기존 bridge.cpp:28의1/1/.1과 다름. 원 search.cpp 그대로 별도 ABI에서 계수만 공급.|
|[explore.cpp](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp)|code fallback(freq1,potential.001,min.5)과 위 배포 launch값 구분. v8은 배포 launch를 일관되게 사용. 실패 callback 즉시 makePlan, timer로 주기적 makePlan.|
|[ROS Time.msg](https://github.com/ros2/rcl_interfaces/blob/rolling/builtin_interfaces/msg/Time.msg)|GitHub API로 확인(sec int32,nanosec uint32); docs.ros2.org는 접근 차단돼 근거로 쓰지 않음. 유한 2D 평가 clock을 정수 tick으로 만들고 B detector/time gap 문턱은 유지.|

[공식 collision monitor 설명](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/)
확인. 좁은 카메라 시야에 없는 장애물을 감지한다고 보장하지 않는다.

## 구현 파일 대조

- `harness/public_navigation_monitor.cpp`: 기존 v7 ABI를 별도 DSO에 포함하고
  FrontierSearch(3,1,.75)만 별도 symbol로 공급. 원 kinematics.cpp를 직접 컴파일.
  polygon.getCollisionTime와 geometry_utils.isPointInsidePolygon 본문을 ROS 자료형만
  평면 배열로 바꿔 포트. polygon/getData/timeout/APROACH 원문과 순서·부등호 유지.
- `harness/public_navigation_monitor.py`: own-camera 점의 own-odom 저장/현재 base 역변환,
  sensor-timeout STOP, TTC 비례 속도; `.33Hz` 탐색 timer를1Hz planner와 별개로 서비스.
  기존 2s 관측 대기에는 controller 콜백이 없으므로 만료 timer는 다음 관측/행동 콜백에서
  실행한다(ROS executor 전체 재현이 아닌 유한 2D 어댑터 한계). 새 관측/접촉/clear에는 즉시
  costmap invalidation, 그 외5Hz 갱신. 타인 지도·GT 물체를 점으로 채우지 않음.
- `code/integer_episode.py`: old run_persistent.episode의 관측/행동 end 시간 계산만 정수
  tick으로 교체, 선택적 monitor 로그 추가. B·접촉·false passage 채점 식은 그대로.
- `code/run_monitor.py`: 기존 seed/world draw split은 원래대로 유지하고 결과 evidence
  split만 development로 표기. 모듈·센서·정적 기준선·GT pose bridge는 고정 v7 합성 재사용.
