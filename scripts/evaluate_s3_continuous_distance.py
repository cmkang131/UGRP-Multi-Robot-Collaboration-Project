"""Post-run only: full raw hash verification and uninterrupted carry metrics."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):return json.loads(path.read_text())
def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def dist(a,b):return math.dist(a,b)


def evaluate(raw,limits):
    manifest=read(raw/'artifacts.sha256.json')
    for name,digest in manifest.items():
        with (raw/name).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=digest:
                raise ValueError('raw hash mismatch: '+name)
    b,r=read(raw/'bundle.json'),read(raw/'result.json')
    states=read(raw/'stage-states.json')
    carry=[s['t'] for s in states if all(v['state']=='carry' for v in s['robots'].values())]
    result=dict(distance_m=b['continuous_distance']['target_m'],seed=b['seed'],
        source_sha=b['source_sha'],status=r['status'],failure=r.get('failure'),
        model_calls=r['model_calls'],wall_s=r['wall_s'],sim_s=r.get('check_sim_s',0.),
        raw=str(raw.resolve()),raw_manifest_sha256=hashlib.sha256((raw/'artifacts.sha256.json').read_bytes()).hexdigest(),
        verified_files=len(manifest),all_raw_hashes_match=True,carry_entered=bool(carry),safe=False)
    if not carry:return result
    start,end=min(carry),max(carry)
    witnesses=[x for x in rows(raw/'eval_only/setdown.jsonl') if start<=x['t']<=end]
    truth=[x for x in rows(raw/'eval_only/referee_truth.jsonl') if start<=x['t']<=end]
    poses=[x for x in rows(raw/'eval_only/continuous-poses.jsonl') if start<=x['t']<=end]
    if not witnesses or not truth or not poses:raise ValueError('missing physical carry samples')
    origin=[truth[0]['items']['beam_1'][k] for k in ('x','y')]
    points=[x['items']['beam_1'] for x in truth]
    # A transient contact solver dropout is reported separately from >=200ms loss.
    loss_start={};longest={rid:0. for rid in ('r1','r2')};loss_samples={rid:0 for rid in longest}
    for x in witnesses:
        for rid in longest:
            if not all(x['fingers'][rid]):
                loss_samples[rid]+=1;loss_start.setdefault(rid,x['t'])
                longest[rid]=max(longest[rid],x['t']-loss_start[rid]+.05)
            else:loss_start.pop(rid,None)
    first=poses[0]['robots'];sync=[];yaw=[];errors={rid:[] for rid in longest};curve=[]
    for x in poses:
        pp=x['robots'];delta={rid:[pp[rid]['actual_xy_m'][i]-first[rid]['actual_xy_m'][i] for i in range(2)] for rid in longest}
        disagreement=[delta['r1'][i]-delta['r2'][i] for i in range(2)]
        drift=(pp['r1']['actual_yaw_rad']-pp['r2']['actual_yaw_rad'])-(first['r1']['actual_yaw_rad']-first['r2']['actual_yaw_rad'])
        drift=abs(math.atan2(math.sin(drift),math.cos(drift)))
        sync.append(disagreement);yaw.append(drift)
        for rid in errors:
            estimate=pp[rid]['estimated_xy_m']
            if estimate is not None and all(v is not None and math.isfinite(v) for v in estimate):
                errors[rid].append(dist(estimate,pp[rid]['actual_xy_m']))
        if len(curve)==0 or x['t']-curve[-1]['t']>=1.-1e-7:
            curve.append(dict(t=x['t'],carrier_displacement_m=delta,
                axis_error_m=disagreement,opposed_heading_drift_rad=drift,
                localization_error_m={rid:errors[rid][-1] if errors[rid] else None for rid in errors}))
    carried=max(dist([p['x'],p['y']],origin) for p in points)
    tilt=max(x['cargo_tilt_deg'] for x in witnesses)
    axis=[max(abs(v[i]) for v in sync) for i in range(2)]
    # A guard AFTER supported setdown is not a drop during the carry window.
    drop=any(x['body_origin_z_m']<=.035 for x in witnesses)
    final=r.get('final',{})
    released=set(final)=={'r1','r2'} and all(v['state'] in ('released','cp_open') and not v['failure'] for v in final.values())
    carry_completed=any(s['t']>end and all(v['state'] in
        ('wait_lower','lower','wait_open','released','cp_open') for v in s['robots'].values()) for s in states)
    drop=drop or ('LOAD_DROP' in (r.get('failure') or '') and not carry_completed)
    target=b['continuous_distance']['target_m']
    reasons=[]
    if not carry_completed:reasons.append('carry_not_completed')
    if carried<target-limits['endpoint_shortfall_m']:reasons.append('distance_shortfall')
    if drop:reasons.append('load_drop')
    if tilt>=limits['tilt_deg']:reasons.append('tilt')
    if max(longest.values())>=limits['persistent_grip_loss_s']-1e-7:reasons.append('persistent_grip_loss')
    if max(axis)>limits['axis_displacement_disagreement_m']:reasons.append('axis_disagreement')
    if max(yaw)>limits['opposed_heading_drift_rad']:reasons.append('heading_disagreement')
    result.update(carry_start_sim_s=start,carry_end_sim_s=end,actual_continuous_distance_m=carried,
        tilt_max_deg=tilt,drop=drop,grip_loss_samples=loss_samples,max_grip_loss_s=longest,
        carrier_axis_error_max_m=axis,opposed_heading_drift_max_rad=max(yaw),
        localization_error_m={rid:dict(max=max(v),final=v[-1],rms=math.sqrt(sum(z*z for z in v)/len(v))) if v else None for rid,v in errors.items()},
        samples=len(witnesses),final_release=released,carry_completed=carry_completed,
        whole_episode_completed=r['status']=='DEV_STAGE_FINISHED' and released,
        post_carry_guard_abort=(r.get('failure') if carry_completed and r.get('failure') else None),
        safe=not reasons,reasons=reasons,curve=curve)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    plan=read(Path(__file__).resolve().parents[1]/'experiments/2026-10-11-s3-continuous-distance/registration.json')
    runs=[]
    for item in plan['runs']:
        target=a.cohort/item['name']
        try:run=dict(name=item['name'],**evaluate(target/'raw',plan['eval_only_limits']))
        except Exception as e:run=dict(**item,status='HOST_ERROR',safe=False,failure=repr(e),raw=str(target/'raw'))
        run['initial_check']=read(target/'initial-check.json') if (target/'initial-check.json').exists() else None
        runs.append(run)
    groups={str(d):dict(n=3,safe=sum(r.get('safe',False) for r in runs if r['distance_m']==d),
        reached=sum(r.get('actual_continuous_distance_m',0)>=d-.020 for r in runs if r['distance_m']==d)) for d in (.85,1.5,2.5,4.)}
    accepted=[float(k) for k,v in groups.items() if v['safe']==3]
    summary=dict(schema='ugrp.s3_continuous_distance.summary.v1',host='ugrp-sim-azure',runs=runs,n=12,
        groups=groups,maximum_tested_safe_distance_m=max(accepted,default=None),
        recommended_max_continuous_distance_m=max(accepted,default=None),
        qualification='DEV synthetic alignment entrance; 3 seeds; no formal/real-robot safety guarantee',
        gt_control=False,model_calls=0)
    a.output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))


if __name__=='__main__':main()
