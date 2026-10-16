#!/bin/bash
# Bit-identity gate for scripts/dev_pair_checkpoint.py. One physics process at a time (coordinator 2026-10-05).
# Start only after the coordinator's resume order. Slots (same coordinator PID) must be held beforehand:
#   SLOT (branch claude/v98-checkpoint) and SLOT_HEAD (branch claude/v98-ckpt-headbase).
# Usage: run_gate.sh <gate output root under primary outputs>
set -u
WT=/Users/changmin/projects/ugrp-wt/v98-checkpoint
HEADWT=/Users/changmin/projects/ugrp-wt/v98-ckpt-headbase
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
SESSION="python3 /Users/changmin/projects/ugrp/scripts/ugrp_session.py run"
ROOT=$1
SLOT=${SLOT:-sim-claude-ckpt-a}; SLOT_HEAD=${SLOT_HEAD:-sim-claude-ckpt-head}
CAL=experiments/2026-10-05-unloaded-gain-calibration-v101/products/C/calibration_dev_pilot_unloaded_v101.json
CALSHA=aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4
CASE=zone_wide_door_geometry_v3
cd $WT || exit 2
git fetch -q origin codex/pair-carry-highpose || exit 2
BASE=$(git rev-parse FETCH_HEAD)
# 0. refuse a stale base: this branch must contain the newest #363 head, and the HEAD worktree must be exactly it.
git merge-base --is-ancestor $BASE HEAD || { echo "rebase onto newest #363 head $BASE first"; exit 3; }
[ "$(git -C $HEADWT rev-parse HEAD)" = "$BASE" ] || { echo "HEAD baseline worktree is not at $BASE"; exit 3; }
[ -z "$(git status --porcelain --untracked-files=all)" ] || { echo dirty; exit 3; }
SHA=$(git rev-parse HEAD)
LOG=$ROOT/gate_log.jsonl
mkdir -p $ROOT
stamp() { $PY -c "import json,os,sys,time; print(json.dumps({'step': sys.argv[1], 'event': sys.argv[2], 'unix': time.time(), 'loadavg': os.getloadavg(), 'code_sha': sys.argv[3], 'base_sha': sys.argv[4]}))" "$1" "$2" "$SHA" "$BASE" >> $LOG; }
COMMON="--check carry --map-id $CASE --admission dev-pilot --calibration $CAL --calibration-sha256 $CALSHA --case-id $CASE --lock-owner claude"
CMP="$PY -m scripts.dev_pair_checkpoint compare"

# 1. HEAD baseline, short probe (same probe as step 2)
stamp head_short start
(cd $HEADWT && $SESSION ckpt-gate-head -- $PY -m scripts.run_pair_highpose $COMMON --sim-slot $SLOT_HEAD \
  --stage-probe raise_high_align --expected-source-sha $BASE --output $ROOT/head_raise_high_align --execute) > $ROOT/head_short.log 2>&1
stamp head_short end

# 2. default off: this branch's plain runner (dev_checkpoint=None), same probe -> must equal HEAD byte for byte
stamp flag_off_short start
$SESSION ckpt-gate-flagoff -- $PY -m scripts.run_pair_highpose $COMMON --sim-slot $SLOT --stage-probe raise_high_align \
  --expected-source-sha $SHA --output $ROOT/flag_off_raise_high_align --execute > $ROOT/flag_off.log 2>&1
stamp flag_off_short end
$CMP --continuous $ROOT/head_raise_high_align/$CASE --resumed $ROOT/flag_off_raise_high_align/$CASE \
  --from-sim-s 0 --min-horizon-s 50 --report $ROOT/compare_flag_off_vs_head.json > $ROOT/compare_flag_off_vs_head.summary.json 2>&1

# 3. continuous align_to_carry with checkpoints (DEV horizon stop 165 SIM s = enough for T+62 at both T)
stamp continuous start
$SESSION ckpt-gate-cont -- $PY -m scripts.dev_pair_checkpoint run --after-carry-go-s 5 --every-s 25 --stop-at-sim-s 165 \
  $COMMON --sim-slot $SLOT --stage-probe align_to_carry --expected-source-sha $SHA --output $ROOT/continuous --execute \
  > $ROOT/continuous.log 2>&1
stamp continuous end
# saving on vs HEAD (cross-probe: the HEAD short run is a prefix up to HIGH; only the stage name differs in one event row)
$CMP --continuous $ROOT/continuous/$CASE --resumed $ROOT/head_raise_high_align/$CASE --from-sim-s 0 --min-horizon-s 50 \
  --ignore-event-key stage --report $ROOT/compare_saving_on_vs_head.json > $ROOT/compare_saving_on_vs_head.summary.json 2>&1

# 4. T1 (inside a carry leg: first carry_go_plus checkpoint) and T2 (last periodic checkpoint before T1)
$PY - "$ROOT" > $ROOT/selected.json <<'PY'
import json, sys
from pathlib import Path
rows = [json.loads(l) for l in (Path(sys.argv[1])/'continuous/checkpoints/manifest.jsonl').read_text().splitlines()]
carry = [r for r in rows if any(t.startswith('carry_go') for t in r['triggers'])]
t1 = carry[0]
t2 = [r for r in rows if r['sim_s'] < t1['sim_s'] - 5 and any(t.startswith('every') for t in r['triggers'])][-1]
print(json.dumps({'T1_in_carry_leg': {'file': t1['file'], 'sim_s': t1['sim_s'], 'triggers': t1['triggers']},
                  'T2_before_carry': {'file': t2['file'], 'sim_s': t2['sim_s'], 'triggers': t2['triggers']}}))
PY
for KEY in T1_in_carry_leg T2_before_carry; do
  FILE=$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]['file'])" $ROOT/selected.json $KEY)
  T=$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]['sim_s'])" $ROOT/selected.json $KEY)
  STOP=$($PY -c "print(round($T + 62.0, 3))")
  stamp resume_$KEY start
  $SESSION ckpt-gate-res-$KEY -- $PY -m scripts.dev_pair_checkpoint resume --checkpoint $ROOT/continuous/checkpoints/$FILE \
    --output $ROOT/resumed_$KEY --calibration $CAL --lock-owner claude --sim-slot $SLOT --stop-at-sim-s $STOP \
    > $ROOT/resumed_$KEY.log 2>&1
  stamp resume_$KEY end
  $CMP --continuous $ROOT/continuous/$CASE --resumed $ROOT/resumed_$KEY/$CASE --from-sim-s $T --min-horizon-s 60 \
    --report $ROOT/compare_$KEY.json > $ROOT/compare_$KEY.summary.json 2>&1
done
stamp all done
(cd $ROOT && find . -name 'compare_*.json' -o -name 'gate_log.jsonl' -o -name 'selected.json' | sort | xargs shasum -a 256) > $ROOT/evidence.sha256
