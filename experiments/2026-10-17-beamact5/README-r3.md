# beamact5 r3: 남은 원인(6·15·27·37) 수정과 6-world 검증

이 문서는 PR #585(claude/beamact5, r2 34/40 FAIL 기록)와 분리된 **새 후보 코드 PR**의 기록이다. 브랜치 `claude/beamact5-r2-t`(r2 base `85b99214` + r3 커밋)이며, companion 고정 트리는 adapter `claude/beamact5-r2-a`, root `claude/beamact5-r2-r`이다. stacked PR: base는 `main`, 선행 후보 커밋은 r1/r2 동결 트리 체인 위에 있다.

## 0. 범위

- ACT 학습·학생 카메라 기록·학생 평가는 하지 않는다. 교사 gate/검증만.
- r1/r2 결과와 합산하지 않는다. MJWarp 결과를 C 결과와 합산하지 않는다.
- 새 거리·각도·시간·간격·margin 상수는 없다. 새 모드는 모두 **기본 off**이고 profile에 항상 기록된다.
- wide_start 40 starts(seed 8420000–8420039)는 r1과 동일한 동결 plan이다(cases는 candidate 필드만 다름).

## 1. 스택 (r3 6-world 실행, gcp6)

|항목|SHA/값|
|---|---|
|root (WARP_SOURCE_ROOT)|`73ff19fa905d7c94af94316c469efd23e6d70368`|
|adapter|`ed5e162478f2fa689a56006cd36661dcfef6194b`|
|teacher|`f919ca72a43c3f8c3b3b6b9b4f7d260e241fdfe3`|
|cases|`ccdbe6bd6630ba021a8ac393d39ca20939f2ee30187fd6117b92126d35484b96` (r2 cases `24903b69…`와 candidate 필드만 다름)|
|plan|`f1a50e8c833c1da9113bdf8cff3844913380e3c821b15c072c0a23c0f54f5148` (r1/r2와 byte-identical)|
|rejection ledger 입력|`16fe662ac3f054106217a116697b9f396f2fcfc0d34215924970e8159f6c7d3f` (gate-40-r2 표 복사)|
|physics/contact|`mjwarp_batch_v1` + `warp_native_contact_v1` (noslip 0)|
|scene|cargo v6, scenario v7, `walls_floor_contrast_v5_indigo110_s80`, canonical XML 재컴파일|
|기타|training RGB off, weld off, held_object_hidden on, top camera control off, gcp6 isolated, placement filter, cap 60 SIM s|

스택 점검: `teacher-gate-stack-check.json` — `ok=true`, `current_compliant=true`, admission `pass` (25 rows). 사전 등록: `validation-r3-preregistration.json` — **실행 전**에 6 world·예상·금지 범위를 고정했다.

## 2. r3 변경(모두 기본 off)

- `search26_peer_memory` (teacher): static-peer witness를 visible-history 기억(`world['robots']`, 기존 `PEER_TTL_S`)이 살아있는 동안 유지. r2 world 6에서 6 s 창이 가시성 flicker마다 재시작해 goal set이 56.1 SIM s에야 열린 것이 근거.
- `search26_reobserve` (teacher): retreat-first reobserve가 0.6 s 경계에서 끝나지 않고 기존 3회 bounded view attempt로 이어진다(r2 world 27의 `retreat_bounded_replan` 근거).
- `search26_reobserve` (adapter ordering): wall layer 활성화가 방금 시작한 비-벽 대상 reobserve를 elapsed 0.0에서 죽이던 순서를, 이 모드가 켜진 실행에서만 유지하도록 고친다(r2 world 27 `wall_layer_hit_miss_replan`).
- `search26_wide_stance` (teacher, **이 후보에서는 켜지 않음**): 5°→1° 각도 격자의 새 certified family. world 37의 ±15° best 4.87 mm < runtime floor 11.07 mm, jaw bound 17.88°가 근거. 5° family와 pooling 금지.
- runner 배선: `scripts/run_grasp_act_teacher.py:run()` 인자·report·search15 dict에 세 키 추가 + signature 회귀 테스트.

