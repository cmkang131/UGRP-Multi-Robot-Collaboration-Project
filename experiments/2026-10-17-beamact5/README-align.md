# beamact5 align 단계 보정 (r10diag–r13) — 2026-10-18

Lead 지시("align 단계 보정을 즉시 실행")에 따른 라운드. 모든 조건은 별도 실행·pooling 없음, 학습 RGB off·weld off·cap 60 SIM s, gcp6 isolated. 요약: [r10-r13-align-summary.json](teacher/r10-r13-align-summary.json).

## 1. 원인 확정 (r10diag / r10diag2, 진단 전용·동작 불변)

- case 27이 align phase에 도달(~19.9 s)하고 visible probes 15, 오차 x=0.0135 m·y=0.0085 m·yaw=-0.0037 rad에서 정체.
- 교사는 매 tick x축 drive 0.021–0.030을 발행했지만 reported pose가 전혀 변하지 않았고, wheel pulse는 **후보 40 ms floor**(0.35 board speed)였다.
- 같은 교사가 approach phase에서는 pulse가 **full 0.1 s control period**까지 커져 정상 주행.
- 결론: **align phase의 40 ms pulse가 static friction을 깨지 못해 로봇이 물리적으로 움직이지 않음** → merit 정체 → 3 s 후 relook ×3 → `alignment_no_progress`.

## 2. 수정 라운드 (각각 별도 조건)

|조건|변경|case27 단독|5-world(6/10/20/27/37)|
|---|---|---|---|
|r11|align에서 매 tick full-period pulse|PASS 29.9 (align 2.6 s)|6/10/20 PASS, **27 FAIL 23.4** (alternating_error_sign_4)·37 FAIL|
|r11b|pose 무변화 시에만 full-period|—|6/10/20 PASS, **27 FAIL 20.0** (pose=command odometry라 트리거 무효)·37 FAIL|
|r12|r11b + open refresh + frozen commit|—|6/10/20 PASS, **27 FAIL 26.8** (align 9.1 s, no_visible_error_progress)·37 FAIL|
|**r13**|**동일 축 visible error가 3 tick 연속 1e-4 m 이내 불변일 때만 full-period pulse**|**PASS 24.0** (align 2.6 s)|**6 PASS 54.7 · 10 PASS 49.5 · 20 PASS 36.3 · 27 PASS 24.0(align 2.6 s·relook 0) · 37 FAIL 30.6**|

r13 stack: teacher `fe6858ec`, adapter `d354468a`, root `05046e9d`, cases `3d4e065d`, 사전등록 r13 `fba83f58`, gate prereg `fba83f58`(실행 전 커밋). 새 시간상수 없음(기존 control period·inner deadband 재사용), 기본 off, mode-gated.

## 3. 39-gate attempt 1 — **37/40 FAIL**

- 실행 `gate39-r13-run`, 실행 전 사전등록 `fba83f58`, stack/funnel: [funnel-attempt1.json](runs/gate39-r13-run/funnel-attempt1.json).
- executed 39, success **37**, cap_end 0, HOST_ERROR 0, wall 2620 s (43.7 min), summary sha256 `470c2b91…`.
- 실패 2: **world 27 `alignment_no_progress` sim 26.0 s** + world 37 approach handoff 29.5 s(구조 라벨·expected FAIL).
- 15는 r3 승인 deviation으로 제외·expected FAIL. 즉 **38/40 미달**.

## 4. 27 flake 정량화 (진단, gate 주장 없음)

|반복|결과|signature|
|---|---|---|
|repeat1|FAIL sim 25.5|align 7.8 s·relook 3 (`alignment_no_progress`)|
|repeat2|FAIL sim 25.5|repeat1과 **동일 signature**|
|repeat3|PASS sim 24.0|r13 stage2 pass와 **동일 signature**(align 2.6 s·relook 0)|

- **27 통과율: 단독 반복 1/3, batch 1/2.** 실패는 후반 align stall, 성공은 조기 align 통과로 두 갈래가 뚜렷 → flake는 align 법칙 이전(wide rescue 선택/approach 궤적)에서 갈린다. align breakaway는 결정적 정체는 고쳤지만 27을 안정화하지 못했다.

## 5. attempt 2 — 동결 스택 반복(Transparency)

- 사전등록 `ba5c97397`(launch 전 커밋): attempt1 실패를 본 뒤의 **repetition**이며 best-of/선택 아님, attempt1·2 **모두 공개**, attempt2만 통과해도 **"2회 반복 중 1회 통과(불안정)"**으로만 보고하고 단독 38/40 주장 금지.
- stack/cases/plan/criterion attempt1과 완전 동결(변경 0). 실행 `gate39-r13-attempt2-run`.
- 결과: 아래 "attempt 2 결과" 참조.

## 6. 남은 결론

- align 수정으로 27은 **처음으로 batch 5-world를 통과**(사전조건 충족)했고 gate에서도 1회 통과 가능성은 있으나 **불안정**하다.
- 안정화하려면 flake의 상류 원인(wide-rescue 선택/approach 궤적)을 다뤄야 하며, 이는 남은 시간의 별도 라운드 대상이다.
- 15·37 라벨/제외는 그대로: 15 r3 deviation 유지, 37 구조 라벨(r1/r2 근거, 재측정 아님).

## attempt 2 결과

(실행 완료 후 기록)
