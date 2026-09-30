# #299b 독립 검증 기록

고정 소스 `8a1631b9cf6f9d658961fcb80339539e87541d3d`, 리뷰 브랜치 `codex/review-299b`. 판정과 재현 입력 설명은 [REVIEW_299b_astra.md](../../REVIEW_299b_astra.md)에 있다. 분류기·기존 시험·공개 숫자·원 raw를 수정하지 않았다.

| 직접 실행한 검사 | 결과 | 기록 |
|---|---|---|
| 기존 관련 6개 시험 파일 | 260 passed | [baseline_tests.txt](baseline_tests.txt) |
| 새 13종/58개 반례 시험 첫 실행 | 40 passed, 18 failed | [initial_new_tests.txt](initial_new_tests.txt) |
| 기존 + 최종 새 시험 | **300 passed, 18 xfailed** | [final_tests.txt](final_tests.txt) |
| strict xfail 해제 | **18 failed, 40 deselected**; 전부 AssertionError | [counterexamples_unmasked.txt](counterexamples_unmasked.txt) |
| 16개 완료 코호트 + 부분 tX1 재분류 | 완료 308건의 공개 집계, 17개 cases.jsonl 해시 일치; tX1 12/14 + HOST_ERROR 2건 | [published_counts.txt](published_counts.txt), [전체 파일 해시](published_count_checks.json) |
| 수치·배치 파일 재현 | sizing/placements `--check` 종료 0 | [sizing_check.txt](sizing_check.txt), [명령/종료 코드](validation_commands.json) |
| 원 probe case 해시·좌표 검사 | 29구성 / 26좌표 / 20근접 묶음 | [probe_dependence.json](probe_dependence.json) |
| 대표 6개 반례 전체 분석 | 예상한 잘못된 출력 재현; 13 FAIL 대조는 47/60, HOST 정리+재시도 후 60/60 | [작은 반례 요약](counterexample_summary.json) |

실제 결함 세 군에만 `strict=True, raises=AssertionError` xfail을 붙였다. 18개 변형 중 14개는 잘못된 전체 PASS이며 4개는 알려진 안전 위반이 NOT_EVALUABLE로 축소된다. 이를 서로 다른 버그 18개 또는 수정 완료로 해석하지 않는다. 초기 시험에서 기대값을 변경하지 않았다. 최종 시험에는 xfail 이유와 혼합 실패 예제의 47/60 대조 assertion을 추가했다.

실행 환경은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`, `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest cache 비활성이다. 검증 드라이버는 모두 `scripts.run_ci_tests.run_locked`로 공용 잠금을 획득한 뒤 실행했다. 다른 작업의 잠금이 있을 때는 시작하지 않고 기다렸으며 다른 프로세스를 종료하지 않았다. 자기 프로세스 그룹 정리 뒤 잠금을 반환했다. 전체 로컬 CI나 GitHub CI 완료를 주장하지 않는다.

로컬 보존 루트는 `/Users/changmin/projects/ugrp/outputs/review-299b-astra-8a1631b9/`다.

- `published/`: 17개 전체 재분류 JSON 및 파일별 입력 해시.
- `baseline-fixtures/`, `initial-new-fixtures/`, `final-fixtures/`, `unmasked-fixtures/`: 각 시험 실행의 합성 입력. 기존 경로를 재사용하거나 덮어쓰지 않았다.
- `examples/`: 이름을 붙인 6개 대표 반례, 전체 raw와 `report.json`. Git에는 해당 결과 해시·변형 원본 행·원본/재시도 파일 해시를 작은 요약에 남겼다.
- `run_review299b.py`, `review299b_validation.py`, `review299b_countercheck.py`, `review299b_examples.py`: 실제 실행한 드라이버 사본.
- `counterexamples_unmasked.xml`, `initial_test_source.py`, 원 stdout: xfail 해제의 실패 종류와 최초 시험 버전을 보존한다.

[provenance.json](provenance.json)은 소스/시험 SHA-256, 정확한 실패 node ID, 원 로그와 Git 사본 해시를 담는다. Git의 TXT 사본은 줄 끝 공백만 제거했다. 원 로그는 수정하지 않았다. 원본과 전체 합성 입력은 로컬 보관이며 원격 전체 백업이 아니다. 새 물리·학습 결과가 없는 코드 검토이므로 TensorBoard snapshot 재변환/서버 시작은 하지 않았고, UGRP 예외에 따라 Drive 작업도 없다. 물리/SIM step/렌더/모델 호출은 0회다.