## 3. 실행 실패/중단 4건 (집계 제외, 원본 보존)

1. `validation-r3-6-wiring-error` — adapter가 `run(**profiles(candidate))`로 부르는데 teacher runner에 r3 키 배선이 없어 `TypeError` (started_N=0, HOST_ERROR=1).
2. `validation-r3-6b-cwd-error` — 실행 명령이 `WARP_SOURCE_ROOT`로 cd하지 않아 canonical scene의 상대 texture 경로가 안 잡힘(`ValueError: zone_wall_divider_1_...png`). started_N=0, HOST_ERROR=1.
3. `validation-r3-6c-reobserve-indexerror` — **world 6개가 시작된 뒤** SIM 약 6 s에서 `grasp_act_reobserve.py:156 IndexError: list index out of range`로 전체가 죽었다. retreat-first reobserve가 0.6 s 경계가 아닌 6 cm 이동으로 view 단계로 전환될 때, 모든 target이 이미 fresh(peer clear dwell 진행 중)면 필터 결과가 비어 `targets[-1]`을 인덱스하는 결함. 전환 시 `fresh_measurements_replan`으로 종료하도록 고쳤고, 수정 전 코드에서 같은 IndexError로 실패하는 회귀 테스트를 넣었다. started_N=6, completed_N=0, HOST_ERROR=1, world 결과 없음.
4. `validation-r3-6d-stall` — **world15가 batch를 막아 중단.** 16:44Z 시작, 139 ticks/13.9 SIM s에서 3분+ 정지(진행 정지, CPU 100%), world-002 raw가 diagnostic-snapshot.json **3,001,561,296 B** + 인터럽트 flush result.json **3,199,783,993 B**로 성장(다른 world 약 5 MB), batch 14.2 wall/SIM(r2 같은 subset 5.87, 차단 기준 6.0). 17:07:04Z Mac에서 `kill -INT 5226`; KeyboardInterrupt handler가 result.json을 쓰고 `compress_logs`가 17:10Z까지 끝났다. 원본 `runs/beamact5/validation-r3-6d-stall`, stall-record.json·SHA는 [gate-40-r3/validation-r3-preregistration.json] 및 이 문서 4.3절. **물리 결과 없음·집계 제외·r3에서 world15 제어 거동 미검증.**

1·2는 world 시작 전, 3·4는 world 시작 후 코드/로그 결함으로 끝났고 모두 summary/로그를 VM 디스크에 보존했다. 상세는 preregistration의 `prelaunch_attempts`.

### 3.1 known defect: world15 로그 폭발 (후속 과제)

world15는 교사가 0.1 s마다 91-pose `blocked_goal` goal_set/search22 감사 결과를 다시 계산·기록해 payload가 world당 수 GB로 커진다. runner가 그 payload를 여러 번 직렬화하면서 batch 전체가 stall한다(r2에서는 SIM 6.4 s의 30 wall-s planning safety cap이 먼저 걸렸지만, r3 경로에서는 cap이 발동하지 않았다). 이번 gate에서는 로깅 수정을 하지 않았고(승인 조건), **world15는 향후 교사 녹화/데이터셋에서도 제외**하며, 로그 volume 수정(중복 제거·증분 기록) 전에는 사용하지 않는다. 수정은 별도 후속 과제다.


## 4. world 15 원인표 (r2 raw + cProfile)

### 4.1 r2 비프로파일 원본 (validation-r2-6/world-002)

