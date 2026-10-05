# R9 — 소통의 효과를 주장하기 전에, 그 정보가 해당 요청에 도달했는가

**우선순위는 기존 request archive에서 메시지 하나가 어느 실제 요청에 들어갔는지 복원하는 것이다.** `input_log.inbox_ids`, `decision_sources`, 최종 성공 여부 중 하나만으로는 충분하지 않다. frozen payload 밖에 붙는 `dialogue_window`까지 포함한 최종 요청, 메시지 접수/전달, action release/dispatch를 이어 보면 새 physics 실행 없이 시간적으로 불가능한 설명을 걸러낼 수 있다.

검토 기준은 #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`와 #363 `6727751b`이다. raw 실험·held-out·LLM 실행은 하지 않았다. 논문 출처와 열람 범위는 `research-sources.md`, PF 수학은 `pf-theory.md`에 분리했다. no_comm에서도 공통 low-level pair coordination을 유지한다는 점은 R1–R8에서 이미 확인한 계약이며 이번 신규 finding으로 세지 않는다.

## 1. 현재 코드가 증명하는 것과 증명하지 않는 것

| 소스 사실 | 증명할 수 있는 좁은 사실 | 이것만으로 증명할 수 없는 것 |
|---|---|---|
| `PairTrial.snapshot` / `build_inputs`: call 시작의 own frame/history/belief/status/inbox를 저장한 snapshot으로 payload 생성 | 해당 payload에 바인딩된 frame와 입력 목록 | 렌더링 후 요청 전체도 같은 시점에 동결됐다는 사실 |
| `PairTrial.prepare_call`: payload 생성 뒤 `channel.window_context(actor, now_sim_s=call.started_sim_s)`를 별도로 얻음 | 최종 요청에 별도 dialogue window 정보가 붙는 경로 | inbox ID만 조사하면 모든 메시지 관련 입력을 포괄한다는 사실 |
| `Transport.window_context`: received는 시간 필터한 inbox, sent는 `sent_ids`, 잔량은 현재 `remaining`에서 얻음 | source별 시점 규칙이 동일하지 않음 | 실제 trial에서 미래 정보가 노출됐다는 빈도·효과; overlap witness는 runtime 담당 별도 검증 |
| `validate_reply`: `decision_sources`가 허용된 nonempty enum이며 message는 channel-open에서만 허용 | 모델의 형식상 자기보고가 schema에 맞음 | 특정 message를 실제 사용했음, 옳게 이해했음, 선택에 인과적 영향을 줬음 |
| `finish_call`: 한 reply 안에 action/messages, 비용 후 release 계산, relay receipt와 request 보관 | 생성된 메시지·행동·비용·접수 경로를 연결할 수 있음 | same-call 발화가 그 same-call 행동의 원인이었다는 사실 |
| `PairLink.belief`: executor의 `belief_projection()`을 반환 | self_belief가 임의 LLM scratchpad는 아님 | belief가 별개의 독립 관측이거나 측정된 실제 운동이라는 사실 |

현재 별도 source enum `own_status`는 없고, `pair_llm_prompts_ko.py:80`은 이를 근거로 쓰면 `own_commands`로 적도록 **명시적으로 매핑**한다(`DECISION_SOURCES`는 static_map/order_sheet/own_rgb/own_commands/own_belief/message). 따라서 이는 빠진 지시나 새로운 schema 버그가 아니다. 다만 enum 자기보고만으로 실제 command history와 own_status의 기여를 분리할 수는 없는 의도된 coarse 분류다. 새 enum 추가나 지표 정의 변경을 이 검토가 구현하지는 않는다.

### 실제 scheduler를 통과한 별도 재현과의 연결

Runtime 담당의 `runtime-protocol-repro.py/json`은 a009의 실제 scheduler/transport/request builder를 쓰는 deterministic fixture다. message call은 t=4.1에 시작해 t=9.5 release인데, 허용된 overlapping common call의 t=8.0 최종 요청에는 own outgoing ID `w1-r1-2`와 줄어든 quota가 들어간다. 외부 상대의 미래 메시지 내용이 노출된 증인은 아니다. payload inbox는 기존 상대 메시지만 유지한다.

