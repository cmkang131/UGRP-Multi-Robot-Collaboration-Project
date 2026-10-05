# E2E readiness batch D — 독립 반례 검토

2026-09-30, Codex. **#313 MERGE, #314/#315 MERGE AFTER FIXES.**
판정은 각 PR의 문서·정적 API 범위에 한정한다. 세 PR 모두 E2E 실행 준비 승인이 아니다.
이번 작업은 검토 기록과 draft PR만 제출하며 대상 PR을 병합하거나 수정하지 않는다.

## 기준과 확인 범위

| 대상 | 검토한 HEAD |
|---|---|
| main / 검토 브랜치 시작점 | `c12796676802ab54cad2f0635e3e96e911691c76` |
| #313 T11 | `9ae84551e54c4356886539362e12daf130d0a5cb` |
| #314 T09a | `e9ee23ea89bc8e1c971f0b719cd8971942a14779` |
| #315 T08a | `823ca2ced2fb65e771ce2be9c08a2864e08db804` |
| #292 | `3c4fe30e2197518443b195392212b0341507ac59` |
| #299 | `c86d9bac62036904ecc641db5e59e79edb58dec2` |
| #301 | `2ff92e9fbeff1b90b0aa35104a9766753e67f94e` |
| #302 요구 문서 | `bd95530a2d5a8b8467620809749273068a7ed55d` |

AGENTS.md, README.md, docs/current_status.md, CONTRIBUTING.md를 먼저 읽었다.
main에는 [P09 prompt](task_prompts/P09_scenario_capabilities.md)가 있고, 상세 T08a/T09a/T11은
아직 열린 #302의 [TASKS.md](https://github.com/kcm0127-dotcom/ugrp/blob/bd95530a2d5a8b8467620809749273068a7ed55d/experiments/2026-09-30-scenario-capabilities/TASKS.md)에 있다.
각 작성자가 인용한 `dec67997` 이후 이 TASKS.md의 변경은 없다. T08a/T09a/T11을 이미 main에 병합된 상세 prompt로 잘못 취급하지 않았다.

`git diff origin/main...origin/<branch>`와 정확한 PR blob을 검토했다.
추가 worktree 없이 선택 경로를 `git archive`로 `/tmp/ugrp-review-e2e-d-20260930/{313,314,315}`에 풀었다.
기존 Python 3.12.13 환경과 공용 잠금을 사용했고 MuJoCo/모델 SDK import와 network connect를 차단했다.
**로컬 물리·렌더·모델 호출·학생 trial은 0회**다. 아래 수치는 정적/fake 검사이며 TensorBoard 실험 성공률로 변환하지 않는다.
Google Drive 작업은 없다.

## 판정과 완료 기준

| PR | 판정 | 완료한 범위 | 남은 일 |
|---|---|---|---|
| #313 | **MERGE** | 세 필요조건·자기 관측 종료식·can any-heading/1.67 mm/타 화물 포함 경로 반례·pivot 비교·H2 영향·미산정 물리 예산을 문서화 | MINOR D3. 코디네이터의 설계 선택과 후속 controller/사전 등록은 별도 |
| #314 | **MERGE AFTER FIXES** | 두 문 후보, 방향/heading, 전체 v3 편대의 연속 병진 검사, 명시적 refusal, private 변화 비간섭 | MAJOR D1: 한 운반자를 빼는 회귀를 신규 검사가 모두 놓침. 전체 편대 검증의 완료 근거를 보강해야 함 |
| #315 | **MERGE AFTER FIXES** | 세 남북 초기 자세, 공개 coarse sheet와 오차/ID/hash, 역할별 v3 geometry, 벽·경계 검사, 실행 불가 반환 | MAJOR D2: carrier 이동 형상이 비어도 전체 sweep 검사가 통과함. 독립 기대 형상으로 검사해야 함 |

