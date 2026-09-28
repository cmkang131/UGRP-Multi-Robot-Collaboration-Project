# 공동 운반 단계별 probe 하네스와 첫 격자 (2026-09-28, Claude)

**stage probe, not E2E success.** 모든 출력에 `stage_probe`, `not_e2e_success`, `dev`, `연구 결과 아님` 라벨이 붙는다.
단계 하나의 통과는 E2E 성공이나 학생 성공이 아니다. weld OFF, `cargo_noslip_v1`, 모델 호출 0.

Refs #221. #259(v6 dev 13회 연속 파지 전 실패)의 후속이다.

## 왜 만들었나

사용자 요청(2026-09-28): "왜 자꾸 E2E로 테스트 하는 거야? 짧게짧게 테스트 못해보나".

- dev05–14와 v6 dev 코호트는 13회 연속 E2E로만 시험했다. 한 번에 3–15분이 걸린다.
- 앞 단계가 실패하면 뒤 단계는 한 번도 실행되지 않는다. 예: v6의 A 플래그(빔 기준 상대 정렬)는 물리에서 한 번도 돌지 않았다.
- 이 하네스는 **단계 하나만** staged state에서 시작해 실행한다. 여러 경우를 병렬로 돌려 단계별 통과율을 본다.

## 설계

진입점: `scripts/run_pair_stage_probes.py` (workflow `pair-stage-probes` 0.1.0). 순수 로직: `harness/pair_stage_probe.py`.

| 단계 | 진입 상태 (제어기 자체 상태) | 끝 (제어기 전이) | SIM 예산 | GT 판정 (eval only) |
|---|---|---|---:|---|
| 1 출발 부트스트랩 | — | — | — | **구현하지 않음.** `claude/zone-pair-v6-boot`가 만든다. 연결 지점만 등록: `owncam_bootstrap_v6b.enable_bootstrap(provider, now)` / `bootstrap_fix(report)` |
| 2 정렬 | `align_start` (접근 끝 pre-station) | `_queue_grasp` 호출 = 자기 판단 "aligned" | 110 s | 각 로봇 grip 오차 \|x−0.162\|≤17 mm, \|y\|≤12 mm, \|yaw\|≤0.052 rad |
| 3 파지+공동 들기 | `pregrasp_standoff` (station) | `_wait_carry` 진입 = 자기 co-motion 확인 뒤 | 60 s | 두 로봇 양 jaw 모두 빔 접촉, 빔 중심 ≥3 cm 상승, 기울기 ≤10° |
| 4 운반 첫 구간 | `wait_carry` (teacher가 든 빔) | `_wait_lower` 진입 = 경로 구간 끝 | 90 s | 계속 들림(≥3 cm), 기울기 ≤10°, 양 jaw, 이동 거리 오차 ≤10 cm |
| 5 내려놓기 | `wait_lower` (teacher가 든 빔, 마지막 구간) | 두 로봇 `done` | 60 s | 빔 바닥(≤5 mm), 기울기 ≤3°, jaw 비접촉, 끌림 ≤5 cm |

GT 기준은 개발 가설이다. raw 지표를 함께 저장하므로 다른 기준으로 다시 판정할 수 있다.

### 한 경우의 흐름

1. **Staging (설정 전용, teacher 예외).** 표준 `Scene`(`DockTaggedCargoZoneScene`, `make_scene` 재사용)의 `setup_only.spawns`를 world 생성 전에 바꿔 r1/r2를 놓는다. 빔은 `team_cargo` pose로 놓는다.
   - 4·5단계는 teacher가 GT grip으로 IK를 풀고 열기→하강→닫기→들기를 한다. 명령은 각 로봇 **자기 port**로 발행되어 자기 명령 이력에 남는다.
2. **사전분포.** 첫 자기 프레임 전에 PF를 명시한 가우시안 사전분포로 초기화한다(ROS amcl `initial_pose`/`initial_cov` 방식).
   - **사전분포는 fix가 아니다.** fix 시각을 만들지 않는다. fix는 이후 자기 RGB 관측으로만 생긴다.
   - teacher 격자: 평균 = 정적 order sheet로 계산한 계획 pose(2단계는 pre-station, 3–5단계는 station), σxy 0.06 m, σyaw 0.05 rad.
   - E2E 체크포인트: 평균·σ = 그 순간 로봇이 **스스로 기록한** PoseReport.