중요한 해석상의 분기: 이를 “아직 SIM 전송되지 않은 자기 결정의 예약”으로 정의하면 허용 가능한 committed state일 수 있다. “SIM t=8.0까지 실제 발송 완료한 ID”라고 해석하면 시점이 맞지 않는다. source/state의 의미를 먼저 정해야 한다. eager acceptance가 snapshot 시점에 이미 일어났으므로 **build를 빨리 호출하는 것만으로 해결되는 lazy-build 문제로 환원하지 않는다.** 연구상 확정 가능한 교훈은 payload inbox hash만으로 model-visible communication state 전체를 인증하지 못한다는 것이다.

같은 재현 묶음의 `reply_provenance`는 더 직접적인 반례다. receiver call은 t=3.9에 시작하고 peer 메시지 `w1-r2-1`은 t=4.1에 전달된다. wire fetch가 t=4.1에 일어나도 frozen inbox는 비어 있고 실제 system/user/image-label text 전체에도 그 ID가 없다. fixture가 예측 가능한 ID를 `reply_to`로 출력하면 t=8.1 release에서 transport가 수락한다. 존재하지 않는 `w1-r2-999` 대조는 `unknown_reply_to`로 거절되고, 이미 prompt에 있던 ID 대조는 수락된다.

이것은 실제 LLM이 추측했다는 실험이 아니라, 실제 request/scheduler/validator를 통과하는 합성 reply의 구성이다. **수락된 reply edge는 발신 시점까지 전달된 ID의 유효성을 뜻할 수 있지만, 그 생성 요청에 해당 내용이 있었음을 증명하지 않는다.** 따라서 reply graph만으로 grounded response율을 계산하면 해석이 과해질 수 있다. actual prior request에 들어갔는지의 별도 join이 필요하다. 정보 유출·실제 hallucination 빈도·task 성능 변화는 이 반례가 입증하지 않는다.

## 2. 가장 작은 유용한 재구성표

분석 단위를 **최종 archive request 한 건**으로 둔다. 각 건에 다음을 결합한다. 존재하지 않는 필드는 만들어 채우지 않고 `unavailable`로 둔다.

| 열 | 기존 근거 / 의미 |
|---|---|
| bundle/code/prompt/cost profile | 같은 요청 계약인지 고정. 호출 수만 맞아도 비용·시점은 같지 않을 수 있음 |
| actor, call_id, request_id, call_started_sim_s | reply·message·action을 묶는 기준. wall-clock fetch 순서와 SIM 순서를 따로 둠 |
| payload hash + 최종 request hash/text | payload 밖 dialogue_window·system instructions까지 조사. raw image는 자기 frame의 ref/time/hash로 결합 |
| message_id, sender, reply_to, accepted_at, delivered_at | 전송 의도·접수·실제 전달을 구분. message ID가 있음은 delivery 완료와 다름 |
| payload inbox, rendered received/sent, remaining | 어느 표현에 어떤 메시지/예산 사실이 실제 들어갔는지. 중복 출현을 독립 정보로 세지 않음 |
| decision_sources | `self_reported_sources`로 이름을 읽음. observed input과 분리 |
| action proposed / released / executor accepted | 생성된 행동이 horizon 안에 실제 효력을 냈는지. old fetched-but-censored issue를 새 버그로 재보고하지 않음 |
| own frame captured_at / state projected_at | 근거가 현재 요청보다 이전인지. delivered message의 내용이 주장하는 관측 시각은 없거나 검증 불가일 수 있음 |

`zone_study_offline._archive`는 최종 request를 `archive_request`로 보관하고 call_id/actor/start를 붙인다. `_record`의 pending action과 실제 `_on_action` 기록도 구별되어 있다. 따라서 새로운 policy input이나 GT 없이 **로그 결합 분석의 설계**는 가능하다. 여기서 실제 로그를 열어 결합 결과를 냈다고 주장하지 않는다.

### 세 가지 시간 판정

1. **payload에 포함될 수 있었음:** delivery가 snapshot 시점 이전이고 해당 ID가 frozen inbox에 실제 존재한다. 시간 비교만으로 inclusion을 추정하지 말고 최종 request를 확인한다.
2. **payload에는 없지만 요청의 다른 부분에 존재함:** dialogue_window의 received/sent/budget나 다른 렌더링 경로를 확인한다. 이를 content delivery와 동일 취급하지 않는다. sent ID/잔량은 메시지 본문보다 약한 정보지만 여전히 model-visible 상태일 수 있다.
3. **해당 요청에는 어디에도 없음:** 그 메시지를 그 call의 직접 원인으로 설명하는 것은 지지되지 않는다. 다만 이전 메시지로 인한 행동·own status 등 매개 경로까지 없었다는 뜻은 아니다.

