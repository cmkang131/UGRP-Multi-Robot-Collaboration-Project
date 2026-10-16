# 공동 운반 이어 달리기(chain) probe: 하네스와 사전 등록 계획 (2026-09-29, Claude)

**물리는 실행하지 않았다.** 이 폴더는 하네스 코드(순수 로직 테스트만 통과)와 실행 전에 고정하는 측정 계획이다. 물리 결과, 성공률, 학생 성공 주장은 없다.
나중에 측정하더라도 결과는 stage probe(개발 지도, 정답 staging 1회, weld OFF, 모델 호출 0)이며 E2E 성공이 아니다.

Refs #221. 출발점은 `experiments/2026-09-29-pair-v6c-carry/README.md`의 후속 작업 제안이다. "8 leg를 이은 누적 오차는 이 probe가 재지 않는다. 수정 후 이어 달리기 probe가 필요하다."
실험 ID `2026-09-29-pair-chain-probe`. 실행 번들/workflow ID는 새로 만들지 않았다(등록된 제어기·번들·workflow 코드는 바이트 그대로).

## 왜 필요한가

단계 probe(`harness/pair_stage_probe.py`, `scripts/run_pair_stage_probes.py`)는 carry leg 하나를 매번 새 teacher staging에서 시작한다. 그래서 앞 leg가 다음 leg에 남기는 것을 못 잰다.

- 열린 고리 주행 오차(빔 위치·yaw 표류)
- 내려놓고 열고 다시 잡는 동안 바뀌는 빔–로봇 관계
- 제어기 상태: PF, 명령 이력, 자기 fix 시계(체크포인트 재국소화로 바뀔 수 있음)

v6c 진단에서 leg별 끝점 오차는 한계(0.10 m) 안이었지만(L1 0.042, L2 0.037 등) 누적은 재지 못했다. chain probe는 파지+들기 완료 상태(teacher staging 1회)에서 레그 0→7과 목적지 내려놓기를 **제어기가 스스로 이어서** 돌리고, leg 경계마다 기록만 한다.

## 설계

### 실행 방식 (재staging 없음)

- 새 단계 `chain`(opt-in, `--stage chain`). 시작은 `carry` 단계 leg 0과 같다: teacher가 빔을 두 로봇이 든 자세로 놓고(정답 staging, 교사 예외), 제어기는 `wait_carry`, 경로 segment 0에서 시작한다. 배치·사전분포는 carry L0과 같다(테스트가 확인).
- **종료 훅이 없다**(`STAGES['chain']['exit_hook'] is None`). 단계 probe의 carry는 leg 끝(`_wait_lower`)에서 로봇을 잡아 세우지만 chain은 그대로 둔다. 제어기가 등록된 흐름을 끝까지 간다: carry, `wait_lower`/`lower`/`wait_open`/`cp_open`, 체크포인트 재국소화·재정렬·재파지·들기, 다음 leg, … 마지막 leg 뒤 목적지 내려놓기, `done`.
- leg 사이 teacher 재staging 없음. 기록기는 `ctl.tick`을 감싸는 통과형 래퍼다: 원래 tick을 먼저 실행하고 그 반환값을 그대로 돌려주며, 제어기 속성을 쓰지 않는다(테스트가 확인). 기록에는 정답이 들어가지만 제어기는 정답을 못 본다(정답은 eval-only 관측기에서만 읽고 leg 경계에서만 호출).
- 제어기 상태 승계: PF·명령 이력·fix 시계를 probe가 건드리지 않으므로 제어기가 갖는 그대로 leg를 넘는다. 제어기가 체크포인트에서 국소화기를 새로 만드는지(현재 코드 `_queue_grasp`는 `pregrasp_done`이 False이면 새 `OwnCamLocalizer`를 만든다)는 제어기 동작이고, 기록의 `localizer_replaced_events`와 leg 시작 σ로 드러난다.

### 기록 (leg 경계마다, 로봇별)

