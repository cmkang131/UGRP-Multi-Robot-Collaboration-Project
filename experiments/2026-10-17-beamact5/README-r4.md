# beamact5 r4: 검색 순서 ablation + case27 수정

이 문서는 r3 gate FAIL(25/40, PR #588) 뒤의 **r4 후보** 기록이다. 별도 브랜치 `claude/beamact5-r4-t`(+ companion `-r4-a`, `-r4-r`)이며 r1/r2/r3와 pooling하지 않는다. ACT 학습·학생 기록 없음(교사 gate만).

## 1. r4 변경

- **검색 순서 revert (ablation 조건 A)**: `search26_circles`(down-first)를 끄고 r1의 up-first 원 순서로 되돌린다. r1 순서는 3번째 원이 최저 pitch `(500,2500)`인 기존 fallback을 포함한다. r3 gate에서 회귀 12개 world의 초기 search가 r1 대비 2.47–3.19배 길어진 것은 확인됐지만, 14/39 world가 초기 max ≥2배였고 그중 3개(30·32·38)는 성공했으므로 **down-first 인과는 가설(미확정)**이다. 이번 A/B 실행이 그 ablation이다.
- **case27 수정 (조건 B)**: retreat-first reobserve의 view 전환 검사가 `attempt==3`(retreat 단계)에서만 실행돼, 0.1 s 양자화 실행에서는 경계 tick(age 0.6 s)에 attempt가 이미 0이므로 **전환이 한 번도 발동하지 않았다.** gcp6 r3 gate case27의 reobserve가 `retreat_bounded_replan`(elapsed 0.6)로 끝난 것이 직접 증거다. 경계를 reobserve 시작 시각 기준으로 재고, 전환 시 view attempt 0(또는 전 target fresh면 fresh_measurements_replan)으로 넘어가게 고쳤다. 기본 off 동작은 불변. 0.1 s tick 전환 회귀 테스트 추가(11 passed).
- 상수(cap·margin·간격·창) 변경 없음. wide_stance 미적용.

## 2. 스택 (r4)

|트리|SHA|
|---|---|
|root|`729670fd4193f7225c3f03050b97cd85f674a49c`|
|adapter|`63c56bd99f3ef627c247eda1cb25593d2d0d85a3`|
|teacher|`82b46ed22e16f05fd4b47838b9a31cb8f1e56a35`|
|plan|`f1a50e8c833c1da9113bdf8cff3844913380e3c821b15c072c0a23c0f54f5148` (r1/r2/r3와 byte-identical)|
|cases r4a|`dc02bcec5b8159c04a76e75f6084ea64e9811db95e546c72dec047abae5058c0` (candidate 필드만 변경)|
|cases r4b|`65412505b12612a22437181e3613f5c7746925c1f0ef61293c6bd3e23de64b92`|

스택 점검: `teacher-gate-stack-check-r4a/r4b.json` — 각각 `ok=true`, admission pass. 사전 등록: [r4-preregistration.json](teacher/gate-40-r4/r4-preregistration.json) (실행 전 commit `63062328e`).

## 3. 후보 조건 (별도 실행, pooling 금지)

- **r4a (조건 A)**: down-first circles OFF(r1 up-first³ fallback) + search23_rects·static_peer·peer_memory 유지. reobserve OFF (27 수정 미포함) → 검색 revert 단독 효과 측정.
- **r4b (조건 B)**: r4a + `search26_reobserve`(전환 경계 수정 포함) → case27 수정 효과 측정.

## 4. 실행 계획·산술

1. 4-world(6,10,20,27)를 두 조건으로 각각 실행.
   - 6: peer-memory fix로 PASS 기대(검색 순서 무관).
   - 10·20: ablation signal — r2에서 down-first로 고쳤으므로 revert 시 회귀 가능. PASS면 conditional circles 불필요.
   - 27: 조건 B에서 reobserve가 retreat 경계를 넘어 view attempts로 이어지는지 확인.
2. 6·10·20·27이 모두 PASS하고 회귀가 없으면 **39-world gate**(world15 제외, r3 승인 deviation 유지) 실행.
3. 38/40 요건: 6·10·20·27 전부 PASS + 기존 통과 world 회귀 없음(15 expected FAIL, 37 구조적 FAIL). 27이 실패하면 37/40 FAIL, 회귀 1개면 37/40 FAIL — margin 없음.

## 5. 결과 (조건 A·B 진행, C 준비)

### 5.1 조건 A — r4a (r1 검색 revert + 6/10/20 유지, reobserve off)

실행 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r4a-4` (4 worlds 6·10·20·27, wall 1437.03 s, HOST_ERROR 0, success 2).

|case|결과|end|SIM s|비고|
|---|---|---|---|---|
|6|**PASS**|teacher_terminal|54.7|peer-memory/static-peer 유지|
|10|**FAIL**|cap_end|60.0|양 로봇 pick/episode_timeout — close-start low pitch가 3번째 원까지 지연|
|20|**PASS**|teacher_terminal|55.2|검색 순서 revert에도 유지|
|27|**FAIL**|teacher_terminal|26.4|approach_blocked_handoff/peer_approach_handoff (reobserve off, 설계상)|

→ **ablation 확인:** 순수 r1 revert는 6·20을 유지하지만 **10이 회귀**한다(close-start fallback이 3번째 원). → 조건 C(조건부 far-first circles) 채택.

### 5.2 조건 B — r4b (r4a + case27 reobserve 수정)

실행 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r4b-4` (wall 1688.18 s, 성공 2).

|case|결과|end|SIM s|비고|
|---|---|---|---|---|
|6|**PASS**|teacher_terminal|54.7|변동 없음|
|10|**FAIL**|cap_end|60.0|검색 revert 영향 (pick/pick)|
|20|**PASS**|teacher_terminal|55.2|변동 없음|
|27|**FAIL**|teacher_terminal|28.4|reobserve 전환은 **수정 확인**(14.9 s에 view attempt 0 → 15.2 fresh_measurements_replan)했으나 red_1 staleness 재발로 handoff. 25.4→28.4 s로 지연만 증가|

### 5.5 r5b·r5c·r6 — case27 집중 (각 별도 조건, pooling 없음)

|조건|변경|5-world 결과|27 기전/결과|
|---|---|---|---|
|r5b|r4c + obstacle refresh 최대 +2|6 PASS 59.1 / 10 PASS 49.0 / 20 PASS 42.1 / **27 FAIL 20.4** / 37 FAIL 29.7|refresh 4회 모두 fresh-ended(2.8·15.8·16.6·17.4 s)였으나 각 fresh 창이 ~0.1 m 이동 후 stale margin에 재차단, +2 한도 소진 후 3 s blocked handoff|
|r5c|r5b의 +2 한도를 제거(open refresh chain)|6 PASS 50.2 / 10 PASS 49.0 / 20 PASS 55.7 / **27 FAIL cap_end 60.0** / 37 FAIL 29.5|refresh 18회(15–59 s) 전부 fresh-ended, 그러나 선택이 매 tick feasible↔92/92 blocked로 진동하며 주행이 ~0.1 s/cycle에 그침. 로봇 root 위치가 18 s 이후 (0.239,-0.72) 고정 → 60 s cap|
|r6|r5c + `search26_commit_plan` (기존 1 s replan 경계까지 committed path 주행)|6 PASS 54.7 / 10 PASS 49.5 / 20 PASS 36.3 / **27 FAIL cap_end 60.0** / 37 FAIL 29.6|commit 가드가 현재 world의 waypoint/unusable 검사(낡은 margin)에 막혀 실제 주행 없음 — r5c와 동일 궤적(18회 refresh, approach 20.9+search 38.8 s)|
|r7|commit_plan 수정: 선택 시 plan·constraints를 **동결**하고 1 s 경계까지 동결 plan으로 주행(progress/peer/escape 블록보다 우선)|(실행 중)|가설: 1 s 창 실제 주행으로 0.36 m를 2–3 사이클에 이동|

- 공통: r4c의 6/10/20 PASS는 r5b·r5c에서도 유지(회귀 없음). 37은 r5b 29.7 / r5c 29.5 teacher_terminal(구조 라벨은 r1/r2 근거, r4/r5 재측정 아님).
- 사전등록: [r5b](teacher/gate-40-r5/r5b-preregistration.json)·[r5c](teacher/gate-40-r5/r5c-preregistration.json)·[r6](teacher/gate-40-r6/r6-preregistration.json). r5c gate prereg는 5-world 미통과로 **발동하지 않음**.

### 5.4 r5a (r4c + wide_stance) — **중단·무효**

`validation-r5a-5-stopped` — case27 FAIL 24.2 s(wide_stance로도 stale red_1 차단 미해소, jaw bound ~19.7°로 lateral 이득 작음), per-world wall/SIM ~13으로 r4c(~5.8)의 2.2배 → gate 후보로 부적합, SIGINT 후 원본 보존(집계 제외).

### 5.3 조건 C — r4c (far→close→mid circles + case27 수정)

실행 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r4c-4` (wall 1382.10 s, **성공 3/4, cap_end 0**).

|case|결과|end|SIM s|비고|
|---|---|---|---|---|
|6|**PASS**|teacher_terminal|54.7||
|10|**PASS**|teacher_terminal|49.5|down-first 45.6 s 대비 +3.9 s, close fallback 2원으로 회복|
|20|**PASS**|teacher_terminal|55.2||
|27|**FAIL**|teacher_terminal|25.4|case27 잔여 원인 → r5a(wide_stance)로 시도|

→ **far-first 조건부 circles가 검색 revert의 10 회귀를 해소**(ablation: r4a 10 FAIL → r4c 10 PASS). 파이프라인: [r4c-preregistration-amendment.json](teacher/gate-40-r4/r4c-preregistration-amendment.json), 스택 점검 ok true. 사전 등록: [r4c-preregistration-amendment.json](teacher/gate-40-r4/r4c-preregistration-amendment.json), 스택 점검 `teacher-gate-stack-check-r4c.json`(ok true). 통과 시 39-world gate(`gate39-r4c-run`, world15 제외).

## 6. 최종 상태 (r4–r9 자율 반복, 2026-10-18 01:25Z)

전체 조건 요약: [r4-r9-summary.json](teacher/r4-r9-summary.json). 모든 조건은 **별도 실행·pooling 없음**, 학습 RGB off·weld off·cap 60 SIM s, 단일 gcp6 L4.

|조건|핵심 변경|5-world 결과(6/10/20/27/37)|판정|
|---|---|---|---|
|r4a|검색 r1 revert(ablation A)|54.7P / **cap_end 60 F** / 55.2P / 26.4F|10 회귀 확인|
|r4b|+ reobserve 경계 수정|54.7P / cap_end F / 55.2P / 28.4F(전환 확인)|27 미해결|
|r4c|+ far→close→mid 조건부 circles|54.7P / **49.5P** / 55.2P / 25.4F|**검색 회귀 해소**|
|r5a|r4c + wide_stance 전면|27 FAIL 24.2, planning 2.2x|중단·무효|
|r5b|r4c + refresh +2|59.1P / 49.0P / 42.1P / 20.4F / 29.7F|27 미해결|
|r5c|r4c + open refresh|50.2P / 49.0P / 55.7P / cap60 F / 29.5F|27 진전 없음|
|r6/r7|r5c + commit plan(1차/동결)|6·10·20 P / 27 cap60 F / 37 F|27 미해결|
|r8|r4c + wide_rescue|P/P/P / **29.5F align** / 29.7F|**approach 돌파**, align 잔여|
|r9|r8 + open refresh + 동결 commit|49.3P / 49.5P / P / **28.0F align** / 30.5F|align 잔여|

**판정: 38/40 gate 기준 미달로 39-gate를 실행하지 않았다.** 6·10·20은 r4c 이후 모든 조건에서 PASS(회귀 없음), 27은 r8/r9에서 **stale-cargo approach는 wide rescue로 해결**됐고 잔여 실패는 **fine-alignment phase(`alignment_no_progress`, 28–30 s)**다. 37은 r8/r9에서 approach handoff(29.7–30.5 s)이며 구조 라벨은 r1/r2 근거다. 15는 r3 승인 로그 폭발 deviation으로 계속 제외.

**다음 라운드 제안**
1. world 27의 **align 단계 visible-error 정체** 수정(wide-rescue -18° stance 도착 후 band 기반 alignment error가 진행되지 않음) — 접근/검색이 아니라 정렬/관측 문제.
2. align을 bundle 내에서 고칠 수 없으면 **min_gap 0.0으로 승인된 3개 start(15/27/37)의 margin-aware 재승인** 여부를 별도 승인·사전등록 deviation으로 결정(기존 40 starts 변경, pooling 금지).
3. 39-gate는 27 통과 또는 start-set 승인 전까지 **실행 불가·결과 주장 없음**.
