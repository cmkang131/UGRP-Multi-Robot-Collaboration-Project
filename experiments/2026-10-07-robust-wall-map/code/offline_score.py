"""Evaluation only, after BOTH predictions are sealed; no feedback or fitting."""
import importlib.util
import json
import math
import sys
import numpy as np
import backend_replay as b

# Reuse the original metric implementation without invoking its predictor/scorer.
old_dir=b.ROOT/'experiments/2026-10-07-arena-wall-map/code'
sys.path.insert(0,str(old_dir))
spec=importlib.util.spec_from_file_location('egomap20_score',old_dir/'score.py')
old=importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
c=old.c
from harness.self_odom_grid import OdomGrid, transform
from harness.self_pose_graph import between, wrap, insert_row


def summarize(values):
    values=np.asarray(values)
    return dict(n=len(values),rmse=float(np.sqrt(np.mean(values**2))),
                median=float(np.median(np.abs(values))),p95=float(np.percentile(np.abs(values),95)),
                end=float(values[-1])) if len(values) else dict(n=0)


def score_gap(scores, labels):
    # Same ECE bin arithmetic, but the caller must retain this non-probability label.
    result=old.calibration(scores,labels)
    result['qualification']='support-score calibration gap; NOT a probability calibration claim'
    result['score_ece']=result.pop('ece')
    result['score_squared_error']=result.pop('brier')
    return result


