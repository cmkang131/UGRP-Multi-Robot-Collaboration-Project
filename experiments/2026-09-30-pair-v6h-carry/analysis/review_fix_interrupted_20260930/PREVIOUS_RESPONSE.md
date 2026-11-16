# #294 리뷰 응답 — 집계 불일치로 중단 (2026-09-30)

작업 시작 소스: `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`, 브랜치 `codex/v6h-classifier-fixes`.
리뷰 원문: `origin/codex/review-293-294:experiments/2026-09-30-pair-v6h-carry/REVIEW_294_293_astra.md`.
사용자의 “308 cases; discrepancies => stop and report” 지시에 따라 첫 공개 집계 불일치에서 수정을 중단했다. 아래는 완료된 수정 보고가 아니다. 반대하는 지적은 없다.

| 리뷰 항목 | 재현 Y/N | 재현 결과 / 수정 상태 | 회귀 시험 / 남은 일 |
|---|---|---|---|
| 1 BLOCKER: 잘린 기록·집게 필드 | Y | 원 코드에서 t=0 한 행만 있는 trace, `jaws={}`, `lift_m=inf`가 모두 `PASS_CLEAN`. 전체 기록 범위·필수 수치·집게 검증을 시도했으나 중단 후 소스를 원상복구했다. 위치: `analysis/classify_placements.py:75`. | 회귀 시험 추가·신구 비교 미완료. trace 순서·최대 공백·기록 건수·접촉 추적 범위를 함께 검사해야 한다. |
| 2 BLOCKER: 봉인 목록과 시드 누락 | Y | P0…P59의 주 시드만 넣어 `PASS_OBSERVED_CRITERION` 재현. 60+12 목록·배치/사전분포/계획/소스 해시·재시도 연결 검증을 시도했으나 적용하지 않았다. 위치: `analysis/classify_placements.py:152`. | 회귀 시험 미완료. 봉인 자료(manifest)를 받는 평가 경로와 과거 탐색 집계를 구분해야 한다. 이 작업에서 봉인 자료를 만들지 않았다. |
| 3 BLOCKER: 미해결 실패와 L0/L1 창 | Y | 내려놓기 실패 기록이 있어도 `PASS_CLEAN`, 운반 가드 실패+접촉이 있어도 `PASS_CONTACT_RECOVERED` 재현. 시도한 실패 검사가 cA 24/24를 0/24로 바꾸어 중단했다. | **수정안 오류:** `bool(result['failures'])`는 `{'r1': None, 'r2': None}`도 실패로 만든다. 값의 실제 실패 여부를 검사해야 한다. L0 내려놓기·개방·재파지와 L1 의도된 종료를 구분하는 시험·초안 동기화 미완료. |
| 5 MAJOR: σ 표본·시각·누락·가중 | Y | 기존 분석의 100초 전 PF 표본이 인정되며, r2 PF 누락에도 관측 배치가 1로 집계된다. 위치: `../2026-09-30-b-v6h-gain/analysis/gain_cohort_analysis.py:48,64`. | 주 941의 r1/r2×L0/L1, 표본 시각 허용치, 누락 거부, 보조 943의 별도 보고/가중을 정하는 코드·문서·시험 미완료. |
| 6 MAJOR: 비독립 배치 추출과 모집단 주장 | N | 생성기가 앞서 채택한 배치를 `taken`에 추가하는 코드는 확인했으나 독립 재현 스크립트/실패 시험은 아직 만들지 않았다. 위치: `make_confirmatory_placements.py:53`. | 관측 관문 48/60은 유지하고 모집단 주장은 독립 설계 또는 추출법에 맞는 추론이 필요하다고 초안에 명시해야 한다. 아직 문서를 바꾸지 않았다. |
| 9 MINOR: Monte Carlo 경계값 | Y | 저장된 ON 모형에서 `P_ge_48=1.0`, 표준오차(MCSE)=0.0이며 draw 성공/실패 수와 구간 필드가 없다. 위치: `analysis/cohort_sizing.py:160`. | draw 수·모형 내부 모의 추출 오차 구간 추가와 3000/3000 경계값 시험 미완료. 원 수치 산출물은 보존했다. |

## 중단 근거

