# s4live5 — S3 v165 기반 실제 LLM 빔 운반 DEV
S3 #416 `60eaf042` 위에 통합, r1 v166/7.59.0→r2 v167/7.60.0→r3 v168/7.61.0; coarse/fine abc·joint_pan·동기 펄스 GO+.20초를 그대로 연결(기본 경로 유지).
4조건 no_comm/peer_ko/leader_ko/structured ×seed601,90 SIM초·dev_light·LP4·weld OFF; [r1 목록](plan.json)·[r2 목록](plan-r2.json)·[r3 목록](plan-r3.json) 4개 동시 oracle-x86 제출.
판정 각 n/1: 두 claim→각 GO/상대 ACK→같은 .05초 tick 공동 출발→양 로봇 양측접촉·COM>.06m 운반>=20mm; 내려놓기는 관측만(판정 제외).
no_comm 고정 상태신호만, 나머지 기존 대화 채널; 실제 모델 응답만 제어에 연결, 접촉·좌표 정답은 평가/초기 건강점검에만.
기존 Mac 감사 프록시+유한 SSH loopback; 키를 읽거나 서버로 전달하지 않음. 요청/응답 텍스트·이미지 SHA·usage/latency·실패·메시지·명령 연결 보존.
사전 등록/결과 [summary.json](summary.json), raw=/Users/changmin/projects/ugrp/outputs/oracle-runs/s4live5-*; 3~5분 초기 프레임·SIM·움직임·명령·단계 점검 필수.
r1 초기중단4/4(자기 단계 이력 누락→227mm/구형503mm 비교), r2 초기점검4/4·집기상승 후4/4 스케줄러 None 오류, r3는 bool predicate 수정 후 실행 전·research_result=false·PR425 초안; DEV TensorBoard 생략(#426). 근거: [GO 준비/결정](https://www.microsoft.com/en-us/research/publication/consensus-on-transaction-commit/)·[SSH loopback](https://man.openbsd.org/ssh).
