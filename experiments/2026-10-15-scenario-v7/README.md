# 시나리오 v7: heavy_crate 제외

사용자 결정(2026-10-15): "무거운 상자나, 긴 빔이나 둘 다 2명이서 들어야 한다는 건 똑같아서 버려도 돼". 선택 버전 `configs/zone_study_scenarios_v7/`를 추가했다. v6 원본 8개와 기본 시나리오 목록은 유지한다. **v7 결과는 v6 및 이전 결과와 합산하지 않는다.** 기준 소스는 `0f92bb93`(PR #518 포함), 작업 브랜치는 `codex/scenarios-v7-nocrate`다.

## 변경과 정적 검증

v6 원본을 확인하니 crate는 s2 하나가 아니라 **s2·s7·s8에 각각 하나**였다. 세 주문을 모두 `long_beam`/`beam_1`로 바꿨다. 주문 ID·슬롯·중심·목적 구역·필요 로봇 수(2)·사건·예산·seed는 그대로이며, yaw만 기존 long_beam 배치와 같은 `1.5708` rad로 바꿨다. 나머지 다섯 시나리오는 ID의 `_v6`→`_v7`만 바뀐다. 전체 화물은 **33→33개**, 필요 로봇 수를 화물별 합산한 작업 수는 **40→40**이다. 실제 소요 시간·물리 난도가 같다는 뜻은 아니다.

| 시나리오 | 주문·슬롯 | 가장 가까운 벽·틈 | 가장 가까운 다른 화물·틈 |
|---|---|---|---|
| s2_unmapped_blockage_v7 | order-3 · P2-1 | wall_south · 0.675 m | green_1 · 1.289435 m |
| s7_pair_with_solo_v7 | order-1 · P2-1 | wall_south · 0.675 m | red_1 · 1.482959 m |
| s8_mixed_tiers_v7 | order-3 · P1-1 | wall_south · 0.675 m | cyan_1 · 2.537157 m |

틈은 기존 배치 검사와 같은 보수적 축 정렬 사각형 사이 거리다. 기존 `zone_environment_registry.validate`로 8개 모두 슬롯 안쪽 0.05 m·벽 0.20 m·화물 간 0.20 m 기준을 통과했고, 정지 로봇 차체와 화물이 겹치지 않는지도 확인했다. 교체 빔의 시작 자세와 목적 구역 B의 남북 방향 내려놓기 자세에서 기존 `zone_team_footprint.pose_clear`를 통과했다. B는 0.60×1.40 m이고, 0.60×0.04 m 빔을 남북 방향으로 놓으면 가장자리 여유는 x 0.28 m·y 0.40 m다. 기존 `landing_fits`와 통로 폭 검사도 재사용했다(편대 최소 폭 0.27 m, 넓은 문 1.00 m).

레지스트리와 `ScenarioFinalV3Scene`은 `_v7` ID를 명시할 때만 v7을 읽는다. 기존 통합 workflow의 설명에 선택 방법을 추가했으며 실행기·workflow 버전·기본값은 유지했다. v7 주문 입력 검증은 상자 네 색과 long_beam만 허용한다. 예전 crate/can/tile/tri_frame 정의는 재생용으로 남긴다. 모든 v7 설정 해시와 resolved scene 해시는 각각 대응하는 v6과 다르며, 파일 해시와 구체적인 값은 [summary.json](summary.json)에 있다. 같은 기하의 XML은 시나리오 ID만 바뀌었다고 다른 기하 해시가 되어야 하는 것은 아니다.

생성 재현(다른 내용의 기존 v7 파일은 덮어쓰지 않음):

```sh
python3 experiments/2026-10-15-scenario-v7/build_v7.py
```

## 시험 기록과 한계

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_zone_study_scenarios_v7.py
```

최종 **3 passed / 실패·오류·skip 0 / 1.054초**. 세 시험은 전체 8개 설정의 교체·이전 버전 보존·정적 기하, XML fixture와 해시, 네 통신 조건(8×4)의 실제 요청 구성을 검사한다. MuJoCo·torch·물리 실행 모듈은 import 차단했다. XML은 기존 오프라인 시험과 같은 최소 robot/dispatch 템플릿을 사용하고 실제 벽·화물·복제·접촉 XML 변환을 적용했다. 네이티브 로봇 모델 전체의 컴파일 검증은 아니다.

시험 수정 전 사유 분포:

| 범주 | 건수 | 근거·수정 |
|---|---|---|
| test_vocabulary_expectation | 1 | 어휘 목록은 종류뿐 아니라 주문·화물 ID도 포함한다. 종류는 주문표에서 검사하고 어휘에는 제외된 종류가 없는지 검사하도록 시험을 수정했다. 제품 동작 결함은 아니다. |

초기 2통과·1실패, 수정 뒤 3통과, XML quaternion 검사를 더한 최종 3통과를 모두 `summary.json.test_attempts`에 원본 경로·SHA-256과 함께 보존했다. 원본은 `/Users/changmin/projects/ugrp/outputs/scenario-v7-nocrate/pytest-{initial,final,verified}.xml`에 있다. v6 파일 8개는 기준 커밋의 blob과 바이트 비교했다.

검증은 유한한 정적 검사만 수행했다. 경로 탐색·시간 상한을 새로 만들지 않았고, 계획기·거부 원장·cap_end 동작도 바꾸지 않았다. 전체 경로의 연속 sweep·동적 막힘 이후 우회·여러 화물 적재 순서는 미검증이다. Mac 물리·렌더·모델 호출·GCP 실행은 모두 0회이며 실제 파지·운반 성공을 주장하지 않는다.

## 참고 자료

- [규칙 PR #518](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/518), [실행 구조 결정 기록](../../docs/act_execution_decisions.md): 사용자 제외 결정. "s2 하나"라는 설정 현황 오류는 이번 원본 확인으로 정정했다.
- [v6 생성·보존 구조](../2026-10-14-scenario-v6/build_v6.py), [v6 기록](../2026-10-14-scenario-v6/README.md): 명시 버전 선택과 원본 보존 방법.
- [기존 슬롯·벽·화물 검사](../../harness/zone_study_scenarios.py), [기존 목적 구역·통로 검사](../../harness/zone_scenario_feasibility.py), [기존 XML fixture](../../tests/test_zone_scenario_scene.py): 새 기하 검사기를 만들지 않고 기존 함수를 재사용했다.
