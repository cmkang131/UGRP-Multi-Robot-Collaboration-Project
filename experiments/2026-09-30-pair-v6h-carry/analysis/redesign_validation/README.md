# #299 v3 재설계 검증

출발 소스는 `8a1631b9cf6f9d658961fcb80339539e87541d3d`다.
첫 리뷰 `de16cbc96becf19755f09197b9ef139609f00fe9`와 두 번째 리뷰
`9a3a338fa784555969b913b2196892a252eaf8d6`의 시나리오를 사용한다.
최종 검증 소스의 파일별 SHA-256·명령·종료 코드는 `provenance.json`에 있다.
실제 실험·물리·SIM step·렌더·모델 호출은 0회다.

## 검증 범위

- 관련 8개 파일: 기존 6개(260개 시험) + 두 번째 리뷰 58개 + 생성 검사 파일.
- 기존 구 코드 회귀 17개 node ID를 그대로 별도 실행한다. 전체 관련 검사에 포함된 부분집합이다.
- 고정 시드 202609300299, 10,000개 생성 사례. 각 사례에서 단조성·하드 우선·순서 불변·완전한 증거·고정 분모를 검사한다.
- 필수 항목 손상 12종 외에도 유일한 선택적 GT 하드 관측의 삭제/정상값 치환을 검사한다.
- 파일 경계 9종은 실제 봉인 합성 자료를 `analyse`에 넣어 검증한다. 빈 시도열과 중복 JSON 키/NaN/저장 요약 모순도 검사한다.
- 원 raw의 16개 완료 코호트 308건과 부분 tX1을 모두 다시 읽는다. 원 cases.jsonl 17개의 해시를 이전 공개 기록과 대조한다.

최종 결과는 `related_tests.txt`, `old_regressions.txt`, `properties.json`,
`published_counts.txt`, `published_count_checks.json`에 남긴다. 실패/초기 실행의 위치와
해시는 `development_runs.json`에 있다. 검증 도중 소스가 바뀌었으면 최종 검증으로 채택하지 않는다.

## 시험 기대값을 옮긴 내역

리뷰에서 만든 반례를 삭제하거나 xfail/skip으로 숨기지 않았다. 원본은 위 두 SHA에서
언제든 비교할 수 있다. 아래는 새 사용자 계약과 충돌한 기대값을 명시적으로 고친 것이다.
“기존 assertion을 전부 그대로 통과했다”는 뜻이 아니다.

| 항목 | v2 시험의 기대 | v3 시험의 기대 |
|---|---|---|
| 양성 fixture | 저장 안전 요약·기록 시점 해시 없음 | 실제 요약 필드와 synthetic record_receipt 추가; 손상 검사는 해시를 다시 만들지 않음 |
| 하드 위반 원본+정상 재시도 | 원본 제외, 주 시드 성공 60 | 원본 종단 실패 유지, 주 시드 위반이면 59; 보조 시드 성공은 A 분자 아님 |
| HOST_ERROR의 누락/손상 | 미분류/NOT_EVALUABLE 또는 파일 없는 재시도 PASS | INVALID→FAIL, 분모 유지, 최종 FAIL |
| 누락/중복/틀린 raw ID | 분석 예외만 기대 | 배치별 실패+이유를 보고, 60개 분모·최종 거부 확인 |
| 여러 원본 하드 위반 | 선택 성공은 60, 안전만 거부 | C01/C02/C60 주 시드 실패가 남아 57/60, 하드 시도 4/배치 3 |
| HOST→HOST | 미분류 | 허용 재시도 소진 실패 |
| 분석 중 파일 변경 | EvidenceError | INVALID_COHORT_EVIDENCE로 최종 거부·INPUT_CHANGED 사유 |
| 도달한 PF 누락 | A PASS, B 미평가 | 해당 기록 INVALID→FAIL, B 진단 미평가, 최종 FAIL |
| 옛 행 선택기 | HOST_ERROR 라벨만으로 먼저 재시도 선택 | 함수 삭제; 입력 검증과 실제 상태 기계/전체 분석을 검증 |