|관측|값|
|---|---|
|end_reason|`planning_wall_safety_cap` (SIM 6.4 s; `planning host safety cap; 30 wall seconds per tick`)|
|world wall|**324.75 s** (SIM 6.4 s → 50.7 wall/SIM)|
|planner_calls|46 (r1)|
|search20_log|44 rows, **body-planning `search20_compute` 0 rows** — cap 전에 body planning이 없었다|
|반복 이벤트|`retained_proposal_blocked` + `reasons.blocked_goal=91`가 0.1 s tick마다 2회씩 기록 (91 = 5° 격자 sampled certified family 전체)|
|로그 크기|`search22_log` 47 rows = **281.5 MB chars**, `goal_set_log` 46 rows = **274.9 MB chars** (result JSON 전체 약 1 GB의 대부분)|
|해석|goal-set/search22 memory audit가 매 tick 전체 91 pose에 대해 재계산·기록되고, 보이는 기억(grid cell)이 늘수록 tick 비용이 커져 어느 tick이 30 wall s를 넘겨 행정 상한이 걸렸다. body planning(search19/20)은 이 시간에 실행되지 않았다.|

### 4.2 cProfile (r2 후보, world 15, `profile15.prof` sha256 `94d426ac…`, 16:05–16:27Z)

- 총 profiled 1312.5 s, 함수호출 4.08e9.
- `write_json`(harness/grasp_act_data) **992.6 s = 75.6%** (24 calls) — 사후 대형 artifact 직렬화(raw/result 52 MB zst, diagnostic-snapshot 49 MB zst, adapter result 52 MB zst). 이 실행은 SIM 6.9 s에서 cap으로 끊겨 **사후 저장이 프로파일의 대부분**을 차지한다. 따라서 이 75.6%를 일반 60 SIM s 실행의 비중으로 전용하지 않는다.
- in-run 상위(profiled): teacher.step 176.2 s/129 ticks, peer_rendezvous `_step` 141.0 s/126, `plan_active` 109.1 s/95, `body_fallback` 93.0 s/44(search19→21→23 fallback 체인), `select_sampled_goal` 55.2 s/53, `ghost_visible_region` 46.3 s/68, search23 `__init__` 71.5 s/363, `measure` 30.0 s/9706(`rectangle_gaps_many` 22.6 s, `_wall_name` 20.1 s/151658), `candidate_audit` 13.2 s/4009, warp step 63.5 s/69(`capture_launch` 57.6 s).
- 가설(certified-family fallback) 판정: **부분 지지**. 상위 계획 경로가 certified family/sampled goal 계열(`body_fallback`·`select_sampled_goal`·`plan_active`)인 것은 확인했지만, 이 프로파일은 6.9 SIM s에서 끝나 그 비중을 60 s 실행으로 전용할 수 없고, 30 s를 넘긴 단일 tick의 실시간 스택은 프로파일에 남지 않았다(도구 한계). r2 raw의 반복 91-pose blocked loop와 body planning 0 rows가 직접 증거다.
- 결론: world 15는 **cap/margin 상수를 올릴 대상이 아니고**, 반복되는 91-pose goal-set/memory audit 경로를 batch/cache하는 후속 수정 대상이다. 이번 r3 후보에는 그 수정을 넣지 않았고(원인표만 확정), gate 산술은 15를 expected fail로 둔다.

### 4.3 r3에서 추가 확인된 비용 (validation-r3-6d-stall, 16:44–17:10Z)

|관측|값|
|---|---|
|배치 진행|139 ticks / **13.9 SIM s**에서 정지(3분+ 진행 없음, 프로세스 CPU 100%)|
|bottleneck|world-002(world15) raw 총 **316 MB zst** (raw JSON 3.2 GB + snapshot 3.0 GB), 다른 world raw 약 5 MB|
|batch 속도|**14.2 wall/SIM** (r2 같은 6-world subset 5.87; AGENTS 차단 기준 6.0 초과)|
|safety cap|r3 경로에서 **30 wall-s planning safety cap 미발동** — r2 world15는 SIM 6.4에서 cap으로 끝났으나 r3에서는 로그·직렬화 비용으로 batch가 계속 느려짐|
|SHA|diagnostic-snapshot.json.zst `ebd037e3…`, result.json.zst `d29b3174…`, summary.json `f120c1ce…` (stall-record.json에 전체 기록)|

