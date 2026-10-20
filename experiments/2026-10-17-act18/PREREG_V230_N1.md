# nav v230-n1 PREREG — stage 1(문 통과) 전 스폰 레인 bearing ±10° 제한 · 2-robot 3시드 — 2026-10-20

**상태: 동결(FROZEN).** Claude 결정(`outputs/reports/claude-arch-parallel-20261019/c4-decision-20261020.md`
§3, 창민 위임 = 승인)과 상위 지시(N1 준비: 구현·prereg, GPU 실행 금지)를 그대로 동결한다.
이 문서는 **결과를 보기 전에** 커밋·push되며, 이 문서를 포함한 branch head SHA가
preregistration ID이자 세 run의 `source_sha`다. 결과를 본 뒤 seed·규칙·수용표를 바꾸지 않는다.

- 작성: 2026-10-20 (dsh worker, `dsh/nav-v230-r6-n1`)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-r6-n1`
- branch: `dsh/nav-v230-r6-n1` (새 브랜치, force 아님)
- base: `e11efbeb9` (= nav r5 결과 커밋; r5 PASS 기록 포함)
- 호스트(실행 시): **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`
- 도메인: **sim 전용**(`domain=sim`). 실기·실카메라 주장 아님.
- **이 커밋 시점에는 GPU 실행 0.** 구현·CPU 시험·prereg·push까지만 하고, 실행은 lead가
  오프피크(2026-10-20 16:30 UTC 이후)에 별도 워커로 띄운다.

## 0. 승인 조건 → 동결 내용

| # | N1 결정 (Claude §3 + 상위 지시) | 이 prereg의 동결 |
|---|---|---|
| ① | stage 1(문 통과, 지면 투영 기준) 동안 **자기 스폰 레인 bearing 목표를 ±10° 이내로 제한** | §3.1. `v230_n1`의 stage 1 = r5의 중심 조준 + own-odometry(스폰 레인) frame에서 목표 방위 `clamp(±10°)` |
| ② | **기존 stage 1 중심 조준 유지** | §3.1. stage 1 slot offset 0(성분 중심)은 r5 그대로; 새 상수는 제한 각 하나뿐 |
| ③ | **stage 2/claim(0.52/1.0) 그대로** | §3.2. stage 2 활성 조건(지면 투영 ≤1.5 m)·slot 25/75 %·±15° clamp·arming `u`=성분 중심·0.52 m·1.0 m 전부 불변 |
| ④ | seeds **601 + 새 seed 2개 이상**, 실행 전 고정, seed별 판정 | §4. **601·602·603**을 이 문서에서 먼저 고정. seed별로 VALID/수용표를 각각 판정 |
| ⑤ | 2 robots, `peer_en`, 60 s | §2. r1/r2, `peer_en`, SIM 60 s (600 tick) |
| ⑥ | 수용표 `GT 2/2 · claim 2/2 · mismatch 0 · FP 0 · 경계 0` **seed별** | §6. r5와 동일, seed마다 따로 |
| ⑦ | **최소 base 박스 분리 ≥0.10 m는 보고용 지표(수용 조건 아님)** | §7.3. 수치·시각·`at_or_above_0.10`만 기록; PASS/FAIL 계산에 넣지 않음 |
| ⑧ | 접촉은 **실패 원인** | §7.2. 접촉은 INVALID가 아님; 횟수·시각·geom 쌍을 실패 원인 칸에 기록 |
| ⑨ | r5/이전 run **pooling 금지** | §1.1·§6. r5의 어떤 수치도 N1 표에 더하지 않음; seed 간 합산·통합 성공률도 보고하지 않음 |
| ⑩ | 오프피크·단일 lease·시작 전 예상 wall | §4·§5·§8. 16:30 UTC 이후, lease 1개를 세 run 내내 유지, 시작 전 예상 wall 기록 |
| ⑪ | sim 전용, 원본 불변, 0.52/1.0/claim 변경 금지 | §2·§3·§9 |