| 기록 | 시점 | 출처 |
|---|---|---|
| 상태 타임라인 `(sim_s, seg, state)` | 변화가 있을 때마다 | 제어기 상태 읽기 |
| leg 시작 스냅샷 | 그 leg의 첫 `wait_carry`/`carry` tick | 자기 PoseReport(σ, fix 나이·출처) + eval-only 정답(빔 pose, 로봇 pose, 접촉) |
| leg 끝 스냅샷 | 그 leg의 첫 `wait_lower` tick(빔은 아직 들림) | 같음 |
| 종료 스냅샷 | 첫 `done` tick, 그리고 host 종료 시 정답 | 같음 |

### 판정 지표 (eval only)

leg k(경로점 route[k]→route[k+1])마다 두 로봇 기록 중 더 늦은 시각을 쓴다(carry 단계와 같은 규칙).

| 지표 | 정의 | 종류 |
|---|---|---|
| `end_error_m` | 빔 끝점과 계획 경로점 route[k+1]의 거리 | 누적(ATE에 해당) |
| `cross_track_m`, `along_error_m` | 계획 leg 직선 기준 횡/진행 오차 | 누적 |
| `yaw_drift_deg` | 빔 yaw − chain 시작 yaw | 누적 |
| `step_error_m` | 끝점 − (그 leg 시작의 실제 빔 위치 + 계획 변위) | leg 단독(RPE에 해당) |
| `leg_error_m`, `yaw_step_deg` | 실제 이동 거리와 계획 길이의 차, leg 내 yaw 변화 | leg 단독 |
| σ 추이 | 로봇 자기 σ_xy, σ_yaw, fix 나이의 leg 시작/끝(두 로봇 중 큰 값) | 자기 보고 |
| 추정 오차 | 자기 추정 대 정답 xy/yaw(leg 끝) | eval-only |

누적 곡선은 `row['chain']['curves']`(leg 0..7, 못 간 leg는 `null`)이고 leg별 표는 `row['chain']['legs']`, 집계는 `summary.json`의 `stages.chain.chain`이다.

### 통과 기준과 첫 실패

- 통과: 8개 leg 모두 leg 끝에서 든 채(높이 ≥ 3 cm), 기울기 ≤ 10°, 두 로봇 집게 모두 접촉, `end_error ≤ 0.10 m`(누적), `leg_error ≤ 0.10 m`이고, 마지막에 목적지 내려놓기 기준(바닥 ≤ 5 mm, 기울기 ≤ 3°, 집게 모두 떨어짐, leg 7 끝에서 ≤ 5 cm 이동)을 만족하며 두 로봇이 `done`이다. 임계값은 단계 probe와 같은 개발 가설이며 raw 지표가 남아 있어 나중에 다시 적용할 수 있다.
- **첫 실패**(`row['chain']['first_failure']`): 제어기 실패(job_failed)와 leg GT 기준 위반 중 시각이 더 이른 것. 필드는 `phase`(`carry` / `handover` / `regrasp` / `setdown`), `leg`, `code`(단계 probe의 원인 코드 어휘 재사용: `SELF_POSE_UNCERTAIN`(sub yaw/xy), `MOTION_ERROR`, `COLLISION_GUARD` 등), `source`(`controller`/`gt_criterion`)이다. `handover`는 leg k가 끝난 뒤 내려놓기·열기·`cp_open`까지, `regrasp`는 다음 leg를 위한 재국소화·재정렬·재파지·들기다.
- `legs_passed_prefix`: leg 0부터 연속으로 자체 기준을 통과한 leg 수.

### 코드 변경 범위 (병합 충돌 최소화)

- 새 파일 `harness/pair_chain_probe.py`(순수 로직, 시뮬레이터 import 없음)와 `tests/test_pair_chain_probe.py`(26건)에 대부분을 넣었다.
- 기존 파일은 모두 `stage == 'chain'`으로 막은 좁은 훅뿐이다.
  - `harness/pair_stage_probe.py`: `STAGES['chain']`, `CRITERIA['chain']`, `_grid_offsets`/`leg_index`/`teacher_cases`의 stage 튜플 확장, `evaluate`의 `elif stage == 'chain'`, `summarize`의 chain 집계 한 줄. `PROBE_VERSION`은 바꾸지 않았다(기존 단계 출력이 바이트 그대로이므로). chain 기록에는 `chain.version = 0.1.0`(`CHAIN_PROBE_VERSION`)이 들어간다.
  - `scripts/run_pair_stage_probes.py`: `install_stage` 끝의 기록기 설치, `run_case`의 `chain_raw` 저장, `finish_result`의 chain 기록·판정·행 추가, `build_cases`의 e2e 소스 제외(chain은 teacher staging 전용, `unavailable_e2e`에 사유 기록).
