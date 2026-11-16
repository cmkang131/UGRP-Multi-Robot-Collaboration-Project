# P02 — 청록 상자와 공동 봉을 한 실행에 연결

UGRP 작업이다. `/Users/changmin/projects/ugrp`에서 배정된 자기 worktree/codex 브랜치만 쓰고 AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 먼저 읽는다. fetch와 열린 PR로 중복을 확인한다. [READINESS S04/S13](../READINESS.md)의 기준은 main `a8094cc14e098a55483f53a3c49bf6a0b116043d`이며 최신 상태를 다시 확인한다.

**범위:** 새 dev scenario의 cyan1개+long_beam1개,3로봇을 하나의 host에 준비하고 독립 robot API가 같은 주문/개체를 끝까지 가리키게 만드는 계약과 가짜 포트 검사를 구현한다. 물리/시뮬레이션/렌더/모든 모델 호출 금지. 기존 s1–s6를 단순한 임무로 덮어쓰지 않는다. 이것은 전체6시나리오 지원이 아니다.

2026-09-30 명확화: 위 실행 금지는 이 작업의 로컬 실행 범위다. 정상 GitHub CI는 허용되며 기대되는 검증이다. CI를 취소하거나 커밋에 CI 생략 표시를 붙이지 않는다.

읽을 대상:

- `scripts/run_zone_study_integration.py::host_spec/placements_match`
- `sim/zone_geometry_scene.py::_resolve`, `sim/zone_cargo_scene.py`
- `harness/zone_study_integration.py::executor_plan`, `harness/zone_pair_executor.py::PairTeam/make_plan`
- `harness/zone_own_executor.py::deliver`, `harness/zone_study_inputs.py::OrderSheetSource`
- `configs/zone_study_integration/i2_pair_long_beam.json`, `configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json`
- `tests/test_zone_study_integration_pair.py`, `tests/test_zone_study_integration_seams.py`, `tests/test_zone_pair_executor.py`

현재 host_spec은 pair-only와 order_id=item_id를 강제하고, cargo 장면은 color placeholder를 지운다. M1은 cyan만, M2는 r1/end_neg·r2/end_pos만 지원한다. 이 제한을 지운 뒤 무조건 수락하는 방식은 금지한다.

구현/완료 기준:

1. 정적 `order_id → physical item_id(s)` 매핑을 분리한다. setup/eval에는 개체 위치가 있어도 runtime 공개 주문서에는 허용된 초기 slot/개략 시트만 들어가야 한다. 정확한 pose를 실시간 입력으로 넣지 않는다.
2. 새 opt-in 혼합 구성에서 cyan과 봉이 모두 준비되도록 scene spec을 만든다. 실제 World 없이 fake scene inventory로 양쪽 보존·중복ID/누락/종류 불일치 거절을 확인한다.
3. r1/r2 pair와 r3 단독 작업이 자기 API로 독립 시작/완료/실패하도록 연결한다. host가 자동으로 상대 claim을 만들거나 r3에게 GT 기반 양보 명령을 주지 않는다. pair 실패가 단독 작업을 임의 중단하지 않는지 검사한다.
4. 고정 r1/r2는 manifest에 제약으로 남기고 r3 pair/비cyan/heavy_crate/새 경로는 명시적 미지원으로 거부한다. 파트너 자유 선택을 구현한 것으로 보고하지 않는다.
5. 동일 seed·scene spec으로4조건 fake decisions를 실행해 주문/개체별 ledger·dispatch/평가 join이 보존됨을 검사한다. teacher 호출·GT/TOP 변경으로 자기 입력이 달라지면 실패다.
6. 코디네이터에게 “초기화부터 두 물건 목적지까지4조건×1800 SIM초 cap” 검증 명세를 넘긴다. 이번에는 실행하지 않는다.

P01/P03과 scene/provider 파일 소유를 먼저 나누고, 변경 관련 pytest는 공용 잠금 보호 아래 실행한다. 검사 통과 후 커밋·push, 커밋 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. `--draft --repo kcm0127-dotcom/ugrp`로 PR을 만들고 `Refs #219, #221, #223`, `## 참고 자료`, 마지막 `Generated with Codex`를 넣는다. **병합/봉인 금지**, 새 번호는 중복 확인 후에만 사용한다. raw/기존 번들 보존, Drive 없음. 한국어로 정적 연결과 물리 미검증을 구분해 보고한다.
