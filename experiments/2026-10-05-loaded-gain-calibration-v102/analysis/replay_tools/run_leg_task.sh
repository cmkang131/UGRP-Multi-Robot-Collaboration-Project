#!/bin/bash
# usage: run_leg_task.sh TREE CFGNAME ROBOT SEEDOFF MODE [CALPATH CALSHA]    TREE: scratch tree dir (base14b | new), MODE: meas | nomeas
D=/Users/changmin/projects/ugrp/outputs/pf-loadedgain-v102-20261005
S=/private/tmp/claude-501/-Users-changmin-projects-ugrp/e27d913e-82e1-4e26-ba35-c8e9658b6400/scratchpad/ld2
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
RAW=/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-fcc5215f/zone_wide_door_geometry_v3
tree=$1; cfg=$2; r=$3; off=$4; mode=$5; calp=$6; cals=$7
CAL=""; [ -n "$calp" ] && CAL="--cal-path $calp --cal-sha $cals"
NM=""; [ "$mode" = nomeas ] && NM="--nomeasure"; PP="--partner-plan"
out=${OUTDIR:-$D/replay}/${cfg}_${r}_s${off}_${mode}
PF_REPLAY_WT=$S/$tree nice -n 8 $PY $D/tools/replay_pf.py $RAW $r $out.jsonl --seed-offset $off $CAL $NM $PP > $out.log 2>&1
echo "EXIT $?" >> $out.log
