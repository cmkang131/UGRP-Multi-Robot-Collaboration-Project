#!/usr/bin/env bash
# Coordinator only. V92_SOURCE_SHA must be the exact reviewed 40-character SHA.
set -eu
cd /Users/changmin/projects/ugrp-wt/v92-loaded
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA="${V92_SOURCE_SHA:?Set the exact 40-character SHA from this PR handoff}"
FINAL_BRANCH=codex/v92-loaded-schedule
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-${FINAL_SHA:0:8}-20261003
SLOT=sim-codex-v92-loaded
CHILD_PID=""
ACQUIRED=0
test "${#FINAL_SHA}" -eq 40
test "$(git rev-parse HEAD)" = "$FINAL_SHA"
test "$(git branch --show-current)" = "$FINAL_BRANCH"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$RUN_ROOT"
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status
cleanup() {
  trap '' INT TERM
  # Keep the coordinator/physics reservation alive until its child is finished.
  if [ -n "$CHILD_PID" ]; then wait "$CHILD_PID" || :; fi
  if [ "$ACQUIRED" -eq 1 ]; then
    "$PY" -m scripts.agent_sim_slots release --owner codex --sim-slot "$SLOT"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PY" -m scripts.agent_sim_slots acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v92 loaded training 720 SIM s; not a timing benchmark' \
  --pid $$ --expected-minutes 90 --sim-slot "$SLOT"
ACQUIRED=1
"$PY" scripts/ugrp_session.py run final-pair-v92-loaded -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-pair-loaded-v92 -- \
  --check calibration-loaded --map-id zone_wide_two_doors_final_v3 --seed 911 \
  --expected-source-sha "$FINAL_SHA" --lock-owner codex --sim-slot "$SLOT" \
  --output "$RUN_ROOT" --execute &
CHILD_PID=$!
RC=0
wait "$CHILD_PID" || RC=$?
CHILD_PID=""
exit "$RC"
