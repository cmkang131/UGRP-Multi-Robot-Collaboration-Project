# v6h 봉인 작업 기록 (2026-10-01, Codex)

조정자의 preflight 재개 결정 A/B에 따라 이전 중단 자료(`../seal_preflight/`)를 그대로 보존하고 작업을 이어갔다. 이 기록의 최종 봉인 SHA/테스트 결과/원격 확인은 같은 폴더의 `validation.json` 및 PR #292를 따른다.

## 수행 범위와 경계

- 블라인드 실행 source: `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`.
- 최종 classifier branch: `1f0e4eb501a8f1b87077df943382fc1f0777dc69`. `3918de41`에서 병합했고 classifier/recorder/CLASSIFY_NOTES는 그 tip 바이트를 보존했다.
- main merge parent: `f5cd3a2b7754236a7b416cca1e1f9fe76fe8dd14`. fetch 직후 `55609ed1`에서 공용 remote ref가 다른 작업에 의해 갱신된 뒤 병합됐다. 이후 새 main을 추적해 바꾸지 않고 이 부모로 검증한다.
- 실행 계약 274파일(EXTRA 6개 포함)은 Git `4c6b439f` blob SHA와 SHA-256으로 검사했다. 작업 트리 drift는 원본 실행 바이트로 대치하지 않는다.
- 분석 계약은 최종 분류기·동적 adapter/분석 import·정의·gate·등록 metadata 및 보수적인 실행 의존성 집합을 봉인 커밋에 따로 고정한다.
- bundle v83 / workflow 2.16.0 유지. CURRENT_REVISION=v6h. `state=sealed`, `sealed=true`, `status=DRAFT`, `runnable=false`, `execution_authorization=null`: 분석은 봉인됐으나 새 실행 권한은 없다.

## main 변경의 공개

이전 preflight의 4파일(`zone_main_budget.py`, `zone_study_llm_driver.py`, `zone_study_llm_transport.py`, `agent_lock.py`)은 조정자가 명시적으로 main 버전을 선택했다. 모델 호출 0, lock은 호스트 도구라는 근거와 원본 Git blob 검증을 함께 남겼다.

후속 main에는 `harness/vision_loc_protocol.py`(응답 seq int 검사/bool 거절)와 `sim/workflow_manager.py`(zone-study 실행 전 admission 검사)가 추가됐다. 별도 질문을 보냈지만, 재개 결정 A(1)의 원본 커밋 고정과 B의 정상 main 병합이 기존 3번 중단 규칙을 대체한다는 지시 범위로 처리했다. 추가 두 파일이 원래 명시된 4개였다고 기록하지 않았다. 총 6파일은 main 바이트이며 원본 274파일은 4c6b439f에서 계속 검증한다. 정확한 해시는 prereg notes에 있다.

## 블라인드 메타데이터와 바이트 비교

허용된 `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`의 RUN_MANIFEST.json, plan.json, placements_seed943_first12.json만 읽었다. 세 파일의 사본과 전체 해시를 보존했다. **블라인드 raw 경로는 목록·내용 모두 열지 않았다.** cases.jsonl/driver 전체 해시는 manifest의 진술이며 독립 raw 검증이라고 표현하지 않는다.

기존 builder의 case 값은 모두 같았지만 `chain_stop_leg`의 키 순서가 driver plan과 달랐다. 등록 metadata builder의 출력 순서만 맞췄다. `registration_run_id`만 제거한 72개 case를 plan의 literal 배열과 직접 비교했으며 양쪽 SHA-256은 `f476c3d3103daa86fcab4553e9e2cfaf3b0abf500b71b6151554de7cbd2a4269`다. 정렬·숫자 반올림·다른 필드 제거를 사용하지 않았다.

## 검증과 환경

- classifier 병합 직후 필수 source 검사 및 classifier/recorder/blinded adapter 검사: 225 passed, 327.40초. 이는 host 부하가 있는 기능 회귀의 소요 시간이며 성능 비교가 아니다.
- 초기 봉인 후보의 새 mutation/gate 테스트: 21 passed, 45.41초. 최종 봉인 결과와 구분한다.
- 최종 전체 회귀와 추가 Git blob 감사는 validation.json/로그에 기록한다. 모든 로컬 검사는 기존 `.venv-sim-worker-mac`에서 `tests.pose_provider_no_physics`를 쓰고 host lock 없이 실행한다.
- 공용 Git `core.worktree`가 다른 작업의 `/private/tmp` 경로를 가리켜 최초 merge가 거절됐다. 공용 설정을 바꾸지 않고 `GIT_WORK_TREE`/명령별 `core.worktree`로 이 작업 경로를 명시했다. 실제 작업 트리는 보존돼 있었다.
- `.github/workflows`는 직접 편집하지 않았다. 병합으로 상속한 바이트는 main과 같음을 확인한다. 새 회귀 파일은 `scripts/run_ci_tests.py` 목록에만 추가한다.
- classifier/main branch에서 상속한 과거 `.patch`/실패 로그의 공백은 원본 기록 보존을 위해 수정하지 않는다. 자체 변경의 diff check는 따로 검사한다.
- `/private/tmp` 추출 디렉터리를 만들지 않았다. 물리·렌더·모델·outcome 분석은 없다. 새 연구 결과가 없으므로 TensorBoard 변환·서버 작업은 없다. UGRP 예외에 따라 Drive를 사용하지 않는다.

PR은 봉인 후에도 독립 검토가 필요하며 병합하지 않는다. 개봉과 실제 classifier 적용·결과 전달/TensorBoard는 별도 작업이다.

첫 전체 회귀는 **545 passed / 8 failed**였다. 실패 8개는 CI 분할 테스트가 main의 새 fixture 사전 검사에서 중단된 것이며, sparse checkout에서 과거 JSON.gz fixture 3개가 빠진 원인이었다. 총 158,676 bytes의 Git 원본을 sparse 예외로 복원했다. 제어기·분류기·테스트 기준은 바꾸지 않았다. 첫 미커밋 봉인 후보는 `UNCOMMITTED_attempt1.json`, 실패 로그/JUnit은 `attempt1_tests.*`로 보존한다. 이 후보는 커밋·push된 봉인이 아니며, 최종 봉인 전의 기록이다.

최종 검토에서 main이 추가한 `sim.zone_study_admission`→`harness.zone_corridor_admission` 전이 import 2개를 분석 pin에 포함했다. 분석 pin의 completeness도 해당 **봉인 커밋의 AST/Git tree**에서 검사하도록 했다. 나중 작업 트리 변경 때문에 과거 분석 감사를 깨뜨리지 않도록 커밋된 봉인은 Git 이력에서 찾아 blob으로 검사한다. 수정 뒤 별도 최종 회귀를 실행한다.

최종 소스에서 전체 관련 회귀는 **555 passed (423.29초)**, 실패/건너뜀 0이다. 비물리 가드의 physics step·실제 vision worker·network 시도는 모두 0이다. 최종 EXECUTION 274 / ANALYSIS 288 pin과 72개 case 바이트 일치를 확인했다. 시간은 성능 비교가 아니다. 커밋 뒤에는 해당 SHA의 Git blob으로 다시 감사하고 정상 CI push·PR 갱신을 확인한다.
