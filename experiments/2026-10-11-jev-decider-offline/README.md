# Jev를 행동 결정기로 쓸 수 있는가 — 오프라인 평가 (사전 등록)

2026-10-11. 시뮬레이션 없음. 질문: 자연어 대화는 LLM(Gemma 4 31B), 행동 **선택**은 Jev가 맡는 분업이 가능한가. Gemma와 의견이 다르다는 이유로 Jev를 기각하지 않는다. Gemma 일치율은 기술 통계일 뿐 성공 기준이 아니다. 기준은 아래 고정한 라벨 집합이다.

## E2E에서 로봇 LLM이 실제로 고르는 행동 (코드 근거)
`harness/e2e_dialogue.py` `check_action`: `continue`, `claim`, `approve_route`(r2만), `route_vote` GO/ACK. 그 밖은 `E2E_DIALOGUE_ACTION_NOT_CONNECTED`. 이동 자체는 코드(`e2e_live_transport`)가 하고 `continue`는 운반을 막는다. 파이프 계층(`pair_llm_decisions.HOOK_ACTIONS`, `e2e_setdown_relook`)에 `carry_decision`(continue/set_down), `post_look_decision`(regrasp/look_again)이 있다. 별도 묶음(carry, postlook)으로 평가한다. 저장된 실제 E2E 요청 54건은 전부 t≤4 s, key=null이며 응답은 전부 `continue`였다. 한 결정 지점만 다룬다. 그래서 라벨 묶음은 합성이다.

## 고정 자료
- `suite.json`: 64개 상태, 결정 지점 10종, 각 상태의 허용 행동 **집합**과 규칙 인용(`rules`). 라벨 근거: hard_contract 51, inferred_from_contract 9(규칙에서 추론, 하드 검사 아님), ambiguous 4. 메시지 민감도 쌍 22(change 6, no_change 14, either 2).
- 분할: `dev` 31 / `holdout` 33. 같은 기준 상태의 변형은 같은 쪽에 둔다. 소금 `s0:`, 그룹 해시로 코드가 고정. 개선 표현은 dev에서만 조정하고 holdout에서 한 번만 시험한다. holdout 개별 실패는 개선안 확정 전에 열지 않는다.
- 구조적 후보 수(`n_structurally_admissible`): 의미 술어만으로 남는 후보 수. 1이면 코드가 사실상 답을 정한 경우. "후보 2개 이상 중 정답" 비율을 따로 보고한다.
- 규칙 기준선은 구조 필드만 보고 피어 텍스트를 무시한다. 하드 라벨은 규칙으로도 풀린다(테스트로 확인). Jev/Gemma가 규칙보다 나을 수 있는 곳은 피어 메시지로 답이 바뀌는 쌍뿐이다.

## 정책·반복
Jev(jev-1.13.0, 선택 API): 표현 2(raw, semantic) × 3회. Gemma(google/gemma-4-31b-it, DeepInfra 고정, temp 0.2 = E2E와 같음): 같은 두 표현 × 3회. 같은 텍스트 상태·같은 선택지. E2E 실제 Gemma 프롬프트(이미지·메시지 생성 포함)와는 다르다. 동일 입력 비교일 뿐이다. 호출 상한 1,500(HTTP 시도 포함, 재시도 2회까지 기록).

## 판정 기준 (결과 보기 전에 고정)
결정 지점 X에서 Jev를 결정기로 쓸 수 있다 = (a) 그 지점 하드 라벨 상태의 허용 행동율 ≥ 90%, (b) 후보 ≥2 구조 상태에서도 ≥ 90%, (c) 반복 안정성(3회 동일) ≥ 90%, (d) 해당 쌍이 있으면 no_change ≥ 80%, change ≥ 80%. 하나라도 모자라면 "아니오" 또는 "표현 의존"으로 적고 원인을 진단한다. 신뢰도는 (정답 vs 오답) AUROC>0.7이고 모호 상태에서 낮을 때만 게이트로 권고한다. 표본이 작아 n/N을 항상 함께 적고 통계적 유의성은 주장하지 않는다.

## 실행 기록
- 라벨·코드 고정 커밋: 609a54c08a28f8ceefbb8a0c462a91c1a013685c
- suite.json sha256: 6a983fa97ddfae9793abeebf7cda36d55caf180c80f491a018623b763dc64b4b
