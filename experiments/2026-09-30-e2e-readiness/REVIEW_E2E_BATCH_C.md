# E2E 준비 PR #310·#311·#312 독립 반례 검토

검토자: Codex, 2026-09-30. 변경 구현과 분리한 검토다. **물리·시뮬레이션·렌더·추론·LLM 호출 0회**이며 병합·봉인·실행 승인이 아니다. 리뷰 브랜치 `codex/review-e2e-batch-c`에는 검토 문서만 추가한다.

## 판정과 고정 소스

| PR | 검토 HEAD | 판정 | 핵심 이유 |
|---|---|---|---|
| #310 T10a | `2bfb9dce5655f2a71e62ab700281cc5258abb40b` | **MERGE AFTER FIXES** | 정적 기하 계약은 유용하지만 기존 복도 진입의 `StopIteration` 제거 기준은 충족하지 못함 |
| #311 P07 | `bd011c997f9f7946de28f912dbdd3833ebb33988` | **MERGE AFTER FIXES** | 실행 차단은 유지됨. #312와 합성할 때 실제 P03 조합 파일이 계획 해시에 빠짐 |
| #312 P03 | `919f78ef6ebaf2495633338bcb1b9510f46399bd` | **BLOCK** | 현재 v6e 소스 계약과 기존 회귀 검사를 깨뜨림. 이관 또는 별도 버전 없이 단독 병합 불가 |

기준 `origin/main`은 `c12796676802ab54cad2f0635e3e96e911691c76`이다. AGENTS.md, README.md, docs/current_status.md, CONTRIBUTING.md와 P03/P07 완료 기준을 읽었다. main의 `task_prompts/`에는 **T10a 파일이 없다**. #310 본문이 가리킨 #302의 `experiments/2026-09-30-scenario-capabilities/TASKS.md:101–106`과 REQUIREMENTS.md를 사용했다. #302 HEAD는 `bd95530a2d5a8b8467620809749273068a7ed55d`이며 아직 draft다. T10a를 main에 병합된 프롬프트라고 취급하지 않았다.

심각도: BLOCKER는 현재 병합을 막는 회귀, MAJOR는 완료 기준/출처 계약의 필수 수정, MINOR는 비차단 보완이다. 확인된 지적은 아래 **BLOCKER 1건, MAJOR 2건**이다. 기존 물리 성능은 재평가하지 않았다.

## #310 — MAJOR C310-1: 새 거절 함수가 실제 생성 경로에 연결되지 않음

**근거:** #310 `harness/zone_corridor_contract.py:30–39`, `tests/test_zone_own_executor_corridor_contract.py:43–68`; 같은 HEAD의 `harness/zone_own_team_host.py:141–149`, `harness/zone_own_executor.py:134`.

`create_own_executor()`는 문이 없으면 `CORRIDOR_RUNTIME_UNSUPPORTED`를 먼저 내지만, 실제 host는 여전히 `ZoneOwnExecutor(...)`를 직접 생성한다. 그 생성자는 `next(... kind == 'door')`에 기본값이 없어 corridor-only 지도에서 `StopIteration`을 낸다. 새 factory를 쓰는 생산 호출자는 없다. PR 설명도 이 잔여 문제를 T10b로 넘겼다고 명시한다.

T10a의 별도 요구는 corridor-only 지도에서 이 예외를 제거하는 것이다. T10b의 실제 주행 구현까지 요구하는 지적이 아니다. 현재처럼 미지원이면 **실제 선택 경로에서 부작용 전에 명시적으로 거절**해도 된다. 기존 봉인 파일을 임의로 고치지 말고, 새 버전 진입점 또는 상위 admission에 연결하고 그 호출 경로를 fake로 검사해야 한다.

**반례:** 기존 executor fixture의 정적 지도에서 passages만 `corridor_1`로 바꾸고 기존 own pose를 주입한다. `UnsupportedCorridor`를 기대하면 실제로는 `zone_own_executor.py:134`의 `StopIteration`으로 실패한다. 새 테스트의 `test_legacy_factory_refuses...`는 새 factory만 호출하므로 이 결함을 잡지 못한다.

