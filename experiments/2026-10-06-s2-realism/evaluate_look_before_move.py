import argparse,json,hashlib,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import read,rows,sha,uncertain,truth_at

p=argparse.ArgumentParser();p.add_argument('raw',type=Path);a=p.parse_args();raw=a.raw
result=read(raw/'result.json');r=read(raw/'student_record.json');truth=rows(raw/'eval_only/trajectory.jsonl')
look=r['look_before_move'];pt={round(p['t'],6):p for p in r['poses']}
# Actual command opportunities including blocked proposals, not duplicated 20Hz frames.
times=set(round(q['t'],6) for q in r['pulse_motion_model']['transformations'])
times.update(round(q['t'],6) for q in look.get('detour_commands',[]))
times.update(round(q['t'],6) for q in look['checks'])
score=[];unavailable=[];no_pose=[]
for t in sorted(times):
 if t not in pt:no_pose.append(t);continue
 q=pt[t];gt=truth_at(truth,q['t_est']);e=np.array([q['x']-gt[0],q['y']-gt[1]])
 mode=q['observation_quality'].get('diagnostics',{}).get('pose_estimate',{});cov=np.asarray(mode.get('selected_cluster_cov',[]))
 valid=(mode.get('cluster_count')==1 and cov.shape==(3,3) and np.isclose(np.trace(cov[:2,:2]),q['std_xy_m']**2,rtol=1e-7,atol=1e-10) and np.linalg.eigvalsh(cov[:2,:2]).min()>0)
 nees=float(e@np.linalg.solve(cov[:2,:2],e)) if valid else None
 if not valid:unavailable.append(t)
 score.append(dict(t=t,error_m=float(np.linalg.norm(e)),alarm=uncertain(q),nees=nees))
contacts=[]
for s in rows(raw/'eval_only/contacts.jsonl'):
 for c in s['contacts']:
  u,v=(c[k].split('__')[0] for k in ('geom1','geom2'))
  if u in ('r1','r2','r3') and v in ('r1','r2','r3') and u!=v:contacts.append(dict(t=s['t'],**c))
peert=sorted(set(q['t'] for q in contacts));episodes=sum(i==0 or t-peert[i-1]>.051 for i,t in enumerate(peert))
valid=[q for q in score if q['nees'] is not None];exceed=sum(q['nees']>5.991464547107979 for q in valid)
miss=sum(not q['alarm'] and q['error_m']>.25 for q in score)
old=read(Path('/Users/changmin/projects/ugrp/outputs/s2-realism-027c567c-s1054-v133-reproduction/result.json'))
post=result.get('posthoc_evaluation',{})
summary=dict(raw=str(raw),seed=result['seed'],source_sha=read(raw/'bundle.json')['source_sha'],status=result['status'],failure=result.get('failure'),evaluation=result.get('evaluation'),posthoc=post,
wall_s=result['wall_s'],sim_s=result['check_sim_s'],wall_per_sim=result['wall_per_sim'],duration_delta_vs_old1054_sim_s=result['check_sim_s']-old['check_sim_s'],duration_delta_vs_old1054_wall_s=result['wall_s']-old['wall_s'],time_comparison='same seed1054 paired only;1055 unpaired descriptive',
peer_contact_points=len(contacts),peer_contact_samples=len(peert),peer_contact_episodes=episodes,peer_contacts=contacts,
look={k:v for k,v in look.items() if k not in ('checks','scans','detour_commands')},scan_count=len(look['scans']),
actual_lateral_commands=sum(c['kind'] in ('drive','mecanum') and bool(c.get('left',0)) for c in r['commands']),
would_stop=r.get('dev_light_would_stop',{}),pose=dict(opportunities=len(times),rows=len(score),missing_pose=no_pose,nees_available=len(valid),nees_exceeded=exceed,nees_rate=exceed/len(valid) if valid else None,unflagged_above_25cm=miss,unavailable_covariance=unavailable),
GT='posthoc only, after runtime close',physical_runs=1,model_calls=0,lock=read(raw/'lock.json'))
summary['criteria_pass']=dict(peer_contact_zero=not contacts,success=all(result.get('evaluation',{}).get(k) for k in ('lifted','inside','stable')),nees=bool(valid) and exceed/len(valid)<=.2,unflagged=miss==0)
summary['input_hashes']={n:sha(raw/n) for n in ('result.json','student_record.json','bundle.json','eval_only/trajectory.jsonl','eval_only/contacts.jsonl')}
(raw/'look-before-move-posthoc.json').write_text(json.dumps(summary,indent=2)+'\n')
(raw/'look-before-move-pose-rows.json').write_text(json.dumps(score)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('peer_contacts','posthoc','input_hashes','lock')},indent=2))
