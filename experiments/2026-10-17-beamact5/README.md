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

## 5. 넓은 시작 교사 gate 40회 (gcp6, 2026-10-17) — FAIL 34/40

이 절은 위 4절의 남은 후속을 실행한 기록이다. **ACT 학습과 학생 카메라 기록은 하지 않았다.** 사전 등록 최소 38/40에 미달해 학생 카메라 ~166 seed 기록으로 넘어가지 않았다. gate 통과를 주장하지 않는다.

### 5.1 사전 등록과 스택

- 사전 등록 [wide-pre-registration.json](teacher/gate-40-r1/wide-pre-registration.json) sha256 `ad849ac2…`; cases [wide-cases.json] sha256 `093901ef…` (132,881 B, seeds 8420000–8420039). 층별 거리·yaw 배분은 등록 파일에 있다.
- 40 runs, 10 거리 층(D00–D09), 층마다 **8 robot starts(8 runs에 걸쳐 r1 4회 + r2 4회)**, 8 yaw bin이 로봇마다 5회, bearing은 배정 끝에서 바깥 방향 1종. gate 최소 38/40, cap 60 SIM s, 훈련 카메라 OFF, 성공은 동결 evaluator의 `physical_success`만.
- 라벨 주의: prereg/distribution의 층별 `planned_runs=4`/`actual_runs=4`는 **r1으로 등장한 run만** 센 값이다(`wide_start.py` 399–402). 실제 층별 노출은 8 runs/8 starts이며 아래 표의 분모 8이 그것이다.
- 스택: source `3170d909…`, adapter `835ccef2…`, teacher dependency `26f84d0f…`, `mjwarp_batch_v1` + `warp_native_contact_v1`(noslip 0), scene `walls_floor_contrast_v5_indigo110_s80`, gcp6 isolated, placement filter, canonical XML 재컴파일. 값은 [teacher-gate-stack-manifest.json](teacher/teacher-gate-stack-manifest.json), 사전 등록 점검은 [teacher-gate-stack-check.json](teacher/teacher-gate-stack-check.json)(`ok:true`). 40-world init preflight passed([summary](teacher/gate-40-r1/remote-hashes.json) sha `13e72836…`), native reference proof sha `f53f54aa…`.
- 카메라: 640×480, K00 619.5194540517232, remap sha `eb9b67fb…`. renderer는 `MJWarp batch RGB; known partial-alpha difference from C remains`이며 C와의 픽셀 동등성을 주장하지 않는다.

### 5.2 실행

- [summary.json.zst](teacher/gate-40-r1/summary.json.zst) 요약: `status=complete`, planned/started/completed **40/40/40**, `HOST_ERROR=0`, `beamact5_gate_eligible=true`, wall **3086.0 s**. 시간당 1.096 USD로 계산한 추정 **$0.94**(청구액 미확인).
- 첫 30 SIM초: per-world wall/SIM **1.635**(기록 전용; 경고 3.5/차단 6.0 미만). loop 1961.9 s 중 physics 451.9 s(23%), render 90.2 s, readback/remap/JPEG/kinematics 60.0 s. [first30-speed.json](teacher/gate-40-r1/first30-speed.json) sha `c0c7c49a…`.

### 5.3 결과: 34/40 FAIL

- `teacher_terminal` 36(성공 34 + handoff 실패 2), `cap_end` **4**: SIM 60 s 상한 2 + planning host wall safety cap 2(계획 tick당 30 wall s, `planning_wall_safety_cap`). driver summary의 `cap_end=2`는 60 s 상한만 센 값이고, 분석은 safety cap을 별도로 표시한다. `HOST_ERROR=0`.
- 층별 성공(로봇 시작 수, 분모 8):