**BLOCKER는 발견하지 않았다.** D1/D2는 현재 구현에서 운반자를 실제로 누락했다는 지적이 아니다.
현재 코드에는 전체 형상이 있다. 그러나 요구한 핵심 안전 회귀를 시험이 검출하지 못함을 변이로 재현했으므로,
정적 계약의 검증 완료 전에 작은 테스트 수정을 요구한다. 원래 suite의 통과만으로 이 공백을 닫을 수 없다.
GitHub CI는 조회 당시 세 PR 모두 대기/진행 중이었으며 전체 green을 확인하지 않았다. MERGE는 검토 의견이고 실제 병합 가능 판정이나 실행 허가가 아니다.

## 지적과 반례

### D1 — MAJOR — #314: 뒤쪽 운반자가 빠진 경로도 신규 62개 검사가 통과한다

- 근거: `tests/test_zone_own_executor_door_routes.py:74-92`의 독립 전체 footprint 확인은 start/goal의 y가 문 중심과 같은 직선 사례다.
  두 문 선택·우회 사례 `:104-113`은 후보 ID/선택만 확인한다. 모서리 반례 `:135-145`는 앞쪽 end_pos만 막는다.
- 구현 근거: `harness/zone_static_door_routes.py:145-163`은 footprint의 xmin/xmax로 완전한 통과와 회전 없는 옆 이동 시작점을 정한다.
  뒤쪽 운반자가 footprint에서 빠지면 문을 덜 빠져나온 상태에서 옆 이동을 허용할 수 있으므로, 이 부분은 중요한 회귀 경계다.
- 재현: `_formation`의 반환에서 long_beam의 `parts`를 `item_parts + carrier_parts['end_pos']`로 바꾼 독립 프로세스에서
  **신규 suite 62/62가 통과**했다. 역할 입력 자체는 두 역할을 유지해 `INVALID_FORMATION` 검사도 통과한다.
  원본 파일이나 원격 PR은 바꾸지 않았다. [변이 실행기](review_e2e_batch_d/guarded_pytest.py),
  [실제 출력](review_e2e_batch_d/20260930T211506-314_drop_trailing.txt).
- 추가 정적 반례: 원본 두 문 지도에서 `(1,-1.2,0)→(3.5,-1.2,0)`, `door_narrow` 요청 시
  원본은 x=`2.8482`까지 간 뒤 옆 이동한다. 변이는 x=`2.575`에서 옆 이동하여 `(2.575,-.575,0)`과
  `(2.575,-1.2,0)`에서 end_neg 형상이 `wall_divider_1`과 겹친다.
  즉 실제로 잘못된 정적 경로를 만드는 변이가 통과한 것이다. [계산 결과](review_e2e_batch_d/counterexample-314.json).
- 필요한 수정: 두 문과 양방향에서 **문 통과 후 옆 이동**이 있는 경로를 검사하고,
  planner 반환 footprint를 믿지 않는 전체 cargo+두 carrier의 독립 sweep으로 모든 후보를 재검사한다.
  end_neg/end_pos 각각만 닿는 벽 fixture를 추가해 어느 쪽 누락도 반드시 실패하게 한다.
  현재 정상 planner 통과와 위 변이 실패를 함께 확인하면 이 지적을 닫을 수 있다.

### D2 — MAJOR — #315: 검사 대상 geometry를 planner 출력에서 가져와 빈 carrier를 검사하지 않는다

- 근거: `tests/test_beam_initial_pose_plan.py:81-103`, 특히 `:92-97`은 반환된
  `local_parts_at_endpoints`를 기대 형상으로 사용한다. 이 목록이 비면 `n=0`이고 carrier 병진 검사 루프가 0회 돈다.
  남는 것은 `search_at_pre` 검사뿐이다. 모서리 검사 `:148-163`도 반환된 bounds에서 장애물을 만들므로 같은 누락을 공유한다.
- 구현 근거: `harness/beam_initial_pose_plan.py:209-213`은 현재 chassis/arm 양끝을 제대로 포함한다.
  문제는 이를 나중에 빠뜨려도 “전체 carrier sweep” 회귀가 방어하지 못한다는 점이다.
