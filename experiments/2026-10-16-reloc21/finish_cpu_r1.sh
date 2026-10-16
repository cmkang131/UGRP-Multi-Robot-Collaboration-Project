#!/usr/bin/env bash
# One bounded terminal analysis chain; cannot submit another physics round.
set -eu
case "$(hostname -s)" in ugrp-sim-gcp2*) ;; *) exit 2;; esac
reloc21_source=/home/ugrp/ugrp-sim/src/6acde414adc6fee74d024e508a9853e4c1cafcf8
reloc21_python=/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python
reloc21_deadline=$((SECONDS+2400))
while ! test -f /home/ugrp/ugrp-sim/runs/reloc21-round1/DONE; do
    test "$SECONDS" -lt "$reloc21_deadline"
    sleep 15
done
cd "$reloc21_source"
PYTHONPATH="$reloc21_source" "$reloc21_python" /home/ugrp/ugrp-sim/analysis-tools/reloc21-analyze.py --controller-source "$reloc21_source" --round 1 --media
date -Is > /home/ugrp/ugrp-sim/runs/reloc21-round1/ANALYSIS_DONE
