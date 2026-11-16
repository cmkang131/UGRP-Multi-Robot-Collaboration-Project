# PR #293 D1 독립 검토 응답 — 2026-09-30

검토 원문: `origin/codex/review-293-294`의
`experiments/2026-09-30-pair-v6h-carry/REVIEW_294_293_astra.md` 중 #293 부분.
검토 브랜치 SHA `26b300b954fcb0079616a05a0ff094b851790b56`, 검토된 D1 SHA
`8ae2237ffbc72e0bcff382654f75d63bc4f3203d`다. 수정은 같은 `codex/stall-d1-prereg`에서 했다.
**DRAFT 유지. 봉인·병합·확증 실행 없음.** 물리/SIM/렌더 실행·모델 호출·제어기 수정은 없다.

| 지적 | 재현 Y/N | 재현 근거와 최소 수정(현재 file:line) | 검사 이름 또는 반박 근거 |
|---|---|---|---|
| #4 BLOCKER: 주 분모 30건/5종과 최소 24건/4종 충돌 | Y | 기존 수용표의 `≥24/≥4`와 본문의 30건이 충돌해 문서 회귀 검사가 실패했다. `PREREG_DRAFT.md:69`, `:75`, `:131`에서 정확히 5종 각 6건을 요구하고 미달은 불완료(INCOMPLETE), 통과 불가로 고쳤다. 같은 기전의 고정 예비 순서만 허용한다. 평가의 개수 관문은 `d1_evaluation.py:16`이다. | `test_preregistration_requires_exact_30_and_predata_freeze`, `test_cohort_count_gate_requires_all_five_kinds_and_exact_30`. 24건/4종으로 완화한 변이를 검출했다. 반박 없음. |
| #7 MAJOR: 회복 뒤 경보가 정체 검출로 계산될 수 있음 | Y | 기존 문서에는 사건 종료와 매칭 검사기가 없었다. GT 창 [4,5)가 STALL이고 6.4 s에 첫 경보가 나면 시작 이후라는 규칙만으로 지연 2.4 s의 TP가 가능했다. `PREREG_DRAFT.md:102`에서 OTHER/MOVING이 사건을 닫고 같은 STALL 창의 경보만 매칭하도록 정했다. `d1_evaluation.py:48`의 별도 평가에서 회복 뒤 경보는 FP, 사건은 누락이다. 선행 FP·후속 사건·반복 경보·고정 관측/창 분모도 보존한다. | `test_alarm_after_recovery_is_false_alarm_not_detection`, `test_other_closes_event_and_later_event_cannot_rescue_first_miss`, `test_early_false_alarm_is_retained_when_later_alarm_matches_event`. 종료를 무시하는 변이도 검출했다. 반박 없음. |
| #8 MAJOR: 시각 지터에서 유효 검사율 <95%인데 EVALUATED | Y | 점수를 항상 유효하게 고정하고 시각만 변형해 아래 6개 비율을 재현했다. 모두 기존 상태가 EVALUATED였다. `d1_detector.py:85`, `:224`에서 기준 이후 전체 예정 검사를 분모로 사용하고 부족하면 관측 실패(INSUFFICIENT_COVERAGE)를 반환한다. 인과적 경보는 그대로 보존한다. `d1_evaluation.py:64`는 관측 실패의 경보를 TP로 쓰지 않는다. `PREREG_DRAFT.md:120`, `:135`, `:159`에서 모든 잡음 조합/시드에 95%를 요구하고 적용 한계·실패를 명시했다. | `test_timestamp_jitter_below_95_percent_is_observation_failure` 6조건, `test_exact_95_percent_boundary_keeps_all_scheduled_checks`, `test_missing_images_remain_in_moving_denominator_and_block_zero_alarm_pass`, `test_coverage_failure_keeps_raw_alarm_but_scores_stall_as_miss`. 95%→80% 완화 변이를 검출했다. 반박 없음. |
| 추가 논점: 탐색 자료를 보고 설정을 골랐으며 잡음 하위 범위 선택도 막아야 함 | Y | 기존 탐색 후 선택 고지를 확인했다. `PREREG_DRAFT.md:13`, `:41`, `:135`, `:137`에서 주 (0.4,2), 보조 (0.5,3), 전체 12조합/3 RNG를 고정하고 사후 설정/잡음 범위 선택을 금지했다. 별도 사전 제한 범위 가설은 없으며 보조·하위 범위 결과가 주 실패를 구제하지 않는다. `STAGING_PLAN.md:66`에도 같은 순서를 반영했다. | `test_preregistration_requires_exact_30_and_predata_freeze`, `test_primary_secondary_order_and_statistics_are_rederived`. 사후 선택 금지 문구를 없앤 변이를 검출했다. 반박 없음. |