- **기존 단계 출력은 불변**이다. 기존 6개 teacher 격자(align, grasp_lift, carry L0, carry L5+e2e prior, setdown end+b-v6d, setdown 옛 위치)의 케이스 목록 digest, carry·setdown `evaluate` 출력, 기준(`CRITERIA`)·단계(`STAGES`) 사본, `summarize` 출력을 origin/main `45a21b23`에서 계산한 값으로 고정한 골든 테스트가 있다. 다른 단계의 행에는 `chain` 키가 생기지 않는다.

## 검증 (물리 없음)

| 확인 | 결과 |
|---|---|
| `tests/test_pair_chain_probe.py` | 26건 통과 |
| `tests/test_pair_stage_probe.py`(기존) | 42건 통과 (합계 68건, 관련 테스트만 실행) |
| plan 전용 실행 `--stage chain --sources teacher --policies b-v6d --prior-std e2e --cells nominal` | 케이스 3개 계획, MuJoCo import 없음 |

테스트 내용: chain 경로·케이스 생성, 통과형 기록기(원래 tick 반환값 그대로, 제어기 속성 쓰기 없음, GT는 경계에서만 호출, 재staging 없음), leg 경계 지표(단계 probe의 `leg_end_metrics`와 같은 값), 누적 대 leg 단독 지표, σ 곡선, 안 간 leg 처리, 누적 표류가 만드는 첫 실패 leg, 핸드오버·재파지 단계의 제어기 실패 귀속, 내려놓기 실패, JSON 왕복(문자열 키), `finish_result` 무시뮬레이터 통합, 기존 단계 골든.

## 사전 등록 측정 계획 (실행하지 않음)

정책은 `--policies` 인자다. b-v6e는 아직 병합·등록 전이므로 이름만 후보로 둔다. b-v6e가 등록되면 `pair_stage_probe.POLICIES`에 들어 있는 이름을 그대로 쓴다(이 PR은 정책 목록을 건드리지 않는다).

### 공통 조건

- 시작: teacher가 leg 0 자세로 들어 올린 빔, `--prior-std e2e`(σ 0.03 m / 0.012 rad), weld OFF, `cargo_noslip_v1`, 모델 호출 0, 초음파 없음(번들이 켜지 않음).
- 소스 고정: 실행 전에 소스를 커밋하고(러너가 tracked 변경을 거부) 코호트 동안 바꾸지 않는다. `manifest.source_changed`가 True면 결과를 표에 넣지 않는다.
- 시간은 SIM 시간으로 판정한다. wall 시간과 부하는 참고다.
- seed는 PF 난수만 바꾼다. 물리는 같으므로 seed 반복은 독립 증거가 아니며 성공률의 신뢰구간이나 유의성 주장을 하지 않는다(개수와 곡선만 보고).
- 격자: 단계 probe와 같은 19케이스(nominal × 3 seed + 16셀) 중 teacher IK가 되는 13케이스(nominal 3 + along−/same, lat±의 same·opp, yaw±의 same·opp, corner−−/same 10셀)가 staged다. 나머지 6셀은 v6c 기록에서 IK 범위 밖이었다(분모 제외 규칙 유지, 배치·prior가 carry L0과 같아 같은 셀이 제외된다).

### 조건부 단계

