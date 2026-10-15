#!/bin/bash
# One pytest process, then stored-input geometry/issued-odometry replay only.
set -euo pipefail
cd "$(dirname "$0")/../.."
crate_python="${UGRP_CRATE_PYTHON:-/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python}"
crate_output="${1:?usage: bash experiments/2026-10-15-crate17/check.sh NEW_OUTPUT_DIR}"
if [ -e "$crate_output" ]; then
  echo "Use a new output directory: $crate_output" >&2
  exit 2
fi
mkdir -p "$crate_output"
"$crate_python" -m pytest -q tests/test_crate17.py tests/test_crate16.py tests/test_crate15.py --junitxml="$crate_output/pytest.xml"
"$crate_python" experiments/2026-10-15-crate17/verify.py --output "$crate_output"
