# PR #519 고정 카탈로그 복구

수정 전 HEAD: `13f50f31a40f2e87e3964137c8c2d6d3075ba4e1`.
CI run: `38719107552`. 코드 수정 전에 실패 사유를 집계했다.

| 사유 범주 | 실패 시험 수 | 대상 파일 | 최소 틈 |
|---|---:|---|---|
| frozen_bytes_changed | 2 | `configs/simulation_workflows.json` | 해당 없음: CI 바이트 보존 검사 |
| upstream_job_failed | 1 집계 job | 위 두 shard에 의존하는 `offline-regressions` | 해당 없음 |

- shard 0/8: `test_consumer_criterion_b_v91.py::test_frozen_files_registrations_and_handoff_prefix_are_byte_identical`.
- shard 3/8: `test_zone_final_pair_loaded.py::test_schedule_archive_and_preserved_sources`.
  이 시험은 schedule 바이트·길이·SHA-256·JSON 동등성 검사를 통과한 뒤
  preserved source의 카탈로그 SHA에서 실패했다. schedule 재생성은 필요 없다.
- 원본 CI 로그와 SHA-256: `outputs/scenv7fix/ci-failures.json`.
  로컬 원본 위치이며 별도 원격 백업 완료를 뜻하지 않는다.

## 기존 등록 방식과 수정 범위

- v5 추가 `1788a95b81384b7d714447fd8943b50e524f382a` (#498)와
  v6 추가 `84653e15520ab0cb33ba5c08ab513058a0958858` (#503)는
  버전별 `configs/zone_study_scenarios_vN/`와 기존 시나리오 로더로 등록했다.
  두 커밋 모두 `configs/simulation_workflows.json`의 SHA-256은
  `fc5bdf913a9f672bb3adb9597e1925b88a163a7ce1a1b30fb4fed9cf7ad0c813`이다.
- v7도 같은 등록 경로가 이미 연결되어 있다. 기존 workflow의 runner·ID·버전을
  바꾸는 작업이 아니므로 새 workflow fragment는 필요 없다.
- v7 소개를 넣으며 바뀐 고정 카탈로그 한 줄만 부모 커밋의 원본 바이트로 복구한다.
  frozen 해시·preservation 기록·schedule·시험 기대값은 바꾸지 않는다.
- 별도 workflow를 추가할 때 쓰는 기존 확장 지점은
  `sim/workflow_manager.py::catalog()`의 `configs/simulation_workflows.d/*.json`이다.
  기존 workflow ID를 덮어쓸 수 없으며 이 수정에서는 새 workflow를 만들지 않는다.

## 재현과 검증 범위

```sh
gh run view --job 116369909906 --log-failed
gh run view --job 116369909932 --log-failed
git show 1788a95b --stat
git show 84653e15 --stat
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_consumer_criterion_b_v91.py tests/test_zone_final_pair_loaded.py \
  --junitxml=outputs/scenv7fix/pytest.xml
```

로컬 검증은 위 실패 시험 파일 두 개만 실행한다. 실행 결과는
`scenv7fix-summary.json`에 기록한다. 시뮬레이션·렌더·모델 호출·실험 대기열은 없다.
계획기·수용 상수·시나리오 화물·물리 동작은 바꾸지 않는다.

결과: **111 passed / 실패·오류·skip 0 / 149.86초**. 문제였던 고정 바이트
검사 두 건과 같은 파일의 나머지 회귀 검사가 모두 통과했다.

| 관문 (단위: 로컬 pytest 시험) | 입력 | 누적 통과 | 거부 |
|---|---:|---:|---:|
| 수집 | 111 | 111 | 0 |
| 실행·판정 | 111 | 111 | 0 |

원본은 `outputs/scenv7fix/pytest.xml`과 `pytest.log`, 재현 명령은 위와 같다.
새 원격 CI 결과는 아직 확인하지 않았으며 로컬 검증과 구분한다.
