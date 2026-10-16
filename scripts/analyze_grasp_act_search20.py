"""Offline evaluator-only error distribution; never imported by a controller."""
from pathlib import Path
import json,math,hashlib
import numpy as np
from scripts.replay_grasp_act_search18 import read
from harness.grasp_act_visible_world import VisibleWorld
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs'))
parser.add_argument('--out',type=Path,required=True)
a=parser.parse_args();root=a.root;out=a.out;out.mkdir(parents=True,exist_ok=True)
errors={'robot_xy_m':[],'assigned_end_xy_m':[],'cargo_xy_m':[],'robot_yaw_rad':[],'relative_body_bound_m':[]};sources=[];runs=[]
for group in ['grasp-search18-repro4-gcp-00620d7a','grasp-search18-novel12-gcp-00620d7a','grasp-search19-repro4-gcp-06558d64']:
 for raw in sorted((root/group).glob('diagnostic*/episode-*/raw')):
  p=json.loads(read(raw/'plan.json'));res=json.loads(read(raw/'result.json'));data=read(raw/'eval-only.jsonl');ev=[json.loads(x) for x in data.splitlines()];led={r:[json.loads(l) for l in read(raw/f'teacher-{r}.jsonl').splitlines()] for r in p['roles']}
  local_errors={k:[] for k in errors}
  models={r:VisibleWorld(r,e,odometry='search17_fixed_v1') for r,e in p['roles'].items()}
  for i,row in enumerate(ev):
   for r,model in models.items():
    w=model.observe(row['visible_measurements'][r],row['t']);start=ev[0]['robots'][r]['pose'];c,s=math.cos(start[2]),math.sin(start[2])
    def anchored(q):
     dx,dy=q[0]-start[0],q[1]-start[1];return [c*dx+s*dy,-s*dx+c*dy]
    true=row['robots'][r]['pose'];local_errors['robot_xy_m'].append(math.dist(w['robots'][r]['pose'][:2],anchored(true)))
    local_errors['robot_yaw_rad'].append(abs(math.atan2(math.sin(w['robots'][r]['pose'][2]-(true[2]-start[2])),math.cos(w['robots'][r]['pose'][2]-(true[2]-start[2])))))
    if w['beam'] is not None and w['visibility'][r]['visible_probes']>=5:
     local_errors['assigned_end_xy_m'].append(math.dist(w['beam']['ends'][p['roles'][r]][:2],anchored(row['beam']['ends'][p['roles'][r]])))
    for k,v in w['objects'].items():
     if k!='beam_1' and k in row['objects']:
      q=anchored(row['objects'][k]['xy']);rp=anchored(true);wp=w['robots'][r]['pose']
      local_errors['cargo_xy_m'].append(math.dist(v['xy'],q))
      vector=math.dist([v['xy'][j]-wp[j] for j in (0,1)],[q[j]-rp[j] for j in (0,1)])
      angular=2*math.hypot(.0925,.07995)*math.sin(local_errors['robot_yaw_rad'][-1]/2)
      local_errors['relative_body_bound_m'].append(vector+angular)
    model.issue(led[r][i]['applied_command'])
  def stats(a):return dict(N=len(a),p50=float(np.quantile(a,.5)),p90=float(np.quantile(a,.9)),p95=float(np.quantile(a,.95)),p99=float(np.quantile(a,.99)),max=max(a)) if a else dict(N=0)
  print(p['seed'],group,{k:len(v) for k,v in local_errors.items()},flush=True)
  runs.append(dict(seed=p['seed'],group=group,errors={k:stats(v) for k,v in local_errors.items()}))
  for k in errors:errors[k].extend(local_errors[k])
  sources.append(dict(path=str(raw/'eval-only.jsonl'),decoded_sha256=hashlib.sha256(data).hexdigest()))
report=dict(scope='evaluator-only frame-anchored error audit; repeated ticks and previously inspected seeds, not independent calibration',errors={k:stats(v) for k,v in errors.items()},runs=runs,sources=sources)
frames=[]
for view in ('eval-overview','eval-own/r1','eval-own/r2'):
 for tick in (0,60,120,190,250,310):
  path=root/'grasp-search19-repro4-gcp-06558d64/diagnostic/episode-000/raw'/view/f'{tick:06d}.jpg'
  frames.append({'view':view,'tick':tick,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
report['reviewed_frames']=frames
report['frame_review']='18 original JPEGs, first/middle/end; blue r1 and teal r2 at opposite ends; no same-end contest or peer body blocking at final alignment'
(out/'error-distribution.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['errors'],indent=2))
