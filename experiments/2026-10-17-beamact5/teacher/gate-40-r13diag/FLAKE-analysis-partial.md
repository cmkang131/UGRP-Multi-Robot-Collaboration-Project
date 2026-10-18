# case27 flake 상류 분석 (부분, 2026-10-18 09:25Z **HOLD로 중단**)

Lead 지시(zone dialogue study 우선)에 따라 진단 실행 3회 중 1회만 완료하고 중단한 상태의 기록이다. **재개 시 이 문서부터 잇는다.**

## 확정된 사실 (저장 원본 비교)

|항목|관찰|
|---|---|
|초기 상태|6개 저장 실행(stage2 PASS / gate1·2 FAIL / repeat1·2 FAIL / repeat3 PASS) 모두 **첫 tick qpos 차이 0.0** — 동일 초기 상태|
|조기 발산|로봇 궤적은 첫 ~5 state(~0.5 SIM s) 안에 갈라짐 → **시뮬 자체가 bit-reproducible하지 않음**(flaky의 근원은 코드 분기가 아니라 물리/부동소수 민감도)|
|선택|모든 실행에서 첫 goal_set row t=2.8: candidates 525·blocked 465, 선택 (-18°, 0.209 m) cost 1.1709, wide_rescue(t=2.8) tested 455·feasible 6 — **선택 stance 동일**|
|추가 이벤트|align 중 추가 wide_rescue(t≈18.3)는 일부 FAIL 실행에서만 관찰|
|signature|PASS: align 2.6 s·relook 0 → `align→ready`(18.5). FAIL: align 7.8–8.4 s·relook 3, `no_visible_error_progress_3s` 3회|
|align 명령|FAIL도 align에서 회전→전진 40 ms pulse를 17.0–18.0 s 발행 후 hold; PASS도 같은 구간 동일 패턴 후 18.2–18.5 s ready|
|align 오차(r13diag rep1 FAIL)|15.9 s x=0.0698 → 17.6 s x=0.0188(정체), y≈0.0096, yaw≈0.008; x오차>inner(0.002)로 axis 0 active·drive 0.035–0.038 매 tick인데 이후 pose 정체 → 3 s 후 relook. **stagnation breakaway pulse가 이 구간에서 발행되지 않았음**(원인 미확정: teacher jsonl duration 확인 필요)|

## 중단 상태 원본 (보존)

- `diag-r13diag-rep1`: 완료 FAIL sim 25.5 (align 7.8 s, relook 3), align 진단 로그 327행.
- `diag-r13diag-rep2-stopped`: 진행 중 SIGINT 정지(부분 원본).
- `diag-r13diag-rep3`: 미시작.
- stack: teacher `fe6858ec` / adapter `230c9985` / root `d0fdeeb9` / cases `21cf43f9`; prereg `092185f34`.
- 모든 이전 원본(validation-r13-5, gate39-r13-run, gate39-r13-attempt2-run, diag-r13-27-repeat1..3)은 그대로 보존.

## 재개 시 다음 단계

1. r13diag rep1 teacher jsonl에서 17.6–21.0 s wheel duration을 확인해 stagnation breakaway가 왜 발행되지 않았는지 확정(코드 조건 vs 명령 로그 불일치).
2. FAIL에서 hold가 되는 시점의 `ready_geometry` 실패 사유(밝힘: align_ready_diag는 ready=True일 때만 기록되므로, 실패 사유를 추가 로깅해야 함 — pick-cloud collision/pose tol/plan invalid 구분).
3. 위 확정 후 안정화 구현(no new constants) → 5-world 3회 반복 → 안정 시 39-gate attempt3(동결 스택, attempt1/2/flake/attempt3 전부 공개).
