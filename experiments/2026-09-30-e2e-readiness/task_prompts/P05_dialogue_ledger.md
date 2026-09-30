# P05 — 네 조건의 다회 한국어 결정·원장 계약

UGRP의 [READINESS S10/S12](../READINESS.md) 작업이다. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 먼저 읽고 fetch/열린 PR을 확인한다. 기준 감사 SHA `a8094cc14e098a55483f53a3c49bf6a0b116043d`와 최신 차이를 확인하고 배정된 자기 worktree/codex 브랜치만 수정한다.

**범위:** 실제 driver/client/request builder/scheduler를 fake wire와 fake robot port로 연결해4조건 다회 의사결정과 전송/사용량 원장을 검증한다. 물리/시뮬레이션/렌더/비전 추론/LLM 호출 금지. network connect를 막는 fixture를 써라. 실제 proxy·budget DB를 생성/리셋/수정하지 않는다.

대상:

- `harness/zone_study_llm_driver.py`, `harness/zone_main_budget.py`, `harness/zone_send_ledger.py`
- `harness/zone_study_integration.py`, `harness/zone_study_prompts_ko.py`, `harness/zone_study_protocol.py`, `harness/zone_sim_cost.py`
- `configs/zone_study_integration/llm_driver.json`, `docs/zone_study_llm_failure_rules.md`
- `tests/test_zone_study_llm_driver.py`, `tests/test_zone_study_multiturn.py`, `tests/test_zone_study_integration.py`, `tests/test_zone_study_inputs.py`
- PR #238/#245/#256; #256의 오래된 prompt 상한 불일치는 main에서 v3로 수정됐으므로 재구현하지 않는다.

완료 기준:

1. 4조건×seed%3 세 값×각 로봇2턴 이상을 결정론적 fake 응답으로 수행한다. 한국어 send→실제 inbox→자기 job 경계 이후 request→다른 claim 수락까지 같은 message/call/job ID로 추적한다. 고정 fixture 대화 이해를 실제 모델 효과라고 부르지 않는다.
2. no_comm 메시지0, leader follower간 직접전송0, structured 자유문0, literal robot/order/item/role ID 보존, pair status 설정 해시 동일을 검사한다. 공통 사건/타이머에 host GT·peer private state가 영향을 주지 않는 변이 검사를 포함한다.
3. 각 요청의 자기 JPEG·텍스트/모델설정 digest와 raw request/response bytes, transport-owned send ledger, 토큰 known/unknown, 비용·SIM release time이 일치해야 한다. 2/6과10/30 prompt의 실효 상한도 검사한다.
4. 429/503, 전송 후 응답 유실, 비정상 finish_reason, budget cap, late reply, ENOSPC를 넣는다. 실제 POST 비용 보존·비정상 응답 실행 금지·첫 송신 전 HOST_ERROR만1회 retry·송신 후 자동 재실행 금지를 현재 규칙대로 검사한다. 실패를 성공으로 덮지 않는다.
5. 새 cohort cap/model/effort/DB/path 승인·상류 usage 정산이 실제 호출 전에 필요한 항목임을 handoff에 남긴다. 실효 모델이나 남은 잔액을 과거값으로 확정하지 않는다.

기존 테스트를 읽고 필요한 검사만 추가한다. 공용 pytest 잠금 보호, 통과 후 커밋·push. 커밋 마지막 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. `gh pr create --draft --repo kcm0127-dotcom/ugrp`, 본문 `Refs #222, #223`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합/봉인/실제 송신 금지.** 기존 raw/원장 보존, Drive 없음. 한국어로 fake 검증과 실제 다회 파일럿 미실행을 분리해 보고한다.