그 외 정적 검사는 의미가 있다. 전체 편대의 앞뒤 끝이 통로를 지난 경우와 mouth 방문을 구별하고, 얇은 벽·yaw 중간 sweep·bay 경계 여유·물건만 회전 가능한 반례를 포함한다. pair+solo 3대와 2pair 4대를 분리하며 static reverse PASS를 동시 교행으로 승격하지 않는다. 생성된 제안은 실제 robot belief나 물리 통과 증거가 아니다.

| T10a 요구 | 확인 |
|---|---|
| 문 없는 지도 안전 처리/기존 StopIteration 제거 | 새 factory만 충족, 실제 생성 경로 미충족 |
| 원판·물건 회전·양방향 pose path 분리 | 충족 |
| bay 정지·대피·재진입·전체 편대 회전 | 충족; 불명한 제안은 unsupported, pair 자동 수용 없음 |
| pair+solo 및 2pair 팀 크기 구별 | 충족; 동시 교행은 계속 unsupported |
| private 입력 비간섭·물리 0 | 신규 API/시험 범위에서 충족 |

## #311 — MAJOR C311-1: #312의 실제 P03 pin을 계획 해시에 포함하지 않음

**근거:** #311 `harness/zone_e2e_manifest.py:29–30,40–54,383–405`, `tests/test_zone_e2e_manifest.py:156–188`; #312 `scripts/run_zone_study_integration.py:79–86,384–390`, `harness/vision_loc_protocol.py:138–169`.

P07은 P03을 기존 `pose_providers.json`으로만 읽고 runner의 `RUNTIME_ENTRY_POINTS`/`RUNTIME_ASSETS` 리터럴을 수집한다. #312는 `runtime_files()` 내부의 **지역 변수 assets**에 `configs/vision_loc_provider_p03.json`을 추가하고, 이 JSON을 실제 provider identity/run bundle에 넣는다. AST import closure는 이 데이터 파일을 자동 추적하지 않는다. 따라서 두 PR이 충돌 없이 합쳐져도 P07의 runtime/evidence/planner pin 어디에도 새 JSON이 들어가지 않는다.

**합성 반례:** #311+#312의 임시 소스에서 draft를 만든 뒤, P03 JSON의 `active.camera.intrinsics_mount`만 변경한다. 실제 `runner.run_bundle()` 해시는 바뀌지만 P07 draft 해시는 그대로다. 이는 P07 완료 기준 2의 모델·로봇·카메라·보정 조합 해시 연결이 빠진 경우다. 파일 변경과 함께 저장된 draft를 재검사하는 테스트가 필요하다. 현재 `test_changed_runtime_or_planner_source...`의 대상 목록에는 새 P03 파일이 없으며 `test_existing_provider_allowlist...`는 예전 registry만 확인한다.

**수정:** P03 소유 JSON 및 그 참조 자산을 명시적으로 읽고 hash에 연결한다. 지원 조합을 추가하는 것과 실행 승인/physical_ready는 분리한다. #301의 새 의존성 계약을 채택하더라도 JSON 입력 선언 자체는 필요하다.

이 결함으로 현재 물리 실행이 허용되지는 않는다. `check_draft()`는 `runnable=false`, `physical_ready=false`, 승인·봉인 null을 재검사하며 23개 claim의 완료를 모두 거절한다. CLI에는 execute가 없고 정상 draft도 미충족 관문 때문에 종료 코드 3이다. 안전 차단을 해제하라는 지적이 아니다.

| P07 완료 기준 | 확인 |
|---|---|
| dev 4+4, 정식 no-LLM 24, 외부 pilot 72 분리 | 충족; cohort·claim·분모·leader 균형 검사 있음 |
| 실행 조건 전체 hash/P01·P03 지원 조합 | 부분 충족; 새 P03 JSON 누락, 최종 v3 조합은 의도대로 차단 |
| 23개 claim의 소스/시험/결과/조건/미측정/승인 | 충족; #292/#293/M1/M2 공백을 성공으로 바꾸지 않음 |
| dry-run 부작용 없음·잘못된 입력/거짓 완료/raw 재사용 거절 | 검사 범위에서 충족; network/process/World/DB/write sentinel 있음 |
| 코디네이터 봉인·번호·비용·잠금·디스크·sim_cli 후속 | 충족; v83/2.16.0 사용 또는 예약 없음 |

