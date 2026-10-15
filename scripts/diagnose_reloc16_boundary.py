import cv2,numpy as np,collections,json
from pathlib import Path
from scripts.summarize_scene_tex3 import read,write
from scripts.score_scene_tex5 import signal
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.zone_teacher import FOLDED
from harness.zone_pair_highpose import HIGH
from harness.scene_colour_boundary import ColourBoundaryState,surface_masks,RELOC16_OPTION
from harness.active_wall_vision import modules
cv2.setNumThreads(1);mp,hfw,_=modules()
root=Path('/home/ugrp/ugrp-sim/runs/scenetex5-r3-indigo110_s80');cal=read(Path('experiments/2026-10-16-reloc16/colour-calibration.json'));counts=collections.Counter();rows=[]
for idx in read(root/'index.json'):
 r=read(root/idx['record']);pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
 if pwm!=FOLDED:continue
 stem=r['case']+'--'+r['material']+'--'+r['quality'];masks={s:cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
 before=cv2.imread(str(root/r['encodings']['png']['file']));after=cv2.imread(str(root/(stem+'--next.png')))
 state=ColourBoundaryState(r['material'],cal,option=RELOC16_OPTION)
 und,scan,cm,truth=signal(before,after,pwm,masks,state,return_scan=True)
 pred,score=surface_masks(und,cal);top=hfw.self_top_mask(und,cm,hfw.PARAMS,False);missing=[]
 for j,u in enumerate(cm.columns):
  edges=np.flatnonzero(truth['wall'][:-1,u]&truth['floor'][1:,u]);v=scan['vb'][j,0]
  if np.isfinite(v) or not len(edges):continue
  y=int(edges[-1]);why=[]
  for surf,sl in [('wall',slice(max(0,y-10),max(0,y-2))),('floor',slice(y+1,min(480,y+11)))]:
   a=np.median(pred[surf][:,max(0,u-2):min(640,u+3)],axis=1)[sl]
   if not a.any():why.append('no_'+surf+'_class_near_truth')
  if y>=top[j]-hfw.PARAMS['self_margin_px']-1:why.append('self_top')
  t=cm.t_of_row(np.full(96,y))[j]
  if np.isfinite(t):
   ran,_=hfw.column_range_bearing(cm,j,t)
   if not hfw.PARAMS['min_range_m']<=ran<=hfw.PARAMS['max_range_m']:why.append('range')
  else:why.append('ray')
  if not why:why=['candidate_or_consensus']
  counts.update(why);missing.append(dict(u=int(u),y=y,why=why,wall=und[max(0,y-5),u].tolist(),floor=und[min(479,y+5),u].tolist()))
 rows.append(dict(case=r['case'],returned=int(np.isfinite(scan['vb'][:,0]).sum()),missing=missing))
rows.sort(key=lambda r:len(r['missing']),reverse=True)
out=Path('/home/ugrp/ugrp-sim/runs/reloc16-static-r1')
write(out/'diagnosis.json',dict(counts=dict(counts),worst=rows[:6]))
print(json.dumps(dict(counts=dict(counts),worst=[dict(case=r['case'],returned=r['returned'],missing=len(r['missing'])) for r in rows[:6]])))
