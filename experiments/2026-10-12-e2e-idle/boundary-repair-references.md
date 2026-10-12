# v211 원인과 수정 근거 (2026-10-12)

- raw: v208/v207 seed61001은 52.8–59.2 SIM에 complete B를 31프레임 검출했지만, 고정된 partial centroid와 0.59–0.65 m 차이로 `harness/e2e_goal_route.py:86`의 0.20 m 연결에서 탈락했다. 265–267 프레임의 투영 경계·원본 이미지 SHA는 `boundary-repair-replay.json`. 이미지에서 측정한 전체 경계와 부분 영역의 중심을 같은 점으로 취급한 것이 원인이다.
- 재관측: seed61003/61007은 3회 모두 `B_view_path_lost`; 실제 관측점 도착 없이 3-view 예산이 끝났다. 새 후보는 actual observation 3회, navigation failure 6회를 별도로 제한한다. 모든 target은 기존 known-free footprint/path 검사를 그대로 거친다.
- 고전 기하: [OpenCV intersectConvexConvex](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html)로 부분 관측 사각 범위와 실제 완전 경계의 겹침을 계산한다. 작은 영역 대비 20% 이상 겹침, 0.10 m 내 연속 3프레임은 DEV 가설값이며 논문에서 검증된 임계값으로 주장하지 않는다. 원래 RGB 경계·표식·자기 몸 가림 조건은 유지한다.
- 표준 복구: [Nav2 consistent replanning](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/trees/nav_to_pose_with_consistent_replanning_and_if_path_becomes_invalid/)는 실패 후 recovery와 최대 6회 navigation retry를 분리한다. 이 횟수를 유한 접근 재시도에 사용하며 costmap 삭제·외부 위치 보정은 적용하지 않는다. 원문 확인.
- 최근 연구: [Bajpai et al., 2025, §IV-A](https://arxiv.org/html/2506.13367v1)은 새 검출 segmentation과 투영으로 target centroid를 구하고 point-goal navigation으로 전환한다. 이는 미리 고정한 partial centroid가 아니라 현재 관측 기반 위치 갱신을 뒷받침한다. 논문은 RGB-D·known pose를 쓰므로 UGRP에서는 자기 RGB·명령 FK·자기 추정 pose만 사용한다. 확률 지도·VLM 방식 전체를 재현하지 않는다.
- 비교: association only / retry only / both, seeds61001–61003, 동일 v211 source. v208/v207 seed61001 baseline도 함께 제출. 이미 본 seed 재사용이므로 확증 코호트가 아니다.
