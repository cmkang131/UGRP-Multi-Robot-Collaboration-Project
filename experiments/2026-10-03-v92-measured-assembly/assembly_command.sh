cd /Users/changmin/projects/ugrp-wt/v92-assembly  # detached HEAD 257953ec36353c37acc61c4cb86563db7c937de2, clean
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.assemble_final_pair_calibration_v92 \
  --unloaded-root /Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded \
  --fine-root /Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001-r6/calibration-fine \
  --loaded-root /Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003 \
  --yaw-candidate /Users/changmin/projects/ugrp/experiments/2026-10-03-critb-rotation/calibration_candidate_r5_yaw.json \
  --criterion-b-result /Users/changmin/projects/ugrp/outputs/criterion-b-v91-score-20261003/criterion_B_v91_with_yaw.json \
  --criterion-b-result /Users/changmin/projects/ugrp/outputs/criterion-b-v91-score-r2-20261003/criterion_B_v91_with_yaw.json \
  --output /Users/changmin/projects/ugrp/outputs/final-pair-v92-measured-20261003T091812Z/assembly