## 1. 조건 / provenance (r5와 동일, 명시된 것만 다름)

| 항목 | 값 |
|---|---|
| 장면 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c572324…c39bed` (light_scale 0.30) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e…a41b` (제어 입력 아님) |
| 시나리오/seed | `s7_pair_with_solo_v7`, seeds **601·602·603**, nworld 1, nav-only(r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, 0.032355, 0)` yaw 0, r2 `(−0.8982, −2.875, 0.032355, 0)` yaw 0 |
| 목적지 (eval-only) | zone B center `(4.6, −2.1)`, half `(0.3, 0.7)` → 서쪽 경계 **x=4.3**, 남쪽 경계 y=−2.8 |
| 문 | door_wide x=2.2, y ∈ [−3.125, −2.125] (폭 1.0 m, 2레인, 레인 간격 0.50 m) |
| 카메라 | 자기 `r1__robot_cam` 640×480, gamma 1.0, JPEG q82, 10 Hz, fovy 48° + fisheye remap |
| 통신/예산 | `peer_en`, SIM 60 s (600 tick, 기대 rows 1202 / commands 1200 — 조기 arrival 종료 시 그 시점 값) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60; forward `0.004024203361827748` m/pct-s, yaw `1.7275488814064257` deg/pct-s; `source_sha=d182b67…` ≠ 실행 SHA → queue에 mismatch 명시, `changes_physics=false`) |
| gate band | `gpu_calib_v230` (H 110–114 OpenCV, S≥100, V 30–230, min component 600), bearing `positive_left` |
| C (r2 승인, 그대로) | `acquire_min_height_norm=0.02`, `acquire_confirm_ticks=3`, `forward_reacquire=true`, 전진 상한 2.4 m |
| 금지 입력 | static map(제어), cargo, top camera, GT 좌표/접촉/성공 판정. 판단은 자기 RGB·자기 명령·통신만 |

### 1.1 r5와의 관계 (pooling 금지)

r5 Step B는 PASS(`GT 2/2 · claim 2/2 · mismatch 0 · FP 0 · 경계 0`, seed 601, 1회)였다. N1은
r5를 재사용하거나 합산하지 않는다. r5의 어떤 수치(최소 중심 0.1770 m, base 박스 0.0457 m,
stage-2 활성 26.5/27.0 s 등)도 **N1의 판정·성공률·통계에 더하지 않는다.** r4/r3/r2 run도 같다.
N1의 모든 판정은 N1 원본 세 run에서만 재계산한다.

## 2. N1 변경 = stage 1 스폰 레인 bearing ±10°

### 2.1 stage 1 (문 통과 전): 중심 조준 + 레인 ±10° 제한

- N1은 r5의 stage 1과 **같은 목표(성분 bbox 중심, slot offset 0)**를 쓴다. 추가로, 목표 **방위**를
  로봇 자신의 **스폰 레인** 기준 ±10°로 제한한다.
- 스폰 레인 frame = **own-odometry frame**: x축은 첫 발행 명령 시점의 heading(저작 스폰 yaw 0).
  따라서 레인 기준 목표 방위는 `lane = wrap(centre_bearing + own_odom_yaw)`이고, 적용 방위는
  `applied = clamp(lane, −10°, +10°)`, 로봇 상대 조준은 `wrap(applied − own_odom_yaw)`다.
  이는 r3 claim의 `u`와 같은 frame 규약이며, **자기 발행 명령·주입 캘리브레이션만** 읽는다.
- **stage 1 종료 = r5의 stage-2 래치(문 통과, 지면 투영 ≤1.5 m)**. 즉 문을 지나 1.5 m 지면
  투영 지점까지 레인 제한이 유지되고, 그 래치가 열리는 순간 해제된다(1회 latch, 재닫힘 없음).
  "문 통과(지면 투영 기준)"는 이 래치와 같은 사건이다: r5 실측에서 활성 시점 GT x≈2.80
  (문 평면 2.2에서 0.60 m 뒤)이었다.
- **왜 10°인가**: 2026-10-20 사용자 승인 N1 값이다(설계값, r5 결과에 맞춘 값 아님). r5 원본
  진단(eval-only, pooling 아님)에서 stage 1의 레인 기준 추종 목표는 r1 16/198 tick,
  r2 **103/229 tick**이 10°를 넘었고 최대 +15.4°/+26.2°였다. r5는 두 로봇이 같은 성분 중심을
  조준해 문 앞에서 중심 0.1770 m/base 박스 0.0457 m까지 접근했다(접촉 0). N1은 그 큰 초기
  회전을 ±10°로 제한해 레인 이탈을 줄이는 것이 목적이다.
- **한계(정직하게 명시)**: 0.50 m 레인 간격에서 10°를 스폰~래치 약 3.5 m 동안 유지하면 이론상
  측방 약 0.62 m다. 즉 이 제한은 레인 분리를 **보장하지 않는다**. 보장이 아니라 "공유 성분을
  향한 큰 조향"을 없애는 제어 제한이다. 실제 분리는 §7.3 보고 지표로만 본다.

### 2.2 불변 (동결 시험)

- **stage 2**: 활성 조건(성분 bbox 하단 행의 지면 투영 ≤1.5 m, 1회 래치, fail-closed),
  조준점 25 %/75 %, 적용 offset `clamp(offset, −15°, +15°)` — r5 그대로.
  해제 후에는 레인 제한을 **적용하지 않는다**(r5 조준 그대로).
- **claim**: `ARRIVAL_ODOM_PROJECTION_M == 0.52`, `ARRIVAL_PROJECTION_PATH_CAP_M == 1.0`,
  arming `u` = 성분 중심 bearing. N1은 이 값·경로를 바꾸지 않는다.
- **C/band/cap/spawn/slot mapping**: r5와 동일(§1).
- **default OFF**: `SelfCentricNavigation(spawn_lane_limit_deg=None)` 기본값이면 r4/r5 코드
  경로·리포트 키가 **바이트 그대로** 같다(§3.4 시험). `v230_n1` mode만 이 값을 binding한다.

### 2.3 mode 결선 (동결, default OFF)

- `E2EWARP_NAV_GATE_MODE=v230_n1` (새 mode; 기본은 `v1_search`),
  `E2EWARP_NAV_ARRIVAL=odom_projection` (flag `--arrival-odom-projection`).
- queue marker(전부 필수, prepare/execute env와 일치해야 admit): r5의 전부
  (`nav_gate_mode=v230_n1`, `nav_zone_profile=gpu_calib_v230`,
  `nav_acquisition=forward_then_search`, `nav_forward_cap_m=2.4`,
  `nav_zone_min_component=600`, `nav_bearing_convention=positive_left`,
  `nav_acquire_min_height_norm=0.02`, `nav_acquire_confirm_ticks=3`,
  `nav_forward_reacquire=true`, `nav_arrival_mode=odom_projection`,
  `nav_arrival_odom_projection_m=0.52`, `nav_arrival_projection_path_cap_m=1.0`,
  `nav_slots={"r1":"left","r2":"right"}`, `nav_slot_stage2_ground_m=1.5`,
  `nav_slot_offset_limit_deg=15.0`)
  **+ `nav_spawn_lane_limit_deg=10.0`**.
- `v230_n1`은 `odom_projection`만 admit한다. lane marker는 **n1 queue에만** 존재해야 하며,
  r5/r4/v1/fwd24/r2/r3 queue에 있으면 거부한다(`NAV_SPAWN_LANE_LIMIT_REQUIRE_V230_N1`).
  n1 queue에서 lane marker가 없거나 값이 다르면 각각
  `NAV_SPAWN_LANE_LIMIT_REQUIRED`/`NAV_SPAWN_LANE_LIMIT_MISMATCH`로 거부한다.
- **r5는 동결**: `v230_r5` mode·queue·코드 경로는 이번 변경으로 바뀌지 않는다(§3.4).

### 2.4 구현·시험 (이 커밋에 동결)

| 파일 | sha256 (이 커밋) | 내용 |
|---|---|---|
| `harness/e2ewarp_selfnav.py` | `426487241143aa2736364c2ba69284303606248a93bf3158bfb5d66ce2e377f5` | `SPAWN_LANE_LIMIT_DEG=10.0`, `spawn_lane_limit_deg` 인자, `_drive_plan`의 stage-1 레인 clamp, n1 전용 진단 6필드 |
| `harness/e2ewarp_nav_gate.py` | `a5e7af9ab0b490dd51dc22bb67ee23a14bf9b0c2839271a46bee7d59d30654f0` | `GATE_MODE_V230_N1`, `SLOT_GATE_MODES`/`ACQUISITION_QUALITY_MODES`/`PROJECTION_GATE_MODES` 추가, factory·queue·validation binding |
| `scripts/run_e2e_warp.py` | `325ba62240fb3e60c1022e40d817d96e6349d605a9edece82ae366a6bb0f8521` | solo 진단 오류 문구에 n1 표기(동작 불변) |
| `tests/test_e2ewarp_nav_v230_n1.py` | `25b46efd423efb1221daf40e7d602b8f3db77e5a88e6e1a48225aa100988b2ec` | 13개: ±10° clamp(양/음), 레인 frame(요 drift 분리), stage 2 해제·±15° 유지, claim 37틱/0.5211 m 불변, default off 리포트 키 부재, fail-closed, gate marker/factory |
| `experiments/2026-10-20-nav-v230-n1/nav_v230_n1_analysis.py` | `964352d39a0b25be79eac96827b9eca1aaa759853961b639d1eb7765ac23bf78` | r5 분석 도구를 import해 수용표를 재계수하고 n1 레인 진단·base 박스 보고 지표·seed별 표를 더한다 |

- CPU 시험: **N1 13 + 기존 nav/e2e 193 = 206 passed**. r4/r5 시험 전부 통과.
- **r4/r5 byte-identical 확인(별도 스크립트, 커밋 밖 임시)**: base 커밋 `e11efbeb9`의
  `e2ewarp_selfnav.py`와 이 커밋의 파일에 같은 입력 7종(레인 내/밖, stage 1/2, slot left/right,
  r4 기본)을 넣어 (report, command) 쌍을 비교 → **완전 동일**, default 모드에서 n1 전용 키 0개.
  `v230_r5` queue fields·mode dict·validation도 base와 **바이트 동일**하고 lane marker가 없다.

## 3. Seeds와 nav-only 장면 (정직한 한계)

- 이 문서에서 **seed 601·602·603**을 실행 전에 고정한다. 실행 후 seed 변경·추가·제외 금지.
- **중요**: nav-only 장면은 cargo를 생성하지 않고, `pair_lane_spawns`가 r1/r2의 y를 레인
  (−2.375/−2.875)으로 덮어쓰며 x·z·yaw는 저작 상수다. CPU에서 세 seed의 `ScenarioFinalV3Scene`
  스폰을 직접 확인한 결과 **세 seed의 실행 스폰이 완전히 동일**했다
  (`601/602/603` 모두 r1 `(−0.8982,−2.375)`, r2 `(−0.8982,−2.875)`; r3은 prune).
  따라서 602·603은 **같은 조건의 반복 실행(repeatability)**이지 독립적인 장면 표본이 아니다.
  seed가 바꾸는 것은 `leader_id = robots[seed % 2]`(보고용 metadata; `peer_en`에서는 제어 입력으로
  쓰이지 않음)뿐이고, 스폰·물리·제어 상태는 세 seed가 동일하다.
- 그럼에도 세 run을 **seed별로 따로** 판정하는 이유: (a) 지시된 3-seed prereg를 그대로 지키고,
  (b) 같은 조건에서도 MJWarp 실행의 재현성(문 통과·claim·접촉·분리)을 seed별로 남기기 위해서다.
  **seed 간 pooling·통합 성공률은 보고하지 않는다.** "3/3" 같은 합산도 성공률 주장으로 쓰지 않고,
  각 seed의 PASS/FAIL만 표로 낸다.

## 4. 실행 절차 (오프피크·단일 lease)

### 4.1 시작 전 (GPU 0인 이 커밋에서는 하지 않음)

1. **예상 wall 먼저 기록**(§8): lease 생성 전에 아래 값을 runbook/report에 적는다.
2. gcp6 start → clone(이 branch head SHA) → `.venv-warp` 확인 → relay/lease 준비(r5와 동일 경로).
3. **사전 FP 재렌더(1회)**: `experiments/2026-10-19-nav-v230-r3/render_check.py`(파일 불변)를
   이 SHA clean clone에서 실행. 5자세 × tick 0·5 = **r1 10프레임**, 검출 0/10, 최대 4-연결성분
   <600 px이어야 `step_b_allowed=true`. 실패하면 **run을 시작하지 않고** 렌더 수치만 보고한다.
4. `scripts/e2ewarp_nav_manifest.py`로 component manifest 작성(factory hash-bound).

### 4.2 세 run (seed별 admission + run, 각 1회, 재실행 없음)

각 seed마다 **새 admission dir + 새 run dir**로 prepare → stack-check → execute:

```
E2EWARP_NAV_GATE_MODE=v230_n1 \
E2EWARP_NAV_ARRIVAL=odom_projection \
E2EWARP_NAV_CALIBRATION=<calib> \
python -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 \
  --output <run-root>/e2ewarp-nav-v230-n1-s<seed>-admission \
  --seed <seed> --nworld 1 --condition peer_en --nav-sim-budget-s 60 \
  --components <components.json> --arrival-odom-projection

