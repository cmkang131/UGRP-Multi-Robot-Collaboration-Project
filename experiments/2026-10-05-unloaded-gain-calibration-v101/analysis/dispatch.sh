#!/bin/bash
# one line of rec_tasks.txt: "HELD cfg case robot" or "REC cfg robot seed mode"
D=/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/tools
k=$1; shift
if [ "$k" = HELD ]; then $D/run_held_task.sh "$@"; else $D/run_rec_task.sh "$@"; fi
