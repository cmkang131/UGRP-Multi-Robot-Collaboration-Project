> **최신성:** 아래 합성 재현은 `1883c56`에 고정합니다. 이후 #371 `a009112f`의 비용·종료 관련 경로가 동일한지 [게시 직전 좁은 대조](runtime-currentness.md)로 확인했습니다. 표의 절대 SIM값은 원래 fixture 값입니다.

# 8차 독립 검토 — PR #371 요청 생명주기와 종료 기록

검토 고정점은 **`1883c56a749dc89597d57f570d4a2243cbb9595d`**다. 2026-10-04 공식 GitHub PR 조회에서 #371이 여전히 이 head의 열린 초안임을 확인했다. main 지침은 `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 `AGENTS.md`를 읽었다. 이번 결과는 이후 rebase/head에 자동 승계하지 않는다.

이 검토는 `pair_llm_live/case/dispatch/runtime`, 공유 `zone_study_llm_transport`, `zone_study_llm_driver`, `zone_send_ledger`, `zone_event_scheduler`, `zone_sim_cost`, 관련 테스트의 요청·완료·비용·종료 경계를 다룬다. 기존 own_status 시계 혼합, `__CHARS__`, #363 peer-abort finding은 다시 집계하지 않았다. **구현 수정·실제 모델 호출·물리/렌더·원본 실험/heldout 열람은 없다.** 테스트 입력, 응답, 실패 지점, world/runtime/evaluation은 아래에 명시한 합성 대역이다.

| 새 결과 | 판정 | 닫는 기준 |
|---|---|---|
| R8-R1: POST 후 transport 실패에서 v100 이미지 SIM 청구 누락 | **P2 후보, 실제 비용 경로 반례 확인** | 정상/실패가 같은 요청 청구 정책을 쓰며, 미전송은 계속 환불되고 legacy 정책은 보존됨 |
| R8-R3: finally의 기록/정리 실패가 실행 원장에서 `finished`로 남음 | **P2 후보, case→run_attempts→SQLite 반례 확인** | case/metrics/attempt/원장의 실패 분류 일치, 이미 전송한 요청 재실행 금지 유지 |
| R8-R2: 600바이트 뒤의 비429 quota 문구 미분류 | **조건부 P3 보강, 현재 운반 차단 원인 아님** | 판별 범위와 요약 표시 범위 분리; 실제 프록시에서 이 형태의 빈도는 미확인 |

## R8-R1 — 실패 요청만 이미지 입력 비용이 빠진다

v100의 명시적 정책은 `total_billed = total_text_billed + 1490 × images`다. [billing65–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L65-L80)은 이를 요청에 기록하고, [PairTrial.finish_call356–377](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L356-L377)은 정상·프로토콜 거절 응답 모두 `total_billed`를 `Attempt.input_tokens`로 넘긴다.

