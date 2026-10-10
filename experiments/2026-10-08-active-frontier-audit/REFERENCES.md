# 그대로 재사용한 원본과 연결 범위

PR409 `ed2fa0e90f89ce759bc65c53a4ad36cbedcd48c8`; [diff0/해시](results/source-audit.json).
아래 파일은 새로 작성/복사하지 않고 이 브랜치에 이미 있던 동일 구현을 import한다.

|정책|PR409 재사용|원본 근거|
|---|---|---|
|navigation 0.05m|public_navigation_resolution.py:12,58–65|[Nav2 bringup YAML252/306](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_bringup/params/nav2_params.yaml#L252)|
|ray clear→hit mark|public_navigation_raytrace.py:23–59 / persistent.py:29–51|ObstacleLayer raytraceFreespace / costmap_2d.h Bresenham (기존 third_party BSD3 원문)|
|현재 footprint clear|public_navigation_unknown.py:54–80|[ObstacleLayer90–91,585–621](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_costmap_2d/plugins/obstacle_layer.cpp#L585)|
|unknown true / 여전히255|UnknownCostmap/UnknownNavigator + MonitorCore native bridge|[Navfn parameter42](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_navfn_planner/src/parameter_handler.cpp#L42)|
|frontier cluster/ABORTED blacklist|public_navigation_unknown.py:131–165 / monitor.py:101–117|[explore.cpp179–280](https://github.com/hrnr/m-explore/blob/26d4183a4fe119a0f83685ce3e06370c0c4d21d9/explore/src/explore.cpp#L179)|

Nav2 Apache2/BSD3, m-explore BSD3 고지와 pinned SOURCES.json 그대로 보존.
로컬 고정 원문 내용/해시와 PR409 README/REFERENCES를 읽기 전용 대조했다. 새 ROS/venv 설치0.
현재 RBPF 삽입 감사는 `rbpf_motion_gate.py:32–73`(1m/0.5rad 보류),
`rbpf_composition.py:37–42`(거부도삽입), `rbpf_rejection.py:187–225`(가중/재표본 분리) 대응.
GMapping 출처는 experiments/2026-10-08-rbpf-insertion 및 rbpf-turn-audit 원문 기록을 유지.

ActiveMapper에서 navigation .1 literal만 PR409 RESOLUTION=.05 선택으로 연결하고,
프런티어/blacklist 함수에는 실제 costmap.resolution을 전달한다. 기본off는 .1 그대로.
알고리즘/해상도 탐색/관측 문턱/미래 footprint 삭제를 새로 구현하지 않는다.
