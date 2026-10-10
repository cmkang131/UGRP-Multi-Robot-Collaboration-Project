# egomap67: receive 연결 + 지나온 차체 영역 귀환 (DEV 사전등록)
- 같은 자기 B 체크포인트 63001–63006 × 기준/진행 lookahead/own-free+궤적/조합 = 24회; 100입자·접근270+귀환270초·.20m/5프레임 고정([등록](prereg.json)).
- eg66 한계: instance receive 우회로 on 30/30 로그 누락; own-free 경로 없음 7292/8106. 새 receive는 가속 base를 보존해 감싸며 첫 프레임 표식·180wall초 점검을 남긴다.
- VTR 제외: 승인3/164; 모드 모호82건 gap 중앙 −.0635<기존 .5, residual27건 중앙 .171>.15m, overlap22건 중앙 .545<.60; 기준 완화0([진단](diagnosis.json)).
- 궤적은 자기 과거 pose의 차체(.28×.24m) 영역만 귀환 costmap에서 free로 누적; 기존 footprint_cells 재사용, unknown 차단·벽 지도/관측 덮음 불변·정답 제어0.
- 자세 점프 구간 보간·미검증 지름길0. 추정 편향·팽창에 따른 단절은 남을 수 있어 경로 보장을 성공으로 가정하지 않는다. FSM/VTR은 이번 물리에서 off.
- 참고 자료: [Nav2 ObstacleLayer L494–525](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/plugins/obstacle_layer.cpp#L494), [convexFillCells L374–478](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/src/costmap_2d.cpp#L374), BSD 원문 확인; 현재 footprint 지우기를 자기 관측 이력에 보존하는 차이만 추가.
- 관련3파일32시험 초록: 가속 포함 6조건 실제 receive probe·FSM fallback·off 출력/스냅샷 bytes·unknown 틈의 경로 복구·점프 미연결·1257 동결 모듈 검사. 물리·재생0.
- oracle-x86 영속 runs만 사용,24개 전체 계획 후 load<51·메모리≥6GiB·초기 디스크≥20GiB에서 입장; 완료 즉시 회수·해시 확인. 현재 여유12GiB로 공간 확보 대기.
- 결과는 summary.json에 전24분모·초기 표식·B/귀환·접촉/거짓·과신·회전/반전·진행률·원본/SHA 기록; 미완료를 성공으로 세지 않으며 PR #405 DRAFT 유지.
