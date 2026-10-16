import json,hashlib,sys,os,math
from pathlib import Path
import numpy as np
base=Path('/home/ugrp/ugrp-sim');renderer=base/'src/drivecheck-renderer-5974a181'
sys.path[:0]=[str(renderer),str(renderer/'scripts')];os.chdir(renderer)
from scripts.probe_scene_tex2 import build_model
from scripts.generate_scene_textures import MAPS
from harness.e2e_rgb_vo import between
m,*_=build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80');bid=m.body('r1__robot').id;adr=int(m.jnt_qposadr[m.body_jntadr[bid]])
def pose(q):
 w,x,y,z=q[adr+3:adr+7];return np.r_[q[adr:adr+2],np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))]
output=[];contacts=[]
for kind,onset,round_ in [('pulse',100,1),('phase',200,2),('native-pulse',100,3),('native-phase',200,3)]:
 for backend in ['cpu','warp']:
  root=base/f'runs/mapbuild4/{kind}-{backend}-r{round_}'
  if not (root/'metrics.json').exists():continue
  rows=json.load(open(root/'metrics.json'));qs=np.load(root/'eval-state.npz')['qpos']
  for i,r in enumerate(rows):
   if r['axis']!='left':continue
   origin=pose(qs[onset,i]);curve=np.asarray([between(origin,pose(q)) for q in qs[onset:,i]])
   output.append(dict(phase=kind,backend=backend,name=r['name'],final_delta=r['delta'],during_delta=r['during_delta'],
      peak_y_mm=float(np.max(curve[:,1])*1000),min_y_mm=float(np.min(curve[:,1])*1000),
      peak_translation_mm=float(np.linalg.norm(curve[:,:2],axis=1).max()*1000),
      wheel_phase=r['wheel_phase'],wheel_rotation=r['wheel_rotation'],
      com_body_m=((np.asarray(r['subtree_com'])-qs[onset,i,adr:adr+3])@np.array([[math.cos(origin[2]),math.sin(origin[2]),0],[-math.sin(origin[2]),math.cos(origin[2]),0],[0,0,1]]).T).tolist(),
      raw=str(root),state_sha256=hashlib.sha256((root/'eval-state.npz').read_bytes()).hexdigest(),
      contact_counts=dict(wheel_floor=sum('roller' in (c['g1']+c['g2']) and ('floor' in (c['g1']+c['g2']) or 'ground' in (c['g1']+c['g2'])) for c in r['contacts_at_onset']),
        r1_nonfloor=[c for c in r['contacts_at_onset'] if 'r1__' in (c['g1']+c['g2']) and not any(s in (c['g1']+c['g2']) for s in ['floor','ground'])])))
path=base/'runs/mapbuild4/pulse-analysis-r1/phase-analysis.json';path.write_text(json.dumps(output,indent=2)+'\n')
for r in output:
 if r['phase'] in ('phase','native-phase'):print(r['backend'],r['name'],'finalmm',np.round(np.asarray(r['final_delta'][:2])*1000,4),'peakmm',r['peak_translation_mm'],'duringmm',np.round(np.asarray(r['during_delta'][:2])*1000,4),'com',r['com_body_m'],'contacts',r['contact_counts'])
