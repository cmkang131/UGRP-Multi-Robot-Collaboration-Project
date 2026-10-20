# pairact P0: gcp6 실행 묶음 (2026-10-20 밤, 19:00 KST 이후)

DeepSeek용 실행 문서입니다. 진단만 하며 관문 결과는 주장하지 않습니다. VM은 gcp6(`ugrp-act-l4-gcp6`)만 쓰고, 끝나면 정지합니다. 다른 GPU 작업과 겹치지 않게 *순서대로* 돌립니다. `--gcp6-isolated-v1`은 GPU 클라이언트가 이미 있으면 실행을 거부합니다.

## 0. 준비 (gcp6)
```bash
cd /home/ugrp/ugrp-sim && git -C ugrp fetch origin dsh/pairact-p0-diag   # 또는 아래 2개 파일만 scp
mkdir -p /home/ugrp/ugrp-sim/ops-reviews/pairact-p0
git -C ugrp show origin/dsh/pairact-p0-diag:experiments/2026-10-21-pairact-p0/repro_cuda.sh > ops-reviews/pairact-p0/repro_cuda.sh
git -C ugrp show origin/dsh/pairact-p0-diag:experiments/2026-10-21-pairact-p0/repeat27.sh  > ops-reviews/pairact-p0/repeat27.sh
```
- `/home/ugrp/ugrp-sim/ugrp`가 이 레포의 clone인지는 [확인 필요]입니다. 아니면 Mac이나 OCI에서 두 파일을 scp합니다.
- 두 스크립트 모두 기본값은 `plan`이고 명령만 출력합니다. `run`일 때만 실행합니다.

### 경로 (r13 기록 기준, 기본값)

| 변수 | 기본값 | 근거 |
|---|---|---|
| `PY` | `/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python` | gcp6setup README |
| `RUNNER` | `/home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py` | r13 summary `reproduce` |
| `WARP_SOURCE_ROOT` | `/home/ugrp/ugrp-sim/src/05046e9d245e46b4ee3d1c43308f7258a9fa41c5` | **[확인 필요]** r13 `source_sha`가 05046e9d입니다. 디렉터리 이름은 관례로 추정했습니다. preflight에서 HEAD가 05046e9d인지 검사합니다. 다르면 `ls /home/ugrp/ugrp-sim/src`로 찾아 `WARP_SOURCE_ROOT=...`를 지정합니다 |
| `ADAPTER` / `TEACHER` | `src/835ccef2…` / `src/26f84d0f…` | r13 `reproduce`. 그런데 `source_contract`는 adapter d354468a, teacher fe6858ec라서 디렉터리 이름과 내용이 다를 수 있습니다. preflight가 HEAD를 기록합니다 [확인 필요] |
| cases / xml / refs | `runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json`, `runs/beamact5/wide-export-old-8420000e/canonical-scene.xml`, `runs/beamact5/native-refs-8420000e/per-world-references.json` | r13 `reproduce` |

cwd는 반드시 `WARP_SOURCE_ROOT`여야 합니다. r3에서 cwd를 다르게 두어 texture 경로 오류가 난 기록이 있습니다. 스크립트가 cwd를 맞춥니다.

## 1. world 27 같은 seed 3회 반복 (먼저, 약 3 × 15–25 min [확인 필요])
```bash
bash /home/ugrp/ugrp-sim/ops-reviews/pairact-p0/repeat27.sh plan     # 명령 확인
bash /home/ugrp/ugrp-sim/ops-reviews/pairact-p0/repeat27.sh run      # 출력: /home/ugrp/ugrp-sim/runs/pairact-p0/repeat27-<UTC>/rep{1,2,3}
```
- 10/18 `diag-r13-27-repeat1..3`와 같은 명령입니다(동결 r13 스택, `--indices 27`, cap 60). 바뀌는 것은 out 경로뿐입니다.
- 회수할 값: rep마다 success, end_reason, sim_s, align 시간, `alignment_relooks`, `alignment_axes_blocked` 횟수(teacher `search20_log`), summary sha256.
- 이전 값은 단독 1/3 PASS입니다. 실패 signature는 align 7.8 s, relook 3이고, 17.6 s 이후 `alignment_axes_blocked`가 91회 나옵니다. *세 번 모두 공개합니다. 고르지 않습니다.*