3. **정지 관측 창.** 1.5 s 동안 fold 자세로 자기 프레임을 받는다(PF가 태그로 fix 가능).
4. **제출.** 두 로봇이 각자 `pair_carry`를 제출한다(실제 admission 통과 필요). 거부되면 `ENTRY:ADMISSION_*`로 기록한다.
5. **단계 진입.** 실제 `m2_controller`(v5h, 변경 없음) 인스턴스의 첫 제어 tick에서 진입 상태로 바꾼다. 필요한 값은 자기 입력에서 채운다.
   - 2단계: `claims['at_prestation']` = 자기 PF 추정. 이는 원래 `_wait_approach`의 barrier GO 뒤 hand-off와 같다.
   - 3단계: `pregrasp_done`, `grasp_estimate` = 자기 report. `pregrasp_started_at` = 정지 관측 창 시작.
     - 자세 = 정적 규칙 `look_posture(0.162)` = `inspect`.
     - `grip_base` = standoff 자세에서 **자기 RGB** `observe_beam`. 안 보이면 `ENTRY:GRIP_NOT_OBSERVED_AT_STANDOFF`.
   - 4·5단계: `grip_base` = 정렬 목표 상수 (0.162, 0). 이는 GT가 아니다. hold anchor는 진입 시 자기 프레임으로 잡는다.
6. **단계 끝.** 끝 전이가 불리면 그 로봇은 `probe_exit_*` 상태에서 멈추고 단계에 맞는 STATUS enum을 계속 보낸다. 상대가 끝나거나 실패하면 종료한다.
   - 판단 근거는 제어기 자기 상태뿐이다. GT는 종료·판정 신호로 제어기에 가지 않는다.
7. **판정.** 통과 조건: 두 로봇이 모두 끝 전이에 도달하고, 단계 안 실패가 없고, GT 기준을 만족한다.
   - GT는 20 Hz 관측기(`eval_only/trace.jsonl`)와 끝 순간 스냅샷에서만 읽는다.
   - 로봇이 **자기 끝 전이 뒤에** 한 행동과 `EPISODE_END` 취소는 단계 밖으로 본다.

### 입력 경계 (AGENTS.md)

- 제어기 입력: 자기 손목 RGB, 정적 지도·보정·coarse order sheet, 자기 발행 명령, STATUS enum, 명시한 사전분포.
- 초음파는 어떤 번들에도 연결되어 있지 않다. 여기서도 끈다.
- GT·접촉·빔 pose는 staging과 eval-only 관측기에만 쓴다. 단계 전환·성공 통보·행동 보정에는 쓰지 않는다.
- 단계 진입 wrapper는 제어기 인스턴스의 `tick`과 끝 전이 메서드 하나만 감싼다. 제어 로직·임계값·guard는 그대로다.

### 병렬·자원

- 경우마다 별도 subprocess(`OMP_NUM_THREADS=2`)로 실행한다. 기본 4 worker.
- 경우마다 자기 프레임 JPEG 전부, 명령, STATUS, controller 이벤트, eval-only trace를 보존한다. 파일 해시는 `artifacts.sha256.json`에 있다.
- `--execute`의 전제 조건: `agent_lock` 보유, 추적 소스 clean, 주 checkout `outputs/` 절대 경로. 이 조건이 없으면 plan만 출력한다. plan 모드는 MuJoCo를 import하지 않는다(테스트로 확인).

## 첫 격자 결과 (merged main v5h 제어기, stage probe, not E2E success)

### 실행 조건

