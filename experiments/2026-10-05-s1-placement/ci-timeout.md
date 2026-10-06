# PR #392 CI 시간 기록 보완 (2026-10-06)

측정 소스: `354b07079d383549806014b3e2644b384562d448`, `codex/s1-placement`.
오프라인 시험과 CI 배정 기록이며 연구·학습·물리 성능 결과가 아니다.
시뮬레이션·MuJoCo 실행·렌더·실제 모델 호출 없이 pytest 한 프로세스씩 실행했다.
PR은 DRAFT를 유지하며 병합하지 않는다.

## 원인

- [실패 run 37325463100](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37325463100),
  job `112047990148`: shard 3이 25m19s 뒤 취소됐다. pytest는 90%까지 진행했지만
  종료 전 취소되어 JUnit이 없었다. 나머지 7개 shard의 JUnit은 회수했다.
- `run_ci_tests.shard_test_files`는 긴 파일부터 최소 누적 비용 shard에 배정한다.
  현재 CI 목록 464개 중 32개의 기록이 없어 각각 중앙값 0.61초로 계산됐다.
  shard 3은 77개 파일, 예측 비용 886.09초였고 아래 4개가 누락됐다.
  `test_highpose_arrival_confirm.py`, `test_highpose_host_clock.py`,
  `test_highpose_refix_hooks.py`, `test_zone_final_pair_new_starts.py`.
  이 shard에는 기존 `test_v6h_classifier_properties.py`(327.78초),
  `test_review_352.py`(131.68초) 등도 배정됐다. 전체 목록은 로컬 기록에 보존했다.
- S1의 새 `test_zone_scenario_scene.py`는 shard 5에 배정됐다. S1 커밋은
  #371 수정 `933e88031e1064c95663ce04f8bd508c494a70f4`보다 약 6분 앞서며
  해당 시간 기록 수정을 포함하지 않았다.

## 측정·수정

`scripts/refresh_ci_durations.py`로 회수한 7개 CI JUnit과 로컬 JUnit의
파일별 testcase 합계·실행 간 최댓값을 임시 JSON에 생성했다. 공유 JSON에는
누락 32개와 기존 비용이 50% 이상·5초 이상 작았던 calibration 1개만 반영했다.
로컬 값에는 1.5배 여유를 적용하고 동일 시험 소스의 #371 기록을 하한으로 유지했다.
두 alias 시험의 원본 경로로 귀속되는 JUnit 비용은 alias의 #371 기록을 재사용했다.
alias와 가져온 시험 파일이 #371 측정 커밋과 동일함을 Git blob으로 확인했다.
다른 기존 키의 값·순서·공백 형식은 보존 검사를 통과했다.

| 시험 파일 (`tests/` 생략) | 로컬 JUnit 합계(초) | 저장값(초) |
|---|---:|---:|
| test_highpose_arrival_confirm.py | 31.670 | 48.71 |
| test_highpose_host_clock.py | 2.689 | 4.07 |
| test_highpose_refix_hooks.py | 145.549 | 219.67 |
| test_zone_final_pair_new_starts.py | 42.429 | 70.16 |
| test_zone_scenario_scene.py | 0.745 | 1.12 |

`test_final_environment_gain_calibration_v101.py`: 65.70 → 101.58초(CI 관측값).
모든 갱신 값·출처는 `configs/ci_test_durations.json`과 로컬 receipt에 보존했다.
갱신 후 누락 0/464개, shard 예상 합계는 1086.81–1086.82초다.
예상 합계는 실제 GitHub 실행 시간이나 timeout 해소 완료 판정이 아니다.

## 검증·원본

- Python: `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`.
- 위 5개 파일: **126 passed in 224.94s**, `CI=true`, `OMP_NUM_THREADS=2`,
  legacy JUnit. 실제 명령·PID·부하 평균·종료 코드는 `local-selected-receipt.json`에 기록했다.
- JSON의 기존 항목 보존과 shard의 정확히 한 번 포함·전체 합집합을 검사했다.
  `tests/test_ci_sharding.py`: **68 passed in 1.65s**. `git diff --check`도 통과했다.
- 원본 경로: `/Users/changmin/projects/ugrp/outputs/ci-durations/pr392-20261006/`.
  실패 로그, 회수 JUnit 7개와 SHA-256, 전후 shard 목록, 로컬 JUnit·로그,
  `duration-update-receipt.json`을 보존한다. push 뒤 CI 결과는 이 경로와 PR 코멘트에 남긴다.
  단위 시험 기록이므로 TensorBoard 연구 결과 snapshot 대상이 아니다.

## 참고 자료

- [pytest-split 공식 문서](https://jerry-git.github.io/pytest-split/),
  [least_duration 구현](https://jerry-git.github.io/pytest-split/api_docs/#algorithms.LeastDurationAlgorithm):
  2026-10-06 본문 확인. 측정 시간을 갱신해 긴 시험부터 배정하는 기존 표준 방식을 유지했다.
  CI 비용 자료 보완이므로 제어기나 논문 기반 물리 방법을 변경하지 않았다.
- `CONTRIBUTING.md`, `scripts/run_ci_tests.py`, `scripts/refresh_ci_durations.py`,
  #371 커밋 `933e88031e1064c95663ce04f8bd508c494a70f4`.