| 단계 | 케이스 | 실행 조건 | 목적 |
|---|---|---|---|
| **S0 스모크 (5개)** | 대조 b-v6d nominal s911 (1) + 후보 b-v6e nominal s911·s912·s913 (3) + 후보 b-v6e `lat+/same` s911 (1) | 항상 먼저 | 하네스가 실제로 leg 경계를 기록하는가, 대조가 단계 probe와 같은 실패를 재현하는가 |
| **S1 격자** | 후보 b-v6e staged 13케이스(nominal 3 seed + 10셀) + 대조 b-v6d nominal 3 seed(3케이스), 합계 16 | S0 정상 **그리고** 후보가 다양한 결과를 냈을 때(아래) | 오프셋 경계에서의 누적 |
| **S2 배치 변형** | 후보 b-v6e 등록 배치 hA·hB·hC의 nominal × 3 seed(9케이스) | S1 정상, 그리고 b-v6e 브랜치의 `--setup-variant`가 main에 있을 때만 | 배치가 바뀌어도 누적 곡선이 같은지 |

**S0 정상 조건 (하나라도 어긋나면 확장 금지, 결과는 하네스 결함으로 보고).**
1. 대조 b-v6d는 단계 probe carry L0과 같은 원인으로 leg 0 안에서 끝난다: 첫 실패 `phase=carry, leg=0, code=SELF_POSE_UNCERTAIN`(sub yaw), 시작 후 약 3 s. (b-v6d가 v6c에 더한 것은 정렬 단계 항목(`align_fine_motion`, `beam_wide_hue`)이라 carry 경로는 v6c와 같다고 본다. 다르게 나오면 이 가정 또는 chain 기록을 먼저 의심한다.)
2. 후보 4케이스에 `HOST_ERROR`·`UNCLASSIFIED`·`STAGE_TIMEOUT_NO_EXIT`이 없다. 특히 `AttributeError`류 예외(로봇 스레드 `robots.json`의 `exception`)가 없다.
3. 후보 4케이스 중 최소 1개는 leg 1의 시작(`leg_start[1]`)까지 도달한다. 도달하지 못하면 "단일 staging에서 첫 체크포인트 재파지가 안 된다"는 하네스 한계(아래 '한계')이며 제어기 결과가 아니다.
4. 기록 무결성: `timelines`의 seg는 단조 증가, leg 시작·끝 스냅샷이 두 로봇에 모두 있고 GT가 들어 있다.

**S1 확장 조건.** S0 정상이고, 후보 4케이스가 모두 같은 leg에서 같은 원인으로 멈춘 경우가 아니다(모두 같은 곳에서 멈추면 셀을 늘려도 같은 정보이므로 확장하지 않고 원인 보고만 한다). 통과가 하나라도 있거나 첫 실패 leg 또는 원인이 케이스마다 다르거나 leg 4 이상까지 간 케이스가 있으면 확장한다.

### 판정 규칙

- 케이스: 위 통과 기준. 실패는 첫 실패(phase, leg, code)로 분류한다.
- 셀 묶음(정책 × 단계)별로 보고하는 것: staged 분모의 통과 수, `legs_passed_prefix` 분포, 첫 실패 `(phase, leg, code)` 분포, leg별 누적 곡선(`end_error`, `cross_track`, `yaw_drift`, σ)의 중앙값과 최댓값, 성공한 케이스의 SIM 시간과 명령 수(기본 명령 수는 `commands_after_submit`).
- 누적 판정 보조: leg 단독 지표(`step_error`)가 기준 안인데 누적(`end_error`)만 넘으면 "누적 오차로 인한 실패"로 표기한다. 이 구분이 chain probe의 목적이다.
- 대조(b-v6d)와 후보(b-v6e)는 같은 소스 SHA·같은 셀·같은 seed로 비교하고, 정책 이외의 조건을 섞지 않는다. 진단 패치(`--diag-patch`)를 쓰면 그 사실을 표시하고 제어기 결과와 합산하지 않는다.
- 단계 probe와의 정합: 후보 chain의 leg 0 결과는 같은 소스·같은 셀의 단계 probe carry L0 결과와 원인·지표가 같아야 한다(다르면 기록 결함으로 보고).

### 사전 예측 (검증되지 않은 산술)