해석: 세계별 교사 로그가 과도하게 커지는 것이 1차 원인이고, runner가 그 payload를 반복 직렬화하는 것이 2차 원인이다. cProfile의 `write_json` 75.6%는 이 경로의 사후/중간 직렬화 비용과 일치한다. 코드 수정 없이 gate를 돌리기 위해 world15만 물리 실행에서 제외했다(7절).


## 5. world 37 (구조적, 수정 제외)

sampled ±15° family best gap 4.87 mm < runtime floor margin 11.07 mm. `search26_wide_stance`는 이 구조를 겨냥한 별도 family지만 이 후보에서 켜지 않는다(단독 비교 실행 필요, r3와 pooling 금지).

## 6. 테스트

- `tests/test_beamact5_r3_modes.py` 10 tests: 등록·기본 off, validate fail-closed, peer memory 유지/만료, 기본 reset, retreat 경계→view attempt, 기본 경계 종료 불변, wide family 상위집합/각도, teacher runner 인자 배선, reobserve 전환 시 빈 target 가드(수정 전 IndexError 재현).
- 기존 회귀: `tests/test_grasp_act_search15/21/22/23/24/25.py`, `tests/test_beamact5_r2_modes.py` 포함 **71 passed** (Mac, 물리/렌더 없음).

## 7. 결과 — 6-world 중단(stall), full gate는 world15 제외 39-world로 실행

- **6-world(`validation-r3-6d`)**: world15 stall로 중단(3절 4항). 원본 보존·집계 제외. 다른 world(6/10/20/27/37)의 r3 거동은 이 실행으로 판정할 수 없다.
- **gate deviation (조정자 A안 승인, 2026-10-18 KST)**: full gate를 **world15 물리 실행만 제외한 39-world**로 실행한다. world15는 **사전등록 expected FAIL**로 분모에 남긴다(nominal 38/40). 실행된 39 world 중 **최소 38 성공**(비-15 실패 최대 1)이면 pass. world37은 이미 알려진 구조적 expected fail(4.87 mm < floor 11.07 mm)이라, 37도 실패하면 38/40 = 정확히 최소 기준이다. 코드·cap·margin 변경 없음. 사전등록: [gate-40-r3/gate39-deviation-preregistration.json].
- 실행: `runs/beamact5/gate39-r3-run`(39 worlds, indices 0–14·16–39, cap 60 SIM s, training RGB off, weld off, gcp6 isolated), 로그 `…/gate39-r3-run.log`.

### 7.1 결과: **25/40 nominal — FAIL** (최소 38)

|항목|값|
|---|---|
|실행/완료|39/39 (`HOST_ERROR=0`), world15는 제외·expected FAIL|
|성공|**25** (nominal 25/40)|
|cap_end|**12**|
|wall|3,209.94 s (loop 2,946.24 s, 606 ticks, SIM 60.6)|
|first30 speed|per-world **1.231 wall/SIM**, speed_gate_fail false (block 6.0)|
|원본|`runs/beamact5/gate39-r3-run`(874 MB), summary sha `02a1260f…`, first30 `12e219d4…`, rejection_table `9072dfc4…`, artifact-sha256 `d837f875…`, progress `a0ea331c…`; 결과 기록 [gate39-result.json], 원시 재계수 [raw-fetch/gate39-recount.json](raw-fetch/gate39-recount.json)(branch 보존 사본 sha `aa773a42…`; Mac /tmp 사본은 없음). run dir i ↔ case index는 0–14,16–39 순서.|

