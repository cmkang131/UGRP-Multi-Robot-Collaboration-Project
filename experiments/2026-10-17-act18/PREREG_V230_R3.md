# nav v230-r3 PREREG — ① claim 정의 수정(자기 오도메트리 투영) — 2026-10-19

**상태: 동결(FROZEN).** 창민 승인·Claude 결정(2026-10-19, 창민 위임) ①을 사전 등록한다.
v230-r2 Step B는 **FAIL로 기록하고 이 문서의 결과표에서 제외**한다(§2). r3는 r2의
0.52 m 기하값을 **바꾸지 않고**, claim의 *정의*만 r2의 "자기 명령 적산 경로길이"에서
**자기 오도메트리 변위의 armed bearing 방향 투영**으로 고친다(§3). 결과를 본 뒤 상수를
바꾸지 않는다.

- 작성: 2026-10-19 (dsh worker, `dsh/nav-v230-r3`)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-r3`
- branch: `dsh/nav-v230-r3` (새 브랜치, force 아님)
- base: `d2e10e7e96c115d6794229f2e493e4caa1b96243` (= v230-r2 prereg/Step B FAIL source)
- 호스트: **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`.
- preregistration ID = 이 문서를 포함한 **push된 branch head SHA**(push 직후 보고서에 기록).
  Step B source = 그 SHA. 증거 스크립트는 `experiments/2026-10-19-nav-v230-r3/`에 있다.
- 도메인: **sim 전용**(`domain=sim`). 실기·실카메라 주장 아님.

## 0. 승인 조건 → 동결 내용

| # | Claude 결정 (2026-10-19, 창민 위임) | 이 prereg의 동결 |
|---|---|---|
| ① | claim 정의를 **x축/자기 bearing 투영**으로 수정 | `d_proj = (p_odom(t) − p_odom(t_armed)) · u(t_armed) ≥ 0.52 m` (§3). 세계 x축·지도·GT 금지 |
| ② | 0.52 m는 **B_A_DERIVATION 기하 값 그대로**, 변경 금지 | `ARRIVAL_ODOM_PROJECTION_M = 0.52`, `B_A_DERIVATION.json`의 `frozen_flag_value_m`과 동일(§3.2) |
| ③ | heading hold: armed 이후 자기 오도메트리 yaw를 armed bearing 방향으로 유지. **기존 turn 제어기**, 입력=yaw 오차. 전진 속도는 r2와 동일 | §4. `turn = clamp(yaw_error / BEARING_FULL_DEG=45°, −1, 1)`, forward=1.0(35 % × pulse 폭) |
| ④ | fail-safe: 경로 길이 **1.0 m**(=0.52/0.5)까지 `d_proj<0.52`면 claim 없이 정지, `NO_CLAIM` 기록 | §5. `ARRIVAL_PROJECTION_PATH_CAP_M = 1.0`, 정지·`NO_CLAIM` 이벤트·per-tick 필드 |
| ⑤ | 새 SHA에서 **FP 재렌더 0/10**. 실패면 Step B 중단·증거 보고 | §7. 5자세 × tick 0·5 = r1 10프레임, V≤230 검출 0/10, 최대 성분 <600 px |
| ⑥ | r2 run은 **FAIL로 기록하고 결과 제외** | §2. r2 수치 그대로 기록, pooling 금지 |
| ⑦ | Step B **1회**, 수용표 불변 | §8·§10. `GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0` |
| ⑧ | 두 로봇 odom vs GT 변위 오차는 **진단 전용** | §10.3. 평가 칸에만 기록, 제어 입력 아님 |
| ⑨ | 남쪽 드리프트/슬립은 **알려진 리스크** | §13. r2 원본에서 정량화 |

## 1. 조건 / provenance (r2와 동일, 변경 없음)

