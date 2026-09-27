# PR #194 10차 리뷰 수정 — 2026-09-27

기준 HEAD: `043f72cdca1ac2b4dd8577bc44a59e65faa67880`, 브랜치
`kiro/zone-study-core`. 사용자 지시대로 **미커밋 변경**으로 남겼다.
물리 실행·실제 모델 호출은 0회다. 새로운 연구 코호트나 TensorBoard 스냅샷은 없다.

## P1-1: 코디네이터의 종료 정책 구현

이슈 #222 정책은 사용자가 전달한 내용 그대로 적용했다. 설치 프록시는 수정하지
않았고 사본도 만들지 않았다. `length`·본문 없음·불완전 JSON·스키마 위반은 비용과
usage를 보존하면서 행동·메시지를 차단하고 성공 집계에서 제외한다.

`stop`이면서 조건별 프로토콜 스키마까지 통과한 응답만 채택한다. 모든 완료 기록에
`upstream_finish_verified=false`를 남기며 기존 `upstream_finish_reason_verified`
필드도 유지한다. 평가·파일럿 manifest의 전체/조건별 집계·CLI 보고에
`accepted_upstream_unverified_calls`와 **정상 채택(상류 미검증)** 라벨을 추가했다.
가려진 `SAFETY`·`RECITATION`·upstream 이유 누락은 정상 STOP으로 검증할 수 없다는
한계를 manifest와 문서에 명시했다.

코호트는 preflight manifest의 `upstream_finish_limitation_acknowledged`가 정확한
boolean `true`일 때만 진입한다. 실행자는 preflight에
`--acknowledge-upstream-finish-limitation`을 지정한다. 기존 4조건별 성공·장부·저장
원문 hash·모든 upstream 시도의 과금 대조 조건은 유지한다.

## P1-2: v62 등록

사용자가 전달한 코디네이터 번호 예약에 따라 `rgb-standard-dispatch-v62`를 등록했다.
전체 RGB Python closure는 174개이며 `harness/llm_completion.py`를 포함한다.
`RUNNABLE_ID`, CI의 `verify-current`, dispatch/dispatch-skills workflow를 갱신했고,
R10 테스트를 CI 선택 목록에 추가했다. 파일럿 workflow는 1.1.0, manifest는 v2다.

- v61 SHA-256: `98b77ad6878548f21d97f4575f37fe5c0dfdbdcdf8b68087ca1f5ea2e829790b`
- v62 SHA-256: `6601192a6da7ac018dd3a7104364065bb9afb9dce0d61e79021f824648b07f69`
- 설치 프록시 SHA-256: `7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556`

v61 바이트와 RGB 물리·카메라·명령 설정을 보존했다. v62는
`experimental_unqualified`이며 과거 성공을 승계하지 않는다.
[파일럿 manifest 미리보기](pilot-manifest-preview.json)는 기본 시나리오·seed 11에
대한 소스 closure/hash, 모델/프록시 요청·실효 설정, 네 조건·지도·주문서·wrist 원본,
프롬프트·프로토콜·전처리, 호출·SIM 비용/tokenizer와 검증 범위를 담는다.
실제 preflight가 아니므로 코호트 게이트를 통과할 수 없다. 최종 실행 SHA는
코디네이터의 커밋 후, 실행 PID는 실제 preflight 시작 시 검증해서 기록해야 한다.
기존 송신 예산은 초기화·교체하지 않았다.

## 검증

모든 pytest는 `OMP_NUM_THREADS=1`과 `--basetemp=./.pytest_tmp`로 실행했다.
종료 후 `.pytest_tmp`를 삭제했다.

| 검사 | 결과 |
|---|---|
| R8/R9/R10 + RGB 번들 대상 검사 | 208 passed, 1 deselected (23.76초) |
| 연구 계약·입력·프로토콜·스케줄러·평가·과거 리뷰·공통 Gemini·workflow 확장 회귀 | 1036 passed, 26 subtests passed, 1 failed, 1 deselected (68.37초) |
| `load_bundle(RUNNABLE_ID)` / CI `verify-current --id rgb-standard-dispatch-v62` | 통과 |
| CI `verify-registry --base HEAD` 및 `--base origin/main` | 통과, 기존 번들 바이트 보존 |
| CI 선택 목록의 R10 포함 / `git diff --check` | 통과 |

확장 회귀의 실패는 기존
`test_simulation_workflow_manager.py::WorkflowManagerTests::test_parent_exit_cleans_background_child`가
`ps`를 실행할 때 샌드박스의 `PermissionError: [Errno 1] Operation not permitted`를
받은 것이다. 테스트가 만든 자식 PID 58087은 후속 `os.kill(pid, 0)`에서 존재하지
않음을 확인했다. 이 실패를 통과로 바꾸거나 관련 없는 코드를 수정하지 않았다.

제외한 기존 `test_existing_registry_bytes_cannot_change_or_disappear`는 임시 Git
커밋을 만들기 때문에 사용자 요청에 맞춰 실행하지 않았다. 저장소 불변성은 위의
읽기 전용 CI 명령으로 확인했다. [JUnit 원문](pytest.xml)과
[기계 판독 검증 기록](verification.json)을 보존한다. 두 pytest 실행의 통과 수는
겹치므로 합산하지 않는다.

실행 명령:

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study*.py tests/test_zone_event_scheduler.py tests/test_zone_sim_cost.py \
  tests/test_gemini_transport_policy.py tests/test_gemini_reasoning_effort.py \
  tests/test_rgb_execution_bundle.py tests/test_simulation_workflow_manager.py \
  --basetemp=./.pytest_tmp -q -k 'not existing_registry_bytes_cannot_change_or_disappear' \
  --junitxml=/private/tmp/pr194-r10-offline-pytest.xml
```

## 남은 범위

`git fetch`는 공용 Git 디렉터리의 `FETCH_HEAD` 쓰기 권한으로, `gh`는 연결 오류로
실패했다. GitHub connector도 redirect 오류여서 원격 최신 HEAD/CI는 확인하지 못했다.
로컬 HEAD와 `origin/kiro/zone-study-core`는 요청 SHA와 같으며 로컬 `origin/main`은
`2823c57c9c555423ab38f9ad8887347208cc6d90`이다. 코디네이터 정책·번호 예약은
사용자가 전달한 값으로 작업했다. 설치 프록시 PID/listener, 4-call 실 preflight,
upstream 과금 대조와 물리 성공은 이번 검증 범위가 아니다.
