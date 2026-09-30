# P06 검증 기록

최종 선별 회귀: **203 passed, 0 failed, 0 errors, 0 skipped** (pytest 표시 13.00초).
이 시간은 테스트 실행 시간이며 로봇/학습 성능 측정이 아니다.

## 환경과 실행 경계

- Python 3.12.13, macOS 27.2 arm64, pytest 9.1.1, TensorBoard 2.21.0, Pillow 12.3.0.
- 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python` 재사용. 설치 없음.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`,
  `MKL_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1`, `PYTHONPATH=<자기 worktree>`.
- `scripts.run_ci_tests.run_locked`로 `/Users/changmin/projects/ugrp/outputs/agent-locks`
  공용 잠금을 획득한 다음에만 pytest를 시작했다. 점유 중에는 pytest 미시작(exit 3),
  유한 대기(최대 300초) 후 재시도했다. 다른 작업의 잠금·프로세스는 조작하지 않았다.
- 아래 테스트의 import/fixture/call 경로를 읽었다. 평가/변환은 순수 JSON/NumPy/fake
  입력이며 모델 wire는 fixture다. `referee_truth`의 MuJoCo 모듈은 통째로 fake로 대체한다.
  새 테스트에는 world/physical runner/TOP 적용 함수 호출을 거절하는 guard가 있다.
- 기존 exporter의 media HTTP 테스트는 임시 파일을 loopback 임시 포트로 읽고 finally에서
  종료한다. 모델 네트워크나 대시보드 서버가 아니다. 새 테스트는 미디어 등록만 검사한다.

## 선별 목록

파일 전체가 순수 synthetic/offline임을 확인한 대상:

- `tests/test_zone_study_evidence.py`
- `tests/test_zone_study_eval.py`
- `tests/test_tensorboard_export.py`

`tests/test_zone_study_referee.py`는 **전체 파일을 실행하지 않았다**. 다음 node만 선택했다.

```text
test_landing_extents_not_the_centre_decide
test_completion_only_stops_the_episode_and_never_reaches_a_robot
test_a_run_without_a_referee_still_writes_a_not_evaluated_trial_record
test_orders_complete_only_when_every_order_is_filled_and_success_comes_from_the_referee
test_departure_undoes_a_delivery_but_a_bump_or_a_brief_touch_does_not
test_a_corrected_misdelivery_keeps_its_history_and_is_delivered_once
test_lifted_moving_or_held_items_are_never_delivered
test_corrupted_truth_rows_are_refused_not_judged
test_failure_is_charged_twice_the_horizon_with_partial_delivery_rate
```

직접 의존하는 지표/기존 미상 usage 회귀도 다음 node만 선택했다.

```text
tests/test_zone_study_review_fixes.py::test_r2_f10_a_missing_cost_source_stays_none_in_the_final_metrics
tests/test_zone_study_review_fixes.py::test_r2_f11_a_misdelivered_fungible_item_does_not_consume_the_quantity
tests/test_zone_study_review_fixes.py::test_r4_f16_the_tensorboard_event_files_carry_the_unknown_marker
tests/test_zone_study_review_r5.py::test_r5_p2_a_summary_only_unknown_usage_stays_a_lower_bound
```

실행 API는 다음과 같고, `selectors`는 위 세 파일과 명시한 `파일::node` 목록이다.
목록을 전체 회귀 스위트나 물리 probe로 대체하지 않는다.

```python
from scripts.run_ci_tests import run_locked
from scripts.agent_lock import DEFAULT_ROOT
run_locked([python, '-m', 'pytest', '-q', *selectors, '--tb=short',
            '--junitxml=/tmp/p06-verified-junit.xml'], env, DEFAULT_ROOT)
```

## 결과와 실패 이력

- 첫 실행: 112 passed, 2 failed. 기존 비교 fixture가 800초 종료 시행에 850초 배송을
  넣어 성공을 기대했다. 비교 목적에 맞게 fixture의 배송 시각만 조정했고, 늦은 배송을
  거절하는 P06 반례를 별도로 유지했다.
- 확대 선별 실행: 202 passed, 1 failed. 새 JSON 전용 fixture의 `record_complete=false`가
  trial에만 있어 manifest/result 일치 검사에서 거절됐다. 두 envelope도 일치시켰다.
- 해당 fixture 재검사: 1 passed. 이후 중단 기록의 하한 처리와 시작 전 scenario ID 보존을
  보완한 최종 소스로 동일 선별 목록 203개를 다시 실행해 모두 통과했다. 앞선 통과 수를 중복 합산하지 않는다.
- 정적 검사: `git diff --check`, 변경 Python 파일의 `py_compile`.

fake raw/event는 pytest 임시 폴더에만 있다. JUnit 역시 `/tmp`의 로컬 검사 기록이며
원격 raw 백업이 아니다. 이 문서의 코호트 분모 사례는 가짜 6개 terminal 상태에 대한
계약 검사다. 실제 실험 성공률로 보고하지 않는다.

## 판정 범위와 후속

검사 대상은 전체 발자국/회전·높이·선속도·held·정착 시간, ID join·중복·늦은 확인,
네 조건의 payload/request/wake 불변성, terminal 분모·cap·모델 비용/토큰 하한·미상 값,
모든 raw/request 이미지 해시, 변조/누락/변환 중 변경/일반 exporter 우회 거절,
실제 event scalar·HParams protobuf readback, TOP 설정과 typed 영상 등록 분리다.

**미검증:** MuJoCo/실물의 실제 정착·외란·종료, 실제 모델/과금, 실행 중 ENOSPC에서의
디스크 복구, 강제 kill 후 기록 회수, 실제 TOP 촬영/동영상 디코딩·재생, 공용 snapshot,
공용 logdir/브라우저 pin/HParams UI. 화면 완료·실제 E2E 완료·S11/S14 전체 완료를 주장하지 않는다.

## 최종 검사 산출물

- JUnit: `/tmp/p06-verified-junit.xml` (로컬 임시 기록).
- JUnit SHA-256: `d20dbda82ba52e6c5e543c2c1224c67d1fe653fff4591b68cc581050e01ee844`.
- 실제 검사 소스 해시: [source_files.sha256](source_files.sha256).

| 테스트 모듈 | 통과 |
|---|---:|
| `tests.test_tensorboard_export` | 58 |
| `tests.test_zone_study_eval` | 71 |
| `tests.test_zone_study_evidence` | 47 |
| `tests.test_zone_study_referee` | 23 |
| `tests.test_zone_study_review_fixes` | 3 |
| `tests.test_zone_study_review_r5` | 1 |

마지막 자기 잠금: PID `49586`, acquired `1790767109.571269`, released `1790767122.730836`. 종료 후 자기 자식 정리가 확인되어 잠금이 반환됐다. 다른 작업의 이후 잠금은 변경하지 않았다.
