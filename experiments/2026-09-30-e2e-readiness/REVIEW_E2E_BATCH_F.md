# E2E Batch F 독립 검토

검토자: Codex, `codex/review-e2e-batch-f`. 2026-09-30.
작성자들의 구현은 수정하지 않았다. 정확한 후보 SHA를 `git archive`로 `/tmp`에 풀어
검사하며 새 worktree는 만들지 않았다. 물리/SIM step·렌더·모델·외부 provider 호출은 0회다.
아래 판정은 코드 병합 검토이며 E2E/실물/확증 실행 승인이 아니다.

## 기준과 범위

| 대상 | 검토 SHA | 기준 브랜치 |
|---|---|---|
| #320 T13a | `ad63341d13a175582fbe7f5a664ca5bca5a33eaf` | main |
| #323 T07 | `1a17829e79cdf7771ee2d09ca25e444c39cf37be` | main |
| #324 T12 | `c4d680c80f5f8a07c27d5a1edb0acf6683a9f014` | #323, `codex/r3-role-exchange` |
| 비교 main | `ad496486271f441f00eb7d95fbd44dc454999004` | 검토 브랜치 시작 HEAD는 `b10907c5f2c84f2712030f48fb38061fd4f51281` |
| #292 | `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` | `codex/pair-v6h-register` |
| #299 | `8a1631b9cf6f9d658961fcb80339539e87541d3d` | `codex/v6h-classifier-fixes`, base `claude/b-v6h-gain` |
| #301 | `e25d7509d78af711b9a33ae62bd5c103a425200e` | `codex/seal-dependency-decouple` |

`AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`를 확인했다.
main의 `task_prompts/`에는 P01–P09가 있고 T07/T12/T13a 개별 파일은 없다.
P09가 만든 [실제 과제 원문](https://github.com/kcm0127-dotcom/ugrp/blob/5d31f6c822a569b195ad7d0ea15a7d95de840974/experiments/2026-09-30-scenario-capabilities/TASKS.md)
의 공통 계약 및 T07(66–72줄), T12(127–133줄), T13a(135–141줄)를 적용했다.
원문은 물리 검증을 별도 작업으로 명시한다. 이번 검토에서 물리를 실행하지 않은 사실 자체를 구현 결함으로 세지 않았다.

## 판정

| PR | 판정 | 이유 |
|---|---|---|
| #320 | **MERGE** | 독립 opt-in 논리 모듈 범위에서 차단 결함 없음. 126개 통과, 핵심 추적 방어 변이 검출, 원격 CI 33개 모두 통과. 실제 인식/운반/E2E 완료 판정은 아님. |
| #323 | **BLOCK** | F1: 현재 v6e pin 검사 5건 실패. F2: 모든 접근 keepout을 제거해도 새 T07 검사 127개가 통과. main CI 목록 충돌도 해결 필요. |
| #324 | **MERGE AFTER FIXES** | T12 자체 delta의 새 검사 204개와 stale 취소/timeout 변이는 유효. 그러나 #323에서 상속한 F1 때문에 현재 tree는 5건 실패. #323의 F1/F2 해결, main base 재설정 및 합성 CI 뒤에만 병합 가능. T07 결함을 T12에서 별도로 재구현해 고치지 않는다. |

`MERGE`는 이 SHA의 코드 검토 의견이다. 이 작업에서는 요청대로 검토 보고서 초안만 제출하며 대상 PR을 병합하지 않는다.

## 지적

### F1 — BLOCKER: #323이 현재 v6e의 소스 봉인을 깨뜨리고 #324가 그대로 상속한다

근거: #323 `harness/zone_own_team_host.py:512`, `harness/zone_own_executor.py:312`,
`harness/zone_pair_executor.py:17`, `harness/zone_pair_status.py:61`,
`harness/zone_study_integration.py:231`.
검사 계약은 `tests/test_zone_pair_registered_source.py:109`과 `:118`, `:143`이다.

`prereg_v6e.json`의 현재 `v6_contract.source_sha256`에 들어 있는 위 5개 파일을 수정했다.
그중 host 파일은 `scene_contract.source_sha256`에도 있다. 새 `zone_pair_roles.py` import도
study의 실제 Python 의존성에 들어간다. 그러나 현재 revision/실행 bundle과 v6e 등록은 그대로다.
따라서 **새 역할을 선택하지 않은 기존 v6e 호출도 현재 소스 검사에서 거절**된다.
`role_profile`/별도 source receipt를 새 세션 기록에 붙이는 것만으로 기존 등록의 실행 허용 조건이 복구되지 않는다.

원본 소스에서 두 요청 pin 파일을 모두 실행했다. #320은 **55/55 통과**, #323과 #324는 각각
**50 통과/5 실패**다. 실패는 현재 v6e scene/full closure 일치 1건과, 원본 clean 등록의 admission부터
실패하는 `test_v6_rejects_stale_or_inherited_source_contracts` 4개 매개변수다.
후자 4건의 실제 오류는 `scripts/zone_pair_v6_contract.py:286`의 `v6 source contract/hash mismatch`다.
역사 감사 16건 및 동적 study pin 33건은 각 후보에서 통과했다.
원격 #323 로그에서도 같은 5건과 `tests/test_zone_pair_door_relax.py:45`의 보호 소스 검사가
`harness/zone_own_team_host.py` 차이로 실패했다. 로컬 숫자와 원격 숫자를 합산하지 않았다.

과거 등록 JSON·과거 Git blob을 덮어쓴 것은 아니다. 역사 감사와 현재 tree 허용 검사를 구분해야 한다.
`tests/test_zone_study_source_pinning.py`는 동적 source closure 및 SHA 검사를 확인하는 성격이어서,
그 파일이 통과해도 v6e 등록 바이트와 현재 실행 소스가 같다는 뜻은 아니다.

수정 조건: 기존 봉인 경로를 보존하는 별도 opt-in 모듈/어댑터로 격리하거나, #292 소유자와
새 revision·bundle·admission을 명시적으로 합성해 기존 v6e를 역사 기록으로 보존해야 한다.
기존 `prereg_v6e.json` 해시를 현재 값으로 다시 쓰거나 실패 검사를 삭제하는 수정은 불가하다.
합성한 최종 SHA에서 두 pin 검사와 기존 r1/r2 경로를 다시 검사한다.
#324의 자체 delta가 새로 이 5개 파일을 수정한 것은 아니지만 main으로 올릴 최종 tree에는 같은 결함이 남는다.

### F2 — MAJOR: #323의 새 역할 기하 검사가 같은 구현을 정답으로 사용한다

근거: #323 `tests/test_zone_pair_role_exchange.py:119`, `:124`, `:125`는
새 역할의 prestation/keepout을 같은 현재 `make_plan()`이 만든 legacy 결과와 비교한다.
실제 전달 경로는 `harness/zone_pair_executor.py:109`–`:117`, `:268`–`:270`이다.

`make_plan()`의 반환값 `'keepouts': keepouts`를
`'keepouts': {r: [] for r in roles.participants}`로 한 군데만 바꿨다.
봉·상대 station·상대 prestation의 금지 영역이 모두 사라지는데,
**`tests/test_zone_pair_role_exchange.py` 전체 127개가 그대로 통과**했다.
새 역할 결과와 legacy 기대값 양쪽이 같은 변이를 받기 때문이다.
반대로 `carry_role_sign()`을 항상 `+1`로 만들면 실제 schedule 검사 12개는 모두 실패한다.
즉 모든 새 검사가 비어 있는 것은 아니며, 기하 보존 assertion에 구체적인 사각이 있다.

수정 조건: 봉/상대 station/상대 prestation의 금지 영역과 padding을 독립적인 고정 기대값으로 검사하고,
각 6배정에서 실제 `GuardedPairApproach`에 전달된 영역도 확인한다. 금지 영역 제거 또는 잘못된
역할의 영역 전달 변이가 실패해야 한다. 현재 원본 기하가 잘못됐다는 판정이 아니라,
이번 PR의 기하 회귀 검사가 이 손상을 검출하지 못한다는 판정이다.

## 과제 충족과 입력 경계

| PR | 코드에서 확인한 것 | 남는 범위 |
|---|---|---|
| #320 | `zone_identity_jobs.py:181`–`:208`의 일대일 추적/겹침/소실 token 보존, `:279`–`:316`의 specific 불확실→3회 재관측→실패, `:319`–`:348`의 target job 전달, `:230`–`:253`과 `:350`–`:388`의 자기 holding/open/목적지 관측 완료 믿음. 하위 done만으로 count를 늘리지 않는다. | 합성 detection을 받는 논리 모듈이다. 실제 RGB 인식기와 target-aware backend가 연결되지 않았다(`:90`–`:100`). specific 정상 재탐색은 아직 지원하지 않으며, 모든 과거 token의 동시 가시성을 요구해 순차 배송도 막힐 수 있다. README:16–35, 52–56에 이를 명시했다. T13a의 논리/fake 부분과 실제 수행 완료를 구분한다. |
| #323 | role→robot 6배정, 자기 API·실제 robot ID port/status 연결, 명시적 양쪽 제출, 제3 로봇 분리. `executor_plan(..., role_assignment=...)`과 `IntegratedTrial(..., pair_role_assignment=...)` 연결. 기존 3인자 r1/r2 API는 남는다. | F1/F2 해결 전 완료로 볼 수 없다. 고정 배정을 Python 호출자가 선택하며 LLM의 동적 파트너 협상/runner CLI는 추가하지 않았다. 12개 물리 셀은 미실행이다. |
| #324 | `zone_pair_rendezvous.py:138`–`:177`의 자기 제출/ack 검증, `:179`–`:197`의 job ID 검사·취소 확인 뒤 caller-selected 재배정, `:207`–`:231`의 기존 enum·timeout 처리. default actor에 자동 연결하지 않았다. | 자체 fake 계약과 #323 위 합성 검사 범위다. #323 수정 후 base 변경/합성 재검사가 필요하다. `tests/test_zone_pair_rendezvous_t07.py:121`–`:139`는 hold 주입 없이 제출을 늦춘 시험이다. `test_zone_pair_rendezvous.py`의 `plant_attempts`는 실제 port 명령에 연결되지 않으므로 40초 바퀴 정지/own RGB 인지/재집결 검증으로 세지 않는다. 작성자도 이를 물리 결과로 주장하지 않았다. |

검토한 변경에서 GT·sim state·상대의 실시간 pose/holding·심판 성공값을 새로 제어 입력이나 성공 통보에
넣은 경로는 발견하지 않았다. #320의 `observed_delivered`는 자기 관측 믿음이며 평가 성공과 구분돼 있다.
#323의 `make_plan`은 공개 static sheet를 사용하고 `world_grasps(..., pose=pose)`는 그 정적 입력의
기하 계산이다. 새 realtime lookup이 아니다. `zone_pair_executor.py:601`은 weld OFF와 contact profile을
계속 강제하며 `:420`–`:426`은 실행 순서 종료를 `unconfirmed`로 남긴다.
`scripts/zone_teacher.py::ArmSequence` 재사용은 자기 발행 servo target의 보간이다(`zone_teacher.py:218`–`:244`).
TeacherRobot/GT IK 실행을 학생에 추가하지 않았다. 네 조건의 enum/message schema를 확대하지 않았다.

## 오프라인 검사와 변이 검사

공용 잠금 아래 기존 Python 3.12 환경을 재사용했다. `mujoco`/모델 모듈·network connect·renderer/provider
진입을 금지한 pytest plugin을 사용했다. archive에는 `.git`이 없으므로 역사 blob 조회에만 기존
Git object DB를 `GIT_DIR`로 제공하고 `GIT_WORK_TREE`는 각 archive로 지정했다.
target code의 원본 테스트를 먼저 실행하고 변이는 그 archive에만 적용한 뒤 매번 원본 bytes로 복원했다.

| 원본 실행 | 결과 | 세부 |
|---|---|---|
| #320 새 테스트 + 요청 pin 2파일 | **126 passed** | T13a 71 + historical/current 등록 22 + study pin 33 |
| #323 새 테스트 + 요청 pin 2파일 | **177 passed, 5 failed** | T07 127 통과; 등록 17 통과/5 실패; study pin 33 통과 |
| #324 새 테스트 2파일 + 요청 pin 2파일 | **254 passed, 5 failed** | T12 159 + T07 합성 45 통과; 등록 17 통과/5 실패; study pin 33 통과 |

각 원본 실행에서 errors/skipped는 0이다. 재사용되는 55개 pin 검사를 합산해 고유 회귀 수처럼 보고하지 않는다.

| 변이 | 검사 범위와 실제 결과 | 판정 |
|---|---|---|
| #320 bbox 겹침 억제 제거 | 겹친 두 detection 반례 **1 실패** | 검출 |
| #320 historical token 가시성 조건 제거 | 소실/재등장·새 birth **3 실패, 3 통과** | 검출 |
| #323 모든 keepout 반환 제거 | 새 T07 파일 **127 통과** | **미검출, F2** |
| #323 역할별 운반 부호를 `+1`로 고정 | 실제 controller schedule **12 실패** | 검출 |
| #324 cancel의 과거 job ID/현재 소유 검사 제거 | stale 취소·실제 host 재배정 **18 실패** | 검출 |
| #324 rendezvous timeout 분기 제거 | deadline 경계 **32 실패, 16 통과** | 검출 |

변이 실행은 모두 collection/import error 없이 assertion으로 검출 여부를 판단했다.
검사 driver 종료 시 자기 잠금을 반환했으며, 후보의 변경 파일들이 원래 Git blob과 바이트 동일하게
복원됐음을 확인했다. 위 원본/변이 검사 범위 밖 전체 테스트나 물리는 새로 실행하지 않았다.

대표 재현:

```sh
mkdir -p /tmp/review-e2e-f-{320,323,324}
git archive ad63341d13a175582fbe7f5a664ca5bca5a33eaf | tar -x -C /tmp/review-e2e-f-320
git archive 1a17829e79cdf7771ee2d09ca25e444c39cf37be | tar -x -C /tmp/review-e2e-f-323
git archive c4d680c80f5f8a07c27d5a1edb0acf6683a9f014 | tar -x -C /tmp/review-e2e-f-324
# 공용 잠금 및 no-physics plugin 아래 각 archive에서:
python -m pytest -q tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
```

로컬 raw/재현 driver/변이 전후 내용/JUnit/metadata는
`/Users/changmin/projects/ugrp/outputs/review-e2e-batch-f/`에 보존했다. 원격 raw 백업은 아니다.
실험·학습·물리 평가 cohort를 만들지 않았으므로 TensorBoard 성공률이나 신규 snapshot을 생성하지 않았다.
실제 결과가 나오면 각 PR의 물리 인계에 적힌 TensorBoard 원본 연결/readback/영상 확인을 별도로 수행해야 한다.
UGRP 예외에 따라 Drive 작업은 하지 않았다.

## PR 간 충돌과 병합 조건

각 쌍의 정확한 SHA에 `git merge-tree --write-tree --name-only`를 적용했다. index/작업 파일은 변경하지 않았다.

| 조합 | 관측한 텍스트 충돌/의미상 의존성 |
|---|---|
| #320 + #323 / #324 | 자동 합성 가능. 공통 수정은 CI 목록이다. identity gate를 r3 pair나 study actor에 연결한 통합은 별개이며, 세 PR 병합만으로 연결됐다고 볼 수 없다. |
| #323 + #324 | #324가 #323 SHA를 조상으로 포함한다. 자체 T12 delta는 새 모듈·테스트·기록 및 CI 두 행이다. base를 main으로 바꾸기 전에 #323 문제를 해결해야 한다. |
| #320/#323/#324 + #292 | 모든 쌍은 텍스트 자동 합성 가능. #323/#324는 `zone_pair_executor.py`, `zone_study_integration.py`, CI 목록이 겹친다. 합성 tree에는 역할 부호와 #292 axial-lag/gain 계산이 함께 남지만, 새 controller closure/등록 digest와 r3×정책 조합은 새 SHA로 재검증해야 한다. #292의 과거 인수 결과를 승계할 수 없다. |
| #320/#323/#324 + #299 | 모든 쌍 자동 합성 가능. 공유 수정은 CI 목록이며 classifier 자체와 T13a/T07/T12 코드의 직접 hunk 충돌은 없다. classifier 고정/인수는 별도 관문이다. |
| #320/#323/#324 + #301 | 모든 쌍 자동 합성 가능. 공유 수정은 CI 목록이다. #301의 새 registry-entry 계약은 **실제 제어 코드 변경을 무시하는 면제**가 아니다. 현 v6e F1을 자동으로 해결하지 않는다. |
| 비교 main + #320 | 자동 합성 가능. |
| 비교 main + #323 / #324 | `scripts/run_ci_tests.py` 충돌. main의 P08 항목과 T07/T12 항목을 모두 보존해 해결해야 한다. |

최종 fetch에서 세 대상 및 #292/#299/#301 HEAD는 위 SHA 그대로다. 작업 도중 #308이 main에
병합되어 종료 시 main은 `504e4bb25a0988aaf0b8a00828ad68fc73df2670`이었다.
이 main과도 세 후보의 `merge-tree`를 다시 실행했고 위와 동일하게 #320은 clean,
#323/#324는 CI 목록만 충돌했다. 최종 main을 합성한 Python 테스트를 실행한 것은 아니다.

GitHub 최종 조회: #320은 **33 checks 모두 SUCCESS**이며
[offline-regressions](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36715030047/job/109901844715)도 통과했다.
#323은 **30 SUCCESS/3 FAILURE**(실패 shard 2개와 집계),
[#323 집계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36715321154/job/109900825600).
#324도 **30 SUCCESS/3 FAILURE**,
[#324 집계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36716101824/job/109907985801).
GitHub의 #324 MERGEABLE은 feature base #323에 대한 텍스트 상태이며 main 준비 통과가 아니다.
보고서 이외의 후보 소스/기존 기록/기본 checkout은 변경하지 않았다.

## 증거 파일

원본 경로는 위 로컬 raw 디렉터리다. `artifact_manifest.json`에는 raw 파일 크기와 전체 SHA-256을 기록했다.

| 파일 | SHA-256 |
|---|---|
| `checks.jsonl` | `bae57cab82d84978dd06dc55681f78c4b3bdf885869e5bbe94545911fa4b03fb` |
| `323_baseline.xml` | `5a8c3cccc8af23f4efd01a9609d6269f47dff74c66277aa0635bf4a8ae2f6379` |
| `323_keepouts_removed.xml` | `c3d8ef7d8a4952f19ec5a7ea4c09598349f849d35edad87907e469331a2aed9e` |
| `324_baseline.xml` | `71a2c45efb3ba93a24e3fb3d355968d51492198d6af6f5ceab52aa11fba0956d` |
| `merge_matrix.json` | `3fe63e56e720db7ae9d744bea3bba446a7b813791e2c000418205334389e26c2` |
| `final_main_merge_matrix.json` | `320c752e554ae0070300b62367e979935bcf4733b6a73fe733201e26d0d1428d` |
| `sealed_overlap.json` | `529900cf6aef596eed8e8f595a4d45fcf04525b4104023c0ead42f1ff1cc953e` |
| `archive_restored.json` | `057df88a6a88a709c6adeb0c38f9c64380f7495650a8dc2b820a36a10b90fdc2` |
| `artifact_manifest.json` | `f4ced8b272fedf16491835a70e739feb178a1973705cb76d2353c7955d5cf1e6` |

Generated with Codex
