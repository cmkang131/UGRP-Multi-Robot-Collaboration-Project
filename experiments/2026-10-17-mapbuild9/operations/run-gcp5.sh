#!/bin/bash
set -euo pipefail
src=/home/ugrp/ugrp-sim/src/mapbuild9-offline-v1
ops=/home/ugrp/ugrp-sim/ops-reviews/mapbuild9
py=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
lease=/home/ugrp/ugrp-sim/leases/mapbuild9.json
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$src"
python3 - "$lease" "$$" <<'PY'
import json,sys,datetime
from pathlib import Path
p=Path(sys.argv[1]);p.open('x').write(json.dumps(dict(owner='mapbuild9',pid=int(sys.argv[2]),start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='three finite stored replays; no physics'))+'\n')
PY
trap 'rm -f "$lease"' EXIT
cd "$src"
"$py" -m pytest tests/test_mapbuild9.py -q > "$ops/tests.txt"
python3 - "$ops" <<'PY'
import json,sys
from pathlib import Path
ops=Path(sys.argv[1]);source='/home/ugrp/ugrp-sim/runs/mapbuild8/'
for i in range(1,4):
 q=dict(flow='self_map',replay_of=source+f'recording-r{i}',host='gcp5',project='ugrp-sim-e-1016',
 account='changmin5781@gmail.com',source_sha='c7bab1ff7bf36a7d16f5ef8a157b03663cc0e2e8',
 rejection_table=str(ops/'prior-rejection_table.json'),physical_steps=0,model_calls=0,
 selfmap_map_correction_v1='on',localization=dict(method='static_amcl_v1',map_correction='on'),
 stack_values=dict(dialogue_language='peer_en',contact_profile='warp_native_contact_v1',noslip_iterations=0,selfmap_map_correction='on'),
 scope='offline historical recording; does not certify current physical/runtime stack')
 (ops/f'r{i}-queue-v1b.json').write_text(json.dumps(q,indent=2)+'\n')
PY
for i in 1 2 3; do
  if [ ! -f "$ops/r${i}-stack-v1b.json" ]; then python3 scripts/check_current_stack.py "$ops/r${i}-queue-v1b.json" --flow self_map --output "$ops/r${i}-stack-v1b.json"; fi
  scan="/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}/scans.json"
  if [ "$i" = 1 ]; then scan=/home/ugrp/ugrp-sim/runs/mapbuild8/replay-r1-v2/scans.json; fi
  "$py" scripts/mapbuild9_replay.py --input "/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}" \
   --saved "/home/ugrp/ugrp-sim/runs/mapbuild8/executed-r${i}" --scan-source "$scan" \
   --output "/home/ugrp/ugrp-sim/runs/mapbuild9/r${i}-seed20261017-v1b" \
   --calibration "$ops/own-noise-command-r1-r2.json" --requirements "$src/experiments/2026-10-17-mapbuild8/requirements.json" \
   --command-model "$src/experiments/2026-10-17-mapbuild8/calibration/own-command-calibration-r2.json" \
   --queue "$ops/r${i}-queue-v1b.json" --stack-check "$ops/r${i}-stack-v1b.json"
done
# All three predictions are sealed before the first evaluation starts.
for i in 1 2 3; do
 "$py" scripts/mapbuild9_evaluate.py --input "/home/ugrp/ugrp-sim/runs/mapbuild8/recording-r${i}" \
  --prediction "/home/ugrp/ugrp-sim/runs/mapbuild9/r${i}-seed20261017-v1b" \
  --output "/home/ugrp/ugrp-sim/runs/mapbuild9/eval-r${i}-seed20261017-v1b" \
  --requirements "$src/experiments/2026-10-17-mapbuild8/requirements.json"
done
