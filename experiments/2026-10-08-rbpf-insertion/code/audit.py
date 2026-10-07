"""Evaluation-only stage/range audit. Stored own observations are authoritative."""
import hashlib,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/baseline')
OUT=Path('/Users/changmin/projects/ugrp/outputs/rbpf-insertion-v1')
from harness.self_odom_grid import transform
from harness.active_wall_vision import modules
BINS=['0–1','1–2','2–3','3–4','>4']

def load(p):return json.loads(p.read_text())
def rows(p):
 with p.open() as f:
  for l in f:yield json.loads(l)
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def bin_id(r):return min(4,max(0,int(r)))
def stats(a):
 a=np.asarray(a);return dict(n=len(a),median_m=float(np.median(a)) if len(a) else None,p95_m=float(np.quantile(a,.95)) if len(a) else None,rmse_m=float(np.sqrt(np.mean(a*a))) if len(a) else None)

def main():
 decisions={d['frame_id']:d for d in load(RAW/'decisions.json')}
 frames={r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
 cams={round(r['t'],6):r for r in rows(RAW/'eval_only/camera.jsonl')}
 truth={round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
 sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
 import odom_grid_replay as metrics
 walls=np.array([w['center_m']+w['half_extents_m'] for w in load(RAW/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
 counts={k:Counter() for k in ('all','after_36_1')}
 byrange={k:[Counter() for _ in BINS] for k in counts}
 errors=[defaultdict(list) for _ in BINS]
 check120=[]
 for row in rows(RAW/'own-contacts.jsonl'):
  d=decisions[row['frame_id']];ranges=np.linalg.norm(np.asarray(row['segments'])-row['camera'],axis=2).max(1)
  groups=['all']+(['after_36_1'] if row['t']>36.1+1e-8 else [])
  for key in groups:
   c=counts[key];c['frames']+=1;c['detected_frames']+=bool(len(ranges));c[d['reason']]+=1;c['inserted']+=bool(d['inserted']);c['duplicate']+=0
   c['admitted']+=d['reason']!='gmapping_motion_gate';c['segments']+=len(ranges)
   for distance in ranges:
    b=byrange[key][bin_id(distance)];b['segments']+=1;b[d['reason']]+=1;b['inserted']+=bool(d['inserted'])
  if abs(row['t']-120.)<.31:check120.append(dict(t=row['t'],frame_id=row['frame_id'],segments=len(ranges),range_min_m=float(ranges.min()),range_max_m=float(ranges.max()),reason=d['reason'],inserted=d['inserted']))
  # Same inferred undistorted pixel -> actual camera ray/floor. This isolates
  # pose/projection error without treating false detections as true wall labels.
  own=np.asarray(row['segments']).reshape(-1,2);origin=np.array(row['camera_origin']);rot=np.array(row['camera_rotation'])
  optical=(np.c_[own,np.zeros(len(own))]-origin)@rot
  ray=optical/optical[:,2,None]
  camera=cams[round(row['t'],6)];actual_R=np.array(camera['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1]);actual_o=np.array(camera['camera_xyz'])
  worldray=ray@actual_R.T
  depth=-actual_o[2]/worldray[:,2]
  target=actual_o+depth[:,None]*worldray
  gt=truth[round(row['t'],6)];world=transform(own,[*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
  projerr=np.linalg.norm(world-target[:,:2],axis=1)
  wallerr=metrics.boundary_dist(world,walls)
  validwall=metrics.boundary_dist(target[:,:2],walls)<=.15
  endpoint_range=np.linalg.norm(own-origin[:2],axis=1)
  for i,r in enumerate(endpoint_range):
   if not np.isfinite(target[i]).all() or depth[i]<=0:continue
   b=errors[bin_id(r)];b['projection'].append(float(projerr[i]));b['total_wall'].append(float(wallerr[i]))
   if validwall[i]:b['wall_matched_projection'].append(float(projerr[i]))
 mp,_,_=modules();h=.23;dp=math.radians(.13)
 theory=[]
 for r in [.5,1.5,2.5,3.5,5.]:
  J=(r*r+h*h)/h
  theory.append(dict(range_m=r,pitch_013deg_m=J*dp,pixel_1px_m=J/mp.FY,pixel_quantization_sd_m=J/mp.FY/math.sqrt(12),combined_1px_rss_m=J*math.hypot(dp,1/mp.FY),pitch_exact_max_m=max(abs(h/math.tan(math.atan2(h,r)+sign*dp)-r) for sign in [-1,1])))
 result=dict(input_frames=len(frames),own_frames=len(decisions),warmup_frames=len(frames)-len(decisions),stage_counts=counts,
  range_segments={k:[dict(bin=name,**values) for name,values in zip(BINS,values)] for k,values in byrange.items()},
  projection_by_endpoint_range=[dict(bin=name,**{key:stats(a) for key,a in b.items()}) for name,b in zip(BINS,errors)],
  theory=dict(height_m=h,pitch_error_deg=.13,width_px=mp.WIDTH,height_px=mp.HEIGHT,fy=mp.FY,rows=theory),
  around_120s=check120,qualifications=['Segment max endpoint range controls bin, inclusive lower and exclusive upper except final >=4; exact 4 absent.',
  'Projection comparison uses evaluation-only actual camera vs command camera at the same inferred pixel; it excludes detector edge picking error.',
  'Total wall error uses GT chassis pose, and includes detection, association and projection error.',
  'Peer/self occlusion is not an RBPF rejection reason; instance masks are unavailable, so physical occlusion count is not inferred from nonempty detections.'])
 dump(EXP/'results/stages-projection.json',result)
 dump(OUT/'audit-inputs.json',{str(p.relative_to(RAW)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [RAW/'decisions.json',RAW/'own-contacts.jsonl',RAW/'eval_only/camera.jsonl',RAW/'eval_only/trajectory.jsonl']})
 print(json.dumps(result,indent=2))
 assert 'mujoco' not in sys.modules
if __name__=='__main__':main()
