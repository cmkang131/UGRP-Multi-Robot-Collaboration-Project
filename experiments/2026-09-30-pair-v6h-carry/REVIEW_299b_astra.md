# PR #299 독립 적대적 재검토 — 2026-09-30

**판정: BLOCK.** 이전의 여섯 핵심 반례와 기존 관련 시험 260개는 수정 코드에서 통과한다. 그러나 재시도를 일반화하면 **저장된 안전 위반 누락, 손상된 저장 기록의 통과, 확정 실패의 재시도 대체**라는 P1 세 건이 남는다. 공개 완료 308건의 집계 보존과 새 확증 판정기의 적합성은 별개다. 이 SHA의 병합·확증 판정기 채택을 승인하지 않는다.

| 항목 | 고정 대상 / 범위 |
|---|---|
| 검토 SHA | `8a1631b9cf6f9d658961fcb80339539e87541d3d` |
| 직전 검토 대상 | `c86d9bac62036904ecc641db5e59e79edb58dec2` |
| 원 독립 리뷰 | `de16cbc96becf19755f09197b9ef139609f00fe9`, `origin/codex/review-299:experiments/2026-09-30-pair-v6h-carry/REVIEW_299_astra.md` |
| 검토 브랜치 | `codex/review-299b` |
| 읽은 수정 설명 | `REVIEW_RESPONSE.md`, `analysis/CLASSIFY_NOTES.md`, `analysis/SEALED_INPUT.md`, `PREREG_DRAFT.md`, #299 구현자 코멘트 |
| 실행 범위 | 합성 JSON 판정, 오프라인 시험, 기존 raw 읽기·재분류, 수치 재현 |
| 제외 | 물리/SIM step/렌더/모델 호출, 제어기·분류기 수정, 실제 봉인·등록·병합 |

이하 `C`는 `experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py`이며 줄 번호는 위 SHA 기준이다. 합성 파일은 가짜 소스 식별자를 쓰는 재현 자료다. 실제 봉인이나 과거 물리 실행에서 이 반례가 발생했다는 주장이 아니다. 새 시험은 첫 독립 리뷰의 JSON 생성기만 재사용하고 기대 판정·변형은 별도로 작성했다.

## 이전 지적의 수정 여부

| 이전 항목 | 직접 확인 | 판정 |
|---|---|---|
| R1: trace 사이 L0/L1 끝점 16°가 일반 FAIL로 축소됨 | 원 두 반례가 `FAIL_HARD_LIMIT`/전체 안전 거부로 바뀐다. teacher·start/end/done·종료 GT, 두 로봇 값의 최대값, 다른 시각, 정확한 15° 및 그 다음 부동소수점 수까지 검사했다 | **해당 끝점/GT 경로 수정 확인**. 형식이 잘못된 일반 입력은 문서대로 EvidenceError로 거부하며 통과로 바꾸지 않는다 |
| R2: HOST_ERROR 원본을 버리고 성공 재시도만 안전 검사함 | 원 기울기/관통 × 941/943 네 반례, 원본 파일 해시, 여러 배치의 동시 재시도, 원본과 재시도 모두 위반, B 누락과 알려진 위반의 우선순위가 통과한다 | **부분 수정**. 실행 시도 보존은 맞지만 실제 기록기의 요약 안전값이 빠져 P1-1이 남는다. 부분 파일 검사도 P1-2만큼 불완전하다 |
| 재시도/분모 보호 | 원본 PASS/FAIL의 단순 재시도, 세 번째 시도, 중복 원본/재시도/배치-시드, C 이름 중복을 거부한다. HOST→FAIL은 일반 실패 한 건, HOST→HOST는 미분류 한 건으로 유지한다 | 단순 순서는 정상. **FAIL 뒤 HOST_ERROR가 덧붙은 순서는 P1-3** |
| 공개 집계 보존 | 16개 완료 코호트 308건 및 부분 tX1을 원 raw에서 다시 읽었다 | 모든 공개 집계·17개 cases.jsonl 해시 일치 |

아래는 **새 반례**다. 세 결함 모두 이번 수정이 새로 만든 회귀라고 주장하지 않는다. P1-1/2는 R2 보완의 누락이고, P1-3은 기존 선택 규칙에 남아 있는 혼합 실패 경로다. 수정으로 추가된 최대값 합산·전체 시도 집계·판정 우선순위의 다른 변형에서는 새 오류를 재현하지 못했다.

## P1-1 — 원본의 `row.wall_contact`에 남은 하드 위반을 여전히 버린다

