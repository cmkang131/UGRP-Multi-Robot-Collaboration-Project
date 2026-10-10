"""Separate evaluation process. Truth is never imported by the prediction API."""
from replay import *


def evaluate(mode):
    if (EXP/f'results/utility-{mode}.json').exists():
        raise ValueError('EVALUATION_ALREADY_SEALED')
    paths = [RAW/f'{c}-{mode}-{i}.json' for c in ('own','static') for i in range(3)]
    predictions = [load(p) for p in paths]
    for v in predictions:
        assert not v['gt_inputs'] and v['prepared_sha256']==sha(CACHE/'prepared.json')
        for name, digest in v['source_code_hashes'].items(): assert sha(ROOT/name)==digest,name
    expected = load(EP/'artifacts.sha256.json')
    for name in ('eval_only/trajectory.jsonl','inputs/static_map.json'):
        assert sha(EP/name)==expected[name]
    truth = rows(EP/'eval_only/trajectory.jsonl')
    by_t = {round(r['t'],6): r for r in truth}
    origin = np.r_[truth[0]['robot_xyz_m'][:2], truth[0]['robot_yaw_rad']]
    static = load(EP/'inputs/static_map.json')
    region = static['regions']['zone_B']
    from harness.self_map_relocalize import GridField
    from harness.public_navigation.costmap import Costmap
    f = GridField(load(CACHE/'maps/static-0.json'))
    oracle = Costmap(f.raw, f.grid_origin, f.grid_resolution)
    out = []; details = {}
    for v in predictions:
        condition, trial = v['condition'], v['trial']
        q = v['rows']; poses = np.array([r['pose'] for r in q])
        if condition=='own':
            poses[:,:2] = transform(poses[:,:2],origin)
            poses[:,2] += origin[2]
        gt = np.array([[*by_t[round(r['t'],6)]['robot_xyz_m'][:2],
                        by_t[round(r['t'],6)]['robot_yaw_rad']] for r in q])
        xy = np.linalg.norm(poses[:,:2]-gt[:,:2],axis=1)
        yaw = abs((poses[:,2]-gt[:,2]+math.pi)%(2*math.pi)-math.pi)
        correct = (xy<=.25)&(yaw<=math.radians(10))
        valid = [i for i,r in enumerate(q) if i>=4 and r['stable_resolved'] and correct[i-4:i+1].all()]
        internal = [i for i,r in enumerate(q) if r['stable_resolved']]
        false_internal = [i for i in internal if not correct[max(0,i-4):i+1].all()]
        inside = np.all(abs(gt[:,:2]-region['center_m'])<=region['half_extents_m'],axis=1)
        declared = np.array([r['declared_goal'] for r in q])
        plan_valid = None
        if v['plan'] is not None:
            path = np.asarray(v['plan']['path_m'],float).reshape(-1,2)
            angle = v['plan']['pose'][2]
            if condition=='own': path=transform(path,origin);angle+=origin[2]
            plan_valid = bool(len(path) and all(oracle.sweep_clear([*a,angle],[*b,angle])
                                              for a,b in zip(path,path[1:])))
        first = valid[0] if valid else None
        item = dict(condition=condition,mode=mode,trial=trial,seed=v['seed'],input_frames=v['input_frames'],
            point_samples=v['points'],landmark_samples=v['features'],landmark_frames=v['feature_frames'],measured_landmarks=v['measured_features'],start_t=v['start_t'],converged=first is not None,
            convergence_s=None if first is None else q[first]['t']-v['start_t'],
            convergence_xy_m=None if first is None else float(np.median(xy[first-4:first+1])),
            convergence_yaw_deg=None if first is None else float(np.median(yaw[first-4:first+1])*180/math.pi),
            internal_convergence_s=None if not internal else q[internal[0]]['t']-v['start_t'],
            false_internal_frames=len(false_internal),path_xy_rmse_m=float(np.sqrt(np.mean(xy**2))),
            final_xy_m=float(xy[-1]), final_yaw_deg=float(yaw[-1]*180/math.pi),
            final_std_xy_m=q[-1]['global_std_xy_m'],final_yaw_std_deg=q[-1]['circular_yaw_std_rad']*180/math.pi,
            final_overconfidence=float(xy[-1]/max(q[-1]['global_std_xy_m'],1e-12)),
            sensor_updates=q[-1]['updates'],resamples=q[-1]['resamples'],
            particles_min=min(r['n'] for r in q),particles_max=max(r['n'] for r in q),
            goal_observed=v['goal'] is not None,goal_declared=bool(declared.any()),
            correct_recorded_goal=bool(np.any(declared&inside)),false_goal=bool(np.any(declared&~inside)),
            actual_recorded_B_frames=int(inside.sum()),
            planned=v['plan'] is not None and v['plan']['status']=='planned',
            static_geometry_path_clear=plan_valid,physical_goal_reached=None,
            physical_scope='not tested: immutable replay cannot follow a new path')
        out.append(item)
        details[f'{condition}-{trial}']=dict(t=[r['t'] for r in q],xy_m=xy.tolist(),
            yaw_deg=(yaw*180/math.pi).tolist(),predicted_world=poses.tolist(),true_world=gt.tolist())
    own = [r for r in out if r['condition']=='own']; reference = [r for r in out if r['condition']=='static']
    matched = [(a,b) for a,b in zip(own,reference) if a['converged'] and b['converged']]
    def ratio(key):
        if not matched:return None
        a,b = [np.median([pair[i][key] for pair in matched]) for i in (0,1)]
        return float(a/b) if b>0 else 1. if a==0 else None
    er,tr = ratio('convergence_xy_m'),ratio('convergence_s')
    gates=dict(reference_converged_at_least_2=sum(r['converged'] for r in reference)>=2,
        own_convergence_count_no_less=sum(r['converged'] for r in own)>=sum(r['converged'] for r in reference),
        common_convergence_exists=bool(matched),xy_error_ratio_at_most_2=er is not None and er<=2.,
        time_ratio_at_most_2=tr is not None and tr<=2.,own_false_convergence_zero=all(r['false_internal_frames']==0 for r in own),
        reference_correct_goal_at_least_1=any(r['correct_recorded_goal'] for r in reference),
        own_correct_goal_no_less=sum(r['correct_recorded_goal'] for r in own)>=sum(r['correct_recorded_goal'] for r in reference),
        own_false_goal_zero=all(not r['false_goal'] for r in own),
        own_paths_clear=all(r['static_geometry_path_clear'] is True for r in own))
    maps = {}
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    rects=np.array([[*o['center_m'],*o['half_extents_m']] for o in static['obstacles'] if o['kind']=='wall'])
    samples=metric.wall_samples(rects)
    prepared=load(CACHE/'prepared.json')
    for c in ('own','static'):
        for trial in range(3):
            g=load(snapshot_path(c,trial));cells=np.array(g['cells']);vals=cells[:,2]
            occupied=(cells[vals>0,:2]+.5)*g['resolution_m']
            world=transform(occupied,origin) if c=='own' else occupied
            quality,covered=metric.quality(world,rects,samples)
            maps[f'{c}-{trial}']=dict(occupied=int((vals>0).sum()),free=int((vals<0).sum()),
                observed_cells=len(vals),observed_area_m2=len(vals)*g['resolution_m']**2,
                free_area_m2=float((vals<0).sum()*g['resolution_m']**2),
                quality=quality,covered_wall_samples=int(covered.sum()),all_wall_samples=len(samples))
    goals=[r['own_goal'] for r in prepared['cuts']]
    goal_errors=[None if g is None else float(np.linalg.norm(transform([g['center_m']],origin)[0]-region['center_m'])) for g in goals]
    summary=dict(source_sha=head(),trials=out,xy_ratio=er,time_ratio=tr,gates=gates,
        offline_proxy_gate=all(gates.values()),physical_goal_success='unmeasured',
        recommendation='one separately preregistered supervisor-authorized physical DEV regardless this offline gate',
        maps=maps,own_goals=goals,goal_center_offsets_m=goal_errors,mode=mode,
        historical_quality=dict(region_precision=103/162,region_recall=111/146,whole_coverage=213/329,
            occupied_cells=381,visible_wall_samples=146,total_wall_samples=329,insertion_scans=64),
        evaluation_gt_inputs={str(EP/'eval_only/trajectory.jsonl'):sha(EP/'eval_only/trajectory.jsonl')},
        sealed_predictions={str(p):sha(p) for p in paths},physics=0,retuning=0)
    dump(EXP/f'results/utility-{mode}.json',summary);dump(RAW/f'evaluation-details-{mode}.json',details)
    print(json.dumps(dict(gates=gates,xy_ratio=er,time_ratio=tr,results=out),indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['tempered'],required=True)
    evaluate(p.parse_args().mode)
