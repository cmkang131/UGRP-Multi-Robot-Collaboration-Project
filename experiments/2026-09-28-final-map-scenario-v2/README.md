# 2026-09-28 최종 지도(walls_v3·표식 0개)와 시나리오 v2 (B5, #218)

사전 등록 초안 PR #254의 차단 조건 B5에 해당하는 작업이다. v1 시나리오 6종(`configs/zone_study_scenarios/s1–s6`)은 표식 지도(`*_tags_v1`)를 고정한다. 이 작업은 이를 최종 환경(walls_v3, AprilTag 0개) 지도로 옮긴 **새 파일**을 만든다. v1 파일과 해시는 바이트 단위로 그대로다. 물리·LLM·학습은 실행하지 않았다(배터리 제약, 2026-09-28). 정적 검사만 했다.

- 브랜치 `kiro/final-map-scenario-v2`, draft PR #255, `Refs #218`
- 모듈 `harness/zone_final_env.py`, 테스트 `tests/test_zone_final_env.py`(90개), CLI `python -m harness.zone_final_env [--write]`
- 번들 ID는 새로 쓰지 않았다(번들 등록은 사전 등록 고정 시점의 관리 세션 몫).

## 1. 표식 참조 재고 (main `d5bd208e` 기준)

| 종류 | 항목 | 표식 참조 |
|---|---|---|
| 연구 시나리오 | `configs/zone_study_scenarios/s1,s3,s5` | `zone_wide_door_tags_v1`(표식 70개), `landmark_detail: full` |
| 연구 시나리오 | `s2,s6` | `zone_wide_two_doors_tags_v1`(65개), `full` |
| 연구 시나리오 | `s4` | `zone_wide_corridor_tags_v1`(87개), `full` |
| 지도 `maps/zones/` | `*_tags_v1`(3), `*_tags_v2`(2), `zone_wide_door_tags_v2_dock_v3` | walls_v1(0.10 m) + 표식 65–87개 |
| 지도 `maps/zones/` | `*_tags_v3`(3), `*_tags_v3a1`(2) | walls_v3(0.40 m) + 표식 33–54개 |
| 지도 `maps/zones/` | `zone_wide_door_geometry_v2`(v4) | **walls_v3, 표식 블록 없음** → 재사용 |
| 실험 지도 | `experiments/2026-09-26-vision-loc/maps/zone_wide_door_walls_v3_notags.json` | walls_v3, 빈 `landmarks` 블록(`tags: []`) |
| 지도 정의 | `sim/zone_landmarks.py` `TAGGED_MAPS`·`ENV_V3_TAGGED_MAPS`·`ENV_V3A1_TAGGED_MAPS`, `sim/zone_tag_rule_v3.py` | 표식 지도 생성 규칙 |
| 통합 에피소드 | `configs/zone_study_integration/i1_cyan_three_slots`, `i2_pair_long_beam`, `multiturn_dev_DRAFT`, `pair_dev_DRAFT` | `zone_wide_door_tags_v2`; DRAFT 2개는 제공자 `tags_temporary` |
| 통합 에피소드 | `i1_cyan_three_slots_geometry_v2` | `zone_wide_door_geometry_v2` + `vision_zero_tag_v2` |
| 위치 제공자 | `configs/zone_study_integration/pose_providers.json` | `tags_temporary`(`uses_landmark_tags: true`, `research_result: false`), `vision_zero_tag_v2`(표식 미사용, `research_result: false`) |
| 실행 경로 | `configs/simulation_workflows.json` | `tags_temporary` 2곳 |
| 통합 번들 | `harness/zone_study_integration.py` v64–v69(`...-v69-multiturn-landmark-agnostic` 등) | 번들 자체는 지도 ID를 고정하지 않는다. 위 에피소드 설정이 표식 지도·제공자를 고정한다 |
| 장면 | `sim/zone_geometry_scene.py` `MAP_IDS = ('zone_wide_door_geometry_v2',)` | 표식 없는 장면은 문 1개 지도만 등록돼 있다 |
| 코드 | `sim/zone_eval_top.py`, `sim/zone_start_dock.py`, `harness/owncam_pose_source.py`, `harness/vision_pose_source.py`, `harness/zone_map_schematic.py`, `harness/zone_study_contract.py`, `harness/zone_study_integration.py`, `scripts/run_zone_study_integration.py`, `scripts/run_zone_pair_dev.py`, `scripts/run_m2_pair.py`, `scripts/evaluate_zone_pair_dev.py`, `scripts/zone_pair_dev_contract.py`, `scripts/build_owncam_loop_views.py` | `tags_v*` 지도나 `tags_temporary`를 이름으로 참조한다(이 PR에서 수정하지 않음) |

