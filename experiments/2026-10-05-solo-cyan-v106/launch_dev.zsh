#!/bin/zsh
# Coordinator only. This file was syntax-checked, never launched in the sandbox.
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/solo-cyan
solo_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
solo_sha=${1:?expected full source SHA required}
solo_out=${2:?absolute new output directory required}
solo_stage=${3:-place}
[[ $(git rev-parse HEAD) == "$solo_sha" ]]
[[ $(git branch --show-current) == claude/solo-cyan ]]
[[ -z $(git status --porcelain) ]]
[[ ! -e "$solo_out" && ! -e "${solo_out}-managed" ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
[[ -f /Users/changmin/projects/ugrp/outputs/v98-probe-tools/sim_watchdog.py ]]

"$solo_py" scripts/agent_lock.py acquire --owner claude --branch claude/solo-cyan \
  --purpose "S2 solo cyan v106 ${solo_stage} DEV" --pid $$ --expected-minutes 180
solo_sim_pid=''
solo_watch_pid=''
cleanup() {
  if [[ -n "$solo_sim_pid" ]] && kill -0 "$solo_sim_pid" 2>/dev/null; then
    kill -TERM "$solo_sim_pid" 2>/dev/null || true
    wait "$solo_sim_pid" 2>/dev/null || true
  fi
  if [[ -n "$solo_watch_pid" ]]; then
    kill -TERM "$solo_watch_pid" 2>/dev/null || true
    wait "$solo_watch_pid" 2>/dev/null || true
  fi
  "$solo_py" scripts/agent_lock.py release --owner claude
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$solo_py" -m scripts.sim_cli workflow run zone-solo-cyan-v106 \
  --record "${solo_out}-managed" --timeout 10800 -- \
  --execute --expected-source-sha "$solo_sha" --output "$solo_out" \
  --stage-probe "$solo_stage" --seed 911 --robot-id r3 --pickup-slot P1-2 \
  --destination B --passage-id door_1 --speedups v98-exact-v6 --lock-owner claude &
solo_sim_pid=$!
"$solo_py" /Users/changmin/projects/ugrp/outputs/v98-probe-tools/sim_watchdog.py \
  "$solo_out" --pid "$solo_sim_pid" --stall-sim 30 --hung-wall 300 --every 30 \
  >"${solo_out}-watchdog.log" 2>&1 &
solo_watch_pid=$!
print -r -- "S2 manager PID=$solo_sim_pid watchdog PID=$solo_watch_pid output=$solo_out"
solo_rc=0
wait "$solo_sim_pid" || solo_rc=$?
solo_sim_pid=''
exit "$solo_rc"
