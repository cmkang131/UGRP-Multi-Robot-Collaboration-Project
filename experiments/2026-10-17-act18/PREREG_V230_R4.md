# nav v230-r4 PREREG — ① 단독 claim 진단 · ② 주문서 슬롯(좌/우) gate · ③ 남쪽 쏠림 조향 진단 — 2026-10-19

**상태: 동결(FROZEN).** 창민이 2026-10-19에 r4 3단계를 승인했다. 이 문서는 **결과를 보기 전에**
커밋되며, 이 문서를 포함한 push된 branch head SHA가 preregistration ID이자 ①②③ run의
`source_sha`다. r3 Step B는 **FAIL로 기록하고 이 문서의 결과표에서 제외**한다(§2).

- 작성: 2026-10-19 (dsh worker, `dsh/nav-v230-r4`)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-r4`
- branch: `dsh/nav-v230-r4` (새 브랜치, force 아님)
- base: `3d90cc3ebbcb97eb7280405de704c7e5b5d1216f` (= v230-r3 post-run: r3 보고서·분석 도구
  수정 커밋. r3 Step B source는 그 이전 `a84082b19`)
- 호스트: **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`
- 도메인: **sim 전용**(`domain=sim`). 실기·실카메라 주장 아님.

## 0. 승인 조건 → 동결 내용

| # | 2026-10-19 r4 승인 (창민) | 이 prereg의 동결 |
|---|---|---|
| ① | 로봇 단독 1회씩(접촉 없이 claim 검증) | §4. `v230_r4` 동일 조건, **한 로봇만 XML에 남긴** 진단 run 2회(r1, r2). 진단 전용, **게이트 아님** |
| ② | 주문서에 로봇별 슬롯(좌/우) 지정 | §3·§5. 주문서 `slots={r1:left, r2:right}`를 근거로 자기 카메라 성분의 **자기 절반 중앙**을 조준. claim 정의·0.52·1.0 불변 |
| ③ | 남쪽 쏠림 조향 진단 | §6. ①② 로그의 명령 yaw·GT yaw·오도메트리 yaw·코스팅·슬립 분해. **수정은 이번 범위 아님** |
| ④ | 수용표 유지 | §8. `GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0` (r3와 동일) |
| ⑤ | r4 prereg에 로봇 간 최소 거리 기록 | §5.3. MJWarp 접촉 원장 + GT base 박스 분리 + 중심거리 |
| ⑥ | 접촉은 INVALID가 아니라 실패 원인으로 기록 | §5.4·§7. 접촉해도 run은 VALID; 접촉 횟수·시각·쌍을 원인 칸에 기록 |
| ⑦ | r3 FAIL 제외·pooling 금지 | §2. r3·r2·45 s dev·fwd24·v1 수치를 r4 n/N에 더하지 않음 |
| ⑧ | 0.52/1.0 claim 정의 변경 금지 | §3.3. `ARRIVAL_ODOM_PROJECTION_M=0.52`, `ARRIVAL_PROJECTION_PATH_CAP_M=1.0`, `u`=arming 성분-중심 bearing. 슬롯은 **추종 조준에만** 작용 |

## 1. 조건 / provenance (r3와 동일, 명시된 것만 다름)

