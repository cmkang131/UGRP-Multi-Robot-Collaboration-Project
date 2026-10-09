#!/bin/zsh
# Finite handover measurements. Each managed child acquires/releases its own lock.
set -eu
setopt NO_BG_NICE
task_sha=${1:?expected committed SHA required}
task_python=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
task_raw=/Users/changmin/projects/ugrp/outputs
for phase in equivalence speed profile render; do
  until [[ "$(python3 scripts/agent_lock.py status)" == null ]]; do
    sleep 15
  done
  case $phase in
    equivalence) variants=(mesh sphere6_freeze) ;;
    speed|render) variants=(mesh sphere6_v1 mesh_freeze sphere6_freeze) ;;
    profile) variants=(mesh mesh_nofl) ;;
  esac
  "$task_python" -m scripts.sim_cli workflow run masterpi-v7-roller-approx-probe \
    --record "$task_raw/v7-roller-approx-record-${task_sha[1,8]}-$phase" --timeout 900 -- \
    --expected-source-sha "$task_sha" --phase "$phase" --variants $variants \
    --repeats 3 --expected-minutes 15 \
    --output "$task_raw/v7-roller-approx-${task_sha[1,8]}-$phase"
done
