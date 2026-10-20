# nav v230-r5 PREREG — 2단계 조준(문 통과 → 1.5 m에서 슬롯) · 단독 r1 진단 → 2-robot Step B — 2026-10-20

**상태: 동결(FROZEN).** Claude 결정(`outputs/reports/claude-arch-parallel-20261019/nav-r5-decision.md`,
창민 위임 = 승인)을 그대로 동결한다. 이 문서는 **결과를 보기 전에** 커밋·push되며, 이 문서를
포함한 branch head SHA가 preregistration ID이자 ①② run의 `source_sha`다. r2·r3·r4 run은
**FAIL로 기록하고 이 문서의 결과표에서 제외**한다(§2).

- 작성: 2026-10-20 (dsh worker, `dsh/nav-v230-r5`)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-r5`
- branch: `dsh/nav-v230-r5` (새 브랜치, force 아님)
- base: `523b011c1` (= v230-r4 post-run: r4 보고서·분석 도구 수정 커밋)
- 호스트: **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`
- 도메인: **sim 전용**(`domain=sim`). 실기·실카메라 주장 아님.

## 0. 승인 조건 → 동결 내용

| # | r5 결정 (Claude, 창민 위임) | 이 prereg의 동결 |
|---|---|---|
| ① | **2단계 조준**: 문 통과 전 offset 0(성분 중심, r2가 성공한 방식) | §3.1. `v230_r5`의 stage 1 = 슬롯 offset 0, 추종 bearing = 성분 중심 |
| ② | **분리**: zone 성분 bbox 하단 행의 지면 투영 거리 ≤1.5 m에서 슬롯 활성 | §3.2. 카메라 모델은 `B_A_DERIVATION.json`과 동일. 1회 래치, fail-closed |
| ③ | 슬롯 조준점 bbox **25 %/75 %** (r1=left 25 %, r2=right 75 %), offset **±15° 제한** | §3.3. r4의 절반-중앙 공식 그대로 + 적용 offset clamp ±15° |
| ④ | claim 정의·0.52·1.0 **불변** | §3.4. `ARRIVAL_ODOM_PROJECTION_M=0.52`, `ARRIVAL_PROJECTION_PATH_CAP_M=1.0`, `u`=성분 중심 |
| ⑤ | 진단: 로봇-벽·문틀 접촉 쌍(eval-only), 명령 적산 대 GT 비율(판정 미사용) | §5.3. MJWarp scene contact 채널 + authored map 보조, 비율은 진단 전용 |
| ⑥ | 순서: ① 단독 r1 1회 → ② 2-robot Step B 1회. ①에서 문에 걸리면 ② 중단 | §4·§9. ①은 게이트 아님(진단). ②는 1회, 재실행 없음 |
| ⑦ | 수용표 `GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0` | §8. r3/r4와 동일, **불변** |
| ⑧ | r2/r3/r4 run FAIL 기록·제외, pooling 금지 | §2 |
| ⑨ | (2026-10-20 추가 지시) Step B 후 **저장된 프레임만** ffmpeg mp4 mux, 실행 중 코드·seed·타이밍 불변 | §7.4. post-processing only |

## 1. 조건 / provenance (r4와 동일, 명시된 것만 다름)

