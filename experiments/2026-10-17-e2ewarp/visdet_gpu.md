# GPU frame 자기 RGB 구역/도착 검출 + R4 자기지도 게이트 재계수 (visgoal 지원)

상태: **준비 완료(비물리)**. GPU 실행은 하지 않았다. R4 원본이 나오기 전에 Mac에서
돌릴 비물리 분석 스크립트와 `navigation_factory`에 넣을 순수 RGB 검출 모듈을 이
브랜치(`claude/e2ewarp-visdet`, base `codex/e2ewarp` 718777118)에 준비했다.

## 1. `harness/own_rgb_zone_visdet.py` — 순수 RGB 구역/도착 검출

- 입력(허용): 자기 RGB uint8 HxWx3, **자기 servo FK에서 만든 카메라 모델**
  (`CameraModel`: pinhole intrinsics+`cam_to_robot` 또는 로봇 프레임 ray table),
  자기 발행 명령(선택, 이 모듈은 기하에 쓰지 않음), 정적 지도 zone 사각형(선택).
- 금지 입력: TOP 카메라, 시뮬레이터/GT pose, 접촉, 측정 관절, 교사 phase/결과,
  다른 로봇 프레임, 정답 라벨. 모듈은 `mujoco`/`warp`/`sim`/`harness`를 import 하지
  않는다(`tests/test_own_rgb_zone_visdet.py`의 AST import 검사).
- 기본 off 토글 `own_rgb_zone_visdet_v1`: `enabled=True` 또는
  `ZoneArrivalReporter(..., enabled=True)`일 때만 동작한다.
- 출력: `pixels/bbox/centroid/nearest_range_m/median_range_m/extent_m/bearing/bottom_norm/
  lower_centre_share/paint_reaches_bottom_band/arrival_ready/status/reason`.
  reason 범주는 CPU 원본의 거부 사유(`destination_colour_absent`,
  `destination_component_small`, `destination_not_ground_ray`,
  `destination_outside_floor_fit`, `destination_too_far`,
  `destination_extent_not_zone`, `painted_ground_hypothesis`)를 유지한다.
- 상수 근거(코드 docstring에도 기재): 색 밴드/S·V 하한은 visgoal C 빌드의 외관
  상수(기하 아님), 바닥 fit 1.8 m·최소 600 px는 vendored
  `destination_visual_acquire` 한계, **arrival bottom-band 0.98**은 CPU crossroom
  raw에서 문 밖 선언(GT margin -0.0162 m) 당시 피팅 bbox bottom 461/480=0.960이었던
  실측에서 온 값이다(성공 판정이 아니라 evidence).
- `ZoneArrivalReporter`: confirm/lost 프레임 디바운스로 `destination_arrived`,
  `zone_visible`, `evidence_revision`만 제공한다. `handoff_ready`는 **소유자
  navigation adapter가 결정**하도록 False로 둔다(이 모듈은 도착 권한이 아니다).

### navigation_factory 통합 방법

```python
from harness.own_rgb_zone_visdet import CameraModel, ZoneArrivalReporter

# owner가 자기 FK로 채운다(해시로 고정되는 소유자 API). 예: pinhole.
camera = CameraModel(kind='pinhole', width=640, height=480, fx=..., fy=...,
                     cx=..., cy=..., rotation=cam_to_robot_R,
                     translation_m=cam_to_robot_t)
reporter = ZoneArrivalReporter(camera, enabled=queue['toggles'].get('own_rgb_zone_visdet_v1') == 'on')

def observe(own_frame):                     # navigation adapter의 observe(OwnFrame)
    report = reporter.observe(own_frame.rgb, exclude_mask=None)
    return dict(destination_arrived=report['destination_arrived'],
                destination_zone='B', zone_visible=report['zone_visible'],
                evidence_revision=report['evidence_revision'],
                handoff_ready=False,        # owner rules decide
                own_rgb_zone=report['detail'])
```

GPU 렌더 프레임 주의: legacy CPU 카메라는 fisheye였고, GPU 렌더는 MuJoCo 카메라
모델(pinhole)이다. **fisheye ray table이 필요한 경우** `CameraModel(kind='rays', rays=...)`로
엔진 import 없이 전달한다. FK/hash는 소유자 `loaded_camera_fk` 부품 계약을 따른다.

