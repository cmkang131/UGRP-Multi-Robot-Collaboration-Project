# vote_ref_v1 (v314/v315): GO/ACK 출력 단축

- 근거: `sdk-llmlat-report`(VM3 최근 29실행·386호출): Gemma 지연은 출력 토큰과 비례(Spearman 0.65), wait_go_ack 출력 중앙 138토큰·지연 중앙 5.7 s(최대 14 s). route_vote가 order_id·64자 route_hash·grip_epoch·seg·peer_go_ref를 되풀이함.
- 구현(`harness/e2e_vote_ref.py`, route_handle typed_ref_v1과 같은 패턴): 모델은 `{"kind":"route_vote","choice":"GO"|"ACK","vote_ref":"<dialogue.vote_ref>"}`만 쓴다. `vote_ref`는 현재 투표 창(key=order,route_hash,grip_epoch,seg)의 sha256 앞 6자리(`v`+6hex)로 호출 시점 view에 들어간다. 호스트는 호출 시점에 캡처한 view로 전체 route_vote를 만들고(새 정보·정답 없음), `check_action`은 확장 뒤 그대로 돈다. 참조 불일치·창 닫힘(epoch 교체/key 없음)·전체 형식 직접 입력은 거부되어 기존처럼 continue.
- 자연어 messages와 연구 변수는 변경 없음. 영어 프롬프트(시스템 문장·action_message_contract)만 갱신, 기본 off(`--vote-ref off|v1`). off이면 view·프롬프트 바이트 동일(시험으로 확인).
- 번들: e2e18-v314 = v313(+hysteresis) + vote_ref v1, e2e18-v315 = v312 + vote_ref v1. 각 workflow 등록 `configs/simulation_workflows.d/e2e18_v314|315.json`.
- 예상(미측정): route_vote 출력 ~138→~50 토큰, 기울기 0.039 s/토큰 기준 지연 −3 s 안팎. 해시를 정확히 되풀이하는 능력 시험은 사라지므로 비교는 별도 표시.
- 검증 범위: 단위·번들 시험만(`tests/test_e2e_vote_ref.py` 10개, 기존 dialogue·acquire_standoff 39개 통과). 실제 LLM 호출·시뮬레이션 실행은 확인 안 됨. VM 제출 없음.
