#!/bin/zsh
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/drive-friction
solo_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
solo_sha=${1:?full source SHA}
solo_out=${2:?new absolute output}
solo_stage=${3:?pick or place}
solo_seed=${4:?registered seed}
solo_slot=${5:?registered slot}
[[ $(git rev-parse HEAD) == "$solo_sha" ]]
[[ $(git branch --show-current) == codex/s2-realism ]]
[[ -z $(git status --porcelain) ]]
[[ ! -e "$solo_out" && ! -e "${solo_out}-managed" ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
[[ $("$solo_py" scripts/agent_lock.py status) == null ]]
"$solo_py" scripts/agent_lock.py acquire --owner codex --branch codex/s2-realism \
  --purpose 'S2 realism sequential DEV' --pid $$ --expected-minutes 180
solo_sim_pid=''
cleanup() {
  if [[ -n "$solo_sim_pid" ]] && kill -0 "$solo_sim_pid" 2>/dev/null; then
    kill -TERM "$solo_sim_pid" 2>/dev/null || true
    wait "$solo_sim_pid" 2>/dev/null || true
  fi
  "$solo_py" scripts/agent_lock.py release --owner codex
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$solo_py" -m scripts.sim_cli workflow run zone-s2-realism-v121 \
  --record "${solo_out}-managed" --timeout 10800 -- \
  --execute --expected-source-sha "$solo_sha" --output "$solo_out" \
  --stage-probe "$solo_stage" --seed "$solo_seed" --robot-id r3 --pickup-slot "$solo_slot" \
  --destination B --passage-id door_1 --speedups v98-exact-v6 --lock-owner codex \
  --camera-profile masterpi-camera-user-observation-target-review-v3 \
  --drive-profile masterpi_drive_friction_v7 --setdown-relook off --grasp-check pickup_site_v1 \
  --min-wheel-cmd real_v1 --dead-reckoning v7_diag_v1 --stagnation-watch window120_v1 --alignment-pulse real_fine_v1 --hover-check real_pregrasp_v1 --idle-robot-contacts freeze_v1 --site-check off --hold-check inhand_rgb_v1 --dev-grasp-policy log_only_v1 --eval-camera-trace pose_v1 &
solo_sim_pid=$!
solo_rc=0
wait "$solo_sim_pid" || solo_rc=$?
solo_sim_pid=''
exit "$solo_rc"
