# 2026-09-27 study core round-7 통합 적응 (PR #229)

코드·MuJoCo-free 회귀검사 기록이다. 물리 스모크, 실모델 호출, 영상 렌더링은 실행하지 않았다.
`tags_temporary / 임시, 표식 사용, 연구 결과 아님`을 유지한다. 기존 v1/v2 raw·prereg·결과는 보존한다.

## 입력 소스와 충돌 해결

- 작업 HEAD: `844d9dfbca49c4c15693c8e84ab6be13d0c1253b` (`kiro/zone-study-integration`).
- 진행 중 병합 대상: `3b86842cf745410021ab5c937e56b6ed74682f12`
  (`origin/kiro/zone-study-core`, PR #194 round-7). `MERGE_HEAD`와 같은 SHA다.
- `experiments/README.md`: 양쪽 링크를 보존하고 r5/r6/r7 항목을 offline smoke 아래에 유지했다.
- `scripts/run_ci_tests.py`: 양쪽 테스트 패턴을 보존했다. r5/r6/r7, integration/seams,
  own-perception v1/v2 모두 남았다. stage 2/3 전체 패턴 합집합 170개, 인덱스 링크 합집합 97개를 확인했다.
- `harness/zone_study_contract.py`: stage 3 = study-core 원본을 바이트 그대로 채택했다.
  integration의 중복 v2 패치는 폐기했다. 두 소스를 별도 모듈로 읽어 v2 registry가 동일함을 확인했다:
  `c9bb55567a82eef535e7b296ae69f35d5a08e8372479a56ef14c1ac76f08037c`.
  core 파일 SHA-256: `f6e4c5fef3bdb7e332d2871b309bec1a46e3d1d98533050e723094200dc460f6`.
- `.git` 쓰기·fetch·stage·commit은 하지 않았다. 파일의 충돌 표시는 제거했지만 index의 세 `UU`는
  coordinator가 `git add`하고 병합을 마칠 때까지 남는다.
- GitHub CLI는 연결 오류, connector는 접근 오류로 #223 댓글/열린 PR을 조회하지 못했다.
  사용자에게 전달받은 coordinator 결정과 로컬 remote ref를 적용했다.

## 실행기 연결

- `_LiveTransport`는 core `ModelCallTransport`를 상속하고 호출 시작의 자기 입력 snapshot만 추가한다.
  core가 생성·scheduler에 연결한 동일 `SendLedger`와 `FixtureWire`를 재사용한다.
  `GeminiProxyCompleter`는 offline wire로만 보내므로 실제 HTTP/모델 호출은 없다.
- `finish()`의 `TrialResult.send_ledger`, `study/send_ledger.json`과 trial record를 통해
  wire 전송 수·과금 시도 수·저장 후 재열기 검증을 연결했다. 실제 client 설정 해시와 새 런타임
  의존 파일도 실행 번들에 포함했다.
- 재질문 시간은 자기 작업 유무에 따라 기존 idle/busy 지연을 선택한다. 대기 1개 상한과 타이머
  해제는 core `arm_reask/REASK_POLICY`가 관리하며 integration의 `_reask_at/_on_timer`는 제거했다.
- #223: 사고·대화 비용을 기다리는 동안 진행 중 작업의 macro는 계속 실행된다. 쉬던 로봇은 다음
  행동 해제까지 기다린다. 네 조건에서 실제 host macro loop와 executor API를 이용한 회귀검사를 추가했다.
- 조건 격리, 네 조건 공통 pair status 채널, 자세 제공자 교체 seam과 임시 태그 표시는 유지했다.

## 평가 TOP 경계

- PR #232의 `origin/kiro/zone-eval-topcam` SHA
  `f5ae83a3c795f84d94145821396a06c627d547a9`에서 `git show`로 읽은
  `sim/zone_eval_top.py`만 그대로 가져왔다. 다른 지도·환경 변경은 가져오지 않았다.
  파일 SHA-256: `22512d20f097af908433e91a1c67e0fc0b716e92408423aae7afbc387df9ab6d`.
- corridor 계열은 `zone_eval_top_v2`, 다른 지도는 authored TOP인 `zone_eval_top_v1`이다.
  base-map 해시가 PR #232의 측정 geometry와 다르면 해당 모듈이 거절한다.
- `scene.setup` 뒤 world TOP에만 적용한다. 원본 static map과 executor별 지도는 바꾸지 않는다.
  manifest bundle의 `eval_top_camera`, `eval_only/top_camera.json`의 실제 readback,
  `eval_only/static_map.json`의 평가용 복사본으로 설정을 보존한다.
- 영상 재생 시 `scene.xml`의 원래 카메라 설정만으로 재생하지 말고, 저장된 profile을
  `sim.zone_eval_top.apply_to_world`로 `scene.setup` 뒤 다시 적용한다.
  로봇 요청은 자기 손목 RGB만 사용하며 HostRobotLink는 TOP 요청·TOP으로 표시된 프레임을 거절한다.
- mock world의 적용/readback·손목 카메라 불변, corridor overlay 전후 네 조건 요청 바이트 불변을
  검사했다. 실제 MuJoCo TOP coverage·영상 품질 검증을 대신하지 않는다.

## 검증과 남은 일

최종 명령·개수·소스 해시는 [검증 기록](core-r7-verification.json)에 저장한다.
Python은 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`,
`OMP_NUM_THREADS=1`이고 `--basetemp`는 이 worktree의 `tmp/` 아래다.
실제 MuJoCo를 생성하는 `test_team_host_feeds_each_executor_only_its_own_camera`는 명시적으로 제외한다.

- 통합 전용 검사: **100 passed** (25.49 s).
- 확장 검사: **951 passed, 2 failed, 1 deselected** (212.05 s).
  core 계약·입력·시나리오·프로토콜·평가·offline·review r5/r6/r7, scheduler·SIM 비용,
  integration, executor, own-perception v1/v2, workflow manager를 포함한다.
- 두 실패 중 executor adapter fixture의 `no_llm_scripted`는 계약의 조건이 아니었다.
  `tests/test_zone_own_executor.py`에서 `no_comm`으로 수정하고 해당 검사 **1 passed** (0.76 s)를 확인했다.
- 나머지 `test_parent_exit_cleans_background_child`는 `ps` 실행이
  `PermissionError: [Errno 1] Operation not permitted`로 차단됐다. 제품 실패로 판정하지 않지만
  자식 종료 확인은 이 환경에서 **미확인**이다. 테스트를 삭제·완화하지 않았다.
- 최종 개별 테스트 상태는 **952개 통과 / 환경 제약 1개 / 물리 검사 제외 1개**다.
  한 번의 전체 실행이 모두 통과했다는 뜻은 아니다. 초기 전용 검사 실패와 basetemp 부모 폴더 누락,
  새 테스트의 수치 표현 기대값을 고친 뒤 전용 100개가 통과했고 그 소스로 확장 검사를 수행했다.
- 충돌 표시 0건, `git diff --check` 통과, core 계약과 PR #232 TOP 모듈의 upstream 바이트 일치를 확인했다.

coordinator가 파일을 stage·commit하여 진행 중 병합을 완료해야 한다. `--bundle` 생성은 물리 없이
검증했으며 이전 `prereg_v2.json`의 bundle 해시와 달라졌다. 후속 물리 실행은 새 소스·bundle을
사전 등록한 뒤 coordinator가 배정한다. 기존 스모크 성공·TensorBoard 결과를 새 코드의 결과로
보고하지 않는다. 이번에는 새 물리/평가 결과나 TensorBoard snapshot을 만들지 않았다.
현재 `tags_temporary` 등록 지도에는 corridor가 없다. 실제 corridor 코호트에는 별도의 적합한
자세 제공자/지도/시나리오 등록이 필요하며, 이번 평가 카메라 연결을 그 물리 역량 검증으로 보지 않는다.