## 재현과 회귀 검사

수정 전 새 검사 8개가 실패했다: 시각 지터 상태 6개, 분모/동결 문서 1개,
회복 뒤 경보 채점 1개(기존에는 평가 모듈 자체가 없음). 이는 정적 반례/검사 공백의 재현이다.
수정 후 관련 테스트 **120/120 통과: D1 54개 + CI 분할 66개**다.
`review_mutations.py`는 메모리 안에서만 5개 변이(24/4 허용, 회복 무시,
95%→80%, INCOMPLETE 삭제, 사후 선택 금지 삭제)를 만들고 기존 회귀 검사를 직접 호출했다.
**5/5 변이 검출**, 파일을 바꾸지 않았다.

기존 Mac Python/NumPy/pytest 환경을 재사용하고 OMP/BLAS/MKL을 1로 제한했다.
처음 잠금 상태는 null이었고, 각 검사 묶음은 `run_ci_tests.run_locked`로 빈 잠금을
짧게 획득·반환했다. 다른 작업의 잠금/프로세스에는 손대지 않았다. 실행 명령은 다음과 같다.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PY'
import os, sys
from scripts.run_ci_tests import local_lock_root, run_locked
cmd = [sys.executable, '-m', 'pytest', '-q',
       'tests/test_stall_detector_d1.py', 'tests/test_ci_sharding.py',
       '-p', 'no:cacheprovider']
code = run_locked(cmd, dict(os.environ), local_lock_root())
if code:
    raise SystemExit(code)
cmd = [sys.executable, 'experiments/2026-09-30-stall-detector-d1/review_mutations.py']
raise SystemExit(run_locked(cmd, dict(os.environ), local_lock_root()))
PY
```

점수 1로 고정한 시각 지터 반례는 다음과 같다. 노출 배율/읽기 잡음을 넣지 않았으며,
검토자가 지적한 원인은 **시각 지터와 동시 시각 제거**다. 검출 성능이나 새 물리 자료가 아니다.

| 명령 길이 / 기준 이후 전체 검사 | RNG 93001 | RNG 93002 | RNG 93003 |
|---|---|---|---|
| 60 s / 284 | 223/284 = 78.52% | 224/284 = 78.87% | 231/284 = 81.34% |
| 90 s / 434 | 349/434 = 80.41% | 341/434 = 78.57% | 350/434 = 80.65% |

## 통계 재계산과 남은 문제

프로젝트 통계 함수를 호출하지 않고 `statistics.NormalDist().inv_cdf(.975)`와
문서의 Wilson 식을 직접 계산했다. 양측 95% 하한은 **22/24: 74.1512%,
27/30: 74.3789%, 24/30: 62.6943%**다. 22/24는 비교 수치이며 이번 주 분모를 뜻하지 않는다.
시작부터 막힌 6건을 모두 놓치면 감도는 **24/30=80%**로 전체 90%와 하한 70%를 모두 실패한다.
0/60의 단측 정확 상한은 직접 계산한 `1-.05**(1/60)` = **4.870291%**다.
이 식과 반례 분모는 테스트에서 다시 계산하며 기계 판독값/환경/파일 해시는
[review_verification.json](review_verification.json)에 보존한다. 최초 verification.json은 그대로 남겼다.

규칙 공백은 고쳤지만 **시작 정체와 시각 지터의 알려진 실패는 해결하지 않았다**.
새 30/60 manifest·동일 기전 예비 셀·독립성, 실제 staging 지원, GT 창 라벨/목표 사건/두 로봇
집계 adapter, 고정 관측 길이와 코드/환경 해시, 독립 재검토·후속 실행 승인이 남아 있다.
개수 관문은 독립성·조작 성립을 입증하지 않고, 창 채점기는 GT를 만들거나 두 로봇 케이스를 집계하지 않는다.
전체 CI·원본 영상 재생·확증·실물·안전·E2E는 검증하지 않았다. 단위 검사 결과이므로
TensorBoard snapshot/서버/새 코호트 결과를 만들지 않았으며 Drive도 사용하지 않았다.

조정자에게 확인할 것: 고정 30/60·12조합의 실패 가능성을 유지한 결과 수집 목적,
staging/GT adapter와 manifest 담당자, 수정본 독립 재검토 담당자를 정해 달라.
