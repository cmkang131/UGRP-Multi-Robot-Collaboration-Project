# nav gate 1 — 목적지 검출기 색 보정 prereg (2026-10-18)

**상태: 오프라인 측정 완료, 물리/GPU 실행 없음.** 이 문서는 gate 1(FAIL: acquisition)
후속으로 검출기 단위·집계·도착 가드를 고치기 전에, 기존 프레임만으로 잰
바닥 vs zone B 색 분포와 문턱 판정을 **사전 등록**한다. 연구 결과가 아니며
R1–R4·visgoal·어떤 research result와도 합산하지 않는다.

측정 원본: `detector-calib.json` (이 디렉토리). 재현:
`/home/ubuntu/ugrp-venv/bin/python scripts/e2ewarp_nav_detector_calib.py ...`
(§11).

## 0. 결론 (5줄)

1. `gpu_calib_v1`의 hue 110–114는 **OpenCV 단위(H 0–180)**다. 도(degree)로
   비교하던 코드는 이 장면에서 0검출이었다(원인 a).
2. 실측 **바닥 H 107–108 / zone B H 110–114** (OpenCV, p5–p95). 중앙값 차이는
   4단위, 문턱 여유는 **2단위**뿐이다.
3. 픽셀 단위로는 완전 분리가 안 된다(바닥 0.02%가 밴드 안, zone 10.7%가 밴드
   밖). 그러나 **최대 연결요소 ≥600 px**로 집계하면 현재 밴드에서
   **zone 30/30, 바닥 0/2**로 분리된다. 밴드를 108–116으로 넓히면 바닥이
   104,907 px 한 덩어리로 들어와 **바닥 2/2 오검출**이 된다.
4. 따라서 문턱은 **현재 110–114 유지**가 맞고, 바닥 도색 변경은 지금 하지
   않는다(§8). 2단위 여유는 얇으므로 nav-gate 장면 자체의 zone B 프레임으로
   재확인이 필요하다(§9, GPU).
5. **검출기 수정만으로는 gate가 출발하지 않는다.** 스폰 프레임의 in-band
   1,583 px는 최대 성분 381 px로 <600이고, 문틈 방향 최대 성분도 91 px다.
   수정 후 스폰은 정상적으로 `no_destination`·wheel 0 → **탐색 정책이 다음
   선행 조건**이다(§6).

## 1. 단위 (명시)

- 프로필 `gpu_calib_v1`: OpenCV HSV, **H 0–180, S 0–255, V 0–255**.
  hue 110–114 OpenCV == **220–228 도**.
- 코드의 `rgb_to_hsv()`는 도(0–360)를 반환하므로 검출기에서
  `hue_degrees_to_opencv(h) = h / 2.0`로 변환한 뒤 비교한다.
  이 변환이 유일한 허용 경로다(단위 혼용이 gate 1 원인 a).
- 측정 스크립트도 `cv2.COLOR_*2HSV`(OpenCV 단위)만 사용한다.

## 2. 입력과 증거 (n/N, SHA)

| 입력 | n | 용도 | SHA256 |
|---|---:|---|---|
| zonecal GPU 캡처 zone_B 프레임 | **30 / 36** (6개는 zoneA/pickup neg, 미사용) | zone B 색 | `frames.json` `a41c5e1e…`; 30 JPEG 모두 `SHA256SUMS.json` 대조 통과 |
| nav-gate 물리 실행 스폰 프레임 `r1-tick5.jpg` | 1 | 바닥 색 | `4e921717dbcc05c1b2c2caeabf97d39bd9ae2cf354a0e863eb5e48b160860ab9` |
| `r1-tick600.jpg` (같은 실행, 스폰 정지) | 1 | 바닥 색(반복) | `9cc95ab2f78d1c240097faf2d92b29371cb771286ff9ce0e5342089d06e6956f` |

- zonecal 출처: `experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu`
  (branch `dsh/e2ewarp-components-v1`, commit `b894d8cb1`;
  render source SHA `718777118be41991156b047faff78621969101bb`).
  "GPU appearance calibration, not research result" 라벨 유지.
