#!/bin/bash
# Start the not-yet-started replay tasks of leg_tasks*.txt, never more than MAX of my replay_pf.py at once (coordinator 2026-10-05 load request: <= 3).
D=/Users/changmin/projects/ugrp/outputs/pf-loadedgain-v102-20261005
MAX=${MAX:-3}
cat ${TASKS:-$D/tools/leg_tasks.txt $D/tools/leg_tasks_nomeas.txt} | while read tree cfg r off mode calp cals; do
  [ -z "$tree" ] && continue
  [ -e "${OUTDIR:-$D/replay}/${cfg}_${r}_s${off}_${mode}.log" ] && continue
  while [ "$(pgrep -f "pf-loadedgain-v102-20261005/tools/replay_pf.py" | wc -l)" -ge "$MAX" ]; do sleep 20; done
  nohup $D/tools/run_leg_task.sh $tree $cfg $r $off $mode $calp $cals > /dev/null 2>&1 &
  sleep 5
done
wait