| 항목 | 값 |
|---|---|
| 장면 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c572324…c39bed` (light_scale 0.30) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e…a41b` |
| 시나리오/seed | `s7_pair_with_solo_v7`, seed 601, 2 robots r1·r2, nav-only(r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, …)` yaw 0, r2 `(−0.8982, −2.875, …)` yaw 0 |
| 목적지 (eval-only) | zone B center `(4.6, −2.1)`, half `(0.3, 0.7)` → 서쪽 경계 **x=4.3** |
| 카메라 | 자기 `r1__robot_cam` 640×480, gamma 1.0, JPEG q82, 10 Hz, fovy 48° + 측정 fisheye remap |
| 통신/예산 | `peer_en`, SIM 60 s (600 tick, localization rows 1202, commands 1200) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60; forward `0.004024203361827748` m/pct-s, yaw `1.7275488814064257` deg/pct-s). `calibration_source_sha=d182b67…` ≠ 실행 SHA → queue에 mismatch 명시(장면 `changes_physics=False`) |
| gate band | `gpu_calib_v230` (H 110–114 OpenCV, S≥100, V 30–230, min component 600), bearing `positive_left` |
| C (r2 승인, 그대로) | `acquire_min_height_norm=0.02`, `acquire_confirm_ticks=3`, `forward_reacquire=true`, 전진 상한 2.4 m |
| 금지 입력 | static map(제어), cargo, top camera, GT 좌표/접촉/성공 판정. 판단은 자기 RGB·자기 명령·통신만 |

## 2. r2 Step B = FAIL (기록·제외)

| 항목 | r2 값 (원본 `…/nav-gate/v230-r2/stepB-20261019T1755Z/`) |
|---|---|
| source SHA | `d2e10e7e9…` (VALID: queue/result/RUN_META/VM HEAD 일치) |
| status / SIM | `NAV_ARRIVAL_UNVERIFIED` (조기 종료) / 41.5 s |
| **판정** | **FAIL** — GT 1/2, claim 2/2, mismatch 1, FP 1, 경계 0 |
| r1 | armed 36.0 s GT `(3.9723,−2.2475)` → claim 41.0 s GT `(4.3705,−2.5023)` (zone 안) |
| r2 | armed 37.5 s GT `(3.9142,−2.3328)` → claim 41.5 s GT `(4.2056,−2.5189)` (**서쪽 경계 −0.094 m 밖**) |
| 원인 | claim은 **경로길이**(odom), 도착은 **위치**. r1은 경로 0.528 m 중 GT 0.479 m(90.7 %)/x 진행 0.398 m, r2는 경로 0.521 m 중 GT **0.349 m(66.9 %)**/x 진행 0.291 m. 슬립·선회로 적산이 과대 |
| 조치 | 이 run은 **r3 결과표에 넣지 않는다**. 같은 조건 재실행 없음(1회 규칙). r2 코드·prereg는 재생용 보존 |

r3의 변경은 r2 FAIL의 직접 원인(경로길이 vs 위치)만 없앤다. 접촉 latch·arming 임계 0.96·
2.4 m 전진·C gate·장면·예산은 r2와 **동일**하다. 결과 pooling 없음.

## 3. claim 정의 (r3)

### 3.1 식과 입력 출처

```
d_proj = (p_odom(t) − p_odom(t_armed)) · u(t_armed)  ≥ 0.52 m
```

| 기호 | 정의 | 입력 출처 |
|---|---|---|
| `t_armed` | 하단 접촉 latch 시각 | **자기 RGB** 검출의 `bottom_norm ≥ 0.96`(=`ARRIVAL_BOTTOM_CONTACT_NORM`, r2와 동일) + C gate(높이 0.02, 3틱)를 통과한 **수용 검출**에서 1회 latch |
| `p_odom(t)` | 자기 오도메트리 2D 자세 `(x, y, yaw)`. 첫 발행 명령 전 `(0,0,0)` | **자기 발행 명령**(35 % × pulse 폭)과 **주입된 percent-second 캘리브레이션**. midpoint 적분 `x += d·cos(yaw+Δyaw/2)`, `y += d·sin(yaw+Δyaw/2)` (r3 코드 `_integrate_projection_step`) |
| `u(t_armed)` | armed 시점 **자기 기억 bearing 방향** 단위벡터 (자기 오도메트리 프레임) | armed를 만든 수용 검출의 `bearing_deg`(positive_left, 120° HFOV 매핑)와 그 시점 `yaw_odom`: `u = wrap(yaw_odom + bearing)` |
| 0.52 m | claim 임계 | §3.2 |

- **세계 x축·지도(정적/동적)·GT·접촉 정답·top camera·시뮬레이터 상태를 쓰지 않는다.**
  `u`도 지도나 GT에서 오지 않고 자기 기억(검출 bearing)에서 온다. `p_odom`은 자기 명령 적산이다.
- 판정은 `d_proj ≥ 0.52`일 때만 claim한다. claim 시점의 `d_proj`·경로·방향·yaw 오차를
  per-tick report(`arrival_projection_m`, `arrival_path_m`, `arrival_u_deg`,
  `arrival_heading_error_deg`, `odom_pose`)에 남긴다.
- **실패 시나리오 구분**: `armed` 없음(접촉 미달) / `armed` 후 `NO_CLAIM`(§5) /
  claim 후 GT zone 밖(FP). 세 경우를 모두 원본에서 따로 센다.

### 3.2 0.52 m 불변 근거 (`experiments/2026-10-19-nav-v230-r2/B_A_DERIVATION.json`)

| 단계 | 값 |
|---|---:|
| 카메라 자세 | h 0.29983 m, pitch 18.9934°, x offset +0.0255 m (측정 fisheye + 지면 mount fit, RMS 0.049 m) |
| 접촉 행 (bottom_norm 0.96) | 460.8 / 480 |
| 그 행의 base 전방 지면거리(paint 근접 모서리) | **0.3649 m** |
| design margin (design parameter) | **0.15 m** |
| 유도값 | **0.5149 m** |
| **동결 flag 값** | **0.52 m** (상향 반올림, 실현 margin 0.155 m) |

- 코드 상수는 `ARRIVAL_ODOM_PROJECTION_M = ARRIVAL_ODOM_RESIDUAL_M = 0.52`이다.
  **r3에서 새로 맞춘 값이 아니며, 결과를 본 뒤 바꾸지 않는다.** 환경변수/CLI로 바꿀 수
  없게 두었다(숫자 flag 없음). 단위 시험이 `B_A_DERIVATION.json`의 `frozen_flag_value_m`과
  일치를 확인한다.

### 3.3 heading hold (기존 turn 제어기, 입력=yaw 오차)

- armed 이후 매 tick: `error = wrap(u − yaw_odom)`, `turn = clamp(error / 45°, −1, 1)`,
  `forward = 1.0`. `BEARING_FULL_DEG=45°`는 r2까지 쓰던 **기존** 비례 turn 이득이며 새 상수가 아니다.
- wheel 결선은 기존 `wheel_mix((forward, 0, turn))` → 35 % 진폭 + `|value|×0.1 s` pulse 폭.
  clamp 후 (left, right)를 계획에 되돌려 실제 발행과 일치시킨다(r2 코드와 같은 경로).
- **전진 속도는 r2와 동일**하다. r2의 appearance-only 추종은 `forward=1.0`(최대)이며,
  armed 후 r3도 같은 1.0을 쓴다. `ALIGN_GATE_DEG`(30°)는 armed 전 추종에만 적용되고
  armed 후 hold에는 적용하지 않는다(정지 대신 yaw 오차로 조향).
- 포화 시 실제 조향 한계: `|turn|`이 1에 가까우면 좌/우 wheel 폭 차가 최대가 되고
  캘리브레이션(yaw 1.7275 deg/pct-s)으로 tick당 약 **1.5°** yaw 변화다(단위 시험의 기준).
  40° 오차에서도 경로 0.545 m에서 projection 0.52 m에 도달함을 CPU 시험으로 확인했다(§6).

## 4. fail-safe (NO_CLAIM)

- armed 이후 **경로 길이** `path = Σ|d_odom|`를 적산한다.
- `path ≥ 1.0 m`이고 `d_proj < 0.52 m`이면: **claim하지 않는다.**
  - 계획은 `no_claim`(wheels 0)으로 정지하고, 이후 tick에서도 claim하지 않는다(latch).
  - per-tick report에 `arrival_no_claim=true`, `arrival_path_m`, `arrival_projection_m`을 남기고
    `nav-events.json`에 **`NO_CLAIM` 이벤트 1회**를 기록한다.
- `ARRIVAL_PROJECTION_PATH_CAP_M = 1.0` (지시값). 지시의 식 `0.52/0.5`는 정확히 **1.04 m**이며,
  1.0 m는 그보다 **작은(더 이른)** 상한이다. 즉 fail-safe는 지시보다 늦지 않다.
- `NO_CLAIM`은 성공도 실패 claim도 아니다. 발생하면 claim n/2가 줄어들므로 수용표는 FAIL이
  되고, 발생 시각·경로·투영·GT 위치를 그대로 보고한다.

## 5. 게이트 mode 결선 (동결, default OFF)

- `E2EWARP_NAV_GATE_MODE=v230_r3` (새 mode; 기본은 `v1_search`),
  `E2EWARP_NAV_ARRIVAL=odom_projection` (flag `--arrival-odom-projection`).
- queue marker(전부 필수, prepare/execute env와 일치해야 admit):
  `nav_gate_mode=v230_r3`, `nav_zone_profile=gpu_calib_v230`,
  `nav_acquisition=forward_then_search`, `nav_forward_cap_m=2.4`,
  `nav_zone_min_component=600`, `nav_bearing_convention=positive_left`,
  `nav_acquire_min_height_norm=0.02`, `nav_acquire_confirm_ticks=3`,
  `nav_forward_reacquire=true`, `nav_arrival_mode=odom_projection`,
  **`nav_arrival_odom_projection_m=0.52`**, **`nav_arrival_projection_path_cap_m=1.0`**.
- v230_r3는 `odom_projection`만 admit한다(flag 없으면 `NAV_ARRIVAL_REQUIRES_V230_R3`로 거부).
  `odom_projection`은 v230_r3 밖에서 거부된다. 0.52/1.0 marker가 queue와 코드 상수에서
  다르면 admit 거부.
- **v1/v230_fwd24/v230_r2 기본값·queue는 byte 불변**: r2 queue에는 projection marker를 쓰지
  않고, 기존 `--arrival-odom-residual`/`--arrival-ground-distance-m` 동작도 그대로다.
  신규 필드는 default off에서 claim/주행에 영향이 없음을 단위 시험으로 확인한다.

## 6. CPU 시험 (Step B 전, 실패 0)

`tests/test_e2ewarp_nav_v230_r3.py` (17개) + 기존 nav 시험:

| 시험 | 확인 |
|---|---|
| projection claim | 0.52 m에서 claim, 36 tick(0.5071 m) 미claim·37 tick(0.5211 m) claim, claim 시 `projection=path`(정렬) |
| 정의 구분 | bearing 40°에서 claim은 **projection 0.52**에서, 그때 `path 0.545 > projection` (경로 정의와 다름) |
| heading hold | 첫 tick 좌조향(우 wheel 폭 > 좌), yaw 오차 30→20 tick에 단조 감소, 30 tick에 \|오차\|<6°, 최종 <3° |
| NO_CLAIM | 1.0 m 경로에서 정지·wheels 0·claim 0, `arrival_no_claim` 1회 이벤트 |
| cap 불변 | `1.0 ≤ 0.52/0.5 = 1.04` (더 이른 상한), 임계=0.52=B_A `frozen_flag_value_m` |
| default off | 생성자 기본 `bottom_band`, v1/fwd24/r2 queue에 projection marker 0, flag 배타·환경 결선 |

전체 관련 시험 **165 passed** (nav/selfnav/gate/mode/r2/r3/fwd24 + e2e_warp + calib-signed).

## 7. FP 사전 gate ② (Step B 전, 새 SHA 재렌더)

- 고정 자세 5개(r1): `wall_south (1.8,−90°)`, `wall_north (1.8,+90°)`, `pickup_west (−1.4,180°)`,
  `pickup_rear (spawn,180°)`, `lane_west (1.5,180°)` × tick 0·5 = **10프레임**.
- 검출기는 게이트와 같은 `GpuCalibZoneDetector(profile='gpu_calib_v230',
  bearing_convention='positive_left')`. 렌더는 계약 v1 게이트 장면(r1/r2, cargo 0,
  light_scale 0.30)을 그대로 만들고 controller·LLM·GT·평가 입력은 없다.
- **판정: 검출 0/10 ∧ 최대 4-연결성분 < 600 px.** 한 프레임이라도 실패하면 **Step B를
  중단**하고 렌더 증거·수치를 그대로 보고한다(재시도·우회 없음).
- ③ 2.4 m 경로 기하 감사는 참고 기록이며 중단 조건이 아니다(지시의 중단 조건은 ② FP).
- 스크립트: `experiments/2026-10-19-nav-v230-r3/render_check.py` (이 SHA에서 실행).

## 8. Step B 절차 (1회)

1. push SHA clean clone(gcp6), VM HEAD 일치·`git status --porcelain` 0줄.
2. lease **1개**(`/home/ugrp/ugrp-sim/leases/e2ewarp.json`, name `e2ewarp-nav-v230-r3`),
   host receipt에 `idle_minutes=20`, `budget_stop=true`, `wall_cap=null`,
   `credentials_on_vm=false`. relay는 Oracle loopback, VM에 키 없음.
3. manifest → prepare(`E2EWARP_NAV_GATE_MODE=v230_r3`, `E2EWARP_NAV_ARRIVAL=odom_projection`)
   → execute(`--mode nav --seed 601 --nworld 1 --condition peer_en --nav-sim-budget-s 60`,
   `--expected-source-sha <SHA>`) → `scripts.e2ewarp_nav_recount` →
   `experiments/2026-10-19-nav-v230-r3/nav_v230_r3_analysis.py`(원본 재계수).
4. Step B는 **새 run 1회만** 센다. 재실행·중단 후 재개 금지. admit/ABI 오류는 우회 없이 기록.
5. r2/45 s dev/decay/fwd24/v1과 **pooling 금지**. r2 source와 같은 장면이어도 조건이 다르다.

## 9. VALID (아니면 결과표 제외)

| 항목 | 요구 |
|---|---|
| source/pin | admission queue·run queue·RUN_META·result `source_sha` == push SHA == VM HEAD, clean |
| 장면·예산 | `s7_pair_with_solo_v7`, `zone_wide_two_doors_final_v3`, spawn y −2.375/−2.875, r1·r2, budget 60.0, static_map false, cargo false |
| mode binding | §5 marker 전부, prepare/execute env 일치(admission == run queue) |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20, **source mismatch 명시** |
| ticks/rows | 60 s면 ticks 601, localization rows 1202, commands rows 1200 (조기 arrival 종료는 그 시점 값으로 기록하고 60 s 기대치를 주장하지 않는다) |
| 경계 감사 | `held_world_reads=0`, `top_camera_control=false`, `static_map_input=false`, `gpu_noslip_iterations=0`, `cpu_physics_steps=0` |
| status | `cap_end`(60 s) 또는 arrival 조기 종료. **`cap_end`는 성공이 아니다.** |

## 10. PASS / FAIL (VALID에만)

```
PASS ⇔ VALID
      ∧ GT 도착 2/2            (zone B center (4.6,−2.1), half (0.3,0.7), eval-only 재계수)
      ∧ claim 2/2 ∧ claim_mismatch 0
      ∧ FP 0                   (§10.1)
      ∧ 경계 위반 0            (§9 경계 감사 전부 통과)
