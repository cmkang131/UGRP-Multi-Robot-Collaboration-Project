#!/bin/sh
# Reproduce every number of the README from the existing raw (read only; no physics is run).
# usage: analysis/run_all.sh [table.json]     (the 20 MB table is written outside the repository)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
EXP=$(dirname "$HERE")
TABLE=${1:-${TMPDIR:-/tmp}/l1_axial_leg_table.json}
PLACEMENTS="$EXP/inputs/placements_confirmatory_DRAFT.json"
python3 "$HERE/extract_legs.py" --out "$TABLE" --manifest "$EXP/results/raw_manifest.json" --csv "$EXP/results/case_table.csv"
python3 "$HERE/axial_decomposition.py" --table "$TABLE" > "$EXP/results/axial_decomposition.txt"
python3 "$HERE/y_bias_phases.py" --table "$TABLE" > "$EXP/results/y_bias_phases.txt"
python3 "$HERE/predict_pass.py" --table "$TABLE" --placements "$PLACEMENTS" --draws 3000 --json "$EXP/results/predict_pass.json" > "$EXP/results/predict_pass.txt"
