#!/bin/bash
# Round-3 test, run ONCE after prereg_v3.json is committed and pushed: observations (vision + oracle), the four
# filters per registered test episode (at most VL_JOBS in parallel), then the single registered scoring.
# Usage: run_test_v3.sh <out root>        (raw outputs under the primary checkout's outputs/)
set -euo pipefail
out=$1
HERE=$(cd "$(dirname "$0")" && pwd)
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
TPY=/Users/changmin/Project-Runtimes/ugrp/.venv-reference-act/bin/python
MAXJ=${VL_JOBS:-4}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1
pre=$HERE/prereg_v3.json
[ -f "$pre" ] || { echo "no prereg_v3.json" >&2; exit 2; }
if [ -n "$(git -C "$HERE" status --porcelain -- prereg_v3.json)" ]; then echo "commit prereg_v3.json first" >&2; exit 2; fi
if [ -e "$out" ]; then echo "refusing to reuse $out" >&2; exit 2; fi
cfg=$HERE/$("$PY" -c "import json;print(json.load(open('$pre'))['student']['config']['file'])")
ckpt=$("$PY" -c "import json;print(json.load(open('$pre'))['student']['model']['checkpoint'])")
eps=$("$PY" -c "import json;print(' '.join(json.load(open('$pre'))['test_episodes']))")
mkdir -p "$out"
log() { echo "$(date -u +%FT%TZ) $* $(uptime)" >> "$out/test_load.txt"; }
log "start test eps=[$eps] own=$(git -C "$HERE" rev-parse HEAD)"
"$TPY" "$HERE/vision_loc_cli.py" segment --episodes $eps --checkpoint "$ckpt" --config "$cfg" --output "$out/obs" \
  > "$out/segment.log" 2>&1
"$PY" "$HERE/vision_loc_cli.py" oracle --episodes $eps --config "$cfg" --output "$out/oracle-obs" > "$out/oracle.log" 2>&1
log "observations done"
for ep in $eps; do
  while [ "$(jobs -rp | wc -l)" -ge "$MAXJ" ]; do sleep 5; done
  log "start localize $ep"
  ( "$PY" "$HERE/vision_loc_cli.py" localize --episodes "$ep" --calibration "$HERE/calibration_train.json" \
      --config "$cfg" --checkpoint "$ckpt" --filters vision,boundary,deadreck,oracle --obs "$out/obs" \
      --oracle-obs "$out/oracle-obs" --output "$out/estimates" > "$out/localize-$ep.log" 2>&1 \
    && log "end localize $ep" || log "FAILED localize $ep" ) &
done
sec=$("$PY" -c "import json;d=json.load(open('$pre'));print(d.get('secondary',{}).get('config',{}).get('file',''))")
if [ -n "$sec" ]; then
  for ep in $eps; do
    while [ "$(jobs -rp | wc -l)" -ge "$MAXJ" ]; do sleep 5; done
    log "start secondary $ep"
    ( "$PY" "$HERE/vision_loc_cli.py" localize --episodes "$ep" --calibration "$HERE/calibration_train.json" \
        --config "$HERE/$sec" --checkpoint "$ckpt" --filters vision --obs "$out/obs" --role secondary \
        --output "$out/estimates-secondary" > "$out/localize-secondary-$ep.log" 2>&1 \
      && log "end secondary $ep" || log "FAILED secondary $ep" ) &
  done
fi
wait
if grep -q FAILED "$out/test_load.txt"; then echo "a localization failed; not scoring" >&2; exit 3; fi
"$PY" "$HERE/vision_loc_cli.py" score --episodes $eps --estimates "$out/estimates" --obs "$out/obs" \
  --oracle-obs "$out/oracle-obs" --config "$cfg" --checkpoint "$ckpt" --output "$HERE/results/metrics_test_v3.json" \
  > "$out/score.txt" 2>&1
log "scored once -> results/metrics_test_v3.json"
if [ -n "$sec" ]; then
  "$PY" "$HERE/vision_loc_cli.py" score --episodes $eps --estimates "$out/estimates-secondary" --obs "$out/obs" \
    --oracle-obs "$out/oracle-obs" --config "$HERE/$sec" --checkpoint "$ckpt" --role secondary \
    --output "$HERE/results/metrics_test_v3_secondary.json" > "$out/score-secondary.txt" 2>&1
  log "secondary scored once -> results/metrics_test_v3_secondary.json"
fi
