#!/bin/bash
set -euo pipefail
src=/home/ugrp/ugrp-sim/src/mapbuild9-sparse-8eead1464
ops=/home/ugrp/ugrp-sim/ops-reviews/mapbuild9
py=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
lease=/home/ugrp/ugrp-sim/leases/mapbuild9.json
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="$src"
python3 - "$lease" "$$" "$ops" <<'PY'
import json,sys,datetime
from pathlib import Path
p=Path(sys.argv[1]);p.open('x').write(json.dumps(dict(owner='mapbuild9',pid=int(sys.argv[2]),start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='418 saved views finite offline replay; no physics'))+'\n')
ops=Path(sys.argv[3])
q=dict(flow='self_map',host='gcp3',project='ugrp-sim-c-1016',account='changmin5781@gmail.com',replay_of='/home/ugrp/ugrp-sim/runs/warp8/selfmap-csm-r1',
 rejection_table='/home/ugrp/ugrp-sim/runs/warp8/selfmap-csm-r1/rejection_table.json',source_sha='8eead1464',
 physics_steps=0,render_calls=0,method='static_amcl_v1',selfmap_map_correction_v1='on',scope='sparse open-camera historical replay; no current physical-stack compliance')
(ops/'queue.json').write_text(json.dumps(q,indent=2)+'\n')
PY
trap 'rm -f "$lease"' EXIT
cd "$src"
python3 scripts/check_current_stack.py "$ops/queue.json" --flow self_map --output "$ops/stack.json" > "$ops/stack.txt"
for stage in predict score; do
 "$py" scripts/mapbuild9_sparse.py --stage "$stage" \
 --owner /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25 \
 --input /home/ugrp/ugrp-sim/runs/warp8/selfmap-open-r1 \
 --output /home/ugrp/ugrp-sim/runs/warp8/mapbuild9-amcl-v1 \
 --calibration "$ops/own-noise-command-r1-r2.json" \
 --requirements "$src/experiments/2026-10-17-mapbuild8/requirements.json" \
 --queue "$ops/queue.json" --stack-check "$ops/stack.json" --workers 4
done
