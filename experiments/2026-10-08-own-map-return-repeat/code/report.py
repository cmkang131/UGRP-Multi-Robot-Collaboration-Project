"""Post-seal six-slot utility scoring, egomap43 thresholds unchanged."""
from pathlib import Path
from collections import Counter
import argparse,importlib.util,json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
from scripts.run_own_map_return_repeat import RAW,SEEDS
from scripts.run_active_wall_rotleft import dump
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def old_report():return module('eg43_report',ROOT/'experiments/2026-10-08-own-map-closed-loop/code/physical_report.py')


def classify(*,status,observed,arrived,false_declarations,end_error,correct_convergence):
    if status!='RECORDED':return 'other'
    if arrived and not false_declarations:return 'success'
    if not observed:return 'exploration_not_covered'
    if false_declarations or end_error is None or end_error>.25 or not correct_convergence:return 'localization'
    return 'path_or_budget'


def nees(error,covariance):
    c=np.asarray(covariance,float)[:2,:2];e=np.asarray(error,float)
    if not np.isfinite(c).all() or np.linalg.eigvalsh(c).min()<=0:return None
    return float(e@np.linalg.solve(c,e))


def score(seed):
    ep=RAW/f'seed{seed}';old=old_report();old.module().verify(ep)
    acquisition=load(ep/'result.json');trace=rows(ep/'own-controller.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl')
    result=dict(seed=seed,acquisition=acquisition,started=bool(truth),arrived=False,false_declarations=0,
        final_xy_m=None,final_sigma_xy_m=None,final_error_sigma_ratio=None,final_nees_xy=None,
        over_3sigma=None,goal_observed=False,failure_class='other',excluded=False,thresholds_unchanged=True)
    out=EXP/'conditions'/f'seed{seed}'/'results';out.mkdir(parents=True,exist_ok=True)
    if not truth or not trace:
        result['unscored_reason']='NO_SAVED_TRAJECTORY_OR_TRACE';dump(out/'report.json',result);return result
    static=load(ep/'inputs/static_map.json');zone=static['regions']['zone_B']
    inside=lambda xy:bool(np.all(np.abs(np.asarray(xy)-zone['center_m'])<=zone['half_extents_m']))
    by_t={round(r['t'],6):np.array([*r['robot_xyz_m'][:2],r['robot_yaw_rad']]) for r in truth}
    origin=by_t[min(by_t)];c,s=np.cos(origin[2]),np.sin(origin[2]);rotation=np.array([[c,-s],[s,c]])
    usable=[r for r in trace if r.get('pose') is not None and round(r['t'],6) in by_t]
    predicted=np.array([r.get('local_pose',r['pose']) for r in usable])
    world=transform(predicted[:,:2],origin);actual=np.array([by_t[round(r['t'],6)] for r in usable])
    delta_local=(world-actual[:,:2])@rotation
    errors=np.linalg.norm(delta_local,axis=1);yaw=wrap(predicted[:,2]+origin[2]-actual[:,2])
    front={round(r['t'],6):r for r in rows(ep/'frontend-covariances.jsonl')}
    uncertainty=[]
    for i,r in enumerate(usable):
        covariance=r.get('belief',front.get(round(r['t'],6),{})).get('covariance')
        sigma=r.get('sigma_xy');ratio=float(errors[i]/sigma) if sigma is not None and sigma>0 else None
        uncertainty.append(dict(t=r['t'],error_m=float(errors[i]),sigma_xy_m=sigma,error_sigma_ratio=ratio,
            covariance=covariance,nees_xy=None if covariance is None else nees(delta_local[i],covariance),
            sigma_definition='sqrt_trace_cov_xy' if 'belief' in r else 'frontend_reported_max_axis'))
    post=[i for i,r in enumerate(usable) if 'belief' in r];valid=[];false=[]
    for k,i in enumerate(post):
        previous=post[max(0,k-4):k+1]
        correct=len(previous)==5 and all(errors[j]<=.25 and abs(yaw[j])<=math.radians(10) for j in previous)
        if usable[i]['stable_resolved']:(valid if correct else false).append(i)
    declarations=[dict(t=r['t'],error_m=float(errors[i]),actual_inside_B=inside(actual[i,:2])) for i,r in enumerate(usable) if r.get('declared_goal')]
    events=load(ep/'utility-events.json');loss=next((r['t'] for r in events if r['reason']=='unknown_start_reset'),None)
    goal=load(ep/'remembered-goal.json');assigned=next((r for r in events if r['reason']=='remembered_target_assigned'),None)
    if assigned and goal:assert goal['t_sim']<assigned['t'] and goal['first_t']<=goal['t_sim']
    if (ep/'snapshot.json').exists():
        snapshot=load(ep/'snapshot.json')
        assert snapshot['t']<loss and all(r['t']<loss for r in snapshot['ledger'])
        assert snapshot['landmarks']['future_observations']==0
    contact=rows(ep/'eval_only/contact-audit.jsonl');contacts={}
    for kind in ('wall','robot'):
        mask=[any(p['kind']==kind for p in r['pairs']) for r in contact]
        contacts[kind]=dict(frames=sum(mask),episodes=sum(x and (i==0 or not mask[i-1]) for i,x in enumerate(mask)))
    g=load(ep/'frontend-grid.json');ledger=load(ep/'frontend-ledger.json')
    cells=np.array([r for r in g['cells'] if r[2]>0]).reshape(-1,3)
    xy=transform((cells[:,:2]+.5)*g['resolution_m'],origin)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'));import odom_grid_replay as metric
    walls=np.array([w['center_m']+w['half_extents_m'] for w in static['obstacles'] if w.get('kind')=='wall'])
    samples=metric.wall_samples(walls);quality,cover=metric.quality(xy,walls,samples)
    cameras=[r for r in rows(ep/'eval_only/camera.jsonl') if loss is None or r['t']<loss]
    visible=old.module().in_view(samples,cameras,walls)
    result.update(goal_observed=goal is not None,goal=goal,target_assignment=assigned,loss_t=loss,
        correct_convergence=bool(valid),false_convergence_frames=len(false),post_loss_frames=len(post),
        declarations=declarations,arrived=any(r['actual_inside_B'] for r in declarations),
        false_declarations=sum(not r['actual_inside_B'] for r in declarations),
        final_xy_m=float(errors[-1]),final_yaw_deg=float(np.degrees(yaw[-1])),
        final_sigma_xy_m=uncertainty[-1]['sigma_xy_m'],final_error_sigma_ratio=uncertainty[-1]['error_sigma_ratio'],
        final_nees_xy=uncertainty[-1]['nees_xy'],final_sigma_definition=uncertainty[-1]['sigma_definition'],
        over_3sigma=None if uncertainty[-1]['error_sigma_ratio'] is None else uncertainty[-1]['error_sigma_ratio']>3,
        post_loss_over_3sigma=sum(uncertainty[i]['error_sigma_ratio'] is not None and uncertainty[i]['error_sigma_ratio']>3 for i in post),
        path_rmse_m=float(np.sqrt(np.mean(errors**2))),error_samples=len(errors),
        missing_gt_trace_samples=sum(r.get('pose') is not None and round(r['t'],6) not in by_t for r in trace),
        final_error_t=usable[-1]['t'],last_truth_t=truth[-1]['t'],
        sim_s=truth[-1]['t']-acquisition['start_sim_s'],wall_s=acquisition['wall_s'],
        arrival_after_loss_s=declarations[0]['t']-loss if declarations and loss else None,
        contacts=contacts,contact_samples=len(contact),contact_scope='5Hz samples/contiguous sampled episodes, plus native failure reason; not exhaustive',
        command_frames=len(trace),hold_frames=sum(r['command']['kind']=='hold' for r in trace),
        return_statuses=dict(Counter(r['status'] for r in trace if r.get('stage')!='explore')),
        return_navigation=dict(Counter(r.get('reason','') for r in load(ep/'return-navigation.json'))),
        travelled_m=float(np.linalg.norm(np.diff(np.array([r['robot_xyz_m'][:2] for r in truth]),axis=0),axis=1).sum()),
        map=dict(quality=quality,occupied_cells=len(cells),inserted_scans=len(ledger),visible_samples=int(visible.sum()),
            total_wall_samples=len(samples),covered_samples=int(cover.sum()),coverage=float(cover.mean())),
        insertion_gate_counts=dict(Counter(r['status']+'/'+r.get('reason','') for r in load(ep/'decisions.json'))))
    result['failure_class']=classify(status=acquisition['status'],observed=result['goal_observed'],arrived=result['arrived'],
        false_declarations=result['false_declarations'],end_error=result['final_xy_m'],correct_convergence=result['correct_convergence'])
    dump(out/'report.json',result);dump(ep/'evaluation-errors.json',uncertainty)
    print(seed,result['arrived'],result['failure_class'],result['final_xy_m'],result['final_error_sigma_ratio'],flush=True)
    return result