212,250 SIM초와 raw 목적지 228개는 **제안 상한과 경로 목록**이다. 실행/생성된 raw/완료된 cohort로 세지 않는다. P02 개발 시나리오와 C6 새 seed의 등록도 아직 필요하다.

## #312 — BLOCKER C312-1: 현재 v6e 소스 계약을 깨뜨리고 이관하지 않음

**근거:** #312 `harness/vision_pose_source.py:135–159,192–225`, `harness/zone_study_pose_delay.py:151–169`, `scripts/run_zone_study_integration.py:79–86`; 그대로 남은 `experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json:377,383–384`, `scripts/zone_pair_v6_contract.py:284–286`, `tests/test_zone_pair_registered_source.py:109–120`.

현재 main의 v6e DRAFT가 고정한 다음 3개 파일은 main에서는 등록 해시와 같고 #312에서는 모두 달라진다.

- `scripts/run_zone_study_integration.py`
- `harness/vision_pose_source.py`
- `harness/zone_study_pose_delay.py`

PR은 등록 JSON bytes를 보존했지만, 기존 현재-source 검사는 여전히 v6e를 요구한다. 그 결과 `test_v6e_records_current_scene_and_full_source_closure`가 실패하고 기존 v6e prepare도 `v6 source contract/hash mismatch`로 거절된다. 이는 **과거 raw/성공 판정을 몰래 수정하는 문제는 아니며, 검사가 닫힌 채 실패하는 현재 경로 회귀**다. 기존 검사를 삭제하거나 JSON의 hash를 새 코드로 덮어써서 해결하면 안 된다.

검토 HEAD `919f78ef...`의 GitHub CI 로그도 같은 문제를 확인한다.

- [shard 0](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36711579154/job/109874386641): `test_registered_sources_are_not_touched_by_this_change`, `AssertionError: scripts/run_zone_study_integration.py`.
- [shard 4](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36711579154/job/109874386448): 현재 v6e 검사 1건과 stale/inherited 계약 검사 4건 실패. 로그의 checkout SHA도 검토 HEAD와 같다.

**수정:** 기존 bytes와 과거 source commit 감사는 보존하면서 별도 버전/명시적 이관을 하거나, 이관을 포함한 선행 PR 의존성을 선언하고 그 위에서 재검사한다. #292에는 v6e를 역사 자료로 옮기는 처리가 있으나 **아직 main에 없으며**, #312의 단독 CI/병합 안전성을 대신하지 않는다. #292를 합쳤을 때도 새 provider 동작을 포함한 후보 hash와 인수 범위를 다시 고정해야 한다.

P03의 신규 fake 검사는 자체로는 의미가 있다. PF 입자/가중치/scale/RNG와 명령·servo clock을 비교하고, 대기 중 명령을 재측위가 지우는 반례, 지난 frame이 현재 PF의 가중치를 바꾸는 반례, prior 재주입·중첩 지연·worker 오류·close 정리를 검사한다. 다만 보고한 선별 suite에는 위 현재-v6e 검사 파일이 빠져 있어서 이 병합 회귀를 놓쳤다.

| P03 완료 기준 | 확인 |
|---|---|
| own dock prior 최초 1회와 출처 기록 | 구현·fake 검사 있음; runtime 뒤 재주입 거절 |
| 단계 사이 PF/clock/분산/servo 연속성·bad fix 거절 | fake 입력과 M2 p20 adapter 경로 검사 있음; 실제 이전 leg의 posterior 정확도는 미측정 |
| 0.16 SIM초 wrapper/worker 비용 구별 | 명시적 계약과 중복 지연 검사 있음; 실제 wall 지연을 성능 증거로 세지 않음 |
| 조합 pin·C_mix_rgb opt-in 준비 | 기존 v2/seg-v2만 pin, C_mix_rgb 미배포·비선택·최종 보정 미검증 유지 |
| 3체크포인트×120 SIM초/Release/최종 보정 후속 | README에 남김; 이번 검토에서도 실행하지 않음 |
| 기존 결과/봉인 경로 보존 | raw·등록 JSON bytes는 보존, 현재 v6e 소스 계약은 깨짐 — C312-1 |

