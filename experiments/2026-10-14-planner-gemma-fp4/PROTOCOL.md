# Gemma DeepInfra fp4 기본 계획기 확인

2026-10-14 사용자 선택. 새 번들 v403(off), v404(static_first_v1).
main과 열린 PR 전체 최댓값 v402 다음 번호(스캔 JSON). 기존 번들 보존.
model google/gemma-4-31b-it, provider order [deepinfra/turbo], fallback false,
온도 0, max_tokens 768, 기존 Gemma reasoning default. 자기 RGB 1장과 sha256 유지.
태그는 공식 엔드포인트 목록에서 fp4로 확인했고 반환 공급자는 DeepInfra로 검사한다.
태그가 작동하지 않으면 묵시적 다른 경로 없이 오류로 기록한다.

새 독립 원장: HTTP 최대 600회(재시도 포함), $0.30.
400 r4 DEV 결정 + 같은 사례 40개 static_first + r80 자기 RGB 5회.
합성 입력과 후보는 기존 동결 자료 그대로이며 새 확증/전체 세트는 실행하지 않는다.
대체 >5%, 형식 오류 >5%, 지연 중앙 >8초면 즉시 추가 요청을 중단한다.
미호출과 오류는 별도 표시하고 원래 분모를 유지한다. 재질문 없음.
429/5xx 최대 2회 재시도, Retry-After 우선, 지수 백오프/full jitter,
중계 동시1·2초 간격. 정책 planner_rate_limit_v1은 새 Gemma fp4 경로에만 적용.
기존 Ling 정책과 이전 Gemma 기본 동작은 그대로다.
Keychain 키는 프로세스에서만 읽는다. 시작 전 및 매50HTTP 시도 잔액 확인,
예상 잔액 $1.5 미만이면 중단. 요청 직전 상한·보수적 비용 예약 검사.
공급자 usage 합계와 비용 미확인을 분리한다. 이미지 비용 예약은 보수적이다.

현재 endpoint 가격: prompt $0.09/M, completion $0.34/M, cache read $0.05/M.
r4 토큰 실측을 현재 가격에 대입한 600회 예상 $0.240588
(445회 단순 환산 약 $0.178436; 이미지/재시도/토큰 차이는 별도). 실제 상한은 비용 원장으로 강제한다.
과거 r4 Gemma 결정과 act/args 일치율을 참고로만 보고하며 결과를 합산하지 않는다.
캐시는 sum(cached_tokens)/sum(prompt_tokens), 이미지 수락은 오류 없음과
무이미지 짝 대비 prompt_tokens 증가를 각각 보고한다.
VM 실행/제출 없음. 중단된 Ling 기록과 조정자 측정은 이 코호트에 포함하지 않는다.

## 참고 자료
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): 특정 endpoint tag와 fallback 차단. 공식 문서 확인.
- [Gemma endpoints](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints): deepinfra/turbo fp4 및 가격 확인, endpoints.json 저장. 반환 alias만으로 가중치 버전의 불변성을 입증하지 못한다.
- [PR #482](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/482): 조정자 40요청 부하 측정이며 이번 정확도 표본과 별개다.
- [이전 제한 처리 근거](../2026-10-14-planner-ling-vl-retry/PROTOCOL.md): OpenRouter 오류·한도와 AWS backoff/jitter.
