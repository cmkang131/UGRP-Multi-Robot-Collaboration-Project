#!/usr/bin/env bash
# Comparison only; no simulation/control environment changes. No runtime cap.
set -euo pipefail
ROOT=/home/ugrp/ugrp-sim/mast3rcmp
mkdir -p "$ROOT" /home/ugrp/ugrp-sim/leases
export MAST3RCMP_ROOT="$ROOT"
python3 - <<'PY'
import json,os,time
from pathlib import Path
Path('/home/ugrp/ugrp-sim/leases/mast3rcmp.json').write_text(json.dumps(dict(task='mast3rcmp',pid=os.getppid(),start=time.time(),expected_end=None)))
PY
exec > >(tee -a "$ROOT/install.log") 2>&1
export PATH=/usr/local/cuda-12.9/bin:$PATH
export CUDA_HOME=/usr/local/cuda-12.9
sudo env DEBIAN_FRONTEND=noninteractive apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential python3.12-dev
command -v c++ nvcc
export MAX_JOBS=4
export TORCH_CUDA_ARCH_LIST=8.9
export GIT_LFS_SKIP_SMUDGE=1
if [ ! -d "$ROOT/MASt3R-SLAM/.git" ]; then
  git clone https://github.com/rmurai0610/MASt3R-SLAM.git "$ROOT/MASt3R-SLAM"
fi
cd "$ROOT/MASt3R-SLAM"
git checkout --detach e6f4e3d474fad0e11f561482012be864ba8c3f17
git -c filter.lfs.smudge= -c filter.lfs.required=false submodule update --init --recursive
python3.12 -m venv "$ROOT/venv"
source "$ROOT/venv/bin/activate"
python -m pip install 'pip==25.0.1' 'setuptools==70.0.0' wheel ninja 'numpy==1.26.4' cython
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
# Headless inference dependencies only; training/demo/viewer extras are omitted.
python -m pip install 'numpy==1.26.4' einops roma 'huggingface-hub==0.28.1' 'opencv-python-headless==4.11.0.86' scipy matplotlib tqdm scikit-learn trimesh pillow pyyaml natsort plyfile pyrealsense2 faiss-cpu
python -m pip install --no-deps --no-build-isolation -e thirdparty/mast3r
python -m pip install --no-deps --no-build-isolation ./thirdparty/mast3r/dust3r/croco/models/curope
python -m pip install --no-deps --no-build-isolation ./thirdparty/mast3r/asmk
if [ ! -d "$ROOT/lietorch/.git" ]; then
  git clone https://github.com/princeton-vl/lietorch.git "$ROOT/lietorch"
fi
git -C "$ROOT/lietorch" checkout --detach e7df86554156b36846008d8ddbcc4d8521a16554
git -C "$ROOT/lietorch" submodule update --init --recursive
python -m pip install --no-deps --no-build-isolation "$ROOT/lietorch"
python -m pip install --no-deps --no-build-isolation -e .
mkdir -p checkpoints
for asset in MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric.pth MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric_retrieval_trainingfree.pth MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric_retrieval_codebook.pkl; do
  if [ ! -f "checkpoints/$asset" ]; then
    curl --fail --location --output "checkpoints/$asset.partial" "https://download.europe.naverlabs.com/ComputerVision/MASt3R/$asset"
    mv "checkpoints/$asset.partial" "checkpoints/$asset"
  fi
done
sha256sum checkpoints/* > "$ROOT/checkpoint-sha256.txt"
python -m pip freeze > "$ROOT/freeze.txt"
git submodule status --recursive > "$ROOT/submodules.txt"
sha256sum LICENSE.md thirdparty/mast3r/LICENSE thirdparty/mast3r/CHECKPOINTS_NOTICE mast3r_slam_backends*.so > "$ROOT/install-sha256.txt"
python - <<'PY'
import torch,mast3r_slam_backends,lietorch,curope
print('INSTALL_IMPORT_PASS',torch.__version__,torch.cuda.get_device_name(0))
PY
