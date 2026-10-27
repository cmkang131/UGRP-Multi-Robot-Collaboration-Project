# HAN-32 strict 재채점 — report only

**teacher-level / HOLD_SCENE / not a gate / new cohort / do not pool**

| 별도 집단 | N | legacy 성공 | strict 결과 | 방법·불확실성 |
|---|---:|---:|---|---|
| 교사 ledger | 420 attempts (JSONL 전체 470행) | 238 | 확정 수 미확정, 하한 0·상한 238 | proxy 238; 문/운반 boolean이 없는 legacy 성공 238행 모두 모호 |
| 현재 scoped C | 20 | 0 | 0 | audit와 회수 raw physical/carry 실패에서 논리적으로 도출 |
| 현재 scoped S | 20 | 0 | 0 | audit와 회수 raw physical/carry 실패에서 논리적으로 도출 |

교사 proxy는 `success AND carried_max_m>=1.0 AND funnel_last=still_1s AND eval_failure=null AND drop_kinds=[]`다. **proxy 238을 strict 확정 성공으로 보고하지 않는다.** 수집기 `harness/pairact_collect.py:619–622`의 `funnel_last`는 참인 마지막 키만 저장한다. 따라서 중간 `door_passed`나 `carried_1m` 통과를 증명하지 않는다. 이번 작업은 ledger의 원본 경로 전체를 재회수하지 않았고, 모든 238행의 모호성·seed·원본 경로는 `teacher-ambiguous.jsonl`에 남겼다. golden 사례의 확인된 결합 조건을 ledger 전체에 확대하지 않았다.

C/S는 선호 경로의 `C-audit.json`, `S-audit.json`을 썼다. 로컬 회수 `results/pair-gpu-scoped-20261027/arm-{c,s}/world-*/raw/result.json.zst` 총 40개를 직접 읽고 해시했다. 각 physical_success와 carry_success는 false이며, 해당 carry-eval 파일/embedded report는 없다. 그러므로 strict는 legacy의 부분집합이라는 논리로 0이며, raw carry-eval/궤적을 통한 strict 재계산 40회라는 주장은 하지 않는다. 이전 baseline-resume archive의 C/S를 현재 scoped C/S 대신 사용하지 않았다.

C funnel은 20→정렬0→READY0, S는 20→정렬1→READY0이다. C cap_end14·조기종료6, S cap_end15·조기종료5를 별도로 유지한다. 각 world/seed·funnel·결과 파일은 JSON 보고서에 있다. 원장 실패 분포도 JSON에 포함했다. 막힌 물체·최소 틈을 새로 추정하지 않는다.

원본은 읽기 전용으로 취급했고, sealed result·prereg v3·기존 요약은 다시 쓰지 않았다. 로컬 새 분석은 0 GPU, VM 조작 0, 새 물리 실행 0이다. PR 자동 CI의 CPU demo 실행·취소 예외는 `CI-CANCELLATION.md`에 기록했다. 동일 입력의 재현 명령과 해시는 README와 artifact index에 있다.
