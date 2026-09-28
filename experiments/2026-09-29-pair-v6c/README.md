# 공동 운반 v6c: PF fix 시계 + 파지 입장 허용오차 (2026-09-29, Claude)

**stage probe, not E2E success.** 모든 물리 결과는 PR #260 단계 probe 하네스로 단계 하나만 통과시킨 결과다. E2E 성공도, 학생 성공도 아니다.
조건: weld OFF, `cargo_noslip_v1`, 모델 호출 0. 제어기에는 정답(GT)을 넣지 않는다. GT는 staging(teacher 예외)과 `eval_only/` 판정에만 쓴다.

Refs #221. #260(단계 probe 첫 격자, v6 정책 probe)의 후속이다.

## 한 줄 요약

| 단계 | 조건 | 이전 | v6c (`b-v6c`) |
|---|---|---:|---:|
| 2 정렬 | teacher 격자 + E2E 체크포인트, E2E 정합 사전분포 | b-only **0/25** (#260 Run A) | **13/25** |
| 3 파지+들기 | 허용오차 경계, E2E 정합 사전분포 | b-only **8/23** (같은 실행) | **22/23** |
| 3 파지+들기 | 허용오차 경계, 격자 사전분포 | v5h **8/23**, b-only 6/23 (#260) | **16/23** |
| 3 파지+들기 | teacher 격자, 격자 사전분포 | v5h **17/35** (#260 grid1) | **31/35** |

- **정렬.** v6c 13/25는 #260의 진단 전용 패치(`fix_age_round`) 결과 13/25와 25건 모두 같은 판정이다. 진단으로 찾은 원인을 제어기에서 정식으로 고쳤다는 뜻이다.
- **파지 입장.** 정렬이 받아들이는 ex −12…+12 mm 전체(7셀)에서 두 사전분포 모두 들기까지 통과한다(#260에서는 ex −8, −4 mm만 통과).
  - E2E 정합 사전분포에서는 ex·ey·yaw 단일 축 15셀이 모두 통과했다.
  - 격자 사전분포(σ 0.06 m)에서는 eyaw −0.035·−0.0175 rad와 모서리 3셀이 입장 전에 거절됐다(`ENTRY:ADMISSION_SELF_UNCERTAIN`, #260 b-only와 같은 사전분포 문제). ey +4 mm 한 셀은 r2의 자기 위치 σ 검사(`std_xy`)에서 실패했다.

## 버전

| 항목 | 값 | 이유 |
|---|---|---|
| 실행 번들 | `zone-pair-v76-fixclock-grasp-entry` | 조정자 배정 번호. 2026-09-29 main 재동기화(a1307b73, #256 v77 · #257 v78 · #249 v79 병합 뒤) 이후 v76 = main v79 + opt-in `b-v6c`. v79는 `RETIRED_BUNDLE_IDS`로 옮겼고 `llm_driver.json`에 v79와 같은 프로필로 v76을 등록했다 |
| 정책 | `b-v6c` = `posterior_relook` + `exact_fix_clock` + `grasp_range_entry` | 새 플래그 2개는 opt-in. v5h·b-only·a+b·b-boot·a+b-boot 동작은 바뀌지 않음 |
| 등록 revision | `v6c` ([prereg_v6c.json](prereg_v6c.json), DRAFT, `CURRENT_REVISION`) | v6(#259, REGISTERED, 3c26acdd)와 v6b(#261 DRAFT, 15793691)는 봉인 커밋 기준 historical 감사만 한다. 재동기화 뒤 한 번 다시 봉인했다(아래) |
| workflow `zone-study-integration-run` | `2.12.0` | main 2.11.0(#249) 다음. 재동기화 커밋에서 카탈로그에 반영 |
| probe | `PROBE_VERSION 0.3.0` (`b-v6c` 추가) | workflow 행 등록은 #260처럼 보류 (`workflow_registration_pending.json`) |

### 재동기화와 재봉인 (2026-09-29, main a1307b73)

- **테스트 헬퍼.** main은 current draft가 없을 때(`CURRENT_REVISION = None`) 합성 revision(`v6-current-tree-test`, v6b 과학 필드)으로 입장 경로를 시험했다. 이제 `CURRENT_REVISION = 'v6c'`이고 `REVISION_POLICIES['v6c'] = (v5h, b-only, b-v6c)`다. 그래서 `tests/test_zone_pair_v6.py`와 `tests/test_zone_pair_registered_source.py`는 합성 revision 대신 실제 v6c 등록을 쓴다.
- **소스 폐포.**
  - #249 뒤 팀 host는 모든 지도에서 `sim/zone_masterpi_v3_scene.scene_robot_model`로 로봇 모델을 고르고, `sim/zone_model_conventions.static_spawn_keepouts`로 출발 keepout을 만든다(v2 지도는 기존 경로에 위임).
  - 그래서 두 파일을 v6c 계약 폐포에 넣었다(75 → 77 파일).
  - 장면 계약 소스 중 v6와 해시가 달라진 것은 `harness/zone_own_team_host.py`, `sim/zone_own_scene_provider.py`, `scripts/run_zone_pair_dev.py`다. v3 분기 추가만 있고 v2 경로는 같다([build_prereg_v6c.py](build_prereg_v6c.py) 허용 목록).
- **재봉인 값.** `registration_sha256` `96e8ec6897233d5beb3b8581801d9a70e786db3b0f5d3aa0aa42b40402b4d3cb`, 파일 sha256 `64acc04a8c08af61b0fa488440c70a8bec4338881c7a32b4895d4b07970ca95e`.
- **단계 probe 결과의 범위.** 위 결과는 병합 전 v76(main v70 위, b5234b7a·b534a9b5)의 것이다. 재동기화로 바뀐 것은 v6b·B7·B6·MasterPi v3 쪽 경로와 번호다. b-v6c 제어 경로 파일(`owncam_recovery_v6c.py`, `zone_pair_grasp_entry_v6c.py`, beam track·guard·grasp 훅, `owncam_recovery_v6.py`, align·global)은 바이트 그대로다. main 쪽 공동 경로 변경은 v6b 부트스트랩 훅뿐이다(`zone_own_executor.py`, `zone_pair_executor.py`). 이 훅은 `stationary_bootstrap` 정책의 제공자 상태가 없으면 아무 일도 하지 않는다. 그래도 재동기화한 소스로 물리 probe를 다시 돌리지는 않았다(조정자 지시: 이 작업에 물리 불필요).

## 문제 1: v6 b-only 정렬 relook의 음수 fix 나이

### 증상 (#260 Run A)

v6 b-only 정렬 25건이 모두 `ALIGN_RELOOK_NO_FIX`로 끝났다. 거부된 relook fix 125건 중 116건은 `fix_age_valid` 하나만 실패했다. 기록된 나이는 −6.7e-14 … −2.5e-13 s였다.

### 근본 원인

SIM 시각을 담은 float 누적값 두 개가 서로 달랐다.

- **fix 시각**은 자기 프레임의 원래 캡처 시각이다(`update(t)`의 `t`). 이 값 자체가 0.00025 s 물리 스텝을 호스트에서 누적한 값이다(예: `1.5002500000000847`).
- **PF 시계** `self.t`는 따로 누적된다. `OwnCamLocalizer.predict_to(t)`는 `min(STEP_S, t − self.t)`씩 더하다가 `self.t ≥ t − 1e-9`에서 멈춘다. 그래서 스텝 합이 `t`보다 최대 1e-9 s **앞에서** 끝날 수 있다.
- `RecoveryLocalizer.estimate`는 `fix_age_s = self.t − last_fix_t`를 반올림 없이 보고한다. 그래서 이 프레임에서 만든 fix의 나이가 음수가 되고, `accepted_fix_checks`가 거부했다.
- v5h는 `round(age, 3)`로 같은 불일치를 가렸다. #260의 진단 패치 `fix_age_round`는 이 가림을 다시 넣어 원인을 확인했을 뿐, 제어기 수정은 아니었다.

기록값으로 재현했다. 앞 fix 1.300250000000018과 프레임 1.5002500000000847로 predict하면 나이가 정확히 −6.661338147750939e-14 s다(`tests/test_zone_pair_v6c.py`).

### 수정 (`harness/owncam_recovery_v6c.py`, 플래그 `exact_fix_clock`)

나이가 아니라 시계를 고쳤다. `predict_to(t)`가 루프 자체의 허용오차(1e-9 s) 안에서 `t` 직전에 멈추면, PF 상태에 요청 시각 `t`를 그대로 붙인다.

- robot_localization `FilterBase::processMeasurement`와 같은 방식이다. 측정 시각으로 predict한 뒤 `lastMeasurementTime_ = measurement.time_`, 즉 상태 시각을 측정 시각으로 둔다.
- 건너뛰는 구간은 루프 자체의 허용오차보다 짧으므로 버려지는 운동이 없다.
- 시계는 뒤로 가지 않는다. PF 시계보다 오래된 프레임은 앞으로 당기지 않는다.
- 사후분포와 객체 정체성은 v6 그대로다. 반올림이나 clamp는 쓰지 않는다.
- 검토 반영: b-v6c로 바뀐 PF를 다른 정책이 재사용하면 `PairTeam`이 거부한다(`exact_clock_bound`).

## 문제 2: 정렬 허용오차(ex ±12 mm)와 파지 입장(ex −8…−4 mm)의 불일치

### 증상 (#260 경계 격자, v5h)

정렬 정지는 |ex| ≤ 12 mm를 받아들이지만, 바뀌지 않은 파지 입장은 ex −8…−4 mm에서만 통과했다. 실패한 로봇은 항상 r1이었다.

- ex ≥ 0: pre-close에서 빔 추정이 없어 `PREGRASP_NOT_READY`로 끝났다.
- ex −12 / ey −8 / corner++−: standoff fit이 실패했다(`PREGRASP_BEAM_UNCERTAIN`).

### 근본 원인 ([replay_boundary_entry.py](replay_boundary_entry.py)로 기록된 자기 프레임 재생)

standoff 축 fit과 pre-close 부분 관측 검사는 **v1 lime 픽셀**(hue 36–54)만 빔 윗면에 투영했다. 그런데 파지 거리에서 빔 윗면은 노랗게(hue ≈ 30) 렌더된다.

- `owncam_pair_beam_v2`가 이 현상을 이미 기록했다(dev 613). `grip_view`와 co-motion은 `beam_colour_mask`(hue 25–54, S ≥ 100, V ≥ 120)를 쓴다. 이 두 검사만 그 모델을 쓰지 않았다.
- **내린 open-jaw 자세.** 빔 색 점은 14k–28k개인데 lime 점은 60개(MIN_POINTS) 미만이다. 예외는 더 어두운 가까운 끝 면이 보이는 경우(ex ≤ −4 mm)뿐이다. 그래서 ex ≥ 0이면 `BEAM_UNCERTAIN`을 거쳐 `PREGRASP_NOT_READY`가 된다.
- **ex −12 mm standoff 관측.** 띠 너머 lime 점은 strip마다 몇 개뿐이고, 끝 면 strip에는 약 1.4k개가 있다. 그래서 두 half-fit이 0.068 rad(> 3°) 어긋났다.
- **마지막 하강 자세의 첫 프레임.** 팔이 아직 명령 PWM을 따라가는 중이었다. `grip_view_m2` 어두운 비율은 0.393(기준 0.40)이었고, 이후 프레임은 0.50–0.60이었다.

### 수정 (`harness/zone_pair_grasp_entry_v6c.py`, 플래그 `grasp_range_entry`)

게이트와 임계값은 모두 그대로 둔다(3°, 50 mm, ≥ 4 strip / ≥ 60 mm, 95 % footprint 지지, MIN_POINTS, 추적 σ·나이·segment). 증거만 바꿨다.

1. standoff edge pair와 pre-close 부분 관측에 파지 거리 빔 색 모델을 쓴다. 수직이고 더 어두운 끝 면은 V < 120으로 빠진다.
2. 띠/끝 경계에 잘린 10 mm strip은 median 지지의 1/4 미만이면 line fit 전에 뺀다(`MIN_STRIP_SUPPORT = .25`).
3. 마지막 하강 자세는 첫 READY 프레임 전에 `FINAL_DESCENT_SETTLE_S = .3` s 정착한다. 다른 자기 관측의 'settled' 규칙과 같은 값이다.
4. **정체성(검토 반영).** v1 경로에서는 lime 형태 분류기가 '잘린 빔'이라고 판정한 patch만 썼다. v6c는 색만으로는 부족하다고 보고, 빔 단면을 요구한다.
   - 추적 축에서 band 너머, 발자국 안의 빔 색 점이 필요하다.
   - 측정 구간(2–98 %) 안에서 **하나의 연속 띠**여야 한다(가장 큰 틈 ≤ 3 mm).
   - 그 가로 폭이 카탈로그 폭 0.04 m의 0.7배 이상이어야 한다.
   - 기록된 파지 자세 155장의 실제 값은 폭 0.032–0.051 m, 가장 큰 틈 0.58 mm다.

정렬을 좁히지 않고 파지 입장을 넓힌 이유는 funnel 순차 합성 원리다(Burridge, Rizzi & Koditschek 1999): 앞 funnel의 목표 집합은 다음 funnel의 영역 안에 있어야 한다. MoveIt Task Constructor pick 파이프라인도 같은 구조다. approach 단계는 거리 범위(`setMinMaxDistance(0.1, 0.15)`)를 받고, 다음 단계는 앞 단계가 남길 수 있는 범위 전체에서 시작해야 한다.

### 오프라인 재생 (#260 경계 raw `pair-stage-probes-78332709-bound`, v5h 23건 × 2 로봇)

| 증거 | standoff 프레임 실패 | 앵커 없음(로봇) | 파지 자세 부분 관측 실패 |
|---|---:|---:|---:|
| v1 lime (v5h/b-only) | 9 / 138 | 3 / 46 | 22 / 155 |
| v6c 최종 (d30381e4) | 0 / 138 | 0 / 46 | 0 / 155 |

- 파지 자세 프레임은 실제로 하강한 로봇의 마지막 하강 자세 첫 4장이다.
- 전체 출력: [replay_boundary_entry.txt](replay_boundary_entry.txt). b5234b7a에서 만든 파일이며, 정체성 검사를 넣은 d30381e4에서 다시 실행한 출력과 바이트 단위로 같다.
- 오프라인 재생은 물리 통과가 아니다. 물리 결과는 아래 격자에서 따로 본다.

## 적대적 검토 (Codex, 읽기 전용, 3회)

| 회차 | 대상 | 지적 | 조치 |
|---|---|---|---|
| 1 (task-mulh56ch) | b5234b7a | P1 색만으로 부분 관측 통과: 빔 없는 노란 바닥 표시로 닫기까지 진행 | 단면 폭 검사 추가 (1f70b1a6) |
| | | P2 b-v6c로 바뀐 제공자를 다른 정책이 재사용하면 exact clock이 남음 | 재사용 거부 (1f70b1a6) |
| | | P2 TensorBoard view 약어 없음 | `C-` 추가 (1f70b1a6) |
| 2 (task-muliinl8) | 1f70b1a6 | P1 발자국 밖 이상점·떨어진 두 띠가 폭을 만듦 | 발자국 안 + 연속 띠 (b534a9b5) |
| | | P1 넓거나 옆으로 비킨 바닥 표시 통과 | 아래 '남은 한계' |
| 3 (task-muljwydj) | b534a9b5 | P2 23k 점 중 2점의 노이즈 꼬리가 실제 빔을 거부 | 연속성은 2–98 % 구간 안에서만 (d30381e4) |
| | | P1 v6c는 빔 폭 노란 바닥 표시를 받는다(v5h는 노랑을 못 봄) | 아래 '남은 한계' |

3차 검토에서 확인된 사항:

- 1·2차 우회 재현은 모두 막혔다.
- 재생 결과는 138/138, 155/155 통과다.
- #262 병합 해소에서 회귀가 없다.
- v5h가 12 mm lime 표시를 받는다는 주장은 등록 소스 `f87921dc`에서 독립적으로 확인됐다.

### 남은 한계 (고치지 않음, 근거와 후속 작업)

단안 한 장면으로는 평면 바닥 표시와 올라온 빔 윗면(z = 0.032 m)을 구별할 수 없다(평면 모호성). 이를 풀려면 두 시점 parallax나 닫은 뒤 확인이 필요하다(Hartley & Zisserman, plane-induced homography/parallax).

[identity_marks_replay.py](identity_marks_replay.py)의 결과는 다음과 같다. 빔을 지우고, 추적 축 위 band 너머에 바닥 표시를 그렸다.

| 표시 | v5h/b-only (RestingBeamTrack) | v6c |
|---|---|---|
| lime 12 mm | 받음 | 거부 |
| lime 24 mm | 받음 | 거부 |
| lime 40 mm | 받음 | 받음 |
| 노랑 12 / 24 mm | 거부 | 거부 |
| 노랑 40 mm | 거부 | **받음** |

- 등록된 기준 경로도 같은 종류의 한계가 있고, 좁은 lime 표시에서는 더 약하다.
- v6c가 새로 받는 것은 빔 폭의 노란 표시다. 이는 노랗게 렌더되는 실제 빔 윗면을 받기 위한 대가다.
- **연구 환경에서의 영향.**
  - 정적 지도의 바닥 구역 색(`maps/zones*`)은 주황(hue 12), 파랑(108/112), 보라(143)뿐이다. 빔 hue 25–54의 바닥 표시는 없다.
  - 잘못 닫으면 들기 뒤 co-motion 검사가 `LOAD_NOT_HELD_AFTER_LIFT`로 실패를 기록한다. 성공으로 보고되지 않는다.
- 이 한계는 후속 작업(두 시점 parallax 또는 닫은 뒤 grip 확인)으로 제안했다. 이 PR에서는 해결하지 않는다.

## 문제 3 (선택): a+b r2 단안 빔 상대 인식 실패 — 진단만

#260 Run A에서 a+b 정렬 23/25가 `BEAM_RELATIVE_UNCERTAIN`으로 끝났다.

**원인.**
- r2 첫 프레임에서 상대 로봇 r1의 노란 부품이 빔 먼 끝 바로 너머에 보이고, `beam_colour_mask`에 들어간다.
- `zone_pair_relative.component_points`는 '큰' 성분(≥ 60점)이 1개 이하이면 모든 점을 유지한다. 그래서 작은 상대 로봇 덩어리가 남는다.
- 그 결과 PCA 길이가 1.54 m(lo 0.389, hi 1.926)가 되어 `SHAPE_AMBIGUOUS`/`MONOCULAR_DEPTH_AMBIGUOUS`로 끝났다. r1 시점에서는 0.667 m로 정상이었다.

**고치지 않은 이유.** 후보 수정은 작은 성분에도 `associate_component`의 결합 길이(> .66 m) 규칙을 적용하는 것이다. 이 수정에는 다음이 필요하다.
- 새 플래그와 정책 `a+b-v6c`
- 빔 자체의 작은 조각이 `ADJACENT_OCCLUDER_CANDIDATE`가 되는 회귀 검사
- 별도 물리 격자

'싸면 고친다'는 조건을 넘으므로 진단만 기록한다.

## 물리 격자 (단계 probe)

### 실행

- 실행 방법: driver 셸 스크립트를 `scripts/ugrp_session.py run`으로 띄웠다. driver는 driver PID로 `agent_lock`을 잡는다.
- 러너는 `python -m scripts.run_pair_stage_probes ... --workers 4 --execute --lock-owner claude`다. workflow 행이 등록 보류라서 `sim_cli`를 거치지 않았다(#260 README 방식).
- 모든 raw의 manifest는 `state=completed`, `source_changed=False`다.

| raw (`/Users/changmin/projects/ugrp/outputs/`) | 소스 | 인자 | 경우 | wall | 부하 평균 (시작 → 끝, 1분) |
|---|---|---|---:|---:|---|
| `pair-stage-probes-b5234b7a-v6c-align` | b5234b7a | `--stage align --sources teacher e2e --prior-std e2e --policies b-v6c --seeds 911 --nominal-seeds 911 912 913 --e2e-seeds 911 912 913` | 25 | 1477 s | 26.2 → 21.2 |
| `pair-stage-probes-b534a9b5-v6c-bound-grid` | b534a9b5 | `--stage grasp_lift --sources boundary --prior-std grid --policies b-v6c --seeds 911` | 23 | 372 s | 20.3 → 36.5 |
| `pair-stage-probes-b534a9b5-v6c-bound-e2e` | b534a9b5 | `--stage grasp_lift --sources boundary --prior-std e2e --policies b-only b-v6c --seeds 911` | 46 | 739 s | 36.5 → 51.6 |
| `pair-stage-probes-b534a9b5-v6c-grasp-grid` | b534a9b5 | `--stage grasp_lift --sources teacher --prior-std grid --policies b-v6c --seeds 911 912` | 35 | 658 s | 51.6 → 52.5 |

부하가 높았던 이유는 다른 작업의 프로세스다. 판정은 SIM 시간 기준이며 wall 시간은 비교하지 않는다.

**소스와 결과의 연결.**
- **정렬.** b5234b7a 이후 바뀐 파일(`zone_pair_grasp_entry_v6c.py`, `owncam_recovery_v6c.exact_clock_bound`, `PairTeam` 재사용 거부)은 정렬 단계 경로에 없다. 새 제공자를 쓰는 b-v6c에서 재사용 거부는 아무 일도 하지 않는다. 그래서 정렬 결과는 최종 소스에도 그대로 적용된다.
- **파지.** 파지 격자는 b534a9b5에서 돌렸다. 최종 d30381e4는 연속성 검사만 2–98 % 구간으로 바꿨다.
  - [equivalence_replay.py](equivalence_replay.py)로 세 격자의 파지 자세 프레임 958장을 두 규칙에 넣었다. 판정 차이는 0건이다([equivalence_replay.txt](equivalence_replay.txt)).

**대체된 중간 실행 (보존, 결과표에 넣지 않음).**
- `pair-stage-probes-1f70b1a6-v6c-bound-grid`(23건 완료)와 `-bound-e2e`(30/46에서 중단): 2차 검토 수정 전 소스다.
- `pair-stage-probes-b5234b7a-v6c-bound-grid.stdout.log`: 정렬 직후 driver를 멈춰 시작만 된 기록이다.
- 각 driver log에 중단 이유를 적었다.

### 단계 2: 정렬 (b-v6c 13/25)

| 출처 | 통과 | 실패 |
|---|---:|---|
| teacher 격자 (19) | 10 | `ALIGN_RELOOK_NO_FIX` 6 (r2 4, r1 2), GT yaw r1 3 |
| E2E 체크포인트 (6) | 3 | GT yaw r1+r2 3 (`v6-s912-v5h` 체크포인트 세 seed, 같은 값) |

- 음수 fix 나이로 인한 거부는 0건이다.
- 남은 `ALIGN_RELOOK_NO_FIX` 6건의 relook fix 거부 사유는 `fix_in_sweep`·`fix_gap`·`informative_fix`(20건)다. relook 스윕이 정보가 있는 fix를 못 얻었다는 뜻이며, 시계 문제와는 다른 문제다.
- GT yaw 실패 6건은 두 로봇 모두 정렬 완료로 나왔지만 평가 기준 |yaw| ≤ 0.052 rad를 넘은 경우다. r1 잔여 yaw는 여섯 건 모두 +0.053…+0.115 rad로 같은 방향이다. `v6-s912-v5h` 체크포인트는 r2도 −0.066 rad다.

### 단계 3: 파지+들기

| 격자 | 사전분포 | 정책 | 통과 | 실패 |
|---|---|---|---:|---|
| 허용오차 경계 | E2E 정합 | b-only (같은 실행, 대조) | 8/23 | `PREGRASP_NOT_READY` 11, `PREGRASP_BEAM_UNCERTAIN` 3, `PREGRASP_BEAM_UNSAFE` 1 |
| 허용오차 경계 | E2E 정합 | **b-v6c** | **22/23** | `LOAD_NOT_HELD_AFTER_LIFT` 1 (corner+−+, r2) |
| 허용오차 경계 | 격자 | v5h (#260) | 8/23 | `PREGRASP_NOT_READY` 11, `PREGRASP_BEAM_UNCERTAIN` 3, `PREGRASP_BEAM_UNSAFE` 1 |
| 허용오차 경계 | 격자 | b-only (#260) | 6/23 | `PREGRASP_NOT_READY` 10, `ENTRY:ADMISSION_SELF_UNCERTAIN` 5, `PREGRASP_BEAM_UNCERTAIN` 2 |
| 허용오차 경계 | 격자 | **b-v6c** | **16/23** | `ENTRY:ADMISSION_SELF_UNCERTAIN` 5 (eyaw−0.035, eyaw−0.0175, corner−+−, +−−, ++−), `LOAD_NOT_HELD_AFTER_LIFT` 1 (corner+−+, r2), `PREGRASP_NOT_READY` 1 (ey+4, r2 `std_xy`) |
| teacher 격자 | 격자 | v5h (#260 grid1) | 17/35 | `PREGRASP_NOT_READY` 10, `PREGRASP_BEAM_UNCERTAIN` 8 |
| teacher 격자 | 격자 | **b-v6c** | **31/35** | `ENTRY:ADMISSION_SELF_UNCERTAIN` 2 (along−/opp s911·s912), `PREGRASP_NOT_READY` 1 (yaw+/same, r2 `std_xy`), `PREGRASP_BEAM_UNSAFE` 1 (yaw−/opp, r2, 닫는 중) |

- **ENTRY 거부.** 격자 사전분포(σ 0.06 m)에서 admission이 스스로 불확실하다며 제출을 거부한 경우다. 단계가 시작되지 않았다. b-only 격자 경계에서도 같은 5건이 나왔다(#260 bound2).
- **v6c 경계 격자에서 lime 증거 실패(`PREGRASP_BEAM_UNCERTAIN`, `BEAM_UNCERTAIN`)는 0건이다.**

## raw와 해시

모든 raw는 `/Users/changmin/projects/ugrp/outputs/`에 있고 로컬에만 보관한다(원격 백업 아님). `cases.jsonl`과 `summary.json`은 이 폴더에 같은 바이트로 복사했다(`cases_*.jsonl`, `summary_*.json`).

| raw | 파일 · 크기 | `artifacts.sha256.json` | `cases.jsonl` | `summary.json` |
|---|---|---|---|---|
| `pair-stage-probes-b5234b7a-v6c-align` | 22,298 · 489M | `e01242b78469a686ad99565d23846b4de583f82cf133f2f0273d40842bd64a98` | `2805da62afdb1864eaafd43b05ed496eb8c006a7ae72ac39e053ac0bc10ac817` | `68783ace4e2f96e42ec7dc4b83706d6ccebf7a82833e61ccb47ff0b6f21d191a` |
| `pair-stage-probes-b534a9b5-v6c-bound-grid` | 3,980 · 84M | `106b9586f6bdaa549a8d2c5f049b40361f59adfc455bdb5db6de3930d6e95366` | `55b9c47d59cd28946360baca0ec22228f69af9877ee883d5109528d41397b1f3` | `fb08533147cc38a06f6ef1fa742e78031d8062016f01ff65f0353f6329c75a55` |
| `pair-stage-probes-b534a9b5-v6c-bound-e2e` | 8,419 · 178M | `a9f68abf7c927b53fd26a467cea71f5fe5fb48a031fdba824610ba59c5f25def` | `8fc97b96b1fbc56bb6bff26c84bbf5fb78e100148cf7b793e173df828a064678` | `6f6a1d804f30d117ea4eaf0bdf50f47e6fcac27fbdcfa4aa8316662ba69c48c4` |
| `pair-stage-probes-b534a9b5-v6c-grasp-grid` | 7,002 · 148M | `d2e847c47fee68b2c486be1e4205aaa3f962a78b87aa05f364e389edf25234e5` | `c2dee54b5c135dde7fff6721913875613263d8826cc9fa1cdac71e34891a4a85` | `20509d985b4d2a889e330993ac8e44da58b1b53f90a5f2bec93156a34f0d332b` |
| 대체됨: `pair-stage-probes-1f70b1a6-v6c-bound-grid` | 3,980 · 84M | `4d850055c68c3d740533036900a50c7701e3166cf9d93c1de23664d9798946ce` | `fb2e7a5a09a8d16e602e74f46503793144e952e03fd9f8e70c5a562cb6352e5b` | `0e0fc9662598d8727c93ae1c484e6d31c77cbba9c8f8fcfec9e9e6975d58af8f` |
| 대체됨: `pair-stage-probes-1f70b1a6-v6c-bound-e2e` (중단) | 5,221 · 109M | 없음(중단) | `bc7e093e9410e9709727821876a21d60d87a0505ed48ac85c7a77162e3be20ae` | 없음 |

driver log sha256:
- `pair-stage-probes-b5234b7a-v6c-driver.log`: `47762d1221efe85f09dae7bdf0357de20f87d5807dd7cf12ecaefffdaf688939`
- `pair-stage-probes-1f70b1a6-v6c-driver.log`: `775fcfe5f281e9fc937dab65484954fa53125959670f72e1f1242c459e41df45`
- `pair-stage-probes-b534a9b5-v6c-driver.log`: `15070dd7e8c66a475e0d3ec4a9e87382f3d91e126cde7ab82f5c02e68f4aad71`

## TensorBoard

- **스냅샷.** `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6c`, run 135개(경우별 129 + 그룹 집계 `ALL-*` 6). `collection.json` sha256 `2e002acbf50ffd0956d1641dc1418a7c8c3961603cfec91973d9cd56d850728e`.
- **파생 뷰.** `outputs/pair-stage-probes-tbviews-0929-v6c`(index sha256 `9e19ab270e5057fdb08bf5b74a3ea86c5794644c71a774d8d1844320bab3e9af`).
  - 빌더 `scripts/build_pair_stage_probe_views.py`, 변환기 `scripts/export_offline_audit.py`.
- **검증 1.** EventAccumulator로 135개 run의 `offline/stage_pass`, `offline/pass_rate`를 파생 뷰 값과 비교했다. 불일치 0건이다.
  - 집계 값: `ALL-C-gl-bd-b534a9b5-e2e` 0.957, `ALL-C-gl-bd-b534a9b5-grid` 0.696, `ALL-C-gl-t-b534a9b5-grid` 0.886, `ALL-C-al-t-b5234b7a-align` 0.526, `ALL-C-al-e2e-b5234b7a-align` 0.5, `ALL-B-gl-bd-b534a9b5-e2e` 0.348.
- **검증 2.** 공용 서버(PID 9291, 다른 작업 소유, 재시작하지 않음)의 `/data/runs`에 새 run 135개가 모두 있다(서버 전체 1765 run).
- **대시보드.** `outputs/tensorboard-view.json`의 `pair_stage_probes_v6c_20260929` URL. run filter `^0929-pair-stage-probes-v6c?/`로 #260 v6 스냅샷(기준선)을 함께 보인다.
- **이름.** `C-` = b-v6c, `B-` = b-only, `AB-` = a+b, 접두어 없음 = v5h. 끝의 `-pE`는 E2E 정합 사전분포다.

## 다음 막힘

1. **단계 2 정렬(13/25)이 가장 앞의 막힘이다.**
   - relook 스윕이 정보 있는 fix를 못 얻는 경우가 6건이다.
   - r1 yaw 잔여 편향(+0.053…+0.115 rad)으로 평가 yaw 기준을 넘는 경우가 6건이다.
2. **단계 3 잔여.**
   - corner+−+의 `LOAD_NOT_HELD_AFTER_LIFT`(두 사전분포 모두 r2)
   - r2 자기 위치 σ(`std_xy`) 거부 2건
   - 닫는 중 `PREGRASP_BEAM_UNSAFE` 1건
3. **단계 4(운반)·5(내려놓기).** v6c 정책으로는 아직 probe하지 않았다. #260의 v5h nominal probe만 있다.
4. **단안 파지 정체성**의 두 시점 parallax 또는 닫은 뒤 확인(후속 작업 제안).

## 참고 자료

- robot_localization, `FilterBase::processMeasurement` (측정 시각으로 predict한 뒤 상태 시각 = 측정 시각). https://github.com/cra-ros-pkg/robot_localization/blob/ros2/src/filter_base.cpp
- R. R. Burridge, A. A. Rizzi, D. E. Koditschek, "Sequential Composition of Dynamically Dexterous Robot Behaviors," IJRR 18(6):534–555, 1999. doi:10.1177/02783649922066385 (앞 funnel의 목표 ⊆ 다음 funnel의 영역)
- MoveIt Task Constructor, Pick and Place tutorial (approach `setMinMaxDistance`, `GenerateGraspPose::setAngleDelta`). https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html
- R. Hartley, A. Zisserman, *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge 2004. 평면 유도 homography와 parallax. 한 시점에서 평면 표시와 올라온 면을 구별할 수 없다는 한계의 근거다.
- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005 (#260에서 인용한 Bayes 필터 predict/update 구조).
- 저장소 내부: `harness/owncam_pair_beam_v2.py`(dev 613 파지 거리 빔 색 모델), `experiments/2026-09-28-pair-stage-probes/README.md`(#260 기준선), #262(v6 historical 감사 방식).
