#!/bin/bash
# usage: run_group.sh <tag> <placements.json> <expected-min>
# Waits for the shared physics lock, holds it (owner claude, pid = this shell), runs one frozen-source stage-probe group, releases.
set -u
TAG=$1; PLC=$2; MIN=$3; SEEDS=${4:-911}   # 4th arg (optional): PF/case seed, default 911 (runner default)
SRC=/Users/changmin/projects/ugrp-wt/phys-caps-1001-src
PRIMARY=/Users/changmin/projects/ugrp
PY=/Users/changmin/Project-Runtimes/ugrp/.venv-sim-worker-mac/bin/python
OUT=$PRIMARY/outputs/phys-caps-1001-l1-$TAG
LOCKCLI="python3 $PRIMARY/scripts/agent_lock.py"
until $LOCKCLI acquire --owner claude --branch claude/phys-caps-1001 --purpose "L1 lateral probes $TAG (b-v6h1 4c6b439f)" --pid $$ --expected-minutes $MIN >/dev/null 2>&1; do sleep 20; done
trap '$LOCKCLI release --owner claude >/dev/null 2>&1' EXIT
echo "LOCK_ACQUIRED $(date -u +%FT%TZ) load=$(uptime | sed 's/.*averages: //') free_gib=$(df -g $PRIMARY | awk 'NR==2{print $4}')"
cd $SRC
[ "$(git rev-parse HEAD)" = 4c6b439f3f7c9a147c901f8b260a1e214d4eb396 ] || { echo SOURCE_SHA_MISMATCH; exit 3; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo DIRTY; exit 3; }
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
$PY -m scripts.run_pair_stage_probes --stage chain --sources teacher --policies b-v6h1 --prior-std e2e --chain-stop-leg 1 \
  --render-profile floor_light_v1 --pf-track --contact-track --workers 2 --omp-threads 1 --seeds $SEEDS \
  --env-placements $PLC --output $OUT --execute --lock-owner claude
RC=$?
echo "RUNNER_EXIT $RC $(date -u +%FT%TZ) load=$(uptime | sed 's/.*averages: //')"
exit $RC
