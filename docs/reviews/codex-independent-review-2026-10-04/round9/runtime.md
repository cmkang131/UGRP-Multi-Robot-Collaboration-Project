# 9차 런타임 검토: 요청 시점과 대화 참조의 의미

검토 commit: PR #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 시작 시 공식 PR metadata와 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 AGENTS.md를 확인했다. 이 문서는 8차의 이미지 SIM bill / finalization 분류 finding을 반복하지 않는다.

**결론:** 실제 scheduler와 최종 모델 요청을 통과하는 두 경계가 재현되었다. 다만 현재 주장은 **대화 메타데이터의 시점·참조 provenance 보증 한계 한 묶음**이다. 미래 외부 관측 누출, 실제 모델 환각 발생, 물리 행동 오류, 성능 편향이 입증된 P1/P2 결함 두 개로 세지 않는다. ① `sent`는 아직 SIM release 전인 자신의 accepted 예약까지 담는다. ② 유효한 `reply_to`라고 해서 그 원문이 해당 호출의 입력에 있었다는 뜻은 아니다.

## 재현 범위와 실행

```sh
PYTHONDONTWRITEBYTECODE=1 python3 runtime-protocol-repro.py \
  --repo /path/to/UGRP-Multi-Robot-Collaboration-Project \
  --source-ref a009112ff5fb18c6b64f58d8cd6392c58d4c028c \
  --output runtime-protocol-repro.json
```

Pillow가 필요하다. 스크립트가 local Git object에서 임시 디렉터리로 `.py` 소스, 저작된 정적 지도 JSON, pair scenario 설정 하나만 복원한다. 원자료/score/heldout는 읽지 않는다. checkout 변경, 구현 수정, 유료 호출, 네트워크, MuJoCo 실행은 없다. `socket.connect`는 금지하고 실제 wire 대신 완성된 JSON envelope를 돌려주는 fake를 사용한다.

실행한 실제 경로는 `DecisionScheduler` → `_LiveTransport.submit` → `ModelCallTransport` → `PairTrial.prepare_call`/`finish_call` → pair payload/request builder → `GeminiProxyCompleter(study_json=True)` → `SendLedger` → protocol relay다. PairTrial의 두 메서드와 pair reply validator, `_LiveTransport`는 pinned 소스의 AST 몸체를 그대로 사용한다. world/link 대신 작은 pipeline fixture가 호출 시작에 synthetic own RGB와 빈 own command history/status, 그때의 실제 bus inbox를 저장한다. own RGB는 Pillow 단색 JPEG, map은 실제 정적 schematic renderer로 만든다. 물리 snapshot나 전체 PairTrial constructor를 실행한 것으로 확대하지 않는다. 패키지 `__init__`의 simulator 등록은 건너뛴다.

최종 JSON은 사용한 소스 SHA256, 복원한 지도 SHA256, snapshot/실제 wire-fetch/release 시각, bus acceptance와 전달, 최종 prompt 정보를 포함한다. 모든 실행은 schema-valid 응답으로 `outcome=ok`, send-ledger violation 0이다. 응답/행동/발화 시각은 실제 비용 함수가 계산하며 clock 강제 변경은 없다.

## A. `dialogue_window.sent`는 호출 시점까지 SIM release된 발화 목록이 아니다

소스 연결:

