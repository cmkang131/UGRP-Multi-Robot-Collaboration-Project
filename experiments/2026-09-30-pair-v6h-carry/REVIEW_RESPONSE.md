# #294 검토 응답 — 분류기·초안 수정 완료 (2026-09-30)

기준 소스 `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`, 작업 브랜치 `codex/v6h-classifier-fixes`, PR 기준 `claude/b-v6h-gain`. 조정자가 이전 집계 불일치 중단 해제를 승인했고 null 실패 항목을 바로잡아 재개했다. 이전 중단 기록은 `analysis/review_fix_interrupted_20260930/PREVIOUS_RESPONSE.md`와 미완성 patch/반례/시험에 그대로 보존한다.

**검증: 16개 완료 코호트 308건의 모든 공개 통과 집계가 일치한다.** cA·cB 각각 24/24, 부분 tX1도 완료 12건 + HOST_ERROR 2건이다. 공개 숫자·배치 파일·raw·제어기·기존 수치 산출물을 바꾸지 않았다. 새 전체 결과/파일 해시는 `analysis/review_validation_20260930/`에 보존했다. 전체 raw는 기본 체크아웃 outputs의 로컬 보관이며 원격 백업이라고 표현하지 않는다.

| #294 항목 | 재현 및 수정 | 검증과 범위 |
|---|---|---|
| 1 잘린 기록·집게 누락 | 엄격한 trace 순서·전체 창·≤0.051 s 간격, 도달 leg의 유한/범위 수치, r1/r2×2 bool 집게를 확인. 확증은 기록 행 수·종료 시각·전체 접촉 추적 범위 필수 | 한 행/앞·뒤 절단/중간 누락/역순/중복/빈 집게/inf 회귀 검사. 빠진 증거는 오류/NOT_EVALUABLE이며 PASS 아님 |
| 2 봉인 60+12 목록·해시 | 독립 고정 hash의 sealed manifest와 C01…C60×941+C01…C12×943, 배치/prior/계획/소스/정책/번들 및 실제 source file inventory를 대조 | 누락 보조 시드·다른 배치/prior/policy/bundle/source·case byte hash·추가/중복 계획 거부. HOST_ERROR 재시도는 봉인에서 최대 1회 미리 허용, 원본/대체 연결 및 단일 선택. 탐색 60곳은 확증 PASS 불가 |
| 3 미해결 실패·L0/L1 창 | **null 값은 실패 없음**. 실제 실패·가드·timeout은 좋은 끝점과 접촉이 있어도 PASS 거부. 확증은 L0 handover 바닥≤5 mm·tilt≤3°·네 집게 개방, L1 시작 전≤.051 s lift≥3 cm·네 집게 접촉, restaging=false. L1 첫 wait_lower 종료와 목적지 setdown 구분 | null 정상 사례와 실패 혼합 반례, handover 실패·잘못된 종료·실제 timeout·목적지 미실행 시험. 기존 PASS_CONTACT_RECOVERED는 **접촉 동반 끝점 통과**이며 실제 복구/접촉 종료 주장 아님. PREREG §4–5.1 동기화 |
| 5 σ 표본·시각·누락·가중 | 941 주 분석은 도달 배치마다 두 로봇 동일 가중, 943 별도. 최신 causal 초기화 PF의 trace/posterior 나이≤.30 s, 같은 행 GT, yaw wrap, 유한 대칭 양의 정부호 covariance. 도달 후 한 로봇 누락도 B NOT_EVALUABLE; 미도달 별도 | 오래된/미래/누락 PF·잘못된 covariance·시간 경계·yaw wrap·주/보조 가중·6개 leg×축 AND·완전한 A/B 성공·missing B 차단 시험. 로봇 표본 포함률과 두 로봇 모두 포함 배치 비율 구별 |
| 6 비독립 추출·모집단 주장 | 이전 확증 추첨도 근접 거부하는 현재 배치 설계는 **비독립**. Wilson/정확 이항은 명목 구간·설계 민감도, p=.88은 검증되지 않은 설계 가정. 모집단 주장은 새 독립 추출/목표 분포 또는 의존 설계에 맞는 추론 필요 | 기록 case hash 재확인: 29 구성=26개 좌표/20개 근접 연결 묶음. 20을 유효 n으로 대체하지 않음. 순차 거부 동작 시험, `probe_dependence.json`. 기존 60곳 바이트 그대로 |
| 9 Monte Carlo 경계값 | 성공/실패 draw·정확 양측 95% 모형 내부 구간·실패 확률 단측 95% 상한 추가. 새 sizing_review_20260930 출력, 기존 출력 보존 | 3000/3000과 0/3000 경계 및 5/10 구간 시험. ON ≥48 성공/실패 3000/0, gate 확률 [0.998771,1], 실패 상한 .000998. 실제 안전·전이 위험 상한 아님 |

