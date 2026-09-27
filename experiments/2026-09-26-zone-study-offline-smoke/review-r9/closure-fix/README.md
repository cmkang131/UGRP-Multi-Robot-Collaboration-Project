# PR #194 R9 공통 소스 의존성 수정 (2026-09-27)

기준 HEAD `59bb3435570235efc5f8c3c6111e5ad42984127e`,
브랜치 `kiro/zone-study-core`. 기존 미커밋 R9 수정 위에서 작업했으며 커밋하지 않았다.
상위 R9 기록·로그·해시는 당시 검증 기록으로 그대로 보존한다.

## 변경과 검증

`gemini_proxy.py → zone_completion.py` 의존성 때문에 표준 RGB 번들의 정적
`source_closure()`에 zone 모듈이 들어갔다. 공통 종료 판정을
`harness/llm_completion.py`로 옮기고 proxy·study·runner·테스트의 import를 변경했다.
모듈 설명과 정책 식별자 보존 주석 외에 이동한 코드의 내용은 동일하다.
기존 R9 정책 ID `ugrp.zone_completion.proxy_stop_and_valid_reply.v1`도 유지한다.
closure 검사 자체를 완화하거나 소스 추적에서 파일을 제외하지 않았다.

| 검사 | 이번 결과 |
|---|---|
| 보고된 `test_zone_scene_reuses_the_standard_scene_path_without_touching_bundle_sources` | 통과 |
| R9 `length` + 유효 JSON 반례 4조건 | 4/4 통과, 행동·메시지 거절 유지 |
| 공통 helper의 closure 포함·pilot 동결 소스 해시 검사 | 새 회귀 1개 통과 |
| study/scheduler/cost/zone dispatch/workflow/Gemini 회귀 | **1,067 passed, 26 subtests passed, 1 deselected** |
| 회귀에 포함된 R9 / R8 / zone dispatch | 107 / 51 / 27개 통과 |
| `git diff --check` | 통과 |

집중 검사 6개는 확장 회귀에 포함되므로 수를 합산하지 않는다.
기존 환경 제한 검사 `test_parent_exit_cleans_background_child`는 `ps` 권한 제한으로
제외했으며 통과로 집계하지 않았다. 공용 잠금 생성이 sandbox 권한으로 차단되어,
사용자가 전달한 coordinator의 **이번 오프라인 pytest 한정 잠금 예외**에 따라 실행했다.
물리 실행·실제 모델 호출은 0회다. 잠금을 쓰는 전체 검증은 coordinator가 별도로 한다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_dispatch.py::test_zone_scene_reuses_the_standard_scene_path_without_touching_bundle_sources \
  tests/test_zone_study_review_r9.py::test_r9_length_valid_json_is_failed_not_executed \
  tests/test_zone_study_review_r9.py::test_shared_completion_source_is_pinned_without_zone_dependencies \
  -q --basetemp=./.pytest_tmp

OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study*.py tests/test_zone_event_scheduler.py tests/test_zone_sim_cost.py \
  tests/test_zone_dispatch.py tests/test_simulation_workflow_manager.py tests/test_gemini*.py \
  -q -k 'not test_parent_exit_cleans_background_child' --basetemp=./.pytest_tmp \
  --junitxml=.tmp/r9/closure-fix/regression.xml
```

검사 종료 뒤 `.pytest_tmp`를 삭제하고 부재를 확인했다. 로그는 `focused.txt`,
`regression.txt`, 해시 감사는 `source_audit.json`, 소스·증거 해시는
`test_results.json`에 보존했으며 복사한 증거의 바이트도 다시 확인했다.
추가 테스트 XML과 변경 전 소스 목록은 로컬 `.tmp/r9/closure-fix/`에 있다.

## 실행 번들·동결 소스 영향

- 표준 closure는 **174 → 174개**, zone 경로는 **1 → 0개**다.
  `harness/zone_completion.py`가 빠지고 `harness/llm_completion.py`가 들어간다.
  공통 경로 중 바이트가 바뀐 파일은 `harness/gemini_proxy.py` 한 개다.
- 등록 번들 JSON **63개 모두 바이트·해시가 그대로**다. 현재 v61 JSON 해시는
  `98b77ad6878548f21d97f4575f37fe5c0dfdbdcdf8b68087ca1f5ea2e829790b`다.
- **v61의 소스 pin 검증은 이번 변경 전부터 실패했다.** v61은 173개 소스를
  고정하며, 미커밋 R9는 새 helper 1개와 변경된 `gemini_proxy.py`를 포함한다.
  이동 뒤에도 `load_bundle(RUNNABLE_ID)`는
  `RGB execution required source set mismatch`로 거절한다. 따라서 위 오프라인
  회귀 통과를 번들 검증 통과로 보고하지 않는다. coordinator가 최종 소스를 고정할 때
  최신 main·열린 PR의 번호를 확인해 새 번들 ID와 전체 소스 pin을 등록해야 한다.
  과거 번들을 덮어쓰거나 임의의 새 번호를 예약하지 않았다.
- pilot의 `source_identity()['files']`는 **334 → 334개**로 helper 경로 변경을
  자동 반영한다. helper와 이를 import하는 8개 실행 파일의 해시가 바뀌므로
  기존 budget의 동결 identity를 그대로 재사용할 수 없다. 송신 비용·예약을
  초기화하지 않았고, 기존 실험·budget·manifest도 수정하지 않았다.

`git fetch origin`은 `FETCH_HEAD` 쓰기 권한, `gh`는 네트워크 제한으로 실패했다.
GitHub 연결 도구도 저장소 redirect/권한 오류여서 최신 원격 상태는 확인하지 못했다.
push·PR 코멘트·병합은 하지 않았다. 새 학습·물리·실호출 결과가 없어 TensorBoard
변환이나 Drive 작업은 수행하지 않았다.