```

### 10.1 FP 0

**① §7의 ② zone-없는 프레임 오검출 0/10 ∧ ② GT zone 밖 claim 0건.** 둘 다 필요하다.

### 10.2 claim 정의·NO_CLAIM 기록 (보고 필드)

- claim 시점 `arrival_projection_m ≥ 0.52`(원본 재계수), 그 시점 `arrival_path_m`,
  `arrival_u_deg`, `arrival_heading_error_deg`, `odom_pose`.
- `NO_CLAIM` 분포: 로봇별 발생 여부·시각·경로·투영(0/2 ~ 2/2).
- detection n/1202(목적지 memory 존재 tick)과 fresh detection n/1202, 첫 검출 tick·위치,
  `drive_reason` 분포, `forward_used_m`, armed/claim 시각.
- wheel n/1200(비영 wheel 발행 row/전체 command row).
- claim 시점·최종 GT 위치, 서쪽 경계 여유, 남쪽(y) 드리프트.

### 10.3 진단 전용 (수용표에 쓰지 않는다)

- armed→claim 구간의 **GT 변위 vs odom 변위**(dx, dy, norm, path, odom/GT 비율)와
  GT 변위의 u방향 투영. 두 로봇의 GT 헤딩은 직접 읽지 않고 spawn yaw 0 기준 세계 좌표
  변위로만 비교한다.
- 이 값은 원인 분석용이며 claim/판정 로직에 들어가지 않는다. GT는 평가 칸에만 둔다.

## 11. 금지 / 중단

- 금지: 0.52/1.0 재조정(결과 본 뒤), v1/r2 기본값 변경, 밴드·문턱·spawn·map·door·C 상수 변경,
  다른 조건과 pooling, 45 s dev/r2를 결과로 쓰기, Step B 2회, admit 우회, VM에 키 배치,
  다른 워커 프로세스/lease kill, 원본 덮어쓰기.
- 중단·보고: CPU 시험 실패, push 실패, ② FP 0 위반, admit/ABI 오류, relay 429/잔액,
  120분 초과, gcp6 stockout/start 실패. 중단 시 증거 보존 → lease 삭제 →
  프로세스 0/GPU 0 → stop → TERMINATED 확인.

## 12. 증거 경로

- 코드: `harness/e2ewarp_selfnav.py`(`ARRIVAL_ODOM_PROJECTION`), `harness/e2ewarp_nav_gate.py`
  (`GATE_MODE_V230_R3`), `scripts/run_e2e_warp.py`(`--arrival-odom-projection`)
- 시험: `tests/test_e2ewarp_nav_v230_r3.py`
- 사전 렌더: VM `runs/nav-v230-r3-render-<TS>/measure.json` + 프레임, Oracle
  `outputs/e2e18-admin/nav-gate/v230-r3/render-<TS>/`
- Step B: VM `runs/e2ewarp-nav-v230-r3-{admission,run}/`, Oracle
  `outputs/e2e18-admin/nav-gate/v230-r3/stepB-<TS>/`, 보고서
  `outputs/reports/2026-10-19-nav-stepB-v230-r3-dsh-<TS>.md`
- 분석 스크립트: `experiments/2026-10-19-nav-v230-r3/nav_v230_r3_analysis.py`

## 13. 리스크 (사전 명시)

1. **sim 전용**(`domain=sim`), n=1, seed 601, 단일 장면, r2와 **별도 조건**. 일반화 주장 아님.
2. **자기 오도메트리 과대 적산(최대 리스크).** r2 원본에서 r2 로봇은 경로 0.521 m에 GT 경로
   0.349 m(66.9 %), x 진행 0.291 m(55.9 %)였다. heading hold가 GT 진행을 u방향으로 정렬해도
   같은 비율이 유지되면 0.52 m 투영 claim의 GT 진행은 약 0.35 m가 되어, r2와 같은 arming
   지점(x 3.9142)에서 x≈4.26으로 **서쪽 경계(4.3)에서 0.04 m 밖**에 설 수 있다. r1은 같은
   비율(90.7 %)이면 x≈4.44로 안쪽이다. **이 리스크는 상수 변경(0.52↑)으로 대응하지 않는다** —
   지시대로 0.52를 유지하고 결과를 그대로 보고한다.
3. **남쪽 드리프트.** r2 원본의 armed→claim y 변화는 r1 −0.255 m, r2 −0.186 m였고 두 레인이
   한 줄로 수렴했다. r3의 heading hold는 armed 시점 bearing(r2 기억 bearing r1 +1.6…+29.4°,
   r2 −5.5…−10.2°)을 유지하므로 남쪽 성분이 남을 수 있다. 조향 부호·차동 실현·슬립 중 어느
   것이 주 원인인지는 이 1회 run으로 분리하지 못할 수 있다(진단 기록만).
4. **접촉 latch 1틱 의존.** arming은 `bottom_norm ≥ 0.96` 수용 검출 1틱에서 선다. 검출 1틱
   누락·오검출이 arming 시각/방향을 바꾼다. C 3틱 gate는 추종 전환에만 걸린다.
5. **heading hold의 조향 한계.** 차동 포화 시 yaw 변화는 약 1.5°/tick이라 큰 초기 오차에서는
   경로 일부가 투영에 기여하지 않는다(CPU 시험: 40°에서 path 0.545 m에서 projection 0.52 m).
   1.0 m fail-safe가 그 손실을 흡수한다.
6. **calibration source mismatch**(`d182b67` ≠ 실행 SHA)는 계속 명시한다(`changes_physics=false`).
7. **정적 지도 금지**는 코드·queue·입력 감사로만 확인하며, 이 run은 top camera/GT를 제어에
   쓰지 않는다. GT는 `evaluation-state.npz`·eval-geometry에서 평가 칸으로만 읽는다.
8. **r2 FAIL은 excluded**: r2의 어떤 수치도 r3의 n/N에 더하지 않는다.
