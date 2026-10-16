#!/bin/bash
# Axial-lag physical check, second driver (2026-09-30, after the laptop was back on AC power). Usage: run_all5.sh <cohort> [<cohort> ...]
# Each cohort takes/releases agent_lock itself (retry every 2 min when another agent holds it). Chained L0 -> L1, floor_light_v1, PF seeds 911/913.
#   tX1b  placements/axial_extra_X06.json (the 2 cases of tX1 killed by SIGTERM)      k1g+p2f+gain+alag
#   tS    the 12 sheet-rounded placements (sB placements)                              k1g+p2f+gain+alag   (control = existing sB, no new run)
#   tR    the 10 recorded hR2 starts                                                   k1g+p2f+gain+alag   (control = existing rB, no new run)
#   tX0   the 7 extra placements of tX1                                                k1g+p2f+gain        (control for tX1/tX1b: same placements, no axial lag)
DIR="$(cd "$(dirname "$0")" && pwd)"
run() {
  for i in $(seq 1 30); do
    "$DIR/run_cohort.sh" "$@" && return 0
    code=$?
    [ "$code" = 3 ] || return "$code"
    sleep 120
  done
}
for c in "$@"; do
  case "$c" in
    tX1b) PLACEMENTS=axial_extra_X06 run tX1b k1g p2f pf --carry-axial-lag axial ;;
    tS)   PLACEMENTS=held_out_sheet_12 run tS k1g p2f pf --carry-axial-lag axial ;;
    tR)   SETUP=hr2 run tR k1g p2f pf --carry-axial-lag axial ;;
    tX0)  PLACEMENTS=axial_extra_7 run tX0 k1g p2f pf ;;
    *) echo "unknown cohort $c" >&2; exit 2 ;;
  esac
done