v6c 진단에서 수정 후(`carry_all_three`) 단독 leg의 끝점 오차는 L0 0.0085, L1 0.0419, L2 0.0371, L6 0.0271, L7 0.0274 m였고 축 방향 leg는 계획보다 길게(+1.5 ~ +4.9 %) 갔다. 오차가 같은 방향이고 재정렬이 지워주지 않는다고 가정하면 축 방향 leg의 진행 오차가 더해져 leg 2 끝의 누적이 약 0.09 m, leg 7 끝이 약 0.14 m가 되어 leg 6 또는 7에서 0.10 m를 넘는다. 이것은 단독 측정값의 산술이지 측정 결과가 아니다. 체크포인트마다 door align(자기 추정으로 축 y 보정)가 있으므로 실제 누적은 이보다 작을 수 있다. 예측이 틀린 쪽(더 일찍 실패 또는 표류가 없음)이 정보가 더 많다.

### 중단 조건

- `agent_lock`이 없거나 소유 PID가 죽음(러너가 시작을 거부한다). 다른 에이전트가 물리·학습 잠금을 잡고 있으면 시작하지 않는다.
- 첫 라운드 케이스에서 `HOST_ERROR`(예외) 또는 S0 정상 조건 위반이 나오면 나머지 케이스를 시작하지 않고 보고한다(`--workers 2` 이하로 첫 라운드를 나눠 확인).
- 여유 디스크가 10 GiB 미만(`ugrp_session.py run`이 거부). 케이스당 raw는 크다: `sdPickup`(SIM 8.75 s, 19 MB / 3케이스)에서 외삽하면 약 0.7 MB/SIM s, 즉 케이스당 약 0.3–0.5 GB(추정, 실측 아님). S0는 약 2 GB, S1은 약 6–7 GB이므로 S1 시작 전에 `python3 scripts/disk_report.py`로 15 GiB 이상 여유를 확인한다. raw는 기본 체크아웃 `outputs/`에만 쓴다.
- 케이스 wall 시간이 `--case-timeout-s`를 넘으면 그 케이스는 `HOST_ERROR:worker_exit_WALL_TIMEOUT`이다. 2개 이상 나오면 중단하고 예산을 다시 정한다.
- 부하 평균이 30 이상으로 지속되면(같은 Mac의 다른 작업) 새 라운드를 시작하지 않는다. 기록은 남긴다.
- 사전 등록 SIM 예산: 케이스당 800 SIM s(`STAGES['chain']['budget_s']`). 넘으면 `STAGE_TIMEOUT_NO_EXIT`이다.

### 예상 SIM / wall (추정, 실측 아님)

- SIM: carry leg 22–26 s(v6c 합성 측정) × 8 + 체크포인트 재국소화·재정렬·재파지·들기 7회(제어기 상수상 재국소화 팬 8개와 재들기 대기 상한 60 s가 있어 회당 약 30–60 s로 추정) + 내려놓기 약 10 s → **케이스당 약 400–800 SIM s**. 제어기가 leg에서 멈추면 그만큼 짧다.
- wall: 단계 probe의 SIM 대 wall 비율(carry L3 SIM 22 s에 wall 88 s, 예전 위치 내려놓기 SIM 8.75 s에 wall 89 s, 부하 15–30)을 쓰면 SIM 1 s당 wall 4–10 s → 케이스당 약 30–115 분. S0의 5케이스를 아래 명령(대조 1, 후보 3을 workers 2로, 후보 1)으로 돌리면 4라운드라서 약 2–8 시간, S1(16케이스, workers 2)은 8라운드로 약 4–15 시간이다. S0에서 실측 비율이 나오면 S1 예산을 그 값으로 다시 계산해 확정한다.
- 러너의 기본 `--case-timeout-s`(1500 s)는 chain에는 짧다. 아래 명령은 9000 s로 잡는다.

### 실행 예시 명령 (실행하지 않음)

소스를 커밋한 worktree에서 실행한다. 다른 에이전트가 잠금을 잡고 있는지 먼저 `python3 scripts/agent_lock.py status`로 확인한다.

