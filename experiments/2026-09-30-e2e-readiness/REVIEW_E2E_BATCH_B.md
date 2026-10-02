# E2E 준비 PR 독립 검토 — Batch B

검토일: 2026-09-30. 검토자: Codex, `codex/review-e2e-batch-b`.

**세 PR 모두 현재 HEAD 그대로는 병합할 수 없다.** #307의 좁은 혼합 임무 계약과 #302의 정적 감사는 작업 범위를 대체로 충족한다. #308은 정상 사용량을 모두 미확인으로 바꾸는 결함이 있다. #307/#308은 현재 v6e 소스 고정 검사도 깨뜨린다. #302는 정상 CI를 다시 시작했지만, CI 취소/skip을 요구하는 문서 지침을 아직 정정하지 않았다.

이 문서의 판정은 코드/문서 병합 준비에 한정한다. 학생 E2E, 실제 모델 대화, 물리/실물 성공 승인이 아니다. 검토에서 물리 step·렌더·모델 서비스 호출을 하지 않았다. 다른 작업의 실행/잠금은 변경하지 않았고, 새 worktree도 만들지 않았다.

## 대상과 판정

작업 프롬프트는 이 폴더의 `task_prompts/P02_mixed_jobs.md`, `P05_dialogue_ledger.md`, `P09_scenario_capabilities.md`를 기준으로 읽었다. 리뷰 브랜치 시작 HEAD는 `6594536b1a1afec6d9d109b35dd85a8426142d01`, fetch 뒤 비교 main은 `c12796676802ab54cad2f0635e3e96e911691c76`이다. 다음 SHA의 변경을 검토했으며 후속 커밋으로 판정을 자동 승계하지 않는다.

