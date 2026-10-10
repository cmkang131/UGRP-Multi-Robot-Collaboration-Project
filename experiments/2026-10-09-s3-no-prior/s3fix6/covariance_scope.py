"""Audit which saved covariance the published S3 sigma describes; no truth."""
import argparse,hashlib,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--replays',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
rows=[];sources={}
for case in ('v149','v150'):
 path=a.replays/(case+'-off')/'state.json';sources[str(path.resolve())]=hashlib.sha256(path.read_bytes()).hexdigest()
 for rid,loc in json.loads(path.read_text()).items():
  poses=[p for p in loc['poses'] if p['t_est']>=13.34-1e-8];present=matches=0;examples=[]
  for pose in poses:
   cov=pose.get('observation_quality',{}).get('diagnostics',{}).get('pose_estimate',{}).get('selected_cluster_cov')
   if cov is None:continue
   present+=1;selected=math.sqrt(cov[0][0]+cov[1][1]);same=math.isclose(selected,pose['std_xy_m'],rel_tol=1e-8,abs_tol=1e-10);matches+=same
   if not same and len(examples)<2:examples.append(dict(t_est=pose['t_est'],reported_sigma_m=pose['std_xy_m'],selected_cluster_sigma_m=selected))
  rows.append(dict(case=case,robot=rid,frames=len(poses),selected_cov_present=present,selected_trace_matches_report=matches,mismatch_examples=examples))
source=Path('harness/zone_solo_cyan_best_cluster.py')
result=dict(gt_read=False,selection_rule_changed=False,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),input_sha256=sources,rows=rows,
 conclusion='Published sigma is sqrt(trace(overall XY covariance)); the per-frame selected_cluster_cov is different. Full matching per-frame XY covariance is not retained in the replay pose records. Do not substitute the selected-cluster matrix into full-stream NEES.')
with a.output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(rows=len(rows),output=str(a.output))))