- zone B 라벨은 캡처의 eval-only `actual_camera_pose`로 만든 floor-ray
  마스크(zone rect x 4.30–4.90, y −2.80–−1.40)다. **정답 라벨은 채점에만**
  쓰고 검출기 입력으로 쓰지 않는다.
- 바닥 ROI(행, 열): `floor_pickup_blue` (150–330, 100–500),
  `floor_pickup_blue_low` (330–380, 150–480). 픽업 구역 바닥 오버레이 위이며
  ROI 좌표는 `detector-calib.json`에 그대로 남는다.
- 두 스폰 프레임은 사실상 같은 정지 자세다(로봇 이동 0.0039 m). 따라서
  **바닥은 1개 자세**로 본 것과 같다.

## 3. 측정 (OpenCV 단위, 픽셀 분포)

### 3.1 zone B — 30프레임, pooled 561,155 px

| 채널 | p5 | p50 | p95 | 비고 |
|---|---:|---:|---:|---|
| H (OpenCV) | 110 | **112** | 114 | 프레임별 중앙값 112–113; 2.98 m 프레임만 p5 108 |
| S | 46 | **202** | 212 | p5는 가장자리 혼합 픽셀; 페인트 코어 ≈200 |
| V | 72 | **85** | 91 | 거리 0.45 m에서 82, 1.6 m에서 87 |

거리 0.45–2.98 m 전 구간 pooled 픽셀의 in-band 비율 89.3%, 프레임별 최대
연결요소 최소 **1,399 px** (2.98 m). 30/30 프레임이 ≥600 px.

### 3.2 바닥(픽업 구역 오버레이) — 2프레임, 144,000 px

| 채널 | p5 | p50 | p95 | min–max |
|---|---:|---:|---:|---|
| H (OpenCV) | 107 | **108** | 108 | 106–111 |
| S | 208 | **212** | 215 | 200–219 |
| V | 87 | **90** | 95 | 81–100 |

### 3.3 겹침

- 현재 밴드(110–114, S≥100, 30≤V≤110) 안에 드는 픽셀 비율:
  - zone B: **89.32%**
  - 바닥: **0.02%** (2프레임 144,000 px 중 29 px 수준)
- 픽셀 단위 겹침은 0이 아니다. 그러나 바닥의 in-band 픽셀은 **흩어진
  경계/JPEG 잡음**이고, 프레임 전체에서 최대 연결요소가 **381 px**다
  (전체 in-band 1,583 px, 성분 106개).
- S는 역방향이다(바닥 212 > zone 202). S 문턱으로는 분리되지 않는다.
- V도 겹친다(바닥 90, zone 85; zone p95 91). V 문턱으로는 분리되지 않는다.

## 4. 문턱 후보 평가 (최대 연결요소 ≥600 px)

| 밴드 | zone 검출 | 바닥 검출 | 바닥 최대성분 | 판정 |
|---|---:|---:|---:|---|
| **110–114 / S≥100 / 30≤V≤110 (현행)** | **30/30** | **0/2** | 381 | **채택** |
| 109–115 / S≥100 | 30/30 | 0/2 | 497 | 여유 더 얇음, 미채택 |
| 108–116 / S≥100 | 30/30 | **2/2** | 104,907 | 명백한 오검출, 금지 |
| 110–114 / S≥140 | 30/30 | 0/2 | 252 | S 여유는 늘지만 zone 코어 일부 손실, 미채택 |

## 5. 판정: 문턱 하나로 분리되는가

- **픽셀 단위로는 아니다.** 바닥 0.02%가 밴드 안, zone 10.7%가 밴드 밖이다.
- **최대 연결요소 + ≥600 px로는 이 프레임들에서 분리된다.** 근거는
  바닥 최대성분 381 px vs zone 최소성분 1,399 px, 사이에 600 문턱.
