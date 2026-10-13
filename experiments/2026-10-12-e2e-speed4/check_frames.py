import hashlib,json,subprocess
from pathlib import Path
from collections import Counter
import cv2,numpy as np
from harness.e2e_rgb_gate import boundary
from harness.e2e_rgb_vo import ground_pair
from harness.active_wall_vision import observe
from harness.active_camera import SEARCH
from scripts.replay_e2e_speed4 import resize_compat,read_rows
root=Path('outputs/e2e-speed4');inputroot=Path('/Users/changmin/projects/ugrp/outputs/e2e-speed/fetch-lite/e2e13-profile-s61001/raw')
manifest=[];wall=[];pairs=[];markers=[]
for rid in ('r1','r2','r3'):
 ledger={Path(f['path']).name:f for f in read_rows(inputroot/f'robots/{rid}/frames.jsonl')}
 ims={}
 for p in sorted((root/f'samples/robots/{rid}/rgb').glob('*.jpg')):
  f=ledger[p.name];data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
  im=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
  low=resize_compat(im);servo={int(k):v for k,v in f['commanded_servo'].items()}
  ims[int(p.stem)]=(im,low,servo)
  manifest.append(dict(path=str(p),sha256=f['sha256']))
  a,b=observe(im,servo),observe(low,servo)
  ap=np.asarray(a['segments']).reshape(-1,2);bp=np.asarray(b['segments']).reshape(-1,2)
  d=np.linalg.norm(ap[:,None]-bp[None,:],axis=-1) if len(ap) and len(bp) else None
  wall.append(dict(robot=rid,frame=int(p.stem),original=len(a['segments']),half=len(b['segments']),
                   endpoint_chamfer_m=None if d is None else float((d.min(0).mean()+d.min(1).mean())/2)))
 for k,(im,low,servo) in ims.items():
  if k+1 not in ims:continue
  im2,low2,servo2=ims[k+1]
  if servo!=servo2:continue
  a,b=ground_pair(im,im2,servo),ground_pair(low,low2,servo)
  pairs.append(dict(robot=rid,frame=k,status_original=a['status'],status_half=b['status'],
     xy_change_m=float(np.linalg.norm(np.asarray(a['delta'][:2])-b['delta'][:2])) if 'delta'in a and 'delta'in b else None,
     yaw_change_rad=float(abs(a['delta'][2]-b['delta'][2])) if 'delta'in a and 'delta'in b else None))
bs=root/'b-samples';frames={Path(f['path']).name:f for f in read_rows(bs/'robots/r1/frames.jsonl')}
for p in sorted((bs/'robots/r1/rgb').glob('*.jpg')):
 f=frames[p.name];data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256'];manifest.append(dict(path=str(p),sha256=f['sha256']))
 im=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
 servo={int(k):v for k,v in f['commanded_servo'].items()};dd=[]
 for v in (im,resize_compat(im)):
  diag={};b=boundary(v,servo,[0,0,0],marker_detect='contrast_v1',diagnostics=diag);dd.append(dict(detected=b is not None,diagnostics=diag))
 markers.append(dict(frame=p.name,original=dd[0],half=dd[1]))
out=dict(scope='saved JPEG downsample+linear upscale; not new native render',images=len(manifest),inputs=manifest,walls=wall,vo=pairs,markers=markers,
 wall_visible_original=sum(v['original']>0 for v in wall),wall_visible_half=sum(v['half']>0 for v in wall),
 vo_status_original=dict(Counter(v['status_original'] for v in pairs)),vo_status_half=dict(Counter(v['status_half'] for v in pairs)),
 marker_detected_original=sum(v['original']['detected'] for v in markers),marker_detected_half=sum(v['half']['detected'] for v in markers))
(root/'frame-check.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('inputs','walls','vo','markers')}))
