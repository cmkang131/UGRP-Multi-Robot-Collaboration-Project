# PR #240 main 병합 및 STATUS v5 통합 검증 — 2026-09-27

작업 기준 HEAD `2aedf030c5236a7aa98329acd8367ad6d76743cb`, 병합 대상
`414f8d8f1873e3309e4dc29b4c1c8930ab5c3a53`. 변경은 미커밋 상태이며
`git add/commit`은 수행하지 않았다. 코디네이터가 인덱스와 병합 커밋을 처리한다.

## 충돌 및 기존 실패

`tests/test_zone_start_dock.py`에서 HEAD의 v4 후계 지도/시작 위치 계약 검사와
main의 `registered_tree()` 및 등록 소스 불일치 시 prepare 거부 분기를 함께 유지했다.
v3와 v4를 각각 그 등록 파일로 검사하며, 검토된 main 환경 소스와 v5 드라이버 소스
이외의 차이는 허용하지 않는다. 파일 내 충돌 표시는 제거했고 인덱스의 UU는 의도적으로 남겼다.

병합 전 HEAD를 별도 임시 디렉터리에 복원해 **2 failed, 490 passed**를 재현했다
([로그](before-head.txt)). 실패는 모두
`test_registered_prepare_and_workflow_inputs_without_mujoco_import[dev07/dev08]`다.
v5에서 드라이버 해시가 달라졌는데도 과거 `prereg_v4.json`의 prepare 성공을 기대했다.
이는 **테스트 기대값의 정당한 갱신**이며 드라이버의 엄격한 소스 거부는 올바른 동작이다.
등록 파일이나 실행기의 검사를 느슨하게 하지 않았다.

main 병합으로 v5 등록의 환경 소스와 workflow 파일 해시도 달라진다. 과거 등록의 거부와
동일한 행동 계약을 검사하고, 별도 임시 current-source fixture로 prepare 성공·원문 복사·
물리/모델 import 차단을 검사한다. 이 합성 fixture는 물리 실행 사전등록이나 승인 근거가 아니다.

## 새 통합 버전

main 및 열린 PR #188/#239/#240/#241/#242/#243을 GitHub GET으로 확인했다
([번호 확인](remote_id_audit.json)). RGB runnable 최댓값은 v63, 통합 러너는 v64다.
새 ID는 **`zone-study-integration-v65-pair-close`**, workflow
`zone-study-integration-run`은 **2.0.0**이다.
실제 파지 v5 후보의 프로필은 STATUS `zone_pair_status_v5`, 실행기 `zone_pair_executor_v6_dev`다.
[번들 스냅샷](integration-v65.json)은 실행 없이 생성했으며 digest는
`40b8d4015a68d8709d76f3eead3865878f849a61121f55eff548695d061a1619`다.
소스 closure에 grasp/status/beam_track/align이 포함되고 이들 변이 시 번들 해시가 바뀌는지 검사한다.

기존 번들·사전등록·결과와 기존 지연 fixture 메타데이터 **123개**의 바이트를 확인했다
([해시 목록](preserved.json)). sparse checkout에서 빠진 offline-smoke v3/v4/v5 `.json.gz`
세 파일은 MERGE_HEAD의 정확한 원본 바이트로 복원했다. 과거 기록을 고치거나 결과를 승계하지 않았다.
셸 `git fetch`는 `.git/.../FETCH_HEAD` 쓰기 제한, `gh`는 네트워크 제한으로 실패했다.
GitHub 연결에서 확인한 최신 main은 `97f91cb040bf382973ce84b24b1ca8399e64a6fb`
(#195 TensorBoard 병합)이며 이번 진행 중 병합 대상은 기존 MERGE_HEAD 그대로다.

## 실제 PairTeam + 지연 제공자 결합

기존 지연 테스트는 새 `pregrasp_standoff`에서도 파지 높이 JPEG를 재생해
`PREGRASP_BEAM_UNCERTAIN`으로 거부됐다([이전 로그](before-delay.txt)).
같은 저장 원본의 로봇별 standoff 영상 두 장과 발행 카메라 명령을 해시 검증 후 추가했다.
`tests/fixtures/zone_study_pair_delay/standoff_v5.json`에 출처와 조합 범위를 기록했다.

실제 M2/PairTeam, 실제 태그 PF와 0.16 SIM s 지연, 실제 RGB 빔 인식·안전 guard·상태 장벽을 사용한다.
검출/READY/guard/지연을 stub으로 대체하지 않는다. 서로 다른 시점의 각 로봇 자기 영상을
명시적으로 조합한 프로토콜 회귀이며 연속 물리 궤적이나 물리 파지 성공 검증은 아니다.

- 시차 6 s와 0 s 모두 close READY → 같은 시각 close GO → 동일한 실제 발행 닫힘 PWM 열 → lift GO를 확인한다.
- v4에서 먼저 닫고 기다리던 0 s 조건은 v5에서 양쪽 준비까지 열린 채 기다려 통과한다.
- r2의 standoff 영상이 없으면 r1의 READY가 있어도 GO·닫힘 명령 없이 양쪽이 중단하고 queue가 비워진다.
- PF 교체 뒤 0.16 s 전에는 추정과 close/lift READY가 공개되지 않고, 기존 추정 시각을 현재로 당기지 않는다.

GT 제어, weld, `cargo_noslip_v1`, 안전 임계값, 실제 제어 소스는 변경하지 않았다.
MuJoCo step·실제 모델 요청·물리 실행은 수행하지 않았다. TensorBoard에 추가할 신규 물리/학습/실험 결과는 없다.

## 검증 명령

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/experiments/2026-09-27-zone-pair-dev/merge-main-v65:$PWD" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -p no_physics \
  tests/test_zone_pair_*.py tests/test_zone_start_dock.py tests/test_zone_study_*.py \
  tests/test_simulation_workflow_manager.py --basetemp=./.pytest_tmp
```

`no_physics.py`는 전체 pytest 세션에서 `mj_step`, `mj_step1`, `mj_step2`를 실패 함수로 막는다.
요청 범위 **39개 파일 모두 run_ci_tests.py에 등록**됨을 확인했다([목록](ci_registration.json)).
세부 소스 해시·최종 결과·임시 디렉터리 정리 여부는 [검증 기록](verification.json)에 남긴다.
핵심 회귀는 [114 passed](targeted.txt); 최종 전체 결과는 작업 종료 시 아래에 기록한다.


## 최종 전체 결과 및 남은 검증

**1 failed, 1625 passed in 253.12s** ([전체 로그](full.txt)). 남은 한 건은
`tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_parent_exit_cleans_background_child`다.
이 환경이 `ps` 실행을 `PermissionError: [Errno 1] Operation not permitted`로 차단해
자식 종료 확인을 수행하지 못했다. 테스트를 skip하거나 종료 판정을 완화하지 않았다.
해당 한 검사는 `ps`가 허용되는 코디네이터 환경/CI에서 다시 확인해야 한다.

최종 `git diff --check` 통과, 저장소 충돌 표시 0개, 작업 디렉터리 `.pytest_tmp` 삭제를 확인했다.
HEAD 재현용 임시 소스 복사본과 그 `.pytest_tmp`도 제거했다. 인덱스 UU를 해제하는 `git add`,
commit/push/병합은 수행하지 않았으며, 새로운 물리 실행에는 이 트리의 별도 동결 등록이 필요하다.