|layer|성공|실패한 world(로봇)|
|---|---|---|
|D00 0.154–0.202 m|5/8|10(r1 timeout), 15(r2 safety cap), 20(r1 search timeout)|
|D01 0.205–0.305|7/8|6(r2 timeout)|
|D02 0.31–0.525|6/8|27(r2 peer approach), 37(r2 safety cap)|
|D03 0.535–0.735|8/8|–|
|D04 0.742–0.781|8/8|–|
|D05 0.785–0.824|5/8|10(r2 timeout), 15(r1 safety cap), 20(r2 peer search)|
|D06 0.835–1.08|7/8|6(r1 timeout)|
|D07 1.09–1.34|6/8|27(r1 approach blocked), 37(r1 safety cap)|
|D08 1.35–1.57|8/8|–|
|D09 1.58–1.6878|8/8|–|

- 로봇 시작 **68/80**, run **34/40**. 실패는 배정식이 묶는 세 조합(D00–D05 3 runs, D01–D06 1 run, D02–D07 2 runs)에만 있고 D03–D04–D08–D09 조합은 전부 통과했다. 원인 진단은 이 단계 범위 밖이며 아래 원장의 기록 범주만 보고한다.

### 5.4 실패 원장 (6 runs)

|world|seed|r1|r2|종료|기록 사유|blocked_object|min_gap_m|scope|
|---|---|---|---|---|---|---|---|---|
|6|8420006|teal D06 0.835 m yaw0|blue D01 0.24 m yaw7|cap 60 s, 둘 다 episode_timeout|cap_end|none:cap_end|null|행정 상한, 간격 판단 없음|
|10|8420010|teal D00 0.16 yaw1|blue D05 0.812 yaw0|cap 60 s, 둘 다 episode_timeout|cap_end|none:cap_end|null|행정 상한|
|15|8420015|blue D05 0.8 yaw5|teal D00 0.18 yaw4|safety cap 4.1 s, outcome null|cap_end(행정)|none:planning_wall_safety_cap|null|행정 상한|
|15 보조|〃|accepted path, path found, t=5.5|–|–|path_or_frontier_block|cyan_1|**-0.02024**|accepted_path|
|20|8420020|teal D00 0.18 yaw2|blue D05 0.824 yaw1|teacher_terminal 58.0 s|peer_search_handoff+search_timeout_handoff|not_observed|null|path/frontier/clearance 행 없음|
|27|8420027|blue D07 1.27 yaw6|teal D02 0.525 yaw5|teacher_terminal 22.4 s|approach_blocked_handoff+peer_approach_handoff|**red_1**|**0.01903**|accepted_path, t=19.5|
|37|8420037|blue D07 1.34 yaw7|teal D02 0.31 yaw6|safety cap 25.4 s, outcome null|cap_end(행정)|none:planning_wall_safety_cap|null|행정 상한|

- `not_observed`와 `null`은 0이 아니라 **측정/기록되지 않음**이다. world 20·27의 상대 로봇 쪽은 path/frontier/clearance 행이 없다.
- world 15의 t=5.5는 절대 world clock이고 표의 report `sim_s`(4.1 s)는 data.time 원점 기준이라 직접 비교하지 않는다([analyze_gate40.py](teacher/analyze_gate40.py)).
- 60 s 상한 2 runs는 늦은 프레임에서 끝 밴드가 보이지만(5.6절) 원장에 간격 행이 없어 원인을 배정하지 않는다. safety cap 2 runs도 물리 실패가 아니라 호스트 wall 시계 상한이다.

### 5.5 READY witness 점검 (toggle default off 유지)

