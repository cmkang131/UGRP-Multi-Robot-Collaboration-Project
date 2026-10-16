#!/usr/bin/env bash
# Rebuilds the representative version videos from saved raw case directories (no simulation is run).
# Usage: OUT=/Users/changmin/projects/ugrp/outputs bash experiments/2026-09-29-version-videos/build_videos.sh [dest_dir]
set -euo pipefail
OUT="${OUT:-/Users/changmin/projects/ugrp/outputs}"
DEST="${1:-experiments/2026-09-29-version-videos/videos}"
PY="${PY:-python3}"          # any python with matplotlib; ffmpeg must be on PATH
R="$PY scripts/render_pair_probe_video.py"
E2E=cases/carry_b-v6e_teacher_lat-_opp_s911_pE2E_L1_Vcal
mkdir -p "$DEST"

# b-v6e-base (source d08818ef, fails) vs b-v6e yaw fix (source f2186414, passes): same case, carry leg 1
$R --case "$OUT/pair-stage-probes-d08818ef-cal2/$E2E" --label "b-v6e-base (실패)" \
   --case "$OUT/pair-stage-probes-f2186414-yawcal/$E2E" --label "b-v6e yaw 수정 (통과)" \
   --output "$DEST/carry_L1_latm-opp_s911_v6e-base_vs_v6e-yaw_topdown.mp4"
$R --case "$OUT/pair-stage-probes-d08818ef-cal2/$E2E" --label "b-v6e-base (실패)" \
   --case "$OUT/pair-stage-probes-f2186414-yawcal/$E2E" --label "b-v6e yaw 수정 (통과)" --wrist \
   --output "$DEST/carry_L1_latm-opp_s911_v6e-base_vs_v6e-yaw_topdown_wrist.mp4"

# b-v6c carry leg 1, nominal seed 911 (baseline failure)
$R --case "$OUT/pair-stage-probes-b604499d-carryL1367/cases/carry_b-v6c_teacher_nominal_s911_pE2E_L1" --label "b-v6c (실패)" \
   --output "$DEST/carry_L1_nominal_s911_v6c_topdown.mp4"

# align stage yaw+/opp seed 911: b-v6c (fails) vs b-v6d (passes); no carry gate line (align does not end on the sigma gate)
$R --case "$OUT/pair-stage-probes-b5234b7a-v6c-align/cases/align_b-v6c_teacher_yaw+_opp_s911_pE2E" --label "b-v6c (실패)" \
   --case "$OUT/pair-stage-probes-052e3eba-v6d-venv-align-0/cases/align_b-v6d_teacher_yaw+_opp_s911_pE2E" --label "b-v6d (통과)" \
   --gate none --dt 0.5 --output "$DEST/align_yawp-opp_s911_v6c_vs_v6d_topdown.mp4"
