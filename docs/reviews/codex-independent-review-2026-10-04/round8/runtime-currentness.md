# #371 게시 직전 최신성 보완 — 1883c56 → a009112

8차 원 검토·재현의 고정점 `1883c56a749dc89597d57f570d4a2243cbb9595d`와 새 head **`a009112ff5fb18c6b64f58d8cd6392c58d4c028c`**를 대조했다. 공식 GitHub compare는 ahead1commit, 변경5파일을 반환했고, 로컬의 정확한 두 Git object에서도 같은 변경 경로를 확인했다. 기존1883 원고·스크립트·결과는 그대로 보존했다.

새 커밋은 `pair_llm_dispatch.py`, `pair_llm_prompts_ko.py`, `pair_llm_status.py`, 관련 status test, 실험 README를 바꿨다. 이 보완은 코드/테스트만 읽었고 새 raw·점수·실험 결과 자료는 열지 않았다. 새 모델·물리 실행도 없다.

| 항목 | a009 판정 | 근거 |
|---|---|---|
| **R8-R1 전송 후 실패의 이미지 SIM 비용 누락** | **유지. 수정 아님** | `zone_study_llm_transport.py`, billing, cost, scheduler, driver는 파일 바이트가 동일. PairTrial의 요청 준비·완료·수집·비용 메서드도 AST 동일 |
| **R8-R3 종료 오류의 failure_class/원장 불일치** | **유지. 수정 아님** | `pair_llm_case.py`, `pair_llm_live.py`, shared driver, budget, CLI 모두 바이트 동일 |
| R8-R2 긴 비429 quota 판별 | 조건부 보강 판정 유지 | `pair_llm_live.py` 바이트 동일; 실제 발생 근거는 여전히 없음 |
| 이전 own_status 시계 혼합 | 이번 새 커밋이 직접 수정한 범위 | gate timestamp에서 origin을 빼고 job-end도 event occurrence time−origin으로 변경. frontier의 별도 반례/대조 재검증 판정을 따른다 |
| 이전 `__CHARS__` prompt literal | 이번 새 커밋의 수정 대상 | prompt 변경은 별도 frontier 검증 대상. 본 메모가 옛 literal finding을 현재 미해결이라고 재게시하지 않는다 |

R8-R1의 새 source anchor는 [PairTrial.finish_call377–425](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L377-L425), [공유 transport 실패 청구159–189](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_transport.py#L159-L189)다. 새 prompt가 텍스트 길이를 바꿀 수는 있으나, 전송된 동일 요청의 실패 경로에서 `total_billed` 대신 `total_text_billed`를 선택하는 차이는 그대로다. 원 재현의 절대 SIM초 표는 합성100텍스트토큰 fixture 값이며 새 실제 prompt 실행값으로 승격하지 않는다.

R8-R3의 새 source anchor는 [case finally271–309](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L271-L309), [live258–264](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_live.py#L258-L264), [run_attempts581–589](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_llm_driver.py#L581-L589)다. 최종 write가 성공하여 record가 반환되는 조건, CLI exit1, provider 사용량 보존, post-send 재전송 금지라는 원 검토의 한계와 수용 기준도 그대로다.

12개 관련 파일의 byte equality와 `PairTrial.__init__`, `prepare_call`, `finish_call`, `_collect`, `cost_summary`, `_release_action`, `_on_action`, `on_claim_result` **8개 메서드의 AST equality**를 확인했다. 변경된 dispatch 부분은 CLOCKS 설명, `PairLink.gate_view`, `PairTrial.on_executor_event`에 한정된다. 이들 수정이 R8-R1/R3의 비용/종료 분류 경로를 바꾸지 않으므로 기존 타깃 재현을 불필요하게 다시 실행하지 않았다. 이는 새 head의 전체 test/물리 검증을 주장하는 것이 아니다.

파일별 old/new Git blob·SHA256, 메서드 줄 번호·AST hash와 비교 시각은 `runtime-latest-delta.json`에 있다. 해당 증거 SHA256: **`530b19b31158cbe9914d08e57bf77f1c542b367252e35a8c96fc8db1d616aa6f`**. exact a009 소스는 `runtime-latest-source/`에 따로 보존했다.
