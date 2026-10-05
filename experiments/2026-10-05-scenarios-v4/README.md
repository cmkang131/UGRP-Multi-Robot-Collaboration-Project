# 시나리오 v4: v3 여덟 종 + 최종 로봇 v3 지도 (2026-10-05)

조정자 결정(E2E 격차 문서 [PR #389](../2026-10-05-scenario-e2e-gap/README.md) 5절 D2의 S0 단계): 연구 시나리오는 v4로 한다. **v4 = 시나리오 v3(s1–s8, `0f0e4f08`) 중 지도 필드만 최종 로봇 v3 지도로 바꾼 것.** 새 지도는 만들지 않는다.

## 변경
- `configs/zone_study_scenarios_v4/`: 여덟 파일. v3와 다른 곳은 `scenario_id`(`_v3`→`_v4`), `map_id`, `eval.setup.map_file_sha256` 세 필드뿐이다.
- 지도 대응: `zone_wide_door_geometry_v2`→`zone_wide_door_geometry_v3`(s1·s3·s5), `zone_wide_two_doors_final_v1`→`zone_wide_two_doors_final_v3`(s2·s6·s7·s8), `zone_wide_corridor_final_v1`→`zone_wide_corridor_final_v3`(s4). 해시는 지도 파일에서 계산한다.
- 생성: `build_v4.py`(기존 v4 파일과 다른 내용으로는 덮어쓰지 않는다). v2·v3 파일은 바이트 그대로이며 v3는 `0f0e4f08` 내용 그대로 이 PR로 main에 들어온다(v3 시험·생성 스크립트·문서 포함).
- 시험: `tests/test_zone_study_scenarios_v4.py` 8개(`scripts/run_ci_tests.py` 등록, v3 시험도 함께 등록).

## 근거
- 지도 v2/final_v1과 v3는 기하가 같다. 직접 비교하면 달라진 필드는 `map_id`·`version`·`robot_model`·`parent_scene`뿐이고 시험이 이를 고정한다.
- 주문·배치·사건·예산·seed는 그대로이므로 시나리오 설계를 다시 하지 않는다. 로봇 v3 소비자 검사는 지도 v3만 허용한다.

## 검증 범위
- 실행: `pytest tests/test_zone_study_scenarios_v4.py` 8 passed, `tests/test_zone_study_scenarios_v3.py` 10 passed(오프라인).
- 수동 확인(시험에 넣지 않음, 약 52초): 여덟 종 모든 물건의 경로가 v3 지도에서 `feasible`.
- **하지 않은 것:** 시뮬레이션·물리·모델 호출, `harness.zone_final_env.FINAL_MAPS`·시나리오 레지스트리에 지도 v3 연결(`maps_dir_for`는 아직 옛 지도만 안다), 새 번들 ID·workflow 번호 예약, s7·s8을 연구에 포함할지(사전 등록 소유자 결정).
