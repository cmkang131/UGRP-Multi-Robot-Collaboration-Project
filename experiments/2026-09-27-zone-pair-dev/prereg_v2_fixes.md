# Pair dev 사전 기록 v2 수정 — 2026-09-27

**tags_temporary, dev, 연구 결과 아님.** PR #235 작업 브랜치
`codex/zone-pair-executor`, 수정 기준 HEAD `1f5c0a412fe207d4de90a63830ab27e881ed7b43`.
이번 변경은 미커밋이며 물리 실행·모델 호출·잠금 획득은 하지 않았다.
dev03/dev04는 `not_run`, 실행 SHA는 코디네이터가 검토·커밋한 뒤 고정한다.
최종 v2 사전 기록 SHA256:
`896091d17022d569dfb34123587712395bf9870d065ce2b438d38acedee9108b`.

## 변경

- [prereg_v2_DRAFT.json](prereg_v2_DRAFT.json): dev03/901, dev04/902.
  기존 v1·dev01 결과·원본을 보존하고 `supersedes`에 v1 바이트 SHA256을 기록했다.
  접촉 프로필 `cargo_noslip_v1`과 `local_contact_fine` 소스는 변경하지 않았다.
- `scripts/zone_pair_dev_contract.py`: 두 프로필의 실제 XML 변환을 정적 option probe에
  적용해 timestep 0.00025초·noslip 10을 유도한다. 프로필 정의 해시, 두 소스 파일 해시,
  파생값을 포함한 계약 전체 해시를 동결한다. MuJoCo import·모델 컴파일·stepping은 없다.
- 드라이버는 프로필/해시·v1 출처·v2 run ID/seed·GT 간격·스텝 수·예산을 검증한다.
  준비 manifest에는 계약과 계산 근거를 복사한다. 실제 모델 적용값은 새 prereg와 비교한다.
- GT는 50 ms = 200 step, 최대 허용 간격은 50.35 ms다. 접촉은 매 0.25 ms step마다
  관측한다. SIM 상한 900초는 유지하며 최대 interval은 450,000 → 3,600,000으로 증가한다.
  실제 관측 interval 수는 시작/끝 차이로 계산하며 초기 관측을 step으로 세지 않는다.
- wall 상한은 7,200 × 8 = 57,600초, 외부 종료 상한은 정리 여유 60초를 더한 57,660초다.
  스텝 수 비율에 따른 보수적 예산이며 실측 속도나 완료 시간 예측이 아니다.
  README는 v2·새 ID·새 출력 경로를 사용하며 외부 timeout과 잠금 예상 분을 JSON에서 읽는다.
- 평가기는 명시적 host 오류를 route/trace/영상 검사보다 먼저 `HOST_ERROR`로 보고한다.
  원래 오류 type/message/ENOSPC를 보존하며 물리 점수는 계산하지 않는다.
  prereg 해시 검증 여부와 누락 증거를 별도로 기록한다. host 오류가 없는 증거 누락은
  `EVIDENCE_INCOMPLETE`로 유지한다. runtime/CLI의 평가 예외 처리도 같은 분류를 사용한다.
  정상 물리 평가는 저장된 prereg의 환경 기준을 사용한다.

## 비물리 검증

기존 `.venv-sim-worker-mac` 환경을 사용했다. 사용자 지시에 따라 잠금 없이 실행했다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_dev.py tests/test_zone_pair_executor.py \
  tests/test_zone_pair_review3.py tests/test_simulation_workflow_manager.py \
  --basetemp=./.pytest_tmp
```

결과: **200 passed, 1 failed, 7.61 s**. 실패는 변경하지 않은
`WorkflowManagerTests::test_parent_exit_cleans_background_child`의 확인용 `ps` 실행이
샌드박스에서 `PermissionError: [Errno 1] Operation not permitted: 'ps'`로 차단된 것이다.
해당 프로세스 정리 검증을 통과로 세지 않았다. `.pytest_tmp`는 삭제했다.
초기 dev 단독 검사에서는 114 pass/1 fail이었고, 남은 합성 fixture의 2 ms 기준
고정 접촉 수를 적용 timestep에서 계산하도록 수정한 뒤 위 검사를 수행했다.

확인 범위: 프로필 유도·변경 감지·해시/예산 불일치 거부, MuJoCo import를 금지한
prepare/help, 0.25 ms fake observer의 200 step 표본 간격·누락 step·정확한 tail,
실제 host 스케줄러/fake world의 정상·abort·적용값 거부 정리,
0.25 ms fake clock의 로봇별 시간 격리, 기존 파지/낙하/문/방출/GO/abort 판정 회귀.
실제 world 생성·물리 stepping·모델 호출은 수행하지 않았다.

최종 JSON 저장 후 dev03/901·dev04/902 모두 표준 workflow plan과 실제 prepare 경로를
MuJoCo import 차단 상태에서 확인했다. 두 manifest 모두 `prepared_not_executed`,
`applied=null`, `model_calls=0`이며 사전 기록 바이트와 프로필 계약이 일치했다.
이 smoke 검사의 임시 receipt는 `/tmp`에서 생성·검증 후 정리했다.

## dev01 읽기 전용 회귀 확인과 보존

원본 위치:
`/Users/changmin/projects/ugrp/outputs/zone-pair-dev-521e5567e4a1d1b0614b86b8bf355e994edca890/dev01`.
원본 실행 SHA는 `521e5567…`이며 이번 수정 기준 HEAD와 구분한다.

`artifacts.sha256.json`의 **14개 파일 크기·SHA256 불일치 0건**.
새 `evaluate_run`에 이 원본을 읽기 전용으로 넣어 다음을 확인했다.

- 새 함수 반환: `verdict=HOST_ERROR`, `physical_success=false`,
  `physical_scoring=not_performed_host_error`.
- 원래 `ValueError: actual model settings differ: ... timestep_s=0.00025` 보존.
- 원본 prereg 무결성: true. SHA256
  `85334a68bae0d35c197c612cd610c84307c0eba268a34247e71f4e233a0fe0f3`.
- 저장된 과거 `eval_only/result.json`의 `EVIDENCE_INCOMPLETE`는 수정하지 않았다.
  새 raw 평가 파일이나 TensorBoard snapshot을 만들지 않았으며 기존 기록을 유지했다.
  이는 오류 분류 회귀 확인으로, 새 물리 결과나 dev01 성공 재판정이 아니다.

`git diff --check` 통과. v1 사전 기록·results.md·두 프로필 소스의 Git diff는 비어 있다.

## 남은 항목

- dev03/dev04 실제 실행, 물리 단계·영상·TensorBoard 검증은 수행하지 않았다.
- 원격 최신 상태 확인은 제한됐다: `git fetch origin`은 공용 `.git`의 `FETCH_HEAD`
  쓰기 차단, `gh pr list/view`는 네트워크 차단. 연결 GitHub 도구도 PR 조회 301 및
  검색 422 오류로 실패했다. 원격 PR·CI·업로드·병합 완료를 주장하지 않는다.
- 커밋·push·병합 없음. Google Drive는 프로젝트 제외 규칙에 따라 사용하지 않았다.
