# #299 안전 분류 수정 검증 (2026-09-30)

검토 코드 `c86d9bac62036904ecc641db5e59e79edb58dec2`, 독립 검토/시험 `de16cbc96becf19755f09197b9ef139609f00fe9`. 새 소스/시험의 정확한 파일 SHA-256과 17개 회귀 node ID는 [provenance.json](provenance.json)에 있다. 물리/SIM step/렌더/외부 모델 호출은 0회다.

| 검사 | 결과 | 파일 |
|---|---|---|
| 관련 6개 시험 파일 | **260 passed**, xfail/skip 0 (기존 201 + 독립 33 + 추가 26) | [related_tests.txt](related_tests.txt) |
| 기존 구 코드 회귀 17개를 현재 코드에서 명시 선택 | **17 passed**; 위 260의 부분집합 | [old_regressions_current.txt](old_regressions_current.txt) |
| 검토 대상 코드의 R1/R2 | **6 failed, 53 deselected**, 실제 assertion 실패 | [reviewed_counterexamples.txt](reviewed_counterexamples.txt), [메모리 전용 loader](reviewed_code_loader.py) |
| 수정 코드의 같은 6개 반례 | 모두 **FAIL_A_B_SAFETY**, 위반 시도 각 1 | [counterexample_summary.json](counterexample_summary.json) |
| 공개 16개 완료 코호트 308건 + 부분 tX1 | 모든 케이스/배치/주 시드/L0/L1/하드 집계와 17개 cases.jsonl 해시 일치 | [published_counts.txt](published_counts.txt), [published_count_checks.json](published_count_checks.json) |
| 첫 실행의 추가 경계 테스트 기대값 오류 | 259 passed, 1 failed; 일반 leg 10°와 하드 15°를 혼동한 테스트를 수정 후 전체 재실행 | [initial_test_expectation_failure.txt](initial_test_expectation_failure.txt) |

R1은 L0/L1 끝점 16°를 넣은 경우 모두 59/60, 선택 72건, 하드 위반 1이다. R2는 기울기/관통 × 941/943 모두 60/60, 선택 72건/실제 73시도, 하드 위반 1이다. 재시도 원본의 result/trace도 input_sha256에 남긴다. cA/cB는 각 24/24, tX1은 12/14 + HOST_ERROR 2건이며 tX1을 완료 308건에 합치지 않는다.

기존 Mac venv, `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest cache 비활성. `scripts.run_ci_tests.run_locked`로 잠금을 획득한 뒤에만 검증 드라이버를 실행했으며 종료 뒤 잠금을 반환했다. 초기 잠금 대기 기록은 로컬 출력 루트에 보존했다. 전체 로컬 CI는 실행하지 않았다.

잠금 wrapper 안에서 실행한 pytest 대상:

```sh
python -m pytest -q -p no:cacheprovider \
  tests/test_v6h_classify_placements.py tests/test_ci_sharding.py \
  tests/test_chain_analysis_hard_limit.py tests/test_pair_chain_probe.py \
  tests/test_b_v6h_gain.py tests/test_classify_review_299.py
```

검토 코드 재현은 이 폴더를 PYTHONPATH에 더하고 위 명령 대신 다음을 실행한다(종료 코드 1/6개 assertion 실패가 기대 결과다). 소스 파일을 덮어쓰지 않는다.

```sh
python -m pytest -q -p no:cacheprovider -p reviewed_code_loader \
  tests/test_classify_review_299.py \
  -k 'endpoint_hard_limit_between_trace_samples_must_veto_cohort or host_retry_must_not_erase_known_safety_violation'
```

공개 집계 재대조는 같은 잠금 아래 기존 raw를 읽고 새 폴더에 썼다.

```sh
python experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py \
  --output /Users/changmin/projects/ugrp/outputs/v6h-fixcls-review299-20260930/final/published
```

재실행할 때 output은 존재하지 않는 새 경로를 사용한다. 전체 명령 드라이버·합성 fixture·전체 재분류 JSON은 `/Users/changmin/projects/ugrp/outputs/v6h-fixcls-review299-20260930/final/`에 있다. 이 폴더에는 작은 검증 기록과 해시만 넣었다. 원 raw의 원격 백업이나 새 확증 결과가 아니며 기존 TensorBoard snapshot을 재변환/재표시하지 않았다. 독립 재검토·실제 러너 계약 검증·봉인/등록 인수는 별도다.

Git에 넣은 두 실패 로그 사본은 줄 끝 공백만 정리했다. 로컬 원 로그는 그대로이며 원본/사본 SHA-256을 provenance.json에 함께 기록했다.
