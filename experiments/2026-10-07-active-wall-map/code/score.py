"""Post-acquisition evaluator. GT is read only after prediction artifacts sealed."""
from pathlib import Path
import argparse
import json
import math
import sys
import hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1')
sys.path.insert(0,str(ROOT))
from scripts.run_active_wall_map import dump
from harness.active_camera import pitch
from harness.self_odom_grid import transform,OdomGrid


def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def verify(ep):
    for name,digest in load(ep/'artifacts.sha256.json').items():
        assert hashlib.sha256((ep/name).read_bytes()).hexdigest()==digest,name


def prediction(case, partial=False):
    ep=RAW/case
    if not partial:
        verify(ep)
        return ep
    view=RAW/(case+'-partial')
    receipt=load(view/'prediction.json')
    assert receipt['input_root']==str(ep)
    for root,hashes in ((ep,receipt['input_hashes']),(view,receipt['files'])):
        for name,digest in hashes.items():
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    return view


def static():
    ep=RAW/'static'
    verify(ep)
    result=load(ep/'result.json')
    if result['status']!='RECORDED':
        report=dict(passed=False,status=result['status'],reason='acquisition_failed')
    else:
        cameras={round(r['t'],6):r for r in rows(ep/'eval_only/camera.jsonl')}
        phases={'SEARCH':[],'look_ahead':[]}
        start=result['start_sim_s']
        for row in rows(ep/'eval_only/servo.jsonl'):
            rel=row['t']-start
            if not (3-1e-8<=rel<=4-1e-8 or 7-1e-8<=rel<=8+1e-8):continue
            c=cameras[round(row['t'],6)]
            rotation=np.array(c['body_rotation']).reshape(3,3).T@np.array(c['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
            actual=math.degrees(math.asin(float(np.clip(rotation[2,2],-1,1))))
            nominal=pitch({int(k):v for k,v in row['commands'].items()})
            phases['SEARCH' if rel<4 else 'look_ahead'].append(actual-nominal)
        stats={k:dict(n=len(a),signed_median_deg=float(np.median(a)),absolute_median_deg=float(np.median(np.abs(a))),p95_deg=float(np.quantile(np.abs(a),.95))) for k,a in phases.items()}
        s=stats['look_ahead']
        report=dict(passed=s['n']>=5 and s['absolute_median_deg']<=.3 and s['p95_deg']<=.5,
            status='EVALUATED',phases=stats,qualification='GT evaluation only; no fitted corrections')
    dump(RAW/'static-gate.json',report)
    dump(EXP/'results/static.json',report)
    print(json.dumps(report,indent=2))


def in_view(points,cameras,rects):
    """GT wall-only occlusion / true-camera FOV potential visibility; no object labels.

    Plane point z=.01 avoids a floor-boundary numerical tie. Hidden object/self
    occlusion is unmodelled and stated in results, so this denominator is potential visibility.
    """
    sys.path.insert(0,str(ROOT/'experiments/2026-09-26-markerless-probe'))
    import markerless_probe as mp
    pts=np.c_[np.asarray(points).reshape(-1,2),np.full(len(points),.01)]
    ever=np.zeros(len(pts),bool)
    for camera in cameras:
        origin=np.array(camera['camera_xyz'])
        R=np.array(camera['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
        vec=pts-origin
        optical=vec@R
        with np.errstate(divide='ignore',invalid='ignore'):
            uv=(optical@mp.K.T)[:,:2]/optical[:,2,None]
        candidate=(~ever)&(optical[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(np.linalg.norm(vec,axis=1)<=4.)
        ids=np.flatnonzero(candidate)
        if not len(ids):continue
        d=pts[ids,:2]-origin[:2]
        blocked=np.zeros(len(ids),bool)
        for x,y,hx,hy in rects:
            lo=np.array([x-hx,y-hy]);hi=np.array([x+hx,y+hy])
            with np.errstate(divide='ignore',invalid='ignore'):
                a=(lo-origin[:2])/d;b=(hi-origin[:2])/d
            entry=np.maximum(np.minimum(a,b).max(1),0)
            exit=np.minimum(np.maximum(a,b).min(1),1)
            # Exclude only an obstruction strictly before target wall face.
            blocked|=(entry<exit)&(entry<1-.05/np.maximum(np.linalg.norm(d,axis=1),.05))&(exit>0)
        ever[ids[~blocked]]=True
    return ever


def calibration(scores,labels):
    scores=np.asarray(scores);labels=np.asarray(labels)
    bins=[]
    for i in range(10):
        ids=(scores>=i/10)&(scores<((i+1)/10 if i<9 else 1.00001))
        bins.append(dict(lo=i/10,n=int(ids.sum()),score=float(scores[ids].mean()) if ids.any() else None,
                         precision=float(labels[ids].mean()) if ids.any() else None))
    return dict(n=len(scores),bins=bins,gap=sum(b['n']*abs(b['score']-b['precision']) for b in bins if b['n'])/len(scores) if len(scores) else None)


def evaluate(case, partial=False):
    ep=RAW/case
    view=prediction(case,partial)
    acquisition=load(view/'result.json')
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metrics
    from scipy.spatial import cKDTree
    actual=rows(ep/'eval_only/trajectory.jsonl')
    truth={round(r['t'],6):np.array([*r['robot_xyz_m'][:2],r['robot_yaw_rad']]) for r in actual}
    origin=truth[min(truth)]
    static=load(ep/'inputs/static_map.json')
    rects=np.array([w['center_m']+w['half_extents_m'] for w in static['obstacles'] if w.get('kind')=='wall'])
    samples=metrics.wall_samples(rects)
    graph=load(view/'graph.json')
    cells=np.array([c for c in load(view/'grid.json')['cells'] if c[2]>0]).reshape(-1,3)
    xy=transform((cells[:,:2]+.5)*.1,origin)
    q,cover=metrics.quality(xy,rects,samples)
    cams=rows(ep/'eval_only/camera.jsonl')
    visible=in_view(samples,cams,rects)
    region=in_view(xy,cams,rects)
    distances=metrics.boundary_dist(xy,rects)
    correct=distances<=.15
    path=[p for p in graph['poses'] if round(p['t'],6) in truth]
    unscored=len(graph['poses'])-len(path)
    assert partial or unscored==0
    estimate=transform(np.array([p['pose'][:2] for p in path]).reshape(-1,2),origin)
    gt=np.array([truth[round(p['t'],6)][:2] for p in path]).reshape(-1,2)
    errors=np.linalg.norm(estimate-gt,axis=1)
    actual_path=np.array([r['robot_xyz_m'][:2] for r in actual])
    travelled=float(np.linalg.norm(np.diff(actual_path,axis=0),axis=1).sum())
    # Actual rectangular footprint union on .05m grid, never sent to exploration.
    from harness.public_navigation_unknown import footprint_cells
    from harness.own_map_navigation import ObservedGrid
    eval_grid=ObservedGrid('r3',.05)
    visited=set().union(*(footprint_cells(eval_grid,p) for p in truth.values()))
    coverage_area=len(visited)*.05**2
    evidence=graph.get('wall_evidence',{})
    support={tuple(c['cell']):c['support_score'] for c in evidence.get('cells',[])}
    score=np.array([support.get(tuple(c[:2].astype(int)),0.) for c in cells])
    belief=1/(1+np.exp(-cells[:,2]))
    traces=rows(ep/'own-controller.jsonl')
    # Wrong-door attempts: a selected door is near the current commanded path,
    # whose GT start-aligned path intersects true walls with the physical rectangle.
    wrong=[];last=None
    door_exposure=dict(candidate_frames=sum(bool(r.get('doors')) for r in traces),
                       feasible_rows=0,selected_path_rows=0)
    for trace in traces:
        if not trace.get('doors') or len(trace['path'])<2:continue
        p=transform(np.asarray(trace['path']),origin)
        for door in trace['doors']:
            if not door.get('payload_clearance_feasible',False):continue
            door_exposure['feasible_rows']+=1
            center=transform([door['center_m']],origin)[0]
            if np.linalg.norm(p-center,axis=1).min()>.3:continue
            door_exposure['selected_path_rows']+=1
            bad=bool((metrics.boundary_dist(p,rects)<.12).any())
            if bad and door['id']!=last:wrong.append(dict(t=trace['t'],door=door['id']));last=door['id']
    b=static['regions']['zone_B']
    inside=np.all(np.abs(actual_path-np.array(b['center_m']))<=np.array(b['half_extents_m']),axis=1)
    confirmed=[t['t'] for t in traces if any(x.get('confirmed_t') is not None for x in t['goal'].get('candidates',[]))]
    contact=int(acquisition.get('failure',{}).get('message')=='WALL_CONTACT')
    area_p=float(correct[region].mean()) if region.any() else None
    recall=float(cover[visible].mean()) if visible.any() else None
    rmse=float(np.sqrt(np.mean(errors**2))) if len(errors) else None
    criteria=dict(recorded=acquisition['status']=='RECORDED',no_contact=contact==0,no_wrong_door=not wrong,
        distance=travelled>=3.,area=coverage_area>=.75,visible_samples=int(visible.sum())>=50,
        precision=area_p is not None and area_p>=.7,recall=recall is not None and recall>=.5,
        wall_rmse=q['wall_error_rmse_m'] is not None and q['wall_error_rmse_m']<=.15,
        path_rmse=rmse is not None and rmse<=.25)
    result=dict(case=case,acquisition=acquisition,full_map=q,wall_sample_count=len(samples),
        prediction_view='partial_frontend_unfinished_graph' if partial else 'completed_graph',
        observed_region=dict(precision=area_p,precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
            recall=recall,recalled_samples=int(cover[visible].sum()),visible_samples=int(visible.sum()),
            visible_wall_fraction=float(visible.mean()),sampled_wall_length_proxy_m=float(visible.sum())*.1,
            qualification='actual camera poses/FOV/range and wall-only occlusion; object/self occlusion not modelled'),
        coverage=dict(travelled_m=travelled,footprint_union_m2=coverage_area,footprint_cells_005m=len(visited),
            frames=acquisition['frames'],mapped_frames=len(graph['ledger']),occupied_cells=len(cells)),
        path=dict(n=len(errors),rmse_m=rmse,end_m=float(errors[-1]) if len(errors) else None,
                  missing_gt_samples=unscored),
        b=dict(first_own_confirmation_s=min(confirmed) if confirmed else None,reached_gt=bool(inside.any()),
               first_gt_reach_s=actual[int(np.flatnonzero(inside)[0])]['t'] if inside.any() else None),
        wall_contacts=contact,wrong_door_attempts=wrong,door_exposure=door_exposure,
        loop_counts=graph['diagnostics'].get('loop_counts'),
        switch_counts=graph['diagnostics'].get('switch_counts'),
        calibration=dict(occupancy_ece_diagnostic=calibration(belief,correct),support_score_gap=calibration(score,correct),
                         qualification='TSDF support is NOT probability'),criteria=criteria,passed=all(criteria.values()))
    dump(EXP/'results'/f'{case}.json',result)
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,(ax,bx)=plt.subplots(1,2,figsize=(12,5))
    for x,y,hx,hy in rects:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7'))
    if len(xy):dots=ax.scatter(xy[:,0],xy[:,1],c=score,s=12,cmap='Blues',vmin=0,vmax=1);fig.colorbar(dots,ax=ax,label='TSDF support (not probability)')
    ax.plot(actual_path[:,0],actual_path[:,1],'--',color='green',label='Actual path (evaluation)')
    if len(estimate):ax.plot(estimate[:,0],estimate[:,1],color='orange',label='Own estimated path')
    ax.set(aspect='equal',xlabel='m',ylabel='m',title=f'{case}{" (partial frontend)" if partial else ""}: {travelled:.2f} m / {coverage_area:.2f} m² / {int(visible.sum())} wall samples')
    ax.legend(fontsize=8)
    for label,c in [('occupancy',result['calibration']['occupancy_ece_diagnostic']),('support',result['calibration']['support_score_gap'])]:
        valid=[b for b in c['bins'] if b['n']]
        bx.plot([b['score'] for b in valid],[b['precision'] for b in valid],'-o',label=label)
        for b in valid:bx.annotate(str(b['n']),(b['score'],b['precision']),fontsize=7)
    bx.plot([0,1],[0,1],'--',color='.7')
    bx.set(xlim=(0,1),ylim=(0,1),xlabel='Score (support is not probability)',ylabel='Actual wall fraction',title='Counts shown at each bin')
    bx.legend();fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures'/f'{case}.png',dpi=140);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k not in ('calibration','acquisition')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('case',choices=['static','photo','speckle'])
    p.add_argument('--partial',action='store_true')
    a=p.parse_args()
    static() if a.case=='static' else evaluate(a.case,a.partial)