- 재현: `TeamFootprintV3`의 stations/item은 유지하고 양 역할의 `carrier_parts`를 빈 목록으로 반환하도록 바꾸어도
  **신규 suite 56/56가 통과**한다. 팔만 제거해도 56/56다. [전체 carrier 누락 출력](review_e2e_batch_d/20260930T211713-315_drop_carriers.txt),
  [팔 누락 출력](review_e2e_batch_d/20260930T211506-315_drop_arms.txt).
- 추가 정적 반례: 공개 coarse `(1.3,.4,1.570796)`의 허용 오차 안인 beam pose
  `(1.25,.35,1.4835295374)`에서 end_neg 정류장 형상의 모서리 `(1.118816959,.055312013)`에
  half-extents `.001×.001 m`의 정적 벽을 둔다. 원본은 `INITIAL_APPROACH_BLOCKED/end_neg`로 거절하지만
  변이는 `STATIC_INITIAL_GEOMETRY_ONLY`를 반환한다. 실제 배치를 바꾼 물리 실행이 아니라 작은 합성 지도 반례다.
  [계산 결과](review_e2e_batch_d/counterexample-315.json), [재현 코드](review_e2e_batch_d/counterexample.py).
- 필요한 수정: 허용 v3 규약으로 별도 구성한 chassis/arm 기준 형상과 사전 고정한 기대 station/prestation으로 sweep을 검사한다.
  각 역할의 chassis/arm 존재·부품 수·양끝 대응도 확인하고, search 자세는 깨끗하지만 접근 중/정류장에서만
  한 carrier가 벽과 겹치는 양성 차단 사례를 넣는다. coarse 오차의 모서리와 yaw 내부 극값 검사는 유지한다.
  빈 carrier/팔 누락 변이가 실패해야 완료로 판단한다.

### D3 — MINOR — #313: pivot 권고를 뒷받침하는 report의 방향·겹침 연결을 고정하지 않는다

- 근거: `experiments/2026-09-30-s6-order-design/test_audit.py:95-101`은 중앙 회전의 can 겹침과
  `unmeasured` 표기만 확인한다. 접점 회전 수식 검사 `:36-44`는 유용하지만 report 행의 방향과 겹침 수 연결은 검사하지 않는다.
- 재현: `pivot_report` 반환에서 end_pos_contact 행의 `delta_deg` 부호만 뒤집어도 **신규 13/13 통과**다.
  [출력](review_e2e_batch_d/20260930T211506-313_flip_pivot_report.txt).
- 권고: A −90°의 끝 중심/고정점/겹침 0과 A +90°의 can 겹침을 report 수준에서 함께 검사한다.
  문서·저장 자료와 현재 수식은 일치하므로 설계 문서 병합을 막는 문제로 보지는 않는다.

## #313 pivot 권고 — A, end_pos 접점 고정 · 시계방향 90°

**하나만 권고하면 A −90°를 후속 진단 후보로 택한다. 최종 결정은 코디네이터가 한다.**
근거는 #313 `README.md:103-148`, `audit.py:121-161`이다.

- 원본 의미에 가장 가깝다. 접점은 약 `(1.1, -.58)`이고 beam 중심은 약 `(.83, -.58)`로 이동한다.
  end_pos 차체가 정지한다는 뜻이 아니다. v3에서 두 base의 회전 반경은 약 `.2032/.7432 m`다.
- 기존 2D proxy의 1° sweep에서 A −90°만 두 margin 모두 can 겹침 0이다.
  A +90°와 중앙 회전 양방향에는 can 겹침 반례가 있다. 내려놓기·재파지는 도착 배치와 하중 인계가 미정이며 원본 연속 pivot 의미도 달라진다.
- 이 선택은 회전의 **필요성**을 입증하지 않는다. can은 any-heading이며, 기존 proxy에서는 선행 없이 가능한 자리와 운반 경로가 있다.
  최종 v3 전체 형상, spawn→접근, 파지, 연속 회전, 세 번째 로봇, 후퇴/하중 해제는 미확인이다.
- 기존 structured는 전용 순서 필드가 없어도 여러 상태 메시지로 순서를 만들 수 있다.
  공통 pivot primitive가 s6 순서를 미리 풀어주는 매크로가 되어서는 안 된다.
  structured의 `after/if`나 고수준 완료 enum 추가는 #254 H2의 비교 대상을 바꾸므로 별도 버전·사전 등록이 필요하다.

