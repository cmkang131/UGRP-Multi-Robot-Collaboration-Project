"""Read saved PF outputs; GT used only for posthoc support/error scores."""
import json,math,pathlib,sys
import numpy as np
from harness.zone_s3_no_prior_contract import hp,old
from harness.zone_solo_cyan_landmarks import MapFeatures,landmark_likelihood,wrap
from harness.zone_solo_cyan_amcl_sensor import likelihood
from harness.zone_solo_cyan_likelihood_field import Field
B=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s3diag-20261009');OUT=pathlib.Path(__file__).parent
RAW=B.parent/'s3-no-prior-6c657124-s14201-v142'
static=hp.resolve(old.solo.MAP_ID)[0];mapped=MapFeatures(static);field=Field(static)
def read(p):return json.loads(p.read_text())
truth_rows=[json.loads(x) for x in (RAW/'eval_only/r1/trajectory.jsonl').read_text().splitlines()]
def gt(t):
 q=min(truth_rows,key=lambda x:abs(x['t']-t));return np.array([*q['robot_xyz_m'][:2],q['robot_yaw_rad']])
def score(q,px):return likelihood(field,px,q['wall_points'])*landmark_likelihood(mapped,px,q['features'])
def analyze(folder):
 p=read(folder/'packets.json');r=read(folder/'record.json');ll=read(folder/'likelihood.json');c=np.load(folder/'clouds.npz');out=[];true=gt(1.3)
 for i,l in enumerate(ll):
  q=next(z for z in p if abs(z['t']-l['t'])<1e-8);px=c[f'px_{i}'];w=c[f'w_{i}'];v=c[f'likelihood_{i}'];good=(np.linalg.norm(px[:,:2]-true[:2],axis=1)<=.25)&(abs(wrap(px[:,2]-true[2]))<=np.deg2rad(15));post=w*v;post/=post.sum();best=px[np.argmax(post)];vt=float(score(q,true[None])[0]);vb=float(score(q,best[None])[0]);out.append(dict(t=q['t'],pan=q['pose']['6'],walls=len(q['wall_points']),features=len(q['features']),n=len(px),unique_xyz=len(np.unique(px,axis=0)),correct_support=int(good.sum()),prior_mass=float(w[good].sum()),posterior_mass=float(post[good].sum()),best=best.tolist(),best_to_true_score=vb/vt,true_score=vt,best_score=vb))
 last=r['poses'][-1];true=gt(last['t_est']);error=float(np.linalg.norm(np.array([last['x'],last['y']])-true[:2]));yaw=float(np.rad2deg(abs(wrap(last['yaw']-true[2]))));convs=[]
 for z in r['poses']:
  if z['std_xy_m']<=.05 and z['std_yaw_rad']<=np.deg2rad(5):
   t=gt(z['t_est']);convs.append(dict(t=z['t'],error_m=float(np.linalg.norm(np.array([z['x'],z['y']])-t[:2])),yaw_error_deg=float(np.rad2deg(abs(wrap(z['yaw']-t[2]))))));break
 # Offline likelihood ratios at exact truth vs the final selected false mode: no update.
 candidates=np.array([gt(1.3),[last['x'],last['y'],last['yaw']]])
 ratios=[float(score(q,candidates)[1]/score(q,candidates)[0]) for q in p]
 return dict(folder=str(folder),receipt=read(folder/'receipt.json'),observations=out,last=dict(t=last['t'],error_m=error,yaw_error_deg=yaw,std_xy_m=last['std_xy_m'],std_yaw_rad=last['std_yaw_rad']),first_convergence=convs,final_mode_vs_truth_likelihood_ratios=ratios,combined_ratio=float(np.prod(ratios)),gt_use='eval_only; never replay input')
folders=[B/'camera-corrected-full-r1']+[pathlib.Path(x) for x in sys.argv[1:]]
results={x.name:analyze(x) for x in folders};(OUT/'r1-support-analysis.json').write_text(json.dumps(results,indent=2)+'\n')
for name,r in results.items():
 print(name,r['last'],'first',r['first_convergence']);print('support',[(round(z['t'],2),z['correct_support'],round(z['prior_mass'],8),round(z['posterior_mass'],8),round(z['best_to_true_score'],2)) for z in r['observations']]);print('mode/truth',r['final_mode_vs_truth_likelihood_ratios'],r['combined_ratio'])
