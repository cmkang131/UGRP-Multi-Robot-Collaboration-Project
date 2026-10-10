# egomap66: 자기 기억 경로 추종 비교 (DEV, 결과 전 고정)
- egomap65 종료: 100입자 기존 B 2/6·귀환 0/6, 수정 B 0/6·hold 67.3%; 수정 heading 미채택.
- [사전등록](prereg.json): 63001–63006, 기준선+4개 단독+조합=36회; 100입자·B/귀환 각270초·.20m/5프레임 동결.
- 네 토글 기본 off; 조합=progress_lookahead+return_own_free_astar+arrival_verify_fsm. 자기 관측/기억만 제어에 사용.
- RPP .6m 보간·순서 보존 투영, 현재 구간의 기존 CSM, unknown 차단 NavFn, 거리수렴 후 동일 B 현재 시각 확인.
- 단안/펄스 제약 차이·원문 위치/해시·전체 명령·초기점검은 prereg.json, 판정 n/N·원본·SHA256은 summary.json.
- oracle-x86 부하<51·여유≥6GiB에서 한 묶음 제출; 각 실행 180초 후 SIM/위치/명령/예외 확인, 이상 실행만 중단·기록.
- 참고 자료: [Nav2 RPP](https://github.com/ros-navigation/navigation2/tree/jazzy/nav2_regulated_pure_pursuit_controller), [NavFn](https://github.com/ros-navigation/navigation2/blob/main/nav2_navfn_planner/src/navfn_planner.cpp), [stateful checker](https://github.com/ros-navigation/navigation2/blob/main/nav2_controller/plugins/simple_goal_checker.cpp) 원문 확인.
- 참고 자료: [VT&R 귀환 §III](https://arxiv.org/html/1809.05757) 원문 확인; [Furgale–Barfoot 2010](https://doi.org/10.1002/rob.20342) 초록만 확인(전문 미확인).
- 상태: 코드/로컬 시험 준비 중, 물리 결과 없음; oracle-x86 SSH 시간 초과 확인(기존 결과를 새 결과로 대체하지 않음).
