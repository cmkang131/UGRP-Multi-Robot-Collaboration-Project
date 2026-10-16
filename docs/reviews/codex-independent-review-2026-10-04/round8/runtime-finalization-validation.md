# 8차 runtime 종료 기록 후보의 독립 검증

2026-10-04 UTC. 대상은 PR #371 `1883c56a749dc89597d57f570d4a2243cbb9595d`의 **종료 단계 예외 뒤 실패 분류와 durable run 상태의 불일치**다. 평가 감사 담당이 runtime 담당의 재현을 별도로 실행하고 실제 호출 경로를 읽었다.

## 확인 결과

`python runtime-finalization-repro.py > runtime-finalization-independent.json`은 종료 코드 0으로 끝났다. 새 출력은 원래 `runtime-finalization-repro.json`과 실제 측정되는 `latency_ms`만 제외하면 모두 같았다. 이 재현은 원본 case 함수/분류 함수의 AST를 바꾸지 않고 실행하며, world·executor·decision·최종 평가 내용은 fixture이고 네트워크는 차단한다. 실제 SQLite 예산·요청 정산 코드와 run-attempt 함수는 사용한다. 실제 디스크를 채우거나 LLM/시뮬레이션을 실행하지 않았다.

| 합성 조건 | case status | failure_class | SQLite run 상태 | 요청 / 보존 토큰 |
|---|---|---|---|---|
| 정상 종료 | COLLECTED_UNQUALIFIED | null | finished | 1 / 100 |
| student record 예외 | HOST_ERROR | **null** | **finished** | 1 / 100 |
| LLM artifacts 예외 | HOST_ERROR | **null** | **finished** | 1 / 100 |
| finalize 예외 | HOST_ERROR | **null** | **finished** | 1 / 100 |
| backend.close 예외 | HOST_ERROR | **null** | **finished** | 1 / 100 |
| 첫 요청 전 reset HOST_ERROR 대조 | HOST_ERROR | infra:HOST_ERROR | failed | 0 / 0 |

마지막 음성 대조만 1회 재시도하고, 재시도도 동일 오류로 끝난다. 요청을 이미 보낸 네 종료 예외는 요청을 반복하지 않는다.

## 실제 호출 경로

1. 최신 [CLI run_live 155–178행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/scripts/run_pair_llm.py#L155-L178)은 `live.run_pair_live`를 호출하고 최종 status/failure_class를 기록한다.
2. [pair_llm_live 244–264행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_live.py#L244-L264)의 실제 `finalize`는 `llm/live_driver.json`을 쓴다. case가 반환되면 `(result, None)`을 `run_attempts`에 넘긴다.
3. [case finally 271–292행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L271-L292)은 이 네 종류의 예외에서 status와 해당 error 문자열은 바꾸지만, 이미 정상 종료로 계산된 `failure_class=None`은 갱신하지 않는다.
4. [run_attempts 578–586행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_study_llm_driver.py#L578-L586)은 예외나 failure_class만으로 durable run의 failed/finished를 정한다. case의 status를 참고하지 않는다.

생산 `_evaluate` 함수도 읽었다. 이 함수는 `host_status`를 metrics에 기록하지만 case의 `failure_class`를 보정하지 않는다. 따라서 fixture에서 최종 평가 내용을 생략한 것이 위 불일치를 만든 원인은 아니다.

## 반드시 유지할 한계

- **무재시도 자체는 버그가 아니다.** 첫 요청 뒤는 HOST_ERROR로 올바르게 분류되어도 재시도하면 안 되는 계약이다.
- **실패가 전부 숨겨지는 것은 아니다.** case status와 `record_error`/`llm_record_error`/`finalize_error`/`cleanup_error`가 남으며, CLI는 status가 HOST_ERROR이면 종료 코드 1을 반환한다.
- **비용 소실 반례가 아니다.** 합성 정상 응답 한 번의 100 토큰은 SQLite와 metrics 양쪽에 남는다.
- `protocol_complete=True`는 bounded loop 완료를 뜻할 수 있다. 종료 기록의 분류 오류와 별개로 이 필드 자체가 틀렸다고 단정하지 않는다.
- 재현은 **한 종료 경계에서 예외가 발생한 뒤 마지막 metrics/result 기록은 성공**하는 경우다. 지속적인 ENOSPC가 마지막 기록도 실패시키면 예외가 `run_attempts`까지 전파되어 HOST_ERROR로 분류될 수 있다. 모든 디스크 부족이 finished가 된다는 주장이 아니다.
- 이 synthetic 결과는 실제 사용자 실행에서 같은 오류가 발생했다는 증거가 아니다.

P2 신규 발견의 범위는 종료 경계의 실패를 담는 case 기록과 canonical `failure_class`/durable run 상태가 서로 모순된다는 점이다. 수정 시 기존 요청·비용·원본 error 필드와 첫 요청 뒤 무재시도 규칙을 그대로 보존해야 한다.
