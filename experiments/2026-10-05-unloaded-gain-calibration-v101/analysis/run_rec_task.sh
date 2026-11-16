#!/bin/bash
# usage: run_rec_task.sh CFG ROBOT SEED_OFFSET MODE   CFG: ctrlC (tree_C), CR1 (tree_C + R1), I (tree_C + R1 + R2); MODE: one | two rejected arrivals
# r2 has its recorded rejected arrival at 49.10 s (frame time); r1 gets counterfactual ones (first frame >= 49.1 s, and 52.1 s in mode two).
# Calibration C in every tree (candidate selected by the pre-registered rule is recorded in the README; these runs use C for all three).
D=/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005
S=/private/tmp/claude-501/-Users-changmin-projects-ugrp/e27d913e-82e1-4e26-ba35-c8e9658b6400/scratchpad/gc
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
RAW=/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3
cfg=$1; r=$2; off=$3; mode=$4
case $cfg in ctrlC) T=tree_C;; CR1) T=tree_CR1;; I) T=tree_I;; esac
CAL="--cal-path $S/$T/experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json --cal-sha aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4"
if [ "$mode" = one ]; then extra="49.1"; [ "$r" = "r2" ] && extra=""; else extra="49.1,52.1"; [ "$r" = "r2" ] && extra="52.1"; fi
ex=""; [ -n "$extra" ] && ex="--extra-reloc $extra"
out=$D/replay/rec_${cfg}_${r}_s${off}_${mode}_until66
PF_REPLAY_WT=$S/$T nice -n 8 $PY $D/tools/replay_pf_rec.py $RAW $r $out.jsonl --until 66 --seed-offset $off $CAL $ex --arm-reloc > $out.log 2>&1
