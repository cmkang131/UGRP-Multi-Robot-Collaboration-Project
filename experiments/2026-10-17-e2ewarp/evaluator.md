# e2ewarp eval-only evaluator (`harness/e2ewarp_evaluator.py`)

물리 실행이 끝난 뒤 raw 디렉터리만 읽어 `physical-evaluation.json`을 만드는
별도 평가 부품이다. 제어기·ACT·LLM·지도에는 어떤 값도 돌려주지 않는다.
`mujoco`·`sim`·`scripts.e2e_warp_physics`를 import하지 않는다.

## 입력 (eval-only, 원자료)

| 파일 | 내용 |
|---|---|
| `evaluation-state.npz` | `qpos` `(ticks, worlds, nq)`, 고정 `dt`. 실행 중 평가 sink가 저장한 것만 읽는다. |
| `eval-geometry.json` | 실행 종료 뒤 평가 sink가 쓴 기하/원장. `schema=ugrp.e2ewarp.eval-geometry.v1`. robot base free-joint qpos 주소, cargo qpos 주소·초기 pickup xy·landing half extents, `zone_A/B/C` 사각형, door aperture, mission 요구, `evaluation-state.npz` 기대 SHA-256, world별 own-map 원장 요약을 담는다. |

`eval-geometry.json`은 `scripts/run_e2e_warp.py:evaluation_geometry()`가
`--mode mission`에서 제어가 모두 멈춘 뒤에만 만든다. static map의 zone/door
기하는 평가 전용이며, own-map 원장은 `localization.json` 행에서 복사한
관측 횟수·삽입 횟수·점유 셀·`map_correction_active` 횟수다. GT/TOP 키가
원장에 있으면 `self_map_used=false`로 닫힌다.

## 출력 `physical-evaluation.json`

`schema=ugrp.e2ewarp.physical-evaluation.v1`

```json
{
  "schema": "ugrp.e2ewarp.physical-evaluation.v1",
  "source_sha": "<40 hex>",
  "evaluation_state_sha256": "<64 hex>",
  "evaluation_state_filename": "evaluation-state.npz",
  "geometry_sha256": "<64 hex>",
  "nworld": 1,
  "eval_only": true,
  "agent_claim_used": false,
  "policy": {"max_tick_step_m": 0.5, "initial_cargo_tolerance_m": 0.1,
             "initial_cargo_yaw_tolerance_rad": 0.35,
             "carry_radius_m": 1.0, "carry_motion_threshold_m": 0.02,
             "attended_motion_fraction": 0.5, "robot_half_width_m": 0.1,
             "gate_footprint_check": true, "require_own_gauge_pose": false},
  "worlds": [{
    "world_id": 0,
    "physical_success": false,
    "first_to_end_transport": false,
    "same_episode": true,
    "self_map_used": true,
    "zone_check": {"destination_zone": "B", "bases_inside": false, "cargo_inside": false,
                   "center_m": [4.6, -2.1], "half_extents_m": [0.3, 0.7],
                   "base_requirement": "all", "required_robots": ["r1", "r2"],
                   "robots": [{"id": "r1", "center_m": [4.45, -1.8], "inside": true, "margin_m": 0.15}],
                   "cargo": [{"id": "beam_1", "inside": false, "margin_m": -0.1,
                              "initial_ok": true, "carried": true, "carried_motion_fraction": 1.0,
                              "initial_distance_m": 0.0, "nearest_robot_m": 0.3}]},
    "gate_check": {"required": true, "ok": true, "gate": {"axis": "x", "plane_m": 2.2,
                   "center_lateral_m": 0.05, "half_width_m": 0.25},
                   "robots": [{"id": "r1", "crossed": true, "via_aperture": true}],
                   "cargo": [{"id": "beam_1", "crossed": true, "via_aperture": true}]},
    "self_map": {"used": true, "robots": {"r1": {"observations": 20, "inserted_frames": 3}}},
    "continuity": {"same_episode": true, "teleports": []},
    "reasons": ["cargo_outside_zone:beam_1"]
  }]
}
```

### 판정 정의

- `same_episode`: `qpos`가 `(ticks, worlds, nq)` 한 덩어리이고, `dt`가
  geometry와 같고, 모든 값이 유한하고, 로봇/cargo의 tick당 이동이
  `max_tick_step_m` 이하. 초기화·재시작으로 생기는 순간이동은 실패다.
- `physical_success`: (1) `base_requirement=all`이면 요구 로봇 base 전부,
  `any`이면 최소 하나가 zone B 사각형 안(최종 tick), (2) 요구 cargo의
  landing AABB가 zone B 안(반폭을 알면 회전 footprint 포함), (3) base와
  cargo가 divider 문 `plane_m`을 통과할 때 lateral 위치+footprint가
  `half_width_m` 안, (4) `same_episode`.