- 단, 여유는 **hue 2단위(108→110)**이고, H 108–116으로 넓히면 즉시
  오검출된다. 문턱을 "넉넉하게" 넓히는 변경은 금지한다.
- 이 결론은 **다른 장면(R4)의 zone B + nav-gate 스폰 바닥 1자세** 조합이다.
  nav-gate 장면의 zone B 외관을 직접 잰 것이 아니므로 "증명"이 아니라
  "현재 증거로 채택 가능한 최소 변경"이다.

## 6. 스폰 가시성: 수정 후에도 게이트는 출발하지 않는다

`r1-tick5.jpg` 실측:

- in-band 전체 **1,583 px** (성분 106개) — **예전 `mask.sum()` 코드는 600을
  넘겨 발화했다** (단위만 고쳤다면 여기서 오검출).
- 최대 연결요소 **381 px** <600 → 수정 검출기 **0검출**.
- 문틈 방향(y≈47–51) 최대 성분도 **91 px**. 스폰에서 zone B는 600 px에
  한참 못 미친다.
- 따라서 수정 후 스폰은 `drive_reason=no_destination`, wheel 0이 정상이다.
  gate 1을 다시 돌려도 **탐색(회전/전진 스캔) 정책이 없으면 출발하지 않는다.**
  검출기 수정은 "바닥 오검출로 직진"을 막는 것이지, 획득을 해결하는 것이 아니다.

## 7. 도착 가드 (계약 v1 문턱은 유지, 가드만 추가)

도착은 이제 다음을 **모두** 만족할 때만 성립한다(코드:
`_arrival_evidence`):

1. 마지막 관측 후 **≤1.0 s** (오검출 1회가 125 s 기억으로 도착 주장이 되던
   fail-open 차단)
2. `bottom_norm ≥ 0.98` (기존 계약값 유지)
3. 최대 연결요소의 `height_norm 0.04–0.65`, `area_norm ≤0.65`,
   `solidity ≥0.45`, 화면 중앙 열 포함, 상단 경계 미접촉
4. 또는 측정 range ≤ `arrival_range_m` (기존 경로 유지)

가드의 근거와 한계:

- 실측 바닥 덩어리(밴드를 108–116으로 넓혔을 때)는 height 0.677,
  solidity 0.59 → **height 한 기준에서 거부**된다(면적·solidity는 통과).
  여유는 height 0.027로 얇고, solidity는 이 fill을 거르지 못한다.
- 이 가드는 **색이 동일한 바닥 fill과 아주 가까운 zone patch를 구분하지
  못한다**. 그 구분은 오직 색 밴드가 담당한다. 밴드를 넓히면 가드도 무력하다.
- zonecal 조준 자세(servo 6=1000)에서 0.45 m일 때 `bottom_norm=0.967`로
  0.98에 못 미쳤다. nav 컨트롤러는 SEARCH(servo 6=1500)를 쓰므로 이 값은
  **전이되지 않는다**. nav SEARCH 자세의 zone 접근 프레임이 아직 없어
  0.98 도달 가능성은 **미검증**이다. 다음 캡처에서 실측 필요(§9).

## 8. 바닥 도색 변경 여부 (사용자 승인 범위)

- 창민 승인(2026-10-18): 색 분포가 겹쳐 문턱으로 안 되면 scene_profile/바닥
  도색 변경 허용, 변경값·측정 근거 기록.
- **이번 PR에서는 변경하지 않는다.** 현재 증거로는 문턱(110–114) + 최대
  연결요소가 30/30 vs 0/2로 분리되고, 오염원은 scene_profile의 벽색이 아니라
  `zone_wide_two_doors_final_v3`의 **pickup region 오버레이**(rgba .12 .36 .70 .14)다.
  이 맵은 R4·기타 실험과 공유되므로 바꾸면 기존 결과의 조건이 달라진다.