## 2. 최종 지도와 시나리오 v2

지도 규칙은 이미 등록된 `zone_wide_door_geometry_v2`와 같다. `sim.zone_arena.authored_map(base)`에 `apply_wall_profile(.., 'walls_v3')`를 적용한다. `map_id`, `version: 4`, `base_map` 연결을 넣고 `json.dumps(indent=2)`로 쓴다. `landmarks` 키는 없다. 문 지도는 기존 파일을 바꾸지 않고 재사용한다. 이 규칙이 그 파일을 바이트 단위로 재현하는지는 테스트로 확인했다. 나머지 두 지도는 소유 규칙에 따라 `maps/zones/`가 아닌 `maps/zones_final/`에 새로 만들었다.

| 지도 | 파일 | SHA-256 |
|---|---|---|
| `zone_wide_door_geometry_v2`(재사용) | `maps/zones/zone_wide_door_geometry_v2.json` | `0a8f5fdc3b3ad01710971a9f5caf020eb76c7e90f3da5713e669d035b4e7ebaf` |
| `zone_wide_two_doors_final_v1`(신규) | `maps/zones_final/zone_wide_two_doors_final_v1.json` | `e93bce155c01aef3…`(전체 값은 `catalog.json`) |
| `zone_wide_corridor_final_v1`(신규) | `maps/zones_final/zone_wide_corridor_final_v1.json` | `f968251ae0e9a3af…` |

모든 해시(파일, `static_map_sha256`, base 지도, wall profile, 로봇용 투영 `public_map_sha256`, v1/v2 시나리오 파일)는 `maps/zones_final/catalog.json`(`ugrp.zone_final_env_catalog.v1`)에 있다. 테스트가 이 값을 파일에서 다시 계산해 대조한다.

시나리오 v2(`configs/zone_study_scenarios_v2/`)에서 바뀐 경로는 네 개뿐이다. 주문·화물·seed·배치·숨은 사건·예산·설명 문구는 v1과 같다.

| v2 | v1 지도 → v2 지도 | 바뀐 경로 |
|---|---|---|
| `s1_normal_mixed_v2` | `zone_wide_door_tags_v1` → `zone_wide_door_geometry_v2` | `scenario_id`, `map_id`, `landmark_detail`(full→none), `eval.setup.map_file_sha256` |
| `s2_unmapped_blockage_v2` | `zone_wide_two_doors_tags_v1` → `zone_wide_two_doors_final_v1` | 같음 |
| `s3_late_rendezvous_v2` | `zone_wide_door_tags_v1` → `zone_wide_door_geometry_v2` | 같음 |
| `s4_narrow_door_standoff_v2` | `zone_wide_corridor_tags_v1` → `zone_wide_corridor_final_v1` | 같음 |
| `s5_moved_dropped_item_v2` | `zone_wide_door_tags_v1` → `zone_wide_door_geometry_v2` | 같음 |
| `s6_novel_relation_v2` | `zone_wide_two_doors_tags_v1` → `zone_wide_two_doors_final_v1` | 같음 |

`landmark_detail: none`은 `scripts/run_zone_study_integration.py`가 표식 미사용 제공자에 요구하는 명시 값이다. `arena_variant`는 base 지도 그대로다(검증기 규칙).

## 3. 정적 검사 결과 (`1cd68812`, 물리 없음)

`python -m harness.zone_final_env`: 9/9 통과(지도 3, 시나리오 6). `pytest tests/test_zone_final_env.py`: 90 passed, 36.96 s. 실행 시 부하 평균은 105.66(다른 에이전트 부하), 스레드는 1개로 제한했다.

