"""Post-seal correspondence/particle audit; truth only in this evaluator."""
from replay import *
from collections import Counter
from harness.active_wall_mapping import inverse


def segment_dist(points,a,b):
    vec=b-a
    closest=a+np.clip((points-a)@vec/(vec@vec),0,1)[:,None]*vec
    return float(np.sqrt(np.mean(np.sum((points-closest)**2,axis=1))))


def region_of(points,edges):
    scores=[segment_dist(np.asarray(points),e['a'],e['b']) for e in edges]
    i=int(np.argmin(scores))
    return dict(region=edges[i]['region'] if scores[i]<=.15 else 'not_static_floor_edge',nearest=edges[i]['region'],distance_m=scores[i])


def associations():
    prepared=load(CACHE/'prepared.json')
    assert prepared['cuts'][0]['own_goal'] is None
    inputs={r['frame_id']:r for r in load(CACHE/'own-inputs.json')}
    truth={round(r['t'],6):r for r in rows(EP/'eval_only/trajectory.jsonl')}
    origin=[*truth[min(truth)]['robot_xyz_m'][:2],truth[min(truth)]['robot_yaw_rad']]
    true_pose=lambda t:np.array([*truth[round(t,6)]['robot_xyz_m'][:2],truth[round(t,6)]['robot_yaw_rad']])
    static=lm.MapFeatures(load(EP/'inputs/static_map.json'))
    mapped=landmark_object(load(CACHE/'maps/own-0-landmarks.json'))
    # Evaluate each remembered partial feature at its original acquisition pose.
    labels=[]
    for e in mapped.edges:
        source=e['source']
        local=transform([e['a'],e['b']],inverse(source['pose']))
        labels.append(region_of(transform(local,true_pose(source['t'])),static.edges))
    records=[]; summaries=[]
    for mode,root in [('off',CACHE),('tempered',RAW)]:
        pred=load(root/('own-on-0.json' if mode=='off' else 'own-tempered-0.json'))
        own=pred['rows'];gt=np.array([true_pose(r['t']) for r in own]);est=np.array([r['pose'] for r in own])
        world=transform(est[:,:2],origin);err=np.linalg.norm(world-gt[:,:2],axis=1)
        yaw=abs(lm.wrap(est[:,2]+origin[2]-gt[:,2]));correct=(err<=.25)&(yaw<=math.radians(10))
        local_rows=[]
        for j,r in enumerate(own):
            if not r['updated']:continue
            false=bool(r['stable_resolved'] and not correct[max(0,j-4):j+1].all())
            for fi,f in enumerate(inputs[r['frame_id']]['features']):
                if f['kind']!='floor_line':continue
                point=transform(f['endpoints'],r['pose']);angle=r['pose'][2]+math.atan2(f['normal'][1],f['normal'][0])
                candidates=[]
                for k,e in enumerate(mapped.edges):
                    hd=abs(e['hue']-f['hue']);hd=min(hd,180-hd)
                    if hd>lm.PARAMS['hue_tolerance']:continue
                    distance=segment_dist(point,e['a'],e['b'])
                    da=float(lm.wrap(angle-math.atan2(e['normal'][1],e['normal'][0])))
                    score=float(lm.gaussian(distance,lm.PARAMS['sigma_line_m'])*lm.gaussian(da,lm.PARAMS['sigma_line_angle_rad']))
                    candidates.append((score,k,distance,da))
                if not candidates:continue
                score,k,distance,da=max(candidates)
                actual=region_of(transform(f['endpoints'],true_pose(r['t'])),static.edges)
                source=labels[k]
                item=dict(mode=mode,t=r['t'],frame_id=r['frame_id'],feature=fi,hue=f['hue'],
                    false_stable=false,pose_error_m=float(err[j]),matched_index=k,matched_source=mapped.edges[k]['source'],
                    predicted_match_distance_m=distance,predicted_match_angle_deg=math.degrees(da),match_score=score,
                    current_truth=actual,source_truth=source,
                    known_region_mismatch=actual['region']!='not_static_floor_edge' and source['region']!='not_static_floor_edge' and actual['region']!=source['region'])
                local_rows.append(item)
        sensor=[r['sensor'] for r in own if r['updated']]
        summaries.append(dict(mode=mode,updated_frames=len(sensor),resamples=sum(r['resampled'] for r in sensor),
            posterior_ess_min=min(r['ess'] for r in sensor),posterior_ess_median=float(np.median([r['ess'] for r in sensor])),
            correspondences=len(local_rows),current_regions=dict(Counter(r['current_truth']['region'] for r in local_rows)),
            associated_regions=dict(Counter(r['source_truth']['region'] for r in local_rows)),
            known_region_mismatch=sum(r['known_region_mismatch'] for r in local_rows),
            false_stable_correspondences=sum(r['false_stable'] for r in local_rows),
            false_stable_region_mismatch=sum(r['known_region_mismatch'] and r['false_stable'] for r in local_rows),
            current_B=sum(r['current_truth']['region']=='zone_B' for r in local_rows),
            current_B_to_other=sum(r['current_truth']['region']=='zone_B' and r['source_truth']['region']!='zone_B' for r in local_rows)))
        records.extend(local_rows)
    audit=load(RAW/'audit-own-0.json');resampled=[r for r in audit if 'resampled' in r]
    summary=dict(own60_B_confirmed_before_loss=False,remembered_edges=len(labels),
        remembered_edge_actual_regions=dict(Counter(r['region'] for r in labels)),rows=summaries,
        tempered_unique_after_resample_min=min(r['resampled']['unique_poses'] for r in resampled),
        tempered_resample_median_unique_fraction=float(np.median([r['resampled']['unique_poses']/next(x['n'] for x in load(RAW/'own-tempered-0.json')['rows'] if x['t']==r['t']) for r in resampled])),
        first_tempered_update=audit[0],evaluation_tolerance_m=.15,
        caution='Region attribution uses evaluation geometry and 0.15m matching only. Not a semantic label or runtime filter; cannot prove single causal mechanism.',
        evidence_sha256={str(p):sha(p) for p in [CACHE/'own-on-0.json',RAW/'own-tempered-0.json',CACHE/'own-inputs.json',CACHE/'maps/own-0-landmarks.json',EP/'eval_only/trajectory.jsonl']})
    dump(RAW/'correspondence-evaluation.json',records)
    dump(EXP/'results/association-diagnosis.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':associations()
