#!/bin/bash
set -euo pipefail
src=/home/ugrp/ugrp-sim/src/mapbuild9-product-3d3050c87
ops=/home/ugrp/ugrp-sim/ops-reviews/mapbuild9
py=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
lease=/home/ugrp/ugrp-sim/leases/mapbuild9.json
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$src"
python3 - "$lease" "$$" "$ops" <<'PY'
import json,sys,datetime
from pathlib import Path
Path(sys.argv[1]).open('x').write(json.dumps(dict(owner='mapbuild9',pid=int(sys.argv[2]),start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='official probability sensor x three stored replays; no physics'))+'\n')
ops=Path(sys.argv[3])
for profile in ['likelihood_product_v1']:
 for i in range(1,4):
  q=dict(flow='self_map',replay_of=f'/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r{i}',host='gcp5',project='ugrp-sim-e-1016',account='changmin5781@gmail.com',
   source_sha='3d3050c87861ce3ba515ce2c1bd50ba3f03da19e',profile=profile,rejection_table=str(ops/'prior-rejection_table.json'),physics_steps=0,model_calls=0,
   selfmap_map_correction_v1='on',localization=dict(method='static_amcl_v1',map_correction='on'),scope='historical offline replay; no current runtime certification')
  (ops/f'r{i}-{profile}-queue.json').write_text(json.dumps(q,indent=2)+'\n')
PY
trap 'rm -f "$lease"' EXIT
cd "$src"
"$py" -m pytest tests/test_mapbuild9.py -q > "$ops/product-tests.txt"
for profile in likelihood_product_v1; do
 for i in 1 2 3; do
  python3 scripts/check_current_stack.py "$ops/r${i}-${profile}-queue.json" --flow self_map --output "$ops/r${i}-${profile}-stack.json" > "$ops/r${i}-${profile}-stack.txt"
  scan="/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}/scans.json"
  if [ "$i" = 1 ]; then scan=/home/ugrp/ugrp-sim/runs/mapbuild8/replay-r1-v2/scans.json; fi
  "$py" scripts/mapbuild9_replay.py --input "/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}" \
   --saved "/home/ugrp/ugrp-sim/runs/mapbuild8/executed-r${i}" --scan-source "$scan" \
   --output "/home/ugrp/ugrp-sim/runs/mapbuild9/r${i}-${profile}" --profile "$profile" \
   --calibration "$ops/own-noise-command-r1-r2.json" --requirements "$src/experiments/2026-10-17-mapbuild8/requirements.json" \
   --command-model "$src/experiments/2026-10-17-mapbuild8/calibration/own-command-calibration-r2.json" \
   --queue "$ops/r${i}-${profile}-queue.json" --stack-check "$ops/r${i}-${profile}-stack.json"
 done
done
# Both profiles/all three streams sealed before scoring the first result.
for profile in likelihood_product_v1; do
 for i in 1 2 3; do
 "$py" scripts/mapbuild9_evaluate.py --input "/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}" \
  --prediction "/home/ugrp/ugrp-sim/runs/mapbuild9/r${i}-${profile}" --output "/home/ugrp/ugrp-sim/runs/mapbuild9/eval-r${i}-${profile}" \
  --requirements "$src/experiments/2026-10-17-mapbuild8/requirements.json"
 done
done
