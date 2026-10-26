# 종료 후 CPU 집계 코드 MiniMax 검토

실행 중 정책은 변경하지 않음. 원문 응답과 stderr/exit는 evidence에 보존.

## 판정: **CONDITIONAL_PASS** (사후 CPU 집계 코드는 등록 정의를 대체로 구현하나, D1–D3 해소 전 집계 실행 보류)

### 차단 결함 (등록 불일치, 집계 실행 전 해소)

- **D1 — READY 관측원 미검증 (A8·P-06).** `summarize_arm.py:180`은 `StudentFunnel.add` 4번째 인자에 정책 stage ready를 주지만, 같은 코드가 계산한 `simultaneous_policy_READY_ticks`(:175)와 funnel의 READY 결과를 교차검증하지 않는다. 원 r2 재집계는 `x['ready']`(프로토콜 ready)를 썼으므로(recount.py:84) "READY=정책 stage"가 단언되지 않는다. → funnel READY 도달 tick == 양 정책 stage가 동시에 ready인 첫 tick 대조를 요구.
- **D2 — 모순 레코드가 무결성 오류로 남지 않음 (A7·P-15).** `:244` `success = bool(physical and carry and carry.get('success'))`는 `carry_eval` 부재 시 원 `physical_success=True`를 조용히 실패(분모 포함)로 내리고 `world_errors`에 아무 기록을 남기지 않는다(:226·258). → `carry is None and physical is True`은 실패가 아니라 무결성 위반으로 기록 필요.
- **D3 — "총거부 0/G1 0" 주장이 이벤트·사유 문자열 가정에 의존 (G2 계측 유지·A9).** `:157–165`는 `event=='proposal_rejected'`, `reason=='close_before_learned_ready'` 문자열에 의존하고, `event` 키 결측은 `'UNKNOWN_NOT_RECORDED'` 집계만 된다(:159) — 오류로 승격되지 않는다. → 미인식 이벤트/사유를 무결성 오류로 처리해야 Arm C 총거부 0, 양 arm G1 0이 검증된다.

### 경미 불일치(보고·공시)

- 등록 산출물 `termination-crosscheck.json` 파일이 없음: `audit_cpu.termination()`은 값만 반환(117–121)하고 요약은 audit.json 에피소드 `termination`에 실림. 값(raw status·cap_end·sim_s·batch cap_end·finished_t·origin·finished_elapsed_s·physical_success·경로/SHA)은 모두 존재 → 판단에 부족하지 않으나 파일명 불일치 공시 필요.
- P-19: GO·ACK가 별도 열이 없고 `protocol_events`(:166·248) 안에만 존재. P-16의 "GT/정책-stage/protocol 관측원" 태그가 candidate/frame에 없음. S arm에도 CP가 계산되어(:305) 기술통계 라벨 없음.
- P-15 3분류가 라벨상 2분류로 축약(:118 `HOST_ERROR_or_uncompleted`).

### 실측 확인 범위(실행 시 1회)

1. 파일명/키: `treatment-first30-audit.json`·`pilot-gate.json`·`summary.worlds[].world/cap_end` 존재 여부 — 부재 시 :276 이후가 per-world try 밖이라 audit.json 없이 중단(산출물 부재). 2. 원 T `StudentFunnel.add`의 인자 순서·READY 관측원(03f6a231…). 3. Arm C carry_eval이 전체 truth 생성 여부(불일치 시 integrity 실패). 4. `read_physical_motion`의 0.1s 표본 간격·에피소드 커버리지(위반 시 UNMEASURED→파일럿 ② 실패).

### 검증 통과(정의·통계)

① `:244` 원 physical_success AND 원 carry_eval.success, 모델 done 미사용. ② approach/alignment/grasp/hold_3s는 원 `eval_passed`와 매 틱 대조(:186–187), hold=원 physics 플래그, GT 기하=원 truth. ③ 읽기 전용, 종료는 `termination(raw, batch cap_end)`로 180 SIM vs batch 60 혼동 차단(batch 불일치 별도 표기). ④ C 거부0·software_hold0·cadence(infer=discard=issue=ticks·stage 합=ticks·{'grasp':ticks}·state225=0)·입력 4계수 0·UNKNOWN/min_gap null 명시. ⑤ planned20/N_eff/결측·관리중단 분리. ⑥ followup=C 정상20·무결성·pilot PASS·speed PASS, 예산/디스크 별도(279–284 재계산 대조 포함). ⑦ McNemar `min(1,2^(1-k))` ✓, CP95% 손계산 0/20=[0,16.8434%], 1/20=[0.1265%,24.8733%] = 등록값 일치, S 확증 p 없음(r2 기준 0/20은 prior-funnel.json cohort success 0으로 뒷받침). ⑧ frame은 원 `funnel.first` 순차 누적, carry/door/place는 hold_3s 0이면 eligible 0 명시·그 외 미측정(None), candidate 8단계·event 원장·SHA 매니페스트·재현 명령, sampled 10Hz hold는 진단 전용(성공 판정 미사용).

