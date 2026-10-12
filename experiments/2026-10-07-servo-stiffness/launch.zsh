#!/bin/zsh
set -eu
setopt NO_BG_NICE
cd /Users/changmin/projects/ugrp-wt/ego-wall-map
case_name="$1"
source_sha="$2"
stiffness="$3"
python_path=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$python_path" -c 'import os; assert os.getpriority(os.PRIO_PROCESS,0)==0, "require nice0 launcher"'
exec "$python_path" scripts/ugrp_session.py run "egomap19-${case_name}" -- \
  "$python_path" -m scripts.sim_cli workflow run wall-servo-stiffness -- \
  --case "$case_name" --servo-stiffness "$stiffness" --expected-source-sha "$source_sha" \
  --output "/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1/${case_name}" --execute
