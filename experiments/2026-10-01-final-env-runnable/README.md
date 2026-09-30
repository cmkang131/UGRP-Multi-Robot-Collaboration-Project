# 최종 v3 환경 v84 — P01 실행 등록, P03 차단점

**DRAFT, 미봉인. P01 3×30 SIM초와 unloaded 보정 수집 경로를 등록했다.
P03 3×120 SIM초의 실행 가능화는 미완료다.**
물리·SIM·렌더·실제 비전 추론·학습·LLM 실행은 모두 0회다.
fake/offline 검사는 호스트 잠금 없이 수행했다.

작업 브랜치는 `codex/integ-final-env-runnable`, 구현 커밋은
`fb58f977`이다. P03 #312의 `b38c1d59`를 먼저 병합했고, 추가 커밋
`71563e88e2bd72c6abf90d50e10f5f627fea2a9b`도 병합 커밋 `8ff4efbc`로 반영했다.
소스·검증 파일 해시와 최종 검사 결과는 [verification.json](verification.json)을 따른다.

## 구현과 실행 경계

- 새 `zone-final-environment-v84` / `zone-final-environment-check` 2.17.0을
  표준 `sim_cli`에 추가했다. 기본 catalog는 기존 봉인에 고정돼 있어 바이트를 유지하고,
  표준 관리자가 추가 catalog 파일도 읽고 hash·중복 ID를 검사하도록 연결했다.
- 기존 `zone_wide_door_geometry_v3`를 그대로 사용하고, 두 문·복도는 기존 정적 부모에서
  새 v3 파일로 분리했다. 새 provider allow-list는 이 3종의 map/model/parent/hash를 검사한다.
- 정적 v3 camera/model/map 보정 계약을 추가했다. 실측값은 null이다. 별도 고정 측정 파일과
  외부 hash가 있어야 새 provider를 구성하며 v2 camera FK·motion 값을 자동 승계하지 않는다.
  미측정 팔 자세는 추정치를 재사용하지 않고 실패로 닫는다.
- P01은 표준 Scene reset 뒤 지도마다 정지 30초를 수집한다. reset은 각 최대 5초,
  총 상한은 105초다. unloaded 보정은 별도 3×120초, reset 포함 최대 375초다.
  실제 engine 생성 중 step에도 상한을 적용한다. 자기 PNG·명령은 보존하고
  좌표·camera label·접촉은 `eval_only/`에만 저장한다.
- 수집 실패는 `HOST_ERROR`, 미시도 사례는 `unattempted`로 남겨 분모 3을 유지한다.
  종료 때 자신이 만든 자원을 닫는다. 새 출력 폴더의 부모도 생성하며 기존 결과는 거부한다.
  수집 완료 표시는 `COLLECTED_UNQUALIFIED`이며 환경 적합이나 운반 성공 판정이 아니다.

## 요청을 완전히 해소하지 못한 이유

`harness/zone_own_team_host.py:84`는 v3 pair executor를 명시적으로 거부한다.
기존 M2 pair 실행기는 v2 arm 기하·파지·drive 보정에 의존하며,
새 provider allow-list만으로 이 실행기를 v3로 이관할 수 없다.
해당 파일과 관련 봉인 소스는 수정하지 않았고 차단을 우회하지 않았다.

현재 P03는 `runnable:false`다. v3 loaded/fine/pan/camera 실측과 별도 v3 pair
adapter를 연결해야 실제 이전 leg부터 문 앞·문 뒤·목적지 전까지 각 120초를
실행할 수 있다. unloaded 수집 CLI는 제공하지만 loaded/fine 수집 경로·fitting·
P03 chain adapter는 아직 없다. 보정 파일만 채워도 이 차단이 해소되지는 않는다.
P03에 성공하는 것처럼 보이는 가상 실행 명령을 제공하지 않는다.

정확한 P01 명령, unloaded 측정 명령, P03 3체크포인트의 상한·현재 거절 조건·
후속 연결 요건은 [PHYSICS_HANDOFF.md](../../PHYSICS_HANDOFF.md)에 기록했다.
이번 PR은 전체 gap 해소나 P03 물리 실행 준비 완료로 병합하면 안 된다.

## 번호 확인과 보존

선택 전 main+열린 PR 27개, push 전 main+열린 PR 22개를 조회했다.
RGB `RUNNABLE_ID` 최대 v63, 관련 실행 번들 최대 v83(#292),
통합 workflow 최대 2.16.0을 확인해 v84/2.17.0을 선택했다.
[최초 조회](reservation_scan.json), [재조회](reservation_recheck.json)에 SHA를 남겼다.

기존 bundle/봉인/지도/보정 bytes를 덮거나 은퇴시킬 필요가 없어 보존했다.
`.github/workflows`, `tests/test_zone_pair_registered_source.py`,
`tests/test_zone_study_source_pinning.py`를 이 작업에서 편집하지 않았다.
의존 브랜치가 포함한 기존 main 변경과 이 작업의 직접 변경을 구분했다.
raw·모델 삭제/덮어쓰기·Drive 작업·TensorBoard 변환은 하지 않았다.
새 물리 결과가 없어 TensorBoard 대상 cohort도 없다. 실제 결과 회수 뒤의
snapshot·영상·카드 검증은 코디네이터 인계에 포함했다.
`/private/tmp` 추출 디렉터리는 만들지 않았다.

## 검증

검사별 결과와 원본 경로/hash는 [verification.json](verification.json)에 있다.
새 테스트는 MuJoCo/torch/실제 worker/network 접근을 막고,
실제 숫자 PF와 fake 자기 RGB/clock/physics 경계를 사용한다.
물리 결과나 모델의 새 조건 정확도를 검증한 것은 아니다.

- 기존 봉인·P01·P03 소스 검사: 최초 후보에서 124 passed.
- #312 재병합 뒤 provider/manager/평가 경계: 86 passed, 1 deselected.
  제외한 기존 manager 검사는 sandbox가 `ps` 실행을 거부해서 로컬에서만 제외했으며
  정상 CI에는 그대로 남아 있다.
- 최종 환경 검사 30 passed: 새 CLI의 3사례 종료·첫 실패의 미시도 분모·기존 결과 보존을 포함한다.
- 새 catalog가 연결되는 v2 의존성 계약 검사 103 passed.
- [초기 mutation 10/10](mutation_results.json)을 보존하고,
  [최종 검사](mutation_results_postmerge.json)에서는 출력 부모 생성 제거까지 11/11개 변이를 검출했다.
  각 변이는 목표 pytest의 실패(exit 1)로 검출하며 소스를 원래 bytes로 복원한다.
- 초기 테스트 작성 중 count/plan 표본 및 fake 입력 시각 오류는 수정했다.
  CLI의 부모 폴더 누락도 최종 회귀와 mutation으로 검출·수정했다.

재현 예시(새 결과 경로 사용, 호스트 잠금 없음):

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PYTHONPATH=.:experiments/2026-09-30-e2e-p03-provider "$PY" -m pytest -q -p offline_guard \
  tests/test_zone_final_environment_runnable.py tests/test_simulation_workflow_manager.py \
  tests/test_vision_loc_provider_lifecycle.py \
  -k 'not test_parent_exit_cleans_background_child'
"$PY" experiments/2026-10-01-final-env-runnable/mutation_check.py \
  --output /absolute/new/local/mutation-results.json
```

## 참고 자료

- [P03 #312](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/312) — 의존 PR
- [물리 큐 #337](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/337)
- [P01 계획](../2026-09-30-e2e-p01-env/README.md), [실행 버전 관리](../../docs/execution_versioning.md)
