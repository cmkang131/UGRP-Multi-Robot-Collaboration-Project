# P05 — 네 조건 다회 한국어 결정·원장 계약 (fake-only)

Refs #222, #223. READINESS S10/S12의 계약 검사이며, 실제 모델 효과·다회 파일럿·물리 성공의 증거가 아니다.

## 소스와 작업 경계

- 감사 기준: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.
- 착수 HEAD/main: `d17ca4345affef8cf027e121cf1f3197b36c23e0`, `codex/dialogue-ledger-wire`.
  fetch 뒤 일치했고 작업 트리는 깨끗했다. 두 SHA 사이 P05 대상 파일 차이는 0이었다.
- PR #238/#245/#256은 병합 상태로 확인했다. #256의 옛 prompt cap 불일치는 현재 v3가 이미 해결하므로 재구현하지 않았다.
- 배정 worktree만 수정했다. 공용 registry·실행 번들·workflow 번호·모델 설정은 변경하지 않았다.
- 실제 driver/client/request builder/scheduler/자기 executor API를 사용하며, wire와 robot port만 fake다.
  socket connect/connect_ex/create_connection/DNS는 fixture로 차단하고 MuJoCo import를 막는다.
  기존 손목 JPEG를 읽기만 하며 물리·시뮬레이션·MuJoCo 렌더·비전 추론·실제 LLM 호출은 0회다.
- DB는 pytest가 새로 만든 **더미 SQLite**뿐이다. 설치된 proxy와 기존 budget/raw/원장은 조회·생성·리셋·수정하지 않았다.
  Drive 작업도 없다. 학습 모델 산출물은 없다.

## 새 검사

- 4조건 × seed 700/701/702(seed%3 전체) × 2/6·10/30 두 프로필: 각 로봇 3턴.
  한국어/정형 제안 → 실제 channel/scheduler inbox → 자기 job 종료 → 다음 요청 → 다른 claim 수락 → reply_to 답신 → 송신자의 다음 inbox를 message/call/request/job ID로 연결한다.
  고정 fixture 문자열을 대조하는 검사이며, 한국어 이해도나 모델의 결정 개선을 측정하지 않는다.
- no_comm 메시지 0, leader follower 직접전송 0, structured 자유문 0,
  robot/order/item/role literal 보존, pair status 설정 해시와 조건 공통 실행 설정 동일을 검사한다.
- host GT/숨은 사건/평가 성공과 pair audit 기록만 바꿨을 때 요청 바이트·scheduler trace는 같아야 한다.
  peer 자기 JPEG/사적 belief를 바꿨을 때 해당 peer 요청은 변하고 다른 로봇 요청·공통 job 사건/타이머는 같아야 한다.
- 각 요청의 raw request/response bytes, 자기 JPEG, archive의 텍스트/이미지 digest, 모델 설정 digest,
  transport-owned POST 행, DB 행, provider token known/unknown, 표준 SIM 비용·해제 시각을 대조한다.
  provider의 fixture 토큰 500/100/600과 로컬 billed token/SIM 모델을 별개로 보존한다.
- 두 프로필을 반복 발화로 실제 포화시켜 로봇/episode 2/6 및 10/30을 확인한다.
  거절된 생성 발화도 SIM 비용에 남고 턴 경계에서 episode 예산이 재충전되지 않는다.
- 네 조건에 429/503, POST 후 read timeout, length/content_filter, stale request ID,
  usage 누락, SIM horizon 이후 해제되는 정상 응답을 주입한다. 비용·unknown charge를 남기고 잘못된 응답은 실행·전달하지 않는다.
  stale 응답은 `invalid_json`이며 정상 completion 비용은 보존한다. 이는 정상 시행 성공을 뜻하지 않는다.
  늦은 SIM 응답은 `censored`로 보존하고 종료 후 진행해도 행동을 실행하지 않는다.
- 실제 원장 경계의 ENOSPC는 첫 요청 저장 전·첫 응답 저장 중·POST 1회 이후에 주입한다.
  첫 송신 전만 1회 retry하고 첫 실패 attempt도 보존한다. 두 번째 사전 HOST_ERROR는 종료한다.
  송신 뒤 저장 실패는 HOST_ERROR와 요청 비용/unknown을 남기고 자동 재실행하지 않는다.
- cohort cap은 다음 자기 경계 전에 차단되고 기존 유료 가능 POST 행을 남긴다. 실제 가격/금전 비용은 측정하지 않았다.

## 발견·최소 수정

수정 전 429 주입은 첫 POST 3건 뒤 `CallPolicy.max_retries=1` 때문에 새 call ID 3개로 자동 재전송했다.
실패한 원본은 로컬 `outputs/e2e-p05-dialogue/check-et73pr5q/`에 보존했다.
이는 main-study driver의 `once_in_place_only_if_host_error_before_first_model_request`와 충돌한다.

