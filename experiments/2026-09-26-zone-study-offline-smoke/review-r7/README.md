# review-r7 — Codex 7차 검토(`codex-194-r7`) 수정: 전송 장부 기반 청구, 기록 해시 기반 계약 버전 감사 (2026-09-27)

- **상태:** 수정 완료. SIM trace는 v5와 같지만 기록 바이트(번들 ID, `model_settings_sha256`, 새 `send_ledger` 절)가 달라서 새 버전 [v6](../v6/README.md)으로 재실행했다. v1~v5는 그대로 둔다.
- **검토 기준:** Codex 7차 검토 `840fd1ce`. 판정은 not-ready이고 P1 1건·P2 1건이며, 실제 LLM 파일럿은 보류였다.
- **수정 커밋:** `9484173871ea9971784561e5ed759d5fbddc7e3a` (브랜치 `kiro/zone-study-core`, PR 194). 기준은 `840fd1ce`다. 그 뒤 테스트만 3건 보강했다(아래 변이 검사).
- **회귀 테스트:** 3개 파일, 86개다. `tests/test_zone_study_review_r7.py`(스케줄러 정산, 26), `tests/test_zone_study_review_r7_transport.py`(장부·실제 completer 경로·오프라인 루프, 38), `tests/test_zone_study_review_r7_contract.py`(P2, 22)다. `scripts/run_ci_tests.py:70`에 `tests/test_zone_study_review_r7*.py` 패턴을 등록했다.
- 모델 호출·네트워크 요청·물리 실행은 모두 0회다. 실제 completer 경로 테스트는 `urlopen`과 소켓을 막은 상태에서 오프라인 wire로 돌린다.

## 근본 수정: 어댑터의 신고가 아니라 전송 장부로 센다 (P1)

5·6차 규칙은 전송 계층의 자기 신고(`NotSent`, `sent_attempts`, 보고한 시도 수)를 믿었다. Codex 반례 두 건은 이 신뢰 가정 때문에 생겼다. 신고에 규칙을 더 붙이지 않고, **실제 전송 진입점에 장부를 두고 스케줄러가 그 장부를 읽도록** 바꿨다.

