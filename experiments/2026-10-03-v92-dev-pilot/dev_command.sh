cd /Users/changmin/projects/ugrp-wt/v92-assembly  # claude/v92-dev-pilot 6a91737c, clean
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-03-v92-dev-pilot/fit_dev_pilot.py \
  --loaded-root /Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003 \
  --measured-calibration /Users/changmin/projects/ugrp/outputs/final-pair-v92-measured-20261003T091812Z/assembly/calibration.json \
  --output /Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/result
