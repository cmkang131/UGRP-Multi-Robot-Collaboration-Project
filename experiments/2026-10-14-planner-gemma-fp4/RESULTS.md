# Gemma fp4 기본 등록: 확인 실행은 형식 오류로 중단

새 기본 번들은 **v403**(prompt order off), **v404**(static_first_v1)다.
`google/gemma-4-31b-it`, provider order `["deepinfra/turbo"]`, fallback false.
공식 endpoint metadata에서 해당 태그의 fp4를 확인했으며 실제 두 응답의
model/provider는 Gemma / DeepInfra였다. 태그가 작동하여 대체 라우팅은 하지 않았다.
기존 Gemma 및 Ling 번들 설정·결과 파일은 변경하지 않았다.
자기 RGB 1장 전달·sha256 검사는 유지하지만 이번 이미지 확인은 실행하지 못했다.

호출 전 소스 `4aaac2c2`, 시작 실패 기록/빈 원장 처리 보완 후 호출 소스
`fcffd4c8c59e8e9afb6860ab685fdc10b43c0d8c`. 등록·전송·중단 관련 시험
총 36개가 통과했다(변경 범위별 실행; 물리·모델 시험 아님).
새 중계에도 600 HTTP 시도/$0.30 제한, 2초 간격·동시1·최대2회 재시도,
429 본문/헤더 원장과 5% 대체·형식 오류 및 지연 중앙8초 중단을 유지했다.

## 실제 결과

시작 시 `/api/v1/key`에서 예산을 뺀 잔여 $12.409815124를 확인했다.
HTTP 두 응답 모두 200이었다. 첫 응답은 유효한 JSON이었고 두 번째는
` ```json ` 코드 블록으로 감싼 JSON이었다. 현행 엄격한 `json.loads`가
이를 거부하여 **형식 오류 1/2와 대체 1/2**가 됐다. 기존 5% 중단 조건이
즉시 작동했고, 파서를 고치거나 중단 기준을 완화해 계속 호출하지 않았다.

| 항목 | 결과 |
|---|---|
| 요청한 본 결정 / 계획 | 2/400; 나머지 398개 미호출 |
| HTTP 시도 / 429 | 2/600 / 0/2 |
| 대체 / 형식 오류 | 1/2 / 1/2 |
| 재질문 / HTTP 재시도 | 0 / 0 |
| 모델 응답 중앙 / p90 | 3.414 / 3.921초, N=2 |
| 전체 결정 중앙 / p90 | 3.460 / 4.011초, N=2 |
| 공급자 usage 비용 | $0.0008241, 비용 미확인 0건 |
| prompt_tokens 중앙 | 4,329 |
| cached_tokens off / on | 0/8,658 = 0% / 미측정(0/40 호출) |
| 이미지 수락 | 미측정(0/5 호출; 수락 확인 0, 거부로 해석하지 않음) |
| 과거 r4 act/args 일치 | 요청한 2개 중 1/2, 유효 모델 결정만 보면 1/1 |

일치율은 거부된 응답을 불일치로 남겼다. 전체 계획 분모로는 확인된
일치 1/400이며 398개 미호출이다. 실패 후 규칙 선택이 과거 결정과 같더라도
모델 일치로 세지 않았다. 기존 r4 점수·호출·비용은 합산하지 않았다.
정확도 비교를 할 수 있는 완료 표본이 아니며 stale/wrong 전체 결과도 미측정이다.
원래 전체 분모를 보존한 raw 표에는 미호출도 대체 표시가 있으므로 그 399/400을
실제 대체율로 읽으면 안 된다. 요청한 결정의 대체는 1/2다.

처음에는 오프라인 입력에 native 전용 `--task-planner-v1` 중계 옵션을 붙여
`planner_backend` 누락으로 로컬에서 거부됐다. 이 시작 오류는 공급자 HTTP
0회·비용0이며 별도 `start-failure.json`에 보존했다. 해당 옵션을 뺀 direct
중계로 시작한 위 두 HTTP 시도와 분리했다. 빈 원장도 보고하도록 보완했다.

## 근거와 남은 일

요약은 `summary.json`, 입력 해시는 `freeze.json`, 번호 스캔은
`number-reservation.json`, 원본 경로·해시는 `raw-manifest.json`에 있다.
큰 결정 원장은 zstd 압축 후 해제 SHA-256을 확인했다. 원본은 로컬 보관이며
GitHub에 전체 raw를 업로드한 것으로 표현하지 않는다.
작업 중계 종료 확인, VM 실행/제출 없음, PR #473 draft 유지.

기존 중단 조건 때문에 **400+40+5 확인은 미완료**다. 코드 블록을 출력한
형식 오류의 원인은 확인했지만 이번 고정 프롬프트·출력 파서를 바꾸어 재평가하지
않았다. 캐시 순서 효과, 이미지 수락, E2E 처리량은 미확인이다.
PR #482의 40회 공급자 부하 검사는 별도 증거이며 여기 합산하지 않는다.

## 참고 자료

- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): endpoint tag를 order로 고정하고 fallback을 끄는 방법 확인.
- [Gemma endpoints](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints): `deepinfra/turbo` fp4와 단가, 저장본 `endpoints.json`. 반환 모델 alias만으로 실제 가중치의 불변 버전을 검증하지는 못했다.
- [PR #482 공급자 검사](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/482): 기본 변경의 조정자 근거. 이 확인의 정확도 결과와 별개.
- [기존 제한 처리 프로토콜](../2026-10-14-planner-ling-vl-retry/PROTOCOL.md): OpenRouter 오류·제한 문서와 AWS backoff/jitter 근거.
