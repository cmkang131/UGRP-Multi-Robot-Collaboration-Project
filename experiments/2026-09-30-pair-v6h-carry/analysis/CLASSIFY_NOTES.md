# v6h 판정기 재설계 — 초안 v3

PR #299의 `c86d9bac`와 `8a1631b9`가 독립 검토에서 두 번 BLOCK됐다.
개별 반례 패치를 중단하고 **전원 분모 유지, 선행 스키마 검증, 종단 실패 상태,
생성 기반 불변식 검사**로 판정 경계를 바꾼다. 제어기·러너·물리를 바꾸거나
실제 확증 자료를 봉인하지 않았다. 이 문서는 v2의 미분류/HOST_ERROR 대체 규칙을 대체한다.
과거 검증은 `review_validation_20260930/`, `review_299_fix_validation/`에 그대로 보존한다.

## 참고 자료

- Schulz, Altman, Moher, **CONSORT 2010 Statement**, item 13/16,
  [BMJ 2010;340:c332](https://www.bmj.com/content/340/bmj.c332),
  [Explanation and Elaboration, item 16](https://www.bmj.com/content/bmj/340/bmj.c869.full.pdf).
  분석에 포함한 수와 제외 사유, 원래 배정된 집단을 명확히 보고하는 원칙을 채택한다.
  이 로봇 실험이 무작위 임상시험이거나 CONSORT 인증을 받았다는 뜻은 아니다.
- **ICH E9(R1)**, 2019-11-20 final, A.1/A.3/A.5/A.6,
  [원문](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf).
  대상 집단·평가량·중간 사건(HOST_ERROR) 처리와 누락 자료 처리를 사전에 구별한다.
  **누락을 실패로 세는 것은 이 프로젝트의 보수적 판정 규칙**이다.
  CONSORT/ICH가 모든 임상 누락값의 실패 대치를 요구한다고 주장하지 않는다.
- **JSON Schema Validation 2020-12**, §6.1/6.3/6.5,
  [type, bounds, required](https://json-schema.org/draft/2020-12/json-schema-validation).
  필드 존재·타입·유한값·범위를 먼저 검사한다. 시간 순서·파일 간 동일성은 별도 의미 검사다.
  구현은 프로젝트 전용 Python 검증기이며 범용 JSON Schema 구현이라고 주장하지 않는다.
- **W3C SCXML 1.0**, D.1,
  [determinism/completeness/run-to-completion](https://www.w3.org/TR/scxml/#AlgorithmforSCXMLInterpretation).
  사건 순서와 우선순위를 고정한 전이표를 사용한다. SCXML 실행기를 도입한 것은 아니다.
- Claessen & Hughes, **QuickCheck**, ICFP 2000,
  [논문](https://www.cs.tufts.edu/~nr/cs257/archive/john-hughes/quick.pdf).
  예제별 기대값만으로 끝내지 않고 생성 입력에 공통으로 성립해야 하는 성질을 검사한다.
  `.venv-sim`에 Hypothesis가 없어 고정 시드 `202609300299`의 Python 난수 생성기를 쓴다.

- **NIST FIPS 180-4**, [Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final).
  저장한 SHA-256과 내용을 비교해 생성 이후 삭제·손상을 확인한다. 자기 파일에 든 해시는
  작성자 인증을 제공하지 않는다. 원본과 해시를 함께 위조한 경우까지 식별한다는 주장은 하지 않는다.

## 입력에서 판정까지

1. **입장 명부를 먼저 고정한다.** 확증은 봉인의 C01…C60×941과 C01…C12×943이다.
   원본 기록이 없거나 파싱되지 않아도 그 자리에 INVALID를 만든다. 등록된 재시도도
   result/trace가 남아 있으면 행이 없어도 검사한다. 파일이 없는 미실행 재시도만 생략하며
   그 파일의 부재도 종료 시 재확인한다. 과거 대조는
   manifest의 계획과 저장 행을 사용한다. 실제 봉인 자체가 없거나 해시가 틀리면
   분석 대상을 승인할 수 없어 CLI 입력 오류(종료 2)이며 PASS 출력이 없다.
2. **증거를 읽고 검증한다.** `EvidenceReader`는 읽은 바이트를 해시하고 유효 JSON
   관측을 보존한다. 파일 부재·빈 파일·잘린 줄·중복 시도·다른 실행 식별자는 오류다.
   정상 JSON 줄에서 끝난 잘림도 coverage/count/time 검사로 잡는다.
   확증에서는 저장된 `result.evidence_sha256`도 필수다. 필수 필드가 아닌 GT 관측 하나를
   지우거나 그 수치를 그럴듯한 정상값으로 바꿔도 기록 당시 해시와 달라져 실패한다. 처리 중 변경은
   코호트 INVALID다. 입력 행 순서로 재시도를 선택하지 않는다.
3. **시도 하나를 판정한다.** `adjudicate_attempt`는 스키마 오류를 결과의 이유로
   바꾼다. 저수준 `classify_case`/검증 함수가 내는 `EvidenceError`는 이 경계에서 잡는다.
   하드 관측 수집은 손상 자료에서 양성 위반만 보존하며 안전함을 증명하지 않는다.
4. **봉인에 적힌 원본→허용 재시도 순으로 전이한다.** 아래 표 외의 선택 경로가 없다.
   `select_confirmatory_rows`와 HOST_ERROR 전용 느슨한 검증 경로를 삭제했다.
5. **선택 결과를 한 번 집계한다.** 72개 시도 슬롯·60개 배치, 주 시드 941 분모 60이다.
   INVALID는 `class=FAIL`, 별도 `state/reason_code/invalid_cases`를 가진다.
   모든 실행 시도(거부한 재시도 포함)의 하드 위반은 전체 안전 관문에 남는다.

## 필수 증거와 경계

| 단위 | 검사 |
|---|---|
| 시도 | `case_id`, `cell`, 정수 `seed`, `stage=chain`; 봉인의 case id·replaces·case.json 해시·설정 일치 |
| 저장 안전 요약 | `row.wall_contact` 필수: episodes 정수≥0, max_penetration_m 유한≥0, max_tilt_deg_stage 유한 0…180, hard_limits 정확히 15°/0.005 m |
| 과제 | `chain.legs`에 L0/L1, `first_failure` 명시; recorded bool, 도달한 leg의 start/end/lift/tilt/error/네 집게 bool, L0 끝<L1 시작 |
| 실패·종료 | `result.failures`에 정확히 r1/r2(null=실패 없음), termination outcome/time; 실패 시각이 있으면 종료 전에 있어야 함. HOST_ERROR 행과 종료 상태 일치 |
| trace | 빈 trace 금지, 시각 엄격 증가, 간격≤0.051 s, 유한 기울기; 확증에서는 lift/네 집게 및 전체 수집→종료 coverage/count 일치 |
| 접촉 | episodes 배열, 유한·정렬된 구간과 관통값; 확증에서 전체 접촉 추적 coverage/count/period/max_gap |
| 확증 성공 | teacher 포함 전체 창, L0 바닥 놓기·개방 및 L1 직전 재파지, restaging=false, L1 첫 wait_lower 종료, 도달한 끝점의 유효 PF 증거 |
| 저장 증거 해시 | 확증에서 evidence_sha256 필수; 아래 canonical payload와 일치. 판정기가 새 해시로 보충하지 않음 |
| 파일 관계 | runtime identity와 봉인 일치, result.row와 cases 행 일치, 입력 파일의 분석 전후 해시/존재 일치 |

저장 증거 해시는 `value_hash({"row": row, "result": payload, "trace": trace})`다.
`value_hash`는 UTF-8 JSON의 sort_keys=true, separators=(",",":"), allow_nan=false에 SHA-256을 적용한다.
`payload`는 result에서 evidence_sha256만 뺀 객체다. 중복 row와 execution_identity도
해시에 포함하고 봉인/행 동일성 검사를 별도로 거친다. trace 순서는 포함하며 무관한
cases 행 순서는 포함하지 않는다. 선택적 관측도 해시 대상이다. 이 필드는 **새 기록 계약**이며
기존 raw에 판정기가 소급 추가하지 않는다. 실제 기록 어댑터는 후속 검토/인수가 필요하다.

기록기에는 두 가지 실패 형식이 있다. pair_chain_probe의 phase/code와
run_pair_stage_probes의 robot_id/sim_s/reason이다. 각각 명시적으로 검사하며 임의의
non-null dict를 허용하지 않는다. reason=HOST_ERROR인 wrapper 표시는 과제 실패와
구별하지만, 같은 기록에 있는 실제 chain/controller 실패는 계속 종단 실패다.
계획된 L2 이후의 미실행 leg도 남기고 검사한다. n_legs가 있으면 그 목록과 일치해야 한다.

하드 관측은 trace, leg 끝점, 저장 GT(teacher·entry/stop/end·robot별 leg start/end/done·exit),
result 최대값, **cases와 result.row 각각의 저장 안전 요약**, 접촉 episodes의 합집합이다.
기울기 **>15°**, 관통 **>5 mm**가 하나라도 있으면 `FAIL_HARD_LIMIT`다.
정확히 문턱인 값과 바로 다음 부동소수점 값을 구별한다. 일반 leg 기울기 한계 10°는 별도다.

과거 raw에는 새 전체 창/접촉 coverage가 없으므로 `historical_endpoints`로만 대조한다.
이 모드의 끝점 PASS를 새 확증 PASS로 승격하지 않는다. 전체 확증 판정은 언제나 봉인과
완전한 기록을 요구한다. 원 raw를 보완하거나 새 필드를 소급 삽입하지 않는다.

## 상태와 전이표

사건은 검증이 끝난 시도다. `HARD`는 알려진 하드 위반, `INVALID`는 증거 오류,
`FAIL`은 확정 과제 실패, `HOST_SAFE`는 **완전한 원본 기록이 위반·과제 실패 없음과
HOST_ERROR 종료를 함께 입증한 경우**, `PASS`는 모든 성공 증거가 유효한 경우다.
과제 실패와 cleanup HOST_ERROR가 함께 있으면 FAIL 또는 INVALID이며 HOST_SAFE가 아니다.

| 현재 상태 | PASS 사건 | FAIL 사건 | HARD 사건 | INVALID 사건 | HOST_SAFE 사건 |
|---|---|---|---|---|---|
| NEW | PASS | FAIL | HARD | INVALID | RETRY |
| RETRY | PASS | FAIL | HARD | INVALID | INVALID |
| PASS | INVALID | INVALID | HARD | INVALID | INVALID |
| FAIL | FAIL | FAIL | HARD | FAIL | FAIL |
| INVALID | INVALID | INVALID | HARD | INVALID | INVALID |
| HARD | HARD | HARD | HARD | HARD | HARD |

EOF에서 NEW/RETRY는 INVALID→FAIL이다. 빈 시도열도 MISSING_ORIGINAL 실패다.
RETRY만 다음 결과를 선택할 수 있고 같은 설정·시드의 봉인된 재시도 최대 1회만 허용한다.
원본 FAIL/FAIL_HARD_LIMIT은 성공 재시도로 바뀌지 않는다. FAIL 뒤 하드 위반은 더 강한
FAIL_HARD_LIMIT으로 남는다. PASS 뒤 추가 실행은 승인된 재시도가 아니므로 INVALID다.
미등록 세 번째 시도도 분모를 늘리지 않으며 증거 오류와 안전 검사에 남는다.
FAIL/HARD 뒤 덧붙인 시도는 원본 선택 ID를 바꾸지 않는다. RETRY 이외 상태에서의
추가 시도는 sequence_issues에 위반으로 남고 전체 PASS를 막는다.

출력은 `attempts`의 모든 시도 상태와 `attempt_transitions`를 보존한다.
`n_attempts`는 실제 행이 있는 시도 수, `n_adjudicated_attempt_slots`는 누락 원본의
INVALID 자리까지 포함한 판정 슬롯 수다. 누락을 실제 실행 증거로 부르지 않는다.
주 시드의 실패를 분모에서 빼지 않는다. 보조 943의 성공은 A의 분자가 아니며
943에서의 위반은 안전 거부 사유다. `full_verdict`는 증거 오류 또는 B 미평가에도
FAIL_A_B_SAFETY다. B의 진단 상태 NOT_EVALUABLE은 그대로 보여 주되 최종 PASS로 읽지 않는다.

## 생성 검사의 불변식

`tests/test_v6h_classifier_properties.py`는 10,000개 생성 사례 각각에서 다음을 확인한다.

- 실패 입력의 필수 필드 삭제·trace 잘림·손상·시각/개수 모순이 성공을 만들지 않는다.
- 어느 시도의 어느 지원 안전 기록에 하드 위반을 넣어도 FAIL_HARD_LIMIT이 남는다.
- 무관한 배치 기록의 순서를 바꿔도 집계와 판정이 같다.
- PASS에는 원본부터 선택 결과까지 유효한 증거가 필요하며, 불완전한 HOST_ERROR는 재시도 성공으로 덮이지 않는다.
- 분모와 상태 집계 합은 입장한 배치 수와 같다.

12개 손상군·선택적 하드 GT 삭제/정상값 손상·다섯 하드 관측 위치·확정 실패+cleanup·허용 재시도를 조합한다.
별도 파일 경계 검사에서 행/파일 삭제, 잘린 JSON, 빈 trace, 중복 행의 하드 위반, 재시도 행만 사라지고 남은 결과 파일,
저장 요약 누락·비표준 NaN JSON·중복 JSON 키를 검사하고 파일 손상을 실제 `analyse`에 넣고 60개 분모와 순서 불변성을 확인한다.
생성 시험은 수학적 증명이나 원본 기록의 진실성 인증이 아니다. 여러 원본을 일관되게
위조한 경우까지 식별한다는 주장이 아니며, 실행 소스 고정·파일 출처 보존은 별도 계약이다.

## 리뷰 finding → 설계 반영

| 리뷰 | 이전 문제 | v3에서 막는 경계 |
|---|---|---|
| #299 R1 | 비동기 끝점 기울기가 일반 실패로 축소 | 안전 관측 합집합과 HARD 최우선 |
| #299 R2 | HOST_ERROR 원본이 선택에서 빠짐 | 모든 시도를 먼저 판정, terminal 실패 보존 |
| #299b P1-1 | row.wall_contact 요약을 읽지 않음 | 필수 저장 요약과 두 복사본의 양성 관측 수집 |
| #299b P1-2 | HOST_ERROR만 coverage/count/시간 검사를 우회 | 원본·재시도 공통 검증기, INVALID→FAIL |
| #299b P1-3 | END_ERROR 뒤 cleanup ENOSPC가 실패를 대체 | HOST_SAFE는 과제 실패 없음 증명 필요, FAIL 흡수 상태 |

리뷰 시험 출처: `de16cbc96becf19755f09197b9ef139609f00fe9` 및
`9a3a338fa784555969b913b2196892a252eaf8d6`. 두 파일을 포함하고 모든 xfail을 제거했다.
양성 합성 fixture에는 필수 저장 안전 요약과 기록 시점 해시를 추가했다.
새 규칙과 충돌한 기대값(미분류, 원본 하드 위반 뒤 60/60, 누락 파일 재시도 PASS)은
반례 입력을 보존한 채 실패 집계로 바꿨다. 모든 스키마 추가·기대값 이관을 검증 기록에
공개한다. “원래 assertion을 전부 그대로 통과했다”라고 보고하지 않는다.

검증 결과·공개 308건 및 부분 tX1의 변경 내역은 `redesign_validation/`에 기록한다.
물리/SIM step/렌더/모델 호출은 없으며 독립 재검토·실제 기록 어댑터·봉인/등록 인수는
별도다. 기존 TensorBoard snapshot을 보존한다. 이 작업은 새 실험/학습 결과가 없어
재변환·서버 실행·브라우저 표시를 하지 않는다.