def evaluate(case):
    source=b.verify_source(case)
    result=dict(case=case,metrics={},calibration={},yaw={},loop_errors=[])
    truth=c.old.current_truth(b.SOURCE/case)
    origin=truth[min(truth)]
    walls=b.load(b.SOURCE/case/'inputs/static_map.json')['obstacles']
    rects=np.asarray([w['center_m']+w['half_extents_m'] for w in walls if w.get('kind')=='wall'])
    samples=c.old.base.wall_samples(rects)
    result['wall_samples']=len(samples)
    displays={}
    for mode in ('off','on'):
        output=b.RAW/case/mode
        grid=OdomGrid('r3')
        grid.cells={(x,y):v for x,y,v in b.load(output/'grid.json')['cells']}
        poses=b.rows(output/'graph-poses.jsonl')
        occupied=sorted((x,y,v) for (x,y),v in grid.cells.items() if v>0)
        xy=transform(np.array([[(x+.5)*.1,(y+.5)*.1] for x,y,v in occupied]),origin)
        labels=(c.old.base.boundary_dist(xy,rects)<=.15).astype(float)
        metric=dict(final=c.old.base.quality(xy,rects,samples)[0],**c.old.path_score(poses,truth))
        result['metrics'][mode]=metric
        belief=1/(1+np.exp(-np.array([v for x,y,v in occupied])))
        result['calibration'][mode]=dict(occupancy_diagnostic=old.calibration(belief,labels))
        scores=belief
        if mode=='on':
            evidence=b.load(output/'wall-evidence.json')
            lookup={tuple(cell['cell']):cell for cell in evidence['cells']}
            scores=np.array([lookup.get((x,y),{}).get('support_score',0.) for x,y,v in occupied])
            stats=result['calibration'][mode]
            stats['support']=score_gap(scores,labels)
            high=scores>=.9
            stats['high_support']=dict(n=int(high.sum()),correct=int(labels[high].sum()),
                precision=float(labels[high].mean()) if high.any() else None)
            stats['occupied_support_missing']=sum((x,y) not in lookup for x,y,v in occupied)
            stats['angular_diversity']=[]
            # Fixed diagnostic bands only, no quality threshold or refitting.
            diversity=np.array([lookup.get((x,y),{}).get('view_circular_variance',0.) for x,y,v in occupied])
            for lo,hi in [(0.,.01),(.01,.1),(.1,1.00001)]:
                ids=(diversity>=lo)&(diversity<hi)
                stats['angular_diversity'].append(dict(lo=lo,hi=hi,n=int(ids.sum()),
                    precision=float(labels[ids].mean()) if ids.any() else None,
                    mean_support=float(scores[ids].mean()) if ids.any() else None))
        ledger=b.rows(output/'graph-ledger.jsonl')
        accumulating=OdomGrid('r3')
        metric['coverage_series']=[]
        for i,row in enumerate(ledger):
            insert_row(accumulating,row,row['pose'])
            if i%25==0 or i==len(ledger)-1:
                quality=c.old.base.quality(transform(accumulating.occupied_points(),origin),rects,samples)[0]
                metric['coverage_series'].append(dict(t=row['t'],**quality))
        assert accumulating.export()['cells']==grid.export()['cells']
        displays[mode]=(xy,scores,transform(np.array([p['pose'][:2] for p in poses]),origin))
    # Frozen §17/§19 relative comparison against original same-observation DR.
    baseline=b.load(b.ROOT/'experiments/2026-10-07-arena-wall-map/results'/f'{case}.json')
    result['relative_gate']=old.acceptance(baseline['metrics']['dr'],result['metrics']['on'])
    # Off rerender/scoring must exactly recover egomap20 geometry and path metrics.
    expected=baseline['metrics']['rbpf_graph']
    for key in ('final','path_position_error','end_position_error_m'):
        assert result['metrics']['off'][key]==expected[key], ('OFF_METRIC_CHANGED',key)
    front=b.rows(source/'frontend-ledger.jsonl')
    graph=b.load(source/'graph-diagnostics.json')
    on_graph=b.load(b.RAW/case/'on/graph-diagnostics.json')
    lookup={(v['submap'],v['scan']):v for v in on_graph['optimization']['switches']}
    for event in graph['loops']:
        if not event['accepted']:
            continue
        sub=graph['submaps'][event['submap']]
        anchor=origin if event['submap']==0 else truth[round(sub['interval'][0],6)]
        relative=between(anchor,truth[round(front[event['scan']]['t'],6)])
        error=np.asarray(event['relative_pose'])-relative
        switch=lookup[(event['submap'],event['scan'])]
        result['loop_errors'].append(dict(**switch,translation_error_m=float(np.linalg.norm(error[:2])),
            yaw_error_deg=float(abs(np.degrees(wrap(error[2])))),false_xy_gt_030=bool(np.linalg.norm(error[:2])>.30)))
    result['loop_counts']=dict(original=graph['loop_counts'],switch=on_graph['switch_counts'])
    result['optimization']=on_graph['optimization']
    # Actual scan-to-own-map yaw correction already lives in the cached frontend.
    for mode,path in [('dr',source/'dr-poses.jsonl'),('frontend',source/'frontend-poses.jsonl'),
                      ('off',b.RAW/case/'off/graph-poses.jsonl'),('on',b.RAW/case/'on/graph-poses.jsonl')]:
        poses=b.rows(path)
        signed=[float(np.degrees(wrap(p['pose'][2]+origin[2]-truth[round(p['t'],6)][2]))) for p in poses]
        result['yaw'][mode]=summarize(signed)
    decisions=b.rows(source/'frontend-decisions.jsonl')
    result['frontend_matching']=dict(frames=len(decisions),attempts=sum(d['matching_attempted'] for d in decisions),
        reasons=dict(__import__('collections').Counter(d['reason'] for d in decisions)),
        qualification='fixed cached frontend; includes particle selection and local matching, not a new causal ablation')
    off,on=result['metrics']['off'],result['metrics']['on']
    high=result['calibration']['on']['high_support']
    result['gate']=dict(
        section17_19=result['relative_gate']['success'],
        precision_nondecrease=on['final']['precision_015']>=off['final']['precision_015'],
        recall_drop_at_most_2pp=on['final']['wall_coverage']>=off['final']['wall_coverage']-.02,
        wall_rmse_nonincrease=on['final']['wall_error_rmse_m']<=off['final']['wall_error_rmse_m'],
        path_rmse_nonincrease=on['path_position_error']['rmse_m']<=off['path_position_error']['rmse_m'],
        false_retained_zero=not any(v['retained'] and v['false_xy_gt_030'] for v in result['loop_errors']),
        high_support_precision=bool(high['n'] and high['precision']>=.90),
        score_ece_le_010=result['calibration']['on']['support']['score_ece']<=.10,
        absolute_precision=on['final']['precision_015']>=.90,
        absolute_recall=on['final']['wall_coverage']>=.70,
        absolute_wall_rmse=on['final']['wall_error_rmse_m']<=.15,
        absolute_path_rmse=on['path_position_error']['rmse_m']<=.25,
        original_tour_complete=baseline['tour']['completed'])
    result['passed']=all(result['gate'].values())
    result['gt_scope']='evaluation only; start SE2 alignment, no ICP, no model fitting'
    b.dump(b.EXP/'results'/f'{case}.json',result)
    gt=np.array([v[:2] for v in truth.values()])
    return result,rects,gt,displays