`MainStudySendLedger.attach`에서 **명시적 `call_policy.max_retries=0`**을 요구한다.
기본값/양수/비정수는 첫 송신 전에 거부하고 값을 묵시적으로 바꾸지 않는다.
공통 scheduler의 기본값과 동결 v64 기록은 유지한다. 실제 driver의 기존 회귀 helper와 새 검사는 0을 명시한다.
실패 규칙 문서에 설정 요건을 추가했다. 새 cohort의 source/bundle 해시는 이 변경을 포함해 다시 계산해야 한다.
기존 성공 판정·번들 ID·설정 값을 바꾸거나 새 실행 승인을 만들지 않았다.

정상 응답의 usage가 누락되면 DB/send 행은 unknown인데 호출 `cost_terms`는 known인
두 번째 불일치도 발견했다. main-study 원장이 요구하는 provider usage 검사를
`_LiveTransport.reply`에서 적용해 같은 `known_total` 기준으로 표시한다.
로컬 billed token과 SIM 비용은 유지한다. 일반 fixture-only 경로의 동결 의미는 바꾸지 않는다.

## 검증·원본

검증 코드 커밋: `8d01d02ca231181d95cc1706c026fe4e65f14e7b`.
아래 기록 커밋은 문서만 추가하며 검증 이후 런타임 소스는 바꾸지 않았다.
관련 11개 파일의 회귀 **656 passed**, 실패·오류·skip 0이다. 새 P05 검사는 84개다.
24개 다회 조합은 로봇당 3턴, fake 요청 216건·전달 메시지 72건이며 pair status 해시가 하나로 같다.
JUnit 시간 135.13초는 검증 실행 기록이며 성능 비교/벤치마크 결과가 아니다.
명령·환경·파일별 소스 해시·JUnit/원본 manifest 해시는 [verification.json](verification.json)에 기록했다.
최종 원본은 `/Users/changmin/projects/ugrp/outputs/e2e-p05-dialogue/regressions-icl2cruy/`다.
수정 전 재송신 반례 `check-et73pr5q/`와 중간 회귀의 651 passed/5 failed 원본
`regressions-ysxi0fte/`도 같은 상위 디렉터리에 보존했다.
`scripts.run_ci_tests.run_locked`로 공용 잠금을 획득한 뒤 pytest를 시작한다.
다른 작업 점유 중에는 테스트를 생성하지 않았다. 기존 raw는 덮어쓰거나 삭제하지 않는다.
pytest의 basetemp는 매 실행 새 디렉터리이며 원본 요청/응답·더미 DB·ID 추적 JSON을 로컬에 보존한다.
GitHub에는 코드·작은 검증/인계 기록만 올린다. 로컬 raw는 원격 백업이 아니다.
새 학습/실제 실험/평가 결과는 없으므로 TensorBoard에 로봇 성공·모델 효과 run을 만들지 않는다.

## 코디네이터 인계 — 실제 호출 전 남은 항목

1. 독립 검토 뒤 새 cohort의 cap, unknown usage charge, model/실효 model,
   temperature/effort/max_tokens/timeout, speech profile, `call_policy.max_retries=0`,
   새 DB 절대 경로와 새 output 경로를 사용자 승인·사전 등록에 포함한다. 과거 잔액/실효 모델을 현재값으로 사용하지 않는다.
2. 변경 소스를 커밋해 source/bundle/config/map/input hashes를 다시 고정한다.
   이번 PR은 draft이며 병합·봉인·실행 승인이 없다.
3. 실제 호출의 `call_id → transport send ledger → raw wire → proxy receipt → upstream attempts/usage`
   정산 계획과 정상 finish_reason 증거를 확정한다. fake POST 행은 상류 호출 수·과금 증명이 아니다.
4. 최종 환경에서 네 조건·각 로봇 최소 2턴의 실제 한국어 연결 파일럿을 별도 승인/실행한다.
   오류·미도달·late/비정상 출력·infra 시행을 분모에 보존한다. 이번 검사로 그 파일럿이나 E2E를 완료 처리하지 않는다.

## 참고 자료

- PR [#238](https://github.com/kcm0127-dotcom/ugrp/pull/238), [#245](https://github.com/kcm0127-dotcom/ugrp/pull/245), [#256](https://github.com/kcm0127-dotcom/ugrp/pull/256), 조정 PR [#298](https://github.com/kcm0127-dotcom/ugrp/pull/298).
- [실패 규칙](../../docs/zone_study_llm_failure_rules.md), [driver 회귀](../../tests/test_zone_study_llm_driver.py), 기존 multiturn/integration/inputs 회귀와 `scripts/run_ci_tests.py` 잠금 wrapper를 재사용했다.
- 새 논문·OSS 의존성은 추가하지 않았다.
