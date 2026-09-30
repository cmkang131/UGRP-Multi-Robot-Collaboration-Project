# E2E Batch G — 첫 독립 재현성 검토

검토일: 2026-09-30–2026-10-01 KST. 검토자: Codex.
기록 브랜치: `codex/review-e2e-batch-g`.

| PR | 검토한 고정 SHA | 판정 |
|---|---|---|
| #325 / T03 | `be97d9dd53638a1efbda7627b420bd9b1cbd9880` | **BLOCK** — 현재 v6e가 고정한 소스 5개 변경, 등록 회귀 5개 실패 |
| #329 / T13b | `823a1ac6d2d62b7cd0e12b3bbc01dfbea0f5f3e5` | **MERGE** — 명시된 오프라인 복구 결정·평가 분리 범위에서 새 지적 없음 |

MERGE는 해당 SHA의 독립 코드 검토 판정이다. 두 PR의 Draft 상태와 실제 병합은 변경하지 않았다. 최종 환경 실행기 연결·물리 인수·E2E 성공은 두 PR 모두 미완료다.

## 범위와 방법

- `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`, P09의 `REQUIREMENTS.md`와 `TASKS.md`를 읽고 T03/T13b 및 공통 입력·4조건 계약에 대조했다.
- 시작 시 `git fetch origin`과 열린 PR/본문/댓글을 확인했다. 기준 main은 `d7ee112e22018055ec08e1098c3f33a7a06cb420`이었다. 두 원격 PR head는 종료 전 재조회에서도 위 SHA와 같았다.
- 각 PR을 `git archive origin/<branch> | tar -x -C <scratch>`로 풀었다. 새 git worktree는 만들지 않았고 PR 코드와 `.github/workflows`를 수정하지 않았다.
- 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. PR #328에 따라 호스트 잠금 없이 오프라인 검사만 했다. MuJoCo/Torch import 및 socket 연결을 차단하는 pytest plugin을 사용했다. `HiddenEventPhysics.apply`는 가짜 배열/actuator/module로만 검사했다. 물리 step·world 생성·카메라 렌더·모델 호출은 0이다.
- 과거 봉인 blob 조회용으로 `GIT_DIR=/Users/changmin/projects/ugrp/.git`, `GIT_WORK_TREE=<scratch>`, `GIT_OPTIONAL_LOCKS=0`을 지정했다. Python 코드와 fixture는 각 PR archive에서 읽었다. 역사 조회의 HEAD는 당시 main이며, 과거 등록 파일은 두 후보와 main에서 동일하다.
- 검사 후 전체 추적 파일을 git blob ID와 대조했다. #325의 7,963파일 / 1,167,952,334바이트, #329의 7,993파일 / 1,170,842,882바이트 모두 archive 원본과 일치했다. mutation은 별도 프로세스의 메모리에서만 적용했다.

## 한 묶음의 지적

### G-325-1 / P1 — 기존 v6e 소스 고정을 깨므로 병합 차단

원인 위치는 #325 SHA의 다음 다섯 파일이다.

| 위치 | 변경 내용 |
|---|---|
| `harness/owncam_delivery_shared.py:8` / `:34` | 새 색 helper import와 `ColorBoxDeliveryMixin` 상속 |
| `harness/zone_own_deliver.py:41` / `:214` | cyan clip 검사를 kind/profile 함수로 교체 |
| `harness/zone_own_executor.py:116` | color profile 상태·dispatch·factory·placement 연결 |
| `harness/zone_own_status.py:96` | job 종료 뒤 kind 보존과 holding 조건 변경 |
| `harness/zone_own_team_host.py:141` | factory에 color profile 전달 |

이 파일들은 `experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json`의 **현재 v6e DRAFT 소스 85개**에 포함된다. 등록 JSON은 그대로인데 이 5개 소스의 SHA-256이 달라졌다. 기본 cyan 경로를 보존하거나 색 기능을 opt-in으로 두어도 바이트 고정 검사에는 예외가 없다.

구체적 반례: 정상 v6e 등록의 `v6e-s911-bv6g`를 **실행 없이 준비 검사**하면 `scripts/zone_pair_v6_contract.py:285`에서 `ValueError: v6 source contract/hash mismatch`가 난다. `test_zone_pair_registered_source.py:118`의 scene/current contract 동일성 검사와 `:143`에서 정상 등록을 먼저 읽는 네 오류 주입 검사가 실패한다. `test_zone_study_source_pinning.py`의 33개 통과는 변경된 입력이 새 bundle hash에 반영되는 검사이며, 과거 v6e 바이트 보존을 대신하지 않는다.

