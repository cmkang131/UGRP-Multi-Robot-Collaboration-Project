import json,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import *
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
root=parser.parse_args().root;raw=OUTPUTS/RUNS[1051]
assert not (root/'miss-cause.json').exists()
r=read(raw/'student_record.json');truth=rows(raw/'eval_only/trajectory.jsonl');ts=np.array([q['t'] for q in truth]);gt=np.array([q['robot_xyz_m'][:2]+[q['robot_yaw_rad']] for q in truth]);gt[:,2]=np.unwrap(gt[:,2])
def actual(t):return np.array([np.interp(t,ts,gt[:,j]) for j in range(3)])
poses=r['poses'];et=np.array([p['t_est'] for p in poses]);est=np.array([[p['x'],p['y'],p['yaw']] for p in poses]);errors=est-np.array([actual(t) for t in et]);errors[:,2]=np.arctan2(np.sin(errors[:,2]),np.cos(errors[:,2]))
lo,hi=81.85,204.45
contacts=rows(raw/'eval_only/wall-contacts.jsonl');nonempty=[q for q in contacts if lo<=q['t']<=hi and any(c['normal_force_n']>0 for c in q['contacts'])]
updates=[];total=np.zeros(3);last=None
for i,p in enumerate(poses):
 if i and p['last_fix_t']!=poses[i-1]['last_fix_t'] and lo<=p['t_est']<=hi:
  delta=errors[i]-errors[i-1];total+=delta
  updates.append(dict(t=p['t_est'],fix_t=p['last_fix_t'],error_before=errors[i-1].tolist(),error_after=errors[i].tolist(),error_change=delta.tolist()))
indices=[int(np.argmin(abs(et-t))) for t in (lo,170.5,178.95,186.9,187.25,194.6,204.45)]
checkpoints=[dict(t=float(et[i]),pose=est[i].tolist(),gt=actual(et[i]).tolist(),error=errors[i].tolist(),std_xy=poses[i]['std_xy_m']) for i in indices]
pulses=[]
for q in r['pulse_motion_model']['transformations']:
 if not lo<=q['t']<=hi:continue
 p=r['pulse_motion_model']['model']['profiles'][q['profile_key']];a=actual(q['t']);b=actual(q['t']+p['times'][-1]);c,s=math.cos(a[2]),math.sin(a[2]);d=b-a;d[:2]=np.array([[c,s],[-s,c]])@d[:2];d[2]=wrap(d[2]);expected=np.array(p['mean_delta'])
 pulses.append(dict(t=q['t'],profile=q['profile_key'],expected=expected.tolist(),actual=d.tolist(),error=(expected-d).tolist()))
def group(pp):
 if not pp:return dict(n=0)
 e=np.array([q['error'] for q in pp]);return dict(n=len(pp),mean_error=e.mean(0).tolist(),sum_error=e.sum(0).tolist(),expected_sum=np.array([q['expected'] for q in pp]).sum(0).tolist(),actual_sum=np.array([q['actual'] for q in pp]).sum(0).tolist())
start,end=indices[0],indices[-1]
miss=read(root/'diagnosis-final/s1051-off-rows.json');miss=[q for q in miss if q['miss']]
result=dict(scope='baseline s1051 posthoc only; GT never fitted or injected',interval=[lo,hi],contact_samples=len(nonempty),checkpoints=checkpoints,updates=updates,total_error_change=(errors[end]-errors[start]).tolist(),update_error_change_sum=total.tolist(),between_update_error_change=((errors[end]-errors[start])-total).tolist(),pulse_groups={k:group([q for q in pulses if q['profile']==k]) for k in sorted(set(q['profile'] for q in pulses))},miss_interval=[min(q['t'] for q in miss),max(q['t'] for q in miss)],miss_landmark_age_range=[min(q['landmark_age_s'] for q in miss),max(q['landmark_age_s'] for q in miss)],miss_error_ranges=np.array([q['error'] for q in miss]).min(0).tolist()+np.array([q['error'] for q in miss]).max(0).tolist())
cmd=r['pulse_motion_model']['transformations'];segments=[]
for i,q in enumerate(cmd[:-1]):
 if not lo<=q['t']<=hi or q['issued'].get('forward',0)==0:continue
 a=actual(q['t']);b=actual(cmd[i+1]['t']);c,z=math.cos(a[2]),math.sin(a[2]);segments.append((np.array([[c,z],[-z,c]])@(b-a)[:2]).tolist())
result['forward_full_intercommand']=dict(n=len(segments),actual_body_xy_sum=np.array(segments).sum(0).tolist(),definition='next issued pulse boundary includes residual coasting; no intervening command')
(root/'miss-cause.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='updates'},indent=2))