| 위치 (`94841738`) | 내용 |
|---|---|
| `harness/zone_send_ledger.py:59` `SendLedger` | 요청을 wire에 올리는 함수 하나를 감싼다. 호출마다 묶인 opener(`opener_for`, `:93`)만 내준다. `_send`(`:105`)는 (1) 주인(스케줄러)에게 허가를 묻고, 거절되면 `SendBlocked`(`:42`, `OSError`가 아니라서 completer가 재시도하지 않는다)로 wire 전에 막는다. (2) wire를 부르기 **전에** 기록한다. wire가 예외를 내도 보낸 것으로 센다. (3) `store_dir`가 있으면 요청·응답 바이트를 `xb`로 저장해 덮어쓰지 않는다(`:139`). 저장에 실패하면 보내지 않는다. 주인은 하나만 둔다(`attach`, `:81`). 오프라인 wire로 `ScriptedWire`(`:189`)와 `FixtureWire`(`:208`)가 있다 |
| `harness/zone_study_llm_transport.py:65` `ModelCallTransport` | 실제 어댑터다. completer는 `harness.gemini_proxy.GeminiProxyCompleter`이고 `http_open`은 호출의 장부 opener다(`gemini_client_factory`, `:40`). 장부 opener가 아니거나 URL이 없으면 거절한다. `GeminiProxyError`는 `TransportFailure`(timeout 또는 error, 사용량 미상)가 되며, 청구는 장부가 한다. 실제 실행용 `live_send_ledger`(`:60`)는 `urlopen`을 감싸고 wire 바이트를 저장한다. 2026-09-25 한국어 파일럿의 `audited_open`(`scripts/pilot_korean_dialogue.py:188`)과 같은 자리다 |
| `harness/zone_event_scheduler.py:455`·`:508` | 장부가 없는 전송 계층은 거절한다(`TypeError`). 장부의 허가 함수는 `_authorize_send`(`:1074`)다 |
| `:1074` `_authorize_send` | 요청 하나마다 호출이 예약한 칸을 쓰거나 예산 소유자에게서 한 칸을 더 예약한다. 칸이 없으면 `http_budget`으로 막는다. 모르는 호출과 응답을 이미 넘긴 호출(`sends_closed`, SIM 해제 전 창 포함)의 요청은 막고 위반으로 기록한다 |
| `:829` `_reply_of` | 호출의 시도 수는 **장부가 센 전송 수**다. 0회면 환불(`_release_unsent`, `:946`)하고 실행·재시도·SIM 비용이 없다. `NotSent`·`sent_attempts`·보고 시도 수는 장부와 대조한다. 어긋나면 `send_violations`에 남기고(`:892`), 장부 수로 청구하며, 응답은 실행하지 않고 재시도하지 않는다(`:1164`). 사용량 미상 응답이 장부보다 적게 보고하면 `error` 시도로 채운다(5차 규칙을 장부 수로 적용) |
| `:1036` `_submit` | `submit()` 예외도 장부로 정산한다. 전송이 있으면 실패 호출로 청구한다. `NotSent`와 함께면 `not_sent_contradicted`다. 0회면 환불하고, `NotSent`는 다시 던진다. 중단은 예약을 남기고 `ledger_sends`를 적는다 |
| `:365` `AttemptBudget.commit` | 모든 요청이 예약에 대해 허가되므로 장부 수가 예약보다 클 수 없다. 크면 스케줄러 버그로 보고 `AssertionError`를 낸다. 그래서 `over_budget_attempts`·`budget_breach` 경로는 도달할 수 없게 되어 지웠다 |
| `:1313` `ReplayTransport` | 대본 응답의 시도마다 장부 opener로 요청을 하나씩 보낸다. 그래서 기존 스케줄러 테스트도 모두 장부를 거친다 |
| `harness/zone_study_offline.py:320`–`:391` | 오프라인 스모크도 실제 경로와 같다: `ModelCallTransport` → `GeminiProxyCompleter` → 장부 → `FixtureWire`(`:372`). fixture는 wire에 실린 system·user 텍스트만 받는다. `prepare_call`/`finish_call`(`:382`, `:391`)이 옛 `_FixtureTransport`·`run_call`을 대체한다. 번들 ID는 `zone_study_offline_v3`(`:68`)이다. `cost_checks`는 장부·wire·호출 기록이 일치하는지 검사한다(`:870`). trial record에는 `send_ledger` 절(`:650`)이 붙는다 |
| `harness/zone_study_eval.py:327` `_check_send_ledger` | 기록의 `send_ledger` 절(선택)은 닫힌 객체다. 요청별 전송 수가 호출 기록의 `http_attempts`와 같고, 합계가 `sent`와 같아야 한다 |

### Codex 반례 재현 (`test_results.json` `codex_counterexamples`)

같은 어댑터·시나리오를 수정 전(`840fd1ce`)과 수정 후 코드에서 돌렸다.

| 반례 | 수정 전 | 수정 후 |
|---|---|---|
| 1. 상한 1. `submit()`이 전송한 뒤 `NotSent`를 던지고, 호출자가 처리한 뒤 3번 다시 실행한다 | 실제 전송 **3**, 청구 **0**, 예산 사용 0, 예약 0, SIM **0** s, 위반 0, 환불 3 | 실제 전송 **1**, 청구 1, SIM 0.5 s, 위반 `not_sent_contradicted`. 재실행 2번은 예산 거절로 **보내지 않는다** |
| 1'. 상한 없이 같은 어댑터 | — | 전송 3, 청구 **3**, 위반 3건, SIM 3 × 0.5 s (`test_r7_codex_1_uncapped_…`) |
| 1''. 상한 1에서 `submit()` 한 번에 3번 보낸다 | — | 1번만 wire에 닿고 2번은 wire 전에 막힌다(`http_budget`) |
| 2. 상한 2. 첫 요청과 예약한 재시도를 보내고 `TransportFailure(sent_attempts=1)`, 호출자가 한 번 더 요청 | 실제 전송 **3**, 청구 **2**, 위반 0 | 실제 전송 **2**, 청구 2, 위반 `declared_sent_mismatch`. 스케줄러 재시도는 예산 거절, 응답 실행 없음 |
| 2'. 상한 3에서 거절된 재시도까지 억지로 보낸다 | — | 3번이 청구되고 4번째는 wire 전에 막힌다 |

## 계약 버전: 기록 자신의 registry 해시로 정한다 (P2)

