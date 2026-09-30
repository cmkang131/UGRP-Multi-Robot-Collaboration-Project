# P06 — 평가 전용 심판과 원본·TensorBoard 연결

Refs #223, #224, #226. READINESS S11/S14의 **synthetic 계약 검사**다.
물리·시뮬레이션·렌더·모델 호출·실제 실험 코호트는 수행하지 않았다.
공용 대시보드 게시, 기존 raw/snapshot 변경, Drive 작업, 병합은 없다.

독립 검토 A303-1/2/3 후속은 [REVIEW_FIXES.md](REVIEW_FIXES.md)를 따른다.
최초 203개 검사에 빠졌던 식별값 교환·terminal 누락·v6e 고정 소스 검사를 추가했다.
정상 GitHub CI는 실행하며 생략·취소하지 않는다.

## 두 차례 BLOCK 뒤 재설계

앞선 수정은 F303-1의 내부 시행 혼합 7건을 막지 못했다. 같은 문제를 두 번 만난 뒤에는
조건문을 더 붙이는 방식을 멈추고, 아래 참고 자료의 **관계형 무결성·고정 분석 집합·출처 추적**을
공통 계약으로 채택했다. 이전 302개 통과를 이번 재설계의 검증으로 재사용하지 않는다.
이번 명령·판정·실패 이력·소스 해시는 [REDESIGN_VERIFICATION.md](REDESIGN_VERIFICATION.md)에 남긴다.

`scripts/zone_study_evidence_join.py`의 키는
`(run_id, trial_id, condition, seed, order_id, attempt)`다. 문자열/정수 타입을 검사하며
bool을 seed/attempt로 받지 않는다. 시행 전체 레코드의 `order_id`는 예약값 `__trial__`,
주문별 관계의 `order_id`는 실제 주문 ID다. result·trial·referee·manifest에는 시행 키와
주문 키 목록을 기록하고, TensorBoard에도 같은 키를 text와 metadata로 남긴다.
내부 call/request/action/message/dispatch/send 행은 `study/record_index.json`에
복합키 + 테이블 내 고유 ID + 해당 JSON 레코드 SHA-256으로 보존한다.
기존 닫힌 runtime 로그 스키마를 고치거나 바깥쪽 이름을 안쪽 로그에 덮어쓰지 않는다.

- **정확한 연결:** trial/referee/order/manifest/TensorBoard 관계는 계획의 각 주문 키와
  정확히 1:1이어야 한다. 중복을 사전으로 덮어쓰기 전에 검사한다. 고아·중복·누락·충돌은
  그 시행의 모든 주문을 `INVALID`로 만들며 성공 0으로 분모에 남긴다. 주인을 식별할 수
  없는 고아는 전체 코호트를 보수적으로 INVALID 처리한다.
- **내부 ID 연결:** 기존 calls/actions/messages의 `run_id`는 `identity.trial_id`와 같다.
  실제 attempt 폴더인 `identity.run_id`와 혼동하지 않는다. 조건·seed, 요청 ID/호출 ID,
  actor·시각·action/message 참조·dispatch·전송 원장·모델 호출 순번도 대조한다.
  scheduler가 수신자마다 반복하는 메시지 참조는 `(message_id, recipient)` 교차 테이블로
  정규화하고 발행 호출 하나·수신자별 행 하나를 요구한다. 단순 set 변환으로 중복을 숨기지 않는다.
  서로 다른 시행의 raw를 가져와 파일 해시만 다시 계산해도 통과시키지 않는다.
- **고정 분모:** 실행 전에 `freeze_plan(admitted)`로 전체 계획을 만들고 canonical JSON
  SHA-256을 사전 등록에 고정한다. writer는 계획과 pin을 필수 인자로 받는다. 종료 후
  찾아낸 파일 목록으로 계획을 만들지 않는다. 논리 시행당 미리 지정한 attempt 하나만
  허용하므로 재시도 중 성공만 고르거나 분모를 늘릴 수 없다. 추가 retry 정책은 별도
  사전 등록 없이는 지원하지 않는다.
