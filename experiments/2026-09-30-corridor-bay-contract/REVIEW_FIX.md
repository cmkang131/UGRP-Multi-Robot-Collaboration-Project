# PR #310 — C310-1 수정

검토 원본은 `origin/codex/review-e2e-batch-c`의
`experiments/2026-09-30-e2e-readiness/REVIEW_E2E_BATCH_C.md`와
[#310 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/310#issuecomment-5911178125)다.
검토 대상 HEAD는 `2bfb9dce5655f2a71e62ab700281cc5258abb40b`이고 지적은 **MAJOR C310-1 한 건**이다.
수정 전에 fetch한 main `c12796676802ab54cad2f0635e3e96e911691c76`을 충돌 없이 병합했다.

## 지적 → 수정

- **지적:** 새 factory만 거절하고 실제 host 선택 경로는 이를 호출하지 않는다.
  복도만 있는 지도에서 봉인된 생성자까지 가면 `StopIteration`이 발생한다.
- **수정:** 기존 표준 진입점 `scripts.sim_cli workflow plan/run zone-study-integration-run`의
  `sim.workflow_manager.plan()`에서 `sim.zone_study_admission.require_study_runtime()`을 호출한다.
  선택한 episode의 공개 지도 파일을 읽고, factory와 공유하는 `require_door_runtime()`으로
  `CORRIDOR_RUNTIME_UNSUPPORTED: T10b required`를 반환한다. CLI 종료 코드는 2다.
- **부작용 순서:** 거절은 실행 기록 폴더·subprocess·host·pose provider·world 생성보다 먼저다.
  `maps/zones`와 `maps/zones_final` 모두 검사하며 파일 이름에 `corridor`가 없어도 지도 내용으로 거절한다.
  네 통신 조건과 `--dev-horizon-s`에서 동일하다. private setup/event/pose로 판단하지 않는다.
- **정상 경로:** 문 지도는 기존 runner와 인자를 유지한다. 기존 승인·소스·provider·scene 검사를 우회하지 않는다.
  선택 episode의 부재/중복, 지도 파일 부재/중복, scenario와 episode의 지도 불일치도 부작용 전에 거절한다.
- **봉인 보존:** `ZoneOwnExecutor`, `OwnCamTeamHost`, scene provider, integration runner,
  `configs/simulation_workflows.json` 및 모든 기존 등록 JSON은 수정하지 않았다.
  v6e가 고정한 85개 source hash를 등록값과 직접 대조한다. 과거 해시를 새 소스로 다시 쓰지 않는다.

복도 주행을 추가한 변경이 아니다. 고정된 생성자를 직접 호출하는 역사 경로까지 수정하지 않았으며,
복도 runtime은 T10b의 새 버전이 필요하다. 관리 경로의 이른 거절만 보장하고 전체 직접 호출의 예외 제거를 주장하지 않는다.
새 bundle/workflow ID, 물리 실행 승인, E2E 성공을 만들지 않았다.

## 회귀 검사와 원본

`tests/test_zone_own_executor_corridor_contract.py`에 실제 CLI와 catalog를 사용하는 fake 검사를 추가했다.
기록 생성과 subprocess에는 실패 sentinel을 넣었고, 올바른 문 지도만 통과하는 양성 대조를 둔다.
기존 workflow 목록 검사는 `{}` 임시 prereg 대신 기존 `pair_dev_DRAFT.json`을 사용하도록 고쳤다.

수정 전 새 검사: **22 failed, 1 passed, 31 deselected**.
복도 plan이 거절되지 않거나 run이 기록 생성 단계에 도달한 실패로 C310-1을 재현했다.
물리 실행은 없었다. 기존 독립 검토의 생성자 반례와 같은 결함을 관리 진입점에서 재현한 것이다.

최종 로컬 실행(`green-03`): **157 passed, 3 deselected in 79.92s**, 종료 코드 0.
새 CLI 검사 23개와 기존 정적 검사 31개를 포함하며,
`tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`를 전체 실행했다.
own executor·fake host·hard routes·workflow manager 관련 검사도 포함한다.
85개 고정 source hash는 검사 전후 모두 등록값과 같고 자신의 잠금을 반환했다.
반복 실행의 통과 수를 서로 더하지 않는다.

세 실행의 로그·receipt·driver 9파일을 [review-fix/](review-fix/)에 복사하고
원본과 전체 bytes/SHA-256을 대조했다(`checksums.json`). 이 복사본은 Git 보존 대상이며,
그 외 임시 테스트 파일을 포함한 raw 전체의 원격 백업을 뜻하지 않는다.

raw 위치는 primary checkout의
`outputs/2026-09-30-cap-t10a-corridor/review-fix-{red,green-02,green-03}/`다.
공용 잠금을 획득하고 MuJoCo·torch·모델 SDK import와 네트워크를 막는 driver로 검사한다.
첫 수정 후 실행(`green-02`)은 **157 passed, 1 failed, 2 deselected**였다.
실패는 기존 `test_parent_exit_cleans_background_child`의
`PermissionError: [Errno 1] Operation not permitted: 'ps'`다. sandbox의 프로세스 조회 제한이며
source-pinning 실패가 아니다. 해당 검사 소스와 CI 선택은 그대로 유지하고,
로컬 최종 실행에서만 물리 host 검사 두 건과 이 환경 제한 검사 한 건을 명시적으로 제외한다.
`green/`에는 잠금을 기다리다 종료한 최초 대기 driver만 있다(검사 실행 전).
모델·렌더·물리 step은 0이며
벽시계 테스트 시간은 성능 측정이 아니다. 최초 `data/` 결과는 덮어쓰지 않는다.

raw receipt의 `head`는 커밋 전 브랜치 HEAD이고 실제 검사 bytes는 `files_sha256`에 있다.
`merged_main` 필드는 driver가 검사 종료 때 관측한 `origin/main`이다. 실제 첫 병합 입력은
위의 `c1279667`이며 검사 대기 중 원격 main이 움직인 것을 병합 완료로 해석하지 않는다.

로컬 정적/fake 코드 검증이므로 새 학습·평가 cohort나 TensorBoard 물리 snapshot은 없다.
UGRP 예외에 따라 Drive를 사용하지 않는다. 정상 GitHub CI는 실행하며 취소·skip하지 않는다.
