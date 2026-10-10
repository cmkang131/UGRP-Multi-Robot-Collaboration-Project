"""Post-run particle and conditional-covariance audit; no control input."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--replays',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
rows={};sources={}
for option in ['off','ess_v1','roughen_v1','roughen_floor_v1']:
 for case in ['55001','55002','v149','v150']:
  root=a.replays/(case+'-'+option)
  path=root/('result.json' if case.startswith('550') else 'recovered-student-record.json')
  d=json.loads(path.read_text());sources[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
  audits={'r3':d.get('audit',{})} if case.startswith('550') else {r:v.get('resampling_diversity',{}) for r,v in d['localizers'].items()}
  for rid,audit in audits.items():
   q=audit.get('rows',[]);record=dict(recorded_updates=len(q),baseline_internal_cloud_unavailable=option=='off')
   if q:
    record.update(resampled=sum(x['resampled'] for x in q),ess_skipped=sum(not x['resampled'] for x in q),floored=sum(x.get('floored',False) for x in q),proposal_floor_calls=audit.get('proposal_floors'),zero_roughening_events=sum(x.get('roughening_sigma') is not None and max(x['roughening_sigma'])==0 for x in q))
    for side in ['before','after']:
     e=np.array([x[side]['eigenvalues'][0] for x in q]);u=np.array([x[side]['unique'] for x in q]);ess=np.array([x[side]['ess'] for x in q])
     xy_e=np.linalg.eigvalsh(np.asarray([x[side]['covariance'] for x in q])[:,:2,:2])[:,0]
     record[side]=dict(min_xy_cloud_cov_eigenvalue_m2=float(xy_e.min()),median_xy_cloud_cov_eigenvalue_m2=float(np.median(xy_e)),min_cloud_cov_eigenvalue=float(e.min()),median_cloud_cov_eigenvalue=float(np.median(e)),min_unique=int(u.min()),median_unique=float(np.median(u)),min_ess=float(ess.min()),median_ess=float(np.median(ess)))
    if any('conditional_min_eigenvalue' in x for x in q):record['min_conditional_cov_eigenvalue']=min(x['conditional_min_eigenvalue'] for x in q)
   if case.startswith('550'):
    poses=[json.loads(s) for s in (root/'frontend-covariances.jsonl').read_text().splitlines()]
    e=np.linalg.eigvalsh(np.array([p['covariance'] for p in poses]))[:,0]
    record['published_covariance']=dict(min_eigenvalue=float(e.min()),median_min_eigenvalue=float(np.median(e)),frames_at_1e_10=int((e<=1.000001e-10).sum()),frames=len(e))
   rows[case+'/'+rid+'/'+option]=record
v=dict(schema='ugrp.pf_diversity_eval.v1',gt_read=False,selection_rule_changed=False,rows=rows,source_sha256=sources,scope='Audit before/after each candidate update. These are candidate internal clouds, not counterfactual baseline clouds; baseline full reported covariance only for own-map. XYZ units are XY metres and yaw radians.')
with a.output.open('x') as f:f.write(json.dumps(v,indent=2,allow_nan=False)+'\n')
