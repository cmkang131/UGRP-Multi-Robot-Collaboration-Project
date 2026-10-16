import json,hashlib,sys,os
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
root=base/'runs/mapbuild4/pulse-warp-r1';states=np.load(root/'eval-state.npz')['qpos'];rows=json.loads((root/'metrics.json').read_text());profiles={};tails=[]
for i,row in enumerate(rows):
 if row['pose']!='drive' or row['axis'] not in ['forward','turn']:continue
 origin=pose(states[100,i]);curve=[between(origin,pose(states[t,i])).tolist() for t in range(100,131)]
 key=f"drive:{row['axis']}:{row['u']:.2f}:{row['ms']/1000:.2f}"
 profiles[key]=dict(times=[t/100 for t in range(31)],curve=curve)
 tails.append(dict(name=row['name'],residual_after_300ms=between(pose(states[130,i]),pose(states[-1,i])).tolist()))
meta=dict(physics_backend='mjwarp',id='mapbuild4_clean_response_v1',qualification='EXPLORATORY_ONE_FIXED_START_NOT_GENERALIZED',profiles=profiles,source=str(root),source_state_sha256=hashlib.sha256((root/'eval-state.npz').read_bytes()).hexdigest(),source_sha=json.load(open(root/'queue.json'))['source_sha'],tail_window_s=.3,tail_basis='existing v122 .1s drive pulse and .2s stop/reobserve; complete residual reported separately',tail_residuals=tails,uncertainty='not independently identified; mapping requires visual pose updates')
p=base/'runs/mapbuild4/pulse-analysis-r1/motion-calibration.json';p.write_text(json.dumps(meta,indent=2)+'\n');print(json.dumps(tails))
