#!/bin/bash
set -x
cd /Users/changmin/projects/ugrp-wt/door-ultrasonic-sweep
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
OUT=/Users/changmin/projects/ugrp/outputs/door-ultrasonic-sweep-20260929-final
export OMP_NUM_THREADS=1
git rev-parse HEAD; uptime
$PY scripts/door_ultrasonic_sweep.py stationary --out $OUT/stationary
$PY scripts/door_ultrasonic_sweep.py occlusion --out $OUT/occlusion --probe-root /Users/changmin/projects/ugrp/outputs
$PY scripts/door_ultrasonic_sweep.py side --out $OUT/side --seeds 8
$PY scripts/door_ultrasonic_sweep.py sweep --out $OUT/sweep --seeds 8
$PY scripts/door_ultrasonic_sweep.py sweep --out $OUT/sweep_far --seeds 8 --approach 1.0,1.2,1.5 --widths 0.15,0.2,0.3 --speeds 0.05
$PY scripts/door_ultrasonic_sweep.py ablate --out $OUT/ablate --d 0.5 --W 0.4 --v 0.05 --seeds 12
$PY scripts/door_ultrasonic_sweep.py report --src $OUT/sweep
$PY scripts/door_ultrasonic_sweep.py report --src $OUT/sweep_far
uptime
$PY scripts/door_ultrasonic_sweep.py manifest --out $OUT
echo ALLDONE
