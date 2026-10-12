"""Evaluation only. Read sealed predictions, then read truth; no estimator writes."""
from pathlib import Path
import json
import math
import sys
import numpy as np
import replay as r
c=r.c
EXP,ROOT,RAW=r.EXP,r.ROOT,r.RAW
from harness.self_odom_grid import OdomGrid,transform
from harness.self_pose_graph import insert_row
from own_map_csm_replay import acceptance


def calibration(scores,labels,*,probability=True):
    scores,labels=np.asarray(scores),np.asarray(labels)
    assert scores.shape==labels.shape and np.isfinite(scores).all()
    bins=[]
    indices=np.minimum(9,(scores*10).astype(int))
    for i in range(10):
        ids=indices==i
        bins.append(dict(lo=i/10,hi=(i+1)/10,n=int(ids.sum()),
            mean_score=float(scores[ids].mean()) if ids.any() else None,
            precision=float(labels[ids].mean()) if ids.any() else None))
    result=dict(bins=bins,n=len(scores),qualification='occupied cells only' if probability else 'insertion evidence weight, not probability')
    if probability and len(scores):
        result.update(brier=float(np.mean((scores-labels)**2)),
            ece=float(sum(b['n']*abs(b['mean_score']-b['precision']) for b in bins if b['n'])/len(scores)))
    return result


def evaluate(case):
    ep,out=r.configure(case)
    for name in ('prediction.json','baseline-prediction.json'):
        receipt=c.read(out/name)
        assert all(c.sha(out/p)==h for p,h in receipt['hashes'].items())
    truth=c.old.current_truth(ep)
    gtrows=c.old.base.read_rows(ep/'eval_only/trajectory.jsonl')
    origin=truth[min(truth)]
    rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    samples=c.old.base.wall_samples(rects)
    result=dict(case=case,recording=c.read(ep/'result.json'),wall_sample_count=len(samples),metrics={})
    curves={}
    display={}
    for mode,gridfile,posefile,ledgerfile in [('rbpf_graph','grid.json','graph-poses.jsonl','graph-ledger.jsonl'),
                                           ('dr','dr-grid.json','dr-poses.jsonl','dr-ledger.jsonl')]:
        grid=OdomGrid('r3')
        grid.cells={(x,y):v for x,y,v in c.read(out/gridfile)['cells']}
        poses=c.old.base.read_rows(out/posefile)
        pts=transform(grid.occupied_points(),origin)
        quality=c.old.base.quality(pts,rects,samples)[0]
        result['metrics'][mode]=dict(final=quality,**c.old.path_score(poses,truth))
        cells=sorted((x,y,v) for (x,y),v in grid.cells.items() if v>0)
        xy=transform(np.array([[(x+.5)*.1,(y+.5)*.1] for x,y,v in cells]).reshape(-1,2),origin)
        belief=1/(1+np.exp(-np.array([v for x,y,v in cells])))
        curves[mode]=calibration(belief,(c.old.base.boundary_dist(xy,rects)<=.15).astype(float))
        ledger=c.old.base.read_rows(out/ledgerfile)
        weights,correct=[],[]
        series=[]
        accumulating=OdomGrid('r3')
        for i,row in enumerate(ledger):
            insert_row(accumulating,row,row['pose'])
            if i%25==0 or i==len(ledger)-1:
                q=c.old.base.quality(transform(accumulating.occupied_points(),origin),rects,samples)[0]
                series.append(dict(t=row['t'],**q))
            if mode=='rbpf_graph':
                # Two correctness views: projection with GT body vs final mapped location.
                for segment,w in zip(row['segments'],row['insertion_weights']):
                    n=max(2,int(math.ceil(np.linalg.norm(np.diff(segment,axis=0))/.05))+1)
                    local=np.linspace(*np.array(segment),n)
                    world=transform(transform(local,row['pose']),origin)
                    direct=transform(local,truth[round(row['t'],6)])
                    weights.extend([w]*n)
                    correct.extend(np.c_[c.old.base.boundary_dist(world,rects)<=.15,
                                        c.old.base.boundary_dist(direct,rects)<=.15].astype(float).tolist())
        assert accumulating.export()['cells']==grid.export()['cells']
        result['metrics'][mode]['coverage_series']=series
        if mode=='rbpf_graph':
            curves['weight_map']=calibration(weights,np.array(correct)[:,0],probability=False)
            curves['weight_gt_body']=calibration(weights,np.array(correct)[:,1],probability=False)
        display[mode]=(xy,belief,transform(np.array([p['pose'][:2] for p in poses]),origin))
    result['relative_gate']=acceptance(result['metrics']['dr'],result['metrics']['rbpf_graph'])
    # Actual path: targets evaluated in order, no runtime target/GT comparison.
    plan=c.read(ep/'authored-plan.json')
    gt=np.array([v['robot_xyz_m'][:2] for v in gtrows])
    cursor=0
    completion=[]
    for waypoint in plan['milestones']:
        target=transform([waypoint['target_own_m']],origin)[0]
        distances=np.linalg.norm(gt[cursor:]-target,axis=1)
        idx=np.flatnonzero(distances<=.35)
        hit=int(cursor+idx[0]) if len(idx) else None
        completion.append(dict(leg=waypoint['leg'],nearest_m=float(distances.min()),
                               reached_time=gtrows[hit]['t'] if hit is not None else None))
        if hit is not None:cursor=hit
        else:break
    complete=len(completion)==8 and all(p['reached_time'] is not None for p in completion)
    result['tour']=dict(completed=complete,waypoints=completion,actual_distance_m=float(np.linalg.norm(np.diff(gt,axis=0),axis=1).sum()),
        initial_to_end_m=float(np.linalg.norm(gt[-1]-gt[0])))
    # Failure diagnosis with the SAME command-only pose; no coefficient update.
    drposes=c.old.base.read_rows(out/'dr-poses.jsonl')
    drworld=transform(np.array([p['pose'][:2] for p in drposes]),origin)
    result['failure_geometry']=dict(actual_end_xy=gt[-1].tolist(),predicted_end_xy=drworld[-1].tolist(),
        planned_leg_at_end=max([-1]+[x['leg'] for x in plan['commands'] if x['t']<=gtrows[-1]['t']-gtrows[0]['t']]),
        nearest_wall_distance_end_m=float(c.old.base.boundary_dist(gt[-1:].copy(),rects)[0]))
    m=result['metrics']['rbpf_graph']
    result['export_gate']=dict(tour_complete=complete,precision=m['final']['precision_015']>=.9,
        recall=m['final']['wall_coverage']>=.7,wall_rmse=m['final']['wall_error_rmse_m']<=.15,
        pose_rmse=m['path_position_error']['rmse_m']<=.25,relative=result['relative_gate']['success'])
    result['export_admitted']=all(result['export_gate'].values())
    prediction=c.read(out/'prediction.json')
    result.update(inserted=prediction['inserted'],loop_counts=prediction['loop_counts'],frontend_counts=prediction['frontend_counts'])
    c.dump(EXP/'results'/(case+'.json'),result)
    c.dump(EXP/'results'/(case+'-calibration.json'),curves)
    return result,rects,gt,display,curves


