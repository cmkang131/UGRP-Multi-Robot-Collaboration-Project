#!/bin/bash
# Driver for one chain cohort of the b-v6h gain-fix study (SIM time, no models). Usage:
#   run_cohort.sh <tag> <door-relax variant> <progress-relax|none> <gain-fix|none> [extra runner args...]
# Holds agent_lock with THIS shell's PID for the lifetime of the run and releases it at the end.
set -u
TAG="$1"; DOOR="$2"; PROG="$3"; GAIN="$4"; shift 4
WT="$(cd "$(dirname "$0")/../.." && pwd)"
PRIMARY=/Users/changmin/projects/ugrp
PY="$PRIMARY/.venv-sim-worker-mac/bin/python"
SHA="$(git -C "$WT" rev-parse --short=8 HEAD)"
OUT="$PRIMARY/outputs/b-v6h-gain-$SHA-$TAG"
LOG="$OUT.driver.log"
cd "$WT" || exit 1
echo "driver pid $$ sha $SHA start $(date -u +%FT%TZ) load: $(sysctl -n vm.loadavg)" >> "$LOG"
"$PY" scripts/agent_lock.py acquire --owner claude --branch claude/b-v6h-gain --purpose "b-v6h gain fix chain $TAG (SIM time, no models)" \
  --pid $$ --expected-minutes "${EXPECTED_MIN:-60}" >> "$LOG" 2>&1 || { echo "lock refused" >> "$LOG"; exit 3; }
EXTRA=()
[ "$PROG" != none ] && EXTRA+=(--progress-relax "$PROG")
[ "$GAIN" != none ] && EXTRA+=(--carry-gain-fix "$GAIN")
"$PY" -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6h --door-relax "$DOOR" "${EXTRA[@]}" \
  --prior-std e2e --chain-stop-leg 1 --render-profile floor_light_v1 --pf-track --workers "${WORKERS:-4}" --omp-threads 1 \
  --env-placements "$WT/experiments/2026-09-30-b-v6h-gain/placements/${PLACEMENTS:-held_out_12}.json" --seeds 911 913 \
  --execute --lock-owner claude --output "$OUT" "$@" > "$OUT.stdout.log" 2>&1
CODE=$?
echo "exit $CODE end $(date -u +%FT%TZ) load: $(sysctl -n vm.loadavg)" >> "$LOG"
"$PY" scripts/agent_lock.py release --owner claude >> "$LOG" 2>&1
exit $CODE
