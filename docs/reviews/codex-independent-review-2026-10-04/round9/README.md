# UGRP 9차 연속 검토 — 2026-10-04 체크포인트

**새로 확인한 것은 평가 기록의 제한시간 검증 공백(P2)과 claim 재시도 기록의 귀속 오류(P3)입니다.** 현재 영상 정책과 모델 요청의 시간 의미에서는 검증한 설계 한계도 찾았습니다. 버그와 설계 선택을 구분해 아래에 적었습니다. 검토는 이 게시 뒤에도 [다음 backlog](backlog.md)로 이어집니다.

| 우선순위·판정 | 이번에 확인한 사실 | 바로 이어갈 판별 |
|---|---|---|
| **P2 · 신규 · P06 candidate 평가** | 고정 bundle은12초인데 raw referee 없는 초기 실패의 writer 인자가6/24초면, VERIFIED/VALID로 통과하며 inspector PAR2가24 대신12/48이 됩니다. 성공 분모는 유지됩니다. | referee 유무와 무관하게 admitted horizon을 대조. 실제 관측 종료시각은 별도 보존. [평가 감사](evaluation.md) |
| **P3 · 신규 · 현재 #371 기록** | claim A의 transient retry2회가 취소/교체 뒤 곧바로 수락된 claim B의 `retried_ticks`에 붙습니다. 누적 refusal_total2는 정상입니다. | permit별 횟수와 누적 횟수를 구분. 실제 motor·비용 영향은 입증하지 않았습니다. [control 감사](control.md) |
| **설계 적용 범위 · 현재 #363** | 같은 운동을0.05초마다 lease 갱신하면 eligible scan마다 new view로 세어 temporal 반복감쇠가 달라집니다. column 감쇠는 유지됩니다. | continuous lease 갱신과 별도 작은 pulse를 같은 new-view 기준으로 볼지 먼저 고정. [vision 감사](vision.md) |
| **provenance/시간 의미 공백 · #371** | 합법적 lane overlap에서 t8 요청에 t9.5 declared-send ID가 보입니다. 또한 시작 snapshot에 없던 추측 reply_to ID가 release 전에 전달되면 relay가 수락할 수 있습니다. | pending reservation·SIM release·실제 최종 요청 포함을 구분. 내용 누출이나 실제 모델 사용/효과를 측정한 것은 아닙니다. [runtime 감사](runtime.md) |
| **한정 반박·통과** | STATUS144개 정상 조합과 철회·만료·재시간화/다른session 거부는 예상대로 동작했습니다. 현재 CLI의 단순 source/map/calibration/cap 불일치 허용 의심도 반박했습니다. | 전체 물리 성공 인증으로 확대하지 않음. [control](control.md), [identity](identity.md) |

**현재 진도와 구별:** 최신 #363 de03 README의 저자 보고에서는 HIGH edge 기준 구간을 통과했고 staged 실행의 현재 막힘은 SELF_UNCERTAIN/POSE_UNCERTAIN입니다. 이 공개 보고를 새 독립 물리 재현으로 세지 않습니다. 아래 ROI/반복감쇠 한계를 그 현재 실패의 원인이라고 연결하지 않습니다.

P06 candidate는 현재 pair live runner에 연결된 경로가 아닙니다. 따라서 첫 E2E blocker로 승격하지 않습니다. 같은-tick peer-abort와 ROI 잘림은 기존 finding이며 새 개수에 넣지 않습니다.

## 막힌 해석에 도움이 되는 연구 검토

[요청 단위 정보의 출처와 시간](research.md)은 메시지→최종 request→action release를 결합해 가능한 설명을 먼저 거르는 방법을 제시합니다. `decision_sources` 자기보고나 reply_to 그래프만으로 정보의 실제 사용·인과효과를 증명하지 않습니다. [직접 읽은 primary5개와 적용 가정](research-sources.md)을 구분했습니다.

[PF 반복감쇠 이론](pf-theory.md)은 현재 지수의 합이 effective sample size와 같아도, 정적 등상관 Gaussian의 정확 joint likelihood와 같아지는 것은 아님을 작은 수학 반례로 보여줍니다. 현재 구현이 exact Bayes를 약속한 오류라고 주장하지 않으며, 동적 PF의 실제 오차를 계산한 것도 아닙니다.

## 고정한 source와 검증 범위

- main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`: P06 후보 writer/validator/collector.
- #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`: claim 기록·최종 요청·identity 경계.
- #363 `6727751b49ce11fb62234bb97274137f22850765`: PF consistency·STATUS·현재 caller. 이후 `de03fe87d08879abefaa7dac67c7ff313df5df89`는06:43:23 UTC 공식 대조에서 README +27행만 바뀌었습니다. 새 공개 물리 결과를 독립 재실행한 것이 아닙니다.

[독립 반증과 재실행](validation.md)은 정상·실패·음성 대조와 fake/stub 경계를 설명합니다. 새 physics·renderer·LLM·학습·실기기 실행은 없으며 raw/heldout 결과를 의도적으로 열어 분석하지 않았습니다. 코드검색에 부수적으로 나온 공개fixture 출처줄은 판단 근거에서 제외했습니다. 전체 저장소 전줄 정독·전체 테스트 통과를 주장하지 않습니다.

1–8차 본문은 당시 SHA의 기록으로 보존합니다. 이 문서는9차 체크포인트이며, 이후 수정·발견은 새로운 추가 문서로 이어갑니다.
