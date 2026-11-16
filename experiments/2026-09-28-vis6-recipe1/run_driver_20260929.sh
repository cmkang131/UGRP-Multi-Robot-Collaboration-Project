#!/bin/bash
# VIS6 replay driver: the #253 README "관리자용 후속 재생 명령" in order, VL_JOBS=3 (shared Mac),
# with the plan stop rules 1-4 and the 40 CPU-h budget (rule 6) applied between stages.
# CPU time = user+sys of each run_units_v6.sh invocation's children (/usr/bin/time -p).
set -euo pipefail
WT=/Users/changmin/projects/ugrp-wt/claude-vis6-replay
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
VIS=$WT/experiments/2026-09-26-vision-loc
P=$WT/experiments/2026-09-28-vis6-recipe1
OUT=$1
FIT="vl-dev-s909 vl-dev-s910 vl-dev-s911 vl3-dev-s941 vl3-dev-s942 vl3-dev-s943"
VAL="vl3-dev-s945 vl3-dev-s946 vl3-dev-s947"
export VL_JOBS=3 OMP_NUM_THREADS=1
[ ! -e "$OUT" ] || { echo "output root exists: $OUT" >&2; exit 2; }
mkdir -p "$OUT"
git -C "$WT" rev-parse HEAD > "$OUT/source_sha.txt"
cp "$0" "$OUT/driver.sh"
log() { echo "$(date -u +%FT%TZ) $* | load $(sysctl -n vm.loadavg)" | tee -a "$OUT/driver_log.txt"; }
units() {  # stage cands seeds eps
  local stage=$1; shift
  log "units start $stage: $1 | seeds $2"
  /usr/bin/time -p -o "$OUT/cpu_$stage.$(date +%s).txt" "$P/run_units_v6.sh" "$OUT" "$@"
  log "units end $stage"
}
cpu_h() { cat "$OUT"/cpu_*.txt 2>/dev/null | awk '$1=="user"||$1=="sys"{s+=$2} END{printf "%.2f", s/3600}'; }
budget() {
  local h; h=$(cpu_h); log "cumulative CPU-h $h after $1"
  if awk -v h="$h" 'BEGIN{exit !(h>40)}'; then log "STOP: budget 40 CPU-h exceeded after $1 (rule 6)"; exit 0; fi
}

# P0
units P0a "T0 T1c_inert" "0" "vl-dev-s909"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes vl-dev-s909 --output "$OUT/P0_first_a1.json"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T1c_inert --baseline "$OUT/runs/T0/seed0" --episodes vl-dev-s909 --output "$OUT/P0_first_inert.json"
log "P0 first-unit reproduction passed"
units P0b "T0" "0" "vl-dev-s910 vl-dev-s911 vl3-dev-s941 vl3-dev-s942 vl3-dev-s943"
units P0c "T0" "1 2" "$FIT"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes $FIT --output "$OUT/P0_reproduce_fit.json"
log "P0 fit reproduction passed"
budget P0

# S1-S3
S13="T1b_eta050 T1b_eta025 T1b_eta0125 T1c T1ac_d02a3 T1ac_d02a6 T1ac_d05a3 T1ac_d05a6 T1ac_d10a3 T1ac_d10a6"
units S13 "$S13" "0 1 2" "$FIT"
$PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 --episodes $FIT --output "$OUT/metrics_fit_S1_S3.json" \
  --candidates T0 $S13
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage calibration --output "$OUT/select_S1.json" \
  --candidates T0 T1b_eta050 T1b_eta025 T1b_eta0125
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage detector --output "$OUT/select_S2.json" --candidates T1c
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S1_S3.json" --stage lowest-nll --output "$OUT/select_S3.json" \
  --candidates T1ac_d02a3 T1ac_d02a6 T1ac_d05a3 T1ac_d05a6 T1ac_d10a3 T1ac_d10a6
budget S13

jget() { python3 -c "import json,sys;v=json.load(open(sys.argv[1])).get(sys.argv[2]);print('' if v is None else v)" "$1" "$2"; }
S2PASS=$(jget "$OUT/select_S2.json" pass)
S3=$(jget "$OUT/select_S3.json" chosen)
B=$(jget "$OUT/select_S1.json" chosen)
[ "$B" = "T0" ] && B=""
log "S1 chosen='$B' S2 pass=$S2PASS S3 chosen='$S3'"

A=""; G=""
if [ "$S2PASS" = "True" ] && [ -n "$S3" ]; then
  G=${S3#T1ac_}
  units S4 "T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125" "0 1 2" "$FIT"
  $PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 --episodes $FIT --output "$OUT/metrics_fit_S4.json" \
    --candidates T1ac_$G T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125
  $PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_fit_S4.json" --stage calibration --output "$OUT/select_S4.json" \
    --candidates T1ac_$G T1abc_${G}_eta050 T1abc_${G}_eta025 T1abc_${G}_eta0125
  A=$(jget "$OUT/select_S4.json" chosen)
  budget S4
else
  log "S4 skipped (rule 2/3: S2 pass=$S2PASS, S3 chosen='$S3')"
fi

# F: order A, T1ac_G, B, T1c; drop empty/duplicate; T1c and T1ac only if S2 passed
FC=""
add() { [ -n "$1" ] && case " $FC " in *" $1 "*) ;; *) FC="$FC $1";; esac; return 0; }
if [ "$S2PASS" = "True" ]; then add "$A"; [ -n "$G" ] && add "T1ac_$G"; fi
add "$B"
if [ "$S2PASS" = "True" ]; then add T1c; fi
FC=$(echo $FC)
log "F candidates: '$FC'"
if [ -z "$FC" ]; then log "F: no candidate (rule 4: keep b0)"; exit 0; fi
units F "T0 $FC" "0 1 2 3 4" "$VAL"
$PY "$VIS/replay_v6.py" reproduce --root "$OUT/runs" --candidate T0 --episodes $VAL --output "$OUT/P0_reproduce_val.json"
$PY "$VIS/replay_v6.py" evaluate --root "$OUT/runs" --seeds 0 1 2 3 4 --episodes $VAL --output "$OUT/metrics_val_F.json" \
  --candidates T0 $FC
$PY "$VIS/replay_v6.py" select --metrics "$OUT/metrics_val_F.json" --stage final --baseline T0 --output "$OUT/select_F.json" \
  --candidates $FC
budget F
log "DONE"
