#!/usr/bin/env bash
# pairact P0: world 27 same-seed x3 repeat on the frozen r13 stack (diagnostic, no gate claim).
# Exactly the command of runs/diag-r13-27-repeat{1,2,3}/summary.json (reproduce), new out dirs.
# Prior: 10/18 repeat1 FAIL 25.5 / repeat2 FAIL 25.5 / repeat3 PASS 24.0 (1/3); gate attempts 1,2 FAIL.
# Usage: bash repeat27.sh plan | run      (sequential; isolated host allows one GPU client)
set -uo pipefail
MODE="${1:-plan}"
PY="${PY:-/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python}"
SRC="${SRC:-/home/ugrp/ugrp-sim/src}"
RUNNER="${RUNNER:-$SRC/beamact5-tools/run_warp_flow_teacher_gcp6.py}"
WARP_SOURCE_ROOT="${WARP_SOURCE_ROOT:-$SRC/05046e9d245e46b4ee3d1c43308f7258a9fa41c5}"  # [확인 필요]
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_ROOT="${OUT_ROOT:-/home/ugrp/ugrp-sim/runs/pairact-p0/repeat27-$TS}"
mkdir -p "$OUT_ROOT"
for i in 1 2 3; do
  out="$OUT_ROOT/rep$i"
  cmd=("$PY" "$RUNNER" --flow beampair
    --adapter-source "$SRC/835ccef26aa84b08cc8f7e256fd0f43aa1583ef9"
    --teacher-source "$SRC/26f84d0f0ada1c33473c83cca2d3415ce51bd247"
    --cases /home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json
    --indices 27 --cap-s 60 --out "$out" --vm-hourly-usd 1.096
    --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1
    --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1
    --canonical-xml /home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml
    --per-world-model-references-v1 /home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json
    --rejection-table /home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json
    --batch-per-world-speed-v1)
  echo "[rep$i] cd $WARP_SOURCE_ROOT && WARP_SOURCE_ROOT=$WARP_SOURCE_ROOT ${cmd[*]}"
  [ "$MODE" = run ] || continue
  ( cd "$WARP_SOURCE_ROOT" && env WARP_SOURCE_ROOT="$WARP_SOURCE_ROOT" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa timeout 5400 "${cmd[@]}" ) > "$OUT_ROOT/rep$i.log" 2>&1
  echo "rep$i rc=$?" | tee -a "$OUT_ROOT/result.tsv"
  sleep 5
done
[ "$MODE" = run ] && "$PY" - "$OUT_ROOT" <<'EOF'
import json, sys, pathlib
root = pathlib.Path(sys.argv[1]); rows = []
for s in sorted(root.glob('rep*/summary.json')):
    d = json.loads(s.read_text())
    rows.append({'rep': s.parent.name, 'keys': sorted(d)[:40]})
print(json.dumps(rows, indent=1))
print('Read success / end_reason / sim_s / alignment_relooks per rep from summary.json and world-000 raw (same fields as runs/diag-r13-27-repeat*/summary.json).')
EOF
exit 0
