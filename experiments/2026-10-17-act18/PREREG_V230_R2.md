# nav v230-r2 PREREG — C(획득 품질) + B(거리 기반 arrival, 방식 TBD) — 2026-10-19

**상태: 동결(FROZEN).** 창민 승인(2026-10-19)의 B/C를 사전 등록한다. **B 방식은
창민 확정: (a) 하단 접촉 후 오도메트리 잔여 거리 주행**(Claude 02:19 결정, 2026-10-19).
잔여 거리는 45 s dev 진단 fit이 아니라 **카메라 기하(row curve) + zone near edge +
0.15 m design margin**에서 유도해 **0.52 m**로 동결했다(§3.1·§4). (b) 지면 투영은
구현·시험만 유지하고 default OFF로 둔다. 결과를 본 뒤 상수를 바꾸지 않는다.

- 작성: 2026-10-19 (dsh worker, `dsh/nav-v230-r2`)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-r2`
- branch: `dsh/nav-v230-r2` (새 브랜치, force 아님)
- base: `adaa426e73351c0b9027c5181de08ddbc5c59984` (= A decay 수정 + v230_fwd24 head)
- 호스트: **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`. Step A 높이 확인 외에는 쓰지
  않았고, Step B는 이 문서의 push 이후 **새 run 1회**만 허용한다.
- 경로 관례: 이 파일은 지시된 경로(`experiments/2026-10-17-act18/`)에 두었다. nav
  증거 스크립트·JSON은 `experiments/2026-10-19-nav-v230-r2/`에 있다.
- preregistration ID = 이 문서를 포함한 **push된 branch head SHA**(push 직후 보고서에 기록).

## 0. 승인 조건 → 동결 내용

| # | 창민 승인 (2026-10-19) | 이 prereg의 동결 |
|---|---|---|
| A | decay는 `adaa426e`에서 완료 | 이 문서는 decay를 다시 건드리지 않는다. v230-r2는 A 위에 얹는다. |
| B | arrival guard는 **재보정이 아니라 거리 기반 재설계**. (a) 하단 접촉 후 오도메트리 잔여 거리 주행 vs (b) 지면 투영 거리 ≤0.25 m 중 선택·명시 | **확정: (a)**. 접촉(0.96) latch + **0.52 m** 자기명령 적산 claim. 0.52 m는 기하 유도값(0.3649+0.15=0.5149, 반올림 상향)이며 진단 fit(0.548)을 쓰지 않는다(§3.1·§4). (b)는 구현·시험만 유지하고 default OFF. |
| C | height≥0.04는 **Step A 렌더에서 정상 zone 검출 높이가 충분한지 확인 후 확정** + **연속 3틱 검출** + **표적 놓치면 재전진 허용**. 단독 임계값 금지 | 실측 결과 0.04는 정상 검출을 거부(§2) → **0.02**로 확정. 3틱 + 재전진(2.4 m 상한 내)을 함께 mode에 넣는다. |
| D | 45 s dev run은 dev 표기로 결과 제외 | §6에 명시. Step B는 새 run만. |
| E | 수용표 유지 (GT 2/2, claim 2/2, mismatch 0, FP 0, 경계 0) | §7. |
| F | V≤230 + 2.4 m 전진 조건은 유지 | `gpu_calib_v230`, `forward_then_search`, cap 2.4 m, min_component 600, bearing `positive_left` — v230_fwd24와 동일. v1 기본값 불변. |

## 1. 조건 / provenance (동결)