- GO(ledger `ready→pick`)가 있는 로봇 **70/80**; 없는 10은 모두 실패 6 runs 소속. tail window 이전 GO 0.
- witness 승인 후 GO **2/70**: world 14 blue(witness 36.1 ≤ GO 38.3), world 28 teal(31.3 ≤ 33.4).
- GO 시점 결정: `BEAM_NOT_VISIBLE_OR_UNBOUNDED` 55/70, `FIT_UNCERTAIN` 15/70, 정렬 0/70. grip x 오차(관측 x − station_radius 0.2032) 중앙 **-0.0667 m**(최소 -0.0817, 최대 -0.0235). 정렬 프레임 8/2478, 꼬리-원장 결합 실패 16(프레임 간격 >0.05 s 또는 GO 없음).
- **정정(2026-10-18, 독립검증):** 이전 기록의 "end band 검출 70/70 null"은 **색 밴드 검출 실패의 근거로 쓸 수 없다.** GO 사유가 55/70 `BEAM_NOT_VISIBLE_OR_UNBOUNDED`, 15/70 `FIT_UNCERTAIN`이고 `FIT_UNCERTAIN`은 band 계산 **전에** 반환되므로 band null은 **선행 관문 탈락의 구조적 결과**다. band 검사를 통과한 aligned 프레임은 8/2478 존재한다. MJWarp render partial-alpha/C 대비 차이는 별개의 미확인 사항이며 이 null의 근거가 아니다.
- 판정: **이 replay로 witness를 평가할 수 없다(out of domain).** witness `_evaluate`의 x 기준은 `station_grasp_convention('masterpi_v3')['station_radius_m']=0.2032 m`인데, 이 교사 run의 ready 자세 grip x는 0.1215–0.1797 m로 기준보다 2.4–8.2 cm 안쪽이다. 판정 근거는 이 x 기준 불일치, 정렬 0/70, witness 승인 2/70(결정함수 replay)뿐이다. **검증 범위:** witness 2/70은 해시·동일 코드 대조까지만 확인했고 **재실행으로 검증되지 않았다**(기록 시점 gcp6 r3 6-world 실행 중). 따라서 2/70은 witness의 성능 수치가 아니며, **on-domain 검증(C-profile 학생 기록 또는 station 반경에 선 교사 replay)은 아직 없다.** toggle은 default off로 두고 코드/기본값을 바꾸지 않았다.

### 5.6 관측한 실패 프레임 (원인 주장 아님)

12장을 처음/중간/끝에서 골라 직접 봤다([frames/](teacher/gate-40-r1/frames/)).

- world 27: r1 t=2 장면, t=10 빔 접근, t=21에는 빨간 상자만 크게 보임. r2 t=21에는 teal 밴드가 화면을 채움. 기록은 r1 `red_1` accepted path 1.9 cm, r2 peer approach handoff.
- world 20: r1 t=2 빨간 상자 중앙, t=30 빈 바닥, t=57 빨간 상자 오른쪽. r2 t=30·t=57 파란 밴드가 중앙에 보임. 기록은 r1 search timeout, r2 peer search handoff.
- world 6: r1 t=40·t=59에 다른 로봇과 초록 빔/teal 밴드가 왼쪽 위, 오른쪽에 가까운 로봇 팔. r2 t=40·t=59 파란 밴드가 중앙에 크게 보임. 60 s 상한.
- world 10: r1 t=59 초록 빔 면이 가까이 보임. r2 t=40 파란 밴드 중앙, t=59 바닥/벽. 60 s 상한.
- world 15: r1 t=3 청록 상자가 앞에, 다른 로봇이 빔 옆. r2 t=3 teal 밴드가 가까이. 4.1 s safety cap.
- world 37: r1 t=24 빔과 다른 로봇이 멀리. r2 t=24 벽/바닥 모서리. 25.4 s safety cap.
- 전체 review-2hz/tail-10hz·상태 npz는 VM 원본에 있고 sha256은 [remote-hashes.json](teacher/gate-40-r1/remote-hashes.json)의 경로·해시로 연결했다. 위 관측만으로 실패 원인을 단정하지 않는다.

### 5.7 원본·해시