| 위치 (`94841738`) | 내용 |
|---|---|
| `harness/zone_study_contract.py:264` `registry_versions`, `:271` `contract_version_for_registry` | `{registry 해시: 버전}`(v1 `f1ff6a49…`, v2 `c9bb5556…`)이다. 모르는 해시·타입은 `ContractViolation`이다 |
| `:1433` `call_record_violations` | 호출 기록의 `provenance.registry_sha256`이 알려진 버전의 해시여야 한다 |
| `harness/zone_study_eval.py:245`·`:277` `_contract_version` | `parse_trial()`이 호출 기록과 시행 provenance가 **하나의** 해시를 쓰는지 확인하고 그 버전을 `trial['contract_version']`에 적는다. 해시가 섞였거나 직접 적은 버전이 다르면 거절한다 |
| `:305` `_stored_payload_problems` | 저장된 요청의 user JSON에서 `dialogue_window`를 뺀 payload를 **그 버전**의 `payload_violations`로 다시 검사한다. 호출 provenance의 주문서·지도 해시로 고정한다 |
| `:640`·`:706` | 문제는 입력 경계 감사의 `payload_contract_violations`가 된다. 시행은 `violation`이 되고 코호트 집계에 들어간다. 보고서 표에는 "계약 버전 위반" 열이 생긴다(`scripts/zone_study_report.py:208`) |

- **Codex 반례:** tags_v2 지도로 만든 정상 기록은 v2로 감사하면 clean이다. 같은 기록의 시행·호출 provenance를 v1 해시로 바꾸면 `violation`이 된다. 모든 요청이 `near_door_spacing_m`·`near_door_radius_m`·`door_posts` 위반을 보고한다. 미등록 해시는 `parse_trial`에서 거절된다.
- **동결 기록:** v3·v4(v1)·v5(v2)의 `example_trial_record.json.gz`는 커밋 해시가 그대로다. 각 기록은 자기 버전으로 감사해 clean이다. v2 예시(v1)는 수정 전과 같이 `unverified`다. 옛 기록이라 요청 원문이 없다.
- 다이제스트를 다시 계산해 금지 키(`own_pose_m`)를 넣은 저장 본문도 버전 재검증에서 잡힌다(`test_r7_p2_a_request_whose_body_was_edited_consistently_is_still_caught`).

## 수정 전 실패 / 수정 후 통과 (`test_results.json`)

- **수정 전:** `840fd1ce`의 트리를 `git archive`로 /tmp에 풀고 최종 r7 테스트 3개 파일만 올려 파일별로 돌렸다.
  - r7 26개 중 **25개가 실패**했다. 통과 1개는 대조군(장부 0회인 참 `NotSent`의 환불·재던짐, 옛 규칙과 같음)이다. Codex 반례는 `assert (3, 0, 0) == (1, 1, 1)`, `assert (3, 2, 2) == (2, 2, 2)`로 실패한다.
  - r7_contract 22개 중 **21개가 실패**했다. 통과 1개는 대조군(tags_v1 기록은 두 버전 모두 clean)이다. 반례는 `'clean' == 'violation'`, 미등록 해시는 `DID NOT RAISE`로 실패한다.
  - r7_transport 38개는 `harness.zone_send_ledger`가 없어 수집 단계에서 `ImportError`가 났다.
- **수정 후:** r7 86/86이 통과했다. 관련 17개 모듈은 **801 passed**이고 실패·건너뜀은 0이다. tensorboard를 막은 실행(CI offline 작업 흉내)에서도 r7 86/86이 통과했다.
- **기존 테스트 이관:** r1~r6와 스케줄러 테스트의 전송 계층 13개가 장부를 지나도록 옮겼다. 규칙이 바뀐 사례 5개는 기대값을 새 규칙으로 바꿨다. 예약보다 많은 보고는 이제 장부 수로 청구하고 위반으로 기록한다. 선언 없이 예약만 하고 보내지 않은 재시도는 2회 대신 장부 1회로 센다. `reply()`의 `NotSent`는 위반이다.
- **CI 수집:** 패턴은 221개 모듈을 고르고 r7 3개 파일을 포함한다. `test_r7_all_files_of_this_round_are_collected_by_the_ci_patterns`가 이를 스스로 확인한다. 필수 모듈이 없으면 성공으로 넘어가지 않고 실패한다(`test_r7_the_send_ledger_is_required`, 수집 오류).

## 변이 검사 (`mutations.json`)

`94841738` 사본에서 수정 조각 43개를 하나씩 되돌렸다. **43/43이 r7 테스트를 실패시켰다.** 원복하면 86/86이 통과한다. 첫 실행은 41/43이었다. 살아남은 2개(응답을 넘긴 뒤 SIM 해제 전 창의 전송, 참 `NotSent` 재던짐 삼킴)는 테스트 약점이었다. 두 테스트를 더한 뒤 전부 다시 돌렸다.

