#!/bin/bash
set -euo pipefail
root=/home/ugrp/ugrp-sim/runs/simalt3
n="$1"
mode="$2"
sha="$3"
export MUJOCO_GL=osmesa LP_NUM_THREADS=1
out="$root/warp-n$n-forward"
args=()
if [ "$mode" = rgb ]; then
 out="$out-rgb"
 args+=(--batch-render-v1)
fi
"$root/warp-env/bin/python" -u "$root/diag/simalt_physics_compare.py" run --source "$root/runtime/source" --fixture "$root/fixture" --out "$out" --engine warp --reference "$root/cpu-n1/result.json" --sha "$sha" --enabled --gcp2-v1 --unused-efm-v1 --only forward --nworld "$n" "${args[@]}" > "$out.log" 2>&1
"$root/c-env/bin/python" -c 'import json,sys;d=json.load(open(sys.argv[1]));print(json.dumps(d));sys.exit(0 if d["status"]=="complete" else 2)' "$out/result.json"