- 변경 트리거(다음 캡처에서 확인): nav-gate 장면 zone B 프레임에서 바닥
  성분이 밴드 안에서 ≥600 px로 뭉치거나, zone B가 600 px를 넘지 못해
  탐색으로도 획득이 안 될 때. 그때는 nav-gate 전용 맵/프로필에서 pickup
  오버레이 색(또는 alpha)을 바꾸고 새 map_id로 재검증한다.

## 9. 아직 없는 프레임 / GPU 필요

1. **nav-gate 장면의 zone B 접근 프레임** (최우선): gcp6 render-only,
   SEARCH arm PWM, 알려진 base pose 6–10개(예: x=3.0/3.4/3.8/4.0/4.2,
   y=−2.6/−2.4/−2.1), 각 2–3프레임. 목적: nav SEARCH 자세에서
   ① zone B in-band 픽셀·연결요소 크기, ② `bottom_norm` 최대값(0.98 도달 여부),
   ③ 도착 가드 문턱 검증.
2. 경로 바닥 프레임: pickup 탈출·wide door·east room에서 floor-only 프레임
   6–10장. 목적: 스폰 외 다른 바닥이 밴드에 들어오는지 확인.
3. 위 캡처는 GPU 렌더가 필요하다(이 작업 범위 밖, VM/GPU 금지).

## 10. 한계 (명시)

- zone B 측정은 R4 장면 캡처다. nav-gate 장면의 조명/벽 프로필과 완전히
  같지 않다. 색은 재질+노출 지배적이라 전이 가능성이 높지만 **미검증**이다.
- 바닥 측정은 스폰 1자세, 2프레임(사실상 동일)이다. 다른 방/각도는 미측정.
- zonecal은 eval-only 라벨을 사용했다. 정답 라벨은 채점에만 쓰였고
  검출기·컨트롤러 입력이 아니다.
- 이 문서의 수치는 threshold 사전 등록용이며 성공/실패 판정이 아니다.

## 11. 재현

```bash
/home/ubuntu/ugrp-venv/bin/python scripts/e2ewarp_nav_detector_calib.py \
  --zonecal-dir /home/ubuntu/UGRP-wt/e2ewarp-integ/experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu \
  --nav-frame experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg \
  --nav-frame /home/ubuntu/UGRP/outputs/e2e18-admin/nav-gate/frames/r1-tick600.jpg \
  --output experiments/2026-10-18-nav-gate-1/detector-calib.json
```

- zonecal 경로는 branch `dsh/e2ewarp-components-v1` 체크아웃이다. 이 PR의
  base(`codex/e2ewarp`)에는 아직 없으므로, 리뷰 시 위 branch/commit과
  `SHA256SUMS.json` 대조 결과(`detector-calib.json`의 `inputs.zonecal`)를 본다.
- `r1-tick600.jpg`는 `outputs/e2e18-admin/nav-gate/frames/`의 실행 보관본이다
  (VM 원본은 `runs/e2ewarp-nav1-run-4`). repo 추적본은 `r1-tick5.jpg`뿐이다.

## 12. 이번 코드 변경과 검증

- `harness/e2ewarp_selfnav.py`: OpenCV 단위 명시(`hue_cv`, `units`),
  최대 연결요소 판정(`largest_component`), 도착 가드 + 1 s 신선도.
- `scripts/e2ewarp_nav_calibrate.py`: `turn_deg_signed` + `rotation` 블록
  (기존 `turn_deg`/`yaw_deg_per_pct_s` 양수 계약 유지).
- 테스트: `tests/test_e2ewarp_selfnav.py`,
  `tests/test_e2ewarp_nav_calibrate_signed.py`.
  - 바닥-only 실제 프레임 → 0검출
  - 두 blob 합 800 px, 최대 400 px → 0검출 (총합 판정 회귀)
  - 바닥색 bottom fill → 0검출
  - 바닥 fill 형상(bottom_norm 1.0, solidity 0.59, height 0.83) → 도착 아님
  - 3 px 띠(bottom_norm 0.999) → 도착 아님
  - 정상 patch → 도착
  - 10 s 지난 검출 → 도착 아님
  - 음수 turn 보존