| 영역 | 변이 수 | 예 |
|---|---:|---|
| 스케줄러 정산 | 18 | `NotSent` 신고 신뢰(옛 규칙), 선언값 청구, 위반 종류 4종 제거, wire 허가에서 예약 생략, 정산 뒤 전송 허용, 과대 보고 미절단, 위반 응답 실행, 환불 누락, `NotSent` 삼킴, 장부 없는 전송 계층 허용, `ReplayTransport` 우회, `commit` 검사 제거, 중단 기록, censor 경로 |
| 장부 | 7 | wire 실패 미계수, 허가 생략, 덮어쓰기, 저장 실패 후 전송, 주인 둘, `SendBlocked`를 `OSError`로, 바이트 아닌 본문 |
| 어댑터·오프라인 | 6 | 임의 opener 허용, timeout을 error로, URL 기본값, `cost_checks` 장부 무시, 기록 키, 번들 ID |
| P2 | 12 | 현재 버전으로 감사, 재검증 제거, 모르는 해시 허용(2곳), 섞인 해시 허용, 직접 적은 버전 모순, 고정 제거, clean·실패 키 누락, 창 포함 검증, 기록 장부 대조 제거, 보고서 열 |

## 스모크 영향 — v6

- 30개 시행 모두 v5와 **SIM trace·요청 입력 해시·호출 수가 같다**. `smoke.json`은 v5와 바이트 단위로 같다(`d61b7e9b…`). 1871개 호출 기록은 provenance만 다르다(`code_sha`, `execution_bundle_id` v2→v3, `model_settings_sha256` null→`2334d86b…`). trial record에는 `send_ledger` 절이 새로 생긴다.
- 30/30에서 장부 전송 수 = 호출 기록 `http_attempts` 합 = 예산 사용 = wire 수신 수다. 막힌 요청, 위반, 환불은 모두 0이다(`../v6/control_runs.json`).
- 기록 바이트가 달라져서 v5를 덮어쓰지 않고 v6으로 남겼다.

## 파일 길이 (600줄·80줄 규칙)

- `harness/zone_event_scheduler.py`는 1370줄이다(r6 1224). `harness/zone_study_offline.py`는 1011줄(r6 947), `harness/zone_study_eval.py`는 2070줄, `harness/zone_study_contract.py`는 1541줄이다. 모두 이미 600줄을 넘는 패키지 파일이다. 이번 라운드에서 새 코드는 새 파일 두 개로 나눴다. `zone_send_ledger.py`는 241줄, `zone_study_llm_transport.py`는 102줄이다. 기존 파일을 나누지 않은 이유는 r6와 같다. PR #229가 같은 파일 위에 쌓여 있어 분할하면 충돌이 커진다. 분할은 #194·#229 병합 뒤 별도 작업으로 한다.
- 새로 만들거나 고친 함수는 모두 80줄 이하다. `__init__`은 75줄, `_on_call_done` 67, `_censor_outstanding` 64, `_reply_of` 62(설명 포함), `_submit` 37, `_authorize_send` 34, `_release_unsent` 31, `audit_input_boundary` 76, `_contract_version` 26이다. eval의 기존 긴 함수(`efficiency_metrics` 등)는 이번에 고치지 않았다.

## 남은 범위

- **신뢰 경계:** 장부는 opener를 지나는 요청만 본다. 어댑터가 소켓을 직접 열면 장부에 잡히지 않는다. `ModelCallTransport`는 호출의 opener만 completer에 넘기고, `GeminiProxyCompleter.complete`의 네트워크 경로는 `self.http_open` 하나다. 이 사실은 코드 검토와 소켓 차단 테스트로 확인했다. 실제 프록시로는 아직 확인하지 않았다.
- 실제 `gemini-3.8-flash` 파일럿에서는 `live_send_ledger(store_dir=…)`로 wire 바이트를 저장하고, 공급자 청구와 장부를 대조해야 한다. 이번에는 실제 호출을 하지 않았다.
- 통합 PR #229는 이제 `ModelCallTransport`·`SendLedger`를 가져와야 한다. `EventScheduler`가 장부 없는 전송 계층을 거절하기 때문이다. #229의 자체 전송 계층도 장부를 지나도록 바꿔야 한다.

## 파일

