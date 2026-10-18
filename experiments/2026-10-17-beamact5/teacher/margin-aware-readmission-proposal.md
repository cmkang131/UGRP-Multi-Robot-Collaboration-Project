# 제안서: margin-aware 재승인 (15·27·37 시작) — **사용자 결정 필요, 실행 금지**

작성 2026-10-18 01:55Z, beamact5 worker(DSH). Lead 지시("②번은 사용자 결정 사항 — 실행 금지, 14:45 핸드오프용 제안 문서만")에 따른 제안 문서다. 이 문서는 실행·승인 기록이 아니다.

## 1. 문제 (r1/r2 기록 근거)

- wide-start 40개 중 **3개 시작(world 15·27·37)**이 교사 admission(`warp_flow_admission.certify`)에서 `free_goal_N>0 & min_gap ≥ FRESH_MARGIN_M(5 mm)`만 만족해 **min_gap_m 0.0**으로 승인됐다(r2 6-world 검증 structural_finding).
- runtime 교사는 자세를 `FRESH_MARGIN_M + K·sigma`(바닥 margin **11.07 mm**)로 거부한다. 즉 시작 승인 기준과 runtime 거부 기준이 다르다.
- 결과: r1 gate 34/40(실패 6·10·15·20·27·37), r2 6-world에서 10·20 수정 확인, r3 39-gate 25/40, r4–r9 5-world에서 6·10·20 PASS 유지. **15(로그 폭발·r3 제외), 27(접근 해결 후 align 잔여), 37(구조적)**은 r1–r9에서 통과한 적이 없다.
- 38/40 요건상 15(제외)·37(구조적 expected FAIL) 외 추가 실패는 허용되지 않으므로 **27 중 하나가 반드시 통과**해야 한다. 현재 align 보정 라운드가 진행 중이다.

## 2. 변경 범위 (승인 시에만)

1. **admission 기준**: certify에서 `min_gap_m ≥ FRESH_MARGIN_M + K·sigma_floor`(= runtime 바닥 11.07 mm)를 요구하거나, **91-pose certified family 전체**를 runtime margin으로 평가해 승인. 기존 상수(5 mm, K=3.03, sigma floor 2 mm)는 유지하고 **비교식만 강화**한다.
2. **시작 집합 재생성**: 승인 기준을 만족하는 starts로 wide-start 40개를 **새 seed 집합으로 재생성**한다(기존 seed 8420000–8420039의 3개만 교체하지 않고, 동일 층화 규칙으로 40개 전체 재샘플링을 권장: 편향 방지).
3. **사전등록**: 새 stems/prereg/cases/plan sha를 새로 커밋하고, **새 gate id**(예: beamact5-teacher-gate-r-next-readmit)로 실행한다.

## 3. no-pooling·비교 규칙

- 재승인 gate 결과는 r1/r2/r3/r4–r9와 **절대 합산하지 않는다**(시작 집합이 다름). 기존 34/40, 25/40, r3 deviation 산술도 재사용하지 않는다.
- 재승인 gate도 **동일 최소 38/40**, 동일 cap 60 SIM s, 동일 장면/스택에서 새로 잰다.
- 기존 40 starts 원본·기록은 재생용으로 보존한다(삭제 금지). 재승인 전후 seed·layers·yaw 분포를 함께 보고한다.
- 재승인 기준으로도 15의 로그 폭발은 별도 수정 전 제외하거나, 로그 volume 수정 후 포함 여부를 다시 결정한다.

## 4. 영향·위험

- **긍정**: 27/37처럼 clearance가 바닥에 걸린 시작이 줄어 gate가 실제 제어 능력을 더 잘 반영할 수 있다.
- **부정**: 40-start 분포가 바뀌어 r1–r9와의 비교 가능성이 완전히 끊긴다. 새 gate를 처음부터 다시 재야 하며, 층화 샘플링 변경으로 다른 실패가 새로 생길 수 있다. 승인 기준 강화로 후보 수(admission 통과 starts)가 줄면 40개를 채우는 seed 재시도가 필요할 수 있다.
- **대안**: align 보정으로 27을 통과시키고 15는 로그 수정 후 재포함, 37은 구조적 expected FAIL로 유지하는 현재 경로가 비교 가능성을 보존한다.

## 5. 결정 요청 (사용자)

- (A) 재승인 승인: admission 기준 강화 + 40 starts 재생성 + 새 gate id/사전등록. (별도 승인 필요)
- (B) 재승인 보류: 현재 40 starts 유지, 27 align 보정 결과에 따라 gate 진행.
- (C) 부분: 15만 로그 수정 후 재포함(시작 집합 유지) — 27/37은 그대로.

**본 문서는 어느 안도 실행하지 않았고, 관련 실행·prereg·gate를 만들지 않았다.**
