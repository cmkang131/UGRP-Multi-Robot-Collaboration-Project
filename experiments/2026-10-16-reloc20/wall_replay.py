import subprocess
import platform
assert platform.node().startswith("ugrp-sim-gcp2"), "gcp2-only analysis"
import json,sys,subprocess,hashlib
from pathlib import Path
import cv2,numpy as np
def read(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from sim.solo_carry_obstacles import detections
from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
from harness.reloc16_floor_mask import floor_clear,OPTION,PROFILE
import harness.reloc16_floor_mask as fm
state=ColourBoundaryState(PROFILE,json.load(open(root/'experiments/2026-10-16-reloc16/colour-calibration.json')),option=RELOC16_OPTION)
old=fm.floor_clear
fm.floor_clear=lambda bgr,clear:old(bgr,clear,state=state,option=OPTION)
r=Path('/home/ugrp/ugrp-sim/runs/reloc20-r1-carry-candidate-93266-aede24d6/raw');lines=read(r/'teacher-commands.jsonl').splitlines();c=[json.loads(x) for x in lines];out=[]
manifest=json.loads(read(r/'playback/manifest.json'))['frames']
for t in [f['t'] for f in manifest if 75<=f['t']<=96]:
 f=min(manifest,key=lambda x:abs(x['t']-t));x=min(c,key=lambda x:abs(x['t']-f['t']));ix=c.index(x);pwm={int(k):v for k,v in c[max(0,ix-1)]['command']['pwm'].items()}
 p=r/'playback'/f['files']['r1'];bgr=cv2.imread(str(p))
 a,_=detections(bgr,pwm,managed=True);b,_=detections(bgr,pwm,managed=True,wall_mask=True)
 out.append(dict(t=f['t'],requested_t=t,source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),before=a,after=b))
p=Path('/home/ugrp/ugrp-sim/runs/reloc20-prior/wall-replay.json');p.write_text(json.dumps(dict(rows=out,scope='saved own RGB; no geometry/GT mask; frozen v5 classifier unchanged'),indent=2)+'\n');print(json.dumps([x for x in out if any(z['kind']=='can' for z in x['before'])],indent=2))
