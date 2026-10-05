#!/usr/bin/env bash
# Coordinator only (v101 unloaded gain calibration). Needs the exact reviewed 40-character source SHA and a stamp.
#   V101_SOURCE_SHA=<sha> V101_STAMP=<yyyymmddThhmmZ> [V101_MAXPAR=2] [V101_RUNS="fitA1 ..."] bash collect.sh
# SIM-time only, not a timing benchmark. Each run takes its own sim-* slot under THIS shell's PID (the coordinator),
# which must outlive every worker. Runs are launched at most V101_MAXPAR at a time.
set -eu
cd /Users/changmin/projects/ugrp-wt/calib-unloaded-gain
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA="${V101_SOURCE_SHA:?Set the exact 40-character SHA}"
STAMP="${V101_STAMP:?Set a UTC stamp such as 20261005T0330Z}"
MAXPAR="${V101_MAXPAR:-2}"
RUNS="${V101_RUNS:-fitA1 fitA2 heldA3 heldM1 heldP1 heldP2}"
BRANCH=claude/calib-unloaded-gain
OUT=/Users/changmin/projects/ugrp/outputs/calib-gain-v101-${FINAL_SHA:0:8}-${STAMP}
test "${#FINAL_SHA}" -eq 40
test "$(git rev-parse HEAD)" = "$FINAL_SHA"
test "$(git branch --show-current)" = "$BRANCH"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$OUT"
"$PY" scripts/disk_report.py | head -4
"$PY" scripts/agent_lock.py status
uptime
mkdir -p "$OUT"
echo "coordinator pid $$ source $FINAL_SHA out $OUT runs: $RUNS maxpar $MAXPAR" | tee "$OUT/coordinator.txt"
PIDS=""
SLOTS=""
live_count() {
  n=0
  for p in $PIDS; do if kill -0 "$p" 2>/dev/null; then n=$((n+1)); fi; done
  echo "$n"
}
cleanup() {
  trap '' INT TERM
  for p in $PIDS; do wait "$p" || :; done
  for s in $SLOTS; do "$PY" -m scripts.agent_sim_slots release --owner claude --sim-slot "$s" >/dev/null 2>&1 || :; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
FAILED=0
for run in $RUNS; do
  while [ "$(live_count)" -ge "$MAXPAR" ]; do sleep 5; done
  seed=$("$PY" -c "from harness import final_environment_gain_calibration_v101 as g; print(g.run_row(g.protocol(), '$run')['seed'])")
  slot="sim-claude-gaincal-$run"
  "$PY" -m scripts.agent_sim_slots acquire --owner claude --branch "$BRANCH" \
    --purpose "v101 unloaded gain calibration $run; SIM time, not a timing benchmark" \
    --pid $$ --expected-minutes 60 --sim-slot "$slot" >/dev/null
  SLOTS="$SLOTS $slot"
  echo "$(date -u +%FT%TZ) start $run seed $seed load $(uptime | sed 's/.*load averages*: //')" | tee -a "$OUT/coordinator.txt"
  (
    "$PY" scripts/ugrp_session.py run "gaincal-v101-$run" -- \
      "$PY" -m scripts.sim_cli workflow run zone-final-environment-gaincal-v101 -- \
      --check calibration-gain-v101 --run-id "$run" --seed "$seed" --expected-source-sha "$FINAL_SHA" \
      --lock-owner claude --sim-slot "$slot" --output "$OUT/$run" --execute
  ) > "$OUT/$run.log" 2>&1 &
  PIDS="$PIDS $!"
done
for p in $PIDS; do wait "$p" || FAILED=1; done
echo "$(date -u +%FT%TZ) all runs finished failed=$FAILED load $(uptime | sed 's/.*load averages*: //')" | tee -a "$OUT/coordinator.txt"
exit "$FAILED"
