#!/bin/zsh
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/s3-host
s3_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
s3_sha=${1:?full committed SHA required}
s3_out=/Users/changmin/projects/ugrp/outputs/s3-host-heading-${s3_sha[1,8]}-s14201-v146
[[ $(git branch --show-current) == codex/s3-no-prior-smoke ]]
[[ $(git rev-parse HEAD) == "$s3_sha" ]]
[[ $(git rev-parse origin/codex/s3-no-prior-smoke) == "$s3_sha" ]]
[[ -z $(git status --porcelain) ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
exec "$s3_py" -m scripts.sim_cli workflow run zone-s3-host-heading-v146 \
 --record /Users/changmin/projects/ugrp/outputs/s3run-20261009/managed-v146 \
 --timeout 10800 -- --expected-source-sha "$s3_sha" --seed 14201 \
 --output "$s3_out" --execute --release-s3-simulation
