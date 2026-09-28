# 공동 운반 단계별 probe 하네스, 첫 격자, v6 정책 probe (2026-09-28–29, Claude)

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

## v6 정책 probe (2026-09-28–29, stage probe, not E2E success)

v6 E2E 코호트(#259)가 파지 전에 끝나 닿지 못한 v6 정책(b-only, a+b)을 2·3단계 probe로 따로 시험했다. 제어기는 main의 코드 그대로다(#246 병합본). A 단독(`beam_relative`만) 정책은 main의 `harness/zone_pair_v6_policy.POLICIES`에 없다(v5h, b-only, a+b). 그래서 A 단독은 측정하지 않았다.

### 실행 조건

| 실행 | 소스 | 내용 | cases | wall | 부하 평균 (시작→끝) |
|---|---|---|---|---|---|
| smoke | `8985db82`, `6184c119` | a+b·b-only 입장 확인 | 3+6 | 11 s, 약 60 s | 49–58 |
| Run A | `8ec4b7f8` | 2단계, b-only·a+b, teacher 19 + E2E 체크포인트 6 | 50 | 643 s | 56 → 32 |
| diag C | `78332709` | Run A와 같은 50건, probe 전용 진단 패치 `fix_age_round` | 50 | 2688 s | 13 → 59 |
| 경계 B1 | `78332709` | 3단계 허용오차 경계 23점 × v5h·b-only. 28/46에서 드라이버 셸이 종료되어 중단 | 28 | – | 59 → 199 (다른 작업) |
| 경계 B1 재실행 | `78332709` | B1에서 빠진 b-only 18건만 | 18 | 167 s | 54 → 36 |
| v5h 대조 | `78332709` | 2단계 v5h, Run A와 같은 사전분포 | 19 | 704 s | 36 → 19 |

- 공통: 4 worker × `OMP_NUM_THREADS=2`, weld OFF, `cargo_noslip_v1`, 모델 호출 0, SIM 시간 동기 모드. wall은 참고값이다.
- 잠금: `agent_lock` owner claude. 처음에는 sleep 자리 표시 PID(39242)로 잡았다. 중단 뒤 재실행은 드라이버 셸 PID(70511)로 다시 잡았고, 끝난 뒤 해제했다.
- **사전분포 (`--prior-std e2e`)**
  - 2단계 정렬 teacher 사례에서 평균은 grid1과 같은 정적 주문서 계획 자세다. 표준편차는 v5h E2E 정렬 진입 때 로봇 자신의 보고값에 맞췄다: 0.03 m, 0.012 rad (E2E 기록 0.026–0.033 m, 0.009–0.012 rad, fix 나이 0 s).
  - 이유: v6의 `RecoveryLocalizer`는 정지 중 반복 프레임으로 분산을 줄이지 않는다. grid1 사전분포(0.06 m)에서는 r2 σxy가 0.052 m에 머물러 입장 게이트(LOW 0.05)를 못 넘었다 (smoke `6184c119`, `ENTRY:ADMISSION_SELF_UNCERTAIN`).
  - 3단계 경계 세트는 grid1 사전분포 그대로다. 그래서 b-only 경계 5건이 입장에서 거절됐다(아래).
- **a+b 전역 안전 앵커 staging.** a+b의 전역 envelope는 접근 단계의 마지막 정보성 fix를 앵커로 쓴다. 단계 probe에는 접근이 없어 제출 즉시 `GLOBAL_ANCHOR_UNKNOWN`으로 끝났다 (smoke `8985db82`). 그래서 명시된 사전분포(teacher)나 로봇 자신의 기록 보고(E2E)를 나이 0의 앵커로 준다. GT가 아니다. envelope 갱신·만료 코드는 그대로다.
- v5h 기준선: grid1(`2aa03454`) 정렬 0/41, 파지+들기 17/35. 사전분포는 0.06 m, 0.05 rad다.

### 단계별 통과표

| 단계 | 정책 | 사전분포 | teacher 격자 | E2E 체크포인트 | 합계 | 주 실패 |
|---|---|---|---|---|---|---|
| 2 정렬 | v5h (grid1) | 0.06 m | 0/35 | 0/6 | **0/41** | `ALIGN_RELOOK_NO_FIX` 32 |
| 2 정렬 | v5h (대조) | E2E 정합 | 0/19 | – | **0/19** | `ALIGN_RELOOK_NO_FIX` 14, `PAIR_COLLISION_GUARD` 4 |
| 2 정렬 | b-only (등록 코드) | E2E 정합 | 0/19 | 0/6 | **0/25** | `ALIGN_RELOOK_NO_FIX` 25 |
| 2 정렬 | a+b (등록 코드) | E2E 정합 | 0/19 | 0/6 | **0/25** | `BEAM_RELATIVE_UNCERTAIN` 23 |
| 2 정렬 | b-only + 진단 패치 | E2E 정합 | 10/19 | 3/6 | **13/25** | GT yaw 기준 6, `ALIGN_RELOOK_NO_FIX` 6 |
| 2 정렬 | a+b + 진단 패치 | E2E 정합 | 0/19 | 0/6 | **0/25** | `BEAM_RELATIVE_UNCERTAIN` 25 |
| 3 파지+들기 | v5h (grid1, 섭동 격자) | 0.06 m | 17/35 | – | **17/35** | `PREGRASP_NOT_READY` 10 |
| 3 파지+들기 | v5h (허용오차 경계) | 0.06 m | 8/23 | – | **8/23** | `PREGRASP_NOT_READY` 11 |
| 3 파지+들기 | b-only (허용오차 경계) | 0.06 m | 6/23 (입장 거절 5 제외 6/18) | – | **6/23** | `PREGRASP_NOT_READY` 10 |
| 3 파지+들기 | a+b | – | smoke 0/2 | – | – | 격자 미실행 (아래) |

- 진단 패치 결과는 등록된 v6 결과가 **아니다**. "이 결함을 빼면 다음 실패가 무엇인가"만 보여 준다.
- 표의 teacher 격자 합계: nominal은 seed 3개(PF RNG만 다름)이고 나머지 셀은 seed 911 하나다. seed는 PF RNG만 바꾸므로 독립 반복이 아니다.

### TensorBoard (v6)

- 스냅샷: `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6`, run 256개(경우별 241 + 그룹 집계 `ALL-*` 15). `collection.json` sha256 `c1ab7705…`. 비교용 v5h grid1 기준선 76건을 함께 넣었다.
- 파생 뷰 `outputs/pair-stage-probes-tbviews-0929-v6` (index sha256 `56586f02…`), 빌더 `scripts/build_pair_stage_probe_views.py`, 변환기 `scripts/export_offline_audit.py`.
- 검증 1: EventAccumulator로 241개 경우의 `offline/stage_pass`와 `gate/stop_grip_x_err_m/*`, 집계 15개의 `offline/pass_rate`를 raw와 비교했다. 불일치 0건이다.
- 검증 2: 공용 서버(PID 9291, 다른 작업 소유, 재시작하지 않음)가 256 run을 제공한다. `ALL-B-al-t-78332709-diagC` pass_rate 0.526(=10/19), `B-gl-bd-ex-4mm-s911` stage_pass 1.
- 대시보드: `outputs/tensorboard-view.json`의 `pair_stage_probes_v6_20260929` URL. 고정 카드 9개가 열리는 것을 확인했다. 서버 run이 500개를 넘어 새 run은 목록에서 직접 선택해야 한다. HParams 열도 설정값대로 직접 켜야 한다.
- 이름: 접두어 `AB-`=a+b, `B-`=b-only, 없음=v5h. `bd`=허용오차 경계. 끝의 `-pE`=E2E 정합 사전분포, `-dx`=진단 패치.

### 2단계: relook이 localizer를 재초기화하는가

사례별 표는 [v6_align_analysis.txt](v6_align_analysis.txt)(등록 코드, v5h 대조 포함)와 [v6_align_diag_analysis.txt](v6_align_diag_analysis.txt)(진단 패치)에 있다. 각 로봇의 relook 호출 수, localizer 객체 교체 수, 멈춘 시점의 GT 잔여 오차(eval only)를 적었다.

- **v5h: relook마다 사후분포를 버린다.** 19건 38 로봇에서 `begin_relocalization` 호출과 localizer 객체 교체 수가 같다(로봇당 1–5회). relook fix 거절 76건은 모두 `gate_ok`·`std_xy`·`sigma_reserve`(분산 과다) 때문이었다. 멈춘 시점 GT grip x 잔여는 대부분 +60–93 mm다.
- **v6 (b-only, a+b): 재초기화하지 않는다.** 100건 200 로봇 모두 localizer 교체 0회다. relook은 `begin_observation`(사후분포 유지)만 불렀다. 따라서 "relook이 localizer를 다시 초기화해서 실패한다"는 v6에는 해당하지 않는다. 멈춤 조건(항목 2)은 성립하지 않았다.
- **b-only 실패 원인: fix 나이가 음수로 보고된다** (등록 코드 버그).
  - relook fix 거절 125건 중 116건이 `fix_age_valid` **하나만** 실패했다. 나머지 9건은 `informative_fix`였다.
  - `harness/owncam_recovery_v6.py` `RecoveryLocalizer.estimate`는 `fix_age_s = self.t - t`를 반올림하지 않는다.
  - `OwnCamLocalizer.predict_to`는 `self.t < t - 1e-9` 동안만 전진한다. 그래서 방금 fix한 프레임의 나이가 약 -1e-13 s가 된다. `owncam_time.accepted_fix_checks`가 `fix_age_s >= 0`에서 거절한다.
  - v5h의 `OwnCamLocalizer.estimate`는 `round(self.t - self.last_tag_t, 3)`이라 이 문제가 없다.
  - probe 전용 진단 패치 `--diag-patch fix_age_round`는 v5h와 같은 반올림을 probe 프로세스에서만 적용한다(case ID `:diag-fix_age_round`). 이 패치로 b-only 정렬이 **0/25 → 13/25**가 됐다.
    - 통과 13건: 멈춘 시점 |grip x| 중앙값 7 mm(최대 8), |yaw| 중앙값 0.024 rad. 단계 SIM 중앙값 36.7 s.
    - 실패 12건 중 6건은 제어기가 정렬 완료라고 판단했지만 GT yaw가 기준(0.052 rad)을 넘었다(r1 0.054–0.115 rad). 자기 heading 추정 오차다.
    - 나머지 6건은 `ALIGN_RELOOK_NO_FIX`다. 거절 사유는 `fix_in_sweep`+`fix_gap`+`informative_fix`(재관측 창 안에 새 정보성 fix 없음)다.
  - 제어기는 고치지 않았다. #259에 코멘트로 알렸다.
- **a+b 실패 원인: r2의 단안 상대 빔 인식** (localizer와 무관).
  - 25건 중 23건에서 r2가 `BEAM_RELATIVE_UNCERTAIN`으로 먼저 끝났다. 순서는 첫 프레임 `SHAPE_AMBIGUOUS`,`MONOCULAR_DEPTH_AMBIGUOUS` → p45 자세 `END_CLIPPED`,`END_ID_AMBIGUOUS` → inspect 자세 `BEAM_NOT_VISIBLE`이다. 볼 자세가 없어 실패한다.
  - r2 첫 프레임에는 빔 전체와 가까운 끝이 보인다. nominal 사례에서 r1은 같은 거리에서 `MONOCULAR_RESTING_PLANE_HYPOTHESIS`로 fit에 성공했다(grip 0.42–0.45 m 앞).
  - 단계 SIM 2.9 s에 끝나 차체가 움직이지 않았다. 멈춘 시점 grip x 잔여는 +228–333 mm로 출발점 그대로다.
  - 진단 패치는 a+b를 바꾸지 않는다(0/25 → 0/25).

### 3단계: 정렬 완료 허용오차와 파지 입장 검사의 불일치

경계 세트는 컨트롤러 자신의 정렬 완료 허용오차에서 시작한다(`ALIGN_TOL_X_M` 12 mm, `ALIGN_TOL_M` 8 mm, `ALIGN_TOL_RAD` 0.035 rad). 실제 grip이 로봇 자기 좌표계의 (0.162+ex, ey)에 있고 yaw 오차가 eyaw가 되도록 GT로 배치했다(setup only). 두 로봇은 같은 오프셋이고, 사전분포는 정적 계획 station이다. 각 로봇에서 처음 실패한 입장 검사를 컨트롤러 순서대로 적었다(전체 [boundary_analysis.txt](boundary_analysis.txt)).

| 오프셋 | v5h | b-only |
|---|---|---|
| ex −12 mm | standoff fit 실패 | standoff fit 실패 |
| ex −8, −4 mm | **통과** | **통과** |
| ex 0, +4, +8, +12 mm | preclose 빔 추정 없음 | preclose 빔 추정 없음 |
| ey −8 mm | standoff fit 실패 | standoff fit 실패 |
| ey −4 mm | preclose 빔 추정 없음 | preclose 빔 추정 없음 |
| ey +4 mm | 통과 | r2 자기 pose `std_xy` |
| ey +8 mm | 통과 | 통과 |
| eyaw +0.0175, +0.035 rad | preclose 빔 추정 없음 | preclose 빔 추정 없음 |
| eyaw −0.0175 rad | `PREGRASP_BEAM_UNSAFE` (닫기 뒤) | 입장 거절 |
| eyaw −0.035 rad | 통과 | 입장 거절 |
| 모서리 (+,+,+), (+,−,+), (+,−,−) | preclose 빔 추정 없음 | preclose / 입장 거절 |
| 모서리 (+,+,−) | standoff fit 실패 | 입장 거절 |
| 모서리 (−,+,−) | `grip_view_m2` 어두운 비율 0.393 < 0.40 | 입장 거절 |
| 모서리 (−,+,+), (−,−,+), (−,−,−) | 통과 | 통과 |

- 입장 거절을 뺀 실패 27건 중 26건에서 r1이 먼저 실패했다(b-only ey+4 mm만 r2).
- **정렬은 ex ∈ [−12, +12] mm를 완료로 받는다. 그러나 파지 입장은 ex ≈ −8…−4 mm에서만 통과한다.** ex ≥ 0이면 r1의 pre-close 빔 가드가 `BEAM_UNCERTAIN`이다(열린 손목 시야에서 정지 빔 추정 없음). ex = −12 mm이면 standoff 시야에서 빔 fit이 안 된다. 카탈로그 station은 ex = −7 mm이고 grid1 nominal이 통과한 것과 맞는다.
- yaw는 +쪽(로봇이 station보다 시계 방향) 두 점 모두 preclose에서 실패했다. −0.035 rad는 v5h에서 통과했다.
- 정렬 목표 0.162 m는 ex=0이다. 이 목표에 정확히 도달해도 파지 입장이 실패한다. 정렬 목표·허용오차와 파지 시야 기하를 함께 맞춰야 한다. 설계 변경은 이 PR 범위 밖이다.
- b-only의 입장 거절 5건은 grid 사전분포(0.06 m)에서 RecoveryLocalizer가 정지 중 수렴하지 않은 결과다(2단계와 같은 원인). 단계 결과가 아니므로 판정에서 뺀다.
- **a+b 3단계 격자는 돌리지 않았다.** smoke 2건(`6184c119`)에서 r2 standoff 상대 추적이 `END_CLIPPED`,`END_ID_AMBIGUOUS`로 끝났다. a+b의 끝 식별·객체 앵커는 정렬 단계의 여러 영상에서 쌓이는 제어기 내부 상태라서, 3단계 staged 진입으로는 재현되지 않는다. 2단계에서 a+b가 정렬을 통과하지 못하므로 3단계 입장 상태를 만들 수 없다.
### relook와 사후분포: 표준 방법 (항목 2의 근거)

- 재귀 Bayes 필터는 정지 후 관측(stop-and-look)에서 **기존 사후분포를 prior로 유지하고 측정만 곱한다**. 다시 초기화하지 않는다.
  - Thrun·Burgard·Fox, *Probabilistic Robotics* (MIT Press, 2005), 2.4절 Bayes filter, 4.3절 particle filter, 8.3절 MCL.
  - 필터 발산(kidnapped robot)은 8.3.5절 Augmented_MCL처럼 **측정 우도의 단기/장기 평균 비율에 따라 일부 무작위 입자만 섞는다.** 전체 재초기화가 아니다.
- Fox·Burgard·Thrun, "Active Markov Localization for Mobile Robots", *Robotics and Autonomous Systems* 25(3–4):195–207, 1998.
  - 어디를 볼지(행동)를 현재 믿음의 기대 엔트로피 감소로 고른다. 믿음은 관측 사이에 유지된다.
- ROS amcl (http://library.isr.ist.utl.pt/docs/roswiki/amcl.html, Nav2 AMCL https://docs.nav2.org/configuration/packages/configuring-amcl.html)
  - 입자 전체를 다시 퍼뜨리는 것은 `initialpose` 토픽(사용자가 준 평균·공분산으로 `pf_init`)이나 `global_localization` 서비스를 **명시적으로 호출할 때만**이다.
  - 평소 복구는 `recovery_alpha_slow/fast`(Augmented MCL)로 무작위 입자를 조금씩 더한다.
- 우리 코드와의 대응
  - v5h relook: `OwnCamPoseSource.begin_relocalization`이 `pose.loc`를 새 `FixReportingLocalizer`로 교체한다 → 사후분포 폐기. grid1 v5h 정렬 relook 거절 175건 중 대부분이 `gate_ok`/`std_xy`/`sigma_reserve`(분산이 커서) 실패였다.
  - v6 B(`posterior_relook`): `RecoveryLocalizer.begin_observation`이 사후분포를 유지하고, 잃었을 때만 20% 입자를 주입한다. 표준 방법(Augmented MCL)과 같은 구조다.
  - 이번 probe에서 b-only·a+b는 localizer 객체 교체 0회(50/50)였다. **"relook이 localizer를 다시 초기화해서 실패"는 v6에서는 성립하지 않는다.** v6 실패 원인은 아래 두 가지로 다르다.
- A 단독(`beam_relative`만) 정책은 main의 `harness/zone_pair_v6_policy.POLICIES`에 없다(v5h, b-only, a+b만). probe도 등록된 정책만 받는다. A 단독 측정은 하지 않았다.

### E2E 실행기의 단계 전이 체크포인트 (항목 4: 설계만)

- **실행기를 고치지 않은 이유**
  - `scripts/zone_pair_dev_runtime.py`와 제어 harness 파일은 v5h 동결 prereg와 v6 DRAFT prereg의 `source_sha256` 계약에 들어 있다. 한 줄을 바꿔도 등록 해시가 바뀌어 새 번들 ID·새 prereg가 필요하다. "작고 따로 버전된 변경"이 아니다.
  - workflow 1개를 `configs/simulation_workflows.json`에 등록하는 것만으로도 v6 prereg 해시가 깨진다(아래 "v6 계약 해시" 참고). 실행기 수정은 그보다 큰 계약 변경이다.
- **mj 상태 + PF만으로는 v6를 이어서 실행할 수 없다 (probe로 확인)**
  - a+b를 3단계(grasp_lift)에서 바로 시작하면 r2의 상대 빔 추적이 `END_ID_AMBIGUOUS`로 끝났다. 끝 식별(identity)과 객체 앵커는 정렬 단계의 여러 영상에서 쌓이는 제어기 내부 상태다.
  - a+b는 전역 envelope 앵커(마지막 정보성 fix)도 필요하다. 없으면 제출 즉시 `GLOBAL_ANCHOR_UNKNOWN`이다.
  - 따라서 체크포인트는 물리·PF 외에 **제어기 객체 상태**를 담아야 한다.
- **설계**
  1. 저장 시점: 각 로봇의 `pair_progress` 단계 전이(`align_start`, `pregrasp_standoff`, `wait_carry`, `wait_lower`, 끝). 두 로봇 중 늦은 쪽 전이 시각에 한 번 더 저장한다.
  2. 내용
     - `mj_getState(model, data, state, mjSTATE_INTEGRATION)`와 모델·장면 해시(MuJoCo 문서 State manipulation, robomimic `reset_to` 방식).
     - 로봇별 PF: `px`, `logw`, `scale`, `vel`, `cmd`, `cmd_expires`, `servo`, `loaded`, `last_tag_t`, `last_informative_t`, `last_fix_quality`, `inconsistent_frames`, `numpy` RNG `bit_generator.state`.
     - 제어기·실행 객체: `PairExecution`(상태, 예산, barrier), `PairCommandGuard`(전역 envelope, 상대 빔 추적, 객체 앵커, 재관측 예산), 팔 명령 큐, 포트 명령 이력, 상태 채널 버퍼. 렌더러·`MjModel`·파일 핸들을 뺀 `pickle`로 저장한다.
  3. 복원: 같은 spec으로 host를 만들고 `mj_setState` + `mj_forward`, 이어서 제어기 객체를 교체한다.
  4. 검증
     - 물리: 새 `MjData`에 `mj_setState` 후 다시 `mj_getState`해 비트 단위 비교.
     - 결정성: 체크포인트 k에서 재개한 N초의 명령·이벤트가 원래 실행과 같은지 비교한다. 같은 호스트의 오프스크린 렌더링에 의존한다.
  5. 버전: 별도 모듈(예: `harness/pair_state_checkpoint.py`)과 기본 OFF 플래그. 켜는 실행은 새 번들 ID와 새 prereg(v7 이후)로 등록한다. v6 DRAFT에는 소급하지 않는다.
- **이번 probe의 원형(구현됨)**
  - `scripts/run_pair_stage_probes.py save_checkpoint`는 `staged_before_submit`과 `stage_stop`에서 (1)과 PF 배열·RNG를 저장한다.
  - 새 `MjData` 왕복 비트 비교를 한다. v6 probe 4개 실행의 체크포인트 325개 모두 `roundtrip_bitwise=true`였다.
  - 제어기 객체 저장은 원형에 없다.

### v6 계약 해시와 workflow 등록 (등록 보류)

- v6 prereg(`experiments/2026-09-28-zone-pair-v6/prereg_v6.json`)의 `v6_contract.source_sha256`는 `configs/simulation_workflows.json` **전체**를 해시한다.
- 이 PR의 첫 커밋(`2aa03454`)이 workflow `pair-stage-probes`를 등록하면서 이 해시가 바뀌었다. `tests/test_zone_pair_v6.py`·`tests/test_zone_pair_registered_source.py`가 실패했는데, 그때 돌리지 않아 놓쳤다.
- `8985db82`에서는 prereg가 DRAFT였으므로 해시 한 줄을 갱신했다(`c6feb21d`와 같은 방식).
- 그 뒤 #259가 v6 prereg를 **REGISTERED**로 전환해 병합했다. 등록된 prereg는 파일 해시까지 승인 기록에 묶인다(`registration hash mismatch`). 동결된 등록은 고치지 않는다.
- 그래서 origin/main 병합(`a25386e9` 이후)에서 두 파일을 main 그대로 되돌렸다. **`pair-stage-probes` workflow 등록은 보류**했다.
  - 등록할 행은 [workflow_registration_pending.json](workflow_registration_pending.json)에 그대로 보관한다(0.2.0).
  - 이 PR의 물리 실행은 모두 등록 상태의 `sim_cli workflow run pair-stage-probes`로 돌았다. 공통 실행 기록은 각 raw의 `*-managed/manifest.json`에 있다.
  - 보류 중에는 `scripts.run_pair_stage_probes`를 직접 실행한다. `--execute`의 잠금·clean 소스·주 checkout 출력 검사는 러너 자체에 있다.
- v6 쪽에서 계약을 자기 workflow 항목만 해시하도록 좁히거나 새 등록 버전을 내면, 그때 이 행을 등록한다. 다른 PR의 workflow 추가도 같은 문제를 겪는다.

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
- 재귀 Bayes·particle filter의 관측 사이 사후분포 유지와 부분 입자 주입(Augmented MCL): Thrun·Burgard·Fox, *Probabilistic Robotics*, MIT Press 2005, 2.4·4.3·8.3절.
- Fox·Burgard·Thrun, "Active Markov Localization for Mobile Robots", *Robotics and Autonomous Systems* 25(3–4):195–207, 1998. 믿음을 유지한 채 다음 관측 행동을 고른다.
- ROS amcl 문서(`initialpose`, `global_localization`, `recovery_alpha_slow/fast`): http://library.isr.ist.utl.pt/docs/roswiki/amcl.html , Nav2 AMCL: https://docs.nav2.org/configuration/packages/configuring-amcl.html
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

v6 정책 probe raw (모두 `/Users/changmin/projects/ugrp/outputs/` 아래, 로컬 전용):

| raw | 파일 수 · 크기 | `artifacts.sha256.json` | `cases.jsonl` (저장소 사본) |
|---|---|---|---|
| `pair-stage-probes-8985db82-smoke` | 133 · 3.2M | `f5371cb0…` | – |
| `pair-stage-probes-6184c119-smoke` | 582 · 13M | `1b8d7737…` | – |
| `pair-stage-probes-8ec4b7f8-alignv6` (Run A) | 6,022 · 149M | `d895a607…` | `5f2f52ca…` ([cases_v6_align.jsonl](cases_v6_align.jsonl)) |
| `pair-stage-probes-78332709-diagC` | 24,995 · 558M | `cbed44cf…` | `393b48e7…` ([cases_v6_align_diag.jsonl](cases_v6_align_diag.jsonl)) |
| `pair-stage-probes-78332709-bound` (28/46 중단, 사후 `summary.json`·해시) | 4,593 · 94M | `9242276a…` | `baeef72b…` |
| `pair-stage-probes-78332709-bound2` | 2,181 · 47M | `e3cd9b1b…` | `4c761f3b…` (두 경계 실행 합본 [cases_boundary.jsonl](cases_boundary.jsonl)) |
| `pair-stage-probes-78332709-v5hctl` | 11,630 · 252M | `8ebdaa3f…` | `a858fd34…` ([cases_v5h_align_e2eprior.jsonl](cases_v5h_align_e2eprior.jsonl)) |

- 중단된 `bound` 실행의 결과 없는 사례 폴더 4개(`ex+12mm`, `ex+8mm`, `ey-4mm`, `ey-8mm`, b-only)는 그대로 두었다. 해당 사례는 `bound2`에서 다시 돌렸다.
- v6 표는 [analyze_v6_policies.py](analyze_v6_policies.py)로 raw에서 다시 계산한다.

정렬 실패 집계는 [analyze_align_failures.py](analyze_align_failures.py)로 raw에서 다시 계산한다. 출력은 [align_failure_analysis.txt](align_failure_analysis.txt)다.

## 재현

```sh
# 계획만 (MuJoCo 없음)
.venv-sim/bin/python -m scripts.run_pair_stage_probes --stage align grasp_lift --seeds 911 912 --e2e-seeds 911 912 913 --output /tmp/x
# 물리 (agent_lock 보유, clean 소스)
.venv-sim/bin/python -m scripts.sim_cli workflow run pair-stage-probes --record <abs>/outputs/<id>-managed -- \
  --stage align grasp_lift --seeds 911 912 --e2e-seeds 911 912 913 --workers 4 --execute --lock-owner claude \
  --output <abs primary>/outputs/<id>
# v6 정책 (각 실행은 agent_lock 보유). workflow 등록 보류 중이면 sim_cli 대신
# `.venv-sim/bin/python -m scripts.run_pair_stage_probes <같은 인자>`로 직접 실행한다.
.venv-sim/bin/python -m scripts.sim_cli workflow run pair-stage-probes --record <abs>-managed -- \
  --stage align --sources teacher e2e --prior-std e2e --policies a+b b-only --seeds 911 \
  --nominal-seeds 911 912 913 --e2e-seeds 911 912 913 [--diag-patch fix_age_round] \
  --workers 4 --execute --lock-owner claude --output <abs primary>/outputs/<id>
.venv-sim/bin/python -m scripts.sim_cli workflow run pair-stage-probes --record <abs>-managed -- \
  --stage grasp_lift --sources boundary --prior-std grid --policies v5h b-only --seeds 911 \
  --workers 4 --execute --lock-owner claude --output <abs primary>/outputs/<id>
.venv-sim/bin/python experiments/2026-09-28-pair-stage-probes/analyze_v6_policies.py <raw> [<raw> ...]
```