같은 다섯 파일을 시작 main과 #329에서 검사하면 모두 기존 pin과 일치한다. 기존 main의 실패를 이 PR에 잘못 귀속한 사례가 아니다. #325 원격 CI도 동일한 5개 실패와 `test_zone_pair_door_relax.py::test_registered_sources_are_not_touched_by_this_change` 실패를 기록했다. [CI run 36718595717](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36718595717)의 필수 `offline-regressions`는 FAILURE다.

**수정 조건:** 기존 등록 JSON·해시·과거 성공 기록을 다시 쓰거나 검사를 완화하지 말고, 고정된 5개 소스 바이트를 보존하는 새 버전/진입점으로 색 확장을 분리한다. 변경 범위에 맞춘 새 실행 의존성 기록과 독립 재검토 후 두 pin 검사 및 정상 CI를 다시 통과해야 한다. #325는 T03 기능 검사 일부를 충족했지만 이 보존 조건을 충족하지 못한다.

반례는 `tests/test_review_e2e_batch_g.py`에 있다. `strict=True, raises=AssertionError`로 5개 파일을 각각 xfail 처리한다. git 조회 실패나 파일 누락은 xfail로 숨기지 않는다. 고정 PR에서 **1 passed, 5 xfailed**, `--runxfail`에서는 **1 passed, 5 failed**를 확인했다. 동일 검사를 시작 main 트리에 대조하면 **6 passed**다. 후속 트리는 `REVIEW_E2E_G_PR325_TREE`로 지정할 수 있으며, 수정 후에는 xfail을 해제해 재검토한다.

## TASKS.md 충족 범위

| 항목 | #325 T03 | #329 T13b |
|---|---|---|
| 요구 논리 | 명시적 cyan/red/green kind가 검색·coarse order·wrist·holding·placement로 전달됨. unknown kind, 잘못된 factory와 다른 kind의 배송 판정 거절 | 이동 unheld→move/held→no-op, 낙하 held→open fault/unheld→no-op의 기존 네 분기를 그대로 유지. 학생 복구와 평가 집계 분리 |
| RGB/가짜 검사 | 저장된 합성 RGB 25개와 라벨/PNG/JPEG 해시 검증. 3색 혼동·그림자·가림·검은 화면·clipping·잘못된 holding/placement 검사 142개 통과 | 새 검사 53개 통과. 연속 own RGB의 held→unheld/resting에서 refresh 전에 cancel; 추적 소실은 unknown; 빈 pickup ROI 두 관측 뒤 지역 부재; 재관측·T13a 검사 후 재시도 |
| 라벨 한계 | 라벨은 detector 결과가 아닌 fixture 제작 규칙에서 정함. 최종 카메라·조명 실측 라벨이나 일반 인식 정확도 증거는 아님. fixture와 최초 구현은 같은 git 커밋 `ae9726a3`에 있어, ‘구현 전 고정’의 시간 순서는 git 이력만으로 독립 확인되지 않음 | `OwnFrame/Detection/PickupView`는 자기 RGB 추론을 받는 계약이다. 실제 recognizer/ROI 판정은 미연결이며 hash 자체가 인식의 진실성을 증명하지 않음 |
| 입력 경계 | 변경한 제어 경로는 own RGB, own pose 추정, 정적 지도·보정, 공개 주문과 발행 PWM을 사용. GT·현재 sim 상태·partner private 상태가 새 입력으로 들어가는 경로 발견 없음 | controller는 평가 모듈을 import하지 않음. 공개 initial_location 불변. 사건 시각·효과·holder·private pose를 바꾼 3 actor×2 identity×4조건×4변형=96개 fake 흐름의 입력/결정 불변 검사 통과 |
| 네 조건 동일성 | 같은 `WristColorBoxDelivery`/profile/상태 enum, condition별 제어 분기 없음. 네 조건 fake action 및 실제 executor/factory 전달 검사 통과. 실행 가능한 최종 4조건 구성은 아직 미등록 | 같은 `RecoveryJobs`와 상수·API/enum을 사용. 네 조건의 고정 action·private 변화 비간섭 통과. host의 상대 상태 기반 선택 없음 |
| cyan/선행 회귀 | M1 21개, owncam memory 44개와 291 subtests 통과. legacy cyan default/다른 kind 거절 보존 | T13a 71개, 공개 입력 45개, 공통 계약 53개 통과. specific identity/red/can 미지원은 계속 거절 |
| sealed/pinned | 과거 등록 JSON·원본 시나리오 보존. **현재 pin 85개 중 5개 불일치**, 등록 검사 17 passed/5 failed; bundle pin 33 passed | 현재 pin 85개 전부 일치. 등록 검사 22 passed, bundle pin 34 passed. 원본 s5/v1·v2 사건 30.0/62.5초와 initial_location 보존 |