- **누락 보존:** 코호트 게시기는 계획에서 시작해 모든 admission에 판정을 남긴다.
  파일이 없거나 깨졌어도 `successes / admitted_trials`를 계산한다. 개별 변환기의 잘못된
  원본은 기존처럼 성공 event를 만들지 않고, 코호트 게시기가 그 거절을 INVALID/0으로
  남긴다. 전체 자료가 없어도 분모 N, 성공 0, INVALID N이다.
- **출처 재검증:** 평가 수치에는 사용한 trial/referee 파일의 정확한 바이트 SHA-256을,
  TensorBoard scalar와 코호트 수치에는 전체 입력 파일 해시를 붙인다. 내부 행은 정렬된
  키·공백 없는 JSON(`harness.zone_study_contract.digest`)으로 정규화해 해시한다. 게시 직전에
  원본을 다시 읽고 키·수치·해시를 재계산해 저장할 요약과 비교한다. 불일치하면 임시 event를
  공개하지 않는다. 해시는 출처 변경 검출이며 작성자 인증이나 물리 성공의 증명은 아니다.

코호트의 단일 공식 게시 경로는 다음과 같다. `--plan-sha256`은 raw의 주장값을 복사하지
말고 실행 전 사전 등록에서 가져온다. `--source`가 없는 계획도 누락 시행을 집계한다.

```sh
PYTHONPATH=. python scripts/zone_study_evidence_cohort.py \
  --plan /absolute/frozen-plan.json --plan-sha256 <사전등록한-canonical-sha256> \
  --source /absolute/run-1 --source /absolute/run-2 --output /absolute/new-snapshot
```

이 경로는 결과 발견 목록을 분모로 쓰는 기존 `zone_study_eval.summarise`를 호출하지 않는다.
기존 평가 라이브러리와 byte-pinned runner는 보존한다. 개별 run의 `cohort/trials=1`은
해당 attempt의 표시일 뿐 연구 코호트의 분모가 아니다. 코호트 성공률은 위 게시기로만
계산한다. 합성 자료는 명시 opt-in과 OS 임시 출력 경로만 허용한다.

두 리뷰의 재현은 `test_zone_study_evidence_review_a303.py` 4건과
`test_zone_study_evidence_review_f303.py` 7건에 편입했다. Hypothesis가 현재 Python 3.12
환경에 없어 seed `30320260930 + 연산번호`로 혼합/중복/삭제/재정렬 각 3,000건,
총 **12,000개 생성 사례**를 검사한다. 성공과 실패가 섞인 1–5개 시행, 1–3개 주문,
다섯 관계와 여섯 키 열을 바꾼다. 불변식은 성공수·성공률 비증가, 키 충돌 시 INVALID,
분모=admission 수이며 재정렬은 판정과 요약의 동일성도 요구한다. 이미 손상된 자료를
사후 수정하는 작업이나 전체 원본과 외부 pin까지 함께 위조하는 공격을 인증하는 검사는 아니다.

이는 synthetic 코드 계약의 재설계다. 물리·모델 호출·새 실제 코호트와 공용 TensorBoard
화면 인수는 여전히 수행하지 않았다. `.github/workflows`는 이번 작업에서 수정하지 않는다.

- 기준 감사 SHA: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.
- 시작 소스: `d17ca4345affef8cf027e121cf1f3197b36c23e0`.
  감사 SHA 이후 차이는 process-review 기록뿐이며 P06 대상 코드는 같다.
- 작업: `/Users/changmin/projects/ugrp-wt/e2e-p06-evidence`, `codex/evidence-referee`.
- PR #257/#241/#291과 READINESS/열린 PR을 읽고 fetch했다. #298에 범위를 알렸다.
  P05/P02/P09의 제어·드라이버·host_spec 구현은 바꾸지 않았다.

