# 2026-10-18 nav-gate 장면: 픽업 바닥 neutral + 조명 상향 (scene profile v6)

**상태: 코드/오프라인 검증 완료. GPU 프레임은 아직 없음(확인 안 됨).**
이 변경은 물리/GPU 실행 없이 저작·검증했고, 실제 after 프레임과 V 측정은
gcp6 nav-gate 재실행이 필요하다. 연구 결과/E2E 성공 주장이 아니다.

## 1. 원인 위치

| 위치 | 내용 |
|---|---|
| `sim/zone_arena.py:251` | `build_authored_map`가 pickup region을 `rgba '.12 .36 .70 .14'`로 저작 |
| `sim/zone_arena.py:411-413` | `build_zone_xml`가 region마다 `zone_<id>` geom을 바닥 위 z=0.0006에 그림 |
| `sim/scene_contrast_v5.py:26-29` | 새 scene profile `walls_floor_contrast_v6_indigo110_s80_neutral_start` |
| `sim/scene_contrast_v5.py:82-83` | 프로필 적용 시 `neutral_pickup_floor.apply_root(root)` 호출 |
| `sim/neutral_pickup_floor.py:57` | `zone_pickup`을 중성 회색 타일 60개로 교체 |
| `sim/scene_contrast_v5.py:38-49` | v6 전용 광원 배율(0.30 → 0.70); `sim/render_profile.py`는 p03 pin 때문에 수정하지 않음 |
| `configs/current_stack.json:290` | `scene_profile.current` = v6 |

공유 맵 파일(`maps/zones_final_v3/zone_wide_two_doors_final_v3.json`)은
**바이트 그대로**다. 기존 R4/기타 실험의 조건을 바꾸지 않기 위해 맵을 고치지
않고, nav-gate가 쓰는 새 scene profile에서만 픽업 오버레이를 다시 칠한다.

## 2. 변경

- pickup 오버레이: `rgba .12 .36 .70 .14`(파랑, alpha 0.14) 1장 →
  **중성 회색 타일 6×10 = 60장**, `rgba`는 세 톤 중 하나(linear 0.75 / 0.88 / 1.0),
  alpha **1.0**, 채널 R=G=B (채도 0). 코너/엣지와 3톤 대비가 특징점으로 남는다.
- 조명: v6의 `light_scale 0.70` — `noshadow_bright_v1`(0.30) 적용 뒤 diffuse/ambient/specular에
  ×7/3를 한 번 더 곱한다(순 0.70). `sim/render_profile.py`는 바이트 pin이라 건드리지 않았다.
- 벽 indigo 도색·벽 텍스처·문·문 폭·스폰·zone A/B/C 도색·맵 geometry는 불변.
  벽 텍스처는 v5 자산을 그대로 재사용한다(`texture_asset_profile`).

## 3. before / after 값

**before (실제 기록 프레임, `experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg`,
sha256 `4e921717…60ab9`)** — [before-after.json](before-after.json),
[before-after-swatch.png](before-after-swatch.png):

- 픽업 바닥: OpenCV **H 108 / S 212 / V 90**, 프레임의 **57.0 %**
- zone B: H 110–114, S≈202, V p50 85 (같은 문서 §3.1)
- detector band(H 110–114, S≥100, 30≤V≤110) 픽셀 1,583 (0.52 %)

**after (저작값 + 1차 예측, 렌더 아님)**:

- 픽업 바닥: **S = 0**, H 없음(무채색), V 예측 **122 / 131 / 139**
  (선택 3톤; 기록 프레임의 G/B 채널 irradiance × 0.70/0.30으로 예측)
- zone B 도색은 맵에서 그대로(`rgba .20 .40 .95 .30`, OpenCV H 109 nominal).
  다만 조명이 밝아져 렌더 V가 올라가므로 **기존 `gpu_calib_v1`
  (H 110–114, S≥100, 30≤V≤110)은 이 장면에서 유효하지 않다.**
- after 프레임은 **없다**: 로컬에 MuJoCo/GPU가 없어 렌더하지 않았다.
  `before-after-swatch.png`의 오른쪽은 렌더가 아니라 저작 예측 swatch다.

## 4. Hash

| 대상 | before | after |
|---|---|---|
| map `zone_wide_two_doors_final_v3.json` | `b6a61f7e…a41b` | **동일** (변경 없음) |
| scene profile v5 (frozen) | `b95ad4e7…94fc4` | 동일 |
| scene profile v6 (new) | — | `8c30b5f2…956ae` |
| render profile `noshadow_bright_v1` (frozen) | `f994f8d6…e2e5f` | 동일 (`sim/render_profile.py` 바이트 동일) |
| v5 wall texture manifest | `cf447537…96757` | 동일 (자산 재사용) |
| v1 floor texture manifest | `4a7005e2…d9a08` | 동일 |

맵이 hash-bound이지만 **바뀌지 않았으므로 재생성하지 않는다.** (프로필 해시만
새로 기록한다.)

## 5. Tests

