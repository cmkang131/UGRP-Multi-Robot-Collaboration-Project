# E2E-1' smoke 실행 명령 (gcp6, DeepSeek 실행용)

작성: 2026-10-21 Claude 구현 워커. 이 문서는 명령만 정리한 것이고, 실행 승인을 대신하지 않습니다.
- 브랜치는 `claude/e2e-min-runner`입니다(base `dsh/e2e-min-runner` 7169bcae5). main 병합은 없습니다.
- 실행은 오프피크(UTC 16:30–00:30)에만 합니다. smoke는 1회이고 결과는 합산하지 않습니다(PREREG_DRAFT §1).
- 값을 확인하지 못한 곳은 [확인 필요]로 두었습니다. 추측으로 채우지 말고, 확인한 값을 넣은 뒤 실행합니다.

## 0. 사전 확인 (하나라도 실패하면 실행하지 않음)
| # | 항목 | 확인 방법 | 상태 |
|---|---|---|---|
| 0.1 | source clone이 브랜치 HEAD이고 clean인지 | `git -C $SRC_DIR rev-parse HEAD`, `git status --porcelain` 비어 있음 | 실행 시 |
| 0.2 | gcp6에 ACT torch env가 있는지 | `$ACT_PY -c "import torch; print(torch.cuda.is_available())"` | **[확인 필요]** DESIGN §6.2: env·checkpoint는 gcp2에 있었습니다 |
| 0.3 | ACT source(`act18-c2c` 257dcacc…)와 R8 step-100000 checkpoint가 gcp6에 있고 sha가 맞는지 | `git -C $ACT_SRC rev-parse HEAD`, `sha256sum` | **[확인 필요]** 전체 SHA·sha256 값 |
| 0.4 | 운반 자세 렌더 판정 파일(`measure.json`)과 sha256 | `CARRY_POSE_RENDER_DRAFT.md` 결과 | **[확인 필요]** 판정이 `act_lift_end`가 아니면 `NavCarryAdapter`가 거부합니다 |
| 0.5 | nav calibration(r5와 같은 파일) | `ls $E2EWARP_NAV_CALIBRATION` | r5 값 재사용 |
| 0.6 | relay(loopback 18627)·host receipt·lease·잔액 | r5 README와 같은 점검 | 실행 시 |
| 0.7 | 같은 GPU에서 MJWarp와 ACT(torch)를 같이 띄울 메모리 | `nvidia-smi` | **[확인 필요]** 측정한 적 없음 |

## 1. 변수
```bash
# VM clone root (Linux gcp6 only). 출력은 모두 /home/ugrp/ugrp-sim/runs 아래 새 경로.
cd $SRC_DIR                                   # claude/e2e-min-runner checkout, clean
SRC=$(git rev-parse HEAD)
P=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
RUNS=/home/ugrp/ugrp-sim/runs
SEED=601            # [확인 필요] PREREG_DRAFT §3: L1-lite test 표의 seed. smoke는 본실행과 같은 seed
CONDITION=no_comm   # [확인 필요] PREREG 확정값. smoke는 LLM 호출이 가장 적은 no_comm 권고
```

## 2. E2E config (repo 밖에 둡니다. repo 안이면 FROZEN_SOURCE_DIRTY로 막힙니다)
```bash
mkdir -p $RUNS/e2e-min-config
cat > $RUNS/e2e-min-config/e2e1p-smoke-$TS.json <<'JSON'
{"level": "E2E-1p",
 "cubes": {"r1": {"item_id": "cyan_1", "xy": [-0.05, -2.375]},
           "r2": {"item_id": "red_1",  "xy": [-0.05, -2.875]}},
 "carry_pose_verdict": {"path": "<[확인 필요] measure.json 절대경로>", "sha256": "<[확인 필요]>"},
 "act": {"python": "<[확인 필요] gcp6 ACT env python>",
         "act_source": "<[확인 필요] act18-c2c-257dcacc clone>",
         "expected_act_sha": "<[확인 필요] 40자>",
         "checkpoint": "<[확인 필요] R8/step-100000>",
         "expected_model_sha256": "<[확인 필요] e1ec6592...>",
         "device": "cuda"},
 "release": {"stop_ticks": 3, "backoff_m": 0.15},
 "sim_budget_s": 200.0}
JSON
```
- 큐브 위치는 DESIGN §3.1의 제안값입니다. 정확한 값은 [확인 필요]입니다.
- `release` 값은 현재 기본값입니다. 사전 등록 전이라 [확인 필요]입니다.

