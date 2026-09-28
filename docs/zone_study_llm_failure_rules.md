# v72 모델 드라이버 실패·분석 규칙 보완

2026-09-28, PR #256의 실행 전 사전 등록 보완이다. Claude PR을 Codex가 수정했다.
실행 전 후보 v72를 유지하며 이미 수집한 시행의 판정이나 원시 자료를 바꾸지 않는다.
등록부 `configs/zone_study_integration/llm_driver.json`의 프로필과 실제 소스 해시는
실행 번들에 포함한다. 본실험 사전 등록을 고정할 때 이 규칙도 함께 고정한다.

## 중단·분류·재시도

- 코호트 token cap은 시행의 결정 호출 예산과 별개다. 코호트 상한으로 막힌 행은
  `blocked / budget_cap`, 시행은 `infra:API`다. 러너는 시작 호출 묶음 직후와
  각 스케줄러 단계 직후에 검사하여 다음 물리 단계 전에 종료한다.
  소진된 코호트에서는 `start_run` 전 검사와 DB 트랜잭션 안의 재검사로 새 시행을 거부한다.
- 응답을 처리한 호출 묶음에 정상 완료 모델 응답이 하나도 없으면 즉시 `infra:API`로
  종료한다. 전송 수 0도 포함한다. 마지막 경계에서도 응답 0을 검사한다.
  `finish_reason` 거절 응답은 정상 응답으로 세지 않는다.
- 네 조건 모두 API 오류가 **1건 이상**이면 시행 전체를 `infra:API`로 분류한다.
  정상 응답과 오류가 섞인 경우의 후속 진단 호출은 보존하지만 정상 시행으로 보고하지 않는다.
  저장되는 `trial_record.json`에도 분류를 넣고 종료 이유는 `api_failure`로 기록한다.
- `HOST_ERROR`는 명시적 `HostError`, MuJoCo `FatalError`, 메모리 고갈,
  OS errno `ENOSPC/EDQUOT/EIO/ENOMEM/EMFILE/ENFILE`, 원장 저장·정산의 SQLite 오류다.
  파일 존재·누락·권한 오류와 나머지 OSError는 `other`이며 자동 재시도하지 않는다.
- 기존 시행 디렉터리, attempt2 디렉터리 또는 attempts 파일이 있으면 원장 등록 전에 거부한다.
  실제 디렉터리 생성과 attempts 파일 저장도 배타 생성한다. 원장이나 코호트를 바꿔도
  같은 결과 경로를 재실행으로 우회하지 않는다.
- 정산 실패는 fatal로 남겨 추가 전송을 막는다. 이미 저장한 응답과 공급자 사용량은 보존하고,
  정산되지 않은 DB 행은 `sent_unknown`으로 남긴다. 추정 토큰 0으로 정산하지 않는다.
- 재시도는 기존 규칙대로 첫 모델 요청 전 `HOST_ERROR`에 한해 제자리에서 한 번이다.
  전송/과금 가능성이 있는 원장 요청이 있으면 어떤 실패든 재실행하지 않는다.

## 조건별 API 노출과 분석

등록 임계 규칙은 `any_api_error_or_budget_cap_or_no_successful_model_reply`다.
`model_usage.api_error_requests`, `api_error_fraction`, `requests`를 조건별 호출 노출
공변량으로 보존한다. 전송 0일 때 비율은 null이고 `tokens_complete`는 false다.
조건별 전체 시도 수, infra 시행 수, 제외 후 시행 수를 각각 보고한다.
정상 시행 비교에는 `failure_class == null`만 사용한다. API 오류 1건 이상 제외를
고정 민감도 집합으로 쓰고, 전체 시도를 실패로 포함한 PAR-2와 함께 보고한다.
예산·HOST_ERROR·정책 실패를 같은 실패율로 묶거나 제외 후 분모만 보고하지 않는다.
이 변경은 드라이버의 분류와 분석 입력 기록이며, 실제 코호트 분석 결과가 아니다.

모든 조건의 실제 POST 시작 간격은 등록값 **최소 2 wall초**다. 같은 LiveDriver의
시행·attempt는 pacer를 공유한다. 별도 프로세스 사이의 전역 속도 제한은 제공하지 않는다.
이 wall 대기는 모델 입력·깨움·SIM 비용에 넣지 않는다. 가짜 통신 테스트에는 실제 대기가 없다.
현재 `latency_ms`는 저장·정산 경계 및 pacing을 포함할 수 있어 순수 공급자 응답 시간으로 해석하지 않는다.

## 프롬프트 호환성

`v66_default`의 2/6과 닫힌 no_comm 채널은 기존 v2 요청 문구·버전을 그대로 쓴다.
`main_pilot_10_30`의 열린 채널은 `ugrp.zone_study_prompts_ko.v3`이며 요청의
`dialogue_window`와 같은 cap 값으로 시스템 문구를 생성한다. registry의
`prompt_versions`가 맞지 않으면 원장을 만들기 전 거부한다.
프로필 수준 번들 버전은 v3이고, no_comm 개별 요청은 기존 v2 바이트를 보존한다.
peer·leader·follower·structured 전부 실제 요청 본문과 시스템 문구를 대조한다.

## 동결 v64 차등 검사의 경계 (PR #256 CI 보완)

`f7289161054d9a92478f31cc1df51c8a3ccc6755`에서 seed 0을 재현했을 때
차이는 결과·시행 기록의 `provenance.prompt_template_sha256` 61곳뿐이었다.
`ValueError: generated pre-wire input failure`는 양쪽에 같은 주입 오류였으며,
종료 이유·호출·입력/요청 해시·dispatch·비용·예산·scheduler trace는 같았다.
동결 세 모듈이 공유하는 현재 프롬프트 모듈의 `PROMPT_VERSION`이 v3로 바뀌면서
참조 모델까지 v3 출처 해시를 기록한 것이 이 반례의 원인이다. 동결 원본 커밋
`97f91cb040bf382973ce84b24b1ca8399e64a6fb`의 해당 상수는 v2다.

참조 모델의 프롬프트 모듈 뷰만 독립시켜 당시 v2 상수를 고정한다. 동결 소스와
해시 manifest는 그대로 보존하며 현재 프롬프트 모듈을 전역 변경하지 않는다.
비교 signature에서 출처 해시를 제외하거나 실패·종료 기대값을 완화하지 않고,
양쪽 출처 해시가 v2인지 명시적으로 검사한다. 전체 요청 바이트와 나머지 v64
비교 필드도 계속 검사한다.

위 정상 응답 0·전송 0의 `infra:API` 규칙은 실제 모델 드라이버에 의도된 규칙이다.
`check_trial_health`와 저장 시 분류는 이미 `MainStudySendLedger` 경로에 제한돼
있어 공통 scheduler의 종료 의미를 바꿀 필요가 없다. 네 조건의 러너 회귀에
입력 구성 실패로 전송·정상 응답이 모두 0인 사례를 추가하여 다음 host step 전
중단, `infra:API` 저장, 재시도 없음과 실제 요청 0을 확인한다. 일반 ValueError를
일괄 API 오류로 재분류하는 변경은 아니다. 런타임·실행 번들 등록은 변경하지 않는다.

물리 에피소드·실제 모델 호출을 실행하지 않았다. 오프라인 회귀는 PHYSICAL 성공이나
공급자 과금 대조, 실제 코호트 분석을 대신하지 않는다.
