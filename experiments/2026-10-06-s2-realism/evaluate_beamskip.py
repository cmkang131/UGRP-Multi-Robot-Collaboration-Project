"""Post-seal GT evaluation only. Never imported by the replay/controller."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from replay_beamskip import RUNS, read, rows, sha, posterior, HERE
from scripts.audit_s2_formal_stops import uncertain

CHI2 = 5.991464547107979


def dist(values):
    return dict(zip(('min','median','max'),map(float,np.quantile(values,[0,.5,1])))) if len(values) else None


def near(px, gt, radius=.1):
    angle=np.arctan2(np.sin(px[:,2]-gt[2]),np.cos(px[:,2]-gt[2]))
    return (np.linalg.norm(px[:,:2]-gt[:2],axis=1)<=radius)&(abs(angle)<=np.deg2rad(5))


def line_match(mapped, feature, pose):
    """Evaluation-only ML correspondence with the exact existing feature geometry."""
    if feature['kind']!='floor_line':return None
    from harness.zone_solo_cyan_landmarks import gaussian,wrap,PARAMS
    co,si=np.cos(pose[2]),np.sin(pose[2]);rot=np.array([[co,-si],[si,co]])
    world=np.array(feature['endpoints'])@rot.T+pose[:2]
    angle=pose[2]+np.arctan2(feature['normal'][1],feature['normal'][0]);matches=[]
    for index,edge in enumerate(mapped.edges):
        hd=abs(edge['hue']-feature['hue']);hd=min(hd,180-hd)
        if hd>PARAMS['hue_tolerance']:continue
        vec=edge['b']-edge['a'];frac=np.clip((world-edge['a'])@vec/(vec@vec),0,1)
        closest=edge['a']+frac[:,None]*vec
        distance=float(np.sqrt(np.mean(np.sum((world-closest)**2,axis=1))))
        da=float(wrap(angle-np.arctan2(edge['normal'][1],edge['normal'][0])))
        matches.append(dict(region=edge['region'],edge=index,distance_m=distance,angle_deg=float(np.rad2deg(da)),
            density=float(gaussian(distance,.1)*gaussian(da,PARAMS['sigma_line_angle_rad'])),
            world_endpoints=world.tolist(),map_endpoints=[edge['a'].tolist(),edge['b'].tolist()]))
    return max(matches,key=lambda q:q['density']) if matches else None


def cloud_metrics(px,w,gt):
    mean=w@px[:,:2];d=px[:,:2]-mean;cov=(d*w[:,None]).T@d;e=mean-gt[:2]
    valid=np.linalg.eigvalsh(cov).min()>0
    return dict(mass_10cm_5deg=float(w[near(px,gt)].sum()),mass_25cm_5deg=float(w[near(px,gt,.25)].sum()),
        count_10cm_5deg=int(near(px,gt).sum()),ess=float(1/(w@w)),
        mean_xy=mean.tolist(),mean_xy_error_m=float(np.linalg.norm(e)),
        covariance_xy=cov.tolist(),nees_xy=float(e@np.linalg.solve(cov,e)) if valid else None,
        expected_xy_error_m=float(w@np.linalg.norm(px[:,:2]-gt[:2],axis=1)),
        unique=len(np.unique(px,axis=0)))


def evaluate(folder):
    prediction=read(folder/'prediction.json');assert not prediction['partial']
    seed=prediction['seed'];raw=RUNS[seed];record=read(raw/'student_record.json')
    tr=rows(raw/'eval_only/trajectory.jsonl');ts=np.array([q['t'] for q in tr])
    xyz=np.array([q['robot_xyz_m'][:2] for q in tr]);yaw=np.unwrap([q['robot_yaw_rad'] for q in tr])
    def gt(t):
        if not ts[0]-1e-9<=t<=ts[-1]+1e-9:raise ValueError('truth interpolation outside trajectory')
        return np.array([*(np.interp(t,ts,xyz[:,j]) for j in (0,1)),np.interp(t,ts,yaw)])
    begin=next(q['t'] for q in record['events'] if q.get('state')=='carry' and q['event']=='state')
    end=next(q['t'] for q in record['events'] if q.get('state')=='real_carry_return' and q['event']=='state')
    poses=prediction['poses'];bytime={round(q['t'],6):q for q in poses}
    if seed>=1059:times=sorted(set(round(q['t'],6) for q in record['global_full_decisions']))
    else:
        times={round(q['t'],6) for q in record['pulse_motion_model']['transformations']}
        times.update(round(q['t'],6) for q in record['events'] if q['event']=='carry_checkpoint' or
                     (q['event']=='state' and q['state']=='search'))
        times=sorted(times)
    decisions=[]
    for t in times:
        p=bytime[t];e=np.array([p['x'],p['y']])-gt(p['t_est'])[:2];cov=np.array(p['cov'])[:2,:2]
        valid=cov.shape==(2,2) and np.isfinite(cov).all() and np.linalg.eigvalsh(cov).min()>0
        decisions.append(dict(t=t,t_est=p['t_est'],xy_error_m=float(np.linalg.norm(e)),
            alarm=uncertain(p),nees_xy=float(e@np.linalg.solve(cov,e)) if valid else None))
    carry=[p for p in poses if begin<=p['t']<=end]
    errors=[np.linalg.norm(np.array([p['x'],p['y']])-gt(p['t_est'])[:2]) for p in carry]
    samples=[];measurements=[]
    from harness.zone_solo_cyan_landmarks import MapFeatures,Measurement
    from harness.zone_solo_cyan_likelihood_field import Field
    from harness import zone_solo_cyan_contract_v106 as contract
    static=contract.hp.resolve(contract.MAP_ID)[0];field=Field(static);mapped=MapFeatures(static)
    with np.load(folder/'clouds.npz') as clouds:
        for q in prediction['periodic']:
            if begin<=q['t']<=end:
                m=cloud_metrics(clouds[q['key']],clouds[q['key']+'w'],gt(q['t']))
                samples.append(dict(t=q['t'],**m))
        for q in prediction['measurements']:
            key=q['key'];px=clouds[key+'p'];w=clouds[key+'w'];parts=clouds[key+'f'];ll=clouds[key+'l'];truth=gt(q['t'])
            before=cloud_metrics(px,w,truth);post=posterior(w,ll)
            after=cloud_metrics(px,post,truth);resampled=cloud_metrics(clouds[key+'after'],clouds[key+'aw'],truth)
            active_parts=clouds[key+'active']
            assert np.allclose(active_parts.sum(0),ll,rtol=1e-12,atol=1e-12)
            components=[]
            # Active single-factor counterfactuals on this same prior; no
            # re-running prediction and no arbitrary ordered attribution.
            for i,llpart in enumerate(active_parts):
                one=posterior(w,llpart);without=posterior(w,active_parts.sum(0)-llpart)
                components.append(dict(kind='wall' if i==0 else q['features'][i-1]['kind'],index=i,
                    log_factor_range=[float(llpart.min()),float(llpart.max())],
                    score_ratio=float(np.exp(min(700.,np.ptp(llpart)))),
                    alone=cloud_metrics(px,one,truth),without=cloud_metrics(px,without,truth)))
            best=int(np.argmax(active_parts.sum(0)));mass=near(px,truth)
            # Per-factor mean log contrast, best-scoring available particle vs
            # current near-truth prior. Missing truth support stays unknown.
            contrast=(active_parts[:,best]-active_parts[:,mass]@(w[mass]/w[mass].sum())).tolist() if mass.any() and w[mass].sum()>0 else None
            geometry=[dict(index=i+1,truth_match=line_match(mapped,f,truth),best_match=line_match(mapped,f,px[best]))
                      for i,f in enumerate(q['features'])]
            measurements.append(dict(**q,truth=truth.tolist(),prior=before,posterior=after,after_resampling=resampled,
                components=components,best_pose=px[best].tolist(),best_vs_near_log_contrast=contrast,
                feature_geometry=geometry,
                attribution='active single-factor / leave-one-out counterfactual on same particles; not additive causal effects'))
    valid=[q['nees_xy'] for q in decisions if q['nees_xy'] is not None]
    mass=[q['mass_10cm_5deg'] for q in samples]
    counts=Counter(f['kind'] for q in measurements for f in q['features'])
    summary=dict(seed=seed,option=prediction['option'],raw=str(raw),carry_interval=[begin,end],
        carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),carry_end_xy_m=float(errors[-1]),
        nees_exceed_fraction=sum(v>CHI2 for v in valid)/len(valid) if valid else None,
        nees_valid=len(valid),decision_count=len(decisions),
        unflagged_gt_25cm=sum(not q['alarm'] and q['xy_error_m']>.25 for q in decisions),
        alarm_count=sum(q['alarm'] for q in decisions),
        near_truth_support_fraction=float(np.mean(np.array(mass)>0)),near_truth_median_mass=float(np.median(mass)),
        near_truth_mean_mass=float(np.mean(mass)),particle_snapshots=len(samples),
        measurement_count=len(measurements),actual_resamples=sum(q['resampled'] for q in measurements),
        feature_counts=dict(counts),feature_count_per_update=dict(Counter(str(len(q['features'])) for q in measurements)),
        legacy_score_ratio=dist([q['legacy_score_ratio'] for q in measurements]),
        active_score_ratio=dist([q['active_score_ratio'] for q in measurements]),
        posterior_ess_fraction=dist([q['posterior_ess']/q['particle_count'] for q in measurements]),
        baseline_recorded_pose_bytes_equal=prediction['pose_fields_sha256']==prediction['recorded_pose_fields_sha256'],
        source_sha=prediction['source_sha'],prediction_hash=sha(folder/'prediction.json'),clouds_hash=sha(folder/'clouds.npz'),
        gt_hash=sha(raw/'eval_only/trajectory.jsonl'),physics_runs=0,gt_use='sealed prediction evaluation only')
    out=dict(summary=summary,decisions=decisions,particle_time_series=samples,measurement_time_series=measurements)
    (folder/'evaluation.json').write_text(json.dumps(out)+'\n')
    print(json.dumps(summary),flush=True)
    return out


def compare(base,on,criteria):
    a,b=base['summary'],on['summary'];eps=criteria['evaluation']['floating_tolerance']
    checks=dict(nees=b['nees_exceed_fraction'] is not None and b['nees_exceed_fraction']<=.2,
        coverage=b['nees_valid']==b['decision_count'],unflagged=b['unflagged_gt_25cm']==0,
        carry_rmse=b['carry_rmse_m']<=a['carry_rmse_m']+eps,
        support=b['near_truth_support_fraction']+eps>=a['near_truth_support_fraction'],
        mass=b['near_truth_median_mass']+eps>=a['near_truth_median_mass'],
        baseline_bytes=a['baseline_recorded_pose_bytes_equal'])
    return dict(seed=a['seed'],baseline=a,on=b,checks=checks,passed=all(checks.values()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);args=p.parse_args()
    criteria=read(HERE/'sensor-consistency-criteria.json');comparisons=[]
    for seed in criteria['seeds']:
        base=args.baseline/f's{seed}-baseline'
        a=read(base/'evaluation.json')
        assert sha(base/'prediction.json')==a['summary']['prediction_hash']
        assert sha(base/'clouds.npz')==a['summary']['clouds_hash']
        sealed=read(base/'prediction.json')
        for key,value in sealed['input_hashes'].items():assert sha(RUNS[seed]/key)==value
        b=evaluate(args.output/f's{seed}-on')
        comparisons.append(compare(a,b,criteria))
    base=read(args.baseline/'s1060-baseline/prediction.json')
    off=read(args.output/'s1060-off/prediction.json')
    equality={k:base[k]==off[k] for k in ('particle_sha256','pose_fields_sha256')}
    assert all(equality.values())
    result=dict(schema='ugrp.s2.beamskip.result.v1',comparisons=comparisons,
        passed=all(q['passed'] for q in comparisons),physics_runs=0,threshold_changes=0,
        off_equivalence=dict(seed=1060,**equality,frame_count=len(off['poses']),max_delta=off['max_delta']),
        criteria_hash=sha(HERE/'sensor-consistency-criteria.json'),raw=str(args.output),
        baseline_root=str(args.baseline),baseline_reuse='sealed hashes and original input hashes verified')
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