| 항목 | 값 |
|---|---|
| 장면 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c572324…c39bed` (light_scale 0.30) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e…a41b` |
| 시나리오/seed | `s7_pair_with_solo_v7`, seed 601, 2 robots r1·r2, nav-only(r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, 0.032355, yaw 0)`, r2 `(−0.8982, −2.875, …)` |
| 목적지 (eval-only) | zone B center `(4.6, −2.1)`, half `(0.3, 0.7)` → 서쪽 경계 x=4.3 |
| 카메라 | 자기 `r1__robot_cam` 640×480, gamma 1.0, JPEG q82, 10 Hz, fovy 48° + 측정 fisheye remap |
| 통신/예산 | `peer_en`, SIM 60 s (600 tick, rows 1202, commands 1200) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60, forward 0.004024203361827748 m/pct-s, yaw 1.7275488814064257 deg/pct-s). `calibration_source_sha=d182b67` ≠ 실행 SHA → 결과·queue에 mismatch 명시(장면 `changes_physics=False`) |
| 금지 입력 | static map(제어), cargo, top camera, GT 좌표/접촉/성공 판정. 판단은 자기 RGB·자기 명령·통신만 |

## 2. C — 획득 품질 gate (확정값과 근거)

### 2.1 높이 실측 (V≤230 게이트 검출기, `gpu_calib_v230`)

`experiments/2026-10-19-nav-v230-r2/C_HEIGHT_EVIDENCE.json` (분석 전용, 새 run 없음):

| 프레임 | r1 x (m) | 스폰 전진 (m) | bbox (l,t,r,b) | px | **height_norm** | bottom_norm | solidity |
|---|---:|---:|---|---:|---:|---:|---:|
| Step A `door_x1.5-t000` | 1.5 | **2.398** | 81,66,379,82 | 1811 | **0.0333** | 0.171 | 0.380 |
| Step A `door_x1.5-t005` | 1.5 | **2.398** | 79,64,376,82 | 2422 | **0.0375** | 0.171 | 0.453 |
| Step A `door_x2.0-t000` | 2.0 | 2.898 | 37,74,401,97 | 3930 | 0.0479 | 0.202 | 0.469 |
| Step A `door_x2.0-t005` | 2.0 | 2.898 | 43,72,400,94 | 4133 | 0.0458 | 0.196 | 0.526 |
| Step A `door_x2.5-t005` | 2.5 | 3.398 | 24,83,439,116 | 7964 | 0.0688 | 0.242 | 0.582 |
| Step A `door_x3.0-t005` | 3.0 | 3.398+ | 22,100,496,148 | 15793 | 0.1000 | 0.308 | 0.694 |
| 45 s dev r1 주행 1.0–1.8 m 구간 | — | — | (보고) | — | **0.023–0.046** | — | — |
| **저품질 r2 1틱** (dev, 3.9 s) | −0.35 | (스폰 근처) | (보고) | — | **0.025** | 0.125 | 0.344 |

- **0.04는 정상 검출을 거부한다**: 승인 정지점 x=1.5(2.40 m)의 정적 렌더 높이는
  0.0333–0.0375이고, 실제 주행에서는 같은 구간이 0.023–0.046이다. **2.4 m 상한 안에서
  height 0.04를 처음 넘는 tick은 x=1.775(2.67 m)** 로 상한 밖이다(아래 표).
- 저품질 r2 1틱(0.025)은 정상 주행값(0.023–0.031)과 **높이로 분리되지 않는다**(폭 0.266 vs
  정상 0.28–0.44, solidity 0.344 vs 0.47–0.67로도 경계). 따라서 **높이 단독 임계값은
  gate가 될 수 없다** — 3틱 규칙이 실제 분리자다(그 1틱 검출은 3틱을 못 채운다).

### 2.2 연속 3틱 기준 임계값 (r1 주행 335 fresh tick, 기록 원본 재생)

| 후보 | 3틱 연속 확정 시각 | 확정 시 x (전진) | 2.4 m 상한 내? | 수용 tick |
|---:|---:|---:|---|---:|
| **0.02 (확정)** | 12.5 s | 0.849 (1.75 m) | **YES** | 301/335 |
| 0.025 (대안) | 15.0 s | 1.190 (2.09 m) | YES(잔여 0.31 m) | 278/335 |
| 0.03 | 17.8 s | 1.571 (2.47 m) | NO | 252/335 |
| 0.04 | 19.3 s | 1.775 (2.67 m) | NO | 234/335 |

→ **동결: `ACQUIRE_MIN_HEIGHT_NORM = 0.02`, `ACQUIRE_CONFIRM_TICKS = 3`.** 0.02는 상한
안에서 확정되고(잔여 0.65 m) 0.013–0.019 원거리 sliver를 거부한다. 0.025는 더 많이
거부하지만 확정에 2.09 m를 써 재전진 여유가 0.31 m로 줄어 대안으로만 기록한다.

### 2.3 표적 상실 시 재전진

- 추종 확정(`_target_confirmed`)은 **연속 3틱**으로 서고, **1틱 누락으로는 풀리지 않는다**.
  표적이 `ACQUIRE_MAX_AGE_S = 1.0 s`(기존 `ARRIVAL_EVIDENCE_MAX_AGE_S` 재사용, 새 상수 없음)
  동안 수용 검출을 못 내면 stale로 보고 확정을 푼다.
- stale/미확정이면 **같은 2.4 m 상한 안에서 재전진**한다(`forward_reacquire=True`).
  전진 적산은 자신이 발행한 명령 + 주입 odometry만 쓰고, 상한을 넘길 수 없다(마지막
  pulse 폭을 잘라 2.4 m에서 멈춘다). 상한 소진 후에는 제자리 SEARCH만 한다.
- v1/v230_fwd24는 `forward_reacquire=False`(one-shot)로 **동작 불변**.

## 3. B — arrival 재설계 (선택 확정: (a); 구현은 두 방식 모두 default OFF)

기존 `ARRIVAL_BOTTOM_NORM=0.98`은 이 장면에서 **도달 불가**다(관측 최대 0.967 = 행
464/480; 그 이상은 로봇 차체가 지면을 가린다). 두 후보 모두 **거리**로 판정하며
bottom band를 재보정하지 않는다.

### 3.1 (a) `--arrival-odom-residual` — 하단 접촉 후 오도메트리 잔여 거리 (**선택됨**)

| 상수 | 값 | 출처 |
|---|---:|---|
| `ARRIVAL_BOTTOM_CONTACT_NORM` | **0.96** | 기하: 하단 포화 0.967 = 행 464 = 차체가 가리는 지면 경계(관측 최대). 0.96은 그 아래 3 px |
| **`ARRIVAL_ODOM_RESIDUAL_M`** | **0.52** | **기하 유도**(아래) = 0.3649 + 0.15 = 0.5149 → 상향 반올림 0.52. 진단 fit 값(0.548)은 쓰지 않음 |
| design margin (0.15 m) | **design parameter** | 측정값 아님. "paint 근접 모서리에서 0.15 m 안쪽에서 claim"이라는 설계 선택 |
| `contract` | — | claim 시점의 **자기 발행 명령 적산 거리 ≥ 0.52 m**. 현재 프레임 불요(dead-reckoning) |

**기하 derivation** (`experiments/2026-10-19-nav-v230-r2/B_A_DERIVATION.json`, 재현 가능):

| 단계 | 값 | 근거 |
|---|---:|---|
| 카메라 자세 | h 0.29983 m, pitch 18.9934°, x offset +0.0255 m | `GATE_GROUND_PROJECTION` (측정 fisheye intrinsics + 지면 mount fit, RMS 0.049 m) |
| 접촉 행 | bottom_norm 0.96 → 행 **460.8** / 480 | `ARRIVAL_BOTTOM_CONTACT_NORM` |
| 그 행의 base 전방 지면거리(= paint 근접 모서리까지) | **0.3649 m** | 주점 열(u=cx) 지면 투영. 행 462.24(0.963)→0.3633, 464.16(0.967)→0.3611 |
| + design margin | **0.15 m** | design parameter |
| 유도 잔여 거리 | **0.5149 m** | 0.3649 + 0.15 |
| **동결** | **0.52 m** | 상향 반올림(반올림이 margin을 줄이지 않도록). 실현 margin **0.155 m** |

- **진단 fit을 쓰지 않는다**: 45 s dev의 GT 접촉 base-to-edge는 0.3982 m(34.7 s, 0.963)로,
  이 값이면 잔여 0.548 m가 되지만 이는 진단 측정값이다. 기하 row curve 값(0.3649)과
  0.033 m 차이(투영 RMS 0.049 m 이내)이며, 지시대로 **기하 값을 동결**했다. 0.3982는
  아래 재생에서 **교차검증**으로만 쓴다.
- 기록 원본 재생(교차검증, 게이트 결과 아님):

| residual | claim 시각 | claim base xy | zone 내부? |
|---:|---:|---|---|
| 0.25 | 36.5 s | (4.1501, −2.0137) | **NO** |
| 0.40 | 37.6 s | (4.3001, −1.9882) | YES(경계 0.0001 m, knife-edge) |
| **0.52 (동결)** | **38.4 s** | **(4.4094, −1.9670)** | **YES(서쪽 경계 0.109 m 안쪽)** |
| 0.55 | 38.6 s | (4.4365, −1.9615) | YES(0.137 m) |
| 0.68 | 40.0 s | (4.5656, −1.9232) | YES(0.27 m) |

  → 0.25 m는 zone 밖(mismatch)이라 불채택. 0.52 m(기하)도 재생에서 zone 안이며, 진단 GT
  기준으로도 0.109 m 안쪽이다.

### 3.2 (b) `--arrival-ground-distance-m 0.25` — 지면 투영 거리

| 상수 | 값 | 출처 |
|---|---:|---|
| 카메라 intrinsics/distortion | fx 619.519, fy 622.165, cx 287.689, cy 218.697, fisheye d=(-0.01998,-0.17076,-0.25683,0.96509) | `sim/masterpi_camera_profile.py` **측정 물리** 카메라(640×480) — 렌더가 쓰는 것과 같은 모델 |
| mount 지면 자세 | height **0.29983 m**, pitch down **18.9934°**, camera x offset **+0.0255 m** | 45 s dev r1 접근 184 fresh 검출 × 지도 zone 근접 모서리 지면 fit. RMS **0.049 m**, max 0.161 m. Step A 8프레임 독립 fit은 pitch 19.06°로 일치(높이/오프셋은 4거리에서 축퇴) |
| `ARRIVAL_GROUND_DISTANCE_M` | **0.25** (승인값) | 창민 승인 문구 |

- 판정: 현재 frame의 검출 bbox **중심 픽셀**을 지면에 투영한 거리 ≤ 0.25 m이면 claim.

**중요 — 0.25 m는 이 카메라로 도달 불가:**

| 지점 | 지면 투영 거리 |
|---|---:|
| 행 464(관측 최대 하단, 차체 가림 경계) | 0.362 m |
| 행 479(이미지 맨 아래 행) | **0.345 m** |
| 기록된 최근접 patch 중심(행 433.5) | **0.373 m** |

→ **bbox 중심 투영 거리의 하한은 0.345 m**(이미지 맨 아래 행)라서 `≤0.25 m`는 어떤
patch 형상으로도 발화하지 않는다. 기록 원본에서 이 기준의 claim은 **0건**이다.
0.40 m로 올리면 기록 최근접(0.373 m)에서 claim되고 그 지점 base는 (4.516, −1.945)로
zone 안이다 — 즉 **(b)는 상수만 재정의하면 성립하지만, 승인된 0.25 m로는 성립하지
않는다.** 이것이 B 선택에 필요한 결정이다(§4).

### 3.3 B 선택 경위 (확정: (a) — Claude 02:19)

| | (a) odometry residual | (b) ground distance |
|---|---|---|
| 상태 | 구현·시험 완료, default OFF | 구현·시험 완료, default OFF |
| 상수 | 0.96 / 0.55 m (기하+기록 원본) | 0.25 m(승인값) — **도달 불가**, 0.40 m면 성립 |
| claim 근거 | 접촉 latch + 자기 명령 적산 | 현재 frame 지면 투영 |
| 기록 원본 재생 결과 | 0.55 m에서 zone 안 claim | 0.25 m에서 claim 0건 |
| 리스크 | 접촉 검출 1틱 의존, 적산 오차(슬립) | 카메라 mount 자세 의존(차체 pitch), 0.25→0.40 재정의 필요 |

→ 창민 확정: **(a)**. (b)의 0.25 m 도달 불가는 기록으로 남기고, (b) 코드는 default OFF로
보존한다. Step B는 이 문서를 포함한 push SHA에서 **1회** 실행하며, (a) flag
(`--arrival-odom-residual`, 잔여 0.52 m는 `ARRIVAL_ODOM_RESIDUAL_M` 기하 유도값)를 쓴다.

## 4. B 선택 기록 (확정 — (a))

| 항목 | 값 |
|---|---|
| 선택 | **(a) 하단 접촉 후 오도메트리 잔여 거리 주행** |
| 선택자/시각 | 창민 확정, Claude 2026-10-19 02:19 결정 |
| 동결 상수 | `ARRIVAL_BOTTOM_CONTACT_NORM=0.96`, **`ARRIVAL_ODOM_RESIDUAL_M=0.52`** |
| derivation | §3.1: row curve(0.96 → 행 460.8) 지면거리 **0.3649 m** + design margin **0.15 m** = 0.5149 → **0.52** (상향 반올림). 진단 fit 0.548은 불사용 |
| 교차검증 | 45 s dev GT 접촉(0.963) base-to-edge 0.3982 m(기하 0.3649와 0.033 m 차, RMS 0.049 이내); 재생 claim (4.4094,−1.9670) = zone 서쪽 경계 0.109 m 안쪽 |
| (b) 상태 | 구현·unit test 유지, **default OFF**. 0.25 m는 도달 불가(하한 0.345 m)라 이번 run에서 쓰지 않는다 |

## 5. 게이트 모드 결선 (동결)

- `E2EWARP_NAV_GATE_MODE=v230_r2` (새 mode, 기본 OFF; 기본은 `v1_search`).
- queue marker(전부 필수, prepare/execute env와 일치해야 admit):
  `nav_gate_mode=v230_r2`, `nav_zone_profile=gpu_calib_v230`,
  `nav_acquisition=forward_then_search`, `nav_forward_cap_m=2.4`,
  `nav_zone_min_component=600`, `nav_bearing_convention=positive_left`,
  `nav_acquire_min_height_norm=0.02`, `nav_acquire_confirm_ticks=3`,
  `nav_forward_reacquire=true`, `nav_arrival_mode`,
  `nav_arrival_odom_residual_m=0.55`, `nav_arrival_ground_distance_m=0.25`.
- `nav_arrival_mode`는 `bottom_band`(기본, B 미선택) / `odom_residual` / `ground_distance`.
  B flag는 **v230_r2에서만** 허용되고 다른 mode의 queue에 있으면 admit 거부.
- v1/v230_fwd24 queue에는 C/B marker를 **쓰지 않는다**(기존 조건 byte 불변).

## 6. Step B 판정 절차 (B 선택 후 1회)

1. push SHA clean clone(gcp6), HEAD 일치·`git status --porcelain` 0줄.
2. lease 1개(`e2ewarp-nav-v230-r2.json`), relay는 Oracle에서만, VM에 키 없음.
3. manifest → prepare(`E2EWARP_NAV_GATE_MODE=v230_r2`, B 선택 시 해당 flag) →
   execute(`--mode nav --seed 601 --nworld 1 --condition peer_en --nav-sim-budget-s 60`,
   `--expected-source-sha <SHA>`) → recount.
4. **45 s dev run은 결과가 아니다**: `class=dev`, 45 s, gate=false로 표기하고 수용표
   분모에서 제외한다. 이전 v1/gate1/r5/v230_fwd24/decay 45 s와 **pooling 금지**.
5. Step B는 **새 run만** 센다. 재실행·중단 후 재개 금지. admit/ABI 오류는 우회 없이 기록.

## 7. 수용표 (원본 재계수)

### 7.1 VALID (아니면 결과표 제외, pooling 금지)

| 항목 | 요구 |
|---|---|
| source/pin | queue/result/RUN_META `source_sha` == push SHA == VM HEAD, clean |
| 장면·예산 | nav_scene `s7_pair_with_solo_v7`, map `zone_wide_two_doors_final_v3`, spawn y −2.375/−2.875, robots r1·r2, budget 60.0, static_map false, cargo false |
| mode binding | §5 marker 전부, prepare/execute env 일치 |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20, **source mismatch 명시** |
| ticks/rows | ticks 601, localization rows 1202, commands rows 1200 |
| 경계 감사 | `held_world_reads=0`, `top_camera_control=false`, `static_map_input=false` |
| status | `cap_end`(60 s) 또는 완주/arrival 조기 종료. **cap_end는 성공이 아니다.** |

### 7.2 PASS / FAIL (VALID에만)

```
PASS ⇔ VALID
      ∧ GT 도착 2/2            (zone B center (4.6,−2.1), half (0.3,0.7), eval-only 재계수)
      ∧ claim 2/2 ∧ claim_mismatch 0
      ∧ FP 0                   (아래 정의)
      ∧ 경계 위반 0