**위치:** `C:234–244,259–269`; 실제 기록 형식은 `scripts/run_pair_stage_probes.py:379–382,875–881`.

`observed_hard_limits`는 `row`/`result.row`의 leg·setdown·최상위 `max_tilt_deg`만 읽는다. 실제 기록기는 최대값을 **`row.wall_contact.max_penetration_m` / `max_tilt_deg_stage`**에 저장한다. 따라서 큰 result/trace가 없어져도 cases.jsonl에 남아 있는 수치 위반을 놓친다. 이것은 임의로 지어낸 필드가 아니다.

재현: 합성 60+12 계획에서 C01 같은 시드의 1회 재시도를 허용한다. 원 시도를 HOST_ERROR로 기록하고 아래 요약을 cases.jsonl에 남긴 뒤 원 result/trace는 없는 상태로 둔다. 허용 재시도는 정상 완료한다.

```json
{
  "category": "HOST_ERROR:ENOSPC",
  "wall_contact": {
    "episodes": 1,
    "max_penetration_m": 0.006,
    "max_tilt_deg_stage": 1.0
  }
}
```

관통 대신 `max_tilt_deg_stage=16.0`으로도 같다. **기대:** 전체 `FAIL_A_B_SAFETY`, 위반 시도 1. **실제:** 선택 72건/실제 73시도, **60/60**, 위반 **0**, **`PASS_A_B_SAFETY`**. 파일이 없음을 표시해도 이미 cases에 있는 위반은 사라지면 안 된다.

- 941/943 × 기울기/관통 × cases에만 존재/두 사본 모두 존재의 **8개 변형은 잘못된 전체 PASS**다.
- `result.row`에만 남고 cases 사본에는 빠진 **4개 변형은 NOT_EVALUABLE**이다. 사본 불일치는 감지하지만 관측된 위반은 여전히 0으로 만든다. 구현자 문서의 “알려진 위반이 증거 불완전보다 우선”도 충족하지 못한다.

**수정 조건:** 실제 기록기의 두 요약 필드도 모든 원본·재시도, cases/result.row 사본의 안전 최대값 합집합에 포함한다. 요약에 양성 위반이 있으면 파일 부재·사본 불일치로 지우지 않는다. 요약의 0은 전체 추적이 완전했다는 대체 증거로 쓰지 않는다.

**재현 시험:** `tests/test_classify_review_299b.py::test_r2_saved_contact_summary_must_keep_known_violation` (12개, strict xfail).

## P1-2 — 줄 경계에서 잘린 HOST_ERROR trace는 정상 파일로 간주한다

**위치:** `C:591–629`, 특히 `607–619,620–627`. 전체 판정 반영은 `C:698–713`.

새 로더는 JSON 구문 오류만 수집하고, 읽은 행의 시각·순서·간격 및 **이미 저장된 coverage와의 모순**을 검사하지 않는다. JSONL이 완전한 줄 뒤에서 잘리면 남은 줄은 모두 파싱된다. 파일이 비어 있어도 `splitlines()`가 빈 목록이 되어 이슈가 없다.

재현: 정상 C01 원본을 HOST_ERROR로 표시하고 정상 재시도를 추가한다. 원 `result.json`에는 `evaluation_coverage={start_sim_s:0,end_sim_s:3.25,trace_count:66}`을 그대로 둔다. 원 trace를 **21개 정상 JSON 행, 0…1.0초**까지만 남긴다.

**기대:** 저장된 66행/3.25초 선언과 모순되므로 `safety_evidence_issues`에 기록하고 **NOT_EVALUABLE**. **실제:** issues `{}`, 위반 0, **60/60, `PASS_A_B_SAFETY`**. 0바이트 파일, 중간 30행 누락, 중복 시각, 역순도 같은 결과다.

이 시험은 “아직 종료 metadata를 못 쓴 HOST_ERROR는 항상 실패여야 한다”는 요구가 아니다. **존재하는 metadata와 존재하는 파일이 서로 모순되는 경우**다. `PREREG_DRAFT.md:177`과 `SEALED_INPUT.md`는 저장 증거 손상이 있으면 알려진 위반이 없는 경우에도 NOT_EVALUABLE이라고 명시한다. 현재 구현은 마지막 JSON 문장이 반쯤 잘린 경우만 잡는다.

**수정 조건:** 부분 기록에서 알 수 있는 일관성을 검증한다. 알려진 행 수·시작/끝·시간 순서·간격과 모순되면 표시하며, 없는 종료 metadata를 억지로 요구하지 않는다. 어떤 손상이 있더라도 읽을 수 있는 위반은 계속 안전 거부에 남겨야 한다(이 양성 대조는 통과했다).