## 2. CUDA 700 재현 매트릭스 (그다음)
```bash
bash /home/ugrp/ugrp-sim/ops-reviews/pairact-p0/repro_cuda.sh plan            # preflight + 명령 출력
bash /home/ugrp/ugrp-sim/ops-reviews/pairact-p0/repro_cuda.sh run             # A1 A2 A3 B1 B2
bash /home/ugrp/ugrp-sim/ops-reviews/pairact-p0/repro_cuda.sh run sanitizer   # 위 + S1 (선택, 마지막)
# 출력: /home/ugrp/ugrp-sim/runs/pairact-p0/cuda-repro-<UTC>/{env.txt,matrix.tsv,<id>.log,<id>.kernel.txt,SHA256SUMS.txt}
```
모든 실행에 `CUDA_LAUNCH_BLOCKING=1`을 걸고 cap은 30 SIM s로 둡니다. warp8 overflow가 난 step 226은 약 22.6 s 지점이라 그 구간을 포함합니다.

| id | nworld | indices | nvmax | 목적 |
|---|---|---|---|---|
| A1 | 1 | 0 | 222 (`--full-active-dof-workspace-v1`) | r13과 같은 대조군, 1 world 단독 |
| A2 | 4 | 0–3 | 222 | nworld 축 |
| A3 | 16 | 0–14,16 | 222 | nworld 축 |
| B1 | 4 | 0–3 | 128 (플래그 OFF, warp4와 같음) | nvmax overflow 가설 |
| B2 | 16 | 0–14,16 | 128 | nvmax overflow 가설 |
| S1 | 1 | 0 | 128 | `compute-sanitizer --tool memcheck`, `--diagnostic-ticks 3`, timeout 1 h. warp6에서는 첫 step도 끝내지 못했습니다 |

- `env.txt`에 Warp, MuJoCo, mujoco_warp 버전과 Warp가 보는 CUDA driver/toolkit 버전, pip freeze, nvidia-smi 출력, compute-sanitizer 버전, 소스 HEAD를 기록합니다. 기대값은 warp-lang 1.15.0, mujoco 3.16.0, mujoco-warp 3.16.0(commit `57b4692f`), driver 580.178.04입니다.
- `<id>.kernel.txt`에는 dmesg(`sudo -n`) 또는 journalctl의 Xid/segfault 줄을 남깁니다.
- 판정 방법: 각 행의 rc와 CUDA/overflow 줄 수를 그대로 보고합니다. B행에서만 오류가 나면 nvmax 가설을 지지합니다. A와 B 모두 깨끗하면 gcp6 비-MPS 조건에서는 재현되지 않은 것이고, MPS·다중 프로세스 축이 남습니다.
- **MPS 축은 재현하지 않습니다.** gcp6 runner가 `--gcp6-isolated-v1`에서 `CUDA_MPS_*`를 거부합니다. warp4의 실패 조건(MPS 3 프로세스, gcp2)을 그대로 재현하려면 별도 승인이 필요합니다.
- `compute-sanitizer`가 PATH에 없으면 `/usr/local/cuda/bin`을 PATH에 추가합니다. 거기에도 없으면 S1은 건너뛰고 [확인 필요]로 보고합니다.

## 3. 끝나면
- `matrix.tsv`, `env.txt`, `SHA256SUMS.txt`, repeat27의 `result.tsv`, rep별 summary.json을 Mac/OCI로 회수합니다(원본은 VM에 보존).
- 실행이 남아 있지 않은지 `nvidia-smi`로 확인한 뒤 VM을 정지합니다.
- 결과는 Claude 워커에게 전달합니다. 결과 해석은 `experiments/2026-10-21-pairact-p0/README.md`에 추가합니다.

## 예상 GPU 시간
- repeat27: r13 단독 실행 wall 기록으로 산정해야 합니다 [확인 필요]. 39-world gate가 43 min이었습니다.
- 매트릭스 A1–B2: 행당 timeout 45 min, 30 SIM s 기준으로 대략 1.5–2.5 h [확인 필요]. S1은 최대 1 h입니다.