| 항목 | 값 |
|---|---|
| 2·3단계 격자 | 소스 `2aa03454` (clean, `source_changed=false`), 76 cases, 4 worker × `OMP_NUM_THREADS=2`, 총 wall 3716 s (62 분) |
| 4·5단계 확인 | 소스 `4237b182` (clean), nominal 1 case씩, 2 worker, 81 s |
| raw | `/Users/changmin/projects/ugrp/outputs/pair-stage-probes-2aa03454-grid1/` (622 MiB, 29,745 파일) |
| raw 4·5단계 | `/Users/changmin/projects/ugrp/outputs/pair-stage-probes-4237b182-s45/` (8.2 MiB) |
| 공통 실행 기록 | `sim_cli workflow run pair-stage-probes`, `*-managed/manifest.json` |
| 잠금 | `agent_lock` owner claude. 격자 동안 보유했고 끝난 뒤 해제했다 |
| 부하 | 부하 평균 시작 34 → 끝 56. 도중 최대 90이며 다른 작업이 원인이다. SIM 시간 동기 모드다. wall은 참고값이다 |
| 무게·접촉 | weld OFF(`eq_active` 0 확인), `cargo_noslip_v1`, timestep 0.25 ms, noslip 10 |
| 기준 배치 | v6-s911과 같다. 실제 빔 (1.0, 0.05, 0), coarse sheet (1.0, 0.0, 0). 실제 빔이 sheet보다 5 cm 옆에 있다 |

### 단계별 통과율

| 단계 | 경우 수 | 통과 | 가장 많은 실패 | 단계 SIM s (중앙값) | wall s/경우 (중앙값, 최대) |
|---|---:|---:|---|---:|---|
| 1 부트스트랩 | — | — | 구현 안 함 (`claude/zone-pair-v6-boot`) | — | — |
| 2 정렬, teacher 격자 | 35 | **0** | `ALIGN_RELOOK_NO_FIX` | 21.2 (2단계 전체) | 273, 619 |
| 2 정렬, E2E 체크포인트 | 6 | **0** | `ALIGN_RELOOK_NO_FIX` 6/6 | 〃 | 〃 |
| 3 파지+공동 들기 | 35 (셀 17) | **17 (48.6 %)**; 셀 기준 8/17 | `PREGRASP_NOT_READY` 10, `PREGRASP_BEAM_UNCERTAIN` 8 | 4.1 (통과 7.0) | 73, 127 |
| 4 운반 첫 구간 | 1 (nominal) | 0 | `POSE_UNCERTAIN` (운반 시작 2.8 s) | 2.8 | 54 |
| 5 내려놓기 | 1 (nominal) | 1 | — | 8.75 | 80 |

- seed는 PF 난수만 바꾼다. 물리 배치가 같은 seed 반복은 결과가 모두 같았다. 독립 증거로 세지 않는다. 3단계는 셀 기준 8/17이다.
- E2E 한 번이 3–15분이었다. 이 하네스에서 한 단계는 SIM 2–30 s, 이 부하에서 wall 40 s–10분이다.
  - 부하가 낮았던 사전 smoke에서 정렬 1건은 103 s였다.

### 2단계 정렬: E2E 실패를 20–30 SIM s 안에 재현

- E2E 체크포인트 6건(v6-s911-v5h·v6-s912-v5h × seed 3개)이 모두 `ALIGN_RELOOK_NO_FIX`로 끝났다. 진입 뒤 19.6–25.6 SIM s였다.
  - s911 E2E는 align_start 뒤 23.2 s에 같은 코드로 실패했다.
  - s912 E2E는 `ALIGN_RELOOK_FIX_EXPIRED`(57 s 뒤)였다. probe는 같은 재관측 실패 계열이지만 코드와 시각이 다르다.
- teacher 격자 35건도 0 통과다. 근본 원인은 동시각 `PARTNER_ABORT`를 뒤로 뺀 기준으로 셌다.
  - `ALIGN_RELOOK_NO_FIX` 32, `PAIR_COLLISION_GUARD` 4, `ALIGN_RELOOK_TIMEOUT` 4, `ALIGN_RELOOK_FIX_EXPIRED` 1.
  - 원 행 2건은 `PARTNER_ABORT`로 기록됐다. 이 tie-break는 `4237b182`에서 고쳤고 원 raw는 보존했다.
