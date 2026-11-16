# T05 — Batch H 검토 지적 수정

2026-10-01, PR #334. 검토 커밋은
`d17327aeacf858108179ebbad2a85d0a9e357608`, 검토 대상은
`a4a0bacb51d46d69c1107277c4d11e67b60e4693`이다.
시작 시 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`를 병합했다
(`3f271c4902ec51cc0236204ceaf2099a6fc1fa32`).
Draft 유지, 병합하지 않는다. 물리·렌더·모델 실행과 호스트 잠금 사용은 없다.

## 수정 내용

- **H334-1:** 상위 action의 `duration`과 발행 이력의 `duration_s`를 혼동했다.
  이제 canonical `duration_s`의 유한한 비음수 값을 사용한다. 잘못된 값은
  명령 이력을 바꾸기 전에 거절한다. 겹치는 명령의 마지막 종료 시각까지
  기다리고, 길이가 0인 명령도 발행 뒤 촬영이 필요하다. 시간 경과만으로
  이전 영상을 다시 운반 허가 근거로 쓰지 않는다.
- **H334-2:** frame ID만 증가한 동일 촬영이 두 번째 확인으로 집계됐다.
  촬영 시각도 엄격히 증가해야 하며, 같은 시각의 JPEG 재전달은
  `OWN_IMAGE_INVALID`로 정지한다. search·verify_hold·holding·verify_release에
  동일 바이트 및 바이트만 바꾼 재전달 회귀를 둔다. 정지 장면처럼 픽셀이
  같더라도 실제 촬영 시각이 증가하면 정상 확인을 허용한다.
- 제어기 profile은 `tile-west-manipulation-dev2`다. 영상 인식 문턱·카메라·
  물체·정적 FK/IK·네 통신 조건의 입력 범위는 그대로다. 자기 RGB·정적 정보·
  자기 발행 명령과 기존 취소 경계만 사용하며 평가·GT·접촉·측정 관절을 추가하지 않는다.

## 반례와 검증 방식

검토 브랜치 `tests/test_review_e2e_batch_h.py` 중 #334 두 함수의 본문을
그대로 가져오고 `xfail`을 제거했다. AST로 원본 assertion 본문이 같음을
확인했다. fixture는 현재 checkout을 기본으로 사용한다. 과거 blob을 기본
로딩해 수정 코드 대신 옛 코드를 검사하는 경로를 없앴다. #333 반례는
beam PR 범위에 남긴다.

`tests/test_zone_own_executor_tile_review_h.py`가 기존 CI glob으로 두 반례를
수집한다. `.github/workflows`와 `scripts/run_ci_tests.py`는 수정하지 않았다.
실제 `OwnCamTeamHost._macro_timeline`의 순수 변환과
`CameraRobotPort.validate_raw_action`의 입력 계약도 실행했다. host/world/port를
생성하거나 실제 주행하지 않았으며, 호출자에게 속한 로봇 ID를 붙인 모의
이력 전달만 확인했다. native dispatch 연결 완료를 뜻하지 않는다.

실행은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`과
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`을
사용했다. 이 폴더의 `offline_guard.py`를 pytest plugin으로 적용해 MuJoCo·
모델 SDK import와 네트워크 연결을 차단했다. pytest를 직접 실행했으며
호스트 잠금을 획득하지 않았다.

최종 집계·로그 해시·소스 해시는
[review_fixes_verification.json](review_fixes_verification.json)에 보존한다.

| 검사 | 결과 |
|---|---:|
| 수정 전 검토 반례, xfail 제거 | 2 failed, 정확히 H334-1/H334-2 assertion |
| 최종 tile 및 검토 반례 | 107 passed = tile 105 + 검토 2 |
| 필수 source 두 파일 전체 | 56 passed = 22 + 34 |
| 기존 v3/v3.1 인식·자기 실행기 | 167 passed, 물리 테스트 1건 제외 |
| 최종 서로 다른 테스트 합 | 330 passed, 1 deselected |
| 제거/변조 검사 | 10/10 검출, import·수집 오류 0 |

중간 106건은 순수 native macro 변환 검사 추가 전 결과이며 최종 합에 더하지 않는다.
수정 전 실패도 xfail로 가리지 않고 원본 로그/JUnit에 보존했다.

```sh
export PYTHONPATH=.:experiments/2026-09-30-t05-tile
export PYTEST_PLUGINS=offline_guard PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m pytest -q tests/test_zone_own_executor_tile.py \
  tests/test_zone_own_executor_tile_review_h.py
"$PY" -m pytest -q tests/test_zone_pair_registered_source.py \
  tests/test_zone_study_source_pinning.py tests/test_zone_own_perception_v3.py \
  tests/test_zone_own_perception_v3_1.py tests/test_zone_own_executor.py \
  -k 'not test_team_host_feeds_each_executor_only_its_own_camera'
"$PY" experiments/2026-09-30-t05-tile/mutation_check.py --output /absolute/new/directory
```

기존 6개 변이에 duration 필드 회귀, 주행 종료 대기 삭제, 발행 뒤 촬영 검사
삭제, 같은 촬영 시각 수용을 추가했다. 변이는 임시 모듈 사본에만 적용하며
실제 assertion 실패/pytest exit 1로 검출한다. import·수집 오류는 검출로 세지 않는다.

## 보존과 남은 범위

필수 source 검사 두 파일 및 `tests.yml`은 검토 당시 PR과 병합한 main에
바이트 단위로 같다. v6e의 85개 source SHA도 모두 일치한다. 기존 실험 기록·
봉인·지도·시나리오·raw는 수정하지 않았다. 새 bundle/workflow ID는 없다.

원본 로그와 JUnit은 로컬
`/Users/changmin/projects/ugrp/outputs/t05-tile/review-fixes-20261001/`에 보존한다.
원격 raw 백업이나 로봇 성공률 자료가 아니다. 수정 전 두 반례의 실패와
중간 106건 통과 기록도 남긴다. 변이용 임시 사본은 실행 후 제거되며,
`/private/tmp`에 별도 checkout 추출 폴더는 만들지 않았다. Drive는 사용하지 않는다.

수정본 독립 재검토, native adapter·자기 navigation 전체 연결, 최종 RGB/접촉
보정과 [두 셀 물리 인수](PHYSICS_HANDOFF.md)는 남아 있다. 사용자 지시로
이번에는 물리 인수를 시도하지 않았다. 코드 회귀검사이므로 로봇 trial이나
TensorBoard 실험 스냅샷으로 변환하지 않는다. 정상 GitHub CI는 push 후 별도로
확인하며 취소·skip하지 않는다.