```bash
# 1) 계획만 확인(물리 없음): 케이스 목록과 해시. b-v6e는 등록되어 POLICIES에 들어간 뒤에만 유효한 이름이다
python3 -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6d b-v6e \
  --prior-std e2e --cells nominal --nominal-seeds 911 912 913 --output /tmp/never-created

# 2) S0 스모크 driver (자기 PID로 잠금을 잡고 EXIT에서 해제한다)
cat > /Users/changmin/projects/ugrp/outputs/pair-chain-driver-smoke.sh <<'EOF'
#!/bin/bash
set -u
cd /Users/changmin/projects/ugrp-wt/pair-chain-probe
SHA=$(git rev-parse --short=8 HEAD)
python3 scripts/agent_lock.py acquire --owner claude --branch claude/pair-chain-probe \
  --purpose "chain probe S0 smoke (SIM time, no models)" --pid $$ --expected-minutes 300 || exit 1
trap 'python3 scripts/agent_lock.py release --owner claude' EXIT
uptime
OUT=/Users/changmin/projects/ugrp/outputs/pair-stage-probes-$SHA
# 대조: b-v6d nominal s911
python3 -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6d --prior-std e2e \
  --cells nominal --nominal-seeds 911 --workers 1 --case-timeout-s 9000 --execute --lock-owner claude \
  --output $OUT-chainS0-ctl
# 후보: b-v6e nominal 3 seeds
python3 -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6e --prior-std e2e \
  --cells nominal --nominal-seeds 911 912 913 --workers 2 --case-timeout-s 9000 --execute --lock-owner claude \
  --output $OUT-chainS0-cand
# 후보: b-v6e lat+/same s911
python3 -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6e --prior-std e2e \
  --cells lat+/same --seeds 911 --workers 1 --case-timeout-s 9000 --execute --lock-owner claude \
  --output $OUT-chainS0-lat
uptime
EOF
chmod +x /Users/changmin/projects/ugrp/outputs/pair-chain-driver-smoke.sh
python3 scripts/ugrp_session.py run chain-s0 -- /Users/changmin/projects/ugrp/outputs/pair-chain-driver-smoke.sh
```

S1은 같은 형식으로 `--policies b-v6e` 전체 격자(`--cells` 생략, `--seeds 911 --nominal-seeds 911 912 913`)와 대조 nominal 3 seed를 돌린다. S2는 `--setup-variant hA|hB|hC`를 쓴다. 결과는 `cases.jsonl`, `summary.json`(`stages.chain.chain`)과 케이스별 `result.json`(`chain_raw`: 상태 타임라인·leg 경계 스냅샷 원본)에 남는다.

## 한계

