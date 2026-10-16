#!/bin/bash
# Third batch: 12 new placements whose order sheet is the beam pose rounded to the sheet grid (as in the recorded hR2 setups), so the
# route start moves with the beam (start offsets of both signs relative to the first route point).
#   sA  k1g + p2f            sB  k1g + p2f + gain
DIR="$(cd "$(dirname "$0")" && pwd)"
run() {
  for i in $(seq 1 30); do
    PLACEMENTS=held_out_sheet_12 "$DIR/run_cohort.sh" "$@" && return 0
    code=$?
    [ "$code" = 3 ] || return "$code"
    sleep 120
  done
}
run sA k1g p2f none
run sB k1g p2f pf
