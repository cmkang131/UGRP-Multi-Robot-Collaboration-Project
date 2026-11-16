# s4live5 — 실제 LLM 빔 첫 운반 DEV
S3 #416 `60eaf042` 통합, 실행 `4ea22948`·v168/workflow7.61.0(최댓값 다음 예약); 기본 경로 유지·새 실행만 opt-in.
4조건×seed601·90 SIM초·dev_light·LP4·weld OFF, oracle-x86 4개 동시; [r1](plan.json)→[r2](plan-r2.json)→[r3 고정 명령표](plan-r3.json).
최종 no_comm/peer_ko/leader_ko/structured 각각 claim·GO/ACK·동시출발·운반≥20mm **1/1**(183.4/183.9/194.9/195.1mm); 정답 접촉/좌표는 사후 평가만.
같은 S3 자기 RGB/발행 명령 단계 이력으로 시작한 구간 시험; 내려놓기 판정 제외·research_result=false·배송/E2E/협업효율 결론 없음.
각 모델호출16/19/17/16, 응답평균5.30/6.43/6.01/8.60초, 총토큰106131/135684/122620/121626, 메시지발행0/10/11/5(전달0/9/9/5); r3 호출 각2 포함.
초기 건강점검4/4(108–130초), 최종EXIT0 4/4; 뒤에는 carry_decision이 held lease를 갱신하지 못해4/4정지. 형식오류1·늦은ACK2 거부·종료후응답8 제어미반영.
r1 이력누락 초기중단4/4·r2 비동기GO None 오류4/4 보존; 관련38/후속6/최종14 pytest 통과(중복 합산 안 함). 키흔적0·전용SSH 종료·Mac 물리/MuJoCo렌더0.
[summary n/N·원본·SHA](summary.json): raw=/Users/changmin/projects/ugrp/outputs/oracle-runs/s4live5-*; 108/108 호출·216 이미지SHA·32407파일/976683060바이트 대조. PR425 초안·병합은 감독.
첫 실제 LLM 빔 성공 예외로 [TensorBoard](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Freported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fsim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_latency_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fplumbing_carry%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcarry_xy_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fmessages_sent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ftokens_total%22%7D%5D&smoothing=0&runFilter=%5E1010-s4live5-first-beam%2F#timeseries) 12run/240scalar·저장RGB4영상 검증; 뷰어 검증후 종료·재열기는 summary. 다음 후보: 운반+시각확인 결합/별도 monitor 토글(제안).
