# s4live7 DEV 사전 등록 (research_result=false)
원인: s4live6 높이 정지2건은 마지막0.5s 양측 접촉22/22, COM49.8/47.5mm, 양쪽lower; 미지원 낙하0/2.
후보: lease off / all_phase_rgb_heartbeat_v2(기본 off); 평가 contact_com_v1(기본 off)는 두 군 공통, cyan·S3 제어기 동결.
단일 heartbeat: 모든 단계의 정상 검증·공개된 fresh 자기 RGB 응답, 같은 epoch·미만료 lease; 명령 거부와 별개이며 이탈·unknown은 정지.
사전 목록 [plan.json](plan.json): 4조건×on/off×seed601, v170/workflow7.63, cap90SIMs, LP4, 8개 동시, 부하<51·여유≥6GiB.
판정: 다음 구간 접촉 운반≥20mm, 계속 운반 거리(m), 고정 목표(4.6,-2.1)±20mm, 안정 내려놓기·미지원 낙하; 각 n/4.
제출후3–5분: 예외·SIM/프레임 증가·실제 이동·정상 명령·집기/상승 점검; 이상 실행 중단/EXIT 기록.
raw는 영속 ~/ugrp-sim/runs, 완료마다 즉시 회수; 결과·원본 위치·sha256 [summary.json](summary.json); ENOSPC=HOST_ERROR.
참고: [Chubby §2.8](https://research.google.com/archive/chubby-osdi06.pdf), [Raft §8](https://raft.github.io/raft.pdf): heartbeat 응답으로 현재 lease 갱신, 만료 세션 부활 금지.
참고: [MuJoCo mjData](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html): xpos=body frame, xipos=COM; 평가만 읽고 제어에는 전달하지 않음.