예를 들어 receiver call 시작이 t=10, 메시지 전달이 t=11, 행동 release가 t=12라면 “행동 전 전달됐으니 그 메시지를 읽고 행동했다”는 결론은 성립하지 않는다. 실제 요청이 t=10 snapshot이라면 다음 call에서야 읽을 수 있다. 반대로 payload가 깨끗해도 별도 렌더링 블록의 시점이 다르면 전체 요청 경계는 별도 확인해야 한다. 이는 toy timeline이며 실제 run에서 이런 사건이 있었다는 보고가 아니다.

## 3. 경쟁하는 설명을 구분하는 최소 흔적

성공 사례를 본 뒤 하나의 그럴듯한 이유를 붙이지 않고, 아래처럼 서로 다른 설명을 남긴다. 모두 기존 로그에 대한 **반증 가능한 분류**이며 새 실험 요구가 아니다.

| 후보 설명 | 설명이 맞다면 필요한 최소 흔적 | 불리한 증거 / 여전히 남는 모호성 |
|---|---|---|
| A. 상대의 새 관측 내용을 전달해 action 선택이 달라짐 | 특정 사실을 담은 상대 메시지가 receiver의 실제 최종 request에 포함되고 이후 선택과 내용이 일치. 발신자의 허용된 frame/command 정보와 주장 일치 여부를 따로 표시 | 메시지가 request에 없으면 직접 내용 경로가 반박됨. 포함돼도 같은 static map·자기 관측으로 같은 결정을 했을 수 있어 인과효과는 미식별 |
| B. 환경 사실보다 의도/준비/순서 합의가 도움 | 사실 추가 없는 intent/ack가 실제 읽힌 뒤 claim/hold/continue 시점과 양립. low-level barrier와 상위 선택의 사건 순서 분리 | 메시지 없이 이미 결정된 call이면 그 call에 대한 직접 합의 설명은 약함. 이후 행동 일치는 공통 prompt/prior 때문일 수도 있음 |
| C. 메시지의 부수적 비용·wake-up·window 상태가 행동 기회를 바꿈 | 동일 runtime 규칙에서 output 길이/비용/release/다음 snapshot이 연결됨; 실제 content가 들어가기 전에도 상태 경로가 달라질 가능성 | 기존 로그에서 이러한 경로가 없으면 그 사건 설명은 약해짐. 관찰 경로 존재만으로 효과 크기는 알 수 없음 |
| D. 새 확인처럼 보이는 것이 이전 메시지의 재진술 | 발신·reply_to·대화 순서상 첫 관측 주장→상대 반복→원발신 재확인의 경로, 새 own frame 근거 없음 | 상대가 실제 독립 관측을 갖고 있었다면 단순 echo 설명 약화. frame가 새로 찍혀도 공유된 오차가 사라졌다는 뜻은 아님 |

A/B/C는 배타적이지 않다. 기존 two-arm 비교가 추정하려는 전체 policy/configuration 차이와 위 기제 분류를 혼동하지 않는다. seed pairing·selected prefix·success-only·mediator conditioning의 일반 문제는 R7에서 다뤘으므로 반복하지 않는다. 여기의 새 가치는 **기제 해석에 앞서 실제 정보 경로가 가능한지 배제하는 것**이다.

## 4. 두 에이전트의 동의를 두 독립 증거로 셀 수 없는 이유

P1의 common-information 원칙에서 가져오는 최소 교훈은 출처를 보존하자는 것이다. Bayesian density `p(x|A)`와 `p(x|B)`를 결합하는 특정 모형에서, unique evidence가 x와 공통 정보 조건에서 독립이면

\[
p(x\mid A\cup B)\propto\frac{p(x\mid A)p(x\mid B)}{p(x\mid A\cap B)}.
\]

독립 정보라고 가정해 그냥 곱하는 것과 공통 정보를 제거하는 것은 다르다. **이 식은 LLM 메시지의 confidence를 계산하는 공식이 아니다.** 현재 자연어는 calibrated likelihood/posterior가 아니며 이 리뷰는 이를 Bayes filter로 바꾸지 않는다.

