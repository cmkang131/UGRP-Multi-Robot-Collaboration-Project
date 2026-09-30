# PR #299 독립 적대적 검토 — 2026-09-30

**판정: BLOCK.** 저장된 안전 위반이 있는데도 확증 코호트 전체를 `PASS_A_B_SAFETY`로 만드는 두 경로를 재현했다. 현재 SHA로 #299 병합 또는 확증 판정기 채택을 승인하지 않는다. 관련 시험 **228 passed, 6 xfailed**이며 xfail을 해제하면 여섯 반례 모두 실제 assertion으로 실패한다. 공개 308건의 집계는 모두 일치한다.

| 구분 | 고정 소스 / 범위 |
|---|---|
| 검토 대상 #299 | `c86d9bac62036904ecc641db5e59e79edb58dec2`, `codex/v6h-classifier-fixes` |
| base / 구 분류기 | `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`, `claude/b-v6h-gain` |
| 검토 브랜치 | `codex/review-299` |
| 작업 | 코드·사전등록·이전 검토 읽기, 합성 JSON, 저장 raw 재분류, 오프라인 pytest |
| 제외 | 물리/SIM step/렌더/모델 호출, 실행·봉인·등록·제어기 수정, 병합 |

이하 `V/`는 `experiments/2026-09-30-pair-v6h-carry/`다. 코드 줄 번호는 검토 대상 SHA 기준이다. 반례는 과거 실험에서 발생했다는 주장이 아니다. 실제 원본과 공개 숫자를 수정하지 않았다. 새 테스트의 입력 생성기는 기존 저자 테스트 fixture를 불러오지 않는다. 합성 manifest는 가짜 소스 식별자를 쓰는 시험용이며 실제 확증 승인·봉인 파일이 아니다.

## BLOCKER R1 — trace 사이의 끝점 기울기 위반이 일반 FAIL로 축소된다

**위치:** `V/analysis/classify_placements.py:206–212,230–235,264–267,478–479`.

전체 안전 최대값은 `trace[*].tilt_deg`에서만 만들고, 이미 검증한 `chain.legs[*].tilt_deg`는 일반 leg 검사에만 쓴다. 끝점은 0.05초 trace 격자와 다른 시각일 수 있다. 실제 기록기도 주기적 trace(`scripts/run_pair_stage_probes.py:483–509`)와 상태 전이의 GT snapshot(`harness/pair_chain_probe.py:113–119,216–222`)을 별도로 기록한다.

재현 입력은 완전한 봉인 60+12건, 유효한 A/B 증거에서 C01/941 한 건만 다음처럼 바꾼 것이다. 원본·계획·실행 identity는 모두 일치한다.

```json
{
  "L1": {"start_sim_s": 2.0, "end_sim_s": 3.01, "tilt_deg": 16.0},
  "first_failure": {"phase": "carry", "leg": 1, "code": "TILT", "source": "gt_criterion", "sim_s": 3.01},
  "nearby_trace": [{"t": 3.0, "tilt_deg": 14.9}, {"t": 3.05, "tilt_deg": 14.9}]
}
```

나머지 trace는 처음부터 종료 정리까지 0.05초 간격이고 handover·집게·PF·접촉 coverage는 정상이다. L0 끝 1.01초로 옮긴 반례도 같은 문제다.

**기대:** C01 `FAIL_HARD_LIMIT`, 하드 위반 1, 코호트 `FAIL_A_B_SAFETY`. **실제 출력:** 일반 `FAIL` 1, 통과 **59/60**, 하드 위반 **0**, `PASS_A_B_SAFETY`. 48/60 문턱보다 성공 수가 많아도 위반 1건이면 전체 거부한다는 §4/§5 규칙을 어긴다.

**수정 조건:** 안전 최대값에 모든 기록된 끝점/GT 안전 관측을 포함한다. 일반 tilt 실패를 코호트의 안전 위반 0으로 낮추지 않는다. 비동기 표본이라는 이유만으로 두 기록 중 작은 값만 택하면 안 된다.

**반례 테스트:** `tests/test_classify_review_299.py::test_endpoint_hard_limit_between_trace_samples_must_veto_cohort` (L0/L1 두 경우, strict xfail).

## BLOCKER R2 — HOST_ERROR 대체가 원 시도의 안전 위반까지 지운다

**위치:** `V/analysis/classify_placements.py:442–447,514–525,529–543,551–559`.

