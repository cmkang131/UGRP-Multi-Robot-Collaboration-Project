# 성공·실패 판정과 집계 독립 감사

- 검토일: 2026-11-16 (KST).
- 기준 커밋: `ca954d9fa64f94303a3f645c265aff85e2af2fce`.
- 범위: 공개 판정·집계 코드에 정상/실패/경계/누락 합성 입력을 넣은 CPU 검사.
- 실제 물리 실행·LLM 호출·실물 실행: **0회**. 기존 실험의 raw 결과를 재채점한 기록이 아니다.
- 현재 연구 계약과 과거 실행 경로의 구분: [contract.md](contract.md).

## 결론

현재 연구의 주 지표는 계획 덮기, 보조 지표는 맞는 목적지 표식 앞에 놓기다.
동일 물체를 두 로봇이 맞잡아 옮기는 과제는 현재 연구에서 제외됐다.
최신 다로봇 실행·계획기 연결·천장 카메라 코드는 일부 미공개이므로 최신 연구
성공률 전체를 검증하지 못했다([#677](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/677)).

아래는 공개된 과거 경로에서 확인한 오류다. 기존 발표 수치가 이 오류로 인해
바뀌었다고 주장하지 않는다. 그런 결론에는 각 수치의 원본 재채점이 필요하다.

## 재현 결과와 수정

| 사례 | 기준 코드의 실제 결과 | 이번 변경 |
|---|---|---|
| 성공 1회, 결과 없이 exit2 1회, 미시작 1회 | scheduler 시도 2, 보고서 시도 1, 성공 표 1/1 | 전체 시도 1/2, 기록된 물리판정 1/1, 운영 실패·미시작을 따로 표시 ([#678](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/678)) |
| 잘린 result JSON | JSONDecodeError, 첫 batch 원장 미생성 | INVALID_RESULT로 시도 보존, 나머지 미시작. 비 UTF-8 결과도 보고 가능 |
| teacher trial ID의 condition만 act로 변경 | complete=true, act planned1/attempted2/pending−1 | 조건·장면 전체·반복이 계획과 다르면 거부. 중복 예정 ID도 거부 ([#680](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/680)) |
| 상자 snapshot의 constraints_active 누락 | constraint_free=true, success=true | 누락 거부. 명시적으로 기록한 빈 맵은 기존대로 허용 ([#681](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/681)) |
| grasp/carry/place/release 경계에서 10초 기록 누락 | 모든 gate 통과, success=true | 기존 0.15초 한도를 모든 인접 sample에 적용 ([#683](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/683)) |
| place_lower와 place_retract 역순 | success=true | 미수정. producer와 일치하는 허용 전이 명세가 필요 (#683) |
| 잠정 Pair 판정의 무한 높이·역행 시각 | success_provisional=true | 미수정. provisional 지위를 유지하고 입력 유효성 문제로 등록 ([#684](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/684)) |

물리 성공 임계값, 제어 코드, 모델, 실행 예산, 재시도 정책은 바꾸지 않았다.
누락된 물리판정을 물리 실패로 만들어 넣지 않는다. 운영 실패는 전체 시도 성공
분자에서 제외하되 원본 물리 결과와 그 가용 여부를 따로 보존한다.

### CI 후속: 고정 실행 버전 보존

최초 PR CI는 `scripts/evaluate_camera_short_transport.py`가 기존 RGB 실행
버전 v63의 소스 hash와 달라진 것을 감지해 거부했다. 이는 이번 판정 수정으로
발생한 실패이며, 기존 증거를 지키는 검사가 정상 작동한 것이다.
main과 열린 PR 전체의 사용 번호를 확인한 뒤 **v64를 새로 등록**했다.
v63과 모든 기존 번들 파일은 바이트 그대로 보존한다. v64는 부모 v63의
물리·카메라·제어 설정을 유지하고 `experimental_unqualified`로 시작한다.
174개 소스 중 변경된 pin은 판정기와 버전 등록 모듈 두 개이며 과거 성공을
새 버전으로 승계하지 않는다. [번호 확인 기록](bundle-reservation.json),
[CI 실패 원인과 후속 검증](ci-followup.md)을 남겼다.

## 정상·실패·경계·누락 확인

### Solo 판정: 32/32 기대값 일치

`harness/grasp_act_rollout.py`와 공개 평가 묶음
`solo_pipeline/harness/grasp_act_rollout.py`를 각각 검사했다(16사례씩).

- 정상 들기와 내려놓기: 통과.
- 전혀 들지 않음, 한 손가락 접촉력 부족, 과도한 기울기: 실패.
- 기존 경계 clearance=0.012 m, tilt=10°, 양쪽 0.5 N, 유지 3초: 통과.
- 유지 2.9초: 실패.
- 내려놓기 범위 양 끝 −0.005/0.006 m, 속도 0.02 m/s: 기존 조건대로 통과.
- 손가락 하중 0.1 N은 해제 조건의 엄격 부등식(`<0.1`)에 따라 실패.
- 한 번 관측된 공중 낙하는 이후 안정적으로 바닥에 놓여도 실패.
- 샘플 없음은 비성공. 0.2초 기록 간격·필수 힘 필드 누락·weld 사용은 예외로 거부.

이는 판정 함수 검사다. 문서의 개발 19/20·평가 12/12를 독립 재현한 수치가 아니다.

### 나머지 판정 probe: 24사례

[probe_outcomes.py](probe_outcomes.py)의 최종 계약에 맞춘 기대값 기준:

- 수정 전 **16/24 일치**, 수정 후 **21/24 일치**.
- 해결된 반례 5개: constraint 누락 2개, phase 경계 gap 3개.
- 남은 반례 3개: 놓기 순서 역전, provisional Pair의 Infinity, 역행 시각.
- 명시적 빈 constraint 맵과 `carry_stop→carry` 재개는 허용된 사례다.
  초기 조사 중 이 둘을 오류 후보로 보았으나 계약/producer 확인 후 제외했다.
- 소수점 비교는 기존 허용 오차를 그대로 사용했다. .15초 gap 통과와
  .150001초 거부는 별도 회귀검사로 확인했다.

원본 함수 출력을 그대로 보존한 `outcomes-*.stdout.txt`에는 의도적으로 넣은
비유한 값의 Python JSON 표기 `Infinity`가 있다. 엄격 JSON 자료는
[summary.json](summary.json)이며, 여기에는 비유한 값을 넣지 않았다.

## 분모·중단·재시도 추적

경로별 정책이 다르므로 하나의 성공률로 합치면 안 된다.

| 공개 경로 | 분모·누락·중단 | 재시도와 제한 |
|---|---|---|
| `rgb_communication_evaluation.evaluate_manifest` | 고정 manifest의 모든 계획 행. failure/timeout/api_error/aborted/unrun/missing_artifact/invalid_artifact 별도 | automatic_retry=false. 성공 시간만 따로 success-only로 표시 |
| `warehouse_evaluation.EvaluationLedger` | 모든 condition×seed×scenario 칸. missing 별도. paired 분석은 실제 양쪽 결과가 있는 쌍과 예정 쌍 수를 각각 표시 | 같은 셀의 중복 결과 거부 |
| `zone_study_eval.summarise` | 전달된 모든 trial. 실패·시간/예산 상한·중단 유지, 기본 PAR-2 시간 벌점 | 이 함수는 예정 manifest를 받지 않으므로 전달되지 않은 시행은 스스로 찾지 못함 |
| `zone_study_evidence_join` | frozen admitted trial 전체, INVALID 포함 | logical trial/run 중복 거부. 사전 선택된 attempt를 쓰며 best-of-retries를 허용하지 않음 |
| `carry_failure_metrics.aggregate` | 전체 실패율은 attempted, pending 별도. 조건부 carry 분모는 carry 진입 후 다른 구성요소 실패로 관측이 중단되지 않은 실행 | 동일 trial_id 중복 거부. 이번 수정으로 메타데이터 불일치도 거부 |
| `evaluate_gemini_cohort` + report | 전체 시도와 기록된 물리판정 분모를 따로 표시. 운영 오류/미시작/진행 중 구분 | 자동 재시도 없음. 진행 중을 종료 실패로 세지 않음 |
| `zone_study_llm_driver.run_attempts` | 각 attempt를 `#a1`, `#a2`로 보존 | 첫 모델 요청 전 HOST_ERROR만 최대 한 번 재시도. 첫 요청 후/API/정책 실패는 재시도 금지 |

새 Gemini 보고서는 scheduler가 종료 근거(returncode 또는 infrastructure_problem)를
남긴 attempt를 사용한다. scheduler 자체가 첫 checkpoint 전에 죽어 원장을 전혀
남기지 못한 실행의 종료 여부를 추측해서 채우지는 않는다. 해당 한계는 최신
시도 원장 규약을 요구하는 #677에도 반영했다.

## 실행 명령과 실제 결과

Python 3.12.14, Linux x86_64. 최종 검증 환경은 requirements-test.txt와
MuJoCo 3.12.0 / GLFW 2.10.2를 설치했다. MuJoCo는 기존 보고서 테스트의
import 때문에 필요했고 물리 실행에는 사용하지 않았다. 초기 검사 때 시스템
pytest 및 MuJoCo 누락으로 각각 1회 실행/수집이 실패했고, 의존성 준비 후 통과했다.

```sh
python -m venv .venv-test
.venv-test/bin/python -m pip install -r requirements-test.txt mujoco==3.12.0 glfw==2.10.2

.venv-test/bin/python -m pytest -q \
  tests/test_gemini_cohort.py tests/test_visual_team_report.py \
  tests/test_carry_failure_measurement.py tests/test_matched_carry_shards.py \
  tests/test_research_cohort_admission.py \
  tests/test_visual_box_evaluation.py tests/test_camera_short_transport_evaluation.py
```

실제 최종 출력: **80 passed, 10 subtests passed in 1.05s**.
원문은 [focused-tests.txt](focused-tests.txt).

carry identity 회귀검사는 수정 전에 **6 failed, 1 passed**를 확인하고 수정했다.
원문: [identity-regressions-before.txt](identity-regressions-before.txt).

```sh
.venv-test/bin/python experiments/2026-11-16-outcome-accounting-audit/probe_solo.py
.venv-test/bin/python experiments/2026-11-16-outcome-accounting-audit/probe_outcomes.py
.venv-test/bin/python experiments/2026-11-16-outcome-accounting-audit/probe_aggregation.py
git diff --check
```

수정 전/후 출력은 이 디렉터리의 `*-before*` / `*-after*` 파일로 보존했다.
probe 스크립트는 호출한 체크아웃의 구현을 사용하므로 기준 커밋으로 재현하려면
별도의 기준 체크아웃에 스크립트만 같은 상대 경로로 복사해 실행한다.
현재 후보에서는 미수정 반례 3개가 계속 재현되는 것이 예상 결과다.

비수정 분모/retry 경로도 아래 선택 검사 15개가 통과했다.

```sh
.venv-test/bin/python -m pytest -q tests/test_rgb_communication_evaluation.py \
  -k 'all_planned_outcomes or absent_directory or duplicate_schedule'
# 3 passed, 24 deselected
.venv-test/bin/python -m pytest -q tests/test_zone_study_eval.py \
  -k 'failures_stay_in_the_denominators or fast_failure_never_beats_slow_success or success_after_horizon_is_refused'
# 3 passed, 68 deselected
.venv-test/bin/python -m pytest -q tests/test_warehouse_evaluation.py
# 5 passed
.venv-test/bin/python -m pytest -q tests/test_zone_study_llm_driver.py \
  -k 'host_error_before_first_request_is_retried_once_and_both_attempts_are_kept or no_retry_after_first_request_or_for_non_host_errors'
# 4 passed, 173 deselected
```

## 검토와 증거 무결성

문서 계약, 개별 판정, 결과 집계를 나누어 읽고 별도의 검토자가 패치를 검토했다.
검토에서 발견한 비 UTF-8 결과 처리 누락을 보완해 코호트→보고서 통합 검사에 넣었다.
진행 중인 실행을 종료 실패로 세지 않으며, raw success와 process exit가 충돌할 때
원본은 보존하고 counted_success만 false로 하는 것도 확인했다.

[summary.json](summary.json)은 환경, 기준/수정 소스 SHA-256, 검사별 분모와
미검증 범위를 담는다. [checksums.json](checksums.json)은 이 기록의 파일 해시다.
수정 전 반례 분포는 [rejection_table.json](rejection_table.json)에 보존했다.

오류 처리는 Python 표준 JSON 예외 규약과 저장소에 이미 있던 shard identity
검사를 재사용했다. 참고: [Python JSON](https://docs.python.org/3.12/library/json.html),
[pytest 매개변수 검사](https://docs.pytest.org/en/stable/example/parametrize.html).