## 3. 환경 변수
```bash
export E2EWARP_NAV_GATE_MODE=v230_r5
export E2EWARP_NAV_ARRIVAL=odom_projection
export E2EWARP_NAV_CALIBRATION=/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json
export E2EWARP_NAV_L1LITE=on_v1
export E2E_MIN_HANDOFF=on_v1
export E2E_MIN_CONFIG=$RUNS/e2e-min-config/e2e1p-smoke-$TS.json
export E2E_MIN_ACTUATION=duty_port_v1   # ACT owner와 같은 servo 갱신 순서(DESIGN §3.5). 끄려면 unset
```
prepare와 execute는 같은 셸에서 같은 값으로 실행합니다. 값이 바뀌면 `E2E_CONFIG_CHANGED_SINCE_PREPARE` 또는 `E2E_ACTUATION_CHANGED_SINCE_PREPARE`로 멈춥니다.

## 4. components → prepare → execute
```bash
$P -m scripts.e2ewarp_nav_manifest --out $RUNS/e2e-min-components-$TS.json \
  --calibration "$E2EWARP_NAV_CALIBRATION" --source-sha $SRC

$P -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 \
  --seed $SEED --nworld 1 --condition $CONDITION \
  --components $RUNS/e2e-min-components-$TS.json --arrival-odom-projection \
  --output $RUNS/e2e-min-smoke-$TS-admission

$P -m scripts.run_e2e_warp --mode nav --execute --e2e-warp-batch on_v1 \
  --seed $SEED --nworld 1 --condition $CONDITION \
  --queue $RUNS/e2e-min-smoke-$TS-admission/queue.json --expected-source-sha $SRC \
  --host-receipt <[확인 필요] r5와 같은 host receipt> \
  --components $RUNS/e2e-min-components-$TS.json --arrival-odom-projection \
  --relay-url http://127.0.0.1:18627/v1/chat/completions \
  --output $RUNS/e2e-min-smoke-$TS
```
- `--nav-solo-robot`은 쓰지 않습니다(E2E-min은 pair·1 world만 허용, 아니면 `E2E_MIN_REQUIRES_L1LITE_PAIR_ONE_WORLD`).
- `--nav-sim-budget-s`는 nav 큐 값일 뿐이고, E2E 루프 예산은 config의 `sim_budget_s`(200 s)입니다.
- 예상 시간과 토큰은 [확인 필요]입니다. r5 pair는 60 SIM s였고, 여기서는 최대 200 SIM s에 ACT 추론이 더해집니다. 실행 뒤 실측을 남깁니다.

## 5. 실행 직후 확인
| 파일 | 볼 것 |
|---|---|
| `…-admission/queue.json` | `e2e_min=on_v1`, `e2e_level=E2E-1p`, `e2e_config.sha256`, `e2e_actuation=duty_port_v1` |
| `…-admission/stack-check.json` | `ok: true` |
| `…/result.json`(runner 결과) | status가 `E2E_EPISODE_FINISHED`인지. `HOST_ERROR`이면 error에 `E2E_SESSION_CLOSE:`가 있는지 |
| `…/e2e-handoff.json` | 로봇별 단계 전환(grasp → settle → carry → release → done)과 실패 코드 |
| `…/act-server.stderr.log` | ACT source SHA·checkpoint sha 검사 통과, CUDA 사용 |
| `…/world-00/eval-geometry.json` | `cube_qpos_adr`, `cube_half_m`, `cargo_contact_pairs` |

판정은 eval-only 재계산으로 합니다(runner는 성공을 주장하지 않습니다):
```bash
$P -c "import json,sys; from harness.e2e_min_eval import recount_run; \
print(json.dumps(recount_run(sys.argv[1]), ensure_ascii=False, indent=1))" $RUNS/e2e-min-smoke-$TS
```
`recount_run`의 zone·drop 인자는 PREREG 확정 전이라 기본값을 씁니다([확인 필요]).

## 6. 로컬 CPU 테스트 (실행 전 재확인용, GPU 없음)
```bash
/home/ubuntu/ugrp-e1-venv/bin/python -m pytest -q tests/test_e2e_min*.py tests/test_e2ewarp_l1lite.py \
  tests/test_e2ewarp_nav_*.py tests/test_nav_v230_fwd24_prereg.py tests/test_e2ewarp_selfnav.py \
  tests/test_e2e_warp.py
```
2026-10-21 브랜치 HEAD 기준 311 passed입니다.