def plot(results):
    sys.path.insert(0,str(b.ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    out=b.EXP/'figures'
    out.mkdir(exist_ok=True)
    fig,axes=plt.subplots(2,2,figsize=(11,9))
    for row,(result,rects,gt,displays) in enumerate(results):
        for col,mode in enumerate(('off','on')):
            ax=axes[row,col]
            for x,y,hx,hy in rects:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7'))
            xy,scores,path=displays[mode]
            sc=ax.scatter(*xy.T,c=scores,cmap='Blues',vmin=0,vmax=1,s=8,marker='s')
            ax.plot(*path.T,color='#ed7d31',lw=.9,label='Estimate')
            ax.plot(*gt.T,color='#338855',ls='--',lw=.8,label='GT (evaluation)')
            q=result['metrics'][mode]['final']
            ax.set(aspect='equal',xlabel='world x (m)',ylabel='world y (m)',
                title=f"{result['case']} {mode} | P {q['precision_015']:.1%} / R {q['wall_coverage']:.1%}")
            ax.legend(fontsize=7)
            fig.colorbar(sc,ax=ax,label='Occupancy (diagnostic)' if mode=='off' else 'TSDF support (not probability)')
    fig.tight_layout()
    fig.savefig(out/'maps.png',dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,(result,*_) in zip(axes,results):
        for name,curve in [('off occupancy',result['calibration']['off']['occupancy_diagnostic']),
                           ('on support',result['calibration']['on']['support']),
                           ('on occupancy (diagnostic)',result['calibration']['on']['occupancy_diagnostic'])]:
            bins=[v for v in curve['bins'] if v['n']]
            ax.plot([v['mean_score'] for v in bins],[v['precision'] for v in bins],'o-',label=name)
        ax.plot([0,1],[0,1],':',color='.5')
        ax.set(xlim=(0,1),ylim=(0,1),xlabel='Score; support is NOT probability',ylabel='True-wall fraction within 0.15 m',title=result['case'])
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out/'calibration.png',dpi=140)
    plt.close(fig)


def main():
    assert not (b.EXP/'results/comparison.json').exists(), 'ONE_SCORE_RUN_ONLY'
    for case in ('forward','reverse'):
        out=b.RAW/case
        receipt=b.load(out/'prediction.json')
        assert all(b.sha(out/p)==h for p,h in receipt['hashes'].items()), 'PREDICTION_SEAL_CHANGED'
    (b.EXP/'results').mkdir(exist_ok=True)
    results=[evaluate(case) for case in ('forward','reverse')]
    plot(results)
    b.dump(b.EXP/'results/comparison.json',[r[0] for r in results])
    manifest={str(p.relative_to(b.RAW)):dict(sha256=b.sha(p),bytes=p.stat().st_size)
              for p in sorted(b.RAW.rglob('*')) if p.is_file()}
    b.dump(b.EXP/'results/raw-manifest.json',dict(root=str(b.RAW),files=manifest,remote_backup=False))
    for result,*_ in results:
        print(json.dumps({k:result[k] for k in ('case','gate','yaw','loop_counts')},ensure_ascii=False))
    assert 'mujoco' not in sys.modules


if __name__=='__main__':main()
