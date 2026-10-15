# 3대 공동 운반 화물 제외: 시나리오 v5 (2026-10-14)

사용자 원문: "3명이서 하는 짐은 뺴주라". 로봇 수(3대)는 그대로, 3대가 함께 드는 화물(`tri_frame`)만 뺀다. 구체안은 조정자 결정(사용자 미확인).

- `configs/zone_study_scenarios_v5/` 여덟 종: s1–s6은 id만 `_v5`, s7은 tri_frame 주문을 heavy_crate(2대)로 교체하고 `s7_pair_with_solo_v5`로 개명, s8은 tri_frame 주문만 삭제. v4는 바이트 그대로.
- 생성: `build_v5.py`(기존 v5 파일과 다른 내용으로는 덮어쓰지 않음). 시험: `tests/test_zone_study_scenarios_v5.py`.
- v4와 v5 결과는 합치지 않는다. 물리 실행은 하지 않았다.
- 근거: s7 원안(tri_frame 1 + 단독 2)에서 3대 화물만 2대 화물로 바꾸면 같은 슬롯·같은 자리에서 2대 운반 1건 + 단독 2건이 되어, 한 로봇이 단독 주문을 맡는 동시성이 남는다. 같은 지도의 s8 v4에 heavy_crate 경로가 이미 feasible로 있었고, s7 v5에서도 오프라인 경로 검사가 feasible이었다.