#329의 범위 제한은 문서와 일치한다. 현재 T13a는 원본 s5의 specific cyan identity를 확정하지 못하고 red/can target 실행기도 지원하지 않는다. 실제 target-aware backend·최종 환경·원본 4물건과의 통합은 물리 인계 전 관문이다. 이 제한을 없애려고 GT lookup이나 거짓 identity를 허용한 코드는 없다. 새 반례는 확인되지 않았다.

## 직접 재현한 검사와 mutation

| PR | 직접 검사 결과 |
|---|---|
| #325 | 271 passed + 291 subtests passed, 제품 회귀 5 failed, import guard 차단 1개. 신규 색 142개는 모두 통과 |
| #329 | **278 passed** = 새 복구 53 + T13a 71 + 공개 입력 45 + 공통 계약 53 + 등록 pin 22 + bundle pin 34 |

#325의 추가 1개는 검토자가 `test_zone_own_executor.py` 전체를 선택하면서 포함한 `test_team_host_feeds_each_executor_only_its_own_camera`다. guard가 `pytest.importorskip('mujoco')`에서 import를 막았으며 world 생성 전 종료했다. 제품 결함 5개와 구분한다. 재현 명령에서는 이 테스트를 제외한다. 최초 두 명령의 잘못된 파일명으로 인한 collection 실패(실행 0개)도 raw에 보존했고 검증 건수에 넣지 않았다.

각 mutation의 원본 테스트는 위 baseline에서 통과했다. 다음 변경을 메모리에만 주입하면 **12/12 검출**, 모두 assertion failure이며 collection/setup error는 0이었다. 이는 선택한 12개 변경에 대한 검사이며 전체 mutation coverage 수치는 아니다.

| PR | 제거/퇴행시킨 논리 | assertion 실패 수 |
|---|---|---:|
| #325 | red/green admission을 cyan-only로 되돌림 | 2 |
| #325 | 검색의 요청 kind 필터 제거 | 3 |
| #325 | red hue를 cyan band로 바꿈 | 1 |
| #325 | attachment의 kind를 cyan으로 고정 | 2 |
| #325 | placement kind 불일치 차단 제거 | 1 |
| #325 | clipping 검출 kind를 cyan으로 고정 | 4 |
| #329 | 취소 backend fault 차단 제거 | 1 |
| #329 | 낙하 관측 뒤 cancel 제거 | 1 |
| #329 | 두 빈 관측 뒤 부재 판단 제거 | 1 |
| #329 | no-op를 실제 효과 분모에 포함 | 1 |
| #329 | held 이동 no-op 분기 제거 | 1 |
| #329 | unheld 낙하 no-op 분기 제거 | 1 |

## workflow와 GitHub CI

