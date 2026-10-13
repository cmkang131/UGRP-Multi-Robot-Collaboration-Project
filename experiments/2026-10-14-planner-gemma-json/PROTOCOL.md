# Gemma fp4 JSON 확인 계속

사용자 지시 2026-10-14. 새 번들 v405(off)/v406(static_first_v1): main과
열린 PR 최댓값 v404 다음 번호. 이전 번들/기록은 보존한다.
모델 google/gemma-4-31b-it, order [deepinfra/turbo], allow_fallbacks false,
response_format {type: json_object}, require_parameters true, 온도0·768토큰.
자기 RGB 한 장 및 해시 경로는 유지한다.

## 먼저 확인한 r4 경로
r4 DEV c041ed7e와 튜닝/확증 ede50b2c의 harness/task_planner.py parse는
json.loads(raw)였다. act/args/menu 검증은 같은 함수에 있고 포장 제거는 없었다.
harness/task_planner_gemma.py는 response_format을 보내지 않았다.
Planner.decide 기본 repair_budget=1로 형식/실행 거부 후 한 번 재질문했다.
따라서 3,556개 HTTP 응답이 있었다는 사실이 3,556개 첫 응답의 형식 성공을
뜻하지 않는다. 새 경로도 같은 내용 검증을 사용하고 앞단에만 코드 블록 제거와
첫 JSON 객체의 JSONDecoder.raw_decode를 추가한다. 깨진 첫 객체를 건너뛰지
않고 배열/미등록 act/수정 args/추가 키를 거부한다. 기존 경로는 parser off.

## 출력 형식 근거
공개 endpoints API를 다시 확인했다. deepinfra/turbo fp4는
response_format 및 structured_outputs 둘 다 supported_parameters에 있다.
이번에는 json_object 모드를 켜고 내용 제약은 기존 후보 검증기가 검사한다.
포장 파서 first_object_v1과 제공자 JSON 모드는 새 번들에만 활성화한다.
원문 응답을 보존하고 strict_json_error(포장 처리 전), rejection(처리 후)을
별도 집계한다. JSON 모드로 형식 오류 자체가 줄어들 수 있어 파서만의 효과로
보고하지 않는다.

## 실행·누적 상한
고정 r4 DEV 400개 결정을 새 출력 옵션으로 확인하고 같은 입력40개 캐시순서,
r80 자기 RGB5개를 확인한다. 이전2응답은 새 옵션 성능 분모에 섞지 않고
별도 보존한다. 비용과 HTTP600회 상한에는 이전2응답 $0.0008241도 포함한다.
같은 upstream 디렉터리 outputs/planner-gemma-fp4-state-20261014/openrouter의
영속 원장을 재사용한다. 따라서 재시도 없는 완료는 누적447HTTP가 된다.
전체 $0.30 유지, 남은 최대598HTTP/$0.2991759. 시작/매50HTTP에서 Keychain
키의 남은 한도를 확인하고 예산을 뺀 값이 $1.5 미만이면 중단한다.
현재 단가와 r4 토큰에 따른 새445개 예상 약$0.1784, 누적 약$0.1793.

중계 동시1, 최소2초 간격, 429/5xx Retry-After 우선 또는 지수백오프+지터,
최대2재시도 유지. 실제 HTTP 오류가5연속이면 더 보내지 않고 영속 원장에
남겨 재시작에도 유지한다. 로컬 HTTP 실패5결정 연속도 즉시 중단한다.
형식 오류·대체 >5%는 요청한20결정부터 판정한다. 지연 중앙8초 조건은 유지.
재질문은0회(현재 확인 정책 유지), 오류/미호출은 전체 분모에 별도 유지.
코호트 동안 코드·입력을 고정하고 VM 실행/제출은 하지 않는다.

## 참고 자료
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): endpoint 단위 지원 확인과 require_parameters 적용; 지원 광고가 내용 검증을 대체하지 않는다.
- [공개 endpoint API](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints): endpoints.json에 확인 시점 원문 보존.
- [Python JSONDecoder.raw_decode](https://docs.python.org/3/library/json.html#json.JSONDecoder.raw_decode): 첫 문서와 끝 위치를 파싱하는 표준 기능. 문자열 내부 중괄호를 정규식으로 잘라내지 않는다.