봉인에 허용한 재시도가 존재하면 원 HOST_ERROR 행을 `select_confirmatory_rows`에서 제거한 뒤 결과/trace를 읽는다. 제거된 시도의 안전 증거를 읽거나 해시하지 않는다. 성공률 분모에 시도 하나만 넣는 것과, 실제로 관측한 안전 위반을 없애는 것은 서로 다른 결정이다.

재현 입력은 실행 전에 C01의 같은 배치·시드 재시도 하나를 봉인하고, 원 시도가 다음과 같이 끝난 경우다.

```json
{
  "original": {
    "category": "HOST_ERROR:ENOSPC",
    "host_error": "ENOSPC during result cleanup",
    "saved_trace_observation": {"t": 1.25, "tilt_deg": 16.0}
  },
  "retry": {"same_settings_and_seed": true, "all_checks_pass": true}
}
```

관통 반례는 원 결과에 `{"t_first":1.25,"t_last":1.3,"max_pen_m":0.006}` 에피소드를 남긴다. 두 반례 모두 충분한 원 trace/coverage가 보존되어 있고, 주 시드 941 및 보조 943에서 각각 검사한다. 73개 실행 행, 72개 선택 결과, 배치 분모 60은 그대로 둔다.

**기대:** 이미 관측한 16° 또는 6 mm 때문에 전체 `FAIL_A_B_SAFETY`. **실제 출력:** **60/60**, 하드 위반 **0**, `PASS_A_B_SAFETY`. 원 ID만 `attempt_case_ids`에 남고 원 `result.json`/trace는 입력 해시에서도 빠진다.

§5.1(10–11)의 HOST_ERROR 대체는 성공률 분모의 이중 계산을 막는 규칙이다. §4의 전체 연쇄·어느 시드든 하드 위반 1건이면 거부한다는 규칙을 면제하지 않는다. 위반 뒤 저장/정리 오류가 났다는 이유로 이미 발생한 위반을 세지 않는 정책을 의도했다면 봉인 전에 별도의 명시적 결정이 필요하다.

**수정 조건:** 실행 시도 목록과 주 판정에 선택할 결과를 분리한다. 모든 시도의 남아 있는 안전 증거와 해시를 보존·검사하고 알려진 하드 위반을 코호트 안전 거부에 반영한다. HOST_ERROR와 실제 controller 실패를 구별하며 성공률에는 허용된 대체 한 건만 넣는다.

**반례 테스트:** `tests/test_classify_review_299.py::test_host_retry_must_not_erase_known_safety_violation` (tilt/penetration × 941/943, strict xfail). 안전 위반이 없는 합법적인 재시도는 별도 양성 대조다.

## 정상 동작 및 분모 검증

- 기존 관련 시험 201개를 직접 실행하여 **201 passed**를 재현했다.
- 새 독립 시험은 0/60, 47/60, 48/60, 60/60, 중단된 L1 실패의 분모 유지, 주/보조 시드 누락, 임의 이름, 중복 행, 미대체 HOST_ERROR, 합법적 재시도를 다룬다.
- teacher 준비·L0·handover·L1·종료 정리의 tilt/penetration, 일반 실패와의 우선순위, 정확히 15°/5 mm 경계, null 실패, 좋은 끝점에 남은 실제 실패를 검사한다.
- 새 시험 33개는 **27 passed, 6 xfailed**. 기존 201개와 함께 실행한 결과는 **228 passed, 6 xfailed**다. xfail은 `strict=True, raises=AssertionError`여서 뜻밖의 import/입력 오류로 버그가 재현됐다고 처리하지 않는다.
- `--runxfail`로 여섯 반례만 다시 실행: **6 failed, 27 deselected**. 전부 실제 `PASS_A_B_SAFETY != FAIL_A_B_SAFETY` assertion이다. 정상 테스트 27개가 통과했다는 사실을 여섯 버그가 수정됐다는 뜻으로 읽으면 안 된다. 전체 CI 실행은 아니다.

## 공개 308건 독립 재대조

`analysis/revalidate_published.py`를 새 출력 경로에서 실행했다. 저자가 저장해 둔 새 JSON을 복사한 것이 아니라 `outputs/`의 원 `cases.jsonl`, `result.json`, trace, manifest를 다시 읽었다. 기대값은 원 README 표와도 대조했다. 16개 완료 코호트 308건의 케이스·모든 시드 배치·주 시드 911·L0·L1 통과 수가 모두 일치한다. 17개 raw의 `cases.jsonl` SHA-256도 기존 값과 같다.

| 코호트 | 케이스 수 | 연쇄 통과 | 모든 시드 통과 배치 | 주 시드 911 통과 | L0 / L1 통과 |
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

