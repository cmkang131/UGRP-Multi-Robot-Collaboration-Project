#!/bin/bash
# Fresh public image/packages. Training dataset is transferred separately by explicit allowlist; no keys/agent config.
set -euo pipefail
sudo env DEBIAN_FRONTEND=noninteractive apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12-venv libosmesa6 libgl1 libglfw3 ffmpeg fonts-noto-cjk rsync zstd
mkdir -p /home/ugrp/ugrp-sim/{ugrp,src,runs,leases,setup}
python3.12 -m venv /home/ugrp/ugrp-sim/ugrp/.venv-sim
/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/pip install mujoco==3.12.0 numpy==2.5.2 opencv-python-headless==5.0.0.93 pillow==12.3.0 websockets==15.0.1 glfw==2.10.2 PyOpenGL==3.1.10 scipy==1.17.1
python3.12 -m venv /home/ugrp/ugrp-sim/ugrp/.venv-warp
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/pip install mujoco==3.16.0 warp-lang==1.15.0 numpy==2.5.2 opencv-python-headless==5.0.0.93 pillow==12.3.0 websockets==17.2 glfw==2.10.2 PyOpenGL==3.1.10 scipy==1.17.1 'https://github.com/google-deepmind/mujoco_warp/archive/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148.zip'
git init --bare /home/ugrp/ugrp-sim/git-shared.git
git --git-dir=/home/ugrp/ugrp-sim/git-shared.git config gc.auto 0
git --git-dir=/home/ugrp/ugrp-sim/git-shared.git config maintenance.auto false
git --git-dir=/home/ugrp/ugrp-sim/git-shared.git config gc.pruneExpire never
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/pip freeze > /home/ugrp/ugrp-sim/setup/warp-freeze.txt
/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/pip freeze > /home/ugrp/ugrp-sim/setup/cpu-freeze.txt

python3.12 -m venv /home/ugrp/ugrp-rl1b-act-env
/home/ugrp/ugrp-rl1b-act-env/bin/pip install --no-deps --extra-index-url https://download.pytorch.org/whl/cu128 -r /home/ugrp/ugrp-sim/setup/act-freeze-reference.txt
/home/ugrp/ugrp-rl1b-act-env/bin/pip freeze > /home/ugrp/ugrp-sim/setup/act-freeze.txt
