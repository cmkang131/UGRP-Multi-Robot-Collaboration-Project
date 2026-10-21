# E2E-min 단독 구성요소 smoke (gcp2 L4, DeepSeek 실행용)

작성: 2026-10-21 Claude 구현 워커. 명령만 정리한 문서이고, 실행 승인을 대신하지 않습니다. 확인하지 못한 값은 [확인 필요]로 두었습니다. 추측으로 채우지 말고 VM에서 확인한 값으로 바꿔 넣으세요.

- 라벨: 출력 JSON마다 `"label": "STANDALONE_SMOKE — 배관 확인, 판정 아님, 수집 데이터 아님"`이 들어갑니다. 결과는 성공률·n/N·본실험·smoke 어디에도 합산하지 않습니다.
- 브랜치: `dsh/e2e-min-standalone`. base는 `claude/e2e-min-runner` `c081cd143`이고, `dsh/e2e-min-render-fix`의 `e2c82d9be`와 `ddcc86f3c`를 충돌 없이 cherry-pick했습니다(새 SHA `64d151e11`, `f72d8ceb1`). main 병합은 없습니다.
- 코드: `scripts/e2e_min_standalone_smoke.py`(드라이버, `--enabled` 없으면 거부), `tests/test_e2e_min_standalone.py`. 기존 runner·handoff·executor 코드는 바꾸지 않았습니다.
- 실행할 SHA는 문서 커밋을 포함한 브랜치 HEAD입니다. 아래 0.1에서 `git ls-remote`로 받습니다.

## 무엇을 하나 (relay 없음, LLM 없음, world 1개)
| 단계 | 하위 명령 | 정책 종류(코드 기준) | 하는 일 |
|---|---|---|---|
| 1a | `act-server --frames synthetic` | **learned**: ACT 학생, R8 step-100000 체크포인트, C2c 설정(`n_action_steps=1`, `temporal_ensemble_coeff=.01`, done head 없음, loop overlay 없음, 클라이언트 쪽 v7 deadband-2 시계) | runner와 같은 `act_server_argv` + `ActServerTransport`로 서버를 띄웁니다. 회색 JPEG로 r1·r2에 grasp 요청을 30 tick 보냅니다(물리 없음, 명령 미발행). 서버 기동·CUDA·프로토콜만 봅니다 |
| 1b | `act-server --frames render` | 같음 | nav 장면(v6) world 1개에 E2E 큐브(`cyan_1`·`red_1`, `PROPOSED_CUBE_XY`)를 둡니다. 자기 카메라 프레임 → ACT → `issue` → MJWarp step을 30 tick(3 SIM s) 돌립니다. **집기 요청 왕복 확인이고, 집기 평가는 아닙니다** |
| 2 | `release-open --physics warp` | **scripted**: 규칙 스크립트 `release_open_v1`(학습 아님. 상수는 teacher 데이터셋 통계에서 가져옴) | 팔을 `act_lift_end` 자세로 잡은 채 시작합니다. 정지 → 그리퍼 2000까지 → 자기 명령 odometry로 0.15 m 후진 → done. 큐브는 없습니다(빈 손가락으로 엽니다). GT 변위는 eval-only로 기록만 합니다 |
| 3 | `nav-render` | **scripted**: `NavCarryAdapter(NavRobot)`, 즉 r5 규칙 기반 self-nav(`e2ewarp_nav_gate:navigation_factory`, 색 띠 zone 검출기 + 자기 명령 odometry). 학습 정책·teacher·LLM 모두 아님 | 팔을 `act_lift_end`에 고정합니다(H3 `last_hold_all_servos_v1`: PWM 5채널 모두 hold). 레인 spawn에서 B zone까지 최대 600 tick(60 SIM s) 운반 주행합니다. 슬롯은 r1=left, r2=right로 **코드가 고정**합니다(LLM 결정 아님). 프레임은 5 tick마다 저장합니다. 큐브 없음 |

`release-open --physics none`(CPU 명령열만)은 로컬 테스트에서 이미 돌렸으므로 gcp2에서는 돌리지 않습니다.

