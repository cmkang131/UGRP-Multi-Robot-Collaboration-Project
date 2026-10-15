#!/bin/bash
# On the existing GCP L4 only, after fresh budget/lifecycle/disk preflight.
# Reproduces the pinned training source; use a fresh output directory.
set -euo pipefail
arm=${1:?p0 or p02}
out=${2:?fresh absolute output directory on the retained L4 disk}
case "$arm" in p0) dropout=0.0;; p02) dropout=0.2;; *) exit 2;; esac
cd /home/ugrp/act13train-source-961aa751
test "$(git rev-parse HEAD)" = 961aa7517b29f187f6869e2624ed848ee2c32cfd
exec timeout -s INT -k 30 900 /home/ugrp/ugrp-act-env/bin/python -m scripts.train_grasp_act \
  --dataset /mnt/act-source/act13train-961aa751/dataset --output "$out" \
  --stage smoke --steps 300 --max-wall-s 840 --seed 20261015 \
  --done-loss balanced_bce_v1 --done-loss-weight 1 --command-history-dropout "$dropout" \
  --run-class dev --profile-timing --checkpoint-every 5000
