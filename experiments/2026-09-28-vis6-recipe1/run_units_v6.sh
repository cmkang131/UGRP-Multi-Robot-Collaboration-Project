#!/bin/bash
# VIS6 offline replay units: one process per (candidate, PF seed index, episode), at most VL_JOBS in parallel.
# No simulation, render or network inference. Refuses to start on battery power or with < 10 GiB free.
# Usage: run_units_v6.sh <out root> "<candidates>" "<seed indices>" "<episodes>"
# Output: <out root>/runs/<candidate>/seed<k>/<episode>.{estimates.jsonl,meta.json}, logs/, load.txt
set -euo pipefail
out=$1; cands=$2; seeds=$3; eps=$4
HERE=$(cd "$(dirname "$0")" && pwd)
VIS=$HERE/../2026-09-26-vision-loc
PY=${VL_PY:-/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python}
MAXJ=${VL_JOBS:-4}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1
if command -v pmset >/dev/null && pmset -g batt | grep -q "Battery Power"; then
  echo "on battery power: VIS6 replay refused (plan stop rule)" >&2; exit 3
fi
mkdir -p "$out/logs" "$out/runs"
free_gib=$(df -g "$out" | awk 'NR==2 {print $4}')
if [ "${free_gib:-0}" -lt 10 ]; then echo "HOST_ERROR: less than 10 GiB free on $out" >&2; exit 4; fi
fails=0
for c in $cands; do
  [ -f "$HERE/configs/$c.json" ] || { echo "unknown candidate $c" >&2; exit 2; }
done
for c in $cands; do for k in $seeds; do for ep in $eps; do
  while [ "$(jobs -rp | wc -l)" -ge "$MAXJ" ]; do sleep 5; done
  echo "$(date -u +%FT%TZ) start $c seed$k $ep $(uptime)" >> "$out/load.txt"
  ( "$PY" "$VIS/replay_v6.py" run --config "$HERE/configs/$c.json" --seeds "$k" --episodes "$ep" \
      --output "$out/runs" > "$out/logs/$c.seed$k.$ep.log" 2>&1 \
    && echo "$(date -u +%FT%TZ) end $c seed$k $ep $(uptime)" >> "$out/load.txt" \
    || echo "$(date -u +%FT%TZ) FAILED $c seed$k $ep $(uptime)" >> "$out/load.txt" ) &
done; done; done
wait
if grep -q "FAILED" "$out/load.txt"; then echo "some units FAILED (see $out/load.txt): HOST_ERROR or bug, rerun into a new root" >&2; exit 1; fi
echo "$(date -u +%FT%TZ) units done $(uptime)" >> "$out/load.txt"
