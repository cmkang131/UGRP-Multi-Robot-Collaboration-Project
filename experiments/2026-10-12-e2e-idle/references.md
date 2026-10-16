# 조사와 적용 범위 (2026-10-12)

- [Yamauchi 1997, A Frontier-Based Approach for Autonomous Exploration](https://www.robotfrontier.com/papers/cira97.pdf): known free/unknown 경계로 이동해 지도를 확장하는 기본 원리. 이번 조회는 검색된 원문 초록까지 확인; PDF 본문은 HTTP403으로 재열람 실패. blacklist TTL이 이 논문의 규칙이라고 주장하지 않는다.
- [explore_lite 원본 explore.cpp](https://github.com/hrnr/m-explore/blob/master/explore/src/explore.cpp#L167-L260): 후보가 없거나 전부 blacklist면 stop; 진전 timeout(기본30초)은 목표를 blacklist하고 재선정, ABORTED도 blacklist 후 재계획한다. 로컬 탐색 종료가 아직 B/경로를 못 찾은 상위 임무 완료는 아니다. 현재 코드가 stop을 무기한 hold로 남기는 통합 경계를 고친다.
- [Nav2 상세 recovery tree](https://github.com/ros-navigation/docs.nav2.org/blob/rolling/docs/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough.md): 재계획/문맥 복구가 실패하면 비용지도 clear와 spin/wait/backup의 한정된 복구를 순환한다. 여기서는 센서 지도 유지·기존 회전 재사용·회전시간 상한만 사용한다. 새 blind backup이나 측정 장애물 삭제를 추가하지 않는다.
- [Liu et al. 2025, Scientific Reports](https://www.nature.com/articles/s41598-025-97231-9): 지도 품질·무효 frontier 억제와 경로 길이/센서 범위/정보이득 비용으로 다음 목표를 선택한다. frontier가 사라진 상황과 임무 완료를 구분해야 한다는 설계 검토에 사용했다. 지도 평활화·MRTSP·새 학습법을 이번 범위에 넣지 않는다.
- [최근 공개 ROS2/Nav2 구현](https://github.com/mertgulerx/frontier_exploration_ros2): README의 목표 재선정·진전 실패 관리와 기본 off frontier 소진 preemption을 확인했다. 알고리즘 성능 수치는 재검증하지 않았다.

적용: 기존 탐색기/플래너 그대로, 기본 off30초 명령 watchdog·목표 제외 목록 epoch 만료·재계획·제한시간 재관측. blacklist와 visited의 일괄 만료는 이 프로젝트의 DEV 적응이며 upstream explore_lite에 TTL이 있다고 주장하지 않는다. 현재 지도 장애물·위치 추정·B 증거를 지우지 않는다. active recovery/B 확인 관측·실패·완료·운반 소유권 중에는 재시작하지 않는다. 임무 유한 budget은 유지한다.

# 원인과 증거 범위

`Navigator.select_frontier`는 `blocked`(blacklist+visited)와 계획 실패를 모두 제거한 뒤, `initial_scan_used`가 이미 true면 `finished=True`로 끝낸다. `PersistentNavigator.update`의 첫 guard가 후보 검색보다 먼저 실행되므로 새 영상과 지도 갱신이 계속되어도 목표를 다시 찾지 않는다. `command`도 zero twist를 반환한다. `make_goal`은 B+box 벤치마크 `_select`/`_arrival`를 비활성화했으므로 이 상위 경로에서 latch를 풀 일이 없다. binary stall detector는 translating 조건이 false인 hold에서 stationary_since를 비우며 `warming_up`/recovery idle로 돌아간다.

예: seed61001 r1은 13A/14B/15B 모두 80.4초 progress_timeout→blacklist, 80.6초 새 frontier, 83.2초 방문 직후 no_frontier 종료다. 지도 위치는 뒤에 소폭 보정되므로 사용자가 반올림 좌표로 계산한 정지시간과 명령 기준 시간이 다르다. 각 정지 직전 ±1초 ownmap 부분과 이전35초 이벤트, 원문 LLM 응답은 압축 audit에 보존했다. frontier 수·정확한 blacklist·costmap은 기존 로그에 없어 empty/모두차단/계획실패 비중을 단정하지 않는다. 새 토글은 frontier 수·계획 시도·도달 가능 수·제외목록 수와 복구 사유를 기록한다.

위치: `active_wall_mapping.local_pose`는 `PoseView.pose`의 own-start reporter 결과다. world bounds[-1.05,5.4]×[-3.15,1.45]와 직접 비교하면 안 된다. 평가 파일의 spawn 변환을 **보고서에서만** 적용해도17/32가 범위를 벗어나고 실제32/32는 안에 있다. `PulseOdometry.advance`는 발행 pulse 모형을 적분하며 unknown gate는 모션을 유지한다. `Reporter.measure`의 innovation gate는 일관성 검사이고 절대 위치/경기장 제약이 아니므로 누적 오차와 받아들인 지도 보정을 제거하지 못한다. 13A61003 r2 마지막 보정은1.466m가 허용됐고, 15B61003 r2는 reporter(3.524,-9.149), command odom(1.297,-3.982)이다. 각 오차 기여를 재생으로 완전히 분해하지 않았으며 이 PR은 위치 보정을 주장하지 않는다.

재현은22개 저장 종료상태 필드와 코드에서 추론한 finished/initial_scan_used를 복원하고, 역사 costmap 대신 명시적 known-free/no-frontier 입력을 준 상태기계 시험이다. off22/22 zero, on22/22 제한시간 회전 명령 재개; 실제 Robot.receive와 새 frontier 계획 경로는 별도 회귀로 연결했다. 실제 영상/물리 재생·정식 E2E/확증 성과는0이다.