- **기전.** 먼저 실패한 로봇의 41건 중 36건이 **두 번째** 재관측에서 실패했다.
  - 첫 재관측은 진입 시 `align_entry`다. 두 번째는 fix 공백 6 s(`fix_gap`)이며 빔 쪽으로 다가가는 도중에 온다.
  - 마지막 fix 거부에는 41/41 모두 `std_xy`가 들어 있다. 실패 시각 σxy 중앙값은 0.114 m다(요구 ≤0.05).
  - v5h 재관측은 `begin_relocalization`으로 PF를 새로 만든다. report가 초기화 전 상태가 됐다가 태그만으로 전역 재초기화된다.
  - nominal s911 r1에서는 첫 재관측이 태그 8개로 σ 0.046 m까지 줄었다(통과). 7.6 s 뒤 두 번째는 태그 7–8개가 보여도 0.083 m에 머물러 거부됐다.
- 실패 순간 GT를 보면 두 로봇 82개 중 2개만 GT 정렬 기준 안에 있었다.
  - grip x 오차 중앙값 7.6 cm(최대 13.3 cm)가 남아 있었다. 로봇은 아직 빔으로 다가가는 중이었다.
  - 횡 오차 중앙값은 6 mm였다.
  - 즉 정렬 제어 자체보다 **6 s마다 멈추고 PF를 버리는 재관측**이 먼저 단계를 끝낸다.
- 섭동(앞뒤 ±4 cm, 옆 ±4 cm, yaw ±3°, 모서리)은 결과를 바꾸지 못했다. 모든 셀이 같은 실패 계열이다.

### 3단계 파지+들기: align 허용 경계 안에서도 절반이 실패

통과 셀: nominal, 옆 +8 mm(같은/반대 부호), yaw ±0.035 rad(같은/반대), 모서리 ++/반대. 통과는 모두 7.0 SIM s에 끝났다.
빔 중심은 5.9 cm 올라갔고, 기울기는 ≤0.14°, 두 로봇 양 jaw가 모두 접촉했다.

| 실패 셀 | 결과 | 원인 (자기 입력 기준) |
|---|---|---|
| 앞 +12 mm(grip 0.146 m), 모서리 ++/같은, 모서리 −−(같은·반대) | `PREGRASP_NOT_READY` 10 | pose 검사는 전부 통과했다. 저장된 자기 프레임으로 오프라인 재평가하면 열린 jaw 확인 `grip_view_m2`의 dark fraction이 0.36–0.37로 기준 0.40에 못 미친다(nominal 0.43). |
| 뒤 −12 mm(grip 0.171 m), 옆 −8 mm | `PREGRASP_BEAM_UNCERTAIN` 8 | r1(end_neg)의 standoff 빔 fit(`standoff_estimate`)이 거부됐다. r1은 이 시야에서 빔 점 1.1–1.9천 개를 보고, r2는 8.8–10.6천 개를 본다. |

- 이 섭동은 모두 v7 설계 축 D의 **align 허용 경계**(±12 mm/±8 mm/±0.035 rad) 위다.
- 따라서 정렬이 "aligned"라고 멈출 수 있는 자세의 절반에서 파지 단계가 거부한다. 단계 사이 허용오차가 서로 맞지 않는다는 뜻이다.
- 아직 E2E에서는 한 번도 보이지 않은 병목이다. 정렬을 고쳐도 다음에 여기서 막힐 가능성이 크다.
- E2E 체크포인트는 만들 수 없었다. 두 로봇이 모두 `pregrasp_standoff`에 들어간 E2E 실행이 없다(s912는 r2만 들어갔다).

### 4·5단계 (nominal 각 1건, 격자 아님)

- **운반**: teacher가 든 빔으로 carry barrier GO까지는 정상이었다. 2.8 SIM s 뒤 r1이 `POSE_UNCERTAIN`으로 멈췄다.
  - 운반 중에는 태그를 볼 수 없다. PF의 yaw σ가 정지 중에도 확산해 0.052 rad(적재 gate 3°)를 넘었다. 마지막 fix는 5.3 s 전이었다.
  - E2E에서 파지 전 재관측 fix부터 운반 시작까지는 이보다 길다(standoff·하강·닫기·들기 ≈ 7 s). 같은 문제가 있을 가능성이 높다. 1건 관측이며 격자로 확인하지 않았다.
- **내려놓기**: 통과. 빔이 바닥에 놓였고(높이 −0.6 mm), 기울기 ≈0°, 양 jaw 비접촉, 끌림 0.02 mm.

