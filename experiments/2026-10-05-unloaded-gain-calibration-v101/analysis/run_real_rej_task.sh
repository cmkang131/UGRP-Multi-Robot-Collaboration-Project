#!/bin/bash
# usage: run_real_rej_task.sh CFG ROBOT SEED_OFFSET   CFG: base (tree at #363 HEAD, recorded DEV calibration) | ctrlC | CR1 | I (calibration C)
# Case: v98-dev-probe-dock_approach-1236c63d (commit 1236c63d has the arrival-view check): r1's arrival is REALLY rejected (recorded begin_relocalization at provider
# time 46.24 s = frame time 46.40 s, then a second rejection ends the approach at ~64 s). The recorded relocalization is armed through the production helper.
D=/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005
S=/private/tmp/claude-501/-Users-changmin-projects-ugrp/e27d913e-82e1-4e26-ba35-c8e9658b6400/scratchpad/gc
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
RAW=/Users/changmin/projects/ugrp/outputs/v98-dev-probe-dock_approach-1236c63d/zone_wide_door_geometry_v3
cfg=$1; r=$2; off=$3
CAL=""
case $cfg in base) T=base94d;; ctrlC) T=tree_C;; CR1) T=tree_CR1;; I) T=tree_I;; esac
[ "$cfg" != base ] && CAL="--cal-path $S/$T/experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json --cal-sha aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4"
out=$D/replay/real_${cfg}_${r}_s${off}
PF_REPLAY_WT=$S/$T nice -n 8 $PY $D/tools/replay_pf_rec.py $RAW $r $out.jsonl --seed-offset $off $CAL --arm-reloc > $out.log 2>&1
