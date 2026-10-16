# 추가7차 — PR #371 runtime/LLM 계약 독립 검토

고정 source: **`1883c56a749dc89597d57f570d4a2243cbb9595d`**, base **`f2577bb5121748644df31eb0fc5a1c1b94b80d80`**. 처음 배정받은 a148 이후 head가 바뀐 사실을 publication_currentness와 확인하고 최신 snapshot으로 옮겼다. #363은 최신73429982를 확인했지만 이 메모의 새 finding은 #371에만 속한다. 이후 head에 자동 승계하지 않는다.

코드·구성·관련 테스트와 기존 round5/6/최종 원고를 읽었다. 저장소 소스 변경, Git 작업, 모델·물리·GPU·실물 실행, raw/blind/results 원본 열람, GitHub 게시를 하지 않았다. 아래 실행은 fake own-link/event 및 fake SIM clock을 넣은 작은 계약 진단이다. 상대 구현과 별도 결과이며 실제 운반·look 회복 효능을 검증한 것이 아니다.

## 결과

| 계약/가설 | 결과 | 실제 경로와 범위 |
|---|---|---|
| 새 own_status가 같은 상대 사건 순서를 reset origin과 무관하게 요약한다 | **신규 P2 후보: 반례 재현**. absolute gate timestamp와 relative job-end timestamp를 직접 비교한다 | 두 LLM arm의 필수 `PairTrial.snapshot` 경로. 순서가 가까운 claim/refusal와 look 종료 조합에서 노출. rule arm에는 없음 |
| look_around가 기존 job을 교체하거나 반복 호출로 두 look을 만든다 | **음성**. busy/stopped에서 거절하고 기존 job 객체를 보존한다 | 선택적 LLM action→`PairLink.call`→기존 executor._start의 실제 함수. physical loaded sweep의 안전성 판정은 아님 |
| 이미지 비용을 포함한 응답 action/message가 청구 완료 전 또는 censor 후 방출된다 | **음성**. action은 cost release, message는 추가 delivery 지연 뒤; horizon censor 후 resume도 방출0 | 새 look action을 담은 actual shared EventScheduler+ReplayTransport. live HTTP/완료 parser 전체 인수는 아님 |

## R7-R1 — own_status의 최신 사건 선택이 reset offset에 의존한다

**문제:** `last_outcome`의 최신 사건을 선택하는 시간축이 섞여 있다. 최신1883의 clock 이름 추가는 로그 설명/필드를 보완했지만 이 비교를 정규화하지 않는다. 코드의 `_RANK`/`max(time, rank)`와 기존 `test_the_latest_fact_wins_a_new_claim_after_a_rejection_after_an_end`의 계약대로라면 동일한 상대 사건 순서는 reset offset과 무관하게 같은 상태가 되어야 한다.

실제 authority/call chain:

