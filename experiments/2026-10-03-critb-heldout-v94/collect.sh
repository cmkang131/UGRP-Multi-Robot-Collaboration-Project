#!/usr/bin/env bash
# Coordinator only: post COMMITMENT.md on #219 BEFORE running this file.
set -eu
cd "$(dirname "$0")/../.."
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA="${V94_SOURCE_SHA:?Set the reviewed exact 40-character collection source SHA}"
PRECHECK="${V94_PRECHECK_DIR:?Set the verified heldout-v94-precheck directory}"
COMMENT="${V94_COMMITMENT_COMMENT:?Post COMMITMENT.md on issue 219 and set its numeric comment ID}"
FINAL_BRANCH=codex/critb-heldout-new-starts
RUN_ROOT="${V94_RUN_ROOT:-/Users/changmin/projects/ugrp/outputs/final-pair-v94-heldout-${FINAL_SHA:0:8}-$(date +%Y%m%dT%H%M%S)}"
SLOT="${V94_SIM_SLOT:-sim-codex-v94-heldout}"
CHILD_PID=""
ACQUIRED=0
[[ "$FINAL_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$COMMENT" =~ ^[0-9]+$ ]]
test "$(git rev-parse HEAD)" = "$FINAL_SHA"
test "$(git branch --show-current)" = "$FINAL_BRANCH"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$RUN_ROOT"
# This check precedes slot acquisition and all renderer/physics construction.
"$PY" - "$PRECHECK" "$COMMENT" <<'PY'
import sys
from scripts.precheck_heldout_v94 import verify_receipt, verify_public_commitment
from pathlib import Path
p = Path(sys.argv[1])
verify_public_commitment(int(sys.argv[2]), p, verify_receipt(p))
PY
"$PY" scripts/agent_lock.py status
cleanup() {
  trap '' INT TERM
  if [ -n "$CHILD_PID" ]; then wait "$CHILD_PID" || :; fi
  if [ "$ACQUIRED" -eq 1 ]; then
    "$PY" -m scripts.agent_sim_slots release --owner codex --sim-slot "$SLOT"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# A coordinator may supply an existing slot for THIS branch. Borrowed slots
# stay owned by that coordinator. Otherwise this script owns its own slot.
if [ -z "${V94_SIM_SLOT:-}" ]; then
  "$PY" -m scripts.agent_sim_slots acquire --owner codex --branch "$FINAL_BRANCH" \
    --purpose 'v94 held-out new starts: 2 maps x 370 SIM s; not wall-time benchmark' \
    --pid $$ --expected-minutes 90 --sim-slot "$SLOT"
  ACQUIRED=1
fi
for MAP in zone_wide_door_geometry_v3 zone_wide_corridor_final_v3; do
  "$PY" scripts/ugrp_session.py run "v94-heldout-$MAP" -- \
    "$PY" -m scripts.sim_cli workflow run zone-final-pair-heldout-v94 -- \
    --check calibration-unloaded --map-id "$MAP" --seed 911 \
    --expected-source-sha "$FINAL_SHA" --lock-owner codex --sim-slot "$SLOT" \
    --precheck "$PRECHECK" --commitment-comment "$COMMENT" \
    --output "$RUN_ROOT/$MAP" --execute &
  CHILD_PID=$!
  RC=0
  wait "$CHILD_PID" || RC=$?
  CHILD_PID=""
  if [ "$RC" -ne 0 ]; then exit "$RC"; fi
done
