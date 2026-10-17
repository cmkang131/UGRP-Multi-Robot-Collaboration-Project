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

실행 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r4b-4` — 결과는 이 절 갱신에서 채운다.

### 5.3 조건 C — r4c (far→close→mid circles + case27 수정)

실행 예정 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r4c-4` (4 worlds). 사전 등록: [r4c-preregistration-amendment.json](teacher/gate-40-r4/r4c-preregistration-amendment.json), 스택 점검 `teacher-gate-stack-check-r4c.json`(ok true). 통과 시 39-world gate(`gate39-r4c-run`, world15 제외).