| PR | 검토 HEAD | 판정 | 병합 전에 필요한 일 |
|---|---|---|---|
| [#307 P02](https://github.com/kcm0127-dotcom/ugrp/pull/307) | `6bb522b14aa28fcaa3ff30f988aebca4ab3aee15` | **MERGE AFTER FIXES** | B1: 기존 v6e 소스 검사와 새 코드의 버전 경계 해결, 정상 CI 통과 |
| [#308 P05](https://github.com/kcm0127-dotcom/ugrp/pull/308) | `5411f5e8d29186c00b44c2731e9915583da39aae` | **MERGE AFTER FIXES** | B2: 정상 usage의 known 표시와 양성 회귀 수정. B1 및 정상 CI 해결 |
| [#302 P09](https://github.com/kcm0127-dotcom/ugrp/pull/302) | `bd95530a2d5a8b8467620809749273068a7ed55d` | **MERGE AFTER FIXES** | B3: CI 해석/후속 지침 정정, 재시작한 정상 CI 확인. B4는 후속 범위의 비차단 보완 |

검토 중 #302에 `ci: run normal checks` 빈 커밋이 추가됐다. 초기 `dec6799`와 최종 `bd95530`의 전체 tree가 모두 `fff0ebc82275012e35eb01bea74d5a8d2adb9bc1`임을 확인했다. 코드/자료 바이트가 같아 정적 재검사 결과는 두 SHA에 동일하게 적용된다. 정상 CI는 재시작됐으며 취소하지 않았다.

BLOCKER로 분류할 새 GT/교사/weld/성공 통보 위반은 찾지 못했다. MAJOR 3건(B1은 두 PR 공통), MINOR 1건이다. 이는 저장소 전체의 정보 경계를 승인한다는 뜻이 아니다.

## 지적과 반례

### B1 — MAJOR: #307/#308을 각각 병합하면 현재 v6e 등록 검사가 실패한다

**변경 위치:** #307 `harness/zone_own_team_host.py:66–85`, `scripts/run_zone_study_integration.py:329–346`, `harness/zone_study_integration.py:275–289`; #308 `harness/zone_study_integration.py:347–355`.

**반례:** 현재 `experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json`의 `v6_contract.source_sha256`과 각 PR의 파일 바이트를 비교하면 #307은 위 세 파일, #308은 integration 한 파일이 다르다. `tests/test_zone_pair_registered_source.py:106–118`의 `test_v6e_records_current_scene_and_full_source_closure`가 그 상태를 거절한다. `scripts/zone_pair_v6_contract.py:286`도 같은 계약/해시 불일치를 거절한다.

GitHub에서도 #307 [실패 job](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36708789798/job/109865334924)은 `test_zone_pair_door_relax.py::test_registered_sources_are_not_touched_by_this_change`에서 `harness/zone_own_team_host.py` 불일치로 실패했다. #308 [실패 job](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36709551344/job/109867788930)은 위 current-source 검사 및 `test_v6_rejects_stale_or_inherited_source_contracts` 네 변형에서 실패했다. CI 실패를 본 리뷰의 물리 실행으로 세지 않는다.

**영향:** 신규 fake 테스트만 녹색이어도 기존 등록을 현재 소스에서 검증/사용하는 경로는 통과하지 못한다. 기존 결과나 prereg JSON 바이트가 덮어써진 것은 아니며, fail-closed 검사가 작동한 것이다. 따라서 이를 ‘봉인이 조용히 통과한다’고 표현하지 않는다.

**수정 조건:** 기존 prereg 해시를 새 파일에 맞춰 덮어쓰거나 검사만 제거하지 않는다. 봉인 소스를 보존하는 별도 진입점으로 분리하거나, 독립 검토된 후속 버전에서 v6e의 등록 커밋에 대한 역사 감사를 명시적으로 연결해야 한다. #292에는 이 전환 코드가 있지만 미병합이므로 현재 두 PR의 독립 병합 근거가 아니다. 합성 뒤 같은 HEAD의 source-pinning 회귀와 정상 CI를 다시 확인한다. 정확한 기대/실제 해시는 [preservation.json](review_batch_b/preservation.json)에 있다.

### B2 — MAJOR: #308은 정상적인 provider usage도 전부 unknown으로 바꾼다

**변경 위치:** [harness/zone_study_integration.py:347–355](https://github.com/kcm0127-dotcom/ugrp/blob/5411f5e8d29186c00b44c2731e9915583da39aae/harness/zone_study_integration.py#L347).

`CallReply.__post_init__`는 `provider_usage`를 `MappingProxyType`으로 고정한다(`harness/zone_event_scheduler.py:175–180`). 그런데 새 호출부가 사용하는 `zone_main_budget.known_total`은 `dict`만 허용한다(`harness/zone_main_budget.py:51–59`). 따라서 정상 응답의 읽기 전용 매핑도 `None` 판정이다.

**반례:** `{prompt_tokens: 500, completion_tokens: 100, total_tokens: 600}`을 반환하는 기존 `DialogueWire`를 사용한다. 원장/SQLite/요청 archive에는 정상 사용량이 남지만 `_LiveTransport.reply`를 통과한 scheduler/result의 `cost_terms.usage_known`은 false, `usage_bound`는 `lower_bound`가 된다. 숫자가 사라지는 결함이 아니라 서로 다른 기록이 동일 호출을 known/unknown으로 다르게 분류하는 결함이다. P05 완료 기준 3을 충족하지 못한다.

**기존 검사가 놓치는 이유:** `tests/test_zone_study_llm_driver.py:782–798`은 원장/DB/archive의 usage와 SIM 비용·release 시간을 확인하지만, 정상 응답의 scheduler/result known 플래그를 그 값과 연결하지 않는다. `:1003–1004`는 usage 누락 때 false인지만 검사한다. 항상 false인 잘못된 구현도 이 검사들을 통과할 수 있다.

**수정 조건:** 읽기 전용 Mapping을 그대로 판정하거나 명시적으로 dict로 변환하되, 누락/잘못된 수치의 unknown 처리는 유지한다. 정상·누락·불일치 usage 각각에서 raw→send row→DB→scheduler→result의 값과 known 표시를 함께 검사한다. 정상의 exact 표시와 censored 응답의 표시도 확인한다. [독립 반례](review_batch_b/repro_usage.py)는 수정 전 실패해야 하는 두 검사이며, 제품 테스트 목록에는 자동 등록하지 않았다.

### B3 — MAJOR: #302의 CI 취소/skip 지침은 허용된 정상 CI와 충돌한다

**위치:** [CI_INCIDENT.md:3–13](https://github.com/kcm0127-dotcom/ugrp/blob/dec67997815e4cdc564a9848ed6020eede45cbfa/experiments/2026-09-30-scenario-capabilities/CI_INCIDENT.md#L3), `VERIFICATION.md:49–51`.

**확인:** 문서는 정상 workflow를 범위 위반으로 해석해 cancel→force-cancel한 사실을 기록하고, 후속 커밋에도 `[skip ci]`를 쓰겠다고 한다. 해당 두 workflow는 cancelled이고 초기 HEAD `dec6799`의 check 목록은 비어 있었다. 검토 중 올라온 빈 커밋 `bd95530`에서 정상 CI가 재시작된 것은 확인했다. 그러나 파일 diff는 0이며 CI_INCIDENT/VERIFICATION/PR 본문의 취소 해석과 앞으로 skip한다는 문구는 그대로다. 사용자 지시는 정상 CI를 허용한다. 로컬 물리/모델 실행 금지를 이유로 필수 CI까지 계속 차단하면 병합 검증이 사라진다.

**수정 조건:** 취소 사실·시각·원본 증거는 보존한다. 여기에 ‘정상 CI는 허용되며 당시 취소 해석이 잘못됐다’는 정정을 추가하고, README/VERIFICATION/PR 본문의 앞으로도 skip한다는 지침을 고친다. 재시작한 정상 CI를 완료하고, 정정 커밋을 추가하면 그 최신 HEAD의 검사도 확인한다. 과거 cancelled 실행을 성공으로 바꾸어 적거나 로컬 static 124건으로 CI를 대체하지 않는다. 검토자는 대상 브랜치/CI를 임의로 고치거나 취소하지 않았다.

### B4 — MINOR: #302 T02를 #307의 완료 조건으로 읽으면 작업 범위가 바뀐다

**위치:** [TASKS.md:23–29](https://github.com/kcm0127-dotcom/ugrp/blob/dec67997815e4cdc564a9848ed6020eede45cbfa/experiments/2026-09-30-scenario-capabilities/TASKS.md#L23).

T02는 ‘P02 소유’라고 적으면서 정식 6종의 다색/count/can/tile/crate inventory를 요구한다. 원래 P02는 cyan 1개+봉 1개에 한정하고 전체 6시나리오 지원을 명시적으로 제외했다. #307이 이를 모두 구현하지 않은 것은 원래 P02의 누락이 아니다.

**수정 조건:** T02를 ‘P02 다음의 별도 확장 과제’로 표시하고 별도 범위/담당을 합의한다. 현재 #307 완료 조건에 소급 추가하지 않는다. 2×900초도 #307의 4조건×1800초 인계와 다른 시험이라는 점을 유지한다.

## 작업 프롬프트별 충족 범위

### #307 / P02

| 완료 기준 | 검토 결과 |
|---|---|
| 1. order→item 분리, 공개 입력에서 exact pose 제외 | 충족. `zone_mixed_jobs.order_bindings/mixed_contract`는 setup/eval의 매핑을 만들고 기존 `OrderSheetSource`의 공개 스키마를 유지한다. 같은 색 다수의 시각적 identity 해결은 범위 밖이다. |
| 2. cyan+봉 inventory, 잘못된 ID/kind 거절 | 충족. 새 opt-in Scene subclass와 별도 inventory 검사. 기존 cargo/geometry Scene과 s1–s6를 덮어쓰지 않는다. World 생성/물리는 검증하지 않았다. |
| 3. r1/r2와 r3 독립 API·실패 격리 | fake 범위 충족. 한쪽 제출만으로 상대 job을 만들지 않고 pair abort가 r3 job을 취소하지 않는다. solo 실패 후 pair 시작도 검사한다. |
| 4. 고정 역할과 미지원의 명시적 거절 | 충족. r1/end_neg·r2/end_pos, r3/cyan, A/B 목적지, v2 지도·v5h만 허용한다. r3 pair/비cyan/crate/다른 policy를 거절한다. |
| 5. 네 조건 ledger/dispatch/eval join·GT/TOP 변이 | fake 범위 충족. 동일 seed/scene, 자기 terminal과 독립 referee delivery를 join한다. 인위적으로 만든 fake done/도착 좌표를 실제 운반 성공으로 주장하지 않는다. |
| 6. 4조건×1800초 인계 | 충족. `COORDINATOR_HANDOFF.md:39–75`에 초기화부터 목적지까지, 실패 분모·ENOSPC·후속 raw/TensorBoard를 명시한다. 이번 실행은 없다. |

신규 26개 검사는 ID 누락/중복/kind/역할 거절, 자기 요청 출처, 실패 격리를 실제 생산 API에 연결해 확인하므로 단순 성공 상수 확인만은 아니다. 다만 M2 완료와 solo 하위 운반은 fake다. 그 통과를 실제 제어 완주·최종 v3/provider 지원으로 넓힐 수 없다. 가장 큰 누락은 B1의 기존 등록 회귀다.

### #308 / P05

| 완료 기준 | 검토 결과 |
|---|---|
| 1. 4조건×seed%3×로봇 2턴 이상 | 충족. seed 700/701/702, 두 speech profile, 로봇당 3턴. send→inbox→자기 job 경계→다른 claim과 message/call/job ID를 확인한다. |
| 2. 채널 제한·literal ID·상태 hash·비간섭 | 충족. no_comm/leader/structured 제한, 자기 frame 변화의 양성 대조, 다른 로봇 wake/timer 불변 검사가 있다. |
| 3. 요청 bytes/digest·원장·usage·SIM 비용·실효 cap | **미충족(B2)**. JPEG/요청/응답·상한 포화·SIM release 검사는 있으나 정상 known이 result에서 깨진다. |
| 4. 오류 주입·송신 뒤 자동 재시도 금지 | 좁은 fake 경로 충족. attach에서 `max_retries=0`을 요구하고 양수/기본/비정수를 첫 송신 전에 거절한다. 429/503, read timeout, 비정상 finish, cap, late/censored, ENOSPC 검사가 있다. |
| 5. 실제 cohort/model/DB 승인·상류 정산 인계 | 충족. 새 cap/모델/effort/DB/output 및 상류 receipt/usage가 별도 선행 조건임을 남긴다. 실제 proxy나 기존 budget DB는 검증하지 않았다. |

한국어 이해는 고정 fixture의 메시지 선택으로만 확인된다. 실제 모델의 대화 효과가 아니다. post-send retry 수정은 기존 공통 scheduler의 기본값을 몰래 바꾸는 대신 본연구 연결을 거절하므로 방향은 맞다. 정상 usage 양성 검사가 없는 것이 핵심 테스트 구멍이다.

### #302 / P09

| 완료 기준 | 검토 결과 |
|---|---|
| 1. 원본 6종의 주문/물건/역할/경로/사건 추출 | 충족. 23주문행·26물건, 원본 파일/위치·거절 함수·hidden event 시각을 연결한다. spawn 후보와 로봇별 실제 배정을 구별한다. |
| 2. maps_dir_for와 정적 evaluator | 충족. 원판 .17/.21 m와 전체 편대, 시작→격자 연결, 같은 경로 역방향 sweep, 문 입구와 중심선 crossing을 구분한다. static import/외부 실행 guard가 있다. |
| 3. 지원 등급과 누락 능력 | 충족. identity/count, r3, 다색/can/tile/crate, 회전, 두 문/복도, 미파지 낙하 no-op, s6 설계 미확정을 남긴다. |
| 4. 원본 보존·작은 후속 PR 분할 | 충족. T01–T13의 a/b 분할로 17과제, fake/물리 분리와 네 조건 동일 controller를 요구한다. B4의 P02 후속 범위 표현만 보완한다. |
| 5. SIM 비용 제안·미산정 | 충족. 50셀×900=45,000 SIM초는 최소 기능 진단 제안이며 staging 포함·경로 길이·추가 미산정 항목과 C6/C7를 분리한다. 관측된 wall 처리량으로 주장하지 않는다. |

세 신규 보조 검사는 문 입구 방문을 실제 문 통과로 잘못 세는 오류, 중심선 touch 후 후퇴, identity/count 추출을 확인한다. 새 제어기 성공을 검사하는 테스트는 아니다. 로컬 정적 완료와 별개로 B3 때문에 병합 검증은 미완료다.

## 입력 경계·기존 결과·기본값

- #307: exact 배치는 setup contract/inventory와 offline referee join에만 쓴다. 공개 주문서는 초기 slot과 정적 ID를 유지한다. 새 mixed admission은 caller의 API를 허용/거절할 뿐 상대 claim 생성·GT 기반 양보·r3 성공 통보를 추가하지 않는다. PairTeam의 `weld=False`, contact profile은 유지한다.
- #308: 수정 경로는 transport retry admission/usage 표시다. GT, sim pose, 접촉, measured joints, peer private 정보가 제어 입력으로 새로 들어가는 변경은 찾지 못했다. 허용 메시지와 기존 모든 조건 공통 pair status를 구분한다.
- #302: inventory/feasibility는 평가 전용 정적 출력이다. 문서도 이를 robot 입력으로 쓰지 말라고 명시한다. 교사 정책이나 weld 실행을 추가하지 않는다.
- 세 PR 모두 기존 prereg·s1–s6·지도 catalog·workflow registry·RGB bundle·공통 prompt 바이트의 변경은 없다([검사 목록/해시](review_batch_b/preservation.json)). #307은 새 profile만 opt-in이지만 `executor_plan`의 목적지/미지원 kind 거절은 공용 경로에도 적용된다. #308의 새 본연구 attach 조건은 `max_retries=0`을 명시하지 않은 기존 호출자를 거절한다. 이 두 변경은 새 실행 source/bundle로 검증해야 하며 과거 성능을 승계하지 않는다.
- v6e 파일 바이트의 보존과 현재 소스 실행 admission은 다르다(B1). 새 버전을 봉인하거나 기존 실패/성공 자료·raw·checkpoint를 수정하지 않았다.

## PR 사이의 충돌과 합성 조건

검토한 다른 HEAD는 #292 `3c4fe30e2197518443b195392212b0341507ac59`, #299 `c86d9bac62036904ecc641db5e59e79edb58dec2`, #301 `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`다.

`git merge-tree --write-tree`로 세 리뷰 대상 사이 3쌍과 각 대상×#292/#299/#301의 9쌍, 총 **12쌍 모두 텍스트 충돌 없음**을 확인했다. checkout/index/브랜치는 바꾸지 않았다. [정확한 tree/겹친 경로](review_batch_b/merge-matrix.json)를 남겼다. 이는 모든 PR을 합성한 최종 runtime 시험이 아니다.

| 조합 | 의미상 주의점 |
|---|---|
| #307 + #308 | `zone_study_integration.py`의 서로 다른 부분이라 자동 병합된다. 그래도 mixed fake가 본연구 `MainStudySendLedger`를 사용한 네 조건 다회 실험까지 대신하지는 않는다. B1/B2 해결 뒤 합성 검사가 필요하다. |
| #307 + #302 | #307은 cyan1+beam1 dev만, #302 T02는 정식 6종 확장이다(B4). 작은 dev 통과를 26물건 지원으로 옮겨 적으면 안 된다. |
| #308 + #302 | 코드 파일 충돌은 없다. P09의 모델/예산은 후속 제안이며 P05 fake 토큰/요청 수를 실제 비용 근거로 쓰지 않는다. |
| #307/#308 + #292 | #292는 v6e를 등록 커밋에 대한 역사 감사로 이동하고 v6h를 미봉인 후보로 둔다. 이 전환이 B1과 연결된다. #307은 여전히 v2/v5h만 허용하고 v3 pair를 거절하므로 v6h1 지원은 자동으로 생기지 않는다. #308의 driver profile/bundle 등록도 최종 합성 HEAD에서 재검사한다. |
| 세 PR + #299 | 직접 파일 충돌 없음. classifier의 평가 전용 입력/분모를 mixed setup이나 대화 입력으로 넘길 연결도 추가하지 않는다. 후속 #292 봉인의 classifier closure는 별도 확정 대상이다. #299 자체의 통계/봉인 타당성은 이번 재검토 범위가 아니다. |
| 세 PR + #301 | #307의 CI 목록 한 행 외에 직접 파일 충돌 없음. #301은 새 dependency API이며 기존 v6e를 자동 이관하지 않는다. 따라서 B1을 저절로 해결하지 못한다. 최종 진입점에는 mixed scene/helper와 driver를 포함하고 사용 registry 항목을 고정해야 한다. #301 자체의 봉인 안전성은 이번에 승인하지 않는다. |

## 독립 검증 기록

아래 수치는 PR 작성자의 254/656/124 통과 기록을 합산한 것이 아니라 본 검토의 별도 실행이다. `git archive <HEAD>`로 `/tmp/ugrp-review-e2e-b/pr{번호}`에 필요한 소스/자료를 추출하고 기존 `.venv-sim-worker-mac`을 사용했다. pytest/정적 evaluator는 공용 `scripts.run_ci_tests.run_locked` 보호 아래 실행했다.

| 대상 | 본 리뷰에서 실행한 검사 | 결과 |
|---|---|---|
| #307 | 신규 `test_zone_mixed_jobs.py` 전체 + 기존 v6e current-source 검사 | **26 passed / 1 failed**. 실패는 B1 |
| #307 추가 | fake parent로 대체하지 않은 실제 정적 Scene resolver/`own_scene`/inventory 연결, World 없음 | **1 passed** |
| #308 | `test_zone_study_llm_driver.py` 전체 + 기존 v6e current-source 검사 + 독립 usage 반례 2개 | **155 passed / 3 failed**. 실패는 B1 1건, B2 반례 2건 |
| #302 | 6종 `audit.audit()` 재실행 + feasibility/final-env/보조 검사 전체 | **124 passed**. s1–s5 feasible, s6 conditional. `inventory.json`와 `feasibility.json` 둘 다 제출본과 바이트 동일 |

통과/실패를 합쳐 ‘전체 통과’로 보고하지 않는다. #308의 기존 검사 155건이 통과하면서 독립 반례가 실패한 것이 B2 테스트 구멍의 직접 증거다. #307 실제 static resolver 확인도 물리 XML의 접촉/완주 성공을 뜻하지 않는다.

초기 리뷰 실행의 환경 오류도 보존했다. #308은 `/tmp`와 `/private/tmp`의 혼합 경로로 pytest 수집 범위가 넓어져 수집 전에 거절됐고, 반례 파일을 archive의 `tests/`에 둔 뒤 정상 수집했다. #302는 새 basetemp 상위 폴더가 없어 123 pass/1 setup error였으며, 새 경로를 만든 뒤 124건과 정적 계산을 재실행했다. 이 두 오류는 대상 PR 결함으로 세지 않는다. 이전 raw/실패 로그를 덮어쓰지 않았다.

명령·대상 SHA·테스트 결과·초기 오류·잠금 획득/반환·원본 경로·SHA-256은 [verification.json](review_batch_b/verification.json)에 있다. raw/JUnit/가짜 request·SQLite는 `/Users/changmin/projects/ugrp/outputs/review-e2e-b-20260930/`에 로컬 보존했다. 두 리뷰 잠금이 모두 반환됐음을 확인했다. 제출 전 원격 재조회에서 #307/#308은 실패 check, #302는 재시작한 정상 check를 확인했으며 전체 CI 통과를 주장하지 않는다.

물리/학습/학생 평가 cohort를 새로 만든 것이 아니므로 TensorBoard snapshot이나 서버는 변경하지 않았다. UGRP 예외에 따라 Drive 작업도 없다. 본 리뷰는 로컬 raw와 Git에 남긴 검토 문서/작은 재현 코드만 보존하며 raw의 원격 백업 완료를 주장하지 않는다.
