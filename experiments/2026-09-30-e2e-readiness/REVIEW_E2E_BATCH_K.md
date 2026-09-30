# E2E Batch K — 독립 재현 검토

2026-10-01, Codex. 구현 수정 없이 두 PR의 **아래 SHA**를 검토했다.
물리·렌더·실제 비전 추론·LLM 호출 0회, 호스트 잠금 사용 0회다.

| PR | 검토 SHA | 판정 | 범위 |
|---|---|---|---|
| [#338](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/338) | `6df8f1ae6ff36b8a779fb36c1cb1c0ab6548e069` | **MERGE AFTER FIXES** | K1과 정상 CI를 해결한 **P01 수집 경로**에 한정. P03 차단은 유지한다. |
| [#339](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/339) | `eb46383f3bc435d1801f4917034606a885d1f8b6` | **BLOCK** | K2/K3 때문에 현재 연결을 인수할 수 없다. K4와 미구현 absence 때문에 TASKS의 최종 환경 T13 완료 후보도 아니다. |

비교 main은 `55609ed1be4e770019e0640f47c7a2f7f0403f37`(#312 병합 포함).
마지막 fetch의 main은 `f5cd3a2b7754236a7b416cca1e1f9fe76fe8dd14`(#310 추가)이고
두 PR HEAD는 그대로였다. 둘 다 DRAFT/BEHIND이며 이 검토에서 병합하지 않았다.

## 한 묶음의 지적

### K1 — P2, #338: 새 테스트 이름이 기존 수집 검사를 깨뜨림

[scripts/run_ci_tests.py:88](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6df8f1ae6ff36b8a779fb36c1cb1c0ab6548e069/scripts/run_ci_tests.py#L88)에
`tests/test_zone_final_environment_runnable.py`를 추가하면 기존
`tests/test_zone_final_env.py:321–324`의 부분 문자열 검색이 두 항목을 잡는다.
기존 검사는 모든 검색 결과가 자기 파일 하나로만 확장되어야 한다고 단정하므로 실패한다.

- 실제 [CI run 36751911961](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36751911961)의 shard 5/8: **1 failed, 1170 passed, 10 skipped, 280 subtests passed**. 실패는 정확히 `test_ci_collects_this_file`이다.
- 같은 PR 추출본에서 그 테스트를 직접 실행해 같은 AssertionError를 재현했다.
- 두 파일 모두 CI에 수집되도록 유지하면서 기존 검사의 일치 범위 또는 신규 테스트 이름을 고친다. 검사 제외나 `.github/workflows` 수정으로 우회하지 않는다.
- 반례: `test_pr338_preserves_existing_ci_collection_check`.

### K2 — P1, #339: 정상적인 같은 시각의 두 촬영이 로봇을 영구 정지시킴

[harness/zone_target_executor.py:135–143](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/eb46383f3bc435d1801f4917034606a885d1f8b6/harness/zone_target_executor.py#L135)와
[scripts/zone_target_host.py:28–29](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/eb46383f3bc435d1801f4917034606a885d1f8b6/scripts/zone_target_host.py#L28)의 연결에서 발생한다.
상속한 `OwnCamTeamHost._physics_until`은 정기 촬영을 하고(`:398–400`),
`_run_timeline_raw`는 같은 tick에서 매크로가 끝나면 다시 촬영한다(`:481–487`).
포트는 서로 다른 frame ID를 만들지만 SIM 시각은 같다.
`IdentityJobs._validate_frame`의 `captured_at_sim_s <= previous` 검사(`:144`)가 거부하고,
host `_guard`(`:273–279`)가 `slot.dead=True`와 `EXCEPTION:ContractViolation`을 기록한다.
`TargetOwnExecutor.step`의 capture 억제는 호스트의 매크로 완료 촬영을 막지 못한다.

물리 World를 만들지 않고 실제 `TargetStudyHost`의 촬영/매크로 스케줄러,
`TargetOwnExecutor`, RGB 인식기, `TargetRecoveryJobs`를 연결했다.
저장된 own JPEG를 읽고 pose 추론과 카메라 획득/평가 I/O만 fake로 바꿨다.

| 입력 | 결과 |
|---|---|
| t=1.0 정기 촬영 → t=1.2 매크로 완료 촬영, ID 1→2 | `dead=false`, 예외 없음 |
| t=1.0 정기 촬영 → t=1.0 매크로 완료 촬영, ID 1→2 | `dead=true`, `stale/reordered frame or broken evidence chain` |

새 adapter에서 같은 시각의 촬영을 합치거나 다음 시각으로 미뤄야 한다.
동일 시각 영상을 독립적인 두 확인으로 세도록 identity의 시간 검사를 풀면 안 된다.
active target/팔 매크로/정기 촬영이 겹치는 실제 호출 순서를 회귀검사에 넣어야 한다.
반례: `test_pr339_same_tick_macro_capture_does_not_permanently_stop_robot`;
별도 양성 대조 `test_pr339_later_macro_capture_is_accepted`는 통과한다.

### K3 — P1, #339: 기존 workflow pin을 다시 써서 바이트 보존 조건을 위반

[configs/simulation_workflows.json:771](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/eb46383f3bc435d1801f4917034606a885d1f8b6/configs/simulation_workflows.json#L771)에
새 row를 넣으면서
[experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json:412](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/eb46383f3bc435d1801f4917034606a885d1f8b6/experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json#L412)의
기존 pin을 `d0b0d57f…0be140`에서 `0a3ef3ac…bfc3e2`로 바꿨다.
이 등록이 **미실행 DRAFT**라는 설명은 맞지만, 이번 요청의 기존 pinned bytes 보존을 충족하지 않는다.
역사적 v6/v6b/v6c/v6d 봉인이나 기존 제어기 파일까지 바뀌었다는 뜻은 아니다.

요청된 두 source-pinning 파일의 **56개 검사는 통과**한다. 현재 파일에 맞춰 pin도
바꾸면 통과하는 검사이므로 이전 기록 보존의 충분조건이 아니다.
추가로 기존 바이트 보존 검사 세 묶음을 실행하면 **13개 모두 실패**한다.
실제 [CI run 36754371662](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36754371662)도
shard 6/8에서 12개, shard 7/8에서 1개가 같은 원인으로 실패했다.

- `tests/test_review_325b.py`: 원 등록 바이트 검사 7개.
- `tests/test_zone_own_executor_color_seals.py`: 원 등록 바이트 검사 5개.
- `tests/test_seal_v2_review_301.py`: v6e 원 등록 보존 1개.

기존 catalog와 등록 파일을 복구하고 #338의 추가 catalog 경로와 조율하여 새 workflow를
등록한다. 새 후보의 bundle/source 검사와 관련 CI를 다시 수행한다.
원 pin을 다시 계산하거나 기존 보존 검사를 약화시키는 수정은 해소가 아니다.
반례: `test_pr339_preserves_existing_preregistration_bytes`.

### K4 — P1, #339: TASKS의 최종 로봇 환경으로 실행할 수 없는 후보

[configs/t13_target_checks.json:6–8](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/eb46383f3bc435d1801f4917034606a885d1f8b6/configs/t13_target_checks.json#L6)은
`masterpi_v2` / `zone_wide_door_geometry_v2` 개발 진단을 선택하고,
`scripts/zone_target_bundle.py:21–22`도 v2만 허용한다.
TASKS 공통 계약(`experiments/2026-09-30-scenario-capabilities/TASKS.md:13`)은
최종 3D 로봇 모델을 요구한다. geometry_v2 지도에 이미 있는 walls_v3를
MasterPi 로봇 모델 v3로 혼동하면 안 된다.

PR 문서가 이 제한을 공개한 것은 적절하며 허위 물리 성공 주장은 발견하지 않았다.
그러나 이 명령을 TASKS T13a/T13b의 최종 환경 인수 명령으로 사용할 수는 없다.
실제 v3 provider/보정/skill 조합과 새 후보 인수가 남았다.
반례: `test_pr339_t13_handoff_uses_required_final_environment`.

## 요구별 확인 범위

| 항목 | #338 | #339 |
|---|---|---|
| TASKS 대응 | T01/P01의 새 v3 세 지도 정적 연결·정지 수집 경로. P03와 원본 6시나리오 전체 임무는 미완료 | T13a의 specific cue/track/job 연결과 T13b의 취소/재관측 연결은 부분 구현. K2/K4, pickup 영역 clear-empty/`OWN_PICKUP_ABSENT` 미구현으로 완료 아님 |
| 번호 | `zone-final-environment-v84`, 2.17.0 | `zone-target-v85`, 2.18.0 |
| 번호 중복 | 최초 main+열린 PR 22개, 마지막 main+열린 PR 21개에서 v84/v85 및 2.17.0/2.18.0 충돌 없음. RGB RUNNABLE_ID는 v63 유지 | 같은 조사. 정확한 ref/SHA는 evidence에 연결 |
| 과거 번들 | main의 기존 RGB bundle JSON **65/65 byte-identical**, 기존 v6e source pin **85/85** 유지 | 기존 RGB JSON **65/65 동일**. v6e source **84/85 동일**, K3의 catalog/pin 변경 |
| 보호된 두 테스트 | 파일 diff 0, PR tree에서 **22+34 passed** | 파일 diff 0, PR tree에서 **22+34 passed**. K3 별도 검사 실패와 구별 |
| `.github/workflows` | 시작/마지막 origin/main과 직접 tree diff 0, PR diff 0 | 동일 |
| 표준 실행 진입점 | `sim_cli` → `workflow_manager.catalog` → 기본 catalog+`configs/simulation_workflows.d/final_environment_v84.json` → runner. 기존 기본 catalog 보존 | `sim_cli` → `configs/simulation_workflows.json` → runner. 직접 runner의 plan도 확인 |
| 입력 경계 | P01은 학생 제어 없음. 보정 schedule은 사전 고정 명령이며 GT/camera/contact는 eval_only에 기록. 새 provider는 own RGB·own command·고정 지도/보정만 받음 | recognizer는 own JPEG/발행 servo 명령, pose는 own provider. 특정 item은 위치 없는 공개 visual catalogue와 영상 cue로 연결. event/holder/접촉/peer private state는 controller 인자로 연결되지 않음 |
| 모호성/identity | 해당 없음(P01 무제어) | public same-color duplicate, visible duplicate, partial/unsupported cue, black/stale/foreign/forged frame 거부 및 취소 검사 통과. 실제 조건의 인식 정확도 증명은 아님 |
| 네 통신 조건 | P01에 조건별 controller 없음. P03는 아직 실행 불가 | 동일 controller/config/센서/자기 기억, 조건별 제어 override 없음. 현재 actor는 모든 label에서 같은 scripted/no-message 경로이므로 통신 효과 검증은 아님 |
| 숨은 사건 | P01 해당 없음 | 원본 s5 30초/62.5초·배치·공개 주문 보존. held/unheld 네 effect/no-op fake 분기 검사 통과. GT 효과는 평가에만 기록 |
| 물리 성공 주장 | 없음. `COLLECTED_UNQUALIFIED`, `physical_success=null`; P03 `runnable=false` 확인 | 없음. 고정 horizon `CAP`, `physical_success=null`; H 미성립/no-op를 따로 보고하도록 인계 |

입력 경계 결론은 읽은 호출 경로와 오프라인 fixture 검사 범위다. 실제 worker의 새 환경
정확도, 물리 파지·복구·완주, 네 조건의 실제 메시지 수신이나 효과를 입증하지 않는다.

## 직접 재현한 검사와 인계

| 검사 | 결과 |
|---|---|
| #338 신규 환경 tests | 30 passed |
| #338 보호된 두 source tests + manager | 73 passed, 프로세스 `ps` 의존 기존 child-cleanup 검사 1개는 로컬 제외 |
| #338 provider lifecycle | 28 passed |
| #338 기존 CI collection 검사 | 1 failed, K1 |
| #339 관련 오프라인 묶음 | 224 passed, 실제 world host 검사 1 skipped; physical step/실제 worker/network 시도 0 |
| #339 보호된 두 source tests 재확인 | 56 passed; 위 224와 중복이므로 합산하지 않음 |
| #339 기존 registration 보존 검사 | 13 failed, K3 |
| #338 작성자 mutation을 독립 재실행 | **11/11 검출**, 각 목표 pytest exit 1, 소스 복원 확인 |
| #339 작성자 mutation을 독립 재실행 | **8/8 검출**, 목표 pytest 실패 및 디스크 소스 불변 확인 |
| 리뷰 반례 | **1 passed, 4 strict xfailed**; `--runxfail` 시 **4 failed, 1 passed** |

두 CI 실패 모두 설치 timeout이 아닌 assertion 회귀다. #333의 과거 10분 설치 timeout을
이번 후보의 결함이나 면책 근거로 사용하지 않았다.
변이 검출은 지정한 19개 제거/변경에 한정하며 K2 같은 통합 누락까지 모두 검출했다는 뜻은 아니다.

두 `PHYSICS_HANDOFF.md`에 실제 `sim_cli workflow run`·세션·잠금·출력 명령이 있다.
리뷰에서는 `workflow plan`과 runner의 **비실행 plan만** 직접 실행했다.

- #338: P01 3×30=90 SIM초, reset 각 최대 5초 포함 최대 105초. unloaded 보정은 별도 3×120=360초, reset 포함 최대 375초다. P03 3×120초는 지도 수가 아닌 연속 leg를 포함한 체크포인트 수이며, 측정 보정과 v3 pair adapter가 없어 실제 실행은 거부한다. 가상 성공 명령으로 포장하지 않았다.
- #339: T13a I1/I2=2×900=1800초, T13b M-U/M-H/D-H/D-U=4×900=3600초. setup/관측/대기/복구를 포함하며 원본 사건 시각을 바꾸지 않는다. 이 후보의 명령은 **v2 개발 진단**이다. 최종 환경 명령이라는 인수는 K4로 차단한다.
- 새 물리/훈련/평가 cohort가 없어 TensorBoard 변환·대시보드 생성은 하지 않았다. 두 인계 문서에는 실제 자료 회수 뒤 실패/no-op도 포함한 native TensorBoard snapshot과 raw hash 확인 절차가 있다.

## 재현 방법과 기록

PR 소스는 `git archive <위 SHA> | tar -x -C <개별 임시 폴더>`로 추출했다.
`git worktree add`를 사용하지 않았다. 역사적 blob 검사를 위해 추출 폴더마다 독립적인
임시 `.git`을 초기화하고 기존 object DB를 read-only alternates로 참조했다.
archive의 export-ignore 미디어는 물리 자료로 사용하지 않았다.

초기 #338 실행에서 `GIT_DIR/GIT_WORK_TREE`를 export한 방법이 temporary `git init` 테스트와
충돌했다. 이로 생긴 shared `core.worktree` 한 항목을 즉시 제거하고 두 실제 checkout의
경로·HEAD·깨끗한 상태를 확인했다. 격리된 `.git` 방식으로 해당 검사와 source/manager
묶음을 재실행해 **73 passed**를 확인했다. 이 초기 harness 실패는 PR 결함으로 세지 않았다.
#339의 첫 시도는 그 트리에 없는 `offline_guard` plugin 이름으로 시작하지 못했고,
실제 제공되는 `tests.pose_provider_no_physics`로 바로잡은 실행만 결과로 셌다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
# PR338_TREE/PR339_TREE는 위 SHA의 별도 archive 추출 폴더.
REVIEW_E2E_K_PR338_ROOT="$PR338_TREE" REVIEW_E2E_K_PR339_ROOT="$PR339_TREE" \
  "$PY" -m pytest -q -rx tests/test_review_e2e_batch_k.py
REVIEW_E2E_K_PR338_ROOT="$PR338_TREE" REVIEW_E2E_K_PR339_ROOT="$PR339_TREE" \
  "$PY" -m pytest -q --runxfail tests/test_review_e2e_batch_k.py
```

후보 소스를 지정하지 않은 notes branch에서의 skip은 검증 통과가 아니다.
수정되면 strict XPASS가 실패로 드러나도록 했으며, 재검토 후 해당 xfail을 제거해야 한다.

원 로그·JUnit·두 CI 실패 로그·번호 조회·계획 JSON·변이별 출력은
`/Users/changmin/projects/ugrp/outputs/review-e2e-batch-k/`에 보존했다.
[검증 요약과 파일 해시](REVIEW_E2E_BATCH_K_EVIDENCE.json)를 함께 커밋한다.
raw는 로컬 보관이며 원격 백업을 주장하지 않는다. Drive는 사용하지 않았다.
검토용 `/private/tmp/ugrp-review-e2e-k-bwbc55kq` 추출 디렉터리는 검증 후 삭제하고 부재를 확인했다.