## 입력 경계·기본값·상호 충돌

변경된 코드에서 새 GT/측정 관절/접촉/심판 성공/상대 실시간 정보가 controller나 성공 신호로 흐르는 경로는 찾지 못했다. 이는 저장소 전체 또는 실제 모델 요청의 입력 경계 인증이 아니다.

- #310은 정적 지도·catalog·호출자가 제안한 pose/역할만 검사한다. private setup/event를 읽지 않으며 host가 양보자나 파트너를 정하지 않는다. 향후 caller가 이 API에 GT pose를 넣지 않는지는 T10b 통합에서 다시 검사해야 한다.
- #311이 scene/setup·평가 파일을 읽는 것은 실행 없는 계획 hash 감사다. 학생에게 전달하지 않으며 unit/hash를 physical_ready로 올리지 않는다.
- #312 fake worker는 자기 이미지 관측만 받는다. runtime 재측위에 B1의 GT 근처 새 PF/교사/oracle 보정을 넣지 않는다. 최초 own dock의 기존 setup 경계를 유지한다.
- 세 PR에서 weld ON, 물리 설정 변경, 기존 s1–s6/raw/model/등록 JSON의 덮어쓰기는 없다. #310/#311은 공용 controller 기본값을 바꾸지 않는다. #312는 기존 provider ID의 공용 동작과 identity를 바꾸므로 새 버전 및 계약 이관이 필요하다.

비교한 열린 PR: #292 `3c4fe30e2197518443b195392212b0341507ac59`, #299 `c86d9bac62036904ecc641db5e59e79edb58dec2`, #301 `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`. #299의 실제 base는 `claude/b-v6h-gain`이며 main 기반 독립 PR로 오인하지 않았다.

| 조합 | 확인/남은 일 |
|---|---|
| #310/#311/#312 사이 3쌍 | `git merge-tree --write-tree --name-only` 텍스트 충돌 없음. #311+#312에는 C311-1이 남음 |
| 각각과 #292/#299/#301, 9쌍 | 같은 검사에서 텍스트 충돌 없음. merge나 새 worktree를 만들지 않음 |
| #310 ↔ #292 | 파일 중복 없음. 기하 PASS는 #292 인수/봉인이나 복도 runtime 승인이 아님 |
| #312 ↔ #292 | source-pinning test를 함께 변경하지만 자동 합성 가능. #292의 v6e 역사 이관은 C312-1의 가능한 선행 작업일 뿐, provider 인수/새 후보 고정을 면제하지 않음 |
| #311 ↔ #292/#299 | P07의 72회는 6시나리오×3seed×4조건 외부 pilot. #292/#299의 60+12 배치/분류 증거와 ID·분모·성공 claim을 합치면 안 됨. 현재 PR은 합치지 않음 |
| #311/#312 ↔ #301 | #301은 신규 계약 v2용이고 기존 whole-file 봉인을 자동 이관하지 않음. P03 JSON·worker·보정·최종 classifier를 명시적 자산으로 포함해야 함 |
| 공용 CI 목록 | #311/#301과 #292 및 #299의 상속 변경이 같은 파일에 있으나 텍스트 충돌 없음. #310은 기존 `test_zone_own_executor*.py`, #312는 `test_vision_loc*.py` glob에 포함됨 |

텍스트 충돌 검사는 합성 제어기 테스트나 물리 인수 재생을 대신하지 않는다. no-physics 요청에 따라 인수 재생은 하지 않았다.

## 독립 검증 기록

소스는 PR remote ref를 fetch한 뒤 `git archive`로 `/tmp/ugrp-review-e2e-c/{310,311,312}`에 추출했다. 새 Git worktree, checkout 전환, 대상 PR 수정은 없다. #311+#312 합성본도 임시 디렉터리만 사용했다. 기존 Python 3.12.13 환경과 공용 `outputs/agent-locks`를 사용하고 MuJoCo/torch/실제 worker/network 접근을 guard로 막았다. 다른 소유자의 살아 있는 잠금은 기다렸고 해제하지 않았다.