def plot(all_results):
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    dest=EXP/'figures'
    dest.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,(result,rects,gt,display,curves) in zip(axes,all_results):
        for x,y,hx,hy in rects:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7'))
        xy,p,path=display['rbpf_graph']
        sc=ax.scatter(xy[:,0],xy[:,1],c=p,cmap='Blues',vmin=.5,vmax=1,s=10,marker='s')
        ax.plot(path[:,0],path[:,1],color='#ed7d31',lw=1,label='RBPF + graph')
        ax.plot(gt[:,0],gt[:,1],color='#338855',ls='--',lw=1,label='Actual (eval only)')
        ax.plot(display['dr'][2][:,0],display['dr'][2][:,1],color='#8855aa',lw=.6,alpha=.6,label='Command DR')
        ax.scatter(*gt[-1],marker='x',color='red')
        q=result['metrics']['rbpf_graph']['final']
        ax.set(aspect='equal',xlabel='world x (m)',ylabel='world y (m)',
            title=f"{result['case']} | P {q['precision_015']:.1%} / R {q['wall_coverage']:.1%}\n{result['recording']['status']} / lap {result['tour']['completed']}")
        ax.legend(fontsize=7,loc='lower left')
    fig.colorbar(sc,ax=axes.tolist(),label='Occupancy belief; not calibrated correctness',shrink=.85)
    fig.savefig(dest/'maps.png',dpi=150,bbox_inches='tight')
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for result,rects,gt,display,curves in all_results:
        for key in ('rbpf_graph','dr'):
            b=[b for b in curves[key]['bins'] if b['n']]
            axes[0].plot([v['mean_score'] for v in b],[v['precision'] for v in b],'o-',label=result['case']+' '+key)
            for v in b:axes[0].annotate(str(v['n']),(v['mean_score'],v['precision']),fontsize=6)
        for key,style in [('weight_map','-'),('weight_gt_body','--')]:
            b=[b for b in curves[key]['bins'] if b['n']]
            axes[1].plot([v['mean_score'] for v in b],[v['precision'] for v in b],'o'+style,label=result['case']+' '+key)
    axes[0].plot([0,1],[0,1],':',color='.5')
    axes[0].set(xlabel='Mean occupancy belief (occupied cells only)',ylabel='Fraction within 0.15 m of true wall',title='Reliability diagnostic; labels = bin counts')
    axes[1].set(xlabel='Insertion weight (not probability)',ylabel='Wall point precision',title='Final map vs GT-body projection')
    for ax in axes:ax.set(xlim=(0,1),ylim=(0,1));ax.legend(fontsize=6)
    fig.tight_layout()
    fig.savefig(dest/'calibration.png',dpi=150)
    plt.close(fig)


if __name__=='__main__':
    # Both predictions must be sealed before either case's truth is inspected.
    assert all((RAW/'predictions'/case/'baseline-prediction.json').exists() for case in ('forward','reverse'))
    data=[evaluate(case) for case in ('forward','reverse')]
    plot(data)
    for result,*_ in data:print(json.dumps({k:result[k] for k in ('case','tour','metrics','export_admitted')},ensure_ascii=False))
