# Gemma 다중 키 분산 — multi_key_v1

10/11 사용자 승인 범위: 기본 OFF, Mac Keychain의 account `aistudio`와
`ugrp-gemma-aistudio`, `-2`, `-3`, ... 서비스만 시작 시 조회한다. 번호가
비어 있어도 뒤의 등록 키를 찾고, 같은 값의 중복 키는 하나로 센다. 키 값은
프로세스 메모리와 Google API 요청 헤더에서만 사용한다. 기록의 키 식별자는
`key_index`이며 모든 등록 키가 upstream 오류에 되비쳐도 마스킹한다.

키가 1개면 기존 단일 키 처리·보수적 한도·journal 정책을 유지한다. 2개
이상이면 프로젝트별 RPM 30 / TPM 16000 / RPD 14400 독립 버킷으로 예약한다.
분당 토큰·요청, 일일 요청의 남은 비율 중 최솟값이 큰 키를 선택하며, 동률은
비율 합·작은 index 순이다. 기존처럼 input + max output을 보수적으로 예약한다.
키 1은 기존 공용 버킷을 재사용하여 기존 단일 키 프록시의 예약을 확인한다.
모든 버킷을 index 순으로 잠그고 선택·예약한 뒤 API 호출 전에 잠금을 푼다.

명시적 429/403/5xx는 해당 키만 쿨다운하고 같은 요청 본문을 다른 키에 보낸다.
Retry-After/RetryInfo·일일 Pacific 자정 reset을 존중하며, 기본 쿨다운은
60초부터 최대 3600초로 증가한다. 모든 키가 보류되면 기존 클라이언트 대기를
위한 429 + Retry-After를 반환한다. 하나의 journal이 전환 전체를 감싸므로
중복 논리 요청은 최종 응답을 재사용한다. timeout/잘못된 JSON·모델 pin
불일치는 다른 키로 재발행하지 않는다. 시작 시 metadata 조회도 전부 보류되면
실제 조회를 보내지 않고 PoolUnavailable로 실패한다.

다음 새 프록시에서만 `scripts.s4_proxy_relay --multi-key-v1` 또는
`scripts.gemma_fallback_proxy --multi-key-v1`로 켠다. 이번 작업에서 프록시를
시작·재시작·종료하지 않았고, 실행 중이던 e2e 경로
`/Users/changmin/projects/ugrp-wt/e2e-integration`의 소스를 편집하지 않았다.
기존 cohort에 적용하거나 프록시 receipt를 갱신한 작업도 아니다.

관련 시험 3파일 56/56 통과(3.58초): 기존 fallback, 단일 키 성공/403/429/503
바이트 동등성 및 한도 보류, 빈 번호·계정 필터·중복 제거, 가짜 HTTP 서버의
분산·비밀 마스킹, 독립 RPM/TPM/RPD, 429/403/5xx 쿨다운·전환, metadata 전환,
쿨다운 후 같은 요청 재개·재시작, 동시 예약·중복 요청, 모호한 실패의 재시도 금지.
원본 JUnit 위치·SHA와 실제 API 확인 상태는 [summary.json](summary.json)에 둔다.
DEV 오프라인/API 진단이며 물리·렌더·배송 성공이나 본 연구 결과가 아니다.

실제 API는 등록 키가 2개 이상인 경우에만 각 키로 짧은 generateContent 1회를
확인한다. 시작 시 등록된 서로 다른 키 5개를 확인했다. API 결과는 코드 커밋
뒤 별도 회수하고 summary에 기록한다. 각 키가 서로 다른 프로젝트라는 것은
사용자 설정 전제이며, 서로 다른 키 값이나 HTTP 200만으로 프로젝트 독립성을
확인한 것으로 표현하지 않는다. 토큰 가격·비용은 이번 진단에서 측정하지 않는다.

## 참고 자료

- [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits):
  한도는 API key가 아니라 프로젝트 단위이며 RPD는 Pacific 자정 reset이다.
  30/16000/14400 수치는 문서의 보장치가 아니라 이번 사용자 승인 설정이다.
- [Google troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting):
  일시적 429/5xx의 유한 재시도·backoff. 403은 일반적으로 재시도 대상이
  아니며, 이번 구현의 다른 프로젝트 키 전환은 사용자 요청으로 추가한 예외다.
- [urllib3 Retry](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html):
  Retry-After 존중·횟수 제한·backoff·모호한 read failure의 구분을 참고했다.
  SDK의 자동 재시도를 중첩하지 않고 기존 직접 REST 및 durable journal을 유지한다.
  최신 공식 문서를 직접 열람했으며 논문이나 미확인 인용을 검증 근거로 추가하지 않았다.
