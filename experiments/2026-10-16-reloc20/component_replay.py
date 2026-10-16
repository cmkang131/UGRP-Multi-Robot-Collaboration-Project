import subprocess
import platform
assert platform.node().startswith("ugrp-sim-gcp2"), "gcp2-only analysis"
from pathlib import Path
import json,sys,inspect,hashlib,collections
import cv2,numpy as np
def read(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
root=Path('/home/ugrp/ugrp-sim/src/1b31086019b0d24a696a8069c790f9113d572e0e');sys.path.insert(0,str(root))
import sim.solo_carry_obstacles as m
from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
from harness.reloc16_floor_mask import floor_clear,OPTION,PROFILE
import harness.reloc16_floor_mask as fm
state=ColourBoundaryState(PROFILE,json.load(open(root/'experiments/2026-10-16-reloc16/colour-calibration.json')),option=RELOC16_OPTION);original=fm.floor_clear
fm.floor_clear=lambda image,clear:original(image,clear,state=state,option=OPTION)
def touches(comp,wall):
 mask=np.zeros((480,640),np.uint8);cv2.drawContours(mask,[comp['contour']],-1,1,-1);return bool(np.any(wall&(mask>0)))
s=inspect.getsource(m.detections).replace('def detections(', 'def candidate(')
a="        raw = raw.copy(); raw[excluded] = 0\n        comps, _ = _components(raw, 6. if kind != 'robot' else 20.)"
b="        raw = raw.copy()\n        held_only=held_mask(held_kind,grasp_pwm,pwm) if held_kind is not None else np.zeros((480,640),bool)\n        raw[held_only]=0\n        comps, _ = _components(raw, 6. if kind != 'robot' else 20.)\n        clear,_=floor_clear(bgr,np.ones((480,640),bool))\n        comps=[comp for comp in comps if not touches(comp,~clear)]"
assert a in s;s=s.replace(a,b);ns=dict(m.__dict__,touches=touches,floor_clear=fm.floor_clear);exec(s,ns);candidate=ns['candidate']
R=Path('/home/ugrp/ugrp-sim/runs');q=json.load(open(R/'reloc20-round2/queue.json'));reports=[]
for t in q['runs']:
 if t['kind']!='carry':continue
 raw=Path(t['raw']);c=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()];manifest=json.loads(read(raw/'playback/manifest.json'))['frames'];results=[]
 for f in manifest:
  if not 1.5<=f['t']<=40:continue
  ix=min(range(len(c)),key=lambda i:abs(c[i]['t']-f['t']));pwm={int(k):v for k,v in c[max(0,ix-1)]['command']['pwm'].items()};p=raw/'playback'/f['files']['r1'];bgr=cv2.imread(str(p));before,_=m.detections(bgr,pwm,managed=True,wall_mask=True);after,_=candidate(bgr,pwm,managed=True,wall_mask=True)
  results.append(dict(t=f['t'],source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),before=before,after=after))
 reports.append(dict(run=t['name'],N=len(results),before=dict(collections.Counter(o['kind'] for x in results for o in x['before'])),after=dict(collections.Counter(o['kind'] for x in results for o in x['after'])),rows=results))
p=R/'reloc20-prior/component-replay.json';p.write_text(json.dumps(dict(scope='retrospective saved2Hz, control exposures offset .2s; no plant, constant changes or live state',runs=reports),indent=2)+'\n');print(json.dumps([{k:v for k,v in x.items() if k!='rows'} for x in reports],indent=2))