cA raw: `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-69c2a99a-cA`.
첫 대조 배열 `[케이스 수, 연쇄 통과, 모든 시드 통과 배치, 전체 배치, L0 통과, L1 통과]`는 공개 `[24,24,12,12,24,24]`, 수정안 `[24,0,0,12,24,24]`였다. 첫 불일치에서 검증 루프를 종료했으므로 **나머지 284건을 수정안으로 재검증하지 않았다**. 전체 308건 일치를 확인했다는 주장은 하지 않는다.

대표 케이스 `chain@b-v6h.k1g+p2f:teacher:F_hR2_04:s913:pPOST:VENV`는 `row.first_failure=null`, `chain.first_failure=null`, `result.failures={'r1': null, 'r2': null}`, `termination.outcome=STUDY_LAYER_DONE`, `chain_stop_leg=1`, 두 로봇 `wait_lower`다. `stop_sim_s`와 L1 끝 시각은 둘 다 `61.50000000020264`다. raw의 `category=STAGE_BUDGET_EXHAUSTED`만으로 의도된 stage stop을 실제 timeout이라고 판단해서도 안 된다.

미완성 수정안은 `analysis/review_fix_interrupted_20260930/classifier_attempt.patch`, 원 코드 반례 결과는 같은 폴더의 `old_code_reproduction.json`에 보존했다. 수정안에는 아직 σ 함수 구현·시험·문서 동기화가 없어 실행/적용할 수 있는 후보가 아니다. `classify_placements.py` 자체는 작업 시작 HEAD의 바이트로 복구했다. 원본·기존 집계·배치 파일·제어기·봉인 파일은 수정하지 않았다.

복구 뒤 기존 관련 시험 `tests/test_v6h_classify_placements.py`와 `tests/test_ci_sharding.py`만 실행해 **101 passed**를 확인했다(`analysis/review_fix_interrupted_20260930/baseline_tests.txt`). 이는 원 코드의 기존 시험 통과이며 수정안의 회귀 검증이 아니다. 기존 venv에서 `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest 캐시 비활성으로 실행했다. 잠금을 획득하거나 물리 실행기를 시작하지 않았다.

## 조정자에게 남긴 결정

**OPEN QUESTION FOR COORDINATOR:** 집계 불일치 중단을 해제하고 null 값의 실패 판정을 고친 뒤 작업을 재개할지. 권장 기본값은 null 실패 항목을 실패로 세지 않고 의도된 L1 stage stop을 허용한 뒤, 같은 308건 대조를 다시 수행하는 것이다.

**OPEN QUESTION FOR COORDINATOR:** L0 뒤 내려놓기/개방/재파지의 주 관문과 전체 기록 경계. 권장 기본값은 L0 끝→L1 시작의 바닥 높이 ≤5 mm·기울기 ≤3°·두 로봇 집게 모두 개방을 평가 전용 증거로 확인하고, L1 시작의 재파지/들기를 확인하며, L1 첫 `wait_lower`를 종료로 두는 것이다. 목적지 최종 내려놓기는 이 두 leg 시험 밖이다. teacher 준비 기록은 별도 경계가 고정될 때까지 전체 기록 안전 거부에 남긴다. 아직 채택·봉인한 정의가 아니다.

**OPEN QUESTION FOR COORDINATOR:** 기록 주기와 PF 표본의 허용 시각 차이. 권장 기본값은 기존 trace 0.05 SIM s에 대해 최대 공백 0.051 SIM s, PF는 끝점 이전의 가장 가까운 초기화된 표본 중 나이 ≤0.30 SIM s를 사용하고, 도달 후 한 로봇의 PF라도 누락되면 B를 `NOT_EVALUABLE`로 막는 것이다. 주 941만 동일 로봇 가중으로 판정하고 보조 943은 별도 표로 보고하며 모든 72건 안전 거부는 유지한다. 아직 채택한 기준이 아니다.

물리·SIM·렌더·모델 호출·봉인·등록·병합은 0회다. 기존 코호트의 진단이므로 새 TensorBoard 변환·서버·브라우저는 시작하지 않았다. Google Drive는 UGRP 예외에 따라 사용하지 않았다. 커밋·push·초안 PR 생성은 하지 않았다.