| 검사 | 독립 실행 결과 |
|---|---|
| #310 `tests/test_zone_own_executor_corridor_contract.py` | **31 passed** |
| #311 `tests/test_zone_e2e_manifest.py` | **110 passed** |
| #312 `test_vision_loc_provider_lifecycle.py`, `test_zone_pair_provider_init.py`, `test_zone_study_source_pinning.py` | **81 passed, 1 deselected**; 실제 예산 DB를 만드는 기존 speech-cap 검사 1건 제외 |
| #312 기존 `test_v6e_records_current_scene_and_full_source_closure` | **1 failed**, C312-1 재현 |
| #310 기존 생성 경로 반례 | **1 failed**, 예상한 명시적 거절 대신 `StopIteration`, C310-1 재현 |
| #311+#312 P03 JSON 변경 반례 | **1 failed**, 실제 run bundle은 변경됐지만 draft digest는 동일, C311-1 재현 |

합계는 서로 다른 선택 시험 **222 passed**, 결함을 드러내도록 작성/선택한 반례 **3 failed**다. 전체 suite 통과라는 뜻이 아니다. #312의 첫 시도는 archive에 `.git`이 없어 과거 `git show 22c84842...:<M1 calibration/localizer>`를 읽지 못했다(**35 failed, 46 passed, 1 deselected**). 이 실패를 제품 결함에 합산하지 않았다. 해당 suite의 Git 호출이 읽기 전용임을 확인하고 `GIT_DIR=/Users/changmin/projects/ugrp/.git`로 과거 blob 접근만 제공하여 81개를 다시 검사했다. 소스나 등록 파일을 수정하지 않았다.

공용 잠금 PID 12268/14828의 획득·반환과 로그를 보존했다. 시간 기록은 성능 비교가 아니다. 원본 위치는 `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-c-20260930/`이며 **로컬 보관**이다. `run_review.py`, `run_review_round2.py`, `review_guard.py`, `repro_310.py`, `repro_311_312.py`, 최초 실패와 최종 로그, CI 로그 및 고정 SHA/12쌍 합성/3개 source hash 비교를 보존했다. `checksums.json` SHA-256은 `c5013bd0475fb20b0d1e483a613b295e410325c89c215b884dd3585d12ff44db`다. 이 문서만 Git에 올리며 로컬 raw 전체의 원격 백업을 주장하지 않는다.

최소 재현은 고정 HEAD를 archive한 별도 디렉터리에서 위 테스트 파일들을 실행하는 것이다. 물리·실제 worker/network를 막는 guard와 공용 잠금을 유지한다. C310-1 추가 검사의 핵심은 다음과 같다.

```python
old = make()  # tests.test_zone_own_executor의 own-camera fixture
static = copy.deepcopy(MAP)
static['passages'] = [{'id': 'corridor_1', 'kind': 'corridor', 'axis': 'x',
    'center_m': [3.0625, 1.175], 'half_extents_m': [.8625, .25], 'width_m': .5}]
with pytest.raises(UnsupportedCorridor):
    zox.ZoneOwnExecutor('r1', static, CALIB['params'], SHEET,
        pose_source=old.pose, skill_factory=lambda *a: None,
        pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
# actual: StopIteration, harness/zone_own_executor.py:134
```

C311-1은 합성본의 `build_draft(default_options('review-c-unreserved'))`와 `vision_bundle()` fixture의 `runner.run_bundle()`을 각각 전후 비교한다. 중간에 `configs/vision_loc_provider_p03.json`의 `active.camera.intrinsics_mount`만 `changed-camera-unvalidated`로 바꾸고 `finally`에서 원래 bytes를 복원한다. run bundle digest 차이는 확인되지만 draft digest는 양쪽 모두 `261e2b3d810827fcfc64ef53af75f8f318f4f04ecf138bf922d954a5db75d342`였다. 합성본 외의 파일은 바꾸지 않았다.

새 학습/물리/평가 cohort가 없어 TensorBoard snapshot이나 서버를 만들지 않았다. UGRP 예외에 따라 Drive 조회·업로드도 하지 않았다. 이 리뷰 및 반례는 E2E 성공/실물 검증 결과가 아니다.
