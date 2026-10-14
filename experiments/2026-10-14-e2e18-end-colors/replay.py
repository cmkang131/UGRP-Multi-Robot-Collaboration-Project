"""Offline negative control on unchanged raw; synthetic unit positives separate."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
from harness.e2e_end_colors import observe,COLORS,record
from harness.e2e_live_mapping import camera_transform
from harness.owncam_view import _pixel_rays
import numpy as np

def rays(servo,step=8):
 o,r=camera_transform(servo);x,y,n,v=_pixel_rays(step);d=np.column_stack((n,np.ones(len(n))))@r.T;d/=np.linalg.norm(d,axis=1,keepdims=True)
 return o,d,x,y,v
manifest=read(ROOT/'experiments/2026-10-14-e2e18-end-assignment/replay-input-manifest.json')
rows=[]
for f in manifest:
 raw=(ROOT/f['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==f['sha256']
 rows.append(dict(source=f['path'],sha256=f['sha256'],results={c:observe(raw,f['servo'],c,rays) for c in COLORS}))
summary=dict(scope='unchanged saved black-band RGB: negative controls only; synthetic recolored fixture positives are unit tests, not physical success',
    frames=len(rows),detections=sum(bool(v.get('end_visible')) for row in rows for v in row['results'].values()),
    observation_count=len(rows)*len(COLORS),profile=record(),input_sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
    results=[dict(source=r['source'],sha256=r['sha256'],reason={c:v.get('reason') for c,v in r['results'].items()}) for r in rows])
p=Path(__file__).with_name('offline-replay.json');p.write_text(json.dumps(summary,indent=2)+'\n')
print({k:v for k,v in summary.items() if k not in ('results','profile')})
