#!/bin/zsh
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/drive-friction
cal_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
cal_sha=${1:?source SHA}
cal_out=${2:?absolute output}
cal_states=${3:-all}
[[ $(git rev-parse HEAD) == "$cal_sha" && -z $(git status --porcelain) ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
[[ $("$cal_py" scripts/agent_lock.py status) == null ]]
"$cal_py" scripts/agent_lock.py acquire --owner codex --branch codex/s2-realism --purpose 'S2 stationary checkerboard calibration' --pid $$ --expected-minutes 12
cal_child=''
cleanup() {
  if [[ -n "$cal_child" ]] && kill -0 "$cal_child" 2>/dev/null; then
    kill -TERM "$cal_child" 2>/dev/null || true
    wait "$cal_child" 2>/dev/null || true
  fi
  "$cal_py" scripts/agent_lock.py release --owner codex
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$cal_py" -m scripts.sim_cli workflow run s2-camera-extrinsic-capture-v1 --record "${cal_out}-managed" --timeout 720 -- --execute --expected-source-sha "$cal_sha" --output "$cal_out" --states "$cal_states" &
cal_child=$!
cal_rc=0
wait "$cal_child" || cal_rc=$?
cal_child=''
exit "$cal_rc"