## gcp6 '다음 2'와의 차이 (중복은 뺐음)
- gcp6 '다음 2'는 ① carry 자세 렌더 재실행(`RENDER_RERUN.md`)과 ② E2E-1' 전체 smoke(`SMOKE.md`: relay·L1-lite LLM 할당·ACT·nav·release를 한 runner에서)입니다.
- **뺀 것:** carry 자세 렌더(`carry_pose_render.py`, tick 0 정지 프레임 4자세 × x 4곳, 큐브 가림 측정)는 gcp2에서 다시 돌리지 않습니다. 같은 일이기 때문입니다. 단계 3은 그 렌더가 아닙니다. 한 자세(`act_lift_end`)로 nav가 **실제로 주행하는 폐루프**이고, 큐브 가림은 다루지 않습니다.
- **남긴 것과 이유:** 1–3은 전체 smoke의 부분집합입니다. 그래도 relay, host receipt, LLM 할당, handoff 상태기계 없이 구성요소 하나씩 띄우므로, 전체 smoke가 실패했을 때 어느 구성요소에서 막혔는지 가를 수 있습니다. 또 ACT env·체크포인트는 gcp2에 있다고 기록돼 있어(DESIGN §6.2) gcp6 smoke 사전 확인 0.2–0.3이 막힐 수 있는데, 1a·1b는 gcp2에서 그 부분을 먼저 확인합니다.
- **건너뛰는 조건:** gcp6 E2E smoke가 이미 `E2E_EPISODE_FINISHED`이고 `e2e-handoff.json`에서 grasp → carry → release 전환이 모두 찍혔다면 1b와 3은 건너뛰고 1a만 돌립니다(gcp2 ACT env 확인용).

## 사전 등록 동결이 필요 없는 이유
판정, 성공 기준에 따른 채택·기각, n/N, 조건 비교가 없습니다. 출력은 "구성요소가 떠서 요청에 응답했고 명령이 물리로 들어갔는가"라는 배관 확인뿐입니다. 출력에는 `verdict=null`, `n_over_N=null`, `pooled=false`를 고정으로 넣습니다. 수집 데이터로도 쓰지 않습니다. seed는 601 하나(carry 렌더와 같음)이고 반복하지 않습니다.

## 0. 사전 확인 (하나라도 실패하면 해당 단계를 돌리지 않음)
```bash
BR=dsh/e2e-min-standalone
SHA=$(git ls-remote https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git refs/heads/$BR | cut -f1)
SRC=/home/ugrp/ugrp-sim/src/e2e-min-standalone-${SHA:0:8}
git clone --branch $BR https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git $SRC   # [확인 필요] gcp2 clone 방식·인증(기존 관례를 따름)
cd $SRC && test "$(git rev-parse HEAD)" = "$SHA" && test -z "$(git status --porcelain)" && echo CLEAN_OK
```
| # | 항목 | 명령 | 기대값 / 상태 |
|---|---|---|---|
| 0.1 | source clone이 HEAD이고 clean | 위 `CLEAN_OK` | 실행 시 |
| 0.2 | nav venv(MuJoCo·Warp) | `$P -c "import mujoco, warp, mujoco_warp; print(mujoco.__version__, warp.__version__)"` | **[확인 필요]** gcp2 `$P` 경로. 스택 복제 작업(RUN_QUEUE gcp2 지금 1)이 새로 만든 `.venv-warp`. gcp6 기준 고정값은 MuJoCo 3.16.0·Warp 1.15.0(RUN_QUEUE gcp6 다음 1)이고, nav r5 venv도 같은지 [확인 필요] |
| 0.3 | ACT torch env | `$ACT_PY -c "import torch, sys; print(sys.version, torch.__version__, torch.cuda.is_available())"` | `True`. 보고서 기록 경로는 `/home/ugrp/ugrp-rl1b-act-env/bin/python`이지만 **gcp2에 있는지 [확인 필요]** |
| 0.4 | ACT source(C2c run source) | `git -C $ACT_SRC rev-parse HEAD`; `git -C $ACT_SRC status --porcelain --untracked-files=no` | `257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8`(브랜치 `dsh/act18-c2c-v7clock`), 출력 비어 있음. gcp2 clone 경로 **[확인 필요]** |
| 0.5 | R8 체크포인트 | `ls $CKPT/model.safetensors $CKPT/adapter.json && sha256sum $CKPT/model.safetensors` | `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`(보고서 기록값). 보고서 기록 경로는 `/home/ugrp/ugrp-sim/runs/act18/training-r1/R8/step-100000`, **gcp2 존재 [확인 필요]** |
| 0.6 | nav calibration(r5와 같은 파일) | `ls $CAL && sha256sum $CAL` | gcp6 경로는 `/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json`. gcp2 복사본 경로와 sha256이 gcp6과 같은지 **[확인 필요]** |
| 0.7 | GPU 비어 있음 | `nvidia-smi` | 다른 작업(C4b 등)과 겹치지 않을 것. 1b는 MJWarp와 torch를 한 GPU에 같이 올립니다. 메모리는 **측정한 적 없음 [확인 필요]** |
| 0.8 | carry 자세 판정(단계 3만) | gcp6 렌더 `measure.json`을 gcp2로 복사하고 `sha256sum` | `.verdict.adopted == "act_lift_end"`이면 `--carry-pose-verdict`로 넘깁니다. 아직 없으면 `--assume-verdict act_lift_end`로 돌리고, 출력에 "NOT render-verified"로 남습니다. 판정이 다른 자세면 드라이버가 `E2E_MIN_TODO:carry_pose_transition`으로 거부하므로 단계 3은 하지 않습니다 |

