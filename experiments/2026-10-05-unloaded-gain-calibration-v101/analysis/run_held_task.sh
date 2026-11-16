#!/bin/bash
# usage: run_held_task.sh CFG CASE ROBOT   false-positive check on the held-out dock probes (CASE 3358372e|7623c4dc); no relocalization happens there
D=/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005
S=/private/tmp/claude-501/-Users-changmin-projects-ugrp/e27d913e-82e1-4e26-ba35-c8e9658b6400/scratchpad/gc
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
cfg=$1; case=$2; r=$3
RAW=/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-${case}/before_door
case $cfg in ctrlC) T=tree_C;; CR1) T=tree_CR1;; I) T=tree_I;; esac
CAL="--cal-path $S/$T/experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json --cal-sha aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4"
out=$D/replay/held_${cfg}_${case}_${r}
PF_REPLAY_WT=$S/$T nice -n 8 $PY $D/tools/replay_pf_rec.py $RAW $r $out.jsonl $CAL --arm-reloc > $out.log 2>&1