## 입력 경계·원본·봉인 감사

| PR | 입력·성공 신호 경계 | 기존 결과/default/sealed bytes |
|---|---|---|
| #313 | `audit.py:61-62,78-83,130-143,165-177`은 eval 배치를 읽지만 실험 폴더의 평가 전용 정적 도구다. controller 연결이 없고 `README.md:33-37,158-160`에 runtime 전달 금지를 명시한다. private 변화 시험은 실제 공개 payload builder를 호출한다(`test_audit.py:74-92`). | 실험 폴더 추가뿐. 기존 입력 24/24 hash 일치. 원본 s6/seed/H2/default 변경 없음 |
| #314 | API는 map/자기 허용 추정 또는 공개 coarse cargo pose/공개 목표/정적 formation만 받는다(`zone_static_door_routes.py:186-196`). private 사건/partner state를 조회하지 않는다. API 자체는 출처 인증을 못 하므로 T09b 호출자가 입증해야 한다. 경로 선택은 통과 성공 통보가 아니다. | 새 모듈·시험·기록만 추가. 기존 40/40 hash 일치. runtime import/patch 설치, M1/M2 기본 문 선택, registry/default 변경 없음 |
| #315 | 공개 sheet 생성은 이미 공개한 coarse 입력만 받는다(`beam_initial_pose_plan.py:127-140`). 출처 문자열/hash가 진실성 증명이 아님을 명시한다. 실제 eval 배치로 sheet를 생성하는 어댑터가 없다. `:226-242`에서 executable/e2e_admitted=false, 미검증 항목을 반환한다. | 신규 파일 외 기존 수정은 `scripts/run_ci_tests.py:116`의 시험 1행뿐. 44/44 보호 hash 일치. `.25 m`는 새 계약이고 기존 `.30 m`와 원본 plan/probe golden은 보존 |

세 PR 모두 새 teacher 제어·teleport·측정 관절/접촉/심판에 의한 단계 전환·partner 실시간 상태·weld ON 경로를 추가하지 않는다.
자기 RGB/실제 통신을 실행한 시험은 없으므로 향후 T08b/T09b의 정보 경계까지 검증된 것으로 확대하지 않는다.
private 비간섭 시험은 현재 정적 API/공개 projection에는 의미가 있으나, 미래 어댑터의 GT 입력 누출을 막는 증거는 아니다.

## PR 사이와 #292/#299/#301의 충돌

세 대상 사이 3쌍 및 각 대상과 #292/#299/#301의 9쌍, 합계 **12쌍**을 `git merge-tree --write-tree --name-only`로 검사했다.
모두 exit 0이고 텍스트 충돌은 없다. checkout/index/작업 브랜치를 병합하지 않았다.
[tree 결과](review_e2e_batch_d/merge-tree.json). 이것은 합쳐진 전체 suite나 실행 의미의 호환성 검증이 아니다.