## 실행한 검증

- 기존 venv 재사용, `PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, pytest cache 비활성. `run_ci_tests.run_locked`로 공용 잠금을 획득·정리한 **오프라인 산술/합성 기록 시험**만 수행.
- `test_v6h_classify_placements`, `test_ci_sharding`, `test_chain_analysis_hard_limit`, `test_pair_chain_probe`, `test_b_v6h_gain`: **201 passed** (`analysis/review_validation_20260930/tests.txt`). 전체 로컬 CI나 물리 실행이 아니다.
- 작업 시작 HEAD의 구 분류기를 메모리에 넣고 같은 새 회귀 시험을 대조: **17 failed, 67 deselected** (`old_code_tests.txt`). 잘린 기록/빈 집게/비유한 leg/null 이후 실제 실패/실제 timeout/봉인 없는 확증 통과의 반례다. 구 코드를 실행 소스에 덮어쓰지 않았다.
- `analysis/revalidate_published.py`: 16코호트 **308건**의 `[건수,연쇄 통과,strict 배치 통과,배치 수,L0 통과,L1 통과]` 전부 공개 값과 같고, tX1 `[14,12,2,7,6]`도 일치. 각 cases.jsonl의 원 공개 SHA-256과 일치. result/trace/manifest/source hash도 기록.
- `analysis/cohort_sizing.py --check`: 새 출력 바이트 재현, 기존 예측/적합/정확 꼬리/최소 N 검증 통과. `make_confirmatory_placements.py --check`: 기존 60곳 바이트 재현. `check_probe_dependence.py`: 원본 29개 case hash와 좌표 재확인. `git diff --check` 통과.

## 남은 실행 경계

실제 봉인 파일을 만들거나 기존 실행 승인/등록 파일을 변경하지 않았다. 확증 입력 계약은 `analysis/SEALED_INPUT.md`다. **기존 러너에는 전체 trace/contact coverage 및 새 실행 identity 입력 계약이 모두 구현돼 있지 않다.** 후속 실행 기록 어댑터와 독립 검토가 필요하며 기존 raw는 확증 성공으로 승격하지 않는다. 이 PR은 분류기와 초안의 오프라인 수정이고 실제 새 봉인 호환 실행·접촉 추적 양성 대조·확증·E2E·실물 성공이 아니다. #293의 별도 D1 검토 항목 4/7/8은 이 작업 범위가 아니다.

원래 물리 결과의 TensorBoard 키 `b_v6h_gain_20260930`, `door_relax_envelope_20260930`, `b_v6h_axial_lag_20260930`은 보존한다. 기존 raw 재분류와 수치 보고 보완이므로 새 변환·서버·브라우저 재검증은 수행하지 않았다. 물리/SIM/렌더·외부 모델 호출·봉인·등록·병합 **0회**. UGRP 예외에 따라 Drive 작업 없음. 커밋·push·초안 PR은 이 수정의 전달 단계이며 병합하지 않는다.

## 참고 자료

- [독립 검토 원문](https://github.com/kcm0127-dotcom/ugrp/blob/codex/review-293-294/experiments/2026-09-30-pair-v6h-carry/REVIEW_294_293_astra.md), 기준 #294 `76e0f9ce`.
- [기존 공개 집계](analysis/VALIDATION.md) 및 [최초 대조 입력](analysis/validation_20260930/published_count_checks.json).
- [입력 계약](analysis/SEALED_INPUT.md), [초안](PREREG_DRAFT.md), [새 검증 기록](analysis/review_validation_20260930/), [모의 추출 구간](analysis/sizing_review_20260930/COHORT_SIZING.md).
