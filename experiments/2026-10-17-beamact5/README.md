# beamact5: READY/done 결함 수정과 교사 시작 분포 계획

작업 브랜치 `claude/beamact5`. 이번 기록은 READY/done 후보의 default-off 코드, 합성 단위 테스트, beamdiag A/B 저장 원장의 오프라인 재계수까지다. **ACT 학습/학생 평가/새 물리·렌더 실행은 없다.** 교사 게이트와 학생 카메라 기록은 후속 단계다.

## 0. SURVEY: 공개 방법과 적용

|방법|출처|이 작업에서 채택|이유/범위|
|---|---|---|---|
|실기 텔레오퍼레이션 시연 수집(ALOHA/ACT, LeRobot)|Zhao et al. 2023; LeRobot dataset docs|시연 시작 상태를 배포 시작 분포에 맞추는 원칙만 채택|학생 배포 분포(beamdiag A/B)와 TRAIN 백분위를分层 인용; 새 시연은 교사 게이트 통과 후|
|DART noisy demonstration injection|Laskey et al. 2017|미채택|상태에 노이즈를 주입해 분포를 넓히는 방법. 이번 지시는 **시작 분포만** 넓히고 교사 동작은 그대로 두는 것|
|DAgger/learner-state relabeling|Ross et al. 2011|미채택(후속 후보)|학생 롤아웃과 전문가 라벨이 필요. 이번에는 학생 평가 금지|
|MimicGen subtask transformation|Mandlekar et al. 2023|미채택|궤적 분할/변환이 필요해 hand-made near-grasp 경로 위험이 있음. 금지 조항과 충돌|
|Mobile ALOHA navigation/manipulation 분리|Fu et al. 2024|구조 참고만|이동(접근)과 조작(파지) 단계를 분리하되, 새 학습 데이터 수집은 게이트 이후|
|STRIPS/PDDL action precondition|Fikes & Nilsson 1971; PDDL|채택|READY를 학습 출력이 아니라 own 입력으로 계산되는 precondition으로 취급|
|Options/SMDP initiation set|Sutton et al. 1999|채택(개념)|READY는 execute option의 initiation condition. GO/ACK 메시지 형식은 그대로|
|BehaviorTree.CPP condition node / Nav2 condition|BehaviorTree.CPP 3.8; Nav2 BT docs|채택(패턴)|조건 노드가 참일 때만 다음 노드 진행. 기존 `zone_own_guards.py`의 own-only gate와 같은 패턴|
|Shield / correct-by-construction guard|Alshiekh et al. 2018|채택(개념)|관측 가능한 조건이 아니면 READY를 내지 않는 fail-closed gate. 물리 안전 보장 주장은 아님|

적용 원칙: 시작 분포는 **층화 할당(stratified quota)** 으로 넓히고, READY는 **own RGB 0 s 프레임 + own issued command history**로만 계산되는 조건으로 바꾼다. 학습 stage 출력은 READY **요청**일 뿐이며, 조건이 참이 아니면 무시된다. GO/ACK/TTL/delay 형식과 상수는 핀된 `GraspStartSync`를 수정하지 않는다.

## 1. READY/done 수정

- 새 default-off toggle `beamact5_ready_witness_v1` (`harness/beamact5_ready.py`).
  - 기존 calibrated `owncam_pair_beam_v2.observe_beam`의 grip/axis, 기존 T08b 상대 허용 `.012/.008/.035 m,rad`, 기존 fit 불확실성 `.05 m / 3°`, 2프레임 streak를 사용한다.
  - 배정 끝 색은 beamdiag color assay의 hue/S/V 밴드를 쓰되 **9 px 면적 상수는 전이하지 않는다**. cargo v6 band의 물리 크기(36 mm × 41 mm)와 투영 extent ≥ half-length로 확인한다.
  - 카메라 profile/640×480이 아니면 fail closed. 새 카메라의 물리적 admission을 주장하지 않는다.
