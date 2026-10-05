# 시나리오 v3: 화물 목록 전체와 3대 운반 (2026-09-29)

요청: "3대 동시 운반 같은 것도 해야 하지 않나" → 화물 목록(`sim/zone_cargo.py`) 기준으로 시나리오를 재구성한다.

## 진단
v2 여섯 종의 주문 종류는 cyan·red·green·can·tile·long_beam·heavy_crate다. **yellow와 tri_frame(3대 필요)은 어느 시나리오에도 없었고**, 필요 인원이 3인 주문이 없었다. 문서에도 "현재 6종에는 사용하지 않음"으로 남아 있었다.

## 변경
- `configs/zone_study_scenarios_v3/`: v2 여섯 종(내용 동일, `scenario_id`만 `_v3`) + `s7_trio_rendezvous_v3` + `s8_mixed_tiers_v3`. v1·v2 파일은 바꾸지 않았다.
- 생성: `build_v3.py`(기존 파일과 다른 내용으로는 덮어쓰지 않는다).
- 테스트: `tests/test_zone_study_scenarios_v3.py` 10개. 여덟 종 검증·seed 유일·지휘자 순환·v2 동일성·모든 화물 종류와 필요 인원 1/2/3 포함·새 시나리오의 경로 feasible·0.5 m 문 지도에서 tri_frame `infeasible` 음성 대조.

## 설계 근거
- s7·s8은 두 문 지도 `zone_wide_two_doors_final_v1`에 둔다. tri_frame 편대(폭 0.889 m)는 폭 1.0 m 문만 지난다(PR #169 B2).
- 큰 물건은 문 앞이 아니라 슬롯 안쪽에 둔다(PR #169 B8).
- 숨은 사건은 넣지 않았다. 삼자 편대는 이미 한 대의 지연이 전체를 세우므로 사건 없이도 협상이 필요하다. 사건 변형(예: 삼자 중 한 대 지연)은 3대 실행기가 생긴 뒤 새 버전으로 더한다.

## 검증 범위
- 실행: `pytest tests/test_zone_study_scenarios_v3.py` 10 passed(오프라인, 정적 지형·설정만). `validate` 전 항목 통과, 새 두 시나리오의 모든 물건 경로 `feasible`.
- **하지 않은 것:** 시뮬레이션·물리 실행·모델 호출. 삼자 운반의 물리 성공, 자기 카메라 3대 실행기, 자기 카메라로 본 vertex 파지. 이 시나리오는 3대 실행기가 없어 아직 실행할 수 없다.
- 본연구 사전 등록 초안(#254)은 여섯 시나리오 기준이다. 시나리오 수가 여덟이 되면 블록 수(18의 배수)와 표본 계산을 고정 전에 다시 해야 한다.
