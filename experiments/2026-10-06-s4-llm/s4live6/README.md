# s4live6 DEV (research_result=false)
기존 raw: 4/4 첫 운반 성공 후 10 SIM초 lease 만료; continue는 OVER_BUDGET, set_down 승인에도 갱신 누락.
후보: 기본 off / accepted_carry_reply_v1; S3 v165 60eaf042 물리·정렬·채널·프롬프트 동결.
사전 등록·8개 이름/명령/seed601: [plan.json](plan.json), v169/workflow7.62; 같은 SHA로 한 묶음 제출.
승인된 carry 응답의 현재 epoch·자기 RGB 요청 나이<10s·미만료 lease만 갱신; 거부·지연·이탈은 연장하지 않음.
판정: 다음 구간 접촉 운반≥20mm / 등록 목표 XY±20mm / 안정 내려놓기 및 낙하; 각 on/off n/4.
건강 점검: 240wall초 안 프레임·SIM 증가, 실제 팔/차체 이동, 정상 명령·집기/상승 진입.
결과·원본 위치·sha256: [summary.json](summary.json); ENOSPC는 HOST_ERROR, 메모리 거부는 동일 명령 재제출.
참고: [Chubby §2.8](https://research.google.com/archive/chubby-osdi06.pdf)의 승인된 KeepAlive 응답 갱신과 만료 시 중지.
참고: [Raft §8](https://raft.github.io/raft.pdf)의 heartbeat 확인·timing lease; 여기서는 공통 SIM시계의 2자 배리어이며 합의/파지 증명 아님.
