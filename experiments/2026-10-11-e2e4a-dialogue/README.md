# e2e4a 대화 계약 (기본 off)
- 자기 지도 어댑터의 경로·map_version·B RGB 출처·SHA256을 실제 OwnRoute 메시지로 전달한다.
- r2 수신 경로 승인 뒤 claim 허가; 현재 order_id/route_hash/grip_epoch/seg의 양쪽 GO/ACK만 운반 허가.
- 재파지 뒤 새 epoch 필수, 무효 정상 응답은 로봇·현재 key당 한 번 새 요청으로 재질의.
- no_comm B 보고·승인·claim 차단; peer_ko 직접, leader_ko 지휘자 중계, structured 정형 확장.
- 관련 시험71/71(새 계약24/24), 합성 응답·실제 scheduler/수신 원장; 실제 모델·물리·렌더0.
- egomap67 어댑터·실제 운반 연결/E2E는 후속 단계. 이번 변경은 대화 허가만 검사한다.
- 판정·작은 압축 원본 경로·전체 파일 검증·출처: [summary.json](summary.json).
