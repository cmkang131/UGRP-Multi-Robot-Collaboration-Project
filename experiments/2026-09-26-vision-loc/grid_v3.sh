#!/bin/bash
# Offline PF grid (no simulation), one process per (config, episode), at most VL_JOBS in parallel; then one score
# per config over all episodes. Refuses to reuse an existing config output directory.
# Usage: grid_v3.sh <out root> <calibration> <obs dir> <oracle obs dir> <filters> "<episodes>" <cfg1.json> [...]
# VL_CKPT: segmentation checkpoint of the vision observation caches (required with the vision filter).
set -euo pipefail
out=$1; cal=$2; obs=$3; orc=$4; filters=$5; eps=$6; shift 6
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${VL_PY:-/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python}
MAXJ=${VL_JOBS:-4}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p "$out"
extra=(--obs "$obs" --oracle-obs "$orc")
[ -n "${VL_CKPT:-}" ] && extra+=(--checkpoint "$VL_CKPT")
for cfg in "$@"; do
  name=$(basename "$cfg" .json)
  if [ -e "$out/$name" ]; then echo "refusing to reuse $out/$name" >&2; exit 2; fi
done
for cfg in "$@"; do
  name=$(basename "$cfg" .json); d="$out/$name"; mkdir -p "$d"
  for ep in $eps; do
    while [ "$(jobs -rp | wc -l)" -ge "$MAXJ" ]; do sleep 5; done
    echo "$(date -u +%FT%TZ) start $name $ep $(uptime)" >> "$out/grid_load.txt"
    ( "$PY" "$HERE/vision_loc_cli.py" localize --episodes "$ep" --calibration "$cal" --config "$cfg" \
        --filters "$filters" "${extra[@]}" --output "$d" > "$d/$ep.log" 2>&1 \
      && echo "$(date -u +%FT%TZ) end $name $ep $(uptime)" >> "$out/grid_load.txt" \
      || echo "$(date -u +%FT%TZ) FAILED $name $ep $(uptime)" >> "$out/grid_load.txt" ) &
  done
done
wait
for cfg in "$@"; do
  name=$(basename "$cfg" .json); d="$out/$name"
  "$PY" "$HERE/vision_loc_cli.py" score --episodes $eps --estimates "$d" "${extra[@]}" --config "$cfg" \
    --output "$d/metrics.json" > "$d/score.txt" 2>&1 || echo "score FAILED $name" >> "$out/grid_load.txt"
done
echo "$(date -u +%FT%TZ) grid done $(uptime)" >> "$out/grid_load.txt"