- 실패 14: **cap_end 12** (case 2·4·8·12·14·18·22·24·28·29·34·39, 모두 sim 60.0) + case **27**(teacher_terminal 22.2 s, peer handoff 그대로) + case **37**(r3 raw: `teacher_terminal` **57.3 s**; r3 raw에 4.87 mm/11.07 mm 측정값은 없다. "구조적 4.87 mm < floor 11.07 mm"는 **r1/r2 근거 라벨이며 r3 재측정이 아니다**).
- 확인된 수정: **case 6 PASS(59.2 s)·10 PASS(45.8 s)·20 PASS(44.4 s)**.
- **회귀: r1에서 통과했던 12개가 전부 cap_end.** phase 비교에서 회귀 world들은 한 로봇의 초기 search가 r1보다 2–3배 길다(case2 r2 47.8 vs 20.4 s, case4 r2 48.9 vs 21.4, case14 r2 47.4 vs 19.9, case24 r2 44.5 vs 17.1, case29 r1 48.8 vs 21.3, case39 r1 45.7 vs 18.3). 상대 로봇은 ready에서 대기 후 60 SIM cap.
- **원인 후보(가설, 미확정):** 회귀 12개에서 한 로봇의 초기 search가 r1 대비 **2.47–3.19배** 길어진 것은 확인됐다. 다만 실행 39개 중 **14개 world가 초기 max search ≥2배**였고 그중 **3개(case 30·32·38)는 성공**했다(case32는 41.0 s search로 성공). 따라서 "`search26_circles`(down-first) 전면 적용이 회귀 원인"은 **가설이며 단정하지 않는다.** per-mode ablation(검색만 revert vs 유지)은 미실행으로 **인과 미확정**이다. peer_memory/reobserve의 기여도 미측정.
- 판정: r3 후보 **gate FAIL**.

### 7.2 r4 산술 (다음 후보 계획, 실행 전 기록)

r3 결과(r1 34 + r3 수정 3개 - r3 회귀 12)로 25다. **r4가 38/40을 넘으려면 37(구조적)과 15(제외·expected FAIL) 외에 실패가 없어야 하고, 따라서 27도 함께 고쳐야 한다.**

|시나리오|성공/40|판정|
|---|---|---|
|r1 baseline (기록)|34/40|FAIL|
|r3 (이번 게이트, 실행 39 + 15 expected FAIL)|**25/40**|**FAIL**|
|r4a: down-first circles revert(+조건부 fallback)로 12 회귀 복구, 6·10·20 유지|37/40 (실패 27·37, 15 제외)|FAIL|
|**r4b: r4a + 27 수정**|**38/40 (실패 37, 15 제외)**|**PASS=최소 기준**|
|r4b에서 회귀 1개 남으면|37/40|FAIL|
|r4b + 37도 pass(별도 wide_stance family 단독 비교 시)|38+/40|(r3와 pooling 금지)|

- r4 계획: (1) `search26_circles` down-first 전면 적용 제거/조건부화 — r1에서 up-first로 통과하던 12 world의 search 시간을 r1 수준으로 복구, (2) **case 27**: teacher_terminal 22.2 s `peer_approach_handoff` 원인 수정(red_1 stale margin > stance gap 악순환; r3 reobserve/peer_memory로 해소되지 않음 — 6·10·20만 해결됨), (3) 6-world에서 **6·10·20·27** 먼저 확인 후 full gate. r1/r2/r3와 pooling 없음.
- 6·10·20은 r3에서 PASS 확인(59.2/45.8/44.4 s)이므로 r4에서 그 3개가 유지되는지가 첫 관문이다.


## 8. 원본·미확인

- gcp6 영속 디스크: `runs/beamact5/validation-r3-6d-stall/`(stall 원본·SHA), `runs/beamact5/gate39-r3-run/`(39-world gate), `gate-40-r3/rejection_table.json`, `wide-start-8420000d-r3/`.
- 미확인: 청구 비용, C 대비 물리/렌더 동등성, 실기 전이. 교사 성공은 학생 성공이 아니다. world15는 이 gate에서 r3 제어 거동 미검증(제외)이고 향후 녹화/데이터셋에서도 로그 수정 전 사용하지 않는다.
