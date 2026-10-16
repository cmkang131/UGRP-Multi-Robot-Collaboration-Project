"""Evaluate sealed final graph; never feeds GT to prediction. No new physics."""
import copy,importlib.util,sys
import numpy as np
import profile_graph as p
from harness.self_odom_grid import transform


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def rows(path):return [p.json.loads(s) for s in path.read_text().splitlines()]


def main():
    benchmark=p.load(p.RAW/'benchmark.json')
    view=p.RAW/'combined-cold';graph=p.load(view/'graph.json');grid=p.load(view/'grid.json')
    stats=p.load(view/'stats.json')
    assert p.hashlib.sha256(p.encoded(graph)).hexdigest()==stats['graph_sha256']
    assert p.hashlib.sha256(p.encoded(grid)).hexdigest()==stats['grid_sha256']
    # Prediction is now sealed. Start-pose transform is evaluation-only.
    old=p.ROOT/'experiments/2026-10-08-navfn-start-recovery'
    score=module('metric',p.ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    sys.path.insert(0,str(p.ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    actual=rows(p.EP/'eval_only/trajectory.jsonl')
    truth={round(r['t'],6):np.array([*r['robot_xyz_m'][:2],r['robot_yaw_rad']]) for r in actual}
    origin=truth[min(truth)]
    walls=np.array([r['center_m']+r['half_extents_m'] for r in p.load(p.EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    cells=np.array([c for c in grid['cells'] if c[2]>0]).reshape(-1,3)
    xy=transform((cells[:,:2]+.5)*.1,origin);samples=metric.wall_samples(walls)
    q,cover=metric.quality(xy,walls,samples)
    cameras=rows(p.EP/'eval_only/camera.jsonl')
    visible=score.in_view(samples,cameras,walls);region=score.in_view(xy,cameras,walls)
    correct=metric.boundary_dist(xy,walls)<=.15
    path=[r for r in graph['poses'] if round(r['t'],6) in truth]
    estimated=transform([r['pose'][:2] for r in path],origin)
    gt=np.array([truth[round(r['t'],6)][:2] for r in path]);error=np.linalg.norm(estimated-gt,axis=1)
    support={tuple(r['cell']):r['support_score'] for r in graph['wall_evidence']['cells']}
    confidence=np.array([support.get(tuple(c[:2]),0.) for c in cells])
    result=copy.deepcopy(p.load(old/'results/new-seed.json'))
    result.update(prediction_view='completed_graph_offline_egomap48',full_map=q,
        observed_region=dict(precision=float(correct[region].mean()),precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
            recall=float(cover[visible].mean()),recalled_samples=int(cover[visible].sum()),visible_samples=int(visible.sum()),
            visible_wall_fraction=float(visible.mean()),sampled_wall_length_proxy_m=float(visible.sum())*.1,
            qualification='Actual camera FOV/range and wall-only occlusion; object/self occlusion unmodelled'),
        path=dict(n=len(error),rmse_m=float(np.sqrt(np.mean(error**2))),end_m=float(error[-1]),missing_gt_samples=len(graph['poses'])-len(path)),
        calibration=dict(occupancy_ece_diagnostic=score.calibration(1/(1+np.exp(-cells[:,2])),correct),
            support_score_gap=score.calibration(confidence,correct),qualification='TSDF support is NOT probability'),
        loop_counts=graph['diagnostics']['loop_counts'],switch_counts=graph['diagnostics']['switch_counts'])
    result['coverage'].update(occupied_cells=len(cells),mapped_frames=len(graph['ledger']))
    result['criteria']=dict(coverage_ge_080=q['wall_coverage']>=.8,region_precision_ge_0636=result['observed_region']['precision']>=.636)
    result['criteria_count']=sum(result['criteria'].values());result['passed']=all(result['criteria'].values())
    result['qualification']='Offline finalization only; acquisition HOST_ERROR remains. Last pose has no GT and is excluded. Original egomap47 criteria, no retuning.'
    prior=p.load(p.ROOT/'experiments/2026-10-08-frontier-duration/conditions/B/results/report.json')
    p.dump(p.EXP/'results/final.json',result)
    p.dump(p.EXP/'results/comparison.json',dict(egomap46_B=prior,egomap47_frontend=p.load(old/'results/new-seed.json'),egomap48_final=result,no_pooling=True))
    p.dump(p.EXP/'results/benchmark.json',benchmark)
    sys.path.insert(0,str(p.ROOT/'outputs/self-map-plot-deps'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,(ax,bx)=plt.subplots(1,2,figsize=(12,5))
    for x,y,hx,hy in walls:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7'))
    dots=ax.scatter(xy[:,0],xy[:,1],c=confidence,s=12,cmap='Blues',vmin=0,vmax=1)
    fig.colorbar(dots,ax=ax,label='TSDF support (not probability)')
    actual_xy=np.array([r['robot_xyz_m'][:2] for r in actual])
    ax.plot(*actual_xy.T,'--',color='green',label='Actual (evaluation)')
    ax.plot(*estimated.T,color='orange',label='Own final graph path')
    ax.set(aspect='equal',xlabel='m',ylabel='m',title=f'Seed47001 final graph: {len(cells)} cells / {len(graph["ledger"])} scans')
    ax.legend(fontsize=8)
    for label,key in [('occupancy','occupancy_ece_diagnostic'),('support','support_score_gap')]:
        bins=[b for b in result['calibration'][key]['bins'] if b['n']]
        bx.plot([b['score'] for b in bins],[b['precision'] for b in bins],'o-',label=label)
        for b in bins:bx.annotate(str(b['n']),(b['score'],b['precision']),fontsize=7)
    bx.plot([0,1],[0,1],'--',color='.7');bx.legend()
    bx.set(xlabel='Score (support not probability)',ylabel='Actual wall fraction',xlim=(0,1),ylim=(0,1),title='Counts at each bin; no calibration tuning')
    fig.tight_layout();(p.EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(p.EXP/'figures/final-map.png',dpi=140);plt.close(fig)
    print(p.json.dumps({k:result[k] for k in ('full_map','observed_region','path','criteria','coverage')},indent=2))

if __name__=='__main__':main()