### 사전 smoke (소스 커밋 전, 기록용)

- `/Users/changmin/projects/ugrp/outputs/pair-stage-probes-smoke-precommit-20260928/` (32 MiB, `artifacts.sha256.txt` sha256 `6ac9d5a0…`).
- 커밋 전 코드로 돌렸다. 결과 근거로 쓰지 않는다. 하네스 디버깅 기록이다.
  - 정렬 nominal 103 s 실패 재현, 파지 nominal 통과.
  - 운반·내려놓기 첫 시도는 teacher staging의 포트 시계 역행으로 HOST_ERROR였다. 두 번째 시도는 PF 확산으로 admission `SELF_UNCERTAIN` 거부였다. 둘 다 고친 뒤 위 결과를 얻었다.

### TensorBoard

- 스냅샷: `/Users/changmin/projects/ugrp/outputs/tensorboard/0928-pair-stage-probes`
  - run 83개: 경우별 78개 + 그룹 집계 `ALL-*` 5개. `collection.json` sha256 `c5fdb727…`.
  - 변환기 `scripts/export_offline_audit.py`, 파생 뷰 빌더 `scripts/build_pair_stage_probe_views.py`.
  - 파생 뷰 `outputs/pair-stage-probes-tbviews-0928` (index sha256 `dfc84ea2…`).
- 검증 1: 78개 경우 run을 EventAccumulator로 다시 읽었다. raw `cases.jsonl`의 통과 여부·단계 SIM s와 불일치 0건이다.
- 검증 2: 공용 서버(PID 9291, 다른 작업 소유, 재시작하지 않음)가 83 run을 제공한다. API 값이 raw와 같다.
  - `ALL-gl-t` pass_rate 0.4857.
  - `al-e2e-s911-v5h-s911` sim_s 21.6.
- 대시보드: `outputs/tensorboard-view.json`의 `pair_stage_probes_20260928` URL.
  - 서버 전체 run이 500개를 넘어 새 run은 자동 선택되지 않는다. 왼쪽 run 목록에서 선택해야 한다.
- 이름 규칙: `<단계>-<출처>-<셀>-s<seed>`.
  - 단계: `al`=정렬, `gl`=파지+들기, `ca`=운반, `sd`=내려놓기.
  - 출처: `t`=teacher 격자, `e2e`=E2E 체크포인트.

## 남은 위험·한계

- **E2E 체크포인트는 부분 재구성이다.** 차체·빔 pose와 servo 명령만 되살렸다. 바퀴·관절 속도, PF 입자, 상대 로봇의 진행 상태는 되살리지 않았다.
  - 앞으로 E2E 실행기는 단계 전이마다 `mj_getState(mjSTATE_INTEGRATION)`와 PF 입자를 저장해야 완전 재현이 된다.
- **3단계 진입은 pregrasp 재관측 sweep을 정지 관측 창으로 대신한다.** fix 시각 조건(`fix_in_sweep`)은 관측 창 시작 시각 기준이다.
  - `grip_base`는 standoff 자세의 자기 RGB 한 장이다. 실제 흐름에서는 정렬의 aligned 프레임 두 장이다.
- **4·5단계는 teacher가 GT grip으로 든 빔에서 시작한다.** 제어기의 grip 믿음은 상수 (0.162, 0)이다.
  - admission의 `holding` 응답은 job 기록 기반이라 teacher가 닫은 뒤에도 'no'로 남는다. 제어 입력은 아니며 기록으로만 남긴다.
- **GT 기준은 개발 가설이다.** 이번 2·3단계 실패는 모두 제어기 자기 판단 단계에서 났다. 그래서 GT 기준이 판정을 가른 경우는 없다.
- 격자는 기하 섭동만 다룬다. 조명·가림·상대 로봇 지연, v7 설계의 축 A–C(출발 지연·속도 gain·팔 yaw 편향)는 없다.
- wall 시간은 부하 34–90인 공유 호스트에서 쟀다. 성능 지표가 아니다.
- 2·3단계 격자 wall이 62분이었다. 요청한 약 60분을 조금 넘었다. 부하가 낮으면 약 1/3로 준다(smoke 103 s 대 격자 중앙값 273 s).

## 참고 자료

