# nav v230_fwd24 — preflight amendment 1 (2026-10-19, 실행 전)

**상태: Step B 실행 전 동결.** 이 문서는 `PREREG.md`(blob sha256
`44c98ef35e8bf7dbf122b346dc1439c06f64093ff7fa37ef115ad9718dfdf6a5`)를 **바꾸지 않고**,
②③ 사전 관문을 통과한 뒤 발견된 **코드 결함 1건과 그 수정**을 기록한다. 승인 조건
(밴드·2.4 m·수용표·금지·pooling 금지)은 그대로이며, 이 수정은 조건 변경이 아니라
"검출 즉시 추종"이 실제로 목적지 쪽으로 향하도록 하는 결함 수정이다.

## 1. ②③ 최초 판정 (source SHA `22f3e03a9c91105b3e5c9b87e102f60c7930e712`)

- ② zone 없는 프레임: r1 5자세 × 2tick = 10프레임. `gpu_calib_v230` detections **0/10**,
  최대 4-연결성분 **최대 1 px**(wall_south 0/0, wall_north 0/0, pickup_west 0/0,
  pickup_rear 0/0, lane_west 1/1). **PASS**.
- ③ 2.4 m 경로: 5자세(x −0.898/−0.3/0.3/0.9/1.5) × 2tick, r1·r2 동일 x. 벽/문틀 교차
  **0**, 레인 간격 0.338 m, 최소 장애물 여유 0.0343 m(spawn 뒤 west wall), wide door
  개구부 안 두 레인(여유 0.169 m), cargo body **0**, 입력 경계 0. **PASS**.
- 증거: VM `runs/nav-v230-fwd24-render-20261019T1429Z/` + tar sha256
  `2d64aaa6348275c30b4dba58c31587214162a4c93f2cd771ea84eb7ed0a8620a`,
  Oracle `outputs/e2e18-admin/nav-gate/v230-fwd24/render-20261019T1429Z/`.
- **Step B는 이 SHA에서 실행하지 않았다.**

## 2. 발견된 결함 — 검출 bearing 부호가 turn 부호와 반대

기존 `GpuCalibZoneDetector`의 `bearing_deg = (cx/(W−1) − 0.5) × hfov`는 **이미지 오른쪽을
양수**로 둔다. 그런데 `SelfCentricNavigation`의 `turn = bearing/45`와
`wheel_mix((forward, 0, turn))`은 **양수 turn = 좌회전(CCW)**이다.

측정 근거(모두 VM, source `22f3e03a`, MJWarp 렌더):

| 증거 | 값 | 의미 |
|---|---|---|
| calib artifact `rotation` | `turn_deg_signed r1 +120.893, r2 +120.957` (`+turn` 패턴) | `turn>0` → 월드 yaw **+120.9°**(CCW, 좌회전) |
| x=1.5, yaw 0 렌더 | zone bbox `[81,66,379,82]`, bbox 중심 230, bearing **−16.90°** | zone B(north)가 이미지 **왼쪽** |
| x=1.5, yaw **+5°** 렌더 | bbox `[135,65,440,80]`, 중심 287.5, bearing **−6.10°** | 좌회전하면 장면이 오른쪽으로 이동(정상, 비거울상) |
| x=1.5, yaw **−5°** 렌더 | bbox `[26,66,320,88]`, bearing **−27.61°** | 우회전하면 장면이 왼쪽으로 이동 |
| x=1.5, y(N) +0.3 m | bbox `[345,67,448,80]`, bearing **+14.37°** | 문 개구부가 로봇 남쪽 → 이미지 오른쪽 = south. 즉 **image-left = north** |

따라서 목적지가 왼쪽(north)에 있으면 검출 bearing은 음수인데, 이 음수로 turn을 만들면
**오른쪽(남쪽)으로 회전**해 목적지에서 멀어진다. v1 게이트·r5는 검출이 0/1202였으므로 이
부호는 실제로 작동한 적이 없고, v230 모드에서 처음 발화하면서 드러났다.

## 3. 수정 (default-off, v230 모드에만 적용)

- `harness/e2ewarp_selfnav.py`
  - `BEARING_POSITIVE_RIGHT='positive_right'`(legacy 기본), `BEARING_POSITIVE_LEFT='positive_left'` 추가.
  - `GpuCalibZoneDetector(..., bearing_convention=DEFAULT_BEARING_CONVENTION)`:
    `positive_left`에서만 offset 부호를 뒤집는다. 검출 밴드·min_component·bbox·bottom_norm은 불변.
- `harness/e2ewarp_nav_gate.py`
  - `GATE_MODES['v1_search'].bearing_convention='positive_right'` — **v1 기본·기존 조건 불변**.
  - `GATE_MODES['v230_fwd24'].bearing_convention='positive_left'` — 승인 모드만 수정.
  - queue에 `nav_bearing_convention`을 기록하고 prepare/execute에서 mode와 일치를 강제
    (`NAV_GATE_BEARING_CONVENTION_MISMATCH`).
- `experiments/2026-10-19-nav-v230-fwd24/render_check.py`: v230 측정도 `positive_left` 사용.
- 단위 시험: legacy 기본은 음수 bearing, `positive_left`는 같은 왼쪽 표적에 양수 bearing,
  그리고 양수 bearing이 실제로 좌회전 wheel 패턴을 내는지 확인. queue marker 불일치 거부.

**바꾸지 않은 것:** H 110–114 / S≥100 / V 30–230 / min_component 600, 2.4 m 상한,
spawn·map·scene·시나리오, 수용표(§5), pooling 금지, calibration 재사용과 그 mismatch 명시.

## 4. 재검증 (이 수정을 포함한 pushed SHA에서 다시 수행)

- 로컬 최소 suite: 실패 0 (보고서에 passed/skipped 수 기록).
- ②③: 수정 SHA clean clone에서 `render_check.py`를 **새 run dir**로 재실행하고,
  ② detections 0·최대성분 <600, ③ 교차 0·간격>0·cargo 0을 다시 확인한다.
  수치는 결과 보고서와 VM run의 `measure.json`에 기록한다.
- ②③ 재통과 전에는 Step B를 시작하지 않는다.

## 5. 판정에 미치는 영향

- 이 수정은 **성공 조건을 완화하지 않는다**. 오히려 추종 방향을 승인된 "검출 즉시 추종"의
  의미에 맞춘다. 수용표·분모·금지·no-pooling은 `PREREG.md` 그대로다.
- 수정 전 SHA(`22f3e03a`)의 ②③ 결과는 폐기하지 않고 사전 관문 증거로 보존하되,
  그 SHA에서는 Step B를 돌리지 않았다. Step B의 source SHA는 이 문서를 포함한
  최종 pushed SHA이며, queue/result/RUN_META/VM HEAD가 모두 그 값과 같아야 한다.
