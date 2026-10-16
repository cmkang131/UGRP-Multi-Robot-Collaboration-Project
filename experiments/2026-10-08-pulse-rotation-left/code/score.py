"""Frozen egomap31 metrics applied only after both replay predictions are sealed."""
import importlib.util
import sys
import numpy as np
from replay import ROOT,EXP,RAW,OUT,load,rows,sha,dump
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap


def main():
    seals={mode:load(OUT/mode/'seal.json') for mode in ('off','on')}
    for mode,s in seals.items():
        for p,h in s['files'].items():assert sha(OUT/mode/p)==h,p
    spec=importlib.util.spec_from_file_location('eg31_metric',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    old=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    truth={round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
    first=truth[min(truth)]
    origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    walls=np.array([r['center_m']+r['half_extents_m'] for r in load(RAW/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    samples=metric.wall_samples(walls)
    cameras=rows(RAW/'eval_only/camera.jsonl')
    visible=old.in_view(samples,cameras,walls)
    curves={}
    def evaluate(pred,graph=False):
        poses=pred['poses']
        times=[p['t'] for p in poses]
        actual=np.array([truth[round(t,6)]['robot_xyz_m'][:2] for t in times])
        estimated=transform([p['pose'][:2] for p in poses],origin)
        error=np.linalg.norm(estimated-actual,axis=1)
        yaw=wrap(np.array([p['pose'][2]+origin[2]-truth[round(p['t'],6)]['robot_yaw_rad'] for p in poses]))
        cells=np.array([c for c in pred['grid']['cells'] if c[2]>0]).reshape(-1,3)
        xy=transform((cells[:,:2]+.5)*.1,origin)
        q,covered=metric.quality(xy,walls,samples)
        region=old.in_view(xy,cameras,walls)
        correct=metric.boundary_dist(xy,walls)<=.15
        result=dict(endpoint_error_m=float(error[-1]),path_rmse_m=float(np.sqrt(np.mean(error**2))),
            yaw_end_deg=float(np.degrees(yaw[-1])),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw**2)))),
            yaw_abs_p50_deg=float(np.degrees(np.median(abs(yaw)))),yaw_abs_p95_deg=float(np.degrees(np.quantile(abs(yaw),.95))),
            full_map=q,region=dict(precision=float(correct[region].mean()) if region.any() else None,
                precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
                recall=float(covered[visible].mean()),recalled_samples=int(covered[visible].sum()),
                visible_samples=int(visible.sum()),total_samples=len(samples)),
            occupied_cells=len(cells),mapped_frames=len(pred['ledger']),n=len(poses))
        curve=dict(t=times,yaw_error_deg=np.degrees(yaw),xy_error_m=error,estimated=estimated,actual=actual)
        if not graph:
            sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.asarray(p['covariance'])[:2,:2]).max()) for p in poses])
            result.update(sigma_xy_m=float(sigma[-1]),error_sigma_ratio=float(error[-1]/sigma[-1]),
                          over_2sigma=int((error>2*sigma).sum()),resamples=pred['grid']['resamples'])
            curve['sigma_xy_m']=sigma
        return result,curve
    report=dict(source=seals['on']['source_sha'],physical_runs=0,modes={},
        qualification='Same egomap31 recorded RGB/commands, no new trajectory. Potential visibility excludes object/self occlusion. Graph has no calibrated covariance.',
        recorded_coverage=load(ROOT/'experiments/2026-10-08-active-frontier-audit/results/new-seed.json')['coverage'])
    for mode in ('off','on'):
        pred=load(OUT/mode/'prediction.json')
        graph=load(OUT/mode/'graph.json')
        front,curve=evaluate(pred)
        back,_=evaluate(graph,True)
        report['modes'][mode]=dict(frontend=front,graph=back,loop_counts=graph['diagnostics'].get('loop_counts'),
                                 motion_reasons=pred['grid']['correction_counts'])
        curves[mode]=curve
    a,b=[report['modes'][k]['frontend'] for k in ('off','on')]
    reference=load(ROOT/'experiments/2026-10-08-active-frontier-audit/results/comparison.json')['frontend']
    for k in ('endpoint_error_m','path_rmse_m','sigma_xy_m','error_sigma_ratio','yaw_end_deg','yaw_rmse_deg','full_map','region'):
        assert a[k]==reference[k],('BASELINE_METRIC_CHANGED',k)
    gates=dict(yaw_rmse_decreases=b['yaw_rmse_deg']<a['yaw_rmse_deg'],endpoint_decreases=b['endpoint_error_m']<a['endpoint_error_m'],
        overconfidence_decreases=b['error_sigma_ratio']<a['error_sigma_ratio'],
        region_precision_non_decreasing=b['region']['precision'] is not None and b['region']['precision']>=a['region']['precision'],
        region_recall_non_decreasing=b['region']['recall']>=a['region']['recall'],
        full_coverage_non_decreasing=b['full_map']['wall_coverage']>=a['full_map']['wall_coverage'],
        wall_rmse_non_increasing=b['full_map']['wall_error_rmse_m']<=a['full_map']['wall_error_rmse_m'])
    report.update(physical_gate=gates,eligible_for_new_seed=all(gates.values()),passed_count=sum(gates.values()),
                  off_golden=load(OUT/'off/golden.json'))
    dump(EXP/'results/replay.json',report)
    dump(OUT/'curves.json',curves)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
    for mode,c in curves.items():
        axes[0].plot(c['t'],c['yaw_error_deg'],label=mode)
        axes[1].plot(c['t'],c['xy_error_m']/c['sigma_xy_m'],label=mode)
    axes[0].set(ylabel='yaw error (deg)',title='egomap31 fixed recording / left gain only')
    axes[0].axhline(0,color='gray',linewidth=.5)
    axes[1].axhline(2,color='gray',linestyle='--',label='2 sigma')
    axes[1].set(ylabel='XY error / sigma',xlabel='SIM time (s)')
    for ax in axes:ax.legend()
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/replay-errors.png',dpi=150)
    print('OFF',a,'ON',b,'GATE',gates,flush=True)


if __name__=='__main__':main()