## 2. `scripts/e2ewarp_selfmap_recount.py` — R4 자기지도 관문 비물리 재계수

R4 원본 디렉터리에서 다음만 읽는다(물리/모델 import 없음, Mac 실행):
`localization.json`(+`.zst`), `runtime-applied.json`, `result.json`, `rejections.json`.

```
python3 scripts/e2ewarp_selfmap_recount.py \
  --raw <R4 raw dir> --output <out>/recount.json --prior \
  experiments/2026-10-17-e2ewarp/r3/rejection_table.json
```

- R3 호환 funnel: `own_rgb → qualified_unloaded_FK → settled_scan →
  observed_wall_contacts → inserted_keyframe`, 각 단계 누적·거부 수.
- `elapsed_sim_v1` 확인(원본 재계수): `keyframe_insertions>0` 여부,
  **old `tick % 10 == 0` 게이트가 놓쳤을 삽입 수**(off-grid), 삽입 간 tick gap
  최소/중앙/최대, `elapsed-rule violations`(gap < interval_ticks).
- CLI는 정책이 `elapsed_sim_v1`인데 삽입이 0이면 exit 1(`SELFMAP_GATE_FAILED`);
  `--allow-zero`로 진단용 출력만 허용. stdout 표 + JSON + `sha256.json`.
- 읽지 않는 것: TOP 프레임, 시뮬 pose/GT, 접촉, 측정 관절, 교사 phase/outcome.
  범위: 자기지도 게이트 재계수만. 운반/위치정확도 성공 주장 아님.

## 3. 테스트·검증 범위

- `tests/test_own_rgb_zone_visdet.py` 5 tests: 기본 off, 엔진 import 없음,
  원거리 zone 검출(범위/넓이), 근거리 zone 도착 evidence(bottom>=0.98),
  exclude mask, reporter 디바운스.
- `tests/test_e2ewarp_selfmap_recount.py` 3 tests: elapsed_sim_v1 funnel/off-grid/
  rule 위반, 삽입 0이면 exit 1, 삽입>0이면 정상 JSON+sha.
- `tests/test_e2ewarp_visdet_replay.py` 1 test: 기록 프레임 디렉터리 재생 경로가
  FK 카메라 모델을 만들고 GPU 프레임에서 모듈을 돌리며 엔진 import가 없음을 확인.
- 전부 비물리·Mac CPU. **GPU 실행·R4 원본 재계수는 아직 하지 않았다.** R4 원본이
  나오면 위 명령으로 재계수해 funnel과 `elapsed_sim_v1` 키프레임 삽입을 원본에서
  확인한다. 검출 모듈의 GPU 렌더 프레임 실측은 R4 또는 별도 승인 실행에서만 한다.

Produced with DeepSeek Harness. https://github.com/deepseek-ai/deepseek-harness

## 4. R4 GPU 원본 공식 재계수 (2026-10-18)

라벨: **R4 = attempt**, `queue.round=3`, source `718777118be41991156b047faff78621969101bb`,
gcp6, nworld 2, smoke 30 SIM s `cap_end`, `mjwarp_batch_v1` /
`warp_native_contact_v1`, policy `elapsed_sim_v1`.
원본 `gcp6:/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run`, Mac 사본 `/tmp/e2ewarp-r4-raw`.
공식 결과: [`r4-selfmap-recount/`](r4-selfmap-recount/) (`recount.json`,
`input-sha256.json`, `visdet-replay*.json`, `SHA256SUMS.json`).

- **funnel 재계수**: `own_rgb 1806 → qualified_unloaded_FK 1806 →
  settled_scan 48 → observed_wall_contacts 48 → inserted_keyframe 48`
  (R3: 0). per-stream 6개 모두 frames 301 / settled 8 / inserted 8,
  삽입 ticks `[24,71,124,148,195,224,248,295]`.
- **elapsed_sim_v1 검증**: 삽입 48>0, elapsed-rule 위반 0(gap min/median/max =
  24/47/53 ticks), **old `tick%10` 게이트가 놓쳤을 삽입 48**. (1차 재계수의
  off-grid 0은 localization row에 `tick`이 없어 gap 계산이 비었던 탓이고,
  공식 재계수는 `sim_s*10`으로 10Hz clock을 유도했다. 결론 동일: 통과.)
