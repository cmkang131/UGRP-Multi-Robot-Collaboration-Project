#!/bin/bash
# v6 dev cohort driver (Claude, 2026-09-28). Sequential: the late authorization
# envelope lives in the single tracked prereg of this worktree, one run_id at a time.
# usage: run_cohort.sh <approval comment URL> [run_id ...]
set -euo pipefail
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
WT=/Users/changmin/projects/ugrp-wt/claude-v6-dev
cd "$WT"
REF=$1; shift
RUNS=${*:-"v6-s911-v5h v6-s911-b v6-s911-ab v6-s912-v5h v6-s912-b v6-s912-ab"}
BRANCH=$(git branch --show-current)
SHA=$(git rev-parse HEAD)
PREREG=experiments/2026-09-28-zone-pair-v6/prereg_v6.json
ROOT=/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v6-$SHA
LOG=$ROOT/cohort.log
test "$BRANCH" = claude/zone-pair-v6-dev
test -z "$(git status --porcelain --untracked-files=all)"
mkdir -p "$ROOT"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
"$PY" scripts/agent_lock.py acquire --owner claude --branch "$BRANCH" \
  --purpose "v6 dev cohort $SHA (6 runs, no model calls)" --pid "$$" --expected-minutes 360
restore() { git checkout -- "$PREREG"; }
trap 'restore; "$PY" scripts/agent_lock.py release --owner claude' EXIT
for RUN in $RUNS; do
  case $RUN in *-v5h) POL=v5h;; *-b) POL=b-only;; *-ab) POL=a+b;; esac
  "$PY" experiments/2026-09-28-zone-pair-v6/dev-runs/envelope.py write "$SHA" "$RUN" "$REF" >> "$LOG"
  echo "$(date -u +%FT%TZ) start $RUN policy=$POL loadavg=$(sysctl -n vm.loadavg)" | tee -a "$LOG"
  set +e
  "$PY" scripts/ugrp_session.py run "pair-$RUN-${SHA:0:8}" -- \
    "$PY" -m scripts.sim_cli workflow run zone-pair-dev \
    --record "$ROOT/$RUN-managed" --timeout 57660 -- \
    --prereg "$PREREG" --run-id "$RUN" --pair-policy "$POL" --output "$ROOT/$RUN" \
    --execute --expected-source-sha "$SHA" --lock-owner claude
  RC=$?
  set -e
  echo "$(date -u +%FT%TZ) end $RUN rc=$RC loadavg=$(sysctl -n vm.loadavg)" | tee -a "$LOG"
  restore
  if [ $RC -ne 0 ]; then echo "stop: $RUN rc=$RC" | tee -a "$LOG"; exit $RC; fi
done
