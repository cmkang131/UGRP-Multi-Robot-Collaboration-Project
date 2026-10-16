# 전달 직전 #371 갱신 — 기존 clock/placeholder 두 항목 해결 확인

**2026-10-04 06:08:23.233 UTC에 공식 metadata를 다시 조회하자 #371 head가 `1883c56a`에서 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`로 바뀌었다**(`updated_at=06:07:54Z`). main `b23fc087`, #363 `0d7c5eb3`, #372 `f676889f`는 그대로였다. 아래는 새 1커밋의 좁은 후속 검증이다. `current-frontier.md` §5의 own_status 지속 판정과 이전 원고의 `__CHARS__` 미치환은 **1883 시점의 역사적 사실**이며, 두 항목 모두 a009에서는 아래 범위로 해결이 확인됐다.

공식 compare에서 바뀐 파일은 `harness/pair_llm_dispatch.py`(+25/−4), `pair_llm_prompts_ko.py`(+15/−2), `pair_llm_status.py`(+4), 관련 상태 시험(+133/−1), 실험 README 문구(+19)뿐이었다. 이 후속은 코드 세 파일과 관련 시험의 차이를 읽고 기존 반례를 다시 실행했다. raw·실제 실험 결과를 새로 열지 않았고 전체 PR/CI/물리/LLM을 재검증한 것은 아니다.

## own_status 시간축: 해결 확인

[PairLink.gate_view](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py)는 permit와 last_event의 absolute SIM 시각에서 reset origin을 빼서 반환한다. [PairTrial.on_executor_event](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py)는 job 종료도 전달 시각 대신 event 자체의 발생 시각에서 origin을 빼서 기록한다. 원본 absolute 기록과 전달 시각은 로그에 따로 남긴다.

기존 재현의 **실제 caller body를 그대로 사용하고 입력 일정도 유지**했다. 새 소스에 맞춰 판정 oracle만 바꿨고, 이전의 테스트 대조용 추가 정규화 값은 이번 결과에서 제거했다. Git blob 정확본 3파일과 변경 없는 공유 helper를 사용했다.

| 기존 반례 일정 | reset origin | a009 결과 |
|---|---|---|
| permit 10.0, look 종료 전달 10.5 | 0 / 1.3 / 2.6 / 4.9 | 모두 `look_around_ended` |
| 거절 10.0, look 종료 전달 14.0 | 0 / 1.3 / 5.0 | 모두 `look_around_ended` |
| 첫 일정에서 `gate_view` 변환만 제거한 돌연변이 | 0 / 1.3 | `look_around_ended` / **`claim_released`**로 옛 반례 재발 |

첫 일정의 종료 event 자체는 전달보다 0.05초 전이므로 `_last_end.sim_s`가 모든 origin에서 **10.45**인 것도 확인했다. 이는 새로운 코드가 전달 지연을 사건 순서로 오해하지 않게 바꾼 범위다. 실제 look 길이·모델 비용을 함께 돌린 물리 인수 결과가 아니라 fake endpoint schedule의 시간축 일관성 확인이다.

따라서 이 항목을 최신 #371의 미해결 P2로 남기면 부정확하다. 1883 스냅샷 반례는 보존하고 a009 해결로 연결한다. 새 SIM 비용·종료 예외 finding의 a009 영향 여부는 runtime 후속 검토가 별도로 다룬다.

## `__CHARS__` 최종 프롬프트: 해결 확인

[a009 prompt renderer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_prompts_ko.py)는 `__CHARS__`를 기존 study의 `PROMPT_TEXT_CHARS=240`으로 채운다. 마지막 `system_prompt`에서 다른 `__X__` 자리표시자가 남으면 `ProtocolError`로 거부한다. transport의 hard cap **600**과 프롬프트가 요청하는 **240**은 다른 값이며 이 수정은 그 기존 구분을 유지한다.

실제 `system_prompt` 함수를 `no_comm/peer_nl × r1/r2` 네 조합에 호출했다. 네 텍스트 모두 미치환 자리표시자 0개, peer_nl 두 텍스트에 `text는 240자 이내`가 들어 있었다. 미치환 `__REVIEW_SLOT__`을 테스트 메모리에서 추가하자 peer_nl renderer가 해당 이름의 `ProtocolError`를 냈다. 실제 wire 전송이나 모델 호출을 수행한 검증은 아니다.

## 재현물과 범위

- `frontier-own-status-a009-repro.py` / `frontier-own-status-a009-result.json`: 최신 actual snapshot 경로와 옛 변환을 되돌린 음성 대조.
- `frontier-prompt-a009-repro.py` / `frontier-prompt-a009-result.json`: 최종 system prompt 네 조합과 미치환 삽입 거부.
- `frontier-a009-source-hashes.json`: 정확한 Git blob·변경 없는 공유 helper 9파일의 SHA-256.
- `frontier-delivery-heads.json`, `frontier-delivery-pr371-delta.json`: 공식 currentness 시각과 changed-file metadata.

이 추가 확인은 a009의 두 수정에 한정한다. 앞의 1883 문서 전체를 최신 head 검토로 재명명하거나 PR 병합/전체 CI 승인으로 확대하지 않는다.
