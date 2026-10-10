# s4live7 DEV 완료 (research_result=false)
원인: 기존 높이 정지2건 접촉22/22·COM49.8/47.5mm; 빔600×40×32mm·COM offset16mm, 원점35mm=수평COM51mm.
최종 v171/SHA369fd854·workflow7.64, [plan-r2.json](plan-r2.json): 4조건×on/off×seed601, cap90SIMs, LP4, 8개 동시.
기본off/all_active_phase_rgb_heartbeat_v3: 모든 활성 단계 단일 heartbeat, 비활성/종료 차단·자기 S3 종료 전달; 평가 guard는 양 군 공통·기본off.
초기8/8·갱신54/54·종료후갱신0; lease만료 on0/4·off4/4, 첫운반180–195mm·추가0m, 계속/목표/안정해제 각0/4.
남은 on4/4 FLOOR_POSE_NOT_COMMANDED·PARTNER_ABORT, 낙하0/4; 다음 후보는 자기 발행 바닥 펄스/저장 파지자세 정합성과 후속 재관측·재집기.
모델171회·보고토큰1,253,682·응답평균5.08s/최대15.72s·승인메시지50, API오류0; 결과·원본 위치·sha256 [summary.json](summary.json).
1차 v170/SHA254ffd48·원래 [plan.json](plan.json)·raw 보존; 비활성갱신36건 및 on표기v1/실제argv·raw v2 오류 공개. 영속 runs raw 16개 전부 회수·해시확인.
참고 [Chubby §2.8](https://research.google.com/archive/chubby-osdi06.pdf), [Raft §8](https://raft.github.io/raft.pdf): 현재 세션 heartbeat 갱신·종료·만료 시 중지.
참고 [MuJoCo mjData](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html): xpos=body origin, xipos=COM; GT는 평가만, S3 동결11파일·weld off 유지.