## 1. 변수 (clone 루트에서, 같은 셸)
```bash
cd $SRC
P=<[확인 필요] gcp2 nav .venv-warp>/bin/python
ACT_PY=<[확인 필요] /home/ugrp/ugrp-rl1b-act-env/bin/python>
ACT_SRC=<[확인 필요] act18-c2c 257dcacc clone>
CKPT=<[확인 필요] .../R8/step-100000>
CAL=<[확인 필요] gcp2 nav-calibration.json>
RUNS=/home/ugrp/ugrp-sim/runs          # [확인 필요] gcp2에서도 같은 경로인지
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=$RUNS/e2e-min-standalone-$TS       # 새 디렉터리(하위 단계별 하위 폴더는 드라이버가 만듦, 이미 있으면 OUTPUT_EXISTS)
mkdir -p $OUT
ACT_ARGS="--act-python $ACT_PY --act-source $ACT_SRC --expected-act-sha 257dcaccc95a6e185f6fcbac2e3837ba4ba6a8b8 \
  --checkpoint $CKPT --expected-model-sha256 e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a"
# gcp6 E2E smoke와 같은 actuation(duty_port_v1). E2E_MIN_HANDOFF 없이 켜면 issue()가 거부합니다
export E2E_MIN_HANDOFF=on_v1 E2E_MIN_ACTUATION=duty_port_v1
```
- 반드시 clone 루트에서 실행합니다(`CWD_MUST_BE_CLONE_ROOT`). source가 dirty이거나 SHA가 다르면 `SOURCE_DIRTY` / `SOURCE_SHA_MISMATCH`로 멈춥니다.

## 2. 단계별 명령
```bash
# 1a. ACT 서버 단독(synthetic, 물리 없음)
$P scripts/e2e_min_standalone_smoke.py act-server --enabled --out $OUT/1a-act-synthetic \
  --expected-source-sha $SHA $ACT_ARGS --frames synthetic --ticks 30
jq '{status, receipt, receipt_problems, plumbing, server_start_s, wall_s, calls, error}' $OUT/1a-act-synthetic/standalone-act-server.json

# 1b. ACT 서버 + world 1개 집기 요청 왕복(30 tick)
$P scripts/e2e_min_standalone_smoke.py act-server --enabled --out $OUT/1b-act-render \
  --expected-source-sha $SHA $ACT_ARGS --frames render --ticks 30
jq '{status, plumbing, world_init_s, loop_s, wall_s, actuation, eval_only, error}' $OUT/1b-act-render/standalone-act-server.json

# 2. release_open_v1 단독(MJWarp, 큐브 없음)
$P scripts/e2e_min_standalone_smoke.py release-open --enabled --out $OUT/2-release \
  --expected-source-sha $SHA --physics warp --calibration $CAL
jq '{status, plumbing, ticks, done_tick, eval_only, wall_s, error} + {backed_m: (.scripts|map_values(.backed_m))}' $OUT/2-release/standalone-release-open.json

# 3. nav carry adapter 운반 주행 렌더(팔 act_lift_end 고정, 슬롯 고정, 큐브 없음)
export E2EWARP_NAV_GATE_MODE=v230_r5 E2EWARP_NAV_ARRIVAL=odom_projection \
       E2EWARP_NAV_CALIBRATION=$CAL E2EWARP_NAV_L1LITE=on_v1
$P -m scripts.e2ewarp_nav_manifest --out $OUT/nav-components.json --calibration $CAL --source-sha $SHA
$P scripts/e2e_min_standalone_smoke.py nav-render --enabled --out $OUT/3-nav-render \
  --expected-source-sha $SHA --components $OUT/nav-components.json \
  --carry-pose-verdict <[확인 필요] gcp6 measure.json 복사본> --carry-pose-verdict-sha256 <[확인 필요]>
#   (판정 파일이 아직 없으면 위 두 인자 대신: --assume-verdict act_lift_end)
jq '{status, plumbing, ticks, robots, carry_pose_verdict, wall_s, error}' $OUT/3-nav-render/standalone-nav-render.json

sha256sum $(find $OUT -name 'standalone-*.json') > $OUT/SHA256SUMS
```
- 1a가 실패하면 1b는 돌리지 않습니다. 2와 3은 ACT와 무관하므로 1의 결과와 상관없이 돌립니다.
- 각 명령의 종료 코드는 `PLUMBING_OK`면 0, 아니면 1입니다. 실패해도 JSON은 남습니다(`status`, `error`).