| 항목 | 값 |
|---|---|
| 장면 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c572324…c39bed` (light_scale 0.30) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e…a41b` (제어 입력 아님) |
| 시나리오/seed | `s7_pair_with_solo_v7`, seed 601, nworld 1, nav-only(r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, …)` yaw 0, r2 `(−0.8982, −2.875, …)` yaw 0 (r3와 동일) |
| 목적지 (eval-only) | zone B center `(4.6, −2.1)`, half `(0.3, 0.7)` → 서쪽 경계 **x=4.3**, 남쪽 경계 **y=−2.8** |
| 카메라 | 자기 `r1__robot_cam` / `r2__robot_cam` 640×480, gamma 1.0, JPEG q82, 10 Hz, fovy 48° + 측정 fisheye remap |
| 통신/예산 | `peer_en`, SIM 60 s (600 tick, 기대 rows 1202 / commands 1200 — 조기 arrival 종료 시 그 시점 값) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60; forward `0.004024203361827748` m/pct-s, yaw `1.7275488814064257` deg/pct-s; `source_sha=d182b67…` ≠ 실행 SHA → queue에 mismatch 명시, 장면 `changes_physics=False`) |
| gate band | `gpu_calib_v230` (H 110–114 OpenCV, S≥100, V 30–230, min component 600), bearing `positive_left` |
| C (r2 승인, 그대로) | `acquire_min_height_norm=0.02`, `acquire_confirm_ticks=3`, `forward_reacquire=true`, 전진 상한 2.4 m |
| 금지 입력 | static map(제어), cargo, top camera, GT 좌표/접촉/성공 판정. 판단은 자기 RGB·자기 명령·통신만 |

### 1.1 mode 결선 (동결, default OFF)

- `E2EWARP_NAV_GATE_MODE=v230_r4` (새 mode; 기본은 `v1_search`),
  `E2EWARP_NAV_ARRIVAL=odom_projection` (flag `--arrival-odom-projection`).
- queue marker(전부 필수, prepare/execute env와 일치해야 admit): r3의 전부
  (`nav_gate_mode=v230_r4`, `nav_zone_profile=gpu_calib_v230`, `nav_acquisition=forward_then_search`,
  `nav_forward_cap_m=2.4`, `nav_zone_min_component=600`, `nav_bearing_convention=positive_left`,
  `nav_acquire_min_height_norm=0.02`, `nav_acquire_confirm_ticks=3`, `nav_forward_reacquire=true`,
  `nav_arrival_mode=odom_projection`, `nav_arrival_odom_projection_m=0.52`,
  `nav_arrival_projection_path_cap_m=1.0`) **+ `nav_slots={"r1":"left","r2":"right"}`**
  (+ 단독 run은 `nav_solo_robot`, `nav_robots`가 1대).
- `v230_r4`는 `odom_projection`만 admit한다(flag 없으면 `NAV_ARRIVAL_REQUIRES_V230_R3`).
  슬롯 marker는 `v230_r4` 밖에서 거부된다(`NAV_SLOTS_REQUIRE_V230_R4`).
- **v1/v230_fwd24/v230_r2/v230_r3 기본값·queue는 불변**: 그 mode queue에는 `nav_slots`/
  `nav_solo_robot` 키가 없고, 생성자 기본 `slot=None`은 조준에 영향이 없음을 단위 시험으로 확인한다.

## 2. r3 = FAIL (기록·제외)

| 항목 | r3 값 (원본 `outputs/e2e18-admin/nav-gate/v230-r3/stepB-20261019T2025Z/`) |
|---|---|
| source SHA | `a84082b195967b39a2e486b3c90a5b1e8eb24d0f` (VALID) |
| 판정 | **FAIL** — GT 1/2(나이프엣지 +2.8 mm), claim 2/2, mismatch 1, FP 1(최종)/2(claim 시점), 경계 0 |
| 원인 | 두 로봇이 26.4 s부터 base 충돌 박스 거리(<0.181 m) 안으로 수렴(최소 0.1681 m, claim 시 0.174 m) → 접촉·밀림. wheel odometry가 GT를 대표하지 못함(r1 GT/odom 0.842, r2 0.613) |

r3의 어떤 수치도 r4의 n/N·최소 거리·접촉 판정에 더하지 않는다. r2/45 s dev/decay/fwd24/v1도 같다.

## 3. r4 변경 = 주문서 로봇별 슬롯 (claim 정의는 불변)

### 3.1 정의와 계산 (새 상수 없음)

- 주문서(static)에 `slots`를 넣는다: `{"r1": "left", "r2": "right"}`. `left`/`right`는 **자기
  카메라 기준** 가시 목적지 성분의 두 동일 절반 중 이 로봇이 맡는 쪽이다(정면 +x 기준 좌=+y 북).
  r1은 북쪽 레인(`LANE_Y r1=−2.375`), r2는 남쪽 레인(−2.875)에 스폰하므로 r1=left, r2=right다
  (기존 lane 배정에서 유도, 새 상수 아님).
- 조준 bearing: 성분 bbox의 중심 column bearing `b_c`, 왼/오른쪽 edge column bearing
  `b_L, b_R`(검출기의 기존 선형 column→bearing 사상). 슬롯 절반의 중심은 **중심과 edge의 중점**이다:
  `b_aim = (b_c + b_L)/2` (left) 또는 `(b_c + b_R)/2` (right). 별도 각도 상수를 두지 않는다.
- 슬롯 offset `offset = wrap(b_aim − b_c)`은 회전 불변량으로 기억 landmark에 저장되고, **추종
  (following) bearing `b_c + offset`에만** 쓰인다. armed 시점의 `u`는 **성분-중심 `b_c`** 그대로다.
- 근거: r3에서 두 로봇이 같은 성분-중심을 추종해 한 점으로 수렴했다(최소 0.168 m). 각자 가시
  성분의 자기 절반 중앙을 추종하면 문(aperture) 통과 전에는 문 개구가, 통과 후에는 목적지 표식의
  절반이 조준점이 되어 분리된다. GT·지도·접촉은 읽지 않는다.

### 3.2 새 mode `v230_r4`

`v230_r4` = `v230_r3`와 **동일**한 band·C gate·2.4 m 전진·arming(0.96)·claim(0.52 투영)·
fail-safe(1.0 m)에 §3.1 슬롯만 더한다. 단독 진단도 같은 mode를 쓴다(활성 로봇 1대의 슬롯).

### 3.3 불변 확인 (동결 시험)

- `ARRIVAL_ODOM_PROJECTION_M == ARRIVAL_ODOM_RESIDUAL_M == 0.52`, `ARRIVAL_PROJECTION_PATH_CAP_M == 1.0`.
- 슬롯이 있어도 armed/claim의 `arrival_bearing_armed_deg`/`arrival_u_deg`는 성분-중심이다
  (`test_slot_aim_never_changes_the_armed_claim_direction`: 슬롯 offset +5°에서도 u=0°, claim 37틱).
- v1/fwd24/r2/r3 queue에 슬롯 marker 0, 생성자 기본 `slot=None`에서 offset 0·동일 궤적.

## 4. ① 단독 로봇 진단 (진단 전용, **게이트 아님**)

| 항목 | 값 |
|---|---|
| run | `e2ewarp-nav-v230-r4-solo-r1`, `e2ewarp-nav-v230-r4-solo-r2` (각각 새 out dir + admission dir) |
| 조건 | §1과 동일. XML에서 **상대 로봇을 prune**(r2 단독 run이면 r1·r3 제거), `nav_robots=[해당]`, `nav_solo_robot=해당` |
| seed/budget | 601 / SIM 60 s, nworld 1, `peer_en` |
| 판정 | **게이트 아님.** 기록: claim 시각·`d_proj`·claim 시점/최종 GT(zone 안/밖)·GT/odom 비율·yaw 오차·코스팅·접촉(불가능=0). "접촉 없이 claim이 성립하는가"는 (i) 씬에 상대 로봇이 없어 접촉 불가, (ii) claim이 있고 claim 시점 GT가 zone 안이면 **성립**, 아니면 수치 그대로 |
| 금지 | 단독 결과로 ② 수용표를 채우지 않는다. 단독 run 실패 시 재실행 없음(1회 규칙) |

## 5. ② 2-robot 슬롯 gate (1회)

### 5.1 절차
- 새 run root `e2ewarp-nav-v230-r4-run` + admission `e2ewarp-nav-v230-r4-admission`.
- prepare → `stack-check ok=True`(blocked 0) → execute(`--mode nav --seed 601 --nworld 1
  --condition peer_en --nav-sim-budget-s 60 --arrival-odom-projection`, `--expected-source-sha <SHA>`)
  → `scripts.e2ewarp_nav_recount` → `experiments/2026-10-19-nav-v230-r4/nav_v230_r4_analysis.py`.

### 5.2 수용표 (r3와 동일, **불변**)

```
PASS ⇔ VALID (§7)
      ∧ GT 도착 2/2            (최종 base가 zone B 사각형 안, eval-only 재계수)
      ∧ claim 2/2 ∧ claim_mismatch 0   (claim 있고 최종 GT 밖 = mismatch)
      ∧ FP 0                   (§5.2.1)
      ∧ 경계 위반 0            (§7 경계 감사 전부 통과)