스키마는 임의로 2개 leg만 허용하지 않는다. 실제 pair_chain_probe는 L2 이후의 미실행
계획도 저장한다. n_legs가 있으면 전체 목록을 검사하되 A는 L0/L1에 적용한다.
실패 기록도 실제 기록기의 두 형식(phase/code 또는 robot_id/sim_s/reason)을 구별한다.
초기 스키마가 이를 좁게 해석해 만든 집계 차이는 원 raw를 고쳐 맞추지 않고, 기록기
소스의 형식과 맞춘 뒤 전체를 다시 검증했다. 이 과정의 출력도 삭제하지 않았다.

## 재현과 보존

Mac의 기존 `.venv-sim`을 사용한다. Hypothesis는 설치돼 있지 않아 새 의존성 설치 없이
seeded generator를 사용했다. 최종 묶음은 `scripts.run_ci_tests.run_locked`로 공용 잠금을
잡은 뒤 실행했고 자식 프로세스 종료 확인 뒤 반환한다. 다른 작업의 잠금/프로세스를
강제로 지우지 않았다. 생성 사례의 시간은 물리·추론 성능 비교가 아니다.

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_classify_review_299.py \
  tests/test_classify_review_299b.py tests/test_v6h_classifier_properties.py \
  tests/test_ci_sharding.py tests/test_chain_analysis_hard_limit.py \
  tests/test_pair_chain_probe.py tests/test_b_v6h_gain.py
```

위 명령도 공유 Mac에서는 공용 잠금 wrapper 안에서 실행한다. 재분류는
`analysis/revalidate_published.py --output <새 디렉터리>`다. 정확한 명령과 17개 node ID는
provenance.json을 따른다. 전/후 코드 해시와 실제 종료 코드를 함께 기록한다.

전체 보고서·임시 실행 로그·드라이버는 로컬
`/Users/changmin/projects/ugrp/outputs/v6h-classifier-redesign-20260930/`에 보존한다.
이 폴더에는 작은 검증 결과만 커밋하며 원 raw의 원격 백업이라고 부르지 않는다.
새 실험 결과가 없어 TensorBoard 재변환·새 서버·브라우저 열기를 하지 않았다.
기존 snapshot을 보존했다. 독립 재검토와 실제 recorder v3 계약 인수·봉인은 별도다.

## 최종 결과

**323 passed, xfail/skip 0**. 별도 선택한 구 코드 회귀 **17 passed**이며 전체의 부분집합이다.
생성 사례 **10,000개 × 5개 불변식**을 통과했다. 검증 전후 코드·테스트·CI 목록 해시가
동일하며 모든 검증 명령의 종료 코드는 0이다. 정확한 파일 해시는 provenance.json에 있다.

완료 16코호트 **308건**의 케이스·배치·주 시드·L0/L1·하드 위반 집계가 모두 일치한다.
**cA/cB 각각 24/24**, 원 cases.jsonl **17개 해시 일치**다. 부분 tX1은 완료 308건에 합치지 않는다.

의도적으로 달라진 두 기록은 다음과 같다.

- `chain@b-v6h.k1g+p2f+gain+alag:teacher:X06:s911:pPOST:VENVS`
- `chain@b-v6h.k1g+p2f+gain+alag:teacher:X06:s913:pPOST:VENVS`

둘 다 HOST_ERROR 뒤 result.json·trace.jsonl과 필수 chain/저장 안전 요약이 없어
**미분류(null) → INVALID→FAIL**로 바뀐다. 성공 수는 **12/14 그대로**다.
미분류 케이스는 2→0, 주 시드 분류 배치는 6→입장 7개이며 주 시드 성공은 6/7로 보고한다.
후속 tX1b의 성공으로 이 원본 실패를 대체하지 않는다. 케이스별 이유는 published_changes.json,
전체 구/신 수치와 모든 입력 해시는 published_count_checks.json에 있다.

최종 원 로그는 로컬 `outputs/v6h-classifier-redesign-20260930/validation-final/`에 있다.
이 커밋은 판정기·합성 시험·읽기 전용 대조 검증이다. 실제 확증 성공이나 recorder 인수,
독립 재검토 완료를 의미하지 않는다.