- `StudentBarrier`는 READY 대기 중 원래 READY 명령을 동결하고, approach/alignment/recover가 오면 pending을 철회한다. `RearmingStartSync`는 GO 이전 철회에서도 재무장한다.
- done은 기존 `beamact4_done_recovery_v1`을 그대로 쓴다. done 다음 tick에 fresh inference를 강제하고, 철회 시 `done_times`에서 제거한다. 새 done toggle은 만들지 않았다.
- runner `scripts/run_beamact2_student.py`는 witness 결정을 `commands.jsonl`의 `ready_witness`, `internal_ready`에 남기고 `start-protocol.json`/`result.json`에 집계를 기록한다. witness가 있을 때 funnel READY는 witness가 승인한 readiness를 쓴다. `harness/beamact_replay.py`는 이미지가 없는 replay에서 witness 결정 기록의 존재/정합성을 검사하고, 없거나 모순되면 fail closed 한다(지각 재실행은 아님).

## 2. 오프라인 재계수 (beamdiag A/B)

[ready-recount.json](ready-recount.json)와 [분석 스크립트](analysis/ready_recount.py) 참조.

- 저장된 protocol audit: A/B 각 `GO_N=20`, `GO_before_joint_alignment_N=20` → 원래 GO 시각 기준 정렬 witness 승인 **0/40**.
- 두 로봇이 실행 중 각자 한 번이라도 정렬된 실행은 **4/40** (A 1/20, B 3/20). 이는 eval-truth 첫 정렬 시각을 쓴 **상한**이며 own-camera 관측성/성공 주장이 아니다.
- 정확한 후속 재-GO/ACK 시각과 실행 결과는 **계산 불가**. 조정자 21:15 허용 후 gcp2 L4를 읽기 전용으로 확인했으나, 요약이 기록한 `heldout20-v1` 원본 디렉터리가 실행 중 L4에 없고 원 출처 CPU VM `ugrp-sim-gcp2`는 TERMINATED였다(시작/정지 금지). [접근 기록](rego-access.json).
- 실행 중 물리 성공은 0/40. 기존 원장에 장애물/접촉/간격이 없어 거부 표의 `blocked_object=UNKNOWN:not_observed`, `min_gap_m=null`을 유지한다.

## 3. 검증

`python3 -m pytest -q tests/test_beamact5.py tests/test_beamact2.py tests/test_beamact4.py tests/test_beamact4_policy.py` → **18 passed, 1 skipped**. skipped는 Linux CI 전용 torch gradient 테스트다. 새 테스트는 (1) 2프레임/중복/간격/오정렬/밴드 없음/카메라 profile fail-closed, (2) pending READY 동결과 GO 이전 철회 재무장, (3) 여러 tick에 걸친 done 철회와 peer 미완료를 다룬다. [verification.json](verification.json), [JUnit XML](local-tests.xml).

## 4. 스택/충돌/금지

- 새 런/큐 없음. [stack-check-input.json](stack-check-input.json)은 저장 원장의 `replay` 선언이며 결과는 [stack-check.json](stack-check.json): `admission=historical_replay`, `current_compliant=false`. 현재 스택 적합 주장이 아니다.
- toggle 이름 충돌 검사: `beamact5_ready_witness_v1`, origin/main+origin/codex+origin/claude 259 refs, matches 0.
- 보호 미추적 파일(`COORDINATOR_NOTE.md`, `experiments/2026-10-16-beamact3/C1-*.py`, `experiments/2026-10-16-beamdiag/`, `scripts/C1-evaluate_beamact3c.py`) 수정 0. gcp 명령/VM 시작/임대/학습/추론/렌더 0.
- 남은 후속: 교사 시작 분포 확장 → gcp6 교사 gate 40회(훈련 카메라 OFF) → 통과 시에만 학생 카메라 ~166 seed 기록. 이번 기록은 그 권한을 주장하지 않는다.
