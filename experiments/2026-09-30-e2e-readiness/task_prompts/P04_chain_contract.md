# P04 — 하나의 실행에서 단계·실패·교사 경계 연결

UGRP의 [READINESS S03–S08/S15](../READINESS.md) 후속이다. 기준 main은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`; 최신 fetch/열린 PR을 확인하고 AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 먼저 읽는다. 배정된 자기 worktree/codex 브랜치만 사용한다.

**범위:** 접근부터 목적지까지 robot/job/phase/leg/명령/프레임/receipt의 한 실행 계약을 검사하는 fake-port 통합과 누락 기록을 구현한다. 로컬 물리/시뮬레이션/렌더/모든 모델 호출 금지. 일반 GitHub CI는 정상 실행하며 취소하거나 커밋에서 생략하지 않는다. 기존 제어기 threshold·정상 물리·카메라·gate를 완화하지 않는다.

읽을 코드/기록:

- `harness/zone_pair_executor.py::PairExecution/PairTeam/m2_controller`, `harness/zone_pair_status.py`
- `harness/m2_provider_adapter.py`, `harness/zone_pair_grasp.py`, `harness/zone_pair_align.py`
- `harness/pair_chain_probe.py`, `scripts/run_m2_pair.py`, `scripts/study_owncam_pair_beam.py`
- `scripts/run_zone_study_integration.py::run_loop/write_outputs`
- `tests/test_pair_chain_probe.py`, `tests/test_zone_pair_executor.py`, `tests/test_zone_pair_status.py`, `tests/test_zone_study_integration_pair.py`
- PR #260/#265/#278/#283, `experiments/2026-09-30-door-relax-envelope/README.md`

첫 teacher lift로 시작하는 chain probe는 E2E가 아니다. 기존 controller에는 lower/open/재파지 상태가 이미 있으므로 새 FSM을 중복 작성하지 말고 현재 전이의 실제 입력/출력을 확인한다.

완료 기준:

1. fake own-port/provider/clock으로 `approach → align → close → lift → leg → lower/open → p20 새 fix → regrasp/lift → 다음 leg → destination release` 전이와 phase별 시작/종료 receipt를 검사한다. 관측을 만들어 성공 강제하는 시험은 “전이 계약 검사”로만 보고한다.
2. run/job identity, provider/PF와 command history, leg index가 이어지며 중간 teacher state replacement·GT prior reset이0임을 확인한다. student 시작 뒤 privileged world 접근은 즉시 실패하는 sentinel을 사용한다. 명령 helper `ArmSequence` import 자체를 GT 유출로 오판하지 않는다.
3. invalid/black/stale frame, 누락 heartbeat, 상대 abort, preclose 거부, own provider failure, budget 종료마다 예정 명령 취소·양쪽 정지/자기 사건·최종 실패 기록을 확인한다. GT failure receipt를 control로 되돌리지 않는다.
4. 접근/파지 미도달과 목적지 실패를 별도로 남기되 전체 분모에는 포함한다. stage PASS를 전체 PASS로 승격할 수 없게 summary schema 또는 verifier를 보완한다.
5. 코디네이터가3개 새 출발에서 실제 연쇄를 돌릴 때 저장해야 할 최소 raw/trace·허용 입력·실패 판정·SIM cap 명세를 기록한다.

P02/P03과 공유 소스를 조율한다. 검사는 공용 잠금이 비어 있을 때 보호 실행기로 수행하고 통과 후 커밋·push한다. 메시지 끝 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. `--draft --repo kcm0127-dotcom/ugrp` PR에 `Refs #219, #221, #225`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합/봉인/물리 실행 금지.** raw 보존·Drive 없음. 최종 보고는 한국어이며 전이 검사와 실제 운반 성공을 구분한다.