1. [case200–213](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L200-L213)는 reset 뒤 `start=backend.now`, `PairLink(...origin_s=start)`를 만든다. [case225–245](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L225-L245)는 `links.tick(backend.now)`와 absolute runtime tick을 쓰지만 own event에는 `at_s=elapsed`를 준다. own event 전달/`trial.step_to`가 다음 `runtime.step`보다 앞선다.
2. [PairLink138–171,183–195](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L138-L195)의 `_abs_now`가 `grant(...now=self._abs_now)`로 전달된다. `gate_view()`는 `status_view()`를 그대로 반환한다. `clock()`와 RGB frame timestamp는 별도로 origin을 빼므로 gate도 이미 상대값이라는 해석은 맞지 않는다.
3. [ClaimGate64–86,89–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_runtime.py#L64-L119)는 permit 및 submission event에 넘겨받은 `now`를 그대로 기록한다. `GatedRuntime.grant`도 정규화하지 않는다.
4. [PairTrial305–328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L305-L328)는 view를 그대로 `status.build`에 주고, `_last_end.sim_s`는 상대 `at_s`를 기록한다.
5. [status89–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L89-L105)가 permit/거절의 absolute 값과 end의 상대값을 하나의 facts에 넣어 `max`를 고른다. [build_inputs335–340](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L335-L340)를 거쳐 모델 입력으로 쓰이는 값이므로 private log 표기의 문제에 그치지 않는다.

작은 반례 A — look이 실행 중일 때 claim permit을 받고, 0.5초 뒤 look 종료 event가 전달되는 동일 상대 history:

| reset offset | permit stored | look-end stored | 현재 last_outcome | 한 시간축으로 정규화한 대조군 |
|---:|---:|---:|---|---|
| 0 | 10.0 | 10.5 | look_around_ended | look_around_ended |
| 1.3 | 11.3 | 10.5 | **claim_released** | look_around_ended |

`PairLink.call('pair_carry')`는 현재 job이 **pair_carry**일 때만 거절하므로 look 실행 중 permit 발행 자체는 현 API에서 허용한다. `Runtime.step`은 job이 있을 동안 gate.start를 시도하지 않는다. look 완료 다음 tick에서 end 이벤트를 전달하고 `trial.step_to`를 먼저 실행하므로, 새 claim submission 이전에 이 snapshot 조합을 읽을 코드 경로가 있다. 다만 이는 **adapter가 허용하는 fake endpoint schedule**이다. 실제 look 길이와 모델 SIM 비용을 함께 실행한 증거가 아니며 실제 provider/초기 look 지속시간으로 그 조합의 발생 빈도를 측정하지 않았다. 별도 독립 검증자가 같은 경로 및 `0 < end_relative - claim_relative < origin`일 때의 역전을 확인했다(끝점 동률 제외).

반례 B — 같은 상대 history에서 거절10.0, look 종료14.0:

| reset offset | refusal stored | look-end stored | 현재 last_outcome | 정규화 대조군 |
|---:|---:|---:|---|---|
| 0 | 10.0 | 14.0 | look_around_ended | look_around_ended |
| 1.3 | 11.3 | 14.0 | look_around_ended | look_around_ended |
| 5.0 | 15.0 | 14.0 | **claim_rejected / WRONG_PAIR_DESTINATION** | look_around_ended |

두 반례에서 `since_claim_s`와 refusal count는 일치하고 모든 실제 결과가 `status_violations(...) == []`이다. 스키마 적합성은 사건 순서의 시간축 일관성을 검증하지 않는다. 반례B의 origin5는 현재 `RESET_CAP_S=5` 범위 끝이며, 작은 origin이면 이 **특정 간격**에서는 문제가 나오지 않는 음성 대조도 보존했다.

**현재 영향/한계:** 최신 사건 label/reason이 오래된 claim 쪽으로 뒤집혀 LLM의 재관측/재요청 판단을 바꿀 수 있다. 실제 LLM이 행동을 바꾸었다거나 물리 실패의 원인이었다고 주장하지 않는다. running job은 `_RUNNING` 분기가 먼저 반환하므로 이 반례는 idle snapshot에서 최신 end와 gate fact가 경쟁할 때의 문제다. no_comm과 peer_nl 모두 같은 경로를 쓰며, 이를 새 정답 입력 누설 finding으로 해석하지 않는다.

**닫는 기준:** model-facing status 비교 전에 gate permit/event와 job end를 동일 시간축으로 맞추고, origin0과 nonzero의 동일 상대 history에 대한 invariance 검사를 추가한다. absolute 원본 로그를 없애거나 사건 분류 정책을 새로 바꾸라는 요청이 아니다. 위 정규화는 테스트 대조군에서만 수행했고 구현은 수정하지 않았다.

## R7-R2 — look re-entry/idle 제한 반증

[dispatch196–199](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L196-L199)는 `ZoneOwnExecutor.look_around()`를 호출하고, 공유 [executor263–271,371–372](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_own_executor.py#L263-L271)의 `_start`가 stopped/모든 busy job을 검사한다.

actual 함수의 작은 합성 결과: idle 최초 look accepted; 곧바로 두 번째 look은 `BUSY:look_around:r1-job-001`; 현재 pair job 중 look은 `BUSY:pair_carry:pair-live`; stopped idle에서는 `ROBOT_STOPPED`. 두 busy 경우의 job 객체 identity를 보존했다. 따라서 새 action이 pair를 강제 중단하거나 look을 겹쳐 실행한다는 가설은 반증됐다. 이 점은 이미 알려진 설계의 재확인이며 새 finding으로 게시하지 않는다. provider 재지역화 정보량, pending claim의 자동 시작 타이밍, 실제 loaded sweep/캐시 신선도의 전 범위를 증명한 것이 아니다.

## R7-R3 — 비용 release와 horizon 뒤 실행의 반증

공유 [EventScheduler944–968](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_event_scheduler.py#L944-L968)는 reply가 이미 도착해도 `started + call_cost`에 완료를 예약한다. [1416–1482](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_event_scheduler.py#L1416-L1482)에서 정상 완료만 action/message를 방출하고, [849–918](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_event_scheduler.py#L849-L918)은 censor된 call_done을 큐에서 제거한다.

새 `look_around` action과 한 메시지, 입력5980/출력40/발화1의 fake reply를 production `ReplayTransport`/`EventScheduler`에 주었다. provisional cost는3.3SIM초. 3.2까지 action0/message0,3.3에 action1/message0,3.4에 action1/message1을 확인했다. 별도3.2 horizon에서 censor하고13.3까지 재개해도 action/message callback0이고 censor row에는 input5980·attempt1이 남는다. 청구 전 방출/늦은 응답 재활성화 가설은 이 경로에서 반증했다.

fullmetrics.model_usage가 실패·unknown cost를 보존하는 최신 개선,1490/image의 연결은 인정한다. 이 검사는 그 provider 비용 원장의 전체 QA나 실제 HTTP wall latency의 인증이 아니며,1490 상수의 타당성/물리 효과를 새로 주장하지 않는다. 이미 알려진 __CHARS__·staged history·same-tick abort·rendezvous admission 문제를 새 finding으로 재포장하지 않았다.

## 독립 재현

```
python3 /workspace/scratch/21cbee94d5d2/review-notes/tmp/round7-runtime-contract-repro.py
```

출력: `review-notes/tmp/round7-runtime-contract-repro.json`. Python 표준 라이브러리와 base의 pure scheduler/helpers만 사용한다. 네트워크 socket/물리·학습 모듈을 명시 차단했다. 원문 AST에서 선택한 함수/클래스를 **body 수정 없이** 컴파일해 optional simulator/OpenCV 의존성을 피했다. constructor/event sink/own input은 fake이고 실제 world 이미지가 아니다. repro 파일의 해시는 아래 코드를 마지막 수정한 시점의 값이다.

| 파일 | SHA-256 |
|---|---|
| tmp/runtime-round7-source/harness/pair_llm_dispatch.py | f53c31b61c6cecee3112d0c31d744f8b55ef8a1b64b429c7903ab3eac0b67dc9 |
| tmp/runtime-round7-source/harness/pair_llm_runtime.py | 5b08cb392e41346d3aad0162f5688bc641c7014dfaeaddf2acfbc3048a52b791 |
| tmp/runtime-round7-source/harness/pair_llm_status.py | 984b440be9c53fe6e610279ad9207a5598a697dda673d52183385a101dab0dd1 |
| tmp/round7-runtime-contract-repro.py | 0b18ec9d6712ba4bfff1a01bafa935f4a8dff1dccf4455daeb08b3b5ad594638 |

runtime snapshot은 GitHub exact1883 파일 API에서 받았고, dispatch/status는 publication_currentness/pr371_delta가 exact1883에서 저장한 snapshot을 복사했다. shared `zone_study_integration.py`, `zone_event_scheduler.py`, `zone_own_executor.py`는 f257 base source로 해당 PR의 변경 대상이 아닌 helper다. 원본 테스트 전체·physics E2E를 실행했다는 주장이 아니다. root가 별도 독립 검증 담당자를 배정했고 게시 여부/표현은 그 검증 결과와 함께 확정한다.