- 지도 스키마: `harness.zone_map_schematic.load_map`(schema·map_id), 정의 재현, 표식 필드 0개(키·문자열 재귀 검색), 모든 벽 0.40 m, 벽 발자국·경계·구역·통로·TOP 설정이 base 지도와 같음. 로봇용 투영(`landmark_detail: none`)에 `landmarks` 없음.
- 교차 확인: 신규 두 지도는 이미 등록된 `*_tags_v3`에서 `landmarks`만 뺀 것과 같다(`map_id`·`version` 제외).
- 통로 폭(벽 사이 실측): `door_1` 0.50 m·1차선, `door_narrow` 0.50 m·1차선, `door_wide` 1.00 m·2차선, `corridor_1` 0.50 m·1차선. 선언 폭 오류, 문 안의 벽, 좁아진 문, NaN·None·빈 값·잘못된 형식은 음성 대조로 검사했다.
- 도달성: 격자 0.02 m, 원판 반지름 0.17 m(빈 로봇)·0.21 m(적재, `harness.zone_scenario_feasibility` 교사 값). 모든 주문의 pickup 슬롯과 목적 구역이 존재하고 연결된다. 음성 대조로 확인한 것은 세 가지다. 유일한 문을 막으면 모든 주문이 끊긴다. `door_narrow`를 막아도 `door_wide`로 연결된다. 반지름 0.26 m 원판은 0.5 m 문을 지나지 못한다.
- 시나리오: `harness.zone_study_scenarios.validate(maps_dir=…)` 전 항목 통과(`has_landmarks: false`). v1 대비 허용된 4개 경로 외에는 차이가 없다.

## 4. 검증하지 않은 것 (전원 확보 후)

- 2인 편대 운반 경로: `harness.zone_scenario_feasibility.evaluate`를 v2에 다시 돌리지 않았다(CPU 약 40 s). 2-D 기하가 v1과 같아 판정이 같을 것으로 **예상**하지만 확인하지 않았다(v1 결과: s1–s5 가능, s6 조건부).
- 장면 연결: `sim/zone_geometry_scene.MAP_IDS`에는 문 지도만 있다. 신규 두 지도(`maps/zones_final/`)를 장면·통합 러너에 연결하는 일은 해당 파일 소유 작업과 조율해야 한다. 기본값 `MAP_DIR`만 보는 호출부(`bundle_for`, 러너의 `validate(scenario)`)에는 `maps_dir_for(map_id)` 전달이 필요하다.
- 최종 환경 3대 no-LLM 스모크와 M1·M2 재검증(B8, #219/#221/#224), 표식 없는 위치 추정 VIS6(B3), 로봇 모델 v3(#249) 전환 뒤 재검증.
- 본연구 보류 seed(PREREG §5.1의 `10000+100k+j`)는 사용자 지시("seed는 v1과 동일")에 따라 넣지 않았다. 고정 시점에 새 버전으로 추가해야 한다.
- 로봇용 도면 PNG 하단 문구("0 AprilTag landmarks marked")와 투영의 `landmark_detail` 키는 공용 렌더러·투영기(`harness/zone_map_schematic.py`)에서 나온다. 값을 바꾸면 기존 해시가 모두 바뀌므로 이 PR에서는 그대로 두었다.

## 참고 자료

- 논문: 이 작업은 정적 지도·설정의 버전 전환이라 새로 참조한 논문이 없다.
- OSS: NumPy 2.5.2(BSD-3-Clause, 격자 팽창 계산), Pillow 12.3.0(HPND, 기존 `zone_map_schematic` 투영 경유, 이번 호출은 `schematic=False`), Python 3.12.13 표준 `collections.deque`(연결 성분 BFS). 새 의존성은 없다.
- 채택하지 않은 대안: `scipy.ndimage.label`은 가상환경에 설치돼 있지 않다. 20줄 BFS를 위해 의존성을 추가하지 않았다. 실험 지도 `zone_wide_door_walls_v3_notags.json`은 빈 `landmarks` 블록이 남아 있고 문 지도만 있으며 실험 폴더 전용이다. `*_tags_v3`에서 표식을 빼는 방식은 ID가 표식 계열이라 쓰지 않고 교차 확인에만 썼다. `maps/zones/`에 새 파일을 두는 방식은 소유 규칙 때문에 쓰지 않았다.
- 내부 재사용: `maps/zones/zone_wide_door_geometry_v2.json`·`sim/zone_geometry_scene.py`(PR #240 계열 지도 규칙), `sim/zone_arena.py`(`authored_map`, `apply_wall_profile`, `wall_profile_record`, `NARROW_DOOR_M`, `WIDE_DOOR_M`), `sim/research_dispatch_arena.digest`, `harness/zone_map_schematic.py`(`load_map`, `public_map`, `pickup_bays`), `harness/static_keepouts.keepout_rects`, `harness/zone_scenario_feasibility.py`(`ROBOT_RADIUS_M`, `CARRY_RADIUS_M`), `harness/zone_study_scenarios.validate`, `harness/zone_study_contract.ZONE_IDS`, `experiments/2026-09-26-vision-loc/tagfree_scene.py`(표식 없는 walls_v3 구성 선례).
- 문서: `experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md`(PR #254, B5·§5.1), `docs/zone_scenario_feasibility.md`, `maps/README.md`, `AGENTS.md`.
