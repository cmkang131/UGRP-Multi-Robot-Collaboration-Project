# PR #371 v103 push 중 원격 갱신 통합 (2026-10-05)

- #363 v103 병합 커밋: `7d356fb1291cf0fa6feffc9b8698ece600fff774`; 부모는 `b13ec137a89e6d71d415ac2f5dd076dd94ccf6cd` + `f2a426e7d5a29e582334c056ce1cd8acc80f65ab`.
- 초기 관련 19파일 시험: `513 passed in 691.27s (0:11:31)`, exit 0. 해당 통과 줄을 확인한 뒤 7d356fb1을 커밋했다.
- 첫 일반 push가 non-fast-forward로 거절됐다. 원격에 다른 작업의 main 동기화 커밋 `39087e36a574dc33f52d565c514f40edd2ffe20e`가 추가됐기 때문이다.
- 이 파일을 포함하는 두 번째 merge는 `7d356fb1` + `39087e36`의 이력을 모두 보존한다. 재작성·force push 없음.
- 충돌 1개: `scripts/run_ci_tests.py`의 같은 삽입 위치. `test_deadband_u0_v102.py`와 `test_dev_pair_checkpoint.py` 항목을 둘 다 남겼다.
- 이전에 검증한 2642개 소스 중 원격 통합으로 바뀐 기존 파일은 `scripts/run_ci_tests.py`, `scripts/run_pair_highpose.py`, `tests/test_simulation_workflow_manager.py` 3개뿐이다. 새 체크포인트·선택형 가속·감시 모듈과 기록은 원격 내용을 그대로 보존했다.
- pair_llm 실행 경로, HIGH runtime/refix, host clock v2, 새 보정 및 `--calibration` 전달 경로는 513개 시험을 통과한 트리와 바이트 동일하다. 실제 pair_llm CLI는 선택형 가속/체크포인트 wrapper를 사용하지 않는다.
- 검증: `127 passed in 428.09s (0:07:08)`, exit 0. 시험 전후 소스 2654개 SHA256 동일.
- native MuJoCo를 실제 진행시키는 체크포인트 시험은 선택하지 않았다. 이 작업의 모든 시험에서 시뮬레이션·렌더·실제 LLM 호출은 0회다.
- 동결 15개, pair_llm_3327a0ea 6개 및 모든 기존 tests/fixtures 바이트/Blob 동일. 최종 소스 해시는 로컬 `v103-remote-integration-source-sha256.json`.
- 원격 문서 2곳의 기존 EOF 빈 줄 경고는 보존했다: `docs/reviews/codex-independent-review-2026-10-04/publication/final-reproduction-comment.md`, `docs/reviews/codex-independent-review-2026-10-04/round23/validation.md`. 그 외 merge diff 공백 검사 통과.

## 최종 재검사 명령

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no:cacheprovider --tb=short \
  tests/test_pair_llm_cli.py tests/test_pair_llm_inputs.py tests/test_highpose_host_clock.py \
  tests/test_highpose_dev_pilot.py tests/test_zone_final_pair_highpose.py \
  tests/test_dev_pair_checkpoint.py::test_runner_default_is_unchanged_signature \
  tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_catalog_has_registered_workflows_and_distinct_adapters
```

로그: `/Users/changmin/projects/ugrp/outputs/stack-371-clock-v2-20261005/pytest-v103-remote-integration.log`.
이 결과는 앞 513개 검사와 겹치므로 합산하지 않는다. 바뀐 highpose CLI와 선택 기능 기본 OFF, pair_llm 보정·시계·입력 경계, 카탈로그 연결을 재검증한다.

## 범위와 명령

작업 시작 fetch에서 확인한 #363 v103 `f2a426e7`과 admitted 보정 `a04371f6…`을 유지한다.
작업 중 #363가 `9f8db2cf`(추가 적재 잡음 변경)와 `a6fec250`(DEV_LIGHT=True·충돌/불확실성 정지 log-only)을 더 받았다.
이 변경은 요청한 v103 보정·정지 동작과 별도 범위다. 이번 검증 대상은 시작 시 확인한 f2a426e7에 고정하며, 후속 2커밋은 통합하지 않았다.

[새 실행 명령과 v103 검증](stack_363_v103_20261005.md)의 3개 명령은 최종 커밋 HEAD의 argparse로 다시 확인한다.
최종 merge SHA·push/원격 HEAD 일치 및 argparse 결과는 로컬 `outputs/stack-371-clock-v2-20261005/REPORT_v103.md`에 남긴다.
실제 운반/E2E·원격 CI·main 병합 완료는 주장하지 않는다.

## 참고 자료

[Git merge](https://git-scm.com/docs/git-merge)와 [Python argparse](https://docs.python.org/3/library/argparse.html) 공식 문서의 기존 절차를 적용했다.
새 제어 방법·임곗값·프롬프트·정답·weld·공용 카메라는 추가하지 않았다.