python -m scripts.run_e2e_warp --mode nav --execute --e2e-warp-batch on_v1 \
  --output <run-root>/e2ewarp-nav-v230-n1-s<seed>-run \
  --queue <run-root>/e2ewarp-nav-v230-n1-s<seed>-admission/queue.json \
  --seed <seed> --nworld 1 --condition peer_en --nav-sim-budget-s 60 \
  --components <components.json> --arrival-odom-projection \
  --expected-source-sha <SHA> --host-receipt <receipt> --relay-url <loopback>
```

- seed 순서: **601 → 602 → 603**. prepare에서 `stack-check.json ok=True`(blocked 0) 확인 후에만
  execute한다. admission queue와 run queue의 marker가 같아야 한다.
- **단일 lease**: `runs/leases/e2ewarp.json` 하나를 첫 run 전에 만들고 세 run·분석·증거 회수
  동안 유지, 마지막에 삭제한다. run 사이에 lease를 갈아치우지 않는다.
- **오프피크**: 2026-10-20 16:30 UTC 이후에만 시작한다. 이 prereg 커밋 시점(04:48 UTC)은 피크다.
- run 후 원본 불변: 실행 디렉터리를 수정하지 않는다. 분석은 별도 output 경로에 쓴다.

### 4.3 분석 (run 종료 후, CPU)

```
python scripts/e2ewarp_nav_recount.py --run <run>           # raw eval-only 재계수 보조
python experiments/2026-10-20-nav-v230-n1/nav_v230_n1_analysis.py \
  --run <run> --admission <admission> --expected-source-sha <SHA> \
  --preflight-render <render>/measure.json --seed <seed> \
  --out <evidence>/nav-v230-n1-s<seed>-analysis.json