| 파일 | 내용 |
|---|---|
| `test_results.json` | 수정 전(파일별 사례·메시지)·후 결과, Codex 반례 수치, tensorboard 없는 실행, 관련 모듈 801, CI 수집, 이관 설명 |
| `mutations.json` | 변이 43개의 원문·변이 문자열·결과, 첫 실행 기록 |

JUnit 원본(`/tmp/kiro-r7-*.xml`)은 임시 파일이며 해시만 남겼다.

## 참고 자료

- 논문: 이번 라운드를 위해 새로 찾은 논문은 없다. 사용량 미상을 하한으로 표시하는 근거는 5·6차와 같다. Donald B. Rubin, "Inference and missing data", *Biometrika* 63(3), 1976, https://doi.org/10.1093/biomet/63.3.581
- OSS
  - CPython 3.12 표준 라이브러리 `urllib.request`(`Request`, `urlopen`)를 썼다(PSF License). 장부는 `GeminiProxyCompleter`가 이미 받는 `http_open(request, *, timeout)` 주입점에 붙였고 새 의존성은 없다.
  - pytest 9.1.1 (MIT), https://github.com/pytest-dev/pytest — `monkeypatch`(`urlopen`·소켓 차단), `parametrize`, `tmp_path`
  - TensorBoard 2.21.0 (Apache-2.0), https://github.com/tensorflow/tensorboard — 기존 `write_events`로 v6 스냅샷을 만들고 HTTP API로 대조했다
  - websockets 16.0 (BSD-3-Clause), https://github.com/python-websockets/websockets — 캡처 도구의 Chrome DevTools Protocol 연결(시스템 python3 3.13.5)
- 내부 모듈·PR
  - `harness/gemini_proxy.py` `GeminiProxyCompleter`(`http_open` 주입, 오류 분류 `GeminiProxyError`)를 그대로 재사용했다
  - 감사 opener 패턴: `scripts/pilot_korean_dialogue.py` `audited_open`(2026-09-25 한국어 파일럿, `experiments/2026-09-25-zone-dialogue-ko-pilot/`), `scripts/three_robot_runtime.py` `audited_open`
  - `harness/zone_event_scheduler.py`(`AttemptBudget`, `PendingCall`, `TransportFailure`), `harness/zone_study_offline.py`, `harness/zone_study_contract.py`(`registry_sha256`, `payload_violations`), `harness/zone_study_eval.py`, `harness/zone_study_prompts_ko.py`(`verify_archived_request`, `WINDOW_KEY`), `scripts/zone_study_report.py`, `scripts/run_ci_tests.py`
  - PR #229 `experiments/2026-09-26-zone-study-integration/tb_capture.py`(TensorBoard 캡처, /tmp 복사 사용)
- 문서·웹
  - Codex 7차 검토 `codex-194-r7`, `docs/zone_sim_cost.md`, `docs/zone_study_contract.md`, `docs/tensorboard.md`, `AGENTS.md`
  - Python `urllib.request` 문서: https://docs.python.org/3.12/library/urllib.request.html
- 채택하지 않은 대안
  - **신고 규칙 보강(6차 방식 연장):** `NotSent`·`sent_attempts`에 조건을 더해도 어댑터가 틀리게 신고하면 과소 청구가 남는다. Codex가 지적한 것은 신뢰 가정 자체였다.
  - **HTTP 응답 뒤에 기록:** wire가 요청을 쓴 뒤 연결이 끊기면 장부에서 빠진다. 5·6차 반례와 같은 구멍이다. wire 호출 전에 기록한다.
  - **예산 초과를 사후 기록(`over_budget_attempts`):** 초과 요청이 이미 나간 뒤에 알게 된다. wire 전 허가로 막았고, 사후 경로는 도달할 수 없게 되어 지웠다.
  - **소켓·`http.client` 수준 패치(monkeypatch)로 계수:** 전역 상태에 기대고, 다른 스레드·작업의 요청까지 섞인다. completer가 이미 주입받는 opener를 호출별로 묶는 편이 귀속이 정확하다. 소켓 차단은 테스트에서만 쓴다.
  - **mitmproxy 같은 외부 프록시 장부:** 새 의존성과 상주 프로세스가 필요하다. 로컬 프록시 앞에 또 프록시를 두는 셈이다. 같은 opener 패턴으로 충분하다.
  - **기록에 계약 버전 문자열만 추가:** 그 문자열이 또 하나의 자기 신고가 된다. 이미 기록된 registry 해시에서 버전을 결정하고, 직접 적은 버전은 해시와 대조만 한다.