```

- `GT 도착`은 **최종** tick 기준이다(r3와 같은 정의). claim 시점 GT가 밖이었던 수는 별도 진단
  칸(`claims_outside_gt_at_claim_time_n`)에 기록한다.

#### 5.2.1 FP 0
**① zone 없는 프레임 오검출 0/10 (새 SHA 재렌더) ∧ ② 최종 GT zone 밖 claim 0건.** 둘 다 필요하다.
- ①은 `experiments/2026-10-19-nav-v230-r3/render_check.py`(파일 불변)를 r4 SHA clean clone에서
  1회 실행한다(5자세 × tick 0·5 = r1 10프레임, 검출 0/10, 최대 4-연결성분 <600 px). 실패하면 ②를
  실행하지 않고 렌더 수치 그대로 보고한다.
- ②는 분석 도구의 `claim_mismatch_n`(=최종 GT 밖 claim)이다.

### 5.3 로봇 간 최소 거리·접촉 기록 (필수)
- **MJWarp 접촉 원장**(`contact-ledger.json`, eval-only): 매 step 후 contact buffer에서 두 로봇의
  서로 다른 geom 쌍을 기록 — 접촉 tick 수, 쌍 수, 첫/마지막 시각, geom 이름, dist.
- **GT 최소 거리**: base 중심거리 최소·시각, base 충돌 박스(`base_lower_collision`) OBB 최소
  분리(m)·시각, 중심거리 <0.181 m tick 수(r3 비교 기준).
- 접촉 원장 필드를 읽을 수 없으면 `contacts_available=false`와 사유를 기록하고, GT 박스 분리·
  중심거리로만 원인을 판정한다(0으로 보고하지 않는다).

### 5.4 접촉의 지위
- 접촉은 **INVALID가 아니다.** run은 VALID로 남고, 접촉 횟수·시각·쌍을 **실패 원인 칸**에 기록한다.
- 수용표가 PASS여도 접촉이 있으면 "PASS(접촉 기록 있음)"으로 표기하고 접촉 수치를 함께 보고한다.
  수용표가 FAIL이면 접촉은 원인 후보로만 쓰고, 판정은 수용표 수치 그대로다.

## 6. ③ 남쪽 쏠림 조향 진단 (진단만, 수정 없음)

①②의 원본에서 로봇별로 다음을 분해한다(모두 eval-only, 제어 입력 아님):

1. **명령**: 매 tick wheel pulse(정규화)×duration → percent-second → 주입 캘리브레이션으로
   명령 forward(m)·yaw(deg). `turn_cmd = ((w_R d_R) − (w_L d_L))/4`.
2. **GT**: qpos quaternion의 yaw, tick별 GT 변위·경로. **odom**: 어댑터의 `odom_pose`.
3. **분해 지표**: 구간(pre_armed / armed→claim / post_claim)별
   - `command_yaw_deg`, `odom_yaw_deg`, `gt_yaw_deg`, `yaw_gain_gt/odom`, `turn_sign_agreement`,
     좌/우 명령별 GT yaw/tick, `zero_command_gt_yaw_drift`,
   - `gt/odom 경로`, `step_forward_gain`, GT의 u방향 투영, `gt_lateral_m`(횡슬립),
   - **코스팅**: wheels=0 tick에서 GT 이동·회전,
   - **yaw 오차 지속 개시**(|GT−odom yaw|>10°가 10틱 지속) 시각·크기.
4. **판정 카테고리**: (a) 조향 **부호** 오류(명령 부호와 GT yaw 부호 불일치가 지속), (b) **차동/캘리브레이션**
   게인 오차(부호는 맞고 크기 배율이 다름), (c) **슬립**(전진 게인 <1, 횡슬립>0, 코스팅 이동),
   (d) **접촉 토크**(접촉 원장 구간과 yaw 오차 급변의 시간 일치). 하나 또는 조합으로 판정하고
   근거 수치를 적는다. **이번 라운드에서 코드 수정은 하지 않는다.**

## 7. VALID (아니면 결과표 제외)

| 항목 | 요구 |
|---|---|
| source/pin | admission queue·run queue·RUN_META·result `source_sha` == push SHA == VM HEAD, `git status --porcelain` 0줄 |
| 장면·예산 | `s7_pair_with_solo_v7`, `zone_wide_two_doors_final_v3`, r4 스폰/로봇 집합, budget 60.0, static_map false, cargo false |
| mode binding | §1.1 marker 전부, prepare/execute env 일치(admission == run queue) |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20, **source mismatch 명시** |
| ticks/rows | 60 s 기대 ticks 601 / rows 1202 / commands 1200 (조기 arrival 종료는 그 시점 값으로 기록하고 60 s 기대치를 주장하지 않는다) |
| 경계 감사 | `held_world_reads=0`, `top_camera_control=false`, `static_map_input=false`, `gpu_noslip_iterations=0`, `cpu_physics_steps=0`, `cpu_render_calls=0` |
| status | `cap_end`(60 s) 또는 arrival 조기 종료. **`cap_end`는 성공이 아니다.** |
| 접촉 | VALID 조건이 아니다(§5.4) |

## 8. PASS / FAIL

`PASS ⇔ VALID ∧ GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0` (§5.2).
- VALID가 아니면 수용표를 채우지 않는다.
- FAIL이면 원인(접촉/슬립/조향/odometry)을 수치로 기록하고 다음 후보는 별도 승인 대상이다.
- ②는 **1회**다. 재실행·중단 후 재개 금지. r3/r2와 pooling 금지.

## 9. 중단·보고

- 중단: CPU 시험 실패, push 실패, ② FP 0 위반(새 SHA 재렌더), admit/ABI 오류, relay 429/잔액,
  gcp6 stockout/start 실패, 180분 초과. 중단 시 증거 보존 → lease 삭제 → 프로세스 0/GPU 0 →
  stop → TERMINATED 확인.
- gcp6 start/stockout 실패는 반복 루프 없이 원인만 보고한다.
- ② 실패·접촉도 숫자 그대로 보고한다(재시도 없음).

## 10. 증거 경로

- 코드: `harness/e2ewarp_selfnav.py`(슬롯 조준), `harness/e2ewarp_nav_gate.py`(`GATE_MODE_V230_R4`,
  `SLOT_BY_ROBOT`, solo), `harness/e2ewarp_nav_mode.py`(`slots` allowlist, robots 인자),
  `harness/e2ewarp_nav_contacts.py`(eval-only 접촉 원장), `scripts/run_e2e_warp.py`
  (`--nav-solo-robot`, contact ledger), `scripts/e2e_warp_physics.py`(`nav_keep`)
- 시험: `tests/test_e2ewarp_nav_v230_r4.py`
- 분석: `experiments/2026-10-19-nav-v230-r4/nav_v230_r4_analysis.py` (r3 원본으로 수용표 재계수
  검증: GT 1/2·claim 2/2·mismatch 1·min 0.1681 m 재현)
- 사전 렌더: VM `runs/nav-v230-r4-render-<TS>/`, Oracle `outputs/e2e18-admin/nav-gate/v230-r4/render-<TS>/`
- run: VM `runs/e2ewarp-nav-v230-r4-{solo-r1,solo-r2,admission,run}/`,
  Oracle `outputs/e2e18-admin/nav-gate/v230-r4/{solo-r1,solo-r2,stepB}-<TS>/`
- 보고서: `outputs/reports/2026-10-19-nav-stepB-v230-r4-dsh-<TS>.md`

## 11. 리스크 (사전 명시)

1. **sim 전용**, n=1, seed 601, 단일 장면. 일반화 주장 아님.
2. **슬롯 조준의 문 통과 위험.** 절반 조준은 r1을 북쪽으로 민다. 문 개구(y −3.125..−2.125)와
   분할벽(x=2.2, y≥−2.125)을 스치는 경로가 되면 접촉·정지가 날 수 있다. 그 경우도 수치 그대로
   기록한다(조준 상수는 결과를 보고 바꾸지 않는다).
3. **자기 오도메트리 과대 적산.** r3에서 armed→claim GT/odom 경로 비 r1 0.842, r2 0.613이었다.
   접촉이 없어도 r2의 적산 오차가 남으면 ②는 GT 2/2에 실패할 수 있다(그것이 ①의 질문이다).
4. **접촉 원장 가용성.** MJWarp contact buffer 필드가 예상과 다르면 접촉을 직접 계수하지 못하고
   GT 박스 분리로 대체한다(0으로 보고하지 않음).
5. **단독 run의 일반화 한계.** 단독은 상대 로봇이 없어 접촉·상호 밀침이 없는 조건만 본다.
   2-robot 조건의 슬립/접촉을 대표하지 않는다.
6. **calibration source mismatch**(`d182b67` ≠ 실행 SHA)는 계속 명시한다(`changes_physics=false`).
7. **RUN_META.class=dev**는 러너 하드코딩 값이다(prereg 등급은 study).
8. **r3 0.52/1.0·claim 정의는 불변**이며, 슬롯은 추종 조준에만 작용한다. 결과를 본 뒤 슬롯
   공식·상수를 재조정하지 않는다.
