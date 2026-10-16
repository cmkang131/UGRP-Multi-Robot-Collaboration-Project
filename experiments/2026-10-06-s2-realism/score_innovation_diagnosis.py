"""Evaluation-only attribution of already sealed v45 approach predictions."""
import importlib.util,json
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,truth_at,wrap,sha
from harness.zone_solo_cyan_contract_v106 import hp,MAP_ID
from harness.zone_solo_cyan_landmarks import MapFeatures
HERE=Path(__file__).resolve().parent
ROOT=OUTPUTS/'s2-innovation-v46-20261008'


def main():
    mapped=MapFeatures(hp.resolve(MAP_ID)[0]);result=dict(gt_use='evaluation only after own-input audit sealed',runs=[])
    for seed in RUNS:
        raw=OUTPUTS/RUNS[seed];record=read(raw/'student_record.json');tr=rows(raw/'eval_only/trajectory.jsonl')
        audit=read(ROOT/'diagnosis'/f's{seed}-audit.json');updates=[];previous=None
        for obs,q in zip(audit['observations'],audit['measurements']):
            assert obs['t']==q['t'];t=q['t'];gt=np.array(truth_at(tr,t));c,s=np.cos(gt[2]),np.sin(gt[2]);rot=np.array([[c,-s],[s,c]])
            means={k:np.array(q[k]['mean']) for k in ('prior','posterior','resampled')}
            row=dict(t=t,gt_pose=gt.tolist(),prior_error=(means['prior']-gt).tolist(),posterior_error=(means['posterior']-gt).tolist(),
                prediction_error_delta=None if previous is None else (means['prior']-previous[1]-(gt-previous[0])).tolist(),
                observation_delta=(means['posterior']-means['prior']).tolist(),resample_delta=(means['resampled']-means['posterior']).tolist(),
                wall_shapley_xy=obs['shapley_xy'][0],features=[])
            for f,contribution in zip(obs['features'],obs['shapley_xy'][1:]):
                assert f['kind']=='floor_line' # all measured approach features in frozen recordings
                world=np.array(f['endpoints'])@rot.T+gt[:2];normal=np.array(f['normal'])@rot.T;matches=[]
                for e in mapped.edges:
                    hd=abs(e['hue']-f['hue'])
                    if min(hd,180-hd)>12:continue
                    vec=e['b']-e['a'];u=np.clip((world-e['a'])@vec/(vec@vec),0,1)
                    distance=float(np.sqrt(np.mean(np.sum((world-e['a']-u[:,None]*vec)**2,axis=1))))
                    angle=float(np.arccos(np.clip(normal@e['normal'],-1,1)))
                    matches.append((distance**2/.1**2+angle**2/np.deg2rad(5)**2,distance,angle,e))
                _,dist,angle,e=min(matches,key=lambda x:x[0])
                row['features'].append(dict(**f,shapley_xy=contribution,eval_world_endpoints=world.tolist(),
                    eval_ml_region=e['region'],eval_ml_edge=[e['a'].tolist(),e['b'].tolist()],eval_distance_m=dist,eval_angle_deg=np.degrees(angle)))
            previous=(gt,means['resampled']);updates.append(row)
        end=next(e['t'] for e in record['events'] if e.get('state')=='carry');pulse_groups={};pulse_rows=[]
        contacts=rows(raw/'eval_only/contacts.jsonl')
        for q in record['pulse_motion_model']['transformations']:
            if q['t']>=end:continue
            p=record['pulse_motion_model']['model']['profiles'][q['profile_key']];t=q['t'];finish=t+p['times'][-1]
            a,b=(np.array(truth_at(tr,z)) for z in (t,finish));c,s=np.cos(a[2]),np.sin(a[2]);dxy=(b[:2]-a[:2])@np.array([[c,-s],[s,c]])
            actual=np.r_[dxy,wrap(b[2]-a[2])];error=np.array(p['mean_delta'])-actual
            hits=[]
            for contact in contacts:
                if not t<=contact['t']<=finish:continue
                for v in contact['contacts']:
                    if 'floor' not in (v['geom1'],v['geom2']):hits.append(dict(t=contact['t'],**v))
            row=dict(t=t,end=finish,key=q['profile_key'],actual_delta=actual.tolist(),model_delta=p['mean_delta'],prediction_error=error.tolist(),nonfloor_contacts=hits)
            pulse_rows.append(row);pulse_groups.setdefault(q['profile_key'],[]).append(row)
        groups={key:dict(n=len(qs),mean_prediction_error=np.mean([q['prediction_error'] for q in qs],axis=0).tolist(),
            yaw_error_sum_deg=float(np.degrees(sum(q['prediction_error'][2] for q in qs)))) for key,qs in pulse_groups.items()}
        result['runs'].append(dict(seed=seed,updates=updates,pulse_groups=groups,pulses=pulse_rows,
            off_pose_bytes_identical=audit['off_pose_bytes_identical'],hashes={n:sha(raw/n) for n in ('student_record.json','eval_only/trajectory.jsonl','eval_only/contacts.jsonl')}))
    (ROOT/'diagnosis-result.json').write_text(json.dumps(result,indent=2)+'\n')
    # Compact tracked record; full per-pulse contacts stay in outputs.
    compact=json.loads(json.dumps(result))
    for run in compact['runs']:
        run['pulses']=[p for p in run['pulses'] if p['nonfloor_contacts']]
        for p in run['pulses']:
            hits=p.pop('nonfloor_contacts');p['contact_count']=len(hits);p['contact_times']=sorted(set(h['t'] for h in hits));p['pairs']=sorted(set(h['geom1']+' / '+h['geom2'] for h in hits))
    compact['raw']=str(ROOT/'diagnosis-result.json');compact['raw_sha256']=sha(ROOT/'diagnosis-result.json')
    (HERE/'innovation-diagnosis.json').write_text(json.dumps(compact,indent=2)+'\n')
    print([(r['seed'],len(r['updates']),[(p['t'],p['contact_count']) for p in r['pulses']]) for r in compact['runs']])

if __name__=='__main__':main()