부분 tX1은 **12/14**, HOST_ERROR 2건, 배치 7곳 중 주 시드 분류 가능 6곳이다. HOST_ERROR를 일반 FAIL 또는 성공으로 바꾸지 않는다. 308건과 부분 14건을 합쳐 완료 코호트로 보고하지 않는다. 이 대조는 과거 endpoint 집계의 보존을 확인하며 새 확증 성공을 뜻하지 않는다.

## “구 코드 17개 실패” 확인

기준 SHA의 분류기를 `git show`로 메모리에 읽고, 저장 로그에 열거된 정확한 17 node ID를 직접 실행했다. 결과는 **17 failed**다. 17개를 명시 선택했으므로 저자 로그의 `67 deselected`는 이번 실행에 없다. import/호환성 오류가 아니라 `AssertionError` 또는 `DID NOT RAISE EvidenceError`로 실패한다.

- 6개: 한 행·앞/뒤 절단·중간 누락·역순·중복 trace.
- 4개: 빈/불완전/정수가 든 jaw 목록.
- 4개: inf lift, 음수 end error, 181° tilt, NaN leg error.
- 각 1개: 봉인 없는 60곳을 확증 PASS로 판정, null 뒤 실제 실패를 무시, 실제 timeout을 무시.

따라서 입력 검증/판정 변경의 실제 회귀 검사는 맞다. 다만 **17개의 서로 다른 false PASS 버그**라는 뜻은 아니다. 특히 181° tilt와 NaN leg error는 구 코드도 일반 `FAIL`을 반환하며 새 테스트는 `EvidenceError`를 요구한다. null 사례의 첫 정상 assertion은 구 코드도 통과하고, 뒤이어 추가한 non-null 실패를 거부하지 못해 해당 테스트가 실패한다. 과거 중단 patch의 cA 0/24 문제와 base 코드의 실패 무시를 구별해야 한다.

## 재현·보존·한계

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest cache 비활성. pytest는 `scripts.run_ci_tests.run_locked`로 공용 잠금을 잡은 뒤에만 실행했다. 다른 작업의 잠금·프로세스는 변경하지 않았다.

잠금 wrapper 안에서 실행할 명령:

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_ci_sharding.py \
  tests/test_chain_analysis_hard_limit.py tests/test_pair_chain_probe.py \
  tests/test_b_v6h_gain.py tests/test_classify_review_299.py

python -m pytest -q -p no:cacheprovider --runxfail \
  tests/test_classify_review_299.py \
  -k 'endpoint_hard_limit_between_trace_samples or host_retry_must_not_erase_known_safety_violation'

python experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py \
  --output /tmp/review299-published-NEW
```

로그와 전체 재분류 출력은 `/Users/changmin/projects/ugrp/outputs/review-299-astra-c86d9ba/`에 새로 보존했다. 완전한 합성 코호트도 `R1_endpoint/`, `R2_tilt_retry/`, `R2_penetration_retry/`에 남겼다. 작은 검증 기록과 해시는 [analysis/review_299_validation/](analysis/review_299_validation/)에 포함한다.

- [전체 관련 시험](analysis/review_299_validation/final_tests.txt), [xfail 해제 결과](analysis/review_299_validation/counterexamples_unmasked.txt), [실제 반례 출력·해시](analysis/review_299_validation/counterexample_summary.json).
- [구 코드 17개 실패](analysis/review_299_validation/old_code_tests.txt), [구 코드의 잘못된 수치 입력 판정](analysis/review_299_validation/old_validation_outcomes.json).
- [공개 집계 재실행 로그](analysis/review_299_validation/published_counts.txt), [17코호트 대조·raw 해시](analysis/review_299_validation/published_count_checks.json), [검증 출처와 파일 해시](analysis/review_299_validation/provenance.json).

원 실험 raw와 전체 합성 파일은 로컬 보관이며 원격 백업이 아니다. 합성 입력은 재현용 JSON이며 물리 결과가 아니다. 새 독립 시험은 위 명시 명령으로 실행했고 공용 CI 시험 목록은 변경하지 않았다.

물리/SIM/렌더·모델 호출은 **0회**다. 새 실험을 수행하거나 기존 결과를 확증으로 승격하지 않았으므로 기존 TensorBoard snapshot을 재변환하거나 viewer를 시작하지 않았다. 이 리뷰는 UI 표시·접촉 추적기 실제 감도·새 러너의 입력 계약 충족을 검증하지 않는다. UGRP 예외에 따라 Drive 작업은 없다. 수정 후 위 반례와 관련 테스트를 다시 통과시켜야 병합/봉인 준비 상태를 재검토할 수 있다.