그러나 [공유 transport126–157](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_llm_transport.py#L126-L157)의 completer 예외는 `_failure`로 이동하며, [183–189](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_llm_transport.py#L183-L189)가 `total_text_billed`만 사용한다. v100이 만드는 [실제 transport284–286](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L284-L286)는 `_LiveTransport`이고, 그 클래스는 [submit만 override](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_integration.py#L342-L348)한다. 따라서 이 실패 경로가 실제로 상속된다.

[scheduler1000–1034](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_event_scheduler.py#L1000-L1034)는 ledger의 전송 **횟수**와 attempt 수를 대조할 뿐, 누락된 이미지 입력 토큰을 복구하지 않는다. 이후 [954–968](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_event_scheduler.py#L954-L968)이 이 attempt로 비용/완료 시각을 잡는다.

### 독립 합성 재현

`runtime-repro.py`는 exact source의 `PairTrial.finish_call`과 `validate_reply`를 AST body 수정 없이 적재했다. 실제 `GeminiProxyCompleter(study_json=True) → PairLiveLedger/MainStudyBudget → ModelCallTransport → EventScheduler`를 통과한다. 요청은 텍스트100토큰+합성이미지2장, 결과 저장 sink와 물리 입력은 대역이다. 실제 provider나 image tokenizer 측정이 아니다.

| 합성 결과 | 실제 Attempt 입력 | 정책상 입력 | 실제 SIM초 | 전체 bill 대조 SIM초 |
|---|---:|---:|---:|---:|
| 정상 protocol 응답 (`outcome=ok`) | 3,080 | 3,080 | 2.5 | 2.5 |
| 전체 reply 필드 정상·허용되지 않는 action (`invalid`) | 3,080 | 3,080 | 2.5 | 2.5 |
| 제공자 `finish_reason=length` (`error`) | 100 | 3,080 | 1.4 | 2.0 |
| 전송 후 timeout | 100 | 3,080 | 20.1 | 20.7 |
| HTTP500 | 100 | 3,080 | 0.6 | 1.2 |
| completion envelope 훼손 | 100 | 3,080 | 0.6 | 1.2 |
| 요청 준비 중 실패, wire 전송0 | attempt 없음 | 청구0 | 완료 call 없음 | 환불1 |

각 전송 후 실패에서 이미지2장의 **2,980토큰**, 기본 계수에서 **0.596 raw SIM초**가 누락된다. 위 fixture에서는 0.1초 grid 반올림 후 차이가0.6초다. 모든 가능한 원래 bill의 반올림 차이가 항상0.6초라고 일반화하지 않는다. timeout은20초 고정항도 실제로 유지되며, [비용 함수253–264](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_sim_cost.py#L253-L264)가 실패 고정항에 입력/출력 토큰항을 **더하도록** 정의한다. 따라서 고정 timeout 비용이 이미지항을 대신한다는 해석과는 맞지 않는다. wall latency 역시 SIM 청구에 더하지 않는다.

**좁은 영향:** 해당 실패가 있는 call의 SIM 비용과 후속 완료/재질문 시점이 요청 정책과 어긋난다. 실행이 health 검사에서 즉시 중단되면 후속 제어 영향은 제한된다. API오류 실행은 기존 정책에서 이미 유효 연구 실행이 아니므로, 유효 코호트의 통신 효과가 실제로 편향되었다고 주장하지 않는다. v100 실제 실행은 검토 당시 없으며 v99 smoke의 과거 비용 오류를 새로 측정한 것도 아니다.

**보존되는 것:** 비정상 completion의 제공자 사용량6,100토큰은 `model_usage`와 SQLite에 남는다. HTTP/timeout의 unknown usage도 unknown으로 남는다. 이 finding은 실제 지불 토큰 유실·추가 POST·무료 요청 주장이 아니다. send-count violation은 전 사례0이며, 0-send failure는 비용 없이 환불되는 음성 대조를 통과했다.

**수정 방향:** pair의 요청 청구 정책이 정상/transport 실패 모두에 전달되는 좁은 계약을 두고, 기존 text-only 스터디의 동결 정책과 역사적 bill을 보존한다. 단순히 모든 전송의 이미지 상수를 두 번 더하거나, 미전송 실패에도 청구하는 방식은 부적절하다. 실제 구현 변경은 이 검토에서 하지 않았다.

## R8-R3 — 종료 단계 실패가 반환 status와 실행 원장에서 다르게 기록된다

핵심은 예외가 조용히 사라진다는 주장이 아니다. [case271–292](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L271-L292)는 각 오류를 `record_error`, `llm_record_error`, `finalize_error`, `cleanup_error`로 보존하고 `status='HOST_ERROR'`로 바꾼다. 그러나 정상 본문에서 정한 **`failure_class=None`을 변경하지 않는다.** [metrics304](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L300-L309)도 그 None을 저장한다.

실제 상위 [run_pair_live258–264](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_live.py#L258-L264)는 이 record를 `(result, None)`으로 넘긴다. [run_attempts581–589](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_llm_driver.py#L581-L589)는 exception 또는 `record.failure_class`만으로 run 상태를 고르므로, `status='HOST_ERROR'`라도 **SQLite run은 `finished`, attempt failure_class는 None**이 된다.

### 독립 합성 재현

`runtime-finalization-repro.py`는 exact source의 case 본문과 write/분류 함수를 body 수정 없이 실행하고, 실제 `run_attempts`, `MainStudyBudget`, `PairLiveLedger`, `check_health`를 연결했다. world/executor/Trial의 작업과 evaluator는 대역이다. 각 정상 경로의 Trial은 가짜 wire로 정상 응답1회를 ledger에 남기고, 실제 health 검사를 통과한다. 네 finalization 경계에 하나씩 `OSError(ENOSPC)`를 주입했으며, 디스크를 실제로 채우지 않았다.

| 상황 | 반환 case status | failure_class | SQLite run | 전송/토큰 | 재시도 |
|---|---|---|---|---|---|
| 정상 대조 | COLLECTED_UNQUALIFIED | None | finished | 1 / 100 | 없음 |
| student record 생성 경계 오류 | HOST_ERROR | **None** | **finished** | 1 / 100 | 없음 |
| LLM artifact 저장 경계 오류 | HOST_ERROR | **None** | **finished** | 1 / 100 | 없음 |
| finalize callback 오류 | HOST_ERROR | **None** | **finished** | 1 / 100 | 없음 |
| backend.close 오류 | HOST_ERROR | **None** | **finished** | 1 / 100 | 없음 |
| 전송 전 reset 오류 대조 | HOST_ERROR | infra:HOST_ERROR | failed | 0 / 0 | 규칙대로 한 번, 총2attempt |

실패4건 모두 provider100토큰, 요청 상태`response_received`, 결과`metrics.model_usage.tokens_total_known=100`을 보존한다. 따라서 **이 분류를 고친다는 이유로 이미 전송한 요청을 재시도해서는 안 된다.** [기존 may_retry560–562](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_llm_driver.py#L560-L562)의 `model_requests == 0` 제한을 계속 지켜야 한다.

**도달 조건/한계:** 해당 오류를 잡은 뒤 최종 metrics/result/hash 기록이 성공하여 함수가 record를 반환하는 경우다. 전역 디스크 고갈이 계속되어 최종 write까지 실패하면 예외가 상위로 올라가므로 같은 `finished` 반례로 일반화하지 않는다. 일시적 저장 실패, 특정 artifact의 직렬화/접근 문제, 특정 cleanup 실패가 이 경계의 실용적 검토 대상이며, 이번 자료는 실제 프로젝트에서 그런 사고가 일어났다는 증거가 아니다. `protocol_complete`는 물리 루프 완료 표시이므로 이것 자체를 거짓이라거나 운반성공으로 승격됐다고 부르지 않는다. evaluator 결과/성공률 소비자의 실제 오분류는 이번에 검증하지 않았다.

**닫는 기준:** 최종 반환 전에 status와 실패 분류를 일치시키고, 기록/정리 실패의 타입·단계·기존 원인을 보존한다. run/attempt 기록은 그 최종 상태와 같아야 한다. 정상 대조, 본문 오류 대조, artifact 오류, close 오류를 포함하고 **post-send 추가 전송0·기존 provider usage 보존**을 동시에 확인한다. 원래 오류를 더 늦은 cleanup 오류가 덮어쓰지 않는 우선순위도 명시하면 된다.

별도 독립 검증에서 [CLI의 반환 처리](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/scripts/run_pair_llm.py#L162-L180)가 case `HOST_ERROR`를 보고 exit1을 반환함도 확인했다. 따라서 실패가 사용자에게 전부 숨겨진다는 주장이 아니라, **이미 드러난 case 실패와 원장/attempt의 무실패 분류가 모순되는 문제**다.

## R8-R2 — 조건부 보강: quota 판별이 표시용 excerpt에 종속됨

[PairLiveLedger87–112](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_live.py#L87-L112)는 HTTP error 본문 전체를 저장·해시하지만, `is_rate_limit`에는 첫600바이트의 excerpt만 전달한다. 현재 모듈 문서와 관련 테스트는429뿐 아니라403quota/503RESOURCE_EXHAUSTED도 명시적으로 지원한다.

합성 JSON에서 앞쪽 diagnostic 문자열700자 뒤에 `RESOURCE_EXHAUSTED`/`quota exceeded`가 있으면 전체 본문 판별은true지만 저장된 `rate_limit=false`다. 앞에 실제 ledger상 정상 응답1회를 둔 뒤 실제 `check_health`를 호출하면 짧은403·긴429는`RateLimited`, 긴403/500는계속 진행한다. 후자는 일반 API오류라는 기록은 남고 최종 연구 유효성은 기존 API오류 규칙을 따른다. 즉 API오류가 사라지거나 유효 실험으로 바뀐다는 주장이 아니다.

**현재 프록시가 실제로 이 긴 오류 형식을 반환했다는 근거는 없다.** 따라서 독립적인 현재 blocker나 연구 결과 영향으로 올리지 않고 방어적 보강 부록에만 둔다. 판별은 전체 보존 본문/구조화 오류코드를 보고, 사람이 읽는 excerpt만600바이트로 제한하면 계약을 분리할 수 있다. HTTP429의 무조건 판별은 이미 정상이다.

## 재현과 증거

```sh
PYTHONDONTWRITEBYTECODE=1 python3 review-notes/round8/runtime-repro.py
PYTHONDONTWRITEBYTECODE=1 python3 review-notes/round8/runtime-finalization-repro.py
```

두 스크립트 최종 실행은 exit0이다. 결과는 `runtime-repro.json`, `runtime-finalization-repro.json`, exact source 파일별 byte수/SHA256/Git blob은 `runtime-source/source-manifest.json`에 있다. 공유 transport/scheduler/driver/cost 파일은 #371 base f257과 head1883 사이 diff가 없음을 확인했다. 소스 snapshot 전체는1883에서 직접 추출했으며 실행하지 않는 optional import 때문에 일부 case/PairTrial 함수를 AST로 분리했다. 함수 body의 고침이나 런타임 코드 패치는 없다.

이 재현은 경계 계약 진단이며 전체 테스트 suite, 실제 provider 응답 분포, 물리 성능, 새 코호트 결과, loaded look의 효과, 현재 #363의 실행 상태를 검증한 것이 아니다. 1차 fixture의 정상 응답은 독립 검증자가 schema 거절임을 발견했고, `decision_sources=['own_rgb']`와 실제 vocabulary 경계를 맞춘 뒤 `outcome=='ok'` assertion을 추가하여 최종 결과를 다시 생성했다. 이 교정 전 출력은 최종 증거로 사용하지 않는다.

최종 스크립트 SHA256: `runtime-repro.py` = `bd238253a5fa89a8a1676ea34ff1250f7f4cc6554cc80668cc1eaa7e08443334`; `runtime-finalization-repro.py` = `ab54475b230a5ea18c2b41db2b9ac50b1afc4a265491550dfa7298a6a820c25f`. Source manifest SHA256 = `c42920c91d9a10b1b025432244f0387b381f10f1b4bbf7f63313e6205ea947fc`.