- **visdet GPU 프레임 재생(새 실행 없음)**: 기록된 own RGB 2Hz review frames
  183장(world-00)에 발행 명령 FK + 고정 fisheye 보정 카메라 모델로 모듈을 돌림
  (Mac CPU 2.66s). **관측 결함**: GPU 렌더에서는 바닥이 채도 높은 파란색이라
  CPU에서 쓰던 파란색 밴드가 floor를 zone paint로 오인한다(uncapped 180/183
  observed, component 185k px·extent 4.05m). zone 크기 기반 extent cap 2.0m
  (zone 대각 1.52m 근거)를 넣으면 144건이 거부되지만 하단 잘린 near-floor
  36건은 여전히 통과하고 arrival evidence는 0이다. **R4 smoke 프레임에는
  zone B paint가 보이는 프레임이 없어 GPU zone 외관을 이 원본으로 보정할 수
  없다** → navigation_factory 도착 판정 연결 전에 GPU zone-visible 프레임
  (동쪽 방 도달 프레임 또는 정적 캘리브레이션 캡처)이 필요하다. 그 전까지
  모듈은 기본 off이고, 재생 검증 범위는 "GPU 프레임에서 동작·근거 기록"까지다.
- 의존성: ACT/loaded FK/mapbuild8 correction/release **waiting** 그대로.


## 5. GPU zone-B appearance 캘리브레이션 캡처 + `gpu_calib_v1` 프로필 (2026-10-18)

라벨: **GPU appearance calibration, not research result**. LLM·제어·물리 step
없이, 기록된 R4 scene을 MJWarp native renderer로 실험자 설정 포즈에서 렌더했다
(zone-B paint가 보이는 10 포즈 + pickup/zoneA negative 2 포즈, 포즈당 2Hz 3프레임
= 36 프레임). 사용 카메라·remap·JPEG 설정은 R4 own frames와 동일하다.

- 원본: gcp6 `/home/ugrp/ugrp-sim/runs/e2ewarp-zonecal-gpu-v2` (TERMINATED 디스크
  보존), Mac `/tmp/e2ewarp-zonecal-gpu-v2`, 저장소 증거
  [`r4-selfmap-recount/zonecal-gpu/`](r4-selfmap-recount/zonecal-gpu/)
  (RGB 36장, `conditions.json`, `frames.json`, SHA256SUMS). scene sha256
  `38c7fdcd9a83dfc104d4b9f998a5ec69a9ce143a3dcd2e38c341686c9541d4b4`,
  remap sha256 `eb9b67fbe2cd9323054c779f34e925507caec635b6e74306241469c5d9c32e42`.
  (pose-aim 버그가 있던 v1 캡처 `...-zonecal-gpu`는 superseded·미사용.)
- fit 결과 [`r4-selfmap-recount/zone-appearance-calib.json`](r4-selfmap-recount/zone-appearance-calib.json):
  eval-only zone-B mask 라벨로 threshold grid 탐색 → **`gpu_calib_v1` = hue
  110-114, S>=100, 30<=V<=110, extent<=1.75 m**.
- before/after (같은 프레임):
  - 캘리브레이션 zone-B positives **33/33 → 33/33 유지**
  - pickup-zone negatives **3/3 FP → 0**
  - 기록 R4 own frames **36/180 FP → 0/180** (`visdet-replay-gpu.json`)
- near-floor bottom-cropped 케이스: 근접(d0.45 m) zone 프레임은 component가
  화면 하단까지 차고(bbox bottom 0.967) V~82로 GPU 프로필에서 정상 검출된다.
  R4의 하단 잘림 blue-floor 36건은 V가 높아(밝은 pickup floor) 새 프로필에서
  전부 거부된다.
- **한계**: 프로필은 이 캡처의 조명/장면에서 fit했다. 다른 조명/원거리 zone
  외관은 그대로 일반화된다고 주장하지 않는다. `navigation_factory`에 연결하는
  실행 검증은 owner manifest의 hash-bound entry 통합(Lead) 뒤에 하고, 그 전까지
  모듈은 **기본 off**다. ACT/loaded FK/mapbuild8 correction/release 대기는 그대로.
