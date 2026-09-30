# P08 — D1 정체 검출기 검토와 관찰 전용 어댑터 계약

UGRP의 [READINESS S09](../READINESS.md) 후속이다. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 읽고 fetch/열린 PR을 확인한다. 기준 main `a8094cc14e098a55483f53a3c49bf6a0b116043d`; 배정된 자기 worktree/codex 브랜치만 사용한다. **#293이 이미 D1 구현/사전 등록을 담당하므로 중복 구현하지 않는다.**

**범위:** #293 최신 head를 읽기 전용 검토하고, 승인된 인터페이스가 있다면 별도 opt-in **관찰 전용** adapter와 fake 중단 계약을 준비한다. 물리/시뮬레이션/렌더/학습과 비전·LLM 등 모든 모델 호출 금지. 실제 controller 경보/정지 기본값은 켜지 않는다. detector 수치 threshold를 개발 영상에 맞춰 다시 고르지 않는다.

출처/대상:

- `experiments/2026-09-30-stall-detection-research/README.md`, `stall_detector_offline.py`(#291)
- PR #293 `experiments/2026-09-30-stall-detector-d1/PREREG_DRAFT.md`, `d1_detector.py`, `STAGING_PLAN.md`
- `harness/zone_pair_progress_relax.py`, `harness/zone_pair_status.py`, `harness/zone_pair_executor.py`, `harness/zone_own_executor.py`
- `scripts/run_zone_study_integration.py`, `tests/test_zone_pair_status.py`, `tests/test_zone_pair_executor.py`
- #285 p2f 미무장0/208, #283 벽 접촉 양성 대조는 r2 뒷바퀴/divider이며 beam-end stall이 아니다.

완료 기준:

1. D1 입력은 자기 손목 RGB 시각과 자기 발행 명령 구간만이다. GT displacement/contact·peer frame·실제 관절을 읽을 수 없게 한다. 시작부터 막힘·기준 부족·ROI 무효·저속·짧은 명령·불연속 시각을 unknown/미검출 분모에 남기는지 검토한다.
2. #293의30정체/60정상 정의와 전체90% 기준의 시작 정체6건 문제를 검토표에 적는다. 기존18/18은 새 확증이 아니며, 보조 threshold 통과로 주 threshold 실패를 대체하지 않는다.
3. adapter는 frame_id/command window/baseline age/noise floor/state/alarm 시각을 자기 로그에 남긴다. 관찰 전용에서 명령/상태/난수 bytes가 바뀌지 않는지 검사한다.
4. synthetic alarm을 주입한 별도 fake 검사에서 자기 예정 명령 취소→hold→같은 pair enum→자기 사건→다음 LLM 결정 가능 시각을 확인한다. 이것은 실제 detector 성능이나 물리 정지 증명이 아니다. 새 enum이 필요하면4조건 공통 계약·해시를 새 버전으로 준비한다.
5. coordinator handoff에 새30/60 물리·3중단 흐름, 최종 바닥/로봇 조합,0.1초+1초 raw 캡처, 접촉 양성 대조 범위, 무장되지 않은 구간 수, 감지 뒤 복구는 별도임을 적는다. 제안 상한은90×120=10,800 SIM초와 중단3×120=360 SIM초이며, 이번 작업의 실제 SIM 비용은0이다. 기본값 활성화는 물리 검증과 독립 검토 뒤 별도 PR로 남긴다.

검사는 공용 잠금 보호 아래, pure NumPy/가짜 포트만 실행한다. 통과 후 커밋·push; 커밋 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. DRAFT PR `--repo kcm0127-dotcom/ugrp`, `Refs #216, #221, #293`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합/봉인/제어기 활성화 금지.** raw 보존·Drive 없음. 한국어로 경보 계약과 실제 감지/정지 미검증을 구분한다.