```

- **FP 0** = ① ② zone-없는 프레임 오검출 0/10(검출기 `gpu_calib_v230`, 최대성분 <600 px)
  **그리고** ② 도착 claim 중 GT zone 밖 claim 0건(= mismatch 0과 별도로, claim이 검출
  오검출에 기인하지 않았음을 확인).
- `detection 0/1202` → FAIL(획득 실패). 검출 n, fresh tick, 첫 검출 tick·위치,
  `drive_reason` 분포, confirm 시각을 기록한다.
- 보고 필드: 검출 n/1202, wheel n/1200, `drive_reason` 분포, GT 2/2, claim 2/2, mismatch,
  FP, 첫 검출/확정 tick, `forward_used_m`, `arrival_armed`, `arrival_travel_m`,
  `arrival_ground_distance_m`, wall/SIM, model_calls, 429/5xx, cap_end, calibration mismatch.

## 8. 금지 / 중단

- 금지: B 선택 전 Step B 실행, 상수 재조정(결과 본 뒤), v1 기본값 변경, 밴드/문턱/spawn/
  map/door 변경, 다른 조건과 pooling, 45 s dev를 결과로 쓰기, Step B 2회, admit 우회,
  VM에 키 배치, 다른 워커 프로세스/lease kill, 원본 덮어쓰기.
- 중단·보고: 테스트 실패, push 실패, ② FP 0 위반, admit/ABI 오류, relay 429/잔액,
  120분 초과. 중단 시 증거 보존 → lease 삭제 → 프로세스 0/GPU 0 → stop → TERMINATED.

## 9. 증거 경로

- 코드/증거: `experiments/2026-10-19-nav-v230-r2/` — `nav_v230_r2_evidence.py`,
  `C_HEIGHT_EVIDENCE.json`, `ARRIVAL_GEOMETRY_AUDIT.json`
- 입력 원본(기존, 보존): Step A sweep
  `outputs/e2e18-admin/nav-gate/light30-stepA/sweep-20261019T1246Z/`, 45 s dev
  `outputs/runs/act18-nav-decayfix-20261019T162044Z/`
- Step B(선택 후): VM `runs/e2ewarp-nav-v230-r2-{admission,run}/`, Oracle
  `outputs/e2e18-admin/nav-gate/v230-r2/<TS>/`, 보고서
  `outputs/reports/2026-10-19-nav-v230-r2-stepB-dsh-<TS>.md`

## 10. 리스크 (사전 명시)

1. **sim 전용**(`domain=sim`). 실제 로봇·실카메라 성능 주장 아님.
2. C 상수는 **한 세션·seed 601·단일 장면**의 Step A 렌더와 45 s dev 원본에서 나왔다.
   0.02는 그 표본에서 확정 가능하지만 다른 자세·조명·화물 장면의 일반화는 미검증이다.
3. 저품질 sliver(0.025)와 정상(0.023–0.031)이 **높이로 분리되지 않는다**. 3틱 규칙이
   주 분리자이며, 2틱짜리 sliver가 연속으로 나오는 조건은 관측되지 않았다(미검증).
4. B(b)의 mount 자세는 **차체 pitch에 의존**한다(fit은 주행 중 frame 포함). B(a)는 접촉
   검출 1틱과 슬립에 의존한다. 둘 다 단일 run 재생 감사이며 물리 게이트가 아니다.
5. `step_odometry`는 게이트 실행 경로에서 호출되지 않아 기억의 yaw/bearing 변환이
   일어나지 않는다(발견 사항, B/C 범위 밖). B(a)는 `command()`에서 자체 적산하므로
   영향받지 않는다.
6. calibration source mismatch(`d182b67` ≠ 실행 SHA)는 계속 명시한다.
7. 2.4 m는 **전진 상한**이며 도착점이 아니다. C 재전진도 같은 상한을 넘지 않는다.