python experiments/2026-10-20-nav-v230-n1/nav_v230_n1_analysis.py \
  --table <s601-analysis.json> <s602-analysis.json> <s603-analysis.json> \
  --table-out <evidence>/nav-v230-n1-seed-table.json
```

- 수용표는 `nav_v230_n1_analysis.py`가 r5 도구(`nav_v230_r5_analysis.py`)를 import해 재계수한다
  (VALID·GT·claim·mismatch·FP·경계). n1 도구는 여기에 **레인 clamp 진단**과 **base 박스 분리
  보고 지표**만 더한다.
- seed 표는 `pooling=False`로 쓰고, seed별 verdict만 담는다.

## 5. 예상 wall (시작 전 확인용)

| 구간 | 예상 | 근거 |
|---|---|---|
| run 1회 | SIM 40 s면 **약 275 s**, 최악 60 s면 **약 412 s** (3.5–7 wall/SIM) | r5 pair 274.13 s / 39.9 SIM s = 6.87 wall/SIM, r5 solo 4.17 |
| prepare+stack 3회 | 약 60 s | r5 prepare 수준 |
| 사전 FP 재렌더 | 약 3–5 분 | r5 01:36Z boot → 01:40Z 렌더 |
| 증거 tar·mp4·회수 | 약 3–5 분 | r5 02:05Z 회수 |
| **총 예상** | **약 20–35 분** (VM boot·relay 포함) | |
| **중단 cap** | **60 분** | 넘으면 남은 run을 시작하지 않고 중단·보고 |

- 실제 wall/SIM이 6.0을 넘으면 기록 전용 경고로 남긴다(차단 아님). 6.0×1.5가 10분 지속되면
  경고 파일을 남긴다.

## 6. 수용표 (seed마다 따로)

```
PASS(seed) ⇔ VALID(seed)
           ∧ GT 도착 2/2        (최종 base가 zone B 사각형 안, eval-only 재계수)
           ∧ claim 2/2 ∧ claim_mismatch 0
           ∧ FP 0               (§6.1)
           ∧ 경계 위반 0        (§6.2)
