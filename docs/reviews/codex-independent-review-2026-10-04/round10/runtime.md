# 10차 런타임 경계 감사: 정상 응답과 실제 대화 노출을 구분하기

대상은 #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 공식 PR metadata 재확인 시에도 head는 같았다(`updated_at=2026-10-04T06:47:27Z`). 이 문서는 **새 P1/P2 finding이 아니라 실제 호출 경로로 확인한 보증 범위**다. R9의 시점/provenance 결과를 새 버그로 다시 세지 않는다.

## 관측 항목이 뜻하는 단계

| 관측값 | 이번에 확인한 의미 | 그것만으로 말할 수 없는 것 |
|---|---|---|
| wire `normal_completion=True` / health 통과 | 정상 stop와 top-level JSON 형식을 갖춘 응답이 wire 원장에 있음 | 해당 request_id/action이 schema-valid이고 실제 실행 가능한 응답이 있음 |
| call `status=ok` | protocol validation과 해당 call 비용 완료 | 해당 메시지가 상대에게 전달됨, 행동이 물리적으로 성공함 |
| `metrics.messages.sent` | eager protocol relay에서 accepted 또는 rejected된 생성 발화 수 | horizon 전에 SIM release되었거나 상대가 받음 |
| `metrics.messages.accepted` | `channel.accepted_messages = len(trial.messages)`; 최종 message log의 delivered 발화 수 | 상대 모델이 그 원문을 입력으로 받거나 인과적으로 사용함 |
| `metrics.language.messages` | protocol relay에서 accepted된 발화의 언어 측정 행 수 | 그 발화가 실제 전달됨 |

마지막 세 항목은 코드 경로에서 추론한 의미이며, 새 이름으로 바꾸는 구현을 한 것이 아니다. producer가 부여한 `accepted`와 final summary의 `accepted`가 서로 다른 단계에 붙는다.

## A. health와 reply validity

실제 `PairLiveLedger` + 임시 SQLite `MainStudyBudget` + completer/transport/PairTrial finish + `live.check_health(final=True)`를 fake wire로 실행했다. 정상 ID/action은 `ok`와 action1, stale ID 또는 unknown action은 `invalid`와 action0이다. 그러나 후자도 wire completion은 정상이라 health/failure_class는 통과/None이었다. JSON 앞 prose는 completion gate에서 거절되어 `infra:API`다. 네 경우 모두 POST1/provider150토큰을 보존한다.

[completion top-level 검사](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/llm_completion.py#L112-L125), [health](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L514-L554), [contextual reply validation](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L711-L768)이 서로 다른 일을 한다. API 정상성과 잘못된 모델 정책을 구분하려는 설계일 수 있으므로 schema-invalid를 자동 API 장애로 바꾸거나 paid retry를 권하지 않는다. invalid call 기록은 남아 있으며 실패 전체 은닉을 주장하지 않는다.

재현: `runtime-health-admission-repro.py/.json`, 상세 범위 `runtime-health-admission-audit.md`. `--repo`와 `--output`을 받으며 `../round9/runtime-protocol-repro.py`의 pinned Git 복원 utility를 사용한다.

## B. horizon과 최종 대화 집계

실제 `PairTrial.finish_call` → `DecisionScheduler` → `OfflineTrial._collect`/channel/cost → `PairTrial._collect`/cost → `pair_llm_eval.trial_metrics`를 연결했다. 응답은 r1의 continue + r2에게 보낼 짧은 발화 한 개다. context fixture의 text bill은100, 이미지 없음; 실제 cost 함수가 release2.8과 delivery2.9를 계산한다. 상대의 message-triggered call도 실제 DecisionScheduler가 시작하며 모든 응답은 fake다.

| stop 시각 | 첫 call 상태 | action callback / delivery | 최종 `sent / accepted / rejected` | 별도 보존된 분류 |
|---:|---|---|---|---|
| 2.7 | censored | 0 / 0 | 1 / 0 / 0 | censored_utterances1, undelivered0 |
| 2.85 | ok | 1 / 0 | 1 / 0 / 0 | censored_utterances0, undelivered1 |
| 3.0 | ok | 1 / 1 | 1 / 1 / 0 | 첫 메시지는 전달됨; 상대의 새 응답 call은 censored |
| 충분히 긴 10.0 cap | ok | 1 / 1 | 1 / 1 / 0 | 상대 응답도 완료, 더 할 사건 없어 scheduler는4.8에 quiet |

언어 측정은 네 경우 모두 accepted-generated message1이다. 첫 행은 SIM상 방출/전달된 메시지가 전혀 없어도 `metrics.messages.sent=1`일 수 있음을 보인다. 하지만 call은 censored로 보존되고 실제 callback/inbox는 0이다. 청구 전 행동·메시지 실행 결함이나 censor 후 재활성화의 새 증거가 아니다. 비용·원문 유실이나 통신 효과의 정량 편향도 측정하지 않았다.

근거:

- [relay 전에 release 계산](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L395-L425)
- [horizon censor와 pending call 정산](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_event_scheduler.py#L849-L916)
- [최종 message log는 scheduler delivery edge에서 생성](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_offline.py#L575-L614)
- [censored_utterances / undelivered 분리](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_offline.py#L616-L657)
- [pair metrics의 sent/accepted/language 조립](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_eval.py#L120-L130)

통신 노출 분석은 generated/relay-accepted, SIM-released, delivered, request-included를 명시적으로 구분해야 한다. 비용 계산용 generated 발화 수를 delivered 발화 수로 바꾸는 제안이 아니다. `reply_to`가 입력 근거를 보장하지 않는 R9 결과도 유지된다.

재현: `runtime-stop-accounting-repro.py/.json`. `--repo /path/to/repo --output result.json`. 이 fixture는 모든 API 호출·원장·cost/최종 message 생성 경로를 실제 소스에서 실행하지만, PairTrial constructor, 실제 robot snapshot, 물리 world, bounded case loop, motion-failure 예외 후 artifact writer를 실행한 것은 아니다. 후자의 interruption 경로는 이번 horizon 정산 결과와 합치지 않는다. raw/score/heldout를 읽지 않았고 네트워크를 금지했다.

## C. 9차 parser 음성 대조와 함께 읽기

`../round9/runtime-response-admission-audit.md` 및 9case fixture가 이 감사의 parser 근거다. 같은 last-wins parser가 completion/schema/action에 쓰이므로 duplicate-key 계층 불일치 가설은 기각했다. stale ID와 unknown action은 실제 행동 없이 거절되고, 단일 전체 json fence는 명시 정책대로 기록하여 허용하며 prose/연속 object는 거절된다. run-local request ID와 durable UUID/run_key를 구별했고, fixed actor-role 오류는 실제 executor_plan에서 차단됨을 source와 독립 QA로 확인했다.
