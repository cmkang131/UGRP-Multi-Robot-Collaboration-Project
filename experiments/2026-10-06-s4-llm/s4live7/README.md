# s4live7 DEV (research_result=false)
원인: 기존 높이 정지2건은 접촉22/22·COM49.8/47.5mm; 빔600×40×32mm·COM 오프셋16mm로 원점35mm는 COM약51mm.
1차 v170/SHA254ffd48: 초기8/8, on lease만료0/4·off4/4; 계속/목표/내려놓기 각0/4, 첫179–195mm·추가0m.
1차 S3 FLOOR_POSE_NOT_COMMANDED4/4 뒤 비활성 heartbeat36건 누락 확인; 원본·기존 [plan.json](plan.json)은 보존.
보완: 기본off/all_active_phase_rgb_heartbeat_v3, 모든 활성 단계에 단일 heartbeat; 종료·미만료·epoch 확인, S3 자기 종료 전달.
사전 등록 [plan-r2.json](plan-r2.json): 4조건×on/off×seed601, v171/workflow7.64, cap90SIMs, LP4, 부하<51·여유≥6GiB, 8개 동시.
평가 contact_com_v1은 양쪽 공통·기본off; S3 동결11파일 유지, GT는 평가만; 다음구간≥20mm·거리·목표(4.6,-2.1)·안정해제/낙하 n/4.
3–5분 건강 점검·완료마다 영속 runs raw 회수; 결과·원본 위치·sha256 [summary.json](summary.json); ENOSPC=HOST_ERROR.
참고 [Chubby §2.8](https://research.google.com/archive/chubby-osdi06.pdf), [Raft §8](https://raft.github.io/raft.pdf): 현재 세션 heartbeat 갱신·종료·만료 시 중지.
참고 [MuJoCo mjData](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html): xpos=body origin, xipos=COM; 제어 전달 없음.