UGRP에서 가능한 해석상의 함정은 `own RGB 주장 → message → 상대의 재진술 → 원발신에게 돌아온 동의`를 독립 확인 두 번으로 읽는 것이다. `reply_to`는 대화 연결의 실마리지만 정확한 observation lineage는 아니며 §1의 재현처럼 생성 요청에 없던 ID도 나중에 수락될 수 있다. 표면 텍스트가 다르다는 사실도 새 정보의 증거가 아니다. 반대로 동일 메시지 ID를 중복 제거했다고 서로 다른 카메라의 공통 calibration/map/model 오차까지 해결되지는 않는다.

그래서 분석표에서는 **새로 전달된 사실 / intent / 이전 사실의 반복 / 출처 불명**을 구분할 수 있지만, 이것을 calibrated information gain이나 센서 독립성 점수라고 부르지 않는다. `own_belief`는 executor projection이므로 LLM이 메시지를 요약해 저장하는 memory라고 가정하지 않는다. 실제 echo는 외부 메시지 내용과 request lineage를 읽어야 확인된다.

최신 #363 PF의 repeat discount는 별도 경로다. 동일 view의 반복 scan에 대한 scalar 정보 예산과 두 LLM 사이 공통 주장 계수는 같은 알고리즘이 아니다. `pf-theory.md`는 현재 지수 합의 항등식과 등상관 Gaussian posterior 보장의 차이를 정확한 조건 아래 계산한다.

## 5. 관련 연구와 구별되는 주장만 남기기

P2–P5의 핵심 비교는 `research-sources.md`에 있다. 새로운 소통 필요성/grounding 최초 주장 대신 아래처럼 질문을 좁히면 현재 구현에 맞고 반증할 수 있다.

| 후보 연구 주장 | 현재 두-arm에서 가능한 수준 | 더 강한 문장이 요구하는 누락 증거 |
|---|---|---|
| “이 허용 입력·실행기·시간 비용 아래, 상위 메시지 policy의 전체 결과가 달라진다” | 고정된 비교 설계와 실제 실행/평가 무결성이 확보될 때의 target claim | 현재 문서는 새 효과 추정치를 생산하지 않았음 |
| “메시지가 자신의 RGB로 보지 못한 상대 사실을 전달한다” | request-level reachable content와 발신자 근거를 기술적으로 분류 가능 | 그 사실의 진실·수신자의 독립 지식 부재·정책 변화의 원인까지는 별개 |
| “의미 내용이 소통 이득의 원인이다” | 현재 two-arm 결과만으로 별도 식별하지 못함 | 내용·시간·호출·window/wake 규칙을 구분하는 정의/증거. 이 검토가 추가 trial을 요구하거나 실행하지는 않음 |
| “두 agent의 합의가 추정 정확도를 높인다” | 실제 동의/사실 반복은 분류 가능 | 독립 근거·잘 정의된 추정량·공통 오차 모델 없이는 정확도/uncertainty 주장 불가 |
| “RGB와 실제 메시지만으로 어려운 연속 물체 협업을 검토한다” | input와 actuator 권한, common low-level support를 함께 명시하는 조건부 task 설명 | broader novelty는 closest methods 전체 비교 필요. P2/P3 존재만으로도 일반적 multi-agent grounding 최초 주장은 과도함 |

CRAFT의 oracle progress 후보, alem의 textual teammate/affordance 노출, negotiation의 symbolic 시나리오 선택, Stag Hunt의 별도 communication stage는 모두 UGRP와 구별해야 하는 설계 요소다. “정보가 있으면 성공”과 “정보를 함께 행동으로 옮긴다”는 평가가 다르다는 점은 참고할 수 있으나, 이 논문들의 수치를 UGRP로 이전하지 않는다.

## 6. 가장 값싼 다음 분석 순서

1. **전체 최종 request 기준의 시간/출처 일관성:** payload+dialogue_window+이미지ref를 함께 결합. runtime의 overlap witness가 확인되면 input_log만으로 된 provenance 인증의 반례로 연결한다.
2. **명시적인 자기보고와 실제 가용성의 불일치:** message 선택인데 빈 inbox/다른 블록에만 존재하는지, message 미선택인데 본문에 존재하는지 등을 descriptive count로만 기록. “모델 거짓말”이나 인과미사용으로 부르지 않는다.
3. **동일 사실의 반복/intent/새 사실 구분:** 새로운 관측이 없는 상호 반복을 독립 확인에서 제외하는 분석 규칙을 명시. 불명확한 경우 unknown을 유지한다.

이 순서는 새로운 broad redesign을 요구하지 않는다. 실제 원자료가 없으면 표의 schema와 판별 규칙까지만 제공하고, 공백을 추정한 결과로 채우지 않는다.
