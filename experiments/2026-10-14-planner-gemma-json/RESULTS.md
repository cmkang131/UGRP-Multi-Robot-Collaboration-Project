# Gemma fp4 JSON 확인 완료

실행 소스 **007f9b23a598c302b5528125c6f0395a615a54b1**, 새 번들
**v405**(prompt order off) / **v406**(static_first_v1).
400개 본 결정 + 같은 입력의 캐시 순서 40개 + 이미지 5개를 모두 확인했다.
관련 시험 54개 통과 뒤 소스를 커밋하고 호출했다. VM 실행/제출은 하지 않았다.

## 파서와 공급자 설정

r4 DEV `c041ed7e`와 튜닝/확증 `ede50b2c`는 `json.loads`로 파싱하고
거부 시 한 번 재질문했다. 코드 블록 제거와 response_format은 없었다.
이번에도 같은 act/args/menu 검증을 사용하되 새 번들에만 포장 제거 후
첫 JSON 객체 추출(`JSONDecoder.raw_decode`)을 추가했다. 후보 밖 act,
추가/변경 args, 추가 출력 키는 계속 거부한다. 기존 번들은 parser off다.

공개 endpoint API에서 `deepinfra/turbo`의 `response_format` 및
`structured_outputs` 지원을 확인했다(`endpoints.json`).
`response_format={"type":"json_object"}`, `require_parameters=true`,
provider order `["deepinfra/turbo"]`, fallback false로 호출했다.
모든 실제 응답의 model/provider는 Gemma 31B / DeepInfra였다.
태그가 작동하여 DeepInfra+quantizations 대체 설정은 쓰지 않았다.

형식/대체 비율 >5%는 20결정부터, 실제 HTTP 오류 5연속은 즉시 중단하도록
고쳤다. 연속 오류는 HTTP 재시도를 포함하고 재시작 시에도 원장에서 복구한다.
지연 중앙8초 조건과 동시1·최소2초 간격·최대2회 재시도는 유지했다.
이번 확인에서는 중단 조건에 걸리지 않았다.

## 결과

| 항목 | 이번 새 형식 확인 |
|---|---|
| 완료 | 445/445: 본400 + 캐시40 + 이미지5 |
| 대체 규칙 | **1/445**, 본 결정만 1/400 |
| JSON 포장/문법 오류 전→후 | **0/445 → 0/445** |
| 형식·후보 내용 검증 거부 전→후 | **1/445 → 1/445** |
| 이전 2응답 재파싱 전→후 | **1/2 → 0/2**, 추가 모델 호출 없음 |
| 429 | 새0/445, 이전2회 포함 **0/447** |
| HTTP 상태 / 재시도 / 재질문 | 새445회 모두200 / 0 / 0 |
| 응답 중앙 / p90 | **2.391 / 3.677초**, N=445 |
| 전체 결정 중앙 / p90 | 2.393 / 3.679초, N=445 |
| 이번 usage 비용 | **$0.16563214** |
| 이전2회 포함 누적 비용 | **$0.16645624**, 미확인 비용0 |
| 누적 상한 사용 | **447/600 HTTP**, $0.16645624/$0.30 |
| prompt_tokens 중앙 | 3,741.5 (본400) |
| 캐시 off / on, 같은40개 | **23,552/166,326=14.16% / 26,112/166,286=15.70%** |
| 캐시 off, 본400 전체 | 285,888/1,693,159=16.88% |
| 이미지 수락 / prompt 증가 | **5/5 / 5/5**, 모두 +334 tokens |
| r4 Gemma 결정 일치 | **395/400 (98.75%)**, act와 args 정확 비교 |

거부 1건(`2d1fc58993ca86`, peer_en)은 JSON 문법이 아니라 후보 args에
`description`을 추가한 것이 원인이다. 포장 제거로 이 오류를 숨기지 않았고
같은 입력 규칙으로 대체했다. 실패는 모든 해당 분모에 남겼다.
이전 코드 블록 응답은 저장 원문 재파싱으로 복구되는 것을 확인했다.
새445개에는 포장 오류가 없었으므로 새 결과를 파서 단독 효과로 해석하지 않는다.
제공자 JSON 모드와 파서 옵션을 함께 바꿨다.

r4 일치율은 실패를 불일치로 센 395/400이며, 유효 결정만 별도로 보면
395/399다. 대체 규칙의 선택을 모델 일치로 세지 않았다. 기존 r4 호출·정확도·비용은
새 형식 성능에 합산하지 않았다. 참고 정확도는 no_comm 모델55/200·규칙52/200,
peer_en 모델85/200·규칙83/200이다. 튜닝 합성 자료이며 확증/현장 성능이 아니다.

캐시 on은 off 다음에 실행했다. 같은40개 짝 비교라도 서버 캐시 상태와 실행
순서가 영향을 주므로 1.54%p 차이를 보장된 개선으로 주장하지 않는다.
이미지 수락은 실제 요청 성공과 토큰 증가 확인이며 영상 내용 이해나 운반 성공
검증이 아니다. 동일한 r80 자기 RGB의 SHA-256을 확인해 5회 전달했다.

## 예산과 원장 대조

이전2HTTP/$0.0008241이 남은 upstream 원장을 재사용해 예산을 초기화하지
않았다. 시작 시 예산을 뺀 키 잔여는 $12.408991024였다. HTTP 시도/응답/상위
원장 각447개와 새 중계 영수증445개를 request ID로 대조했고 중복은 없었다.
비용은 원장 usage 합계다. 청구서 대조나 가중치 불변 버전 증명은 미확인이다.

이전 두 응답과 로컬 중계 시작 실패는 원래 결과 폴더에 별도 보존했다.
누적 원장의 처음 두 줄을 `outputs/planner-gemma-fp4-prior-two-snapshot-20261014/`
에도 보존했고 http_attempts/http_responses/ledger 세 파일 모두 이전 manifest의
SHA-256과 일치했다. 누적 원장 증가를 이전 결과 변경으로 오인하지 않도록
이 보존본을 연결했다. 로컬 시작 실패는 공급자0회/비용0이다.

## 보존과 범위

`summary.json`은 짧은 결과, `analyze.py`는 원장에서의 재집계,
`freeze.json`은 고정400입력 해시, `raw-manifest.json.zst`는 모든 보존 파일
경로/크기/SHA-256이다. 큰 JSON/JSONL은 무손실 zstd와 해제 해시로 검증했다.
raw는 로컬 보관이며 GitHub에는 요약·재집계 코드·해시 목록을 보존한다.
작업 중계 종료, draft PR 유지, VM 미제출이다.

## 참고 자료

- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): endpoint 지원 확인과 require_parameters. 공식 문서 확인.
- [Gemma endpoint API](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints): deepinfra/turbo fp4의 출력 형식 지원·단가를 저장 시점에 확인.
- [Python JSONDecoder.raw_decode](https://docs.python.org/3/library/json.html#json.JSONDecoder.raw_decode): 첫 JSON 문서를 구조적으로 추출. 이후 후보 검증은 프로젝트의 기존 검증을 유지.
- [실행 프로토콜](PROTOCOL.md): r4 SHA 확인, 번호 예약, 누적 예산 및 중단 조건.
