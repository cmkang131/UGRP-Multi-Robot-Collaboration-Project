# E2E 수정 검증 1 — #303 / #305 / #307 / #311

2026-09-30, 독립 검토자 Codex (`codex/review-fixes-1`). 물리·렌더·학습·실제 모델 호출 없이 수정 검증만 수행했다. 대상 PR 소스를 수정하거나 PR을 병합하지 않았다. 아래 판정은 명시한 SHA의 기술 검토이며, GitHub 필수 CI·최신 base 반영·실행 승인과 구분한다.

## 판정과 검토 소스

| PR | 수정 검토 HEAD | 판정 | 이유 |
|---|---|---|---|
| #303 / P06 | `114349e0adc6d934ceb9a990ee9589aa123b8543` | **BLOCK** | A303-1의 내부 기록 연결 누락이 남음. 서로 다른 시행의 호출·행동 정보를 섞어도 성공 event 1.0 발행 |
| #305 / P01 | `408d384b880bb80a014580ec8bd3da03874d6422` | **MERGE** | 도크 경로·고정 소스 복원 및 별도 환경 후보의 명시적 의존성 계약 확인 |
| #307 / P02 | `1bf7a1cd6352effce0b5619a7e01a3c960068263` | **MERGE** | B1 고정 소스 복원, 혼합 어댑터의 생성·명령·실패 격리 회귀 확인 |
| #311 / P07 | `f7a3ac29678af5a2b5639504572679d20a1adf56` | **MERGE** | 실제 P03 조합 JSON과 참조 자산의 변경·삭제를 계획 검사가 탐지 |

이전 검토 소스는 Batch A `933bb1d63f2de7d5df16ede55c4235e4a65cc1f4`, Batch B `ec0f85807ddb55927a81ac071b407b8ea53802d8`, Batch C `7ee20a048c6b29089dbcd3c332d734bf43cd77c0`의 `REVIEW_E2E_BATCH_{A,B,C}.md`다. 이전 피검토 HEAD는 각각 #303 `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8`, #305 `5a852fbfde3b0df836f3a423be29a774a9c54614`, #307 `6bb522b14aa28fcaa3ff30f988aebca4ab3aee15`, #311 `bd011c997f9f7946de28f912dbdd3833ebb33988`이다. 작업 기준 main/리뷰 브랜치 시작은 `ad496486271f441f00eb7d95fbd44dc454999004`다.

## 이전 지적 전수 대조

