#!/usr/bin/env bash
# One finite terminal-analysis dependency chain; never starts a simulation.
set -eu
test "$(hostname -s)" = ugrp-sim-gcp2
analysis_source=/home/ugrp/ugrp-sim/src/cb8b37c2994f5c77bcfaea469341bf987c7d3779
analysis_python=/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python
analysis_tools=/home/ugrp/ugrp-sim/analysis-tools
analysis_deadline=$((SECONDS+3600))
while ! test -f /home/ugrp/ugrp-sim/runs/reloc20-round3/DONE; do
    test "$SECONDS" -lt "$analysis_deadline"
    sleep 15
done
cd "$analysis_source"
"$analysis_python" "$analysis_tools/reloc20-full-plan-audit.py" --round 3
PYTHONPATH="$analysis_source" "$analysis_python" "$analysis_tools/reloc20-analyze-v3.py" --controller-source "$analysis_source" --round 3 --media
"$analysis_python" "$analysis_tools/reloc20-delivery.py"