시작 main `d7ee112e`와 두 PR의 `.github/workflows`는 파일 내용이 같았다. 종료 전 fetch에서 main이 **`26545c2499f94c3f99a5d650f7cc8ea992f24196`**으로 전진했다. 이는 별도 [#332](https://github.com/kcm0127-dotcom/ugrp/pull/332)가 Ubuntu 두 job의 timeout을 10→15분으로 바꾼 병합이며, main의 다른 파일 변경은 없다.

따라서 마지막 시점의 **직접 `git diff origin/main <PR>`에는 `tests.yml` 차이가 있다**. 두 PR이 도입한 변경인 `git diff origin/main...<PR> -- .github/workflows`는 모두 비어 있다. 최신 main과의 완전한 파일 동일성은 미충족이며, 원인은 검토 중 base 전진이다. 작성자/조정자는 통합 시 main의 #332 변경을 보존하고 병합 대상의 CI를 확인해야 한다. 이 검토에서는 workflow를 수정하지 않았다.

#329 [CI run 36730335077](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36730335077)의 head는 검토 SHA와 같고 33개 check 모두 SUCCESS였다. 이것은 원격 CI 확인이며 로컬 278개 재현과 별도 증거다. #325 필수 CI는 위 P1과 같이 실패했다. CI 취소·재실행·면제 요청은 하지 않았다.

## 물리 인계의 구체성과 남은 관문

- **T03:** `PHYSICS_CHECKS.md`/`physics_proposal.json`에 red→B, green→C 각각 정상/다른 색 도전, 고정 배치·spawn·r1 배정, staging 포함 **4×900=3,600 SIM초**가 있다. negative 물체의 실제 가시성 미확인은 실패 도전 통과로 세지 않는다. v3 provider/FK/IK/카메라 연결, P02 distractor 표현, 라벨 고정·새 bundle/workflow가 선행이며 기존 v3 consumer gate는 거절한다.
- **T13b:** `SIM_CHECKS.md`에 seed 641, 동일 초기 배치/구성, 네 사건 분기 각 900초로 **총 3,600 SIM초**가 있다. 원본 30.0/62.5초를 유지하고, close 명령만으로 held를 확정하지 않는다. 효과 있는 사건의 복구율과 전체 할당·no-op·분기 미성립·HOST_ERROR 분모를 구분한다. 원본 두 사건을 모두 남기되 focal event를 사전에 지정한다.
- 두 문서는 최종 3D v3/walls_v3/표식0/weld OFF/cargo_noslip_v1, cap 종료·raw 보존·별도 TensorBoard snapshot/readback을 요구한다. cap은 최소 진단 제안이며 실제 물리 성공을 주장하지 않는다. 본 검토는 새 실험 결과가 없는 코드/fixture 회귀이므로 TensorBoard 변환·viewer를 만들지 않았다.

## 재현 명령과 원본

원본/로그: `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-g-20260930/`.
로컬 raw 보관이며 원격 백업으로 세지 않는다. 검토 문서와 반례 테스트만 Git에 보존한다.

```sh
# 후보별로 빈 scratch를 만들고, 지정 head가 위 SHA인지 먼저 확인한다.
git archive origin/codex/red-green-m1 | tar -x -C <scratch325>
git archive origin/codex/event-recovery-noop | tar -x -C <scratch329>
# offline_guard.py는 #325의 experiments/2026-09-30-cap-t03-redgreen/에 있다.
# 각 scratch에서, 공용 guard 디렉터리와 현재 scratch를 PYTHONPATH에 넣는다.
export GIT_DIR=/Users/changmin/projects/ugrp/.git
export GIT_WORK_TREE="$PWD"
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
# 기존 Python 환경으로 실행; PR #328에 따라 host lock을 사용하지 않는다.
python -m pytest -p offline_guard -q \
  tests/test_zone_own_executor_color_boxes.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_own_executor.py tests/test_m1_owncam.py tests/test_owncam_memory.py \
  -k 'not test_team_host_feeds_each_executor_only_its_own_camera'
# #329 트리:
python -m pytest -p offline_guard -q \
  tests/test_zone_own_executor_recovery.py tests/test_zone_identity_jobs.py \
  tests/test_zone_study_inputs.py tests/test_zone_study_contract.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py
# 검토 브랜치의 반례:
python -m pytest -q tests/test_review_e2e_batch_g.py
python -m pytest -q --runxfail tests/test_review_e2e_batch_g.py
```

`run_mutations.py`에는 정확한 12개 치환 문자열·대상 테스트·guard/subprocess 실행 방법이 있고, `mutation-summary.json`에는 각 return code·failure/error 수·원본 소스 해시가 있다. `audit_trees.py`/`pr*-tree-audit.json`에는 전체 archive 불변 확인과 85개 pin 비교가 있다. JUnit은 `pr325-r1.xml`, `pr329-r1.xml`, `counterexamples*.xml`에 남겼다.

오프라인 등록 검사만 다시 실행한 `pr325-pins-only.log`에서도 **17 passed, 5 failed**를 재현했다. 환경 버전·전체 주요 산출물 해시는 `review-verification.json`에 보존했다.

| 로컬 증거 파일 | SHA-256 |
|---|---|
| `pr325-r1.xml` | `b2f379777480cbb7e64bc543a7b06cde4ba1ffee36faf6d760987e2ff0332ed7` |
| `pr325-pins-only.log` | `9fb8b942ed74f72147986bb8799b90705fc6bf7ce4199bc11f0a8a769d6c8eb3` |
| `pr329-r1.xml` | `33e630763ffef517e59b31f757817fa45ecea0819310928e80dc1f6b40ae3c6a` |
| `mutation-summary.json` | `79ac5267e71e5c9a9a1499f580d46a16ae93ea7c48f5c3e54997847ff3f6470a` |
| `run_mutations.py` | `9b76a8d74614b77fb5c28bf0177eba062a81030c17ebd59aabafcf08f62c6c9a` |
| `pr325-tree-audit.json` | `aa16e3a8ba50a90ae5f88e771f808f080fd15431373d1316a8444963a75d7ece` |
| `pr329-tree-audit.json` | `08eb1d97aa092565f48159c96ca29f1952d0588970cff59bcea0fb62d54c676d` |
| `counterexamples-unmasked.xml` | `3e80af78bd1d2dfb205456e65028e00e3b8e74fba52a3e0a52204c34ed915b2b` |
| `review-verification.json` | `5936c681e2b2b4594a2ad968ab210f16d3dc5d06137750f1ed2899d8a9fb54bd` |
