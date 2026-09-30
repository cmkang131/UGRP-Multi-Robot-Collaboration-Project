# P09 — 정식6시나리오의 실행 능력 차이와 작업 분할

UGRP의 [READINESS S01/S04/S13 및 C6/C7](../READINESS.md) 후속이다. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 읽고 fetch/열린 PR을 확인한다. 감사 기준 main `a8094cc14e098a55483f53a3c49bf6a0b116043d`; 배정된 자기 worktree/codex 브랜치만 사용한다.

**범위:** 6시나리오의 정적 실현 가능성을 다시 확인하고 물건/역할/경로/사건별 지원 차이를 실행 가능한 후속 작업으로 나눈다. 이 작업은 **문서와 정적 지원표/검사만**이며 controller를 한 번에 확장하지 않는다. 물리/시뮬레이션/렌더와 비전·LLM 등 모든 모델 호출 금지. 정적 경로 계산을 실제 통과로 보고하지 않는다.

입력:

- `configs/zone_study_scenarios_v2/`, `maps/zones_final/catalog.json`
- `harness/zone_scenario_feasibility.py`, `harness/zone_final_env.py`, `docs/zone_scenario_feasibility.md`
- `harness/zone_own_executor.py::deliver`, `harness/zone_pair_executor.py::make_plan/PairTeam`, `harness/zone_study_integration.py::executor_plan`
- `scripts/run_zone_study_integration.py::host_spec`, `sim/zone_geometry_scene.py`
- `tests/test_zone_scenario_feasibility.py`, `tests/test_zone_final_env.py`
- PR #202/#255/#254와 #219–#224 이슈

확정된 시작점: M1 cyan만, M2 long_beam1개·r1/r2 고정·특정door/axis·개략 시트 범위 제한. s1/s3/s4는 혼합/다색·can/tile, s2는heavy_crate, s6는 빔90° 회전과 순서 관계를 요구한다. 지도가 읽힌다는 것만으로 지원이 되지 않는다.

완료 기준:

1. 각 시나리오의 주문 종류/개수·identity·필요 로봇 수/역할·초기 자세/정류장·경로/방향·목적지·숨은 사건/시각을 원본에서 추출한다. exact file/함수/거절 이유와 매핑한다.
2. v2 지도에서 existing feasibility evaluator를 **정적 연산만** 실행한다. import side effect를 먼저 확인한다. `maps_dir_for`를 전달하고 단독 원판·전체 편대 발자국/양방향 통과를 구분한다. 계산이 막히면 진입점과 원인을 기록하고 물리로 우회하지 않는다.
3. “이미 지원/정적 어댑터 부족/하위 제어·인식 필요/물리 미확인/설계 범위 미확정”으로 행을 나눈다. order_id≠item_id, partner r3, 색/종류별 인식, can 접근로·봉 회전, 좁은 문/넓은 문/복도 우회, 낙하 때 미파지 no-op을 빠뜨리지 않는다.
4. 기존 s1–s6는 바꾸지 않는다. 작은 dev cyan+봉 시나리오를 전체 대체로 제시하지 않는다. 각 부족 능력을1개 PR 크기의 task prompt와 fake 시험·물리 시험·SIM cap/미산정 사유로 나눈다. 같은 controller를4조건 모두 쓰게 한다.
5. 후속 physics 비용은 “기능당 정상+실패2×900초” 같은 명시적 제안과 실제 staging/경로 길이로 나눠 추정한다. static PASS를 학생 성공으로 세지 않고 모든 지원 표의 미측정 셀을 남긴다.

정적 pytest는 공용 잠금 보호로 실행하며 통과 후 커밋·push한다. 커밋 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. `--draft --repo kcm0127-dotcom/ugrp` PR에 `Refs #218, #219, #221, #223, #224`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합 금지.** 원본·기존 문서/설정 보존, Drive 없음. 한국어로6시나리오 전체 파일럿을 막는 능력과 물리 미측정 목록을 보고한다.
