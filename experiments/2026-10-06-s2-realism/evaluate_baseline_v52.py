"""Frozen v133 descriptive cohort audit; reads completed logs only, never runtime."""
import argparse,bisect,collections,json,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import read,rows,sha,uncertain,wrap


def audit(raw):
    result=read(raw/'result.json');record=read(raw/'student_record.json');bundle=read(raw/'bundle.json')
    truth=rows(raw/'eval_only/trajectory.jsonl');tt=np.array([v['t'] for v in truth]);xy=np.array([v['robot_xyz_m'][:2] for v in truth]);yaw=np.unwrap([v['robot_yaw_rad'] for v in truth]);poses=record['poses'];pt=[v['t'] for v in poses]
    def error(p):
        t=p['t_est'];assert tt[0]<=t<=tt[-1]
        gt=np.array([np.interp(t,tt,xy[:,i]) for i in (0,1)]);e=np.array([p['x'],p['y']])-gt
        return e,dict(t=p['t'],t_est=t,estimated_xy_m=[p['x'],p['y']],truth_xy_m=gt.tolist(),xy_error_m=float(np.linalg.norm(e)),yaw_error_deg=math.degrees(wrap(p['yaw']-np.interp(t,tt,yaw))),std_xy_m=p['std_xy_m'])
    times={round(v['t'],6) for v in record['pulse_motion_model']['transformations']}
    times.update(round(e['t'],6) for e in record['events'] if e['event']=='carry_checkpoint' or (e['event']=='state' and e['state']=='search'))
    bytime={round(p['t'],6):p for p in poses};score=[]
    for t in sorted(times):
        p=bytime[t];e,q=error(p);mode=p['observation_quality'].get('diagnostics',{}).get('pose_estimate',{});cov=np.asarray(mode.get('selected_cluster_cov',[]));valid=mode.get('cluster_count')==1 and cov.shape==(3,3) and np.isclose(np.trace(cov[:2,:2]),p['std_xy_m']**2,rtol=1e-7,atol=1e-10) and np.linalg.eigvalsh(cov[:2,:2]).min()>0
        q.update(alarm=uncertain(p),nees=float(e@np.linalg.solve(cov[:2,:2],e)) if valid else None);score.append(q)
    hits=[]
    for sample in rows(raw/'eval_only/contacts.jsonl'):
        for c in sample['contacts']:
            a,b=(c[k].split('__')[0] for k in ('geom1','geom2'))
            if a in ('r1','r2','r3') and b in ('r1','r2','r3') and a!=b:hits.append(dict(t=sample['t'],**c))
    contact_times=sorted(set(c['t'] for c in hits));groups=[]
    for t in contact_times:
        if not groups or t-groups[-1][-1]>.051:groups.append([])
        groups[-1].append(t)
    episodes=[]
    for g in groups:
        before=poses[max(0,bisect.bisect_right(pt,g[0]-.05)-1)];after=poses[min(len(poses)-1,bisect.bisect_left(pt,g[-1]+.05))];one=poses[min(len(poses)-1,bisect.bisect_left(pt,g[-1]+1))]
        episodes.append(dict(first_t=g[0],last_t=g[-1],samples=len(g),points=sum(c['t'] in g for c in hits),before=error(before)[1],after=error(after)[1],after_one_second=error(one)[1]))
    wall=collections.defaultdict(list)
    for q in rows(raw/'eval_only/wall-contacts.jsonl'):
        for c in q['contacts']:
            if c['normal_force_n']>0:wall[c['category']].append(dict(t=q['t'],**c))
    walls={}
    for k,ls in sorted(wall.items()):
        ts=sorted(set(q['t'] for q in ls));walls[k]=dict(points=len(ls),samples=len(ts),episodes=sum(i==0 or t-ts[i-1]>.051 for i,t in enumerate(ts)),first_t=ts[0],last_t=ts[-1],max_normal_force_n=max(q['normal_force_n'] for q in ls))
    valid=[q for q in score if q['nees'] is not None];exceeded=sum(q['nees']>5.991464547107979 for q in valid);moving=next((q['t'] for q in record['commands'] if q['kind'] in ('mecanum','drive') and any(q.get(k,0) for k in ('forward','left','turn'))),pt[-1]);start=poses[max(0,bisect.bisect_right(pt,moving)-1)];post={k:v for k,v in result.get('posthoc_evaluation',{}).items() if k not in ('actual_visibility','update_times')}
    s=dict(seed=bundle['task']['seed'],raw=str(raw),source_sha=bundle['source_sha'],reproduction=bundle.get('reproduction'),bundle_sha256=bundle['bundle_sha256'],options=bundle['options'],status=result['status'],failure=result.get('failure'),evaluation=result['evaluation'],sim_s=result['check_sim_s'],wall_s=result['wall_s'],wall_per_sim=result['wall_per_sim'],initial_pose=error(start)[1],posthoc=post,peer_contact_points=len(hits),peer_contact_samples=len(contact_times),peer_contact_episodes=episodes,peer_pairs=sorted(set(c['geom1']+' / '+c['geom2'] for c in hits)),walls=walls,would_stop=record.get('dev_light_would_stop',{}),pose=dict(decision_rows=len(score),alarm_rows=sum(q['alarm'] for q in score),nees_available=len(valid),nees_exceeded=exceeded,nees_rate=exceeded/len(valid) if valid else None,unflagged_above_25cm=sum(not q['alarm'] and q['xy_error_m']>.25 for q in score),scope='pulse selection + carry checkpoint + search-entry decision times; XY single-cluster matching covariance only; information, not gate'),contact_failure_causality='no_failure' if result['evaluation']['success'] else ('no_robot_contact' if not hits else 'requires_posthoc_cause_review'),input_hashes={p:sha(raw/p) for p in ('result.json','student_record.json','bundle.json','eval_only/trajectory.jsonl','eval_only/contacts.jsonl','eval_only/wall-contacts.jsonl')},gt_scope='posthoc only after runtime closed',model_calls=0)
    if (raw/'lock.json').exists():s['lock']=read(raw/'lock.json')
    return s,score

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();summary,score=audit(a.raw)
    with a.output.open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
    with a.output.with_name(a.output.stem+'-pose-rows.json').open('x') as f:json.dump(score,f);f.write('\n')
    print(json.dumps({k:summary[k] for k in ('seed','evaluation','peer_contact_points','sim_s','wall_s','pose','contact_failure_causality')},indent=2))