| 항목 | 값 |
|---|---|
| 장면 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c572324…c39bed` (light_scale 0.30) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e…a41b` (제어 입력 아님) |
| 시나리오/seed | `s7_pair_with_solo_v7`, seed 601, nworld 1, nav-only(r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, …)` yaw 0, r2 `(−0.8982, −2.875, …)` yaw 0 |
| 목적지 (eval-only) | zone B center `(4.6, −2.1)`, half `(0.3, 0.7)` → 서쪽 경계 **x=4.3**, 남쪽 경계 **y=−2.8** |
| 문 | door_wide x=2.2, y ∈ [−3.125, −2.125] (폭 1.0 m, 2레인) |
| 카메라 | 자기 `r1__robot_cam` 640×480, gamma 1.0, JPEG q82, 10 Hz, fovy 48° + fisheye remap |
| 통신/예산 | `peer_en`, SIM 60 s (600 tick, 기대 rows 1202 / commands 1200 — 조기 arrival 종료 시 그 시점 값) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60; forward `0.004024203361827748` m/pct-s, yaw `1.7275488814064257` deg/pct-s; `source_sha=d182b67…` ≠ 실행 SHA → queue에 mismatch 명시, `changes_physics=False`) |
| gate band | `gpu_calib_v230` (H 110–114 OpenCV, S≥100, V 30–230, min component 600), bearing `positive_left` |
| C (r2 승인, 그대로) | `acquire_min_height_norm=0.02`, `acquire_confirm_ticks=3`, `forward_reacquire=true`, 전진 상한 2.4 m |
| 금지 입력 | static map(제어), cargo, top camera, GT 좌표/접촉/성공 판정. 판단은 자기 RGB·자기 명령·통신만 |

### 1.1 mode 결선 (동결, default OFF)

- `E2EWARP_NAV_GATE_MODE=v230_r5` (새 mode; 기본은 `v1_search`),
  `E2EWARP_NAV_ARRIVAL=odom_projection` (flag `--arrival-odom-projection`).
- queue marker(전부 필수, prepare/execute env와 일치해야 admit): r4의 전부
  (`nav_gate_mode=v230_r5`, `nav_zone_profile=gpu_calib_v230`, `nav_acquisition=forward_then_search`,
  `nav_forward_cap_m=2.4`, `nav_zone_min_component=600`, `nav_bearing_convention=positive_left`,
  `nav_acquire_min_height_norm=0.02`, `nav_acquire_confirm_ticks=3`, `nav_forward_reacquire=true`,
  `nav_arrival_mode=odom_projection`, `nav_arrival_odom_projection_m=0.52`,
  `nav_arrival_projection_path_cap_m=1.0`, `nav_slots={"r1":"left","r2":"right"}`)
  **+ `nav_slot_stage2_ground_m=1.5`, `nav_slot_offset_limit_deg=15.0`**
  (+ 단독 run은 `nav_solo_robot`, `nav_robots`가 1대).
- `v230_r5`는 `odom_projection`만 admit한다. `v230_r4`/v1/fwd24/r2/r3 queue에는 stage-2 marker가
  없고, 다른 mode에 marker가 있으면 거부한다(`NAV_SLOT_STAGE2_REQUIRE_V230_R5`).
- **r4는 동결**: `v230_r4` mode·queue·slot 동작(항상-켜짐)은 이번 변경으로 바뀌지 않는다
  (단위 시험 `test_r4_default_keeps_the_slot_always_on_and_reports_no_stage2`).

## 2. r2·r3·r4 = FAIL (기록·제외)

| run | 판정 | 원인 (원본 보고서) |
|---|---|---|
| r2 Step B | FAIL | claim이 경로 길이 기준(0.52 m)이라 위치 도달 미달 |
| r3 Step B | FAIL | 두 로봇 수렴(최소 중심 0.1681 m) → 접촉·밀림, mismatch 1·FP 1 |
| r4 Step B | FAIL | GT 1/2·claim 1/2. r1이 문 통과 전에 문 북단에 걸림(슬롯 조준이 북쪽으로 밀음) |

r2/r3/r4의 어떤 수치도 r5의 n/N·최소 거리·접촉 판정에 더하지 않는다. 단독 r4 r2 성공(claim
GT-valid)도 r5 표에 넣지 않는다(합산 금지). r5의 모든 판정은 r5 원본에서만 재계산한다.

## 3. r5 변경 = 2단계 슬롯 (claim 정의는 불변)

### 3.1 stage 1 — 문 통과 전: offset 0 (성분 중심)

- 슬롯 모드에서도 **stage-2가 열리기 전에는 추종 bearing = 성분 bbox 중심 column의 bearing**이다.
  r4의 `slot_bearing_offset_deg`는 매 프레임 계속 *측정·기록*하지만 적용하지 않는다
  (`slot_bearing_offset_applied_deg = 0`). 이는 r2가 단독·2-robot 모두에서 문을 통과한 방식이다.
- arming bearing `u`와 claim 방향은 stage와 무관하게 **항상 성분 중심**이다(§3.4).

### 3.2 stage 2 — 활성 조건: 성분 bbox 하단 행의 지면 투영 거리 ≤1.5 m

- 매 accepted 검출(가장 큰 destination 성분, C height pre-filter 통과)에서
  `ground_distance_m(u=(left+right−1)/2, v=bottom−1)`를 계산한다. `bottom`은 detector의
  **exclusive** 하단이므로 `bottom−1`이 성분의 마지막(가장 가까운) 행이다.
- 카메라 모델은 `experiments/2026-10-19-nav-v230-r2/B_A_DERIVATION.json`과 동일한
  `GATE_GROUND_PROJECTION`(fx 619.5194540517232, fy 622.1654884818748, cx 287.68910608896766,
  cy 218.69686648455726, fisheye d 4개, height 0.29983 m, pitch_down 18.9934°, x offset 0.0255 m).
- **1.5 m 유도 근거(설계값, r4 결과에 맞춘 값 아님)**: 문 x=2.2와 zone B 근접 모서리 x=4.3의
  거리 **2.1 m**에서 차체 길이와 여유를 뺀다. 차체 충돌 박스는 origin 뒤 −0.0856 m( rear cage)에서
  앞 +0.0925 m(front plate)까지이고, 1.5 m에서 base origin은 x≈**2.8 m**, 즉 문 평면을 약
  **0.6 m 지난** 위치다(차체 뒤끝도 문 평면에서 약 0.51 m 뒤). 남는 약 0.42 m는 문틀 스윕 여유다.
- 이 카메라 모델에서 1.5 m는 principal column 기준 **row 137.3/480**(norm 0.286): row 137 =
  1.5036 m(닫힘), row 138 = 1.4915 m(열림). 행→거리 감도는 그 부근 약 12 mm/px이고, 성분 폭
  안 column 변화(200–360 px)에 따른 거리 변화는 약 1.5 %(1.507–1.523 m)이므로 column 선택은
  판정을 좌우하지 않는다.
- **1회 래치**: 한 번 열리면 재관측이 멀어져도 닫히지 않는다(one-shot). bbox가 없거나 행이
  지면에 투영되지 않으면 **열리지 않는다**(fail-closed: 추측 거리로 대체하지 않음).
- 활성 시각·활성 거리·활성 tick·raw/applied offset을 run의 `own_navigation` 행에 매 tick 기록한다.

### 3.3 슬롯 조준점 25 %/75 % 와 ±15° 제한

- 조준점은 r4와 동일하게 **성분 bbox의 25 %(left) / 75 %(right) column**이며, detector의 선형
  column→bearing 사상에서 `(b_c + b_edge)/2`와 같다(r1=left 25 %, r2=right 75 %). 별도 각도
  상수는 없다.
- stage 2가 열린 뒤 **적용** offset은 `clamp(offset, −15°, +15°)`다. raw offset은 기록하되 적용하지
  않는다. 15°는 활성(1.5 m)에서 arming row(0.365 m)까지 약 1.1 m 주행할 때 측방 약 0.29 m를
  만들어 두 로봇을 분리하면서, r4 r1 arming에서 측정된 −21.0°처럼 문틀을 향하는 과도한 조준을
  막는 값이다(사용자 승인 r5 결정, 새로 맞춘 값 아님).

### 3.4 불변 확인 (동결 시험)

- `ARRIVAL_ODOM_PROJECTION_M == ARRIVAL_ODOM_RESIDUAL_M == 0.52`, `ARRIVAL_PROJECTION_PATH_CAP_M == 1.0`.
- stage 2가 켜져도 arming `u`는 성분 중심이다: `test_stage2_never_changes_the_armed_claim_direction_or_0_52`
  (슬롯 +5°, stage 2 활성 상태에서 u=0°, claim 37틱=0.5211 m).
- stage 2는 추종 조준에만 작용한다. arming/claim/fail-safe(1.0 m)는 r3/r4와 같은 코드 경로다.
- r4 mode는 무변경(위 §1.1).

## 4. ① 단독 r1 진단 (진단 전용, **게이트 아님**, 1회)

| 항목 | 값 |
|---|---|
| run | `e2ewarp-nav-v230-r5-solo-r1` (새 out dir + admission dir) |
| 조건 | §1과 동일. XML에서 r2를 prune, `nav_robots=['r1']`, `nav_solo_robot=r1`, slot left |
| seed/budget | 601 / SIM 60 s, nworld 1, `peer_en` |
| 기록 | 문 통과 여부(GT x가 2.2를 넘는 시각), stage-2 활성 시각·거리, arming/claim 시각, claim `d_proj`·path, claim/최종 GT(zone 안/밖), GT/명령 적산 비율, 로봇-벽·문틀 접촉 쌍(§5.3) |
| 판정 | **게이트 아님.** "문 통과"는 GT x>2.2 도달로 기록하고, r1이 문에 걸려 GT 전진이 멈추면 **② 중단**(§9). 단독 실패 시 재실행 없음(1회 규칙) |

## 5. ② 2-robot Step B (1회)

### 5.1 절차
- 새 run root `e2ewarp-nav-v230-r5-run` + admission `e2ewarp-nav-v230-r5-admission`.
- prepare → `stack-check ok=True`(blocked 0) → execute(`--mode nav --seed 601 --nworld 1
  --condition peer_en --nav-sim-budget-s 60 --arrival-odom-projection`, `--expected-source-sha <SHA>`)
  → `scripts.e2ewarp_nav_recount` → `experiments/2026-10-20-nav-v230-r5/nav_v230_r5_analysis.py`.

### 5.2 수용표 (r3/r4와 동일, **불변**)

```
PASS ⇔ VALID (§7)
      ∧ GT 도착 2/2            (최종 base가 zone B 사각형 안, eval-only 재계수)
      ∧ claim 2/2 ∧ claim_mismatch 0   (claim 있고 최종 GT 밖 = mismatch)
      ∧ FP 0                   (§6)
      ∧ 경계 위반 0            (§7 경계 감사 전부 통과)
