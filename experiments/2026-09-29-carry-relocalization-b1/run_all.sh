#!/bin/bash
# Full cohort of the carry-relocalization B1 measurement (offline: no physics step, no model calls, no agent_lock).
# Run from the repository root of the worktree. Output root is the primary checkout's outputs/ (raw stays local).
set -euo pipefail
SIM=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
TORCH=/Users/changmin/Project-Runtimes/ugrp/.venv-reference-act/bin/python
B1=experiments/2026-09-29-carry-relocalization-b1
OUT=${OUT:-/Users/changmin/projects/ugrp/outputs/carry-relocalization-b1-20260929/cohort}
export OMP_NUM_THREADS=1
mkdir -p "$OUT"
uptime > "$OUT/load_start.txt"
for prof in default floor_light_v1; do
  R="$OUT/render_$prof"
  [ -f "$R/render_manifest.json" ] || $SIM $B1/render_checkpoints.py "$R" --profile "$prof"
  [ -f "$R/obs_vision.json" ] || $TORCH $B1/segment_frames.py "$R"
  $TORCH $B1/relocalize_grid.py "$R" "$OUT/runs_${prof}_vision_wide.jsonl" --obs vision --prior wide --n S=40,Y=8,L=20 --consistency
done
R="$OUT/render_default"
$TORCH $B1/relocalize_grid.py "$R" "$OUT/runs_default_vision_tight.jsonl" --obs vision --prior tight --cells S Y --n S=40,Y=8
$TORCH $B1/relocalize_grid.py "$R" "$OUT/runs_default_oracle_wide.jsonl" --obs oracle --prior wide --n S=40,Y=8,L=20
uptime > "$OUT/load_end.txt"
python3 $B1/analyze.py "$OUT/analysis" "$OUT"/runs_*.jsonl --renders "$OUT/render_default" "$OUT/render_floor_light_v1"
