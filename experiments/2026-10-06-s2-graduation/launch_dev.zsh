#!/bin/zsh
# Frozen S2 graduation launcher, adapted from PR #391.
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/s2-graduation
solo_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
solo_sha=${1:?expected full source SHA required}
solo_out=${2:?absolute new output directory required}
solo_stage=${3:-place}
solo_seed=${4:?preregistered seed required}
solo_slot=${5:?preregistered slot required}
[[ $(git rev-parse HEAD) == "$solo_sha" ]]
[[ $(git branch --show-current) == codex/s2-graduation ]]
[[ -z $(git status --porcelain) ]]
[[ ! -e "$solo_out" && ! -e "${solo_out}-managed" ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
[[ -f /Users/changmin/projects/ugrp/outputs/v98-probe-tools/sim_watchdog.py ]]

[[ $("$solo_py" scripts/agent_lock.py status) == null ]]
"$solo_py" scripts/agent_lock.py acquire --owner codex --branch codex/s2-graduation \
  --purpose "S2 graduation" --pid $$ --expected-minutes 180
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
  "$solo_py" scripts/agent_lock.py release --owner codex
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$solo_py" -m scripts.sim_cli workflow run zone-solo-cyan-v106 \
  --record "${solo_out}-managed" --timeout 10800 -- \
  --execute --expected-source-sha "$solo_sha" --output "$solo_out" \
  --stage-probe "$solo_stage" --seed "$solo_seed" --robot-id r3 --pickup-slot "$solo_slot" \
  --destination B --passage-id door_1 --speedups v98-exact-v6 --lock-owner codex &
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