**재현 시험:** `tests/test_classify_review_299b.py::test_host_stored_trace_contradiction_is_not_silent_success` (5개, strict xfail).

## P1-3 — 확정 FAIL 뒤 정리 오류가 나면 실패를 재시도로 대체한다

**위치:** `C:522–527`의 HOST_ERROR 표식만 보는 선택, `C:661–668`의 일반 실패 검사 생략. 일반 케이스의 실패 검사는 `C:313–335`에 있지만 이 경로에서는 실행되지 않는다.

재현: C01…C13의 941 원본은 L1 끝 오차 **0.11 m**, `chain.first_failure={phase:carry,leg:1,code:END_ERROR,sim_s:3.01}`, `result.failures.r1`도 같은 실제 실패다. 다른 47곳은 통과한다. 같은 입력의 양성 대조는 **47/60, FAIL_A_B_SAFETY**다.

이 13건에 **끝점·실패 기록을 그대로 둔 채** 나중 정리 중 `HOST_ERROR:ENOSPC`를 추가하고, 미리 허용한 같은 설정/시드의 성공 재시도를 실행한 합성 기록을 넣는다.

**실제:** 선택 72건/실제 **85시도**, `counts.FAIL=0`, **60/60, `PASS_A_B_SAFETY`**. 원 시도 목록·안전 수치만 남고 이미 확정된 일반 실패가 A에서 없어진다. §5.1 및 입력 계약의 “controller 실패는 재시도하지 않는다”, 코드 자체의 `never retry controller failure`와 맞지 않는다. HOST_ERROR만 발생한 정상 재시도와, 실패 판정 뒤 결과 저장/정리까지 겹친 경우를 구별해야 한다.

**수정 조건:** 재시도 적격성을 최종 wrapper 표식 하나로 결정하지 않는다. 종료 전 확정된 controller/평가 실패를 유지하거나, 혼합·모순 입력을 거부하고 봉인 전에 우선순위를 명시한다. 반례 시험은 입력 거부 또는 원 실패를 보존한 비통과를 허용한다. 모든 HOST_ERROR를 일반 FAIL로 바꾸라는 뜻은 아니다.

**재현 시험:** `tests/test_classify_review_299b.py::test_controller_failures_followed_by_cleanup_errors_cannot_be_retried_to_pass` (1개, strict xfail).

## 새 반례 범위

새 파일은 **13종의 변형, 58개 시험**이다. 초기 실행은 **40 passed, 18 failed**였고 모두 실제 판정 assertion 실패였다. 18개를 서로 다른 버그 18개로 세지 않는다. **14개는 잘못된 전체 PASS, 4개는 알려진 위반의 NOT_EVALUABLE 축소**다.

최종 관련 7개 파일은 **300 passed, 18 xfailed**(기존 260 + 새 통과 40 + 반례 18)다. 세 결함군만 `strict=True, raises=AssertionError`로 표시했다. `--runxfail -m xfail`로 다시 실행하면 **18 failed, 40 deselected**이며 전부 판정 assertion 실패다. import 오류·잘못된 fixture 예외를 xfail로 숨기지 않았다. 알려진 결함을 표시한 시험 실행 성공은 분류기 승인을 뜻하지 않는다.

| 새 변형 | 수 | 확인 내용 |
|---|---:|---|
| 다른 시각의 비동기 GT·두 로봇 최대값·15° 다음 표현 가능 수 | 10 | 통과 |
| 준비/전이/종료 직전 관통·5 mm 다음 표현 가능 수 | 10 | 통과 |
| 일반 끝점의 jaws/lift/time/tilt 누락 | 4 | 입력 거부 |
| 원본 접촉 요약만 남음 / 두 사본 / result 사본만 남음 | 12 | P1-1 |
| 저장 trace의 빈 파일/정상 줄 뒤 절단/중간 누락/중복/역순 | 5 | P1-2 |
| 잘린 원본의 알려진 위반 + 재시도 PF 누락 | 1 | B 미평가보다 안전 거부 우선 |
| HOST_ERROR GT/접촉의 수치 필드 누락 | 2 | NOT_EVALUABLE |
| 4개 합법 재시도·역순 행·같은 배치의 941/943 위반 | 1 | 76시도/72선택, 위반 4시도/3배치 |
| HOST→FAIL/HOST, 원본 위반 유/무 | 4 | FAIL/미분류 유지, 알려진 안전 거부 우선 |
| PASS/FAIL 원본의 금지 재시도 | 2 | 입력 거부 |
| HOST→HOST→PASS / HOST→FAIL→PASS, 3회 시도 봉인도 시도 | 2 | 추가 실행·3회 허용 봉인 모두 거부 |
| 완료 FAIL→정리 HOST_ERROR→PASS | 1 | P1-3 |
| 원본/재시도 중복, 다른 ID의 동일 배치·시드, 배치 이름 중복 | 4 | 입력 거부 |