| 조합 | 확인과 통합 시 남은 조건 |
|---|---|
| #313 ↔ #314/#315 | 파일 겹침 없음. T11 수치 sweep은 legacy proxy, #314/#315는 v3 규약이므로 T11의 clear를 v3 성공으로 승계하면 안 됨. #313도 이 한계를 명시 |
| #315 ↔ #314 | 파일 겹침 없음. #315는 북남 beam yaw≈π/2만 지원(`beam_initial_pose_plan.py:123-124`), #314는 동서 고정 heading만 지원(`zone_static_door_routes.py:206-211`). 따라서 두 API를 직결하면 `UNSUPPORTED_ROTATION`이며, 중간 pivot/방향 전환 구현과 검증이 필요. 의도된 별도 과제이며 이번 PR의 숨은 통합 성공으로 세면 안 됨 |
| 대상 3개 ↔ #292 | 현재 runtime 연결 없음. #292 `zone_pair_executor.py:28-50`의 door_1/기존 pose 범위는 그대로다. 새 정적 plan을 b-v6h1 실행 가능 plan으로 바꿔 넘길 수 없음. 연결할 때 `.25/.30 m`, v3 station, 0.85 m/8구간, 자기 추정 인계와 새 소스·bundle/인수를 함께 재검증 |
| 대상 3개 ↔ #299 | 분류·60+12 배치·안전 임계·raw 결과 경로를 수정하지 않는다. 정적 plan 허용은 #299의 접촉/종료 증거를 대체하지 않음. 이번 검토는 #299 분류기 자체 재승인이 아님 |
| 대상 3개 ↔ #301 | 새 등록의 의존성 계약을 자동 적용하지 않는다. 현재 새 모듈은 기존 실행 import 경로 밖이다. 후속 controller가 import할 때는 closure/입력 해시에 포함해야 하며 “정적 helper”라는 이유로 제외하면 안 됨. `execution_dependency_contract.py:143-185,189-208`의 선택 행·기대 digest 검증을 유지해야 함 |
| #315 ↔ #292/#299/#301 | 공통 수정 파일은 `scripts/run_ci_tests.py` 하나다. 시험 추가 위치가 달라 현재 3-way merge는 깨끗함. 합친 뒤 신규 시험 각각 1회 수집·기존 glob 보존을 확인할 것. 현재 대상 PR들은 workflow/bundle 번호를 새로 발급하지 않음 |

#292의 `scripts/zone_pair_v6_contract.py:80-83,132-184`는 최종 classifier와 실행 의존성을 별도로 고정해야 하는 미봉인 경로다.
이번 정적 PR 병합을 #292/#299/#301의 최종 등록·인수 완료로 세지 않는다. 과거 봉인 파일 재작성도 하지 않았다.

## 독립 재검사와 전달 자료

| 검사 | 이번 결과 | 의미 |
|---|---:|---|
| #313 신규 13 + 기존 feasibility 31 | 44 passed | 순서 설계의 정적 반례와 입력 projection |
| #314 신규 62 + 관련 suite 88 | 150 passed | 문 후보/방향/거절·기존 passage/formation/map 회귀 |
| #315 신규 56 + 기존 plan/probe 4 | 60 passed | 공개 sheet·정적 geometry·기존 default golden |
| #313 report 부호 변이 | 13 passed — 변이 생존 | D3 |
| #314 end_neg footprint 누락 변이 | 62 passed — 변이 생존 | D1 |
| #315 양 역할 arm 누락 변이 | 56 passed — 변이 생존 | D2 |
| #315 양 역할 carrier 이동 형상 전부 누락 변이 | 56 passed — 변이 생존 | D2 |

원본 suite 합계는 PR별 실행 **254회**이며 중복을 뺀 고유 테스트 수가 아니다. 테스트 시간은 성능 비교가 아니다.
첫 archive에서 calibration fixture 하나를 빠뜨려 #314는 148 passed/2 failed, #315는 collection error였다.
정확한 각 PR의 `experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json` blob을 추가한 뒤 같은 소스로 재검사했다.
이 실패는 리뷰어의 추출 누락이며 PR 결함에 합산하지 않았다. 실패 출력도 보존했다.

작은 로그·변이 실행기·SHA/명령/보존 검사·merge-tree 결과는 [review_e2e_batch_d](review_e2e_batch_d/)에 있다.
JUnit·잠금·원본 출력은 `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-d-20260930/`에 보존한다.
Git에 올린 작은 기록과 로컬 raw/JUnit 보관을 구분한다. 이 검토에서 새 물리 결과나 TensorBoard snapshot은 만들지 않았다.
Git의 `.txt` 사본은 줄 끝 공백만 정리했으며 원본 `.log`는 그대로 보존했다. 두 해시는 `verification.json`에 구분한다.

작성자는 D1/D2의 독립 기준 형상·차단 fixture를 한 묶음으로 보완하고, 위 생존 변이가 실패하는 결과를 제출하면 된다.
T11 선택, 실제 접근/회전/통과, 최종 봉인, CI 완료와 물리 인수는 코디네이터의 후속 일이다.
