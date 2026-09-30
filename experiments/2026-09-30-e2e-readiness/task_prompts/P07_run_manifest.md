# P07 — 실행하지 않는 E2E 계획·증거 관문 생성기

UGRP의 [READINESS §4](../READINESS.md)를 실제 검토 가능한 실행 계획으로 만든다. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 읽고 fetch/열린 PR을 확인한다. 감사 기준 main `a8094cc14e098a55483f53a3c49bf6a0b116043d`; 배정된 자기 worktree/codex 브랜치만 사용한다.

**범위:** 실행 없는 manifest/사전 등록 초안과 admission 검사를 작성한다. 물리/시뮬레이션/렌더/비전 추론/LLM 호출/worker 시작/실제 DB 생성 금지. `execute` 기능을 만들거나 승인·봉인 값을 채우지 않는다. 기존 사전 등록·bundles는 byte 보존한다.

읽을 자료:

- `experiments/2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md`(#254)
- `configs/zone_study_integration/pair_dev_DRAFT.json`, `configs/zone_study_integration/multiturn_dev_DRAFT.json`
- `scripts/run_zone_study_integration.py::run_bundle/check_run_source`, `configs/simulation_workflows.json`
- `scripts/zone_pair_v6_contract.py`, `scripts/zone_pair_authorization.py`, `scripts/zone_pair_registered_source.py`
- `harness/zone_study_contract.py`, `tests/test_zone_study_source_pinning.py`, `tests/test_zone_pair_authorization.py`
- 열린 PR #285/#292/#293 및 feature로 병합된 #294. 다른 작업의 v83/2.16.0 예약을 임의로 쓰지 않는다.

완료 기준:

1. 작은 cyan+봉 개발 연결(4조건), 정식 no-LLM24회, 본연구 초안72회 파일럿을 서로 다른 cohort/claim 범위로 나타낸다. 줄인 시나리오로 기존6종 완료를 표시할 수 없게 한다.
2. robot model·walls_v3·tag0·render/카메라·provider/모델·보정·memory·sensor OFF/ON·pair policy·map/scenario/seed·contact/weld·실효 지연·LLM/speech/budget·eval profile을 빠짐없이 해시 입력으로 묶는다. P01/P03의 지원 조합만 허용한다.
3. 모든 필수 claim에 “기존 소스/시험/결과/조건/미측정/실행 승인”을 연결한다. 단위 검사나 해시만 있으면 physical_ready가 되지 않는다. #292의 인수·#293의 detector 확증·M1/M2 최종 검증은 비어 있으면 차단한다.
4. dry-run은 순서·총 SIM cap·leader 균형·raw 목적 경로·미충족 조건만 출력한다. 알 수 없는 enum, source/map mismatch, null 필수값, false 완료, 쓰기 충돌, 이전 raw 재사용을 거절한다. dry-run이 World/worker/network를 시작하지 않음을 fake sentinel로 검사한다.
5. 최종 봉인/새 bundle 번호 예약/실제 모델 비용 승인/잠금/10GiB 검사/표준 sim_cli 실행은 코디네이터 체크리스트로 남긴다. 이 작업의 draft 생성이 실행 승인으로 읽히지 않게 한다.

공용 pytest 보호를 사용하고 검사 통과 후 커밋·push한다. 커밋 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. `--draft --repo kcm0127-dotcom/ugrp` PR에 `Refs #218, #219, #222, #223, #224`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합/봉인 금지.** raw 보존·Drive 없음. 한국어로 미충족 관문을 정확히 보고한다.