## 발견과 변경

1. `efficiency_metrics`가 `orders_complete` 문자열만 보고 성공을 셌다.
   이제 주문 ID/개체 ID·종류·목적지의 최종 배송 상태, 평가 상태, failure class를
   함께 확인한다. 중복 order/item ID를 거절한다. 같은 색 다른 개체는 named 주문을
   채우지 않고 반복 배송은 같은 item ID 1개로 센다.
2. 정착 시작을 배송 시각으로 기록하는 기존 정의에서 확인 시각이 사라지면 cap 뒤
   확인을 cap 안 성공으로 소급할 수 있다. 심판 v3는 `confirmed_sim_s`와
   `observed_end_sim_s`를 함께 보존하고, 확인이 종료/cap 뒤면 배송으로 세지 않는다.
   전체 발자국·높이·선속도·손에서 놓임·2초 연속 정착의 기존 기준은 유지한다.
   truth 누락 표본은 연속 정착/기존 배송을 무효화하고 비유한 시각·개체 종류 변조를 거절한다.
3. 러너의 `result=None`/`trial=None` 종료에는 trial record가 빠질 수 있었다.
   별도 후보 `scripts/zone_study_evidence_writer.py`는 HOST_ERROR·API·정책실패·중단/
   미평가의 터미널 기록을 남기고 불완전성을 표시한다. 기존 runner는 v6e가 고정한
   바이트로 복원했으며 이 후보를 자동으로 호출하지 않는다. 새 실행기에서 예외·중단을
   잡고 실제 SIM cap·scenario ID·attempt를 전달하는 연결은 후속 등록 때 필요하다.
   실패 기록을 만들기 위해 scheduler를 추가 실행하지 않는다. 시작 전 실패도 같은
   scenario/seed 비교에 남기며 불완전 모델 기록은 알려진 하한과 미상 총계를 구분한다. 외부 강제 종료·ENOSPC로 기록 쓰기 자체가
   불가능한 경우까지 디스크 기록을 보장하는 수정은 아니다.
4. 통합 run의 전용 TensorBoard adapter를 추가했다. raw manifest의 전체 파일/해시,
   bundle digest, trial/result/evaluation/manifest 연결을 검증하고 숫자를 다시 계산한다.
   파일 누락·변조·변환 중 변경은 이벤트 미게시로 끝난다. 성공·실패·중단/미평가는
   시도 단위 분모에 남긴다. 알 수 없는 값은 scalar로 만들지 않는다.
5. 요청 원문과 모든 요청 원본 이미지 검증은 미리보기 표본 수와 독립적이다.
   TOP 설정 JSON과 영상 파일 등록을 분리하고 `top_rgb`와 `gt_visualization`을 구분한다.
   synthetic 결과는 명시 opt-in + 임시 output만 허용한다.

공용 registry 변경은 `scripts/run_ci_tests.py`의 새 테스트 파일 **한 줄**뿐이다.
실행 번들/workflow 번호는 예약하지 않았다. 실행 전에 코디네이터가 새 심판 profile과
합성된 소스/번들을 고정해야 한다. 현재 PR은 새로운 실행 승인이나 과거 성공 판정의 승계가 아니다.

## 검증 범위

[검증 기록](VERIFICATION.md)에 최종 명령·선별 node ID·결과·JUnit 해시를 남긴다.
모든 fake JSON/JPEG/MP4/event는 OS 임시 폴더에서만 생성한다. 이 폴더에는 테스트
코드/검증 문서만 있으며 fake 자료를 연구 결과로 커밋하거나 공용 snapshot에 게시하지 않는다.