- `first_to_end_transport`: `same_episode` + cargo가 geometry의 초기 pickup
  xy/yaw에서 `initial_cargo_tolerance_m`/`initial_cargo_yaw_tolerance_rad`
  이내로 시작 + 움직인 tick의
  `attended_motion_fraction` 이상에서 요구 로봇 base와 `carry_radius_m`
  이내(정지 상태만 가까운 것은 운반이 아님) + 최종 landing이 zone B 안 +
  문 통과. 즉 “처음 위치에서 실제로 들고 끝까지 옮겼는가”다.
- `self_map_used`: 월드의 요구 로봇별 원장에 관측이 있고,
  `inserted_frames`/`occupied_cells_max`/`map_correction_active_rows` 중
  하나가 0보다 크고, GT/TOP 키가 없음. `all`이면 전부, `any`이면 최소 하나.
  qpos에서 유도할 수 없는 값이므로 eval-only 원장만 쓴다. 원장이 없거나
  손상되면 예외다.

성공은 제어기의 주장(`result.json`, `mission-events.json`,
`physical-evaluation.json` 기존 파일, npz의 추가 키)을 읽지 않는다. 평가
대상 파일은 `evaluation-state.npz`와 `eval-geometry.json` 둘뿐이다.

## Fail-closed

`EvaluatorError`로 중단하며, `scripts/run_e2ewarp.py`는 이를
`status=HOST_ERROR`, `E2E_success=false`로 기록한다. 성공으로 바꾸지 않는다.

- `EVALUATOR_INPUT_MISSING`: raw 디렉터리/`evaluation-state.npz`/`eval-geometry.json` 없음
- `EVALUATOR_INPUT_CORRUPT`: npz zip/JSON 파손, `qpos`/`dt` 누락
- `EVALUATOR_GEOMETRY_INVALID`: schema/eval_only/필드/zone/gate/mission/self_map 불일치
- `EVALUATOR_SOURCE_SHA_INVALID`: 40자리 소문자 hex 아님
- `EVALUATOR_STATE_SHA_MISMATCH`: 실제 `evaluation-state.npz` SHA-256 != geometry 기록
- `EVALUATOR_DT_MISMATCH`, `EVALUATOR_STATE_SHAPE_INVALID`, `EVALUATOR_STATE_TOO_SHORT`,
  `EVALUATOR_STATE_NOT_FINITE`, `EVALUATOR_WORLD_SET_MISMATCH`
- `EVALUATOR_SELF_MAP_EVIDENCE_MISSING`: world/robot 원장 누락
- `EVALUATOR_CARGO_MISSING`, `EVALUATOR_MISSION_INVALID`

## 배선 / 기본 off

`harness/e2e_warp_components.require_components`는 `evaluator_factory`의
`entry`/`sha256`이 root 안 실제 파일과 일치하고 `ready=true`,
`owner`, `evidence`가 있어야 통과한다. 즉 manifest에 명시하지 않으면
mission 입장이 `DEPENDENCY_WAIT:hash-bound evaluator_factory`로 닫힌다.
`experiments/2026-10-17-e2ewarp/components.pending.json`에는 이 evaluator가
`ready=true`/현재 SHA로 등록돼 있지만 나머지 부품이 `false`라 기본 mission은
계속 `DEPENDENCY_WAIT`다. `--mode smoke`와 기본 CLI는 이 부품을 호출하지 않고
기존 산출물/성공 판정도 바꾸지 않는다. `--mode nav`가 추가되는 후속
브랜치에서는 evaluator를 선택 사항으로 두고 nav 재계수 경로를 그대로 둔다
(현재 base에는 nav mode가 없다).

호출 순서: 모든 제어 종료 → `evaluation-state.npz` 저장 → 평가 sink가
`eval-geometry.json` 기록 → `physical-evaluation.json` 기록 → `sha256.json`.
평가 출력은 `result.json`의 `E2E_success`/`research_result`에만 반영되고,
제어 관측·전이에는 재입력되지 않는다.

## 검증 범위

`tests/test_e2ewarp_evaluator.py`의 합성 npz/json fixture로 다음을 확인한다:
zone 안 성공, zone 밖 실패, 문 aperture 밖 실패, 옆으로 든 beam footprint
실패, 로봇과 무관하게 움직인 cargo 실패, tick 사이 순간이동 실패, 파일
누락/파손, SHA 불일치, world 수 불일치, NaN, agent claim 무시, npz 추가
claim 무시, self-map 원장 누락/0/GT 키, `any` base mode, manifest
ready/hash gate, mujoco 미import, run 평가 sink가 만드는 geometry 계약.

아직 남은 것: 실제 2로봇 wide-door 장면(PR #602 계열)과의 scene 통합,
gate2 mode, 그리고 실제 MJWarp 실행에서 evaluator를 통과시키는 물리 검증.
이 문서/시험은 그 물리 성공을 주장하지 않는다.
