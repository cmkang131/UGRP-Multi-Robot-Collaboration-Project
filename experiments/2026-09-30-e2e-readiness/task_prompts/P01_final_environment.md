# P01 — 최종 지도·장면·제공자 등록 연결

UGRP의 E2E 준비 작업이다. 저장소 `/Users/changmin/projects/ugrp`의 main에서 **배정된 자기 worktree/codex 브랜치만** 사용한다. AGENTS.md, CONTRIBUTING.md, README.md, docs/current_status.md를 먼저 읽고 fetch/열린 PR로 중복 작업을 확인한다. 기준 감사는 `a8094cc14e098a55483f53a3c49bf6a0b116043d`, [READINESS S01](../READINESS.md)이다. 최신 코드에서 이미 해결됐다면 재구현하지 말고 검증한다.

**범위:** 최종 지도3개가 같은 static-map resolver를 통해 scenario validator·공개 지도·표준 Scene 선택·provider 설정·실행 bundle에 연결되도록 파일/설정 계약을 구현한다. 물리/시뮬레이션/렌더/비전 추론/LLM 호출은 금지한다. Scene/World 생성 없이 dict·가짜 factory로 검사한다. 기존 지도·실험·봉인 bytes와 기본값은 보존한다.

읽을 파일:

- `maps/zones_final/catalog.json`, `harness/zone_final_env.py`, `configs/zone_study_scenarios_v2/`
- `sim/zone_geometry_scene.py`, `sim/zone_masterpi_v3_scene.py`, `sim/zone_own_scene_provider.py`
- `configs/zone_study_integration/pose_providers.json`, `harness/vision_pose_source.py`
- `scripts/run_zone_study_integration.py::run_bundle`, `harness/zone_study_scenarios.py`
- `tests/test_zone_final_env.py`, `tests/test_zone_study_integration_seams.py`, `tests/test_zone_study_source_pinning.py`
- PR #255, #249; `experiments/2026-09-28-final-map-scenario-v2/README.md`

현재 단절은 geometry `MAP_IDS`와 vision provider가 문1개 v2만 받으며, run_bundle의 `validate/bundle_for`가 `maps_dir_for()`를 전달하지 않는 것이다. 로봇 모델v3 장면 ID는 별도로 존재한다. 벽v3와 로봇v3를 혼동하거나 v2 보정의 재사용 적합성을 가정하지 않는다.

할 일과 완료 기준:

1. map_id→파일→정적 hash→scene class→robot model→provider/보정 지원의 단일 설정 계약을 만든다. 미검증 모델 조합은 명시적으로 거부한다. P03 소유자와 provider 등록부를 동시에 수정하지 않는다.
2. 원래3지도/6시나리오 해시는 유지한다. 새 모델 조합이 필요하면 새 버전 파일로 준비하고, 물리 검증 전 `research_result:true`를 만들지 않는다.
3. 정적 시험에서3지도/6시나리오의 일치, 알 수 없는 지도, 잘못된 map/model/hash, 표식 있는 map을 무표식 provider에 주는 반례를 검사한다. 현재 성공한 v2/옛 태그 경로의 입력 bytes는 유지한다.
4. renderer·World·worker·network를 호출하면 실패하는 fake-seam 검사를 넣는다. `zone_final_env`는 정적 검사지만 기존 테스트 전체의 side effect를 읽고 실행 범위를 선정한다.
5. 코디네이터용3×30 SIM초 reset/초기 충돌/카메라 검증 계획과 남은 v3 보정 항목을 기록한다. 물리 통과라고 쓰지 않는다.

공용 pytest는 `scripts/run_ci_tests.py`의 잠금 보호를 재사용한다. 다른 작업 잠금이 있으면 우회하지 않는다. 변경 관련 검사가 통과한 뒤 커밋하며 메시지 마지막은 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`이다. push 후 `gh pr create --draft --repo kcm0127-dotcom/ugrp`, 본문에 `Refs #218, #223`, `## 참고 자료`, 마지막 `Generated with Codex`를 넣는다. **병합 금지.** bundle/workflow 변경 시 main+열린 PR 번호를 확인하며 봉인은 코디네이터에게 남긴다. 결과는 로컬 기록, Drive 없음. 최종 한국어로 변경·검증·물리 미확인 범위를 짧게 보고한다.