`referee_truth`는 가짜 MuJoCo 모듈·가짜 body/contact/velocity 값으로 변환 계약만 검사한다.
MuJoCo 모델 생성·`mj_forward`·물리 step·렌더를 실행하지 않는다.
네 조건의 실제 study 입력/요청 builder와 scheduler에 고정된 자기 프레임·명령·수신
메시지를 넣고, fake 평가 truth/TOP 설정·영상/hidden event만 바꿔 payload/request/wake가
같은지 대조한다. 심판 완료는 loop 정지만 바꾸고 로봇 완료 통보를 생성하지 않는지 검사한다.
이는 실제 물리 외란의 효과나 카메라 재배치의 영상 불변성을 증명하는 실험이 아니다.

## 코디네이터에게 남은 실제 확인

[TensorBoard의 P06 절](../../docs/tensorboard.md#zone-study-통합-실행-평가--원본--event-계약-p06)에
첫 실제 결과의 snapshot → event readback → 공용 logdir → 영상 → pin/HParams 검증을 적었다.
D1 0.1초/1초 비교창은 1 Hz 기록만으로 재현할 수 없다. 실제 사용 프레임 쌍의 원본·촬영
시각·해시를 보존하고 빠진 쌍은 `insufficient_evidence`로 남겨야 한다.

현재 미확인: 새 고정 소스의 실제 배송·hidden event·terminal 종료, 실제 provider 정산,
새 실제 snapshot/event, 공용 logdir와 영상 재생, 브라우저 pin/HParams 화면.
이 문서는 S11/S14 전체 또는 E2E 파일럿 완료 선언이 아니다.

## 참고 자료

- [PostgreSQL: constraints / primary keys / foreign keys](https://www.postgresql.org/docs/current/ddl-constraints.html)
  — NOT NULL·복합 고유키·외래키의 원리를 메모리 내 관계 검증에 적용했다. SQL 서버를 추가한 것은 아니다.
- [ICH E9(R1), ITT 원칙](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf),
  [CONSORT 2025 item 22a: 배정·수행·분석 수](https://www.consort-spirit.org/item-22a-randomized)
  — 미리 정한 분석 집합과 누락의 투명한 보고를 따른다. INVALID를 비성공으로 세는 규칙은
  이 연구의 보수적 판정 정책이며 CONSORT가 모든 결측치를 실패로 대체하라고 요구한다는 뜻은 아니다.
- [W3C PROV overview](https://www.w3.org/TR/prov-overview/)
  — 원본 entity → 도출 activity → 결과 entity의 출처 관계를 따른다. SHA-256과 게시 전
  재계산은 이 구현의 선택이며 PROV 표준 자체의 해시 의무사항이나 표준 준수 인증이 아니다.
- [Hypothesis: property-based testing](https://hypothesis.readthedocs.io/en/latest/)
  — 예시 몇 개뿐 아니라 생성한 입력 전체에서 불변식을 검사하는 방법을 채택했다. 이번 환경에서는
  같은 목적의 고정 seed 생성기를 사용하며 자동 shrinking은 제공하지 않는다.
- [1차 검토와 재현](https://github.com/kcm0127-dotcom/ugrp/blob/codex/review-e2e-batch-a/experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_A.md),
  [수정 검증 F303-1](https://github.com/kcm0127-dotcom/ugrp/blob/eaf1ff7d5bf75b65f4740cab1bf46e9fe0c2134b/experiments/2026-09-30-e2e-readiness/REVIEW_FIXES_1.md)
- [READINESS / P06 원문](https://github.com/kcm0127-dotcom/ugrp/pull/298)
- [심판·hidden event PR #257](https://github.com/kcm0127-dotcom/ugrp/pull/257)
- [캡처 정책 PR #241](https://github.com/kcm0127-dotcom/ugrp/pull/241)
- [D1 탐색 기록 PR #291](https://github.com/kcm0127-dotcom/ugrp/pull/291), [사전 등록 초안 #293](https://github.com/kcm0127-dotcom/ugrp/pull/293)
- [평가 지표](../../harness/zone_study_eval.py), [심판](../../harness/zone_study_referee.py),
  [기록 후보](../../scripts/zone_study_evidence_writer.py), [변환기](../../scripts/tensorboard_tools/zone_study.py)
