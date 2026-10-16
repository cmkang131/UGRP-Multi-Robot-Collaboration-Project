#!/bin/bash
# usage: run_ens_task.sh CFG ROBOT SEED_OFFSET [UNTIL=60]   CFG in base|B|C|C2  (trees built from #363 HEAD 94d083ba; C/C2 replay with the candidate calibration)
D=/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005
S=/private/tmp/claude-501/-Users-changmin-projects-ugrp/e27d913e-82e1-4e26-ba35-c8e9658b6400/scratchpad/gc
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
RAW=/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3
cfg=$1; r=$2; off=$3; u=${4:-60}
extra=""
case $cfg in
  base) WT=$S/base94d;;
  B) WT=$S/tree_B;;
  C) WT=$S/tree_C; extra="--cal-path $S/tree_C/experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json --cal-sha aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4";;
  C2) WT=$S/tree_C2; extra="--cal-path /Users/changmin/projects/ugrp/outputs/calib-gain-v101-product-20261005/C2/calibration_dev_pilot_unloaded_v101.json --cal-sha 8afc61252934fd69e3a56a074d73d6f23dac0dad31a407987170a7c01b976aa8";;
esac
out=$D/replay/ens_${cfg}_${r}_s${off}_until${u}
PF_REPLAY_WT=$WT nice -n 8 $PY $D/tools/replay_pf.py $RAW $r $out.jsonl --until $u --seed-offset $off $extra > $out.log 2>&1
