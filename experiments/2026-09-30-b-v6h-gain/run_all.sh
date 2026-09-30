#!/bin/bash
# Runs the exploratory b-v6h gain-fix chain cohorts one after another (each cohort takes/releases agent_lock itself;
# a refused lock is retried every 2 minutes, never forced). Run from the frozen run worktree.
#   A  k1g + p2f                (control: no gain fix)
#   B  k1g + p2f + gain         (variant ii)
#   D  k2  + p2f + gain         (registered sigma multiples and gate + gain fix; variant iii)
#   C  k1  + p2f + gain         (sigma multiple 1, registered gate + gain fix; variant iii)
#   F  k2  + p2f                (registered guard, no gain fix: isolates the gain effect at the registered guard)
DIR="$(cd "$(dirname "$0")" && pwd)"
run() {  # tag door prog gain
  for i in $(seq 1 30); do
    "$DIR/run_cohort.sh" "$@" && return 0
    code=$?
    [ "$code" = 3 ] || return "$code"
    sleep 120
  done
}
run cA k1g p2f none
run cB k1g p2f pf
run cD k2 p2f pf
run cC k1 p2f pf
run cF k2 p2f none
