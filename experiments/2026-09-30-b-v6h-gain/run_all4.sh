#!/bin/bash
# Axial-lag check (PR #286 P1b), k1g + p2f + gain (+ axial lag). Each cohort takes/releases agent_lock itself (retry every 2 min).
#   tX1 extras (F_hR2_04 + 6 fresh draws)      k1g+p2f+gain+alag   <- run first as the smoke
#   tS  the 12 sheet-consistent sB placements  k1g+p2f+gain+alag
#   tR  the 10 recorded hR2 setups             k1g+p2f+gain+alag
#   tX0 extras                                 k1g+p2f+gain        (control: same placements without the axial lag)
DIR="$(cd "$(dirname "$0")" && pwd)"
run() {
  for i in $(seq 1 30); do
    "$DIR/run_cohort.sh" "$@" && return 0
    code=$?
    [ "$code" = 3 ] || return "$code"
    sleep 120
  done
}
PLACEMENTS=axial_extra_7 run tX1 k1g p2f pf --carry-axial-lag axial
PLACEMENTS=held_out_sheet_12 run tS k1g p2f pf --carry-axial-lag axial
SETUP=hr2 run tR k1g p2f pf --carry-axial-lag axial
PLACEMENTS=axial_extra_7 run tX0 k1g p2f pf
