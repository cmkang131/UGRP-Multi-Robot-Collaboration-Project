# egomap66: 고정 36회 DEV 비교 완료
- [사전등록](prereg.json) 697947cd / 실행 af2eaa43, oracle-x86, 63001–63006×6조건·100입자·B/귀환 각270초·.20m/5프레임; 새 확증 아님.
- B/귀환: 기준 2/6·0/6, lookahead 2/6·0/6, VTR 2/6·0/6, own-free 2/6·0/6, FSM 0/6·0/6, 조합 0/6·0/6; 거짓 귀환은 조합 2건.
- 회전%/반전: 기준 60.0/1271, lookahead 52.2/762, VTR 25.4/923, own-free 27.9/1033, FSM 55.4/1357, 조합 13.3/276; 벽 접촉 순서 1/1/0/0/0/1.
- VTR 정합 3/164·귀환 대기 7950/8106프레임, own-free 경로 없음 7292/8106; 조합 거짓 선언 실제 시작거리 .510/.342m. 미채택·결과 후 변경 0.
- 연결 한계: scalar_rays_v1 인스턴스 receive가 새 클래스 receive를 우회(물리 없는 소스 probe 확인); on 30/30 진행률 로그 누락·FSM 재관측 fallback 일부 미실행. 정확한 free-path 진행률은 미측정.
- 로컬 기존 32시험 초록(이 래퍼 조합 미포함); off 6seed×기존 6파일=36/36 전체 바이트 동일·첫60초 1800/1800행 동일; 초기36/36 정상, HOST/차단/물리 재시도 0.
- 참고 자료: [Nav2 RPP](https://github.com/ros-navigation/navigation2/tree/jazzy/nav2_regulated_pure_pursuit_controller), [NavFn](https://github.com/ros-navigation/navigation2/blob/main/nav2_navfn_planner/src/navfn_planner.cpp), [stateful checker](https://github.com/ros-navigation/navigation2/blob/main/nav2_controller/plugins/simple_goal_checker.cpp) 원문 확인; 적응 차이는 prereg.json.
- 참고 자료: [VT&R 귀환 §III](https://arxiv.org/html/1809.05757) 원문 확인; [Furgale–Barfoot 2010](https://doi.org/10.1002/rob.20342) 초록만 확인(전문 미확인). 다음 후보=가속 receive 연결/실제 준비 상태 회귀시험 후 시각 확인·free 연결 진단.
- [판정·원본·SHA256](summary.json): outputs/oracle-runs/egomap66-batch 전36회 회수·86751파일 해시 일치; 전송 오류1회 자동 복구, 물리36회 유지. PR #405 DRAFT.
