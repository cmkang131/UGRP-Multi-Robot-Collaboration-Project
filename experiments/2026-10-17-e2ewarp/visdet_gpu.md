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
- 전부 비물리·Mac CPU. **GPU 실행·R4 원본 재계수는 아직 하지 않았다.** R4 원본이
  나오면 위 명령으로 재계수해 funnel과 `elapsed_sim_v1` 키프레임 삽입을 원본에서
  확인한다. 검출 모듈의 GPU 렌더 프레임 실측은 R4 또는 별도 승인 실행에서만 한다.

Produced with DeepSeek Harness. https://github.com/deepseek-ai/deepseek-harness