```

- `GT 도착`은 **최종** tick 기준이다. claim 시점 GT가 밖이었던 수는 별도 진단 칸
  (`claims_outside_gt_at_claim_time_n`)에 기록한다.
- **접촉은 INVALID가 아니라 실패 원인**이다(§5.4).

### 5.3 진단 기록 (필수, 판정 미사용)

1. **로봇-벽·문틀 접촉 쌍 (eval-only)**: r5 contact-ledger의 새 `scene` 채널 — MJWarp contact
   buffer에서 실행 로봇 geom과 **비로봇 geom**(floor 제외)의 접촉을 geom 이름·MuJoCo dist와 함께
   매 step 기록한다. `zone_wall_divider_1`/`zone_wall_south`는 문틀로 분류한다. 원본이 읽히지
   않으면 `scene_contacts_available=false`와 사유를 기록하고 0으로 보고하지 않는다. 보조로
   authored map 사각형 대 로봇 footprint OBB 최소 분리(eval-only)를 같은 분석에 남긴다
   (이 보조는 box-only라 양수여도 접촉 없음을 증명하지 않는다고 명시).
2. **명령 적산 대 GT 이동 비율**: 로봇별 전체 run의 `command_path_m`(발행 wheel pulse × 주입
   캘리브레이션 적산), `odom_path_m`(adapter 자기 적산), `gt_path_m`(eval-only qpos)와 그 비율.
   **판정에는 쓰지 않는다**(구속/헛바퀴 식별용).
3. stage-2: 활성 시각·활성 거리·활성 tick 수·raw/applied offset 범위·clamp tick 수.

### 5.4 접촉의 지위
- 접촉은 **INVALID가 아니다.** run은 VALID로 남고, 접촉 횟수·시각·geom 쌍을 **실패 원인 칸**에 기록한다.
- 수용표가 PASS여도 접촉이 있으면 "PASS(접촉 기록 있음)"으로 표기하고 접촉 수치를 함께 보고한다.

### 5.5 로봇 간 최소 거리 (r4와 동일 정의)
- MJWarp 접촉 원장(robot-robot tick/pair/first/last), GT base 중심거리 최소·시각, base 충돌 박스
  (`base_lower_collision` 0.181×0.087 OBB) 최소 분리·시각, 중심거리 <0.181 m tick 수.

## 6. FP 0
**① zone 없는 프레임 오검출 0/10 (r5 SHA 재렌더) ∧ ② 최종 GT zone 밖 claim 0건.**
- ①은 `experiments/2026-10-19-nav-v230-r3/render_check.py`(파일 불변)를 r5 SHA clean clone에서
  1회 실행한다(5자세 × tick 0·5 = r1 10프레임, 검출 0/10, 최대 4-연결성분 <600 px). 실패하면
  ②를 실행하지 않고 렌더 수치 그대로 보고한다.
- ②는 분석 도구의 `claim_mismatch_n`이다.

## 7. VALID (아니면 결과표 제외)

| 항목 | 요구 |
|---|---|
| source/pin | admission queue·run queue·RUN_META·result `source_sha` == push SHA == VM HEAD, `git status --porcelain` 0줄 |
| 장면·예산 | `s7_pair_with_solo_v7`, `zone_wide_two_doors_final_v3`, r5 스폰/로봇 집합, budget 60.0, static_map false, cargo false |
| mode binding | §1.1 marker 전부, prepare/execute env 일치(admission == run queue) |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20, source mismatch 명시 |
| ticks/rows | 60 s 기대 ticks 601 / rows 1202 / commands 1200 (조기 arrival 종료는 그 시점 값으로 기록) |
| 경계 감사 | `held_world_reads=0`, `top_camera_control=false`, `static_map_input=false`, `gpu_noslip_iterations=0`, `cpu_physics_steps=0`, `cpu_render_calls=0` |
| status | `cap_end`(60 s) 또는 arrival 조기 종료(`NAV_ARRIVAL_UNVERIFIED`). **`cap_end`는 성공이 아니다.** |
| 접촉 | VALID 조건이 아니다(§5.4) |

### 7.4 녹화 (2026-10-20 지시, post-processing only)
- 실행 중 프레임 저장 주기·해상도·JPEG 품질·seed·timing·코드를 **바꾸지 않는다**. run이 이미
  저장하는 `world-00/review-rgb/r{1,2}-NNNNNN.jpg`만 사용한다.
- Step B **종료 후** 저장된 프레임을 ffmpeg로 mux한다: 실제 저장 fps = 프레임 수/구간 길이로
  먼저 확인하고 `-framerate <fps> -i <pattern> -c:v libx264 -crf 23 -pix_fmt yuv420p`, 대표
  클립은 720p(`scale=-2:720`) 15 MB 이하 1개 + full mp4. run root/evidence에 저장.
- 보고에 프레임 경로·수, fps, mp4 경로·길이·크기, 실행 SHA/seed/prereg 불변, in-run 코드 변경 0을 적는다.

## 8. PASS / FAIL

`PASS ⇔ VALID ∧ GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0`.
- VALID가 아니면 수용표를 채우지 않는다.
- FAIL이면 원인(접촉/슬립/조향/odometry)을 수치로 기록한다. 다음 후보는 별도 승인 대상이다.
- ②는 **1회**다. 재실행·중단 후 재개 금지. 다른 run과 pooling 금지.

## 9. 중단·보고

- **①→② 중단 조건**: ① 단독 r1이 문에 걸려 GT x가 2.2를 넘지 못하거나, 20 s 이후 GT 전진이
  정체(문틀 구속)하면 **②를 실행하지 않고** ① 수치·프레임·접촉으로 보고한다.
- 그 밖의 중단: CPU 시험 실패, push 실패, ② FP 0 위반(새 SHA 재렌더), admit/ABI 오류,
  relay 429/잔액, gcp6 stockout/start 실패, 180분 초과. 중단 시 증거 보존 → lease 삭제 →
  프로세스 0/GPU 0 → stop → TERMINATED 확인.
- gcp6 start/stockout 실패는 반복 루프 없이 원인만 보고한다.
- ② 실패·접촉도 숫자 그대로 보고한다(재시도 없음).

## 10. 증거 경로

- 코드: `harness/e2ewarp_selfnav.py`(stage-2 슬롯), `harness/e2ewarp_nav_gate.py`
  (`GATE_MODE_V230_R5`, `SLOT_GATE_MODES`), `harness/e2ewarp_nav_contacts.py`(scene 접촉 채널),
  `scripts/run_e2e_warp.py`(scene ledger, solo r5), `harness/e2ewarp_nav_mode.py`(불변)
- 시험: `tests/test_e2ewarp_nav_v230_r5.py`
- 분석: `experiments/2026-10-20-nav-v230-r5/nav_v230_r5_analysis.py` (r4 분석 도구를 import해
  수용표를 재계수하고 stage-2·scene 접촉·명령/GT 비율을 더한다)
- 사전 렌더: VM `runs/nav-v230-r5-render-<TS>/`, Oracle `outputs/e2e18-admin/nav-gate/v230-r5/render-<TS>/`
- run: VM `runs/e2ewarp-nav-v230-r5-{solo-r1,admission,run}/`,
  Oracle `outputs/e2e18-admin/nav-gate/v230-r5/{solo-r1,stepB,render}-<TS>/`
- 보고서: `outputs/reports/2026-10-20-nav-stepB-v230-r5-dsh-<TS>.md`

## 11. 리스크 (사전 명시)

1. **sim 전용**, n=1, seed 601, 단일 장면. 일반화 주장 아님.
2. **stage 1 수렴 위험**: 문 통과 전 두 로봇이 모두 성분 중심을 조준하므로 r3처럼 수렴할 수
   있다(r3 최소 중심 0.1681 m, 접촉). r5의 분리는 1.5 m 이후에만 작동하므로 **문 앞 수렴은
   이번 라운드가 고치지 않는다.** 그 경우 접촉 수치를 그대로 기록한다.
3. **활성 시점 오차**: 1.5 m 게이트는 bbox 하단 행(보이는 성분) 기준이다. 문틀에 가려 하단이
   잘리면 보이는 하단이 실제 근접 모서리보다 멀어 활성이 **늦어질** 수 있다(조기 활성보다 안전한
   방향). 12 mm/px 감도와 1.5 % column 편차는 허용 오차가 아니라 기록 사항이다.
4. **문틀 접촉 계수**: r5에서 MJWarp scene 접촉 채널을 새로 쓴다. 버퍼 필드가 예상과 다르면
   `scene_contacts_available=false`로 기록하고 authored-map 보조(박스 전용, 양수≠무접촉)로만
   판정한다. 0으로 보고하지 않는다.
5. **단독 run의 일반화 한계**: 상대 로봇이 없어 접촉·상호 밀침이 없는 조건만 본다.
6. **calibration source mismatch**(`d182b67` ≠ 실행 SHA)는 계속 명시한다(`changes_physics=false`).
7. **RUN_META.class=dev**는 러너 하드코딩 값이다(prereg 등급은 study).
8. **claim·0.52/1.0·슬롯 공식은 결과를 본 뒤 재조정하지 않는다.** 1.5 m도 r4 결과에 맞춰
   바꾸지 않는다(§3.2의 기하 유도값).
9. **녹화는 post-processing only**(§7.4). 실행 중 프레임 저장 조건을 바꾸지 않으므로 seed·타이밍·
   물리 결과에 영향이 없다. 만약 mp4 mux가 원본 프레임을 변경·삭제하면 그 사실을 보고한다.