- robomimic `EnvRobosuite.reset_to(state)`: 저장한 MuJoCo flattened state로 `sim.set_state_from_flattened` 뒤 `sim.forward()`. 데모의 임의 시점부터 재생·평가하는 표준 방식이다.
  - https://github.com/ARISE-Initiative/robomimic/blob/master/robomimic/envs/env_robosuite.py
  - `robomimic/scripts/playback_dataset.py`
- MuJoCo 문서, Simulation → State / State manipulation: `mj_getState`/`mj_setState`와 `mjSTATE_INTEGRATION`. 같은 integration state의 두 mjData는 이후 결과가 같다.
  - https://mujoco.readthedocs.io/en/stable/programming/simulation.html
- ROS amcl `initial_pose_*`/`initial_cov_*`: 사전분포로 입자를 초기화한다. 전역 초기화는 사전 정보가 없을 때만 쓴다.
  - https://wiki.ros.org/amcl
  - Thrun·Burgard·Fox, *Probabilistic Robotics* 8장.
- 섭동 격자: v7 측면 파지 설계 `experiments/2026-09-28-pair-carry-v7-side-grasp/DESIGN.md`의 축 D. align 허용 경계 ±12 mm·±8 mm·±0.035 rad 모서리이고, 두 로봇 부호를 같게/반대로 둔다.
- 기존 GT staging 선례: `scripts/study_owncam_pair_beam.py`의 `stub_approach` 조건(GT stub로 pre-station까지만, 그 뒤 GT 미사용). `scripts/probe_dual_grasp_sync.py`(GT fixture, weld 기본 OFF).
- **적용과 차이.** robomimic·MuJoCo 방식은 저장한 전체 state로 되돌린다. 과거 E2E 실행은 mjData state를 저장하지 않았다.
  - 그래서 E2E 체크포인트는 eval-only GT trace(차체 pose·빔 pose)와 명령 이력(servo)으로 **부분 재구성**한다.
  - PF 입자도 저장되지 않았다. 그 순간의 자기 report(평균·σ)를 사전분포로 쓴다.

## 원본 해시 (raw는 로컬 전용, 원격 백업 아님)

| 파일 | SHA-256 |
|---|---|
| grid1 `artifacts.sha256.json` (29,745 파일) | `d6df55d72392d642ea569e3f9ecf42d0b8fbbeea21892acb28cef52feb9023f5` |
| grid1 `cases.jsonl` (= [cases_grid1.jsonl](cases_grid1.jsonl)) | `170f78f5a0d3250466c7913d5cba870de8004e88cf8f1e38b601e19ad50985b3` |
| grid1 `summary.json` (= [summary_grid1.json](summary_grid1.json)) | `23ff3d5d1d7a0ac942c51aa206ff3e8c1916dc4b9d550cbdb23ee63785cea437` |
| s45 `artifacts.sha256.json` (446 파일) | `364eb858edef51b58dd1b2c61ee24d7cc56d9d67f04c6828ff441513b1e7ccf4` |
| s45 `cases.jsonl` (= [cases_s45.jsonl](cases_s45.jsonl)) | `ad680f828bf1246f56a7d75fe9b20f3dbd6c99620cdaf25445d2030f5aaa4f83` |
| TensorBoard `collection.json` | `c5fdb727f82aed5868f273943e45e1cc330d580678a6b83e1cc0b56444e37d7c` |

정렬 실패 집계는 [analyze_align_failures.py](analyze_align_failures.py)로 raw에서 다시 계산한다. 출력은 [align_failure_analysis.txt](align_failure_analysis.txt)다.

## 재현

```sh
# 계획만 (MuJoCo 없음)
.venv-sim/bin/python -m scripts.run_pair_stage_probes --stage align grasp_lift --seeds 911 912 --e2e-seeds 911 912 913 --output /tmp/x
# 물리 (agent_lock 보유, clean 소스)
.venv-sim/bin/python -m scripts.sim_cli workflow run pair-stage-probes --record <abs>/outputs/<id>-managed -- \
  --stage align grasp_lift --seeds 911 912 --e2e-seeds 911 912 913 --workers 4 --execute --lock-owner claude \
  --output <abs primary>/outputs/<id>
```