def aggregate():
    reports=[load(EXP/'conditions'/f'seed{s}'/'results/report.json') for s in SEEDS]
    errors=[r['final_xy_m'] for r in reports if r['final_xy_m'] is not None]
    result=dict(registered=6,physical_attempts=sum(r['started'] for r in reports),arrivals=sum(r['arrived'] for r in reports),
        false_declarations=sum(r['false_declarations'] for r in reports),
        final_error_median_m=float(np.median(errors)) if errors else None,final_error_max_m=max(errors) if errors else None,
        endpoint_error_n=len(errors),over_3sigma=sum(r['over_3sigma'] is True for r in reports),
        uncertainty_available_n=sum(r['over_3sigma'] is not None for r in reports),
        failure_classes=dict(Counter(r['failure_class'] for r in reports)),excluded=[],conditions=reports,
        qualification='Six preregistered seeds, same scene/start. No parameter selection or retuning. Not real hardware.')
    dump(EXP/'results/summary.json',result);return result


def movies():
    reports=[load(EXP/'conditions'/f'seed{s}'/'results/report.json') for s in SEEDS]
    selected=[]
    for success in (True,False):
        candidates=[r for r in reports if (r['failure_class']=='success')==success and r['started']]
        if candidates:selected.append(candidates[0])
    for r in selected:
        seed=r['seed'];old=old_report();old.EP=RAW/f'seed{seed}';old.RAW=old.EP;old.EXP=EXP/'conditions'/f'seed{seed}'
        old.movie()
    dump(EXP/'results/video-selection.json',dict(seeds=[r['seed'] for r in selected],rule='first registered success and first registered failure, if available'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['score','aggregate','movies']);p.add_argument('--seed',type=int,choices=SEEDS);a=p.parse_args()
    if a.mode=='score':score(a.seed)
    elif a.mode=='aggregate':print(json.dumps(aggregate(),indent=2))
    else:movies()