- 신규 `tests/test_neutral_pickup_floor.py` (**9 tests**): 오버레이 제거·타일 60개·
  면적/위치·S=0·zone B 불변·기록 프레임 before 실측·v5/v6 프로필 해시 고정·
  `apply_xml`이 v6에서만 오버레이를 바꾸는지·current_stack/맵 SHA 고정·
  fail-closed 2건(오버레이 없음 → `NEUTRAL_PICKUP_OVERLAY_MISSING`,
  rgba 변경 → `NEUTRAL_PICKUP_OVERLAY_RGBA_CHANGED`).
- 함께 실행: `tests/test_zone_scenario_scene.py`, `tests/test_render_profile.py`,
  `tests/test_e2ewarp_nav_gate.py`, `tests/test_zone_environment_registry.py`,
  `tests/test_natural_scene_texture.py`.

## 6. GPU가 필요한 것 (확인 안 됨)

1. **after 프레임 1장 + V·채도 실측**: 새 프로필로 nav-gate를 다시 돌려
   스폰 프레임에서 픽업 바닥 V가 120–160인지, S가 100 미만인지 확인.
   V가 범위 밖이면 v6의 `light_scale`(0.70) 또는 타일 팔레트만 조정.
2. **zone B 재캘리브레이션**: 새 장면의 zone B 접근 프레임 6–10자세로
   H/S/V 분포를 다시 재고 `gpu_calib_v1` 문턱을 새로 등록해야 한다.
   밝기 변경 전 문턱으로 이 장면을 판정하면 안 된다.
3. 위 두 가지는 이 PR 범위 밖(VM/GPU 금지). 아래 명령이 그 실행이다.

## 7. 재실행 명령 (gcp6, MJWarp; 로컬/GPU 금지)

```bash
cd /home/ugrp/ugrp-sim/src/<this-commit>
# 1) nav 구성요소 manifest (측정된 odometry calibration 그대로 사용)
python -m scripts.e2ewarp_nav_manifest \
  --out /home/ugrp/ugrp-sim/runs/e2ewarp-nav2-components.json \
  --calibration /home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/<measured calibration.json> \
  --source-sha "$(git rev-parse HEAD)"

# 2) admission queue (물리 없음)
python -m scripts.run_e2e_warp --prepare --e2e-warp-batch on_v1 --mode nav \
  --seed 601 --condition peer_en --nworld 1 --nav-sim-budget-s 60 \
  --components /home/ugrp/ugrp-sim/runs/e2ewarp-nav2-components.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-nav2-admission

# 3) 실제 gate (GPU): 같은 seed/조건, source SHA 고정
python -m scripts.run_e2e_warp --execute --e2e-warp-batch on_v1 --mode nav \
  --seed 601 --condition peer_en --nworld 1 --nav-sim-budget-s 60 \
  --expected-source-sha "$(git rev-parse HEAD)" \
  --queue /home/ugrp/ugrp-sim/runs/e2ewarp-nav2-admission/queue.json \
  --host-receipt /home/ugrp/ugrp-sim/ops-reviews/e2ewarp-host-receipt.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-nav2-run
```

LLM relay(`127.0.0.1:18627` → Mac `127.0.0.1:18626`)는 gate 1과 동일하게
켜 둬야 한다. 실행 후 프레임 측정은 다음으로 재현한다:

```bash
python experiments/2026-10-18-nav-scene-neutral/measure.py  # before/예측 재계산
```

## 8. 한계

- after V는 기록 프레임 1장에서 유도한 1차 예측이다. 실제 렌더의 톤 매핑·광원
  배치가 달라 V가 ±10 이상 틀릴 수 있다.
- 타일 패턴은 자연 바닥 텍스처를 덮는다. 픽업 구역의 **특징점은 유지**하지만
  (코너+3톤) 질감 자체는 인공 패턴이다.
- `walls_floor_contrast_v6_…`는 `configs/current_stack.json`의 current가 되어
  이후 모든 flow의 새 실행에 적용된다. 과거 결과는 각자의 v5 프로필 해시로
  남아 있으며, v5는 동결이라 재현 가능하다.
- CALIBRATION_PREREG.md §8은 "문턱+최대연결요소로 분리되므로 바닥 도색은
  바꾸지 않는다"고 적었다. 이 PR은 팀장 결정(2026-10-18: 시작 바닥 파랑 제거,
  특징점 유지, 조명 상향)으로 그 권고를 대체한다. 문턱 캘리브레이션은 새
  장면에서 다시 해야 한다.
- `configs/current_stack.json`의 current가 v6로 바뀌므로 mission/release의
  `ColourBoundaryState`(reloc16)는 여전히 **v5 캘리브레이션**을 검증한다
  (`harness/scene_colour_boundary.py:25`). v6 렌더에서 mission/release를 돌리려면
  새 scene colour calibration을 만들거나, 그 flow는 v5를 명시적으로 pin해야 한다.
  nav gate는 colour boundary를 쓰지 않아 이번 범위에서는 영향이 없다.
