# CI 후속: 기존 실행 버전 보존

## 최초 CI 실패

PR #705의 최초 커밋 `4f4fb568fcfb2ea9ec83289ee55147da8c349f79`에서
[offline-regression-checks](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/43798751461/job/133073669996)의
`Verify current RGB execution bundle and source pins` 단계가 다음 이유로 실패했다.

```text
RGB execution bundle invalid: RGB execution source drift: scripts/evaluate_camera_short_transport.py
```

기준 커밋의 v63 소스 pin 174개는 일치했다. 이번 단계 경계 기록 검사 수정이
그중 평가기 한 파일을 바꿨으므로 우리 변경으로 발생한 실패다. v63의 hash를
덮어쓰거나 검사 범위를 줄이지 않고 저장소의 실행 버전 절차를 적용했다.

## v64 등록

[main과 모든 열린 PR의 번호 확인](bundle-reservation.json) 후
`rgb-standard-dispatch-v64`를 추가했다. v63은 은퇴 목록에 등록하고 모든 기존
registry JSON은 바이트 그대로 보존했다. v64의 부모는 v63이며 상태는
`experimental_unqualified`다. 물리·카메라·제어·명령 설정 및 나머지 정책 필드는
같고, 174개 소스 중 평가기와 버전 등록 모듈 두 개의 hash만 바뀌었다.
과거 성공률과 실행·청구 기록은 새 버전으로 승계하지 않는다.

| 파일 | SHA-256 |
|---|---|
| 기존 v63, 변경 없음 | `ef4fe391e57c145b6625ba052e651542745bfcb6244d8e25736827ee8122aa01` |
| 신규 v64 | `5187af8d8c0662595b247d6050eecce527d8621f7063ec8bc4567ea569df53b8` |

## 실제 후속 검증

다음 세 명령은 모두 exit code 0이었다.

```sh
python -m harness.rgb_execution_bundle verify-current --id rgb-standard-dispatch-v64
python -m harness.rgb_execution_bundle verify-registry --base ca954d9fa64f94303a3f645c265aff85e2af2fce
git diff --check
```

```sh
OMP_NUM_THREADS=2 .venv-test/bin/python -m pytest -q \
  tests/test_rgb_execution_bundle.py \
  tests/test_zone_study_review_r10.py::test_dry_manifest_binds_full_source_bundle_inputs_without_implicit_ack \
  tests/test_zone_study_review_r10.py::test_v62_retires_v61_with_identical_physics_and_immutable_bytes \
  tests/test_zone_study_review_r10.py::test_v63_preserves_executed_v62_bytes_and_effective_contract \
  tests/test_zone_study_review_r10.py::test_v64_preserves_v63_bytes_and_limits_changes_to_evaluator_sources
```

실제 pytest 결과: **11 passed in 16.82s**, exit code 0.
이 검사는 기존 v63 bytes 보존, 설정 동일성, 변경된 소스 범위, 새 source의
manifest 연결과 과거 버전 실행 거부를 확인한다.

이는 로컬 정적·오프라인 검증이다. GitHub 전체 CI 완료를 뜻하지 않으며
후속 원격 결과는 [PR #705의 Checks](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/705/checks)에 남는다.
감사용 물리 코호트·LLM 호출·실물 실행은 추가하지 않았다.
