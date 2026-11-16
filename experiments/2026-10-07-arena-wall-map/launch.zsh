#!/bin/zsh
set -eu
setopt NO_BG_NICE
cd <home>/projects/ugrp-wt/ego-wall-map
case_name="$1"
source_sha="$2"
python_path=<home>/projects/ugrp/.venv-sim-worker-mac/bin/python
"$python_path" -c 'import os; assert os.getpriority(os.PRIO_PROCESS,0)==0, "require nice0 launcher"'
exec "$python_path" scripts/ugrp_session.py run "egomap20-${case_name}" -- \
  "$python_path" -m scripts.sim_cli workflow run arena-wall-map -- \
  --case "$case_name" --expected-source-sha "$source_sha" \
  --output "<home>/projects/ugrp/outputs/arena-wall-map-v1/${case_name}" --execute