- Mac 회수 파일과 해시는 [remote-hashes.json](teacher/gate-40-r1/remote-hashes.json)에 있다. analysis JSON은 zstd 압축본 sha `e3726380…`, 해제 sha `0f24c879…`(원본과 일치 확인). summary는 zstd sha `423f55bb…`, 해제 sha `5771ce3a…`.
- run 원본 `/home/ugrp/ugrp-sim/runs/beamact5/gate-run-40-r1/`(world-000..039, adapter/raw/tail/review), cases·사전 등록 `/home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d/`. 전체 해시 목록 `artifact-sha256.json` sha `b537dc7e…`, 27,430 files(4.05 MB, Mac 미회수).
- rejection ledger 원본 [rejection_table.json](teacher/gate-40-r1/rejection_table.json) sha `7a628eaa…`; funnel requested 40→setup 40→completed 40→success 34. driver 표는 `teacher_failure` 4로 뭉치고 safety cap을 분리하지 않지만, 이 기록의 5.4절 분석 표가 사유·물체·최소 간격과 cap_end를 분리한다.
- gcp6는 이 기록 후 임대 해제·정지했고 원본은 영속 디스크에 보존한다.

### 5.8 미확인·한계

- 교사 성공은 학생 성공이 아니다. 훈련 RGB 기록·ACT 학습·학생 평가는 하지 않았다(사용자 지시 범위).
- 6 실패 중 4 runs(world 6·10·20·37의 상대 로봇 포함)는 clearance 행이 없어 `blocked_object=not_observed`, `min_gap_m=null`이다. world 15·27만 accepted path 간격이 있다.
- safety cap 2 runs는 호스트 wall-clock 행정 상한이며 SIM 시간 상한과 구분해 `cap_end`로 표시했다.
- witness 점검은 out-of-domain replay다(5.5절). band null 70/70은 선행 관문 탈락의 구조적 결과이지 색 밴드 검출 실패 근거가 아니다(정정). witness 승인 2/70은 해시·동일 코드 대조까지만 확인했고 재실행은 미검증이다. C-profile 학생 기록에서의 on-domain 재검증 전까지 witness의 작동/불작동을 주장하지 않는다.
- 층별 `planned_runs/actual_runs=4` 라벨은 r1-only다. 실제 노출은 8 runs/8 starts다.
- MJWarp와 C 결과를 합산하지 않는다. C 대비 물리·렌더 동등성, 청구 비용, 실기 전이는 미확인이다.
- 이번 gate FAIL에 대한 원인 진단·수정 후보·재실행은 하지 않았다. 다음 단계는 6 실패 run의 search23/frontier 로그 분포를 먼저 재계수해 가장 큰 원인을 정하고, 그 뒤 후보를 정하는 것이다.

### 5.9 참고 자료

