# 시나리오 세트 v6: tile·can을 작은 상자로 교체

사용자 결정(2026-10-14): "걍 타일같은 건 빼는 게 어떄? 보라 캔도 연구 목적과 상관없는 거 같아". 질문 "빠진 자리는 어떻게 할까요?"에 사용자 선택 "같은 상자로 대체 (Recommended)".

v5 여덟 장면의 화물 33개와 작업량·위치·목적 구역·개수·이벤트·seed·지도·예산을 유지한다. 6개 장면의 can 4개·tile 3개만 기존 작은 색 상자로 바꾼다. 파일명과 시나리오 ID는 `_v6`, 교체 개체 ID는 새 색에 맞춰 참조와 함께 바꾼다. 이전 파일·코드·결과는 재생용으로 보존하며 v6 결과와 합산하지 않는다. 기본값 변경 없이 `_v6` 명시 경로만 추가했다.

색은 주문 순서대로 미사용 색을 먼저, 네 색이 모두 있으면 개체 수가 가장 적은 색을 고른다. 동률은 청록(cyan)→빨강(red)→초록(green)→노랑(yellow), 교체할 때마다 개수를 갱신한다. 생성: `build_v6.py`(기존 v6의 다른 내용을 덮어쓰지 않음). 전체 대응·중복 개체 목록: `replacements.json`.

| 시나리오 | 원래 종류·ID → 새 색·ID | 같은 색·같은 목적 구역 |
|---|---|---|
| s1_normal_mixed_v6 | can_1 → yellow_1(노랑) | 없음 |
| s1_normal_mixed_v6 | tile_1 → red_2(빨강) | **새 중복** red_1/red_2, B, 둘 다 P2(슬롯 P2-1/P2-2) |
| s3_late_rendezvous_v6 | tile_1 → green_1(초록) | 없음 |
| s5_moved_dropped_item_v6 | can_1 → green_1(초록) | 없음 |
| s6_novel_relation_v6 | can_1 → red_1(빨강) | 없음 |
| s7_pair_with_solo_v6 | tile_1 → red_1(빨강) | 없음 |
| s8_mixed_tiers_v6 | can_1 → cyan_1(청록) | 없음 |

같은 색·같은 목적 구역 중복은 전체 5그룹(새 1, 기존 4): s1 청록/A·빨강/B, s2 청록/A, s5 빨강/B, s8 노랑/A. s2·s4는 ID만 바뀐다.

입력 점검: `zone_study_inputs.FORMATIONS/ITEM_KINDS`와 `zone_goal_v2.ALL_KINDS`, `zone_mixed_episode.PLACE_ORDER`, 인식·교사 코드의 can/tile 정의는 재생용으로 유지한다. 주문표 `_kind_table`, 프롬프트 `StudyInputs.kinds/roles_by_order/vocabulary`, 후보 선택 `FixtureActor._target_order`와 실행 계획 `zone_study_integration.executor_plan`은 현재 주문에서만 종류를 받는다. v6 입력 검증은 상자 네 색·long_beam·heavy_crate만 허용한다. 네 통신 조건의 실제 요청 생성·종류/ID 목록·모든 주문 후보를 오프라인 시험한다.

1대 교사 `sim/grasp_act_solo_teacher.py`의 **v6 운반 종류는 BOX_KINDS(cyan/red/green/yellow)뿐**이다. 이 파일은 기준 main에 없고 별도 PR #502에서 개발 중이며, 그 경로의 can/tile 코드·이전 시연은 재생용으로 보존한다. s6의 기존 기하 수치·접근 가정은 그대로이며, 바뀐 상자 형상의 실제 접근·운반 성공은 미검증이다.

검증(2026-10-15): `tests/test_zone_study_scenarios_v5.py`, `tests/test_zone_study_scenarios_v6.py`만 실행해 **78 passed**(8.142초), 실패·오류·skip 0. v5 원본 8개는 기준 SHA와 바이트 동일하다. 결과와 원본 파일 해시는 `summary.json`에 기록했다. 물리·렌더·원격 서버·모델 호출 0회. 기준 소스: `580e9100fad670fe85460872dc010cec541024fa`.

## 참고 자료

[PR #498](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/498): `1788a95b`(v5 생성·레지스트리·시험), `393a432d`(ScenarioFinalV3Scene 문자열 ID 경로 수정). 두 diff의 명시 버전 라우팅·이전 파일 보존 구조를 따른다.
