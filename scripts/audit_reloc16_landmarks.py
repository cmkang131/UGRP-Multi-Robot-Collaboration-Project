import cv2,numpy as np,json,collections
from pathlib import Path
from scripts.summarize_scene_tex3 import read,write
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.zone_teacher import FOLDED
from harness.scene_colour_boundary import surface_masks
from harness.self_map_landmark_sensor import Sensor
from harness.selfmap4_geometry import static_input
from harness.own_map_amcl_vendor import landmarks as lm
from harness.active_wall_vision import modules
cv2.setNumThreads(1);mp,_,_=modules();static,_=static_input();sensor=Sensor(lm.MapFeatures(static).hues)
cal=read(Path('experiments/2026-10-16-reloc16/colour-calibration.json'));orig=lm.floor_features
root=Path('/home/ugrp/ugrp-sim/runs/scenetex5-r3-indigo110_s80');rows=[]
empty=dict(columns=[],uv=[])
def masked(image,cm,K,palette,clear):return orig(image,cm,K,palette,clear & ~surface_masks(image,cal,expanded_wall_value=True)[0]['wall'])
def wall_support(f,gt):
 p,q=np.asarray(f['pixels']);d=q-p;n=np.array([-d[1],d[0]])/np.linalg.norm(d)
 uv=p+(q-p)*np.linspace(.05,.95,15)[:,None]
 fractions=[]
 for sign in (1,-1):
  z=np.rint(uv+sign*lm.PARAMS['side_offset_px']*n).astype(int);z[:,0]=z[:,0].clip(0,639);z[:,1]=z[:,1].clip(0,479)
  fractions.append(float(gt[z[:,1],z[:,0]].mean()))
 return max(fractions)
for idx in read(root/'index.json'):
 r=read(root/idx['record'])
 if pose_pwm_mode(r['pose'])!='FOLDED':continue
 stem=r['case']+'--'+r['material']+'--'+r['quality']
 truth={s:cv2.remap(cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0),mp._UNDISTORT[0],mp._UNDISTORT[1],cv2.INTER_NEAREST)>0 for s in ('wall','floor')}
 for e in ('png','jpeg90','pil82'):
  bgr=cv2.imread(str(root/r['encodings'][e]['file']));und=mp.undistort(bgr)
  lm.floor_features=orig;a=[f for f in sensor.measure(bgr,FOLDED,empty) if f['kind']=='floor_line']
  lm.floor_features=masked;b=[f for f in sensor.measure(bgr,FOLDED,empty) if f['kind']=='floor_line']
  mask=surface_masks(und,cal,expanded_wall_value=True)[0]['wall']
  rows.append(dict(case=r['case'],encoding=e,before_N=len(a),after_N=len(b),before_wall_lines=sum(wall_support(f,truth['wall'])>=lm.PARAMS['side_support'] for f in a),after_wall_lines=sum(wall_support(f,truth['wall'])>=lm.PARAMS['side_support'] for f in b),floor_pixels_removed=int((mask&truth['floor']).sum()),floor_pixels=int(truth['floor'].sum()),before=a,after=b))
  lm.floor_features=orig
out=Path('/home/ugrp/ugrp-sim/runs/reloc16-landmark-audit');out.mkdir(exist_ok=False)
summary={e:{k:sum(r[k] for r in rows if r['encoding']==e) for k in ('before_N','after_N','before_wall_lines','after_wall_lines','floor_pixels_removed','floor_pixels')} for e in ('png','jpeg90','pil82')}
write(out/'summary.json',summary);write(out/'cases.json',rows);print(json.dumps(summary))