- 사전 등록의 거리 분포 근거: TRAIN 배정 거리 p25/p50/p75/p95/p99와 beamdiag A/B 실측 min–max를 `wide-pre-registration.json`의 `sources`에 기록했다.
- 동결 소스: teacher tree `3170d909…`, adapter `835ccef2…`, dependency `26f84d0f…`; MJWarp contact profile `warp_native_contact_v1`(`sim/warp_native_contact.py` sha `a5c8d370…`, PR #562)과 noslip 0 규칙(AGENTS.md).
- MJWarp 공식 문서(접촉 용량·그래프 캡처): https://mujoco.readthedocs.io/en/latest/mjwarp/
- 비교 기준(합산 금지): 좁은 시작 CPU beampair7 40/40, 이전 warp 교사 gate 기록. 이번 넓은 시작 gate는 새 조건이다.
- 시연 시작 분포 원칙: ALOHA/ACT(Zhao et al. 2023), DART(Laskey et al. 2017), DAgger(Ross et al. 2011), MimicGen(Mandlekar et al. 2023), Options(Sutton et al. 1999) — 0절 표 참조.
- 내부 진단: `experiments/2026-10-16-beamdiag/`(시작 위치 분포), `experiments/2026-10-17-beamact5/analysis/ready_recount.py`(READY 오프라인 재계수).

## 6. r2 수정 묶음과 6-world 검증 (2026-10-17, gcp6) — 2/6, 40-run gate는 아직 아님

### 6.1 수정 묶음

- r1 실패 6개(6, 10, 15, 20, 27, 37)의 원인별로 default-off 모드 3개를 새 번들 `beamact5_r2`에 묶었다: `search23_rects=search23_batched_rects_v1`, `search26_circles=search26_downfirst_circles_v1`, `search26_static_peer=search26_static_peer_stance_v1`.
- 새 gate id `beamact5-teacher-gate-r2`, 같은 40 고정 시작·같은 plan(`f1a50e8c…`)·cases(`24903b69…`, candidate 필드만 다름)·min 38·cap 60 SIM s. 사전 등록·stack check는 [gate-40-r2/](teacher/gate-40-r2/), stack check `ok:true`.
- 상수(마진·cap·간격)는 바꾸지 않았다. 새 모드는 모두 default off이며 r2 켠 실행만 비교한다.

### 6.2 검증 범위

- 40-run gate를 돌리지 않고, r1에서 실패한 6 world만 같은 plan의 index로 다시 쟀다. `planned_N=6`, `gate_eligible=false`, 학습 RGB off, weld off, gcp6 isolated.
- 결과: 6 started / 6 completed / **성공 2** / cap_end 1(60 s) / HOST_ERROR 0 / wall 2010.8 s. first30 batch wall/SIM **5.866**(기록 전용, speed_gate_fail false). 원본 603 MB는 gcp6 영속 디스크에 보존.

### 6.3 결과

| world | seed | 결과 | end_reason | SIM s | 핵심 증거 |
|---|---|---|---|---|---|
| 6 | 8420006 | FAIL | cap_end | 60.0 | goal_set 행 2개: 56.1 s(209 후보, 선택 없음), 59.5 s(0°/0.203 m feasible 선택). 60 s 상한 0.5 s 전 |
| 10 | 8420010 | PASS | teacher_terminal | 45.6 | down-first circles 수정 확인, joint_held true |
| 15 | 8420015 | FAIL | planning_wall_safety_cap | 6.4 | goal_set 46행, cyan_1 최선 stance gap **14.94 mm**(+15°/0.1992 m), 관측 margin 18.75 mm. 직접 원인은 계획 tick 30 wall s 초과 |
| 20 | 8420020 | PASS | teacher_terminal | 44.4 | down-first circles 수정 확인, joint_held true |
| 27 | 8420027 | FAIL | teacher_terminal | 21.8 | goal_set 147행, red_1 stale margin 46.3–52.1 mm > stance gap 46.7 mm. 15.1/17.6/18.1/20.6/20.9 s feasible ↔ 15.0/16.0/17.0/19.0/20.0/21.0+ s 92/92 blocked_goal 진동 |
| 37 | 8420037 | FAIL | teacher_terminal | 57.5 | cyan_1 최선 sampled stance gap **4.87 mm**(-15°/0.2092 m) < 측정 바닥 margin 11.07 mm. admission은 free_goal_N 12·min_gap 0.0으로 통과 |

### 6.4 원인 → 수정 → 재검증

- **10·20 (수정 확인):** r1의 up-first 원형 탐색이 0.16–0.18 m 근접 시작을 세 번째 원에서야 잡던 문제. down-first circles로 45.6/44.4 s 성공. r2 검증에서 재현됨.
- **6 (남음):** static-peer goal set이 56.1 s에야 진입해 59.5 s에 첫 feasible stance를 골랐고 60 s 상한에 걸렸다. peer_wait/encounter deadline(47.9 s) 전에 goal set을 여는 것이 후보.
- **15 (남음):** batched rects가 r1의 30 s 소진 경로 하나를 없앴지만, 다른 계획 경로가 아직 30 wall s를 넘겨 6.4 s에 safety cap으로 끝났다. stance 자체는 14.94 mm로, 측정 바닥 margin 11.07 mm보다 크다(관측 거리 약 0.81 m 이내에서 새로 보면 통과 가능). cap이나 margin 상수를 올리는 대신 남은 비싼 경로를 찾아 batch하는 것이 먼저다.
- **27 (남음):** red_1이 신선할 때는 stance gap 46.7 mm가 floor margin 11.07 mm보다 커 feasible하지만, 조금이라도 stale해지면 margin 46.3–52.1 mm로 올라 전부 막힌다. reobserve 2회가 모두 실패했다: 2.8 s의 retreat-first는 0.6 s 경계에서 `retreat_bounded_replan`으로 끝나 camera/body view 단계에 도달하지 못했고, 14.9 s의 stale reobserve는 같은 tick에 wall layer가 활성화되며 `wall_layer_hit_miss_replan`(elapsed 0.0)로 중단됐다. wall layer 활성화가 방금 시작한 obstacle reobserve를 죽이는 순서 문제와 retreat-first 경계 문제를 함께 고치는 것이 후보.
- **37 (남음, 구조적):** sampled ±15° stance의 최선 gap 4.87 mm는 측정 바닥 margin 11.07 mm보다 작다. admission은 5 mm 기준 free_goal_N 12로 통과시켰지만 runtime은 5 mm + 3.03σ를 요구한다. 이 world는 controller tweak으로 풀 대상이 아니라 admission/runtime margin 불일치 또는 전체 91-pose certified family 평가/시작 집합 재승인 결정 대상이다.

### 6.5 gate 산술과 판정

- r1 34/40, r2에서 10·20을 고쳤으므로 40-run gate를 돌리면 최대 36/40. min 38을 넘으려면 {6, 15, 27, 37} 중 **둘 이상**을 추가로 고쳐야 한다. 6·15·27은 수정 후보가 있고, 37은 현 sampled set에서 구조적으로 막혀 있다. 최선 39/40(37만 실패)이며, 기존 통과 world의 회귀가 하나라도 있으면 38 미만이 된다.
- 따라서 이번 라운드에서는 40-run gate를 돌리지 않았다(known-bad run을 계속하지 않는다). 학생 카메라 기록·ACT 학습도 하지 않았다(사용자 지시 범위).
- 다음 라운드 후보: (a) 6 static-peer 조기 진입, (b) 15 남은 30 wall-s 계획 경로 batch, (c) 27 wall-layer abort/retreat-first view 수정 후 6-world 재검증, (d) 37은 별도 결정. 수정은 새 번들/새 gate id로 하고 r1/r2와 합산하지 않는다.

### 6.6 원본·해시·VM

- 원본 `/home/ugrp/ugrp-sim/runs/beamact5/validation-r2-6`(6 world, 603 MB). summary sha `e2417ecd…`, first30 sha `a24b6014…`, progress sha `e61b4dc3…`, artifact-sha256 sha `6eed73f8…`; world별 result sha는 [validation-r2-6.json](teacher/gate-40-r2/validation-r2-6.json)과 [rejection_table.json](teacher/gate-40-r2/rejection_table.json)의 `r2_validation`에 적었다.
- gcp6는 임대 `beamact5-teacher-gate-r2.json` 해제·실행 프로세스 0·GPU 0% 확인 후 정지했고 `TERMINATED`를 확인했다. 원본은 영속 디스크에 보존한다.

### 6.7 미확인·한계

- 6-world 검증은 40-run gate가 아니다. 34개 통과 world의 회귀 여부, 층별 분포, 전체 gate 성공률은 측정하지 않았다.
- world 15의 14.94 mm는 관측된 best stance gap이며, 실제로 그 stance에 도달해 성공한다는 뜻이 아니다. world 27의 fresh margin은 floor 값(11.07 mm)이고 실제 fresh 관측 분포는 재측정하지 않았다.
- world 37의 91-pose certified family 전체를 runtime margin으로 평가하지 않았다(admission의 free_goal_N 12는 ≥5 mm 기준).