```

- **seed별로만 판정**한다. 세 seed를 합산한 통과율·성공률을 만들지 않는다.
- `GT 도착`은 **최종** tick 기준. claim 시점 GT가 밖이었던 수는 별도 진단 칸
  (`claims_outside_gt_at_claim_time_n`)에 기록(수용표 계산에는 최종 GT 사용, r5와 동일).
- **접촉은 INVALID가 아니라 실패 원인**이다(§7.2). PASS여도 접촉이 있으면 "PASS(접촉 기록 있음)".
- `cap_end`(60 s 소진)는 성공이 아니다. status가 `cap_end` 또는 `NAV_ARRIVAL_UNVERIFIED`여야
  VALID이고, 둘 다 성공 주장이 아니다.

### 6.1 FP 0

**① zone 없는 프레임 오검출 0/10 (N1 SHA 재렌더) ∧ ② 최종 GT zone 밖 claim 0건.**
- ①은 §4.1의 사전 렌더 1회 결과다(세 seed 공통, SHA 단위). 실패하면 run을 시작하지 않는다.
- ②는 분석 도구의 `claim_mismatch_n`이다.

### 6.2 VALID (아니면 그 seed 결과표 제외)

| 항목 | 요구 |
|---|---|
| source/pin | admission queue·run queue·RUN_META·result `source_sha` == push SHA == VM HEAD, `git status --porcelain` 0줄 |
| 장면·예산 | `s7_pair_with_solo_v7`, `zone_wide_two_doors_final_v3`, §1 스폰/로봇 집합, budget 60.0, static_map false, cargo false |
| mode binding | §2.3 marker 전부(특히 `nav_gate_mode=v230_n1`, `nav_spawn_lane_limit_deg=10.0`), prepare/execute env 일치(admission == run queue) |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20, source mismatch 명시 |
| ticks/rows | 60 s 기대 ticks 601 / rows 1202 / commands 1200 (조기 arrival 종료는 그 시점 값으로 기록) |
| 경계 감사 | `held_world_reads=0`, `top_camera_control=false`, `static_map_input=false`, `gpu_noslip_iterations=0`, `cpu_physics_steps=0`, `cpu_render_calls=0` |
| status | `cap_end`(60 s) 또는 arrival 조기 종료(`NAV_ARRIVAL_UNVERIFIED`). **`cap_end`는 성공이 아니다.** |
| 접촉 | VALID 조건이 아니다(§7.2) |

## 7. 보고 지표 (판정과 분리)

### 7.1 run 기본
- seed별: status, SIM s, wall s, wall/SIM, source/pin, stack, 경계 감사, 검출 수(첫 검출 시각),
  전진 사용량, drive_reason 분포, 문 통과 시각(GT x>2.2), stage-2 활성 시각·투영 거리·활성 tick,
  arming 시각/`u`/bearing, claim 시각/`d_proj`/path/자세오차, claim·최종 GT(zone 안/밖, 여유),
  GT/명령 적산/odom 경로와 비율, yaw 오차(GT−odom) 최대·최종, LLM 호출 수·모델·비용.

### 7.2 접촉 (eval-only, 실패 원인)
- MJWarp 로봇-로봇 contact tick/pair/first/last.
- MJWarp 로봇-씬(비로봇 geom, floor 제외) contact tick/pair/geom·dist. `zone_wall_divider_1`/
  `zone_wall_south`는 문틀로 분류. **원본이 읽히지 않으면 `scene_contacts_available=false`와
  사유를 기록하고 0으로 보고하지 않는다.**
- 보조: authored map 사각형 대 로봇 footprint OBB 최소 분리(박스 전용; 양수≠무접촉 명시).
- 접촉이 있으면 그 횟수·시각·geom 쌍을 그 seed의 실패 원인 칸에 적는다.

### 7.3 로봇 간 거리 — **최소 base 박스 분리 ≥0.10 m는 보고용 지표**
- r4/r5와 같은 정의: GT base 중심거리 최소·시각, base 충돌 박스(`base_lower_collision`
  0.181×0.087 OBB) 최소 분리·시각, 중심거리 <0.181 m tick 수.
- 새 보고 칸: `min_base_box_separation_m`, `min_s`, `reference_m=0.10`,
  `at_or_above_0.10`(bool). **수용 조건 아님**: `acceptance.pass_` 계산에 들어가지 않으며,
  FAIL/PASS 판정과 무관하게 숫자 그대로 보고한다. 0.10 m 미만이어도 접촉이 없으면 PASS일 수 있고,
  그 사실을 표에 같이 적는다(예: r5는 0.0457 m였지만 접촉 0).

### 7.4 stage 1 레인 제한 진단
- 로봇별: `spawn_lane_limit_deg`(10.0), 활성 tick 수, 실제 clamp tick 수(raw≠applied),
  레인 frame 목표 raw/applied 최소·최대, 로봇 상대 조준 raw/applied 최소·최대,
  stage-2 활성 시각, **활성 이후 레인 제한 tick 수(0이어야 해제)**.
- 이는 진단이며 판정에 쓰지 않는다.

### 7.5 영상 (post-processing only)
- 실행 중 프레임 저장 주기·해상도·JPEG 품질·seed·timing·코드를 바꾸지 않는다.
- run이 저장한 `world-00/review-rgb/r{1,2}-NNNNNN.jpg`(2 Hz)만 사용해 run **종료 후** ffmpeg mux.
  대표 720p 1개(15 MB 이하)+full mp4. in-run 코드 변경 0을 보고에 적는다.

## 8. 중단·보고

- **중단 조건**: CPU 시험 실패(이 커밋에서 이미 통과: 206 passed), push 실패, 사전 렌더 FP 0
  위반, admit/ABI 오류, stack blocked, relay 429/잔액, gcp6 stockout/start 실패, **60분 cap**.
- admission 오류 run(예: 플래그 누락·lease 파일명 오류)은 **SIM 0 tick**으로 별도 기록하고
  수용표·n/N에 넣지 않는다(r5와 같은 처리). 실행 source는 바꾸지 않는다.
- **run은 seed별 1회.** 재실행·중단 후 재개 금지. 실패도 숫자 그대로 보고한다.
- 중단 시 증거 보존 → lease 삭제 → 프로세스 0/GPU 0 확인 → stop → `describe` TERMINATED 확인.
  gcp6 start/stockout 실패는 반복 루프 없이 원인만 보고한다.

## 9. 증거 경로

- 코드: `harness/e2ewarp_selfnav.py`(§2.4), `harness/e2ewarp_nav_gate.py`, `scripts/run_e2e_warp.py`
- 시험: `tests/test_e2ewarp_nav_v230_n1.py`
- 분석: `experiments/2026-10-20-nav-v230-n1/nav_v230_n1_analysis.py`
- 사전 렌더: VM `runs/nav-v230-n1-render-<TS>/`, Oracle `outputs/e2e18-admin/nav-gate/v230-n1/render-<TS>/`
- run: VM `runs/e2ewarp-nav-v230-n1-s{601,602,603}-{admission,run}/`,
  Oracle `outputs/e2e18-admin/nav-gate/v230-n1/stepB-<TS>/`
- 분석 JSON: `…/nav-v230-n1-s<seed>-analysis.json`, seed 표 `…/nav-v230-n1-seed-table.json`
- 보고서: `outputs/reports/2026-10-20-nav-v230-n1-dsh-<TS>.md`
- 실험 요약: `experiments/2026-10-20-nav-v230-n1/summary.json`, `README.md`

## 10. 리스크 (사전 명시)

1. **sim 전용**, seed 3개지만 §3대로 **독립 표본이 아님**(같은 스폰·cargo 없음). 일반화 주장 아님.
2. **레인 제한은 분리를 보장하지 않는다**: 10° 유지 시 이론 측방 0.62 m. 문 앞 근접이 남을 수
   있고, 그 경우에도 §7.3 수치를 그대로 보고한다(접촉은 실패 원인).
3. **조향 제한이 검출·문 통과를 바꿀 수 있다**: stage 1에서 덜 돌기 때문에 보이는 성분 조각이
   달라져 stage-2 활성 시각이 이동할 수 있다. 활성 조건·1.5 m·slot은 불변이므로 새 튜닝은 없다.
4. **레인 frame은 own-odometry yaw**다. r5 solo에서 yaw 오차 최대 7.7°가 관측됐다. 오차가 크면
   레인 기준 자체가 흔들리며, 그 수치는 §7.4에 기록한다.
5. **r2의 r5 yaw 오차 15.6°**는 stage 2 회전 구간에서 시작됐다. N1은 stage 2를 바꾸지 않으므로
   같은 계열의 오차가 남을 수 있다(이번 수정 범위 아님).
6. **접촉 계수**: scene 채널이 unavailable이면 0으로 보고하지 않고 사유를 기록한다. authored-map
   보조는 박스 전용이라 양수≠무접촉이다.
7. **calibration source mismatch**(`d182b67` ≠ 실행 SHA)는 계속 명시한다(`changes_physics=false`).
8. `RUN_META.class=dev`는 러너 하드코딩 값이다(prereg 등급은 study).
9. **결과 후 재조정 금지**: 10°·1.5 m·±15°·0.52/1.0·seed를 결과를 보고 바꾸지 않는다.
10. **세 seed가 같은 조건**이므로, 세 verdict가 모두 같아도 그것은 독립 재현 3회가 아니라
    같은 조건의 반복 3회다. 표에 그대로 적는다.

## 11. 결과 전 커밋

- 이 문서와 §2.4 코드·시험·분석 도구를 **한 커밋**으로 `dsh/nav-v230-r6-n1`에 push한다.
  push SHA가 세 run의 `source_sha`이며, 실행 전에 push되어 있어야 한다.
- 이 커밋 시점 GPU 실행 0. 실행은 lead가 오프피크(16:30 UTC 이후)에 별도 워커로 띄운다.
- 결과가 나오면 이 문서의 seed·규칙·수용표를 바꾸지 않고, 결과는 별도 보고서에만 쓴다.