- [scheduler 계약 10–21](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_event_scheduler.py#L10-L21): 입력은 시작 t에 고정되고 action/message는 t+d 전 보이지 않는다는 설명.
- [합법적인 lane overlap 124–135](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/docs/zone_study_integration.md#L124-L135): 이미 시작한 message call과 나중 common call은 겹칠 수 있다.
- [pair prepare/finish 369–403](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L369-L403): call-start snapshot을 사용하지만 relay는 응답 cost를 알게 된 순간 미래 `release` stamp로 즉시 수행한다.
- [sent/window 585–604](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L585-L604): `sent_ids`의 정의는 “actually got accepted”. `received`만 now로 자르고 sent/remaining은 eager 현재 상태다.
- [최종 request 367–415](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_inputs.py#L367-L415): window를 budget-only metadata로 설명하고, 실제 모델 JSON에 `sent`와 `your_utterances_left`를 붙인다.

| 사건 | 실제 SIM 시각 | 모델이 보는 결과 |
|---|---:|---|
| r2 최초 발화 release / r1 수신 | 4.0 / 4.1 | r1 inbox에 `w1-r2-1` |
| r1 message call 시작 / release | 4.1 / 9.5 | 자기 응답 발화 ID는 `w1-r1-2` |
| r1 후속 common call 시작 / 실제 wire fetch | 8.0 / 8.0 | `sent=["w1-r1-2"]`, 남은 quota 2 |
| 위 자기 발화가 r2에 실제 전달 | 9.6 | 8.0보다 이후 |
| 음성 대조: common call을 30.0에 시작 | 30.0 | 미래 sent ID 없음 |

JSON: `window_overlap[0].requests`의 `call-0004-r1`에 `future_sent_ids`, `snapshot.window_at_start`, `user_dialogue_window`가 함께 있다. 시작 snapshot에도 이미 같은 예약 ID가 있다. 따라서 **prepare 시점의 window를 snapshot에 단순 복사하는 것만으로 해결되지 않는다.** 관측 inbox는 수신 시점대로 유지했고 command history는 fixture가 시작에 고정한 빈 목록 그대로다. 실제 history/executor 전반의 새 검증을 뜻하지 않는다.

해석의 경계: quota를 미리 예약해야 초과 송신을 막을 수 있고, `sent_ids`도 accepted를 명시한다. 그러므로 감소 자체를 잘못된 예산 처리로 보지 않는다. 기록된 것은 자신의 pending 발화 ID이며 동료의 미래 내용/GT가 아니다. 다만 request `sim_time_s=8.0`에 붙은 `sent`를 “8.0까지 발화를 마쳤음”으로 읽거나 frozen input의 모든 필드가 동일 as-of 시각이라고 인증하면 틀린다. 예약 의미를 계속 사용할지 SIM release 의미로 바꿀지 계약을 명시할 필요가 있다.

권장 수용 기준: reserved와 SIM-released를 구분하고, 전자는 pending임과 release 시각을 명시하거나 모델에게 보여주지 않는 예산 상태로 남긴다. 후자를 표방한다면 call-start 기준 time filter를 적용한다. cap 보호를 없애는 수정은 권하지 않는다.

## B. 유효한 `reply_to`는 해당 호출이 원문을 입력으로 받았다는 증거가 아니다

소스 연결:

- [snapshot/input 321–366](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L321-L366): inbox는 call start에 고정한다.
- [스케줄러 resolution 944–969](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_event_scheduler.py#L944-L969): 최소 가능한 비용보다 이른 사건은 pending call의 reply를 fetch하기 전에 진행할 수 있다.
- [참조 검증 386–393, 512–545](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L386-L545): `reply_to`는 relay `at_sim_s`까지 실제 delivered 집합에 있는지 검사한다. 해당 request의 frozen inbox 집합은 인자가 아니다.

| case | r1 snapshot | peer 전달 | 실제 wire fetch | reply_to | 원래 prompt에 ID | relay 결과 |
|---|---:|---:|---:|---|---|---|
| inflight | 3.9, inbox `[]` | 4.1 | 4.1 | `w1-r2-1` | 없음 | 8.1에 accepted |
| nonexistent 대조 | 3.9, inbox `[]` | 4.1 | 4.1 | `w1-r2-999` | 없음 | `unknown_reply_to` |
| known 대조 | 5.0, inbox에 ID 있음 | 4.1 | 5.0 | `w1-r2-1` | 있음 | 9.2에 accepted |

첫 행은 fake model이 예측 가능한 ID를 의도적으로 출력한 것이다. 그 ID는 prior r1 call에도 없었다. `reply_provenance[0].requests`의 `call-0003-r1`에 최종 wire의 **system + user + 이미지 label text 전체**를 합친 `prompt_text`와 `reply_ids_found_in_prompt={"w1-r2-1":false}`를 저장한다. 이미지에는 synthetic RGB/정적 지도만 있다. 별도 window에 ID가 숨어 있었던 반례가 아니다. 실제 payload inbox는 올바르게 과거 것으로 유지되었다.

이것은 비밀 내용 조회가 아니라 **잘못 지목한 답글 참조가 송신 시점의 전달 사실만으로 통과할 수 있음**이다. 현재 `_received_ids` 계약은 delivered-by-send-time이므로 구현은 그 좁은 규칙을 따른다. `reply_to` 그래프를 LLM이 메시지를 보았거나 사용했다는 관측치로 해석할 때 그 이상의 보장이 없다는 점이 핵심이다. 실제 모델이 이를 얼마나 자주 출력하는지, 현재 평가가 그 그래프를 인과 지표로 쓰는지는 이 재현으로 판단하지 않는다.

권장 수용 기준: 입력 provenance가 필요하다면 `request_id → 실제 최종 request inbox IDs`와 `reply_to`를 조인해 `in_prompt`를 별도로 표시한다. validator에서 차단할지, protocol violation으로 기록하고 발화 비용은 계속 청구할지 정책을 명시한다. delivered 여부와 read/use 여부는 계속 구분한다. 기존 요청의 숨은 원문을 보았다고 복원하거나 새 물리실험을 추정하지 않는다.

## 이어서 확인할 범위

두 결과는 하나의 시점/provenance audit로 묶어 freeze한다. 그 뒤 request identity, 중복 JSON key와 invalid response 정규화는 별도 fixture 파일로 조사한다. source/schema 위반을 찾았다는 이유만으로 provider 발생이나 실제 행동 영향까지 자동 승격하지 않는다.
