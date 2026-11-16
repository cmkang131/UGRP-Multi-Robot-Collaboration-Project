#!/usr/bin/env bash
# Coordinator only (owner claude). Post COMMITMENT.md on #219 BEFORE running this.
# Rendered v95 held-out collection: 2 maps x 370 SIM s, both robots driven.
# Required: V95_SOURCE_SHA (exact reviewed 40-char head), V95_PRECHECK_DIR
# (verified heldout-v95-precheck-* directory), V95_COMMITMENT_COMMENT (#219
# comment id). Optional: V95_SIM_SLOT (borrow an existing claude slot for this
# branch), V95_COORDINATOR_PID (when another claude SIM slot already holds the
# physics coordinator, e.g. a running v92 collection; default: this shell).
set -eu
cd /Users/changmin/projects/ugrp-wt/critb-heldout-v94
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA="${V95_SOURCE_SHA:?Set the exact 40-character reviewed collection SHA}"
PRECHECK="${V95_PRECHECK_DIR:?Set the verified heldout-v95-precheck directory}"
COMMENT="${V95_COMMITMENT_COMMENT:?Post COMMITMENT.md on issue 219 and set its numeric comment ID}"
FINAL_BRANCH=codex/critb-heldout-new-starts
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-pair-v95-heldout-${FINAL_SHA:0:8}-$(date -u +%Y%m%dT%H%M%SZ)
SLOT="${V95_SIM_SLOT:-sim-claude-v95-heldout}"
COORDINATOR_PID="${V95_COORDINATOR_PID:-$$}"
CHILD_PID=""
ACQUIRED=0
[[ "$FINAL_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$COMMENT" =~ ^[0-9]+$ ]]
test "$(git rev-parse HEAD)" = "$FINAL_SHA"
test "$(git branch --show-current)" = "$FINAL_BRANCH"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$RUN_ROOT"
"$PY" scripts/disk_report.py
# Receipt + unedited public commitment are checked before any slot/physics.
"$PY" - "$PRECHECK" "$COMMENT" <<'PY'
import sys
from pathlib import Path
from scripts.precheck_heldout_v95 import verify_receipt, verify_public_commitment
p = Path(sys.argv[1])
verify_public_commitment(int(sys.argv[2]), p, verify_receipt(p))
print('precheck receipt and #219 commitment verified')
PY
"$PY" scripts/agent_lock.py status
"$PY" -m scripts.agent_sim_slots status
cleanup() {
  trap '' INT TERM
  # Keep the slot alive until the child has finished.
  if [ -n "$CHILD_PID" ]; then wait "$CHILD_PID" || :; fi
  if [ "$ACQUIRED" -eq 1 ]; then
    "$PY" -m scripts.agent_sim_slots release --owner claude --sim-slot "$SLOT"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -z "${V95_SIM_SLOT:-}" ]; then
  "$PY" -m scripts.agent_sim_slots acquire --owner claude --branch "$FINAL_BRANCH" \
    --purpose 'v95 held-out new starts: 2 maps x 370 SIM s rendered; not a timing benchmark' \
    --pid "$COORDINATOR_PID" --expected-minutes 120 --sim-slot "$SLOT"
  ACQUIRED=1
fi
for MAP in zone_wide_door_geometry_v3 zone_wide_corridor_final_v3; do
  "$PY" scripts/ugrp_session.py run "v95-heldout-$MAP" -- \
    "$PY" -m scripts.sim_cli workflow run zone-final-pair-heldout-v95 -- \
    --check calibration-unloaded --map-id "$MAP" --seed 911 \
    --expected-source-sha "$FINAL_SHA" --lock-owner claude --sim-slot "$SLOT" \
    --precheck "$PRECHECK" --commitment-comment "$COMMENT" \
    --output "$RUN_ROOT/$MAP" --execute &
  CHILD_PID=$!
  RC=0
  wait "$CHILD_PID" || RC=$?
  CHILD_PID=""
  if [ "$RC" -ne 0 ]; then exit "$RC"; fi
done
echo "collected (unqualified) under $RUN_ROOT; rerun the v95 kinematic gate before any B scoring"
