"""Saved egomap22 diagnostic; no fitting, physics, or control truth."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.self_pulse_odom import PulseOdometry,MODEL_SHA256
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1')
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def audit(case):
 p=RAW/case; events=json.loads((p/'decisions.json').read_text()); commands=sorted(rows(p/'robots/r3/commands.jsonl'),key=lambda x:x['t'])
 driver=PulseOdometry(commands[0]['t']); cursor=0; prev=np.zeros(3); ancestry=np.arange(100); res=[]; stationary=[]; first_one=None; sig=[]; q=np.zeros(3)
 driver.step_callback=lambda delta,variance:np.add(q,variance,out=q)
 for e in events:
  t=e['t']
  while cursor<len(commands) and commands[cursor]['t']<t-1e-8:driver.command(commands[cursor]);cursor+=1
  driver.advance(t); pose=np.array(driver.pose)
  if e.get('matching_attempted'):
   still=np.linalg.norm(pose[:2]-prev[:2])<1e-4 and abs(np.arctan2(np.sin(pose[2]-prev[2]),np.cos(pose[2]-prev[2])))<1e-4
   stationary.append(dict(t=t,still=still,resampled=e['resampled']))
   prev=pose.copy()
  if e.get('resampled'):
   parents=np.array(e['parent_indices']);ancestry=ancestry[parents]
   res.append(dict(t=t,neff=e['neff'],parents=len(set(parents)),ancestors=len(set(ancestry))))
   if first_one is None and len(set(ancestry))==1:first_one=t
  if 'covariance' in e:sig.append(float(np.sqrt(np.linalg.eigvalsh(np.array(e['covariance'])[:2,:2]).max())))
 final=json.loads((p/'frontend-grid.json').read_text())
 diag=json.loads((ROOT/f'experiments/2026-10-07-active-wall-map/results/{case}-diagnostics.json').read_text())
 return dict(case=case,events=len(events),matches=len(stationary),resamples=len(res),stationary_matches=sum(x['still'] for x in stationary),stationary_resamples=sum(x['still'] and x['resampled'] for x in stationary),first_single_ancestor_t=first_one,last_ancestors=len(set(ancestry)),resample_events=res,sigma_xy_first=sig[0],sigma_xy_last=sig[-1],end_neff=1/np.square(final['weights']).sum(),end_unique_poses_1mm=len(np.unique(np.round(np.array(final['particle_poses'])[:,:2],3),axis=0)),command_noise_variance_sum=q.tolist(),motion_sha256=MODEL_SHA256,previous_diagnostic=diag['online_uncertainty'],hashes={name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ('decisions.json','frontend-grid.json','robots/r3/commands.jsonl')})
if __name__=='__main__':
 report={c:audit(c) for c in ['photo','speckle']}
 out=Path(__file__).resolve().parents[1]/'results/egomap22-audit.json';out.write_text(json.dumps(report,indent=2,default=lambda x:x.item())+'\n')
 for c,r in report.items():print(c,{k:v for k,v in r.items() if k not in ('resample_events','hashes','previous_diagnostic')})