- **물리 미실행.** 하네스는 합성 기록으로만 검증했다. 실제 제어기·시뮬레이터에서 leg 경계가 기록되는지는 S0가 확인한다.
- **단일 staging에서의 재파지 가능성이 미확인이다.** 진입 코드는 `carry` 단계 leg 0과 같아서 첫 체크포인트(`cp_open` 이후 재국소화·재정렬·재파지)에 필요한 제어기 필드가 모두 채워져 있는지는 코드를 읽어 확인했을 뿐 실행하지 않았다. 빠진 필드가 있으면 S0 조건 3에서 드러나며, 그때는 진입 코드를 보강하는 별도 작업이다(제어기 변경 아님).
- **상태 이름은 정적 읽기로 정했다.** `phase_of`의 상태 목록(`wait_carry`/`carry`, `wait_lower`/`lower`/`wait_open`/`cp_open`/`released`/`done`)은 `scripts/run_m2_pair.py`와 `scripts/study_owncam_pair_beam.py`에서 읽었다. 재파지 단계의 이름은 목록에 없는 것을 모두 `regrasp`로 본다. 다른 제어기 버전에서 이름이 바뀌면 귀속만 틀리고 기록·판정은 유지된다.
- **개발 지도에는 AprilTag가 있다.** 체크포인트 재국소화에서 태그로 절대 fix가 만들어지고 door align이 그 추정으로 횡 오차를 줄인다. 최종 환경은 태그가 0개이므로 이 chain의 누적 곡선은 태그 없는 환경보다 낙관적일 수 있다. σ 곡선의 leg 시작 값(재국소화 뒤)과 끝 값을 함께 봐야 한다.
- 통로·지형 지도는 측정하지 못한다(단계 probe와 같은 `UNSUPPORTED_PAIR_MAP`, 영역 지도는 지형 없음).
- 목적지 내려놓기는 v6c에서 영상 검사와 벽 여유 때문에 막혔다. b-v6e 계열이 이를 풀었는지에 따라 chain은 leg 7에서 끝날 수 있고, 그때 내려놓기 기준은 판정되지 않는다(`setdown.reached=false`).
- teacher IK 범위 밖 6셀은 측정되지 않는다. seed는 PF 난수만 바꾼다. wall 시간은 부하에 따라 달라진다.
- TensorBoard 변환기(`scripts/build_pair_stage_probe_views.py`)는 chain 행을 아직 다루지 않는다. 결과가 생기면 별도 변환·검증이 필요하다(이 PR은 결과가 없어 TensorBoard 스냅샷을 만들지 않았다).
- 새 테스트 파일은 `scripts/run_ci_tests.py`의 `TEST_PATTERNS`에 넣지 않았다(기존 `test_pair_stage_probe.py`도 목록에 없고, b-v6e 브랜치가 그 파일을 수정 중이라 충돌을 피했다). 로컬에서 위 두 파일을 실행하면 된다.
- b-v6e 브랜치(`claude/pair-v6e-carry`)는 같은 두 파일(`PROBE_VERSION 0.6.0`, `--pf-track`, `--setup-variant`, 정책 목록)을 고치고 있다. 겹치는 곳은 `pair_stage_probe.py`의 `POLICIES`·`_grid_offsets` 인접 줄과 `run_pair_stage_probes.py`의 `build_cases`이며, 나머지 훅은 서로 다른 줄이다.

## 참고 자료

저장소 기존 조사를 우선 재사용했다(출처와 인용은 `experiments/2026-09-29-pair-v6c-carry/README.md`의 참고 자료).

- J. Borenstein, L. Feng, "Measurement and correction of systematic odometry errors in mobile robots," IEEE Trans. Robotics and Automation 12(6):869–880, 1996 (UMBmark). 이 계획이 leg를 이어 누적 오차를 재는 방식의 원형이다: 짧은 구간이 아니라 이어진 경로의 끝에서 오차를 재야 계통 오차(열린 고리 배율)가 드러난다.
- S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005, 5장 odometry 운동 모델(잡음이 이동량에 비례). 오차가 leg마다 더해지는 성질과 σ 추이 기록의 근거.
- J. Sturm, N. Engelhard, F. Endres, W. Burgard, D. Cremers, "A benchmark for the evaluation of RGB-D SLAM systems," IROS 2012. 누적 절대 오차(ATE)와 구간 상대 오차(RPE)를 나누어 보고하는 관례. 이 probe의 `end_error`(누적)와 `step_error`(leg 단독)의 대응. 이번 작업에서 원문을 다시 열람하지는 않았고 잘 알려진 정의를 인용했다.
- R. R. Burridge, A. A. Rizzi, D. E. Koditschek, "Sequential Composition of Dynamically Dexterous Robot Behaviors," IJRR 18(6):534–555, 1999. 단계 probe를 앞 단계 종료 상태에서 시작하는 근거이자, 단계 사이 누적(앞 단계 종료 집합 ⊆ 다음 단계 입장 영역)을 이어서 확인해야 하는 이유.
- Nav2 AMCL 설정(`alpha1…alpha5`, `update_min_d`, `update_min_a`): https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/others/configuring_amcl/ (σ 확산 모델, v6c 막힘 1의 근거).
- 저장소 내부: `experiments/2026-09-29-pair-v6c-carry/README.md`(막힘 1–3, 후속 작업 제안), `experiments/2026-09-28-pair-stage-probes/README.md`(단계 probe 기준선), `harness/pair_stage_probe.py`, `scripts/run_pair_stage_probes.py`, `scripts/run_m2_pair.py`(`_cp_open`, `_queue_grasp`, `door_schedule`), `harness/zone_pair_executor.py`(`m2_controller`, `make_plan`), `docs/execution_versioning.md`.
