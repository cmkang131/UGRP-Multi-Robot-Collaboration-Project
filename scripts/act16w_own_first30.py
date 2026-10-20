"""Inspect an active ACT owner's already saved first30SIM own RGB at2Hz.

Images only; no physics, model call, overview reconstruction or terminal replay.
Complete episode2Hz plus terminal10Hz playback remains a separate review.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from act16w_runtime import require_gcp2,frozen_source,sha256

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--world-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--label',required=True);a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',a.label):p.error('simple review label required')
    host,source=require_gcp2(training=True),frozen_source(ROOT)
    from PIL import Image
    plan=a.world_root/'plan.json';seed=json.loads(plan.read_text())['seed']
    frames=[x for x in sorted((a.world_root/'review-own').glob('*.jpg')) if int(x.stem)<=300]
    if [int(x.stem) for x in frames]!=list(range(0,301,5)):
        raise ValueError('actual61 first30SIM at2Hz frames required; do not impute running data')
    if any(Image.open(x).size!=(640,480) for x in frames):raise ValueError('actual ACT owner640x480 frames required')
    a.out.mkdir(parents=True,exist_ok=False)
    for start in range(0,len(frames),18):
        part=a.out/f'part-{start//18:02d}';part.mkdir()
        for i,path in enumerate(frames[start:start+18]):(part/f'{i:03d}.jpg').write_bytes(path.read_bytes())
        subprocess.run(['ffmpeg','-y','-loglevel','error','-threads','1','-i',str(part/'%03d.jpg'),
            '-vf',f"scale=320:240,drawtext=text='{a.label} own RGB SIM {start/2:.1f} + %{{n}}/2s':x=4:y=4:fontsize=14:fontcolor=white:box=1:boxcolor=black@0.7,tile=3x6",
            '-frames:v','1',str(a.out/f'first30-2hz-{start//18:02d}.jpg')],check=True)
    report=dict(status='complete',host=host,source_sha=source,seed=seed,SIM_range=[0,30],frames=61,
        original_world=str(a.world_root),plan_sha256=sha256(plan),
        raw=[dict(path=str(x),sha256=sha256(x)) for x in frames],
        sheets=[dict(path=str(x),sha256=sha256(x)) for x in sorted(a.out.glob('*.jpg'))],
        physics_steps=0,model_calls=0,scope=__doc__)
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='complete',seed=seed,first30SIM_frames=61)))


if __name__=='__main__':main()
