"""Evaluator-only C state rendering, ffmpeg4x and ffprobe; no native windows."""
import os
from pathlib import Path
import subprocess

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt5')
OLD=ROOT.parent/'simalt3'
SOURCE=Path('/home/ugrp/ugrp-sim/src/51048030')
for name,run,anchor in [
    ('original-endpoint-fail',ROOT.parent/'simalt4/legacy-r3-grip',12.2085),
    ('C312-positive',ROOT.parent/'simalt4/c312-grip',12.2085),
    ('compiled312',ROOT/'warp-compiled312-grip',23.8)]:
    # The new candidate must be fully retrieved on-host before rendering.
    if not (run/'states.npz').is_file():continue
    out=ROOT/('review-'+name)
    with (ROOT/('review-'+name+'.log')).open('x') as log:
        subprocess.run([str(OLD/'c-env/bin/python'),str(SOURCE/'scripts/simalt_review_physics.py'),
            '--gcp2-v1','--source',str(OLD/'runtime/source'),'--fixture',str(OLD/'fixture'),
            '--run',str(run),'--out',str(out),'--case','grip','--failure-time-s',str(anchor)],
            stdout=log,stderr=subprocess.STDOUT,
            env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'},check=True)
    print(name,'REVIEW_COMPLETE',flush=True)