## 3. 성공 기준 (배관 확인만, 판정 아님)
| 단계 | `status == PLUMBING_OK` 조건(드라이버가 계산) | 추가로 볼 것(기록만) |
|---|---|---|
| 1a | 서버 `ready`, receipt의 `act_source_sha`·`model_sha256`가 기대값과 같고, `done_head=false`, `loop_overlay=false`, executor `{n_action_steps:1, temporal_ensemble_coeff:0.01}`. 로봇마다 30개 요청 모두에 계약 검증을 통과한 명령과 bool `done`이 돌아옴 | `server_start_s`, 행별 `latency_s`, `receipt.device`, `act-server.stderr.log` |
| 1b | 1a와 같은 조건 + world 초기화와 30 tick step이 예외 없이 끝남 | `world_init_s`, `loop_s`, `eval_only.cube_start/end`·`base_start/end`(GT, 기록만), `frames/*.jpg` 육안 확인 |
| 2 | 로봇마다 `done`에 도달, 그리퍼 명령이 `OPEN_PWM=2000`에 도달, 자기 odometry 후진 ≥ `backoff_m`(0.15) | `eval_only.base_displacement_m`(GT)와 `backed_m`(자기 odometry)의 차이. 기록만 하고 판정하지 않습니다 |
| 3 | 로봇마다 adapter가 1회 이상 질의됨, 발행 PWM이 모두 hold 값 | `robots.<r>.arrived_tick`/`no_claim_tick`(자기 claim, 검증 안 됨), `moving_ticks`, `base_start/end`(GT), `destination`, `frames/` |

도착 여부, 큐브가 들렸는지, 후진 거리의 GT 일치는 **성공 기준이 아닙니다**. 기록만 합니다.

## 4. 예상 GPU 시간·비용 (gcp2 L4 1장, $1.096/h)
| 단계 | 예상 GPU 시간 | 비용 |
|---|---|---|
| 0 사전 확인 + clone | ≤ 0.10 h | ≤ $0.11 |
| 1a | ≤ 0.10 h(서버 기동과 체크포인트 로드가 대부분) | ≤ $0.11 |
| 1b | ≤ 0.20 h(Warp 커널 컴파일·graph capture 포함, 30 tick) | ≤ $0.22 |
| 2 | ≤ 0.15 h(최대 120 tick, 기본값이면 약 23 tick에 done: 정지 3 + 열기 8 + 후진 약 11 + done 1) | ≤ $0.16 |
| 3 | ≤ 0.30 h(최대 600 tick, 둘 다 도착하면 조기 종료) | ≤ $0.33 |
| **합계** | **≤ 0.85 h**(상한 1 h) | **≤ $0.93**(1 h면 $1.10). 런당 $20보다 훨씬 작음 |
- tick당 wall 시간과 Warp 커널 캐시가 비어 있는 첫 컴파일 시간은 gcp2 실측이 없습니다 **[확인 필요]**. 1 h를 넘길 것 같으면 3을 `--ticks 300`으로 줄이고, 그 사실을 보고합니다.

## 5. 실패 시 보고할 것
- 공통: 단계, `status`, `error` 전체, 출력 JSON 경로와 sha256, `$SHA`, `nvidia-smi` 한 줄, venv 버전(0.2·0.3 출력).
- 1a·1b: `act-server.stderr.log` 전체. `receipt_problems`, `plumbing.problems`. 서버가 `{"error":...}`로 끝났으면 그 줄(`ACT source SHA mismatch`, `checkpoint sha256 mismatch`, `ACT source must be clean`, CUDA 없음 등).
- 1b·2·3: `transport()` 또는 `initialize`에서 난 예외(`CUDA required`, `one exact scene model per batch required`, nconmax/njmax overflow)의 traceback 전체.
- 2: `scripts.<r>.log`의 단계 순서(stop → open → backoff → done)가 어디서 끊겼는지, `release_open_v1 backoff tick cap reached`가 났는지.
- 3: `NAV_CALIBRATION_*`, `NAV_SLOT_*`, `NAV_ARRIVAL_REQUIRES_V230_R3`, `L1LITE_ORDER_CANDIDATE_MISSING`, `E2E_MIN_TODO:carry_pose_transition` 등 코드명. `robots.<r>`와 마지막 프레임 몇 장.
- 코드 수정이 필요한 막힘은 고치지 말고 증상과 로그 경로를 스레드에 올립니다(Claude가 고침).

## 6. 로컬 CPU 테스트 (실행 전 재확인용, GPU 없음)
```bash
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_e2e_min_standalone.py
```
2026-10-21 브랜치 기준 24 passed입니다. 실제 `NavRobot`·`navigation_factory`·`ActServerCore`·`ReleaseOpenV1`을 가짜 world와 loopback transport에 붙여 세 하위 명령의 CPU 경로를 확인합니다. MuJoCo·Warp·torch 경로는 VM에서만 확인됩니다.
