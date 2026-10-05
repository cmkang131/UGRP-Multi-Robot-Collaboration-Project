#!/bin/bash
cd /Users/changmin/projects/ugrp-wt/phys-v89-motion
set -euo pipefail
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
SHA=$(git rev-parse HEAD)
BR=$(git branch --show-current)
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001
"$PY" scripts/agent_lock.py acquire --owner claude --branch "$BR" --purpose 'v89 unloaded steps and PRBS, <=235 SIM s including reset' --pid $$ --expected-minutes 45
trap '"$PY" scripts/agent_lock.py release --owner claude' EXIT
"$PY" scripts/ugrp_session.py run measurement-v89 -- "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-v2-check -- --check calibration-motion-v2 --seed 911 --expected-source-sha "$SHA" --execute --lock-owner claude --output "$RUN_ROOT"
"$PY" scripts/agent_lock.py release --owner claude
trap - EXIT