## 반영

D1: 같은 틱 policy READY와 순차 alignment 이후 첫 READY를 각각 기록·대조. D2: physical_success=true인데 carry_eval 누락이면 무결성 오류. D3: 원 S/처리 코드에서 추출한 이벤트·거부 사유 목록 밖의 레코드와 로봇별 원장 누락을 무결성 오류 처리. termination-crosscheck.json 별도 출력, GO/ACK/START 열·관측원 태그·S 기술통계 라벨·미완료 분류를 추가. 원본 실행·물리 판정·동결본은 변경하지 않음. 보완판 서면 확인 수령: 구조적 차단0, 실측 확인 대기.


## 보완판 서면 확인 전문

## 판정: **CONDITIONAL_PASS** — 미해소 차단결함 **0건** (구조적), 실측 게이트 5건 대기

**원문 구조적 판정 (등록 대조)**
- **D1 해소**: 원시 동시 policy READY 첫 시각(`first_simultaneous_policy_t`), alignment 도달 후 첫 동시 policy READY(`..._after_alignment`), 실제 funnel READY 첫 시각(`funnel_first_READY_t`)을 299–302행에 모두 기록하고, 221행은 READY 관측원이 정책 stage임을 단언하며, 226–227행은 prefix 게이트된 첫 동시 READY와 funnel READY를 대조. alignment 이전 policy READY는 `expected_funnel_ready_t`에서 제외되어 퍼널 통과로 집계되지 않음.
- **D2 해소**: 292행 `physical_success_without_carry_evaluation`이 world_errors→`integrity_pass=False`(345행)로 승격, 무음 실패 강등 없음.
- **D3 해소**: 26–28행 이벤트·사유 allowlist, 39–40행 로봇별 원장 키 집합 강제, 49·54행 unknown/빈 사유 → 무결성 오류, 204행 protocol unknown → 오류.
- **경미 5항목 반영 확인**: `termination-crosscheck.json`(379행), GO/ACK/START 독립 열(303행), GT/정책-stage 관측원 태그(30–33·330·355행), S 기술통계 라벨(363행), P-15 3분류(153–155행). 등록판정·기준·실험은 변경되지 않음.

**잔여 등록 불일치 (경미·공시 대상)**
1. 285행 물리 이동 무결성 게이트를 전 20월드에 적용(등록은 파일럿 ② 첫 4완료 월드)→등록보다 과잉, 보고서 공시 필요.
2. 종료 대조 파일이 미완료 월드의 `sim_s`·`cap_end` 미포함(등록①~④ 일부만 audit.json 경유).
3. P-19 `state[250:252]` 중 252 변화 요약 누락; protocol 관측원은 태그 없이 열로만 존재.

**실측 확인 범위 (원본 VM CPU, 정상 GPU 종료 후만)**
- G1 T `03f6a231…` `StudentFunnel.add` 반환 `passed`/`first`의 prefix 게이트 여부 — `passed`가 prefix 게이트면 221행이 오탐→무효화 필수.
- G2 원장 위치·구조(`student_eval.barrier_events` dict/rid 키)·사유 필드명(`reason_category` 대조)·allowlist 출처(S/controller.py).
- G3 stage 토큰 `ready`·인자 순서·`summary.worlds[].world/cap_end`·`treatment-first30-audit.json`·`pilot-gate.json` 존재(332·333행은 try 밖이라 부재 시 산출물 부재).
- G4 `read_physical_motion` 0.1s 표본·커버리지; G5 McNemar `min(1,2^(1−k))`·CP 95% 재계산.

G1–G5 통과 시 PASS로 승격할 수 있으며, 새 실험·기준·확대 구현은 요구되지 않습니다.

## 보완판 경미 항목과 실측 전 원문 확인

- 전20 이동진단을 추가 무결성 관문으로 사용하던 행을 제거했습니다. 등록된 첫4 완료 C 파일럿의 이동 관문만 유지하고 나머지는 진단만 보고합니다.
- 미완료 종료 대조 파일에도 raw_sim_s/raw_cap_end를 추가했습니다. protocol 관측원은 original_READY_GO_ACK_boolean_protocol_log로 명시했습니다.
- state[250:252]는 Python 끝점 제외 슬라이스로250·251 두 값입니다. 원 S 계약의252차원에 index252는 없습니다. 두 값은 모두 기록되어 있어 추가 인덱스는 만들지 않습니다.
- T StudentFunnel.add 원문은 passed에 개별 raw 조건을 반환하고 self.first에만 순차 prefix를 적용합니다. READY 원시 조건과 prefix 통과를 분리한 대조는 그 원문과 일치합니다. 원문은 Oracle Git에서 읽었고 GPU VM CPU 분석은 하지 않았습니다.
