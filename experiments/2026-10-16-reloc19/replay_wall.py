"""Native saved-JPEG wall-alias replay; gcp2 only, evaluation-free gates."""
import platform
assert platform.node().startswith("ugrp-sim-gcp2")
from pathlib import Path
import os,json,subprocess,collections,hashlib
import cv2,numpy as np
from sim.solo_carry_to_zone import CarryToZone
from sim.solo_carry_pose import task_start
from harness.visual_arm_v3 import forward_grip
from sim.grasp_act_solo_lookback import regions
from harness.zone_own_perception import PAINT_HUE
from harness.scene_colour_boundary import surface_masks
R=Path('/home/ugrp/ugrp-sim/runs');p=R/'reloc19-r1-carry-A-93315-3da9f8d9/raw'
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
c=[json.loads(x) for x in load(p/'teacher-commands.jsonl').splitlines()];by={round(x['t'],5):x for x in c}
r=json.loads(load(p/'result.json'));static=json.loads((p/'carry-static-map.json').read_text());low=next(x['command']['pwm'] for x in reversed(c) if x['phase']=='close');low={int(k):v for k,v in low.items()};low[1]=1500
gp=forward_grip(low);carry=CarryToZone(static,'C',start=task_start(static));carry.grip_xy=gp[:2];carry.slot=static['regions']['zone_C']['center_m']
cal=json.loads(Path('experiments/2026-10-16-reloc16/colour-calibration.json').read_text());out=[]
for f in json.loads((p/'failure-rgb/manifest.json').read_text())['frames']:
 path=p/'failure-rgb'/f['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
 bgr=cv2.imread(str(path));row=by[round(f['t'],5)];pwm={int(k):v for k,v in row['command']['pwm'].items()}
 roi,_,geom=regions(r['object_kind'],low,pwm,site=(gp[0]+.15,gp[1],0))
 hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV);lo,hi=PAINT_HUE['C'];paint=(hsv[...,0]>=lo-5)&(hsv[...,0]<=hi+5)&(hsv[...,1]>=30)&(hsv[...,2]>=30)
 wall=surface_masks(bgr,cal,expanded_wall_value=True)[0]['wall'];old=bool(geom['qualified'] and np.mean(paint[roi])>=.6);new=bool(geom['qualified'] and np.mean((paint&~wall)[roi])>=.6)
 out.append(dict(t=f['t'],phase=row['phase'],old_gate=old,wall_mask_gate=new,paint_pixels=int(paint.sum()),wall_paint_pixels=int((wall&paint).sum()),paint_fraction=float(np.mean(paint[roi])),masked_fraction=float(np.mean((paint&~wall)[roi])),geometry=geom['qualified']))
result=dict(analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),run=p.parent.name,source=str(p),low=low,grip=list(gp),frames=out,summary=dict(N=len(out),old_gate_true=sum(x['old_gate'] for x in out),wall_mask_true=sum(x['wall_mask_gate'] for x in out),all_wall_paint_pixels=sum(x['wall_paint_pixels'] for x in out)),scope='native last10s JPEG and issued PWM, no evaluator input to reconstructed gates')
(R/'reloc19-round1/wall-replay.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))
