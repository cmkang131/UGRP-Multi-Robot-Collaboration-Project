#!/bin/bash
# Second batch: the recorded hR2 setups (PR #283 conditions incl. the failing hR2_04-06) with seeds 911 and 913.
#   rA  k1g + p2f            rB  k1g + p2f + gain
DIR="$(cd "$(dirname "$0")" && pwd)"
run() {
  for i in $(seq 1 30); do
    SETUP=hr2 "$DIR/run_cohort.sh" "$@" && return 0
    code=$?
    [ "$code" = 3 ] || return "$code"
    sleep 120
  done
}
run rA k1g p2f none
run rB k1g p2f pf
