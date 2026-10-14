# DeepSeek V4.1 Flash 확인 — 기본 Gemma 유지

사용자 승인 2026-10-14. 새 선택 모델 `deepseek/deepseek-v4.1-flash`,
provider.order `[deepinfra/fp8]`, allow_fallbacks=false,
reasoning.enabled=false, response_format=json_object, require_parameters=true.
온도0·max_tokens768·후보 act/args 엄격 검증·first_object_v1 파서와 자기 RGB
1장 해시 확인/이미지 마지막 배치를 유지한다. 모델은 서버 응답마다 실제
model/provider/usage/캐시/비용을 보존하고 endpoint 원문 dated name도 기록한다.
별칭과 공개 endpoint 이름이 불변 가중치 버전을 증명하지는 않는다.

main 및 열린 PR 전체 검사 최대 v431 다음 **v432(off), v433(static_first_v2)**.
새 DeepSeek 옵션 번들만 등록하며 기본 v405 및 기존 구성 파일은 그대로다.
VM 제출/실행은 하지 않는다. 결과 보고 뒤 사용자가 모델 채택을 결정한다.

## 고정 자료와 예산
- v405와 같은 r4 DEV 초기 입력400개(JSON 구조 전체 동일 확인), 입력 해시
  4d7b0c1f4692b1c78e4f53d464f37c1ff8910d2ba3c54e58b81399ee48baf74e.
- 먼저 off400, 동일 입력 중 처음40개 static_first_v2, 처음5개 자기 RGB 추가.
  원본 이미지 SHA256 15673f61873991c84cfe449747efa858b4986e36d8f48c5874f483574ec0cfc3.
  이미지는 r80에 저장된 실제 자기 RGB 한 장이고 5개 합성 사례의 이미지
  수락·토큰 증가 확인용이다. 시각 판단 정확도나 새 장면 성공 평가가 아니다.
- 재질문0회. 총445결정, 모든 HTTP 재시도를 포함해 **600회/$0.30** 영속 원장.
  요청 직전 카운터와 미확인 비용을 포함한 보수적 비용 예약을 검사한다.
  이전 모델 실행의 원장과 분리한다. 키는 Keychain→프로세스만 사용한다.
- 시작 전 GET /api/v1/key와 /api/v1/credits로 잔여 한도/계정 잔액을 확인한다.
  최대 예산을 뺀 값이 $1.5 미만이면 중단한다. 기존 실행 중50HTTP마다 키 확인.
- 캐시 없이 r4 실제 토큰으로 추정한445개 비용 약$0.2747. 잔액/모델 실제 가격은
  preflight.json/endpoints.json에 저장한다. 실제 비용은 원장에서 다시 합산한다.
- 20결정 뒤 형식/대체>5%, HTTP5연속 오류 즉시 중단. 기존 지연 중앙8초 조건도
  유지. DeepSeek에서는 출력 상한에 끊긴 JSON도 형식 오류로 센다. 실패·미호출은
  분모에서 제외하지 않고 별도 수를 표시한다. 순차1개/최소2초, 최대2재시도,
  Retry-After 우선 및 지수 백오프·지터 유지.

## 비교·자료 보존
최종 비교 기준은 **v405 Gemma 140/400**, 같은 입력 강한 규칙135/400이다.
공통 평가기의 내부 r4 historical summary를 v405 점수와 혼동하지 않는다.
조건별 correct, v405만 맞음/DeepSeek만 맞음, 정확한 act/args 선택 일치를 센다.
대체 응답도400 분모에 남고 정확도(correct)는 모델 유효 응답만 인정한다.
실제 대체 후 정답(effective_correct)은 따로 기록한다. 캐시 비율은 cached 합 /
prompt 합이며 off400, off 중 동일40, v2 40을 함께 제시한다. 다른 순서·캐시
워밍을 통제하지 않았으므로 순서만의 인과 효과로 확정하지 않는다.

DEV, 예상 텍스트 원장 <30MiB, 기존 이미지 재사용. 요청·응답·원장·해시·요약을
보존하고 >64KiB JSON은 종료 뒤 검증 압축한다. Mac 물리/렌더는 없다.

## 참고 자료
- [공개 endpoint API](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints):
  DeepInfra fp8, dated endpoint deepseek-v4.1-flash-20260910,
  response_format/structured_outputs/reasoning 지원. 원문 endpoints.json.
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs):
  지원 endpoint에서 JSON 출력 형식과 require_parameters를 사용하고 후보 검증은
  코드에서 유지한다. Gemma와 동일한 json_object를 선택해 출력 제약을 맞춘다.
- [Reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens):
  reasoning.enabled=false를 보내며 실제 reasoning token 사용도 원장에 보존한다.