## 308건 재대조와 검증 기록

직접 실행한 `revalidate_published.py`가 원 cases/result/trace/manifest를 새로 읽었다. 구현자가 남긴 재분류 JSON을 복사하지 않았다. 케이스 수·연쇄 통과·모든 시드 배치 통과·주 시드 911·L0/L1·하드 위반 수·실행 SHA가 모두 이전 공개 기대값과 같고, **17개 cases.jsonl SHA-256도 일치**한다.

| 코호트 | 건수 | 연쇄 통과 | 모든 시드 통과 배치 | 주 시드 통과 | L0 / L1 통과 |
|---|---:|---:|---:|---:|---:|
| cA | 24 | 24 | 12/12 | 12 | 24 / 24 |
| cB | 24 | 24 | 12/12 | 12 | 24 / 24 |
| cC | 24 | 5 | 0/12 | 5 | 24 / 5 |
| cD | 24 | 1 | 0/12 | 1 | 22 / 1 |
| cF | 24 | 0 | 0/12 | 0 | 14 / 0 |
| rA | 20 | 14 | 7/10 | 7 | 20 / 14 |
| rB | 20 | 14 | 7/10 | 7 | 20 / 14 |
| sA | 24 | 20 | 10/12 | 10 | 24 / 20 |
| sB | 24 | 22 | 11/12 | 11 | 24 / 22 |
| chBase | 10 | 0 | 0/10 | 0 | 4 / 0 |
| chK1g | 20 | 0 | 0/10 | 0 | 20 / 0 |
| chK0g | 10 | 0 | 0/10 | 0 | 10 / 0 |
| chK1gP1 | 20 | 14 | 7/10 | 7 | 20 / 14 |
| chK1gP2 | 20 | 14 | 7/10 | 7 | 20 / 14 |
| chK0gP1 | 10 | 7 | 7/10 | 7 | 10 / 7 |
| chK1P1 | 10 | 4 | 4/10 | 4 | 10 / 4 |

부분 tX1은 **12/14 + HOST_ERROR 2건**, 7곳 중 주 시드 분류 가능 6곳이다. 완료 308건에 합치지 않았다. `cohort_sizing.py --check`, `make_confirmatory_placements.py --check` 및 29구성/26좌표/20근접 묶음의 원 case 해시 검사도 직접 통과했다.

재현은 기존 Mac venv를 사용한다. 아래 명령은 `scripts.run_ci_tests.run_locked`로 공용 잠금을 획득한 wrapper 안에서 실행한다. `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest cache 비활성이다.

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_ci_sharding.py \
  tests/test_chain_analysis_hard_limit.py tests/test_pair_chain_probe.py \
  tests/test_b_v6h_gain.py tests/test_classify_review_299.py \
  tests/test_classify_review_299b.py

python -m pytest -q -p no:cacheprovider --runxfail -m xfail \
  tests/test_classify_review_299b.py

python experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py \
  --output /tmp/review299b-published-NEW
```

시험 fixture 출력도 새 디렉터리에 보존한다. 전체 재분류·합성 입력·원 로그는 `/Users/changmin/projects/ugrp/outputs/review-299b-astra-8a1631b9/`, 작은 검증 기록은 [analysis/review_299b_validation/](analysis/review_299b_validation/)에 있다. 실제 raw와 원 공개 숫자는 변경하지 않았다. 새 테스트는 위 명시 명령으로 실행하며 공용 CI 목록은 리뷰에서 수정하지 않았다.

물리/SIM step/렌더/모델 호출은 **0회**다. 이 리뷰는 코드 반례와 과거 집계 대조이고 새 물리·학습 결과가 아니므로 기존 TensorBoard snapshot을 재변환하거나 viewer를 시작하지 않았다. 실제 러너의 새 입력 계약 충족, 접촉 추적 감도, UI 표시, 새 확증·E2E·실물 성공은 검증하지 않았다. UGRP 예외에 따라 Drive 작업은 없다. 전체 로컬 raw의 원격 백업을 주장하지 않는다. 수정 뒤 세 반례군과 관련 시험을 다시 통과시켜야 병합 준비 상태를 재검토할 수 있다.