| 이전 지적 | 검증 판정 | 근거와 일반화 범위 |
|---|---|---|
| A303-1: 다른 trial/scenario/seed/order를 성공 기록에 결합 | **부분 수정, 미해결** | 최상위 trial/result/manifest/evaluation·주문서·요청 주문서·심판의 개체/시각/수량 검사는 추가됨. 내부 calls/actions의 run_id/condition/seed와 선언한 시행을 연결하지 않음. 아래 F303-1 |
| A303-2: 현재 v6e runner 바이트 변경 | 해결 | runner를 등록 바이트로 복원. 새 writer는 별도 파일이며 전역 hook 설치 없음. 기대 해시·등록 JSON·검사 조건을 바꾸지 않음 |
| A303-3: terminal 표식 생략 허용 | 해결 | result의 정확한 bool true, manifest의 필수 terminal 필드, 세 기록의 bool record_complete를 검사. 구형 표식 없는 자료도 묵시적으로 허용하지 않음을 문서화 |
| A305-1: 기존 dock 지도 factory 이전 거절 | 해결 | 공식 dock ID를 `dock_map()`으로 검증. 기존 경로와 새 어댑터 양쪽에서 fake factory에 도달하고 접촉 프로필 유지. 다른 지도/모델/해시·미지원 provider 거절도 유지 |
| A305-2: runner/Scene provider의 v6e 봉인 충돌 | 해결 | 해당 파일과 scenario 모듈 원본 복원. 신규 기능은 환경 bundle/Scene 어댑터로 분리. 과거 등록에 현재 해시를 덮어쓰지 않음 |
| A305-3: #292 후보에서 registry/catalog/dynamic Scene 누락 | 해결 | 기존 경로에서 새 숨은 의존성을 제거. 환경을 선택하는 새 후보는 registry·두 catalog·선택/부모 지도·보정·동적 Scene/import closure를 명시적으로 고정. 기반 계약을 복사·검증하고 runnable=false 유지 |
| B1 (#307): 세 공용 파일 수정으로 v6e 회귀 | 해결 | 세 파일 원본 복원. 별도 `MixedOwnCamTeamHost`, `MixedIntegratedTrial`, `zone_mixed_study_adapter`에 기능을 보존. 기존 admission·전역 객체·import closure와 분리 |
| C311-1: #312 P03 조합 및 참조 파일 누락 | 해결 | `_p03_combination_pin()`이 실제 JSON과 `active.files_sha256` 전체를 읽고 검증. 카메라 선언·신규 참조 파일·JSON 삭제가 저장 초안을 무효화. invalid/missing/nonlocal 참조를 거절하고 실행 차단 유지 |

## F303-1 — P1: 내부 호출·행동의 시행 신원을 대조하지 않아 다른 시행 기록도 성공으로 변환

위치: [`scripts/zone_study_evidence_contract.py:40–55`](https://github.com/kcm0127-dotcom/ugrp/blob/114349e0adc6d934ceb9a990ee9589aa123b8543/scripts/zone_study_evidence_contract.py#L40), 같은 파일 `:72–89`; 호출부 [`scripts/tensorboard_tools/zone_study.py:109`](https://github.com/kcm0127-dotcom/ugrp/blob/114349e0adc6d934ceb9a990ee9589aa123b8543/scripts/tensorboard_tools/zone_study.py#L109).

`validate_record_identity()`는 최상위 trial의 필드와 주문서만 비교한다. calls에 대해서는 provenance의 주문서 해시만 대조하고, 각 call/action/message의 `run_id`, `seed`, `condition`을 선언한 시행과 비교하지 않는다. `parse_trial()`도 행별 스키마를 검사할 뿐 이 시행 간 연결을 보장하지 않는다. 동일 시나리오를 반복하는 두 시행의 로그를 잘못 섞으면 파일 해시가 모두 맞아도 비용·호출·행동 출처가 다른 성공 자료를 게시할 수 있다.

독립 반례는 PR의 정상 synthetic 성공 원본을 새 임시 폴더에 만들고 다음 값 **하나씩만** 바꾼다. 심판 성공·주문·요청 이미지·바깥쪽 identity는 그대로 두고 raw 파일 inventory 해시만 다시 계산한다.

| 변경 | 실제 결과 |
|---|---|
| `calls[0].run_id = 'foreign-trial'` | 수락, `evaluation/reported_success = 1.0` |
| `actions[0].run_id = 'foreign-trial'` | 수락, 성공 1.0 |
| `calls[0].seed = 987654` / `actions[0].seed = 987654` | 두 경우 모두 수락, 성공 1.0 |
| `calls[0].condition = 'peer_ko'` / `actions[0].condition = 'peer_ko'` (원 시행은 no_comm) | 두 경우 모두 수락, 성공 1.0 |
| 최상위 trial_id와 네 envelope의 evidence_identity.trial_id만 `unrelated-trial`로 변경, 내부 call/action run_id는 원 시행 그대로 유지 | 수락, 성공 1.0 |

거절을 기대하는 독립 테스트 **7/7 실패**이며, 모두 실제 EventAccumulator readback으로 위 scalar를 확인했다. 제출된 관련 테스트가 통과하는 것과 별개다. 메시지 행에도 같은 정적 누락이 보이지만 이 7건에 메시지 반례 실행을 합산하지 않았다.

수정 조건: call/message/action 각 행의 시행·조건·seed를 identity에 연결하고, 같은 호출의 request/dispatch/원장 식별값도 일관되게 검사해야 한다. 현재 정상 자료의 `record.trial_id`와 내부 log `run_id`는 `no_comm-i1_cyan_three_slots-s700`, raw attempt의 `identity.run_id`는 `success`다. **내부 log run_id를 raw 디렉터리명과 무조건 같게 만들면 정상 경로가 깨진다.** 이 명시적 매핑을 유지하면서 다른 시행의 내부 행을 거절하고 event가 없음을 확인해야 한다. 불완전 실패 기록에서 존재하지 않는 행을 만들거나 삭제로 문제를 감추면 안 된다.

재현 코드: [test_pr303_identity_join.py](review_fixes_1/test_pr303_identity_join.py). 검토 SHA archive의 `tests/test_review_independent.py`로 복사하여 공용 잠금 아래 실행한다. 테스트는 synthetic fixture만 사용한다. 제품 테스트 목록에는 등록하지 않았다.

## 수정으로 생길 수 있는 회귀 검토

- #303: writer 분리로 기존 runner의 연결이 자동 유지되는 것은 아니다. PR 문서와 현재 P06 프롬프트가 새 실행기 연결·종료/중단 인수를 후속으로 명시한다. 이 검토는 synthetic writer/exporter 범위다. A303-2/3은 해결됐지만 F303-1 때문에 A303-1 전체 해결을 승인하지 않는다.
- #305: 신규 경로는 명시적 opt-in이고 기존 CLI/registry를 바꾸지 않는다. preview의 execution_bundle_id는 null이며 base ID만 별도로 기록한다. 등록 번호·실행 승인·v3 보정 지원을 물려받지 않는다. 기존 경로에서 registry가 읽히지 않는지 별도 import-closure 반례도 검사했다.
- #307: 생성자에서 정적 계약·inventory·frames 설정을 먼저 검사하고, 기존 solo 초기화 뒤 원래 spec으로 pair를 연결한다. World 소유 부분만 fake로 대체한 실제 생성자 경로와 닫힘/죽은 로봇 거절 우선순위를 검사했다. `_on_action`의 명령 시각·원장 기록·명령 기억·재질문 처리는 기존과 동일하다. 기존 네 통신 조건의 자기 API·pair 실패와 r3 격리 검사도 유지된다. 물리 성공이나 최종 v3 지원 판정은 아니다.
- #311: 평가 선언을 JSON으로 옮긴 뒤에도 입력 경계 검사를 완화하지 않았다. 기존 RobotInputBoundaryTests가 통과한다. P03 JSON 존재·정상 해시만으로 final v3를 수락하지 않으며 runnable/physical_ready=false와 승인 null이 유지된다. 과거 저장 초안은 새 planner에서 재검토·재생성이 필요하다.

## 독립 실행 및 수정 전 음성 대조

검사는 PR ref를 fetch하여 정확한 SHA의 `git archive`를 `/private/tmp/ugrp-review-fixes-1/`에 추출한 뒤 수행했다. 새 worktree는 만들지 않았다. 5 MiB 초과 media archive member만 제외했으며 선택한 테스트와 모든 등록 해시 입력은 존재한다. 기존 Python 3.12.13 환경을 재사용하고 공용 `run_locked()` 잠금을 획득했다. 다른 소유자의 잠금은 기다렸으며 해제하지 않았다. 과거 blob 검사에만 `GIT_DIR=/Users/changmin/projects/ugrp/.git`을 제공했다.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, BLAS/OMP/MKL/VECLIB 스레드 1, MuJoCo/torch import 및 실제 vision worker 차단을 적용했다. 수정된 guard는 TensorBoard 기존 media 테스트의 임시 localhost HTTP 연결만 허용하고 외부 네트워크를 차단한다. 실제 물리·렌더·모델 호출은 없다. wall 시간은 검사 실행 시간이며 로봇 성능 측정이 아니다.

| 현재 PR tree 검사 | 결과 |
|---|---|
| #303: evidence, eval, TensorBoard export + 공통 소스 고정 검사 | **275 passed** |
| #303: 내부 기록/시행 이름의 독립 반례 | **7 failed**, 모두 잘못 수락한 성공 1.0을 readback |
| #305: environment registry, final env, scenario, integration seam + 공통 검사 | **320 passed** |
| #307: mixed jobs + 공통 검사 | **92 passed** |
| #311: E2E manifest, RobotInputBoundaryTests + 공통 검사 | **179 passed** |
| #311+#312 실제 merge-tree: P03 연결 검사 | **9 passed** (기타 112 deselected; 위 단독 PR의 소스 고정 검사와 구분) |
| #305+#292 실제 merge-tree: 기반/환경 candidate 및 registry 변조 | 스크립트 종료 0. base 274 / composed 280개 source, 기존 dock factory 2회, registry 변경 때 기존 경로 유지·새 후보 거절 |

공통 검사는 registered-source 22개 + study source-pinning 33개 + door-relax 등록 보존 1개다. PR 간 공통 검사의 반복을 서로 다른 기능 검사 총합으로 부풀리지 않는다.

| 수정 전 파일/동작을 복원한 음성 대조 | 현재 테스트 결과 | 의미 |
|---|---|---|
| #303 이전 exporter (`cbac1df`) | **34 failed / 1 passed** | A303-1/3의 35개 반례 중 기존에도 terminal=false는 거절. 새 identity·생략/타입 검사는 실제 결함 검출 |
| #303 이전 runner (`cbac1df`) | **1 failed** | A303-2 등록 바이트 검사 검출 |
| #305 이전 resolver (`5a852fb`) | **2 failed** | 기존/새 경로 모두 `unknown tagged zone map` 도크 반례 검출 |
| #305 이전 runner/provider/scenario (`5a852fb`) | **2 failed** | 등록 source hash 및 기존 closure의 숨은 환경 의존성 검출 |
| #305 source_files에서 JSON 의존성을 빼는 통제 변이 | **12 failed** | 6개 지도 pin 및 6개 파일 변이 검사가 누락을 탐지. 수정 전 파일 그대로의 검사는 위 행과 구분 |
| #307 이전 공용 세 파일 (`6bb522b`) | **4 failed** | 3개 등록 byte 검사 및 기존 mixed admission/closure 분리 검사 검출 |
| #311 이전 planner (`bd011c9`) | **3 failed** | 카메라·새 참조 파일 변경 및 P03 JSON 삭제를 구 코드가 놓침 |

이 음성 대조는 errors/수집 오류 없이 기대한 테스트 본문에서 실패했다. 대상 archive의 모든 검토 변경 파일 해시가 대조 후 원본으로 돌아왔음을 확인했다.

수정 전 음성 대조는 **현재 테스트를 그대로 유지하고** 피검토 PR의 수정 전 생산 파일만 임시 archive에 되돌렸다. 각 검사가 끝나면 원본 bytes를 복원했다. #311의 구 planner에는 새 테스트 수집에 필요한 `EVALUATION_PATH` 상수명만 제공했으며 P03 해시 동작은 추가하지 않았다. 수집 오류를 결함 검출로 세지 않는다. #305의 별도 data-pin 제거 변이는 JSON 의존성 누락을 일반적으로 검출하는 추가 대조다.

초기 실행 오류도 보존했다. #303 첫 시도는 OS tempfile 루트와 별도로 정한 basetemp가 달라 synthetic export가 차단됐고, 과도한 네트워크 guard가 기존 localhost media 검사 2건을 막았다(247 passed / 28 failed). TMPDIR와 basetemp를 맞추고 localhost만 허용해 다시 검사했다. #305 첫 시도는 검토자가 `test_zone_final_environment.py`로 잘못 지정해 수집 전에 종료됐다(실제 파일은 `test_zone_final_env.py`). 이를 제품 결함이나 음성 대조 통과로 세지 않는다.

## 소스 보존·합성·CI 및 저장 범위

네 PR 각각에서 v6e source **85/85개**가 원 등록 해시와 일치한다. 이전 피검토 HEAD에 존재하는 `prereg*.json` **53/53개**도 각각 바이트 동일하다. 아래 실행 결과에는 요구된 `tests/test_zone_pair_registered_source.py` **22개 전체**와 `tests/test_zone_study_source_pinning.py` **33개 전체**, 기존 door-relax 등록 보존 검사도 포함했다. 일부 테스트만 고르거나 해시 기대값을 바꾸어 통과시킨 것이 아니다.

#305+#292(`4c6b439f3f7c9a147c901f8b260a1e214d4eb396`) 합성은 `experiments/README.md`의 **텍스트 충돌 1개**가 있다. Git merge-tree의 진단 tree `a18101590c7d55d7d49988c6ffdabeafe872ee0b`를 임시 추출하여, 해당 인덱스를 읽지 않는 후보/도크 검사를 수행했다. 충돌 없는 실제 병합이라고 주장하지 않으며 합성 시 문서 충돌 정리가 필요하다. 기존 candidate가 registry 변경과 무관한 것과 새 환경 candidate가 그 변경을 거절하는 것을 모두 확인했다.

#311+#312(`919f78ef6ebaf2495633338bcb1b9510f46399bd`)는 텍스트 충돌 없이 tree `3f75485769e430f283835824bd69c8db0c9c8bcb`로 합성됐다. 실제 P03 JSON/worker가 들어간 상태에서 위 9개 검사가 통과했다. #312 자체의 v6e 회귀나 다른 병합 자격을 승인한 것은 아니다.

제출 전 원격 재조회에서 네 PR의 HEAD는 검토 SHA와 같았다. **#303/#305/#311은 33/33 check SUCCESS**, #307은 **31 SUCCESS / 2 CANCELLED**다. #307의 취소 검사는 [ubuntu-simulation-runtime](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36717376631/job/109900402944), [individual-proxy-bootstrap](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36717376631/job/109900402925)이며 정상 재실행·통과가 실제 병합 전에 필요하다. `offline-regressions`만 성공했다고 전체 CI 통과로 쓰지 않는다. 네 PR 모두 조회 시 `BEHIND`라 최신 base 반영 뒤 영향 범위 재검증도 필요하다. **MERGE는 코드 수정 검증 의견이며 이 남은 병합 관문을 면제하지 않는다.** 검토자는 workflow 취소/재실행·자동 병합 예약·실제 병합을 하지 않았다.

본 검토의 두 테스트 잠금은 종료 후 반환됐다. 뒤이어 다른 작업이 획득한 잠금은 건드리지 않았다.

정확한 명령·JUnit 개수·SHA-256·source 보존·합성/CI snapshot은 [verification.json](review_fixes_1/verification.json)에 저장한다. 원본 로그·JUnit·검토 driver는 `/Users/changmin/projects/ugrp/outputs/review-fixes-1-20260930/`, 합성 JSON/JPEG/event fixture는 위 `/private/tmp/ugrp-review-fixes-1/`에 로컬 보관한다. Git에는 이 문서와 작은 재현 코드·검증 요약만 올리며 로컬 원본 전체의 원격 백업을 주장하지 않는다.

신규 물리/학습/평가 cohort가 없는 코드 검토이므로 공용 TensorBoard snapshot·서버·UI를 변경하지 않았다. synthetic event readback을 실제 연구 dashboard 검증으로 표현하지 않는다. UGRP 예외에 따라 Drive 작업도 없다.
