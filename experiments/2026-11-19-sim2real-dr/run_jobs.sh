# usage: run_jobs.sh jobs.txt results.jsonl
cd /home/user/UGRP-Multi-Robot-Collaboration-Project
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
cat "$1" | xargs -P 4 -L 1 sh -c 'nice -n 10 /home/user/venv-sim/bin/python experiments/2026-11-19-sim2real-dr/approach_dr.py --scene-source /home/user/deps/solo-teacher-6f057f7e "$@" 2>/dev/null | tail -1 >> '"$2" _
echo finished
