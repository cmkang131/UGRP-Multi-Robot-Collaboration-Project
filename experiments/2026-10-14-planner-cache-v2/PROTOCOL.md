# static_first_v2 DEV 확인

사용자 요청 2026-10-14. 기본 옵션 off와 v405/v406 바이트를 보존한다.
v2는 공통 schema/public_rules, 실행 task/static_map/order_sheet, 조건/로봇,
동적 관측/결과/메시지/사건/근거/후보 순이다. 중첩 객체 키는 정렬하고 JSON
숫자는 Python의 결정적 무손실 표기를 사용한다. 값, 배열 순서, 후보 인자는
바꾸지 않는다. 자기 영상은 기존 검증 경로로 해시를 확인하고 텍스트 뒤에 둔다.

현재 E2E context의 order_sheet는 매번 같은 리터럴 주문을 복사한다. 완료 상태는
own/own_act_results에 있다. 따라서 별도 상태 분할이 필요 없다. evidence_gate는
archived_reports가 변하므로 공통 고정 칸으로 옮기지 않는다. r80 이전 스키마에는
order_sheet/evidence_gate 자체가 없으며 task만 고정이다. 이를 실제 새 계획기의
연속 실행 관측으로 대체해 보고하지 않는다.

## 범위와 채택
- v405와 같은 r4 DEV 고정 400결정. 같은 정보, 온도0, 768출력토큰, JSON mode.
- 새 HTTP 원장 하나에 모든 재시도/재생을 합산: 600회/$0.25. 이전 실행 비용 별도.
- 시작 전 GET /api/v1/key와 /api/v1/credits 확인. 남은 예산을 뺀 잔액/키 한도
  $1.5 미만이면 중단. 실행 중 기존 50HTTP 간격 키 검사 유지.
- 직렬 요청, 2초 최소 간격, 최대2재시도, 연속5HTTP실패 즉시 중단.
  20결정 이후 형식/대체 5% 초과, 지연 중앙8초 초과 중단. 재질문0회.
- 채택은 400 중 정확한 act/args 일치388 이상, 형식오류/대체 각각 v405+2 이내.
  실패도 분모400에 유지. 미달이면 기본 번들을 등록하지 않는다.
- main+모든 열린 PR 검사 최댓값 v414(PR483). 채택 후보 번호 v415 예약;
  실제 등록 직전 다시 확인한다. 아직 등록/실행 번들이 아님.
- r80 원본 입력 envelope와 실제 공급자 speech 요청을 구별한다. 확인한 r80
  v379/61006 code_v1은 행동을 코드로 고정하고 공급자에는 텍스트 발화만 보낸다.
  사용자에게 196개 이미지 판단 요청의 정확한 경로를 요청했다. 이를 찾지 못하면
  r80 재생을 새 계획기 실제 연속 캐시 성능으로 표현하지 않는다.

## 참고 자료 (공식, 2026-10-14 확인)
- https://openrouter.ai/docs/guides/best-practices/prompt-caching : sticky routing은
  provider.order 지정 시 적용되지 않는다. session_id가 고정 제공자의 내부 서버를
  고정한다는 보장은 없으므로 추가하지 않는다.
- https://docs.deepinfra.com/chat/prompt-caching : 자동 prefix KV 재사용, 동일 prefix,
  계정/모델 범위, 비활성 뒤 만료. prompt_cache_key는 직접 API에 문서화되어 있으나
  OpenRouter deepinfra/turbo supported_parameters에는 없다(endpoints.json).
  OpenRouter 전달/효과는 미확인이라 효과가 검증된 장치처럼 켜지 않는다.
- https://docs.deepinfra.com/chat/prompt-cache-retention : 명시 retention은 Nemotron과
  Kimi만 명시. Gemma에는 cache_control/retention을 추가하지 않는다.
- Gemma 최소 길이/TTL/블록 크기의 공식 수치는 미확인. 원장 32배수는 관측일 뿐
  공급자 계약으로 쓰지 않는다. metadata supports_implicit_caching=false와 실제
  cached_tokens>0는 서로 다르며 실측 합계를 보고한다.
- https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints : fp4
  deepinfra/turbo 입력 $0.09/M, 캐시읽기 $0.05/M, 출력 $0.34/M.

저장: DEV 가벼운 텍스트 원장/요약/해시 영구 보존. 예상 원장 <30MiB,
관련 r80 대표 실행 이미지 27개 373,374bytes만 ARM 보관 원본에서 읽어 회수했다.
VM이나 새 물리는 실행하지 않는다. 실험 후 큰 JSON은 검증 압축한다.

## r80 원장 확인 뒤 고정한 재생 범위
protocol-relay-r17/code_v1-dialogue/speech.jsonl에서 r80 본 실행의 실제 공급자
요청 735개를 확인했다(speed-gate 80개 제외). 모두 이미지 없는 발화 생성이며,
입력 envelope의 자기 RGB와 다르다. 원본 경로 회신은 아직 없다. 확인 가능한
실제 공급자 기록 한 실행(v379/61006)의 r1/r2 27개를 동일 시간순으로 off/v2 각
한 번 재생한다. 이 54개와 400개 합계454개, 같은 HTTP600/$0.25 원장을 쓴다.
이는 과거 발화 요청의 캐시 비교이며 **새 계획기 영상 판단의 실제 실행 검증이
아니다**. 텍스트 내용을 보존하고 동일한 현행 모델/온도0/768토큰/JSON 설정을
두 팔에 적용한다. 원래 기록의 온도 .2/1600출력 상한과 다름을 기록한다.
원래 SIM 순서와 로봇 교차는 유지하되 wall 시간 간격은 직렬2초 pacing이다.
따라서 원래 실행 간격의 TTL 효과와 미래 실제 계획기 캐시는 미확인이다.

## 토크나이저 검산
Google 공개 google/gemma-4-31B-it tokenizer/공식 chat_template을 사용했다.
HF commit 842da3794eaa0b77d5f08bae87a17459d91ff475, SHA는 provenance에 있다.
v405 원장400개 모두 공식 토크나이저 계산이 실제 prompt_tokens보다 1 작았다.
이는 제공자 템플릿 차이로 남기며, 숫자를 강제 보정하지 않는다. 필드별 토큰
기여, 로봇별 직전 요청, 교차 호출의 직전 요청, 같은 실행의 모든 과거 요청 중
최장 prefix를 각각 센다. 마지막 값은 퇴거/서버분산 없는 이상적 상한이며
실측 hit가 아니다. tokenizer만 작업 outputs에 설치했고 공유 환경은 바꾸지 않았다.
