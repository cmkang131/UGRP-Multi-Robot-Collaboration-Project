# MuJoCo·Warp venv RUNBOOK (pairact -c4)

gcp6 2026-10-21 실행(`pairact-p3-detour-20261021T0320Z`)에서 MuJoCo 3.12와 3.16이 섞였습니다. -c4 root는 시작할 때 버전을 검사해 다르면 바로 멈춥니다(`scripts/runtime_pins.py`, `SystemExit('RUNTIME_PIN_MISMATCH: …')`).

## 고정값과 근거

| 용도 | venv (gcp6, 2026-10-20 확인) | 고정값 | 근거 |
|---|---|---|---|
| rollout·init-only (`mjwarp_batch_v1`) | `/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python` (`PYW`) | mujoco 3.16.0, warp-lang 1.15.0, mujoco-warp `57b4692f` | r13 `gate39-r13-run/summary.json` `"mujoco": "3.16.0"`, r3 gate log `Warp 1.15.0 initialized`, `experiments/2026-10-15-simalt3/evidence/warp-freeze.txt` |
| canonical XML export (`--export-compiled-only`)·`prepare_native_references` | `/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python` (`PYS`) | mujoco 3.12.0 | runner `C312 reference export requires3.12`, `evidence/c-freeze.txt` |

- venv 경로는 `dsh/pairact-p0-diag` `experiments/2026-10-21-pairact-p1/TONIGHT.md` §0.1의 확인값입니다. [확인 필요] 지금도 같은지.
- mujoco-warp commit은 PEP 610 `direct_url.json`에서 읽습니다. 로컬 디렉터리 설치처럼 commit을 못 읽으면 멈추지 않고 `summary.json.runtime_pins.mujoco_warp.status = unverified_no_direct_url`로 기록합니다. 읽었는데 다르면 멈춥니다.
- 검사는 root `scripts/run_warp_flow_teacher.py`의 `main()`에 있습니다. VM wrapper `beamact5-tools/run_warp_flow_teacher_gcp6.py`가 이 root의 `main()`을 실행하는지는 [확인 필요]입니다. 판정은 `summary.json`에 `runtime_pins` 키가 있는지로 합니다. 키가 없으면 wrapper가 다른 root를 실행한 것이고, 그 run은 무효입니다.

## 실행 전 확인 (수 초, GPU 없음)

```bash
R=$SRC/root    # -r-c4 체크아웃
PYW=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python; PYS=/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python
$PYW -c "import sys;sys.path.insert(0,'$R/scripts');import runtime_pins as r;print(r.check('rollout'))"
$PYS -c "import sys;sys.path.insert(0,'$R/scripts');import runtime_pins as r;print(r.check('export'))"
```

둘 다 dict를 출력해야 합니다. `RUNTIME_PIN_MISMATCH`가 나오면 그 venv로 실행하지 않습니다.

## venv를 새로 만들어야 할 때 (기존 venv는 덮어쓰지 않음)

새 디렉터리에 만듭니다. 기존 `.venv-warp`·`.venv-sim`은 지우거나 덮어쓰지 않습니다.

```bash
NEW=/home/ugrp/ugrp-sim/venvs/c4-$(date -u +%Y%m%dT%H%MZ); mkdir -p $NEW
python3.12 -m venv $NEW/warp && $NEW/warp/bin/pip install --no-deps -r $R/experiments/2026-10-21-pairact-p2/requirements-rollout-mujoco316.txt
python3.12 -m venv $NEW/sim  && $NEW/sim/bin/pip install --no-deps -r $R/experiments/2026-10-21-pairact-p2/requirements-export-mujoco312.txt
$NEW/warp/bin/pip freeze > $NEW/warp-freeze.txt; $NEW/sim/bin/pip freeze > $NEW/sim-freeze.txt   # 기록·sha256
```

- `requirements-rollout-mujoco316.txt`는 `evidence/warp-freeze.txt`에 `scipy==1.17.1`(`requirements-warp-flows.txt`)을 더한 것입니다. `requirements-export-mujoco312.txt`는 `evidence/c-freeze.txt`와 같습니다.
- [확인 필요] python 3.12: simalt3 README에 `python3.12-venv` 설치 기록이 있습니다. torch 등 teacher 실행에 필요한 다른 패키지가 기존 `.venv-warp`에만 있으면 새 venv에서 import 오류가 납니다. 그때는 기존 venv의 `pip freeze`를 기록하고 Claude에게 넘깁니다(추가 설치로 맞추지 않음).
