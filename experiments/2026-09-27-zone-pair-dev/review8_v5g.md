# PR #240 검토 8 반영 — v5g, 비물리 검증

기준 HEAD: `1d756c5f2706bc662d50f334d0db9e7b8a75d479`.
이 문서의 변경은 **미커밋 로컬 후보**다. 물리 실행·실제 모델 호출·승인 댓글 생성·커밋·push·병합 없음.

## 변경

- P1: `--execute`의 최종 진입에서 `gh api --hostname github.com repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/<id>`로 실제 댓글을 조회한다.
  설정에 고정된 저장소 별칭, 소유자 허용 목록, 이슈/댓글 ID, 소스 SHA·등록 해시·run_id를 담은 정확한 승인 줄을 검증한다.
  조회 실패·오프라인·삭제·시간 초과는 실행을 거부한다. 성공 응답의 comment id, author, updated_at, body SHA-256을
  manifest의 `github_authorization`에 기록한다. 조회 전후 소스·승인 바이트를 다시 검증한다.
  [승인 형식과 절차](../../docs/zone_pair_execution_authorization.md), [정책](../../configs/zone_pair_authorization.json).
- P2-1: tags·vision·delayed 제공자에 `get_motion_params()`를 구현했다. memory-v3 ON/OFF guard는 공개 인터페이스를 사용한다.
  조회는 복사본을 반환하며 지연 큐나 관측 시각을 진행시키지 않는다. 기존 보정 선택·confidence 임계값은 유지한다.
  [인터페이스 문서](../../docs/pose_provider_motion_params.md).
- P2-2: host fixture가 실제 물리 모듈을 import한 뒤 교체하던 경로를 없애고, lazy import 전에 가짜 의존 모듈을 주입한다.
  `test_provider_prior_and_close_hooks_use_only_preregistered_own_docks`를 독립 프로세스에서 단독 실행해 통과했다.
- `wall_tags.camera_in_base()`는 자기 발행 PWM만 사용하는 순수 기하 함수다. 태그 관측 API와 구분하고 동결 markerless/VIS3 원본 참조를 유지했다.

## 검증

최종 전체: **1,604 passed, 2 skipped, 183 subtests passed**, 139.60초.
비물리 가드의 `physical_step_attempts`, `real_vision_worker_attempts`, `network_attempts`는 모두 **0**.
실제 MuJoCo step이 필요한 기존 host 테스트 2건은 사용자 금지 범위라 제외했다:

- `tests/test_zone_own_executor.py::test_team_host_feeds_each_executor_only_its_own_camera`
- `tests/test_zone_own_executor_host.py::test_team_host_isolation_abort_and_horizon_on_the_real_world`

```sh
OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 ../../ugrp/.venv-sim/bin/python -m pytest -q \
  -p no:cacheprovider -p tests.pose_provider_no_physics --basetemp=./.pytest_tmp \
  tests/test_zone_pair_*.py tests/test_zone_start_dock.py tests/test_zone_study_pair_delay.py \
  tests/test_zone_own_*.py tests/test_zone_study_integration*.py tests/test_pose_provider_boundary.py \
  tests/test_owncam_memory*.py tests/test_real_scene_memory.py \
  tests/test_pose_provider_contract.py tests/test_vision_pose_source.py
```

단독 검증은 비물리 플러그인 없이 실행했고 **1 passed**:

```sh
OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 ../../ugrp/.venv-sim/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=./.pytest_tmp \
  tests/test_zone_study_integration_pair.py::test_provider_prior_and_close_hooks_use_only_preregistered_own_docks
```

집중 회귀 69건도 통과했다. gh 호출은 모두 가짜로 주입했다. 위조·다른 작성자·다른 저장소·digest의 SHA/등록/run 불일치·삭제·오프라인·timeout·gh 부재·잘못된 응답 및 조회 중 파일 변경을 거부한다.
성공 fixture는 물리 함수 대신 가짜 진입 함수를 사용해, 조회 결과가 먼저 manifest에 저장됨을 확인한다.
memory-v3는 ON/OFF × vision/tags × 지연 여부 8조합과 지연 profile/복사 독립성 2건을 검증했다.

첫 전체 실행에서는 추가된 공개 메서드의 SHA가 M1/M2 후속 해시 허용 목록에 없어 2건이 실패했다.
과거 해시·원본 등록을 그대로 두고 v5g의 명시적 후속 SHA를 추가한 뒤 위 전체 명령을 다시 통과했다.
추가한 `owncam_pose_source.py` SHA-256: `7e45cc820f3c0b96b0144c2a3318bf7b18a97f61d88aec2a62130e96ed29b155`.

## 등록·보존·남은 범위

[prereg_v5g.json](prereg_v5g.json)은 v5f를 대체하는 별도 등록이며 `execution_authorization`과 `execution_source_sha`는 null이다.
등록 해시: `1d50f5b7708698dc4b8b5d8fca94ee0f1f2f67425bec8891722c303847eccd2b`.
dev11/907, dev12/908 모두 prepare-only 통과: `prepared_not_executed`, `applied=null`, `physical_success=null`, `model_calls=0`, `github_authorization=null`.
prepare 프로세스는 MuJoCo/모델 import와 gh 조회를 차단한 상태에서 실행했다.

v5f 대비 runs·criteria·stage_rules·planned_setdown·limits·timing·safety_coverage·environment·inputs·contact_profile_contract·scene_instances **11개 절 동일**.
σ 5 cm·yaw 3°·margin 35 mm, GT/eval_only 제어 유입 금지, weld OFF, `cargo_noslip_v1` 유지.
동결 제어 소스 4개, memory-v2 보존 파일 23개, VIS3 파일 7개 및 과거 사전등록 11개 원본 해시 일치.
scene/grasp contract와 새 등록 해시는 현재 실행 소스와 일치한다. 새 workflow/실행 번들 번호는 할당하지 않았다.

`git fetch`는 공용 Git 디렉터리 쓰기 권한으로 실패했고, `gh pr list/view`는 네트워크 제한으로 실패했다.
따라서 최신 원격 PR 상태나 실제 GitHub 승인 인증을 확인한 결과는 아니다. 실조회 인증은 승인된 물리 실행 직전에 필수이며 현재 승인은 null이다.
현재 결과는 코드 회귀와 준비 검증이다. 신규 물리·학습·평가 실험이 없어 TensorBoard snapshot은 만들지 않았다. UGRP 예외에 따라 Drive는 사용하지 않았다.

원문 로그·보존/prepare 영수증은 [review8_validation/](review8_validation/)에 저장했다.
prepare manifest는 해당 준비 시점의 미커밋 소스 목록도 보존한다. 최종 검증 후 `.pytest_tmp`를 삭제했고 Git 커밋은 만들지 않았다.
