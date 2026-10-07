"""Post-seal evaluation and chronological 4x movie; no simulator imports."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys,subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-recovery-v1')
EP=RAW/'new-seed'
sys.path.insert(0,str(ROOT))
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.self_wall_evidence import build_evidence
from scripts.run_active_wall_recovery import dump


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(line) for line in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metrics_module():
    spec=importlib.util.spec_from_file_location('frozen_eg22_score',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.RAW=RAW;m.EXP=EXP
    def prediction(case,partial=False):m.verify(RAW/case);return RAW/case
    m.prediction=prediction
    return m


def score():
    m=metrics_module();m.verify(EP)
    partial=load(EP/'result.json')['prediction_view']!='completed_graph'
    m.evaluate('new-seed',partial=partial)
    # Covariance belongs to frontend; graph's optimized endpoint is separate.
    truth={round(r['t'],6):r for r in rows(EP/'eval_only/trajectory.jsonl')}
    first=truth[min(truth)];origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    poses=rows(EP/'frontend-covariances.jsonl')
    est=transform([p['pose'][:2] for p in poses],origin)
    gt=np.array([truth[round(p['t'],6)]['robot_xyz_m'][:2] for p in poses])
    errors=np.linalg.norm(est-gt,axis=1)
    sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.array(p['covariance'])[:2,:2]).max()) for p in poses])
    yaw=wrap(np.array([p['pose'][2]+origin[2]-truth[round(p['t'],6)]['robot_yaw_rad'] for p in poses]))
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    walls=np.array([r['center_m']+r['half_extents_m'] for r in load(EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    g=load(EP/'frontend-grid.json');cells=np.array([c for c in g['cells'] if c[2]>0]).reshape(-1,3)
    xy=transform((cells[:,:2]+.5)*.1,origin)
    samples=metric.wall_samples(walls);q,cover=metric.quality(xy,walls,samples)
    cameras=rows(EP/'eval_only/camera.jsonl');visible=m.in_view(samples,cameras,walls);region=m.in_view(xy,cameras,walls)
    correct=metric.boundary_dist(xy,walls)<=.15
    decisions=load(EP/'decisions.json')
    baseline=load(ROOT/'experiments/2026-10-08-rbpf-wide-confirm/results/new-seed.json')
    baseline_uncertainty=load(ROOT/'experiments/2026-10-08-rbpf-wide-confirm/results/comparison.json')['frontend']
    front=dict(endpoint_error_m=float(errors[-1]),sigma_xy_m=float(sigma[-1]),error_sigma_ratio=float(errors[-1]/sigma[-1]),
        over_2sigma=int((errors>2*sigma).sum()),n=len(poses),path_rmse_m=float(np.sqrt(np.mean(errors**2))),
        yaw_end_deg=float(np.degrees(yaw[-1])),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw**2)))),
        full_map=q,region=dict(precision=float(correct[region].mean()) if region.any() else None,
            precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
            recall=float(cover[visible].mean()),recalled_samples=int(cover[visible].sum()),visible_samples=int(visible.sum()),total_samples=len(samples)),
        occupied_cells=len(cells),mapped_frames=len(load(EP/'frontend-ledger.json')),resamples=g['resamples'],
        rejected_resamples=sum(bool(d.get('resampled')) for d in decisions if d['status']=='rejected'),
        rejected_csm_updates=sum(bool(d.get('sensor_weight_update')) for d in decisions if d['status']=='rejected'))
    gate=dict(within_2sigma=front['error_sigma_ratio']<=2,
        precision_improves=front['region']['precision'] is not None and front['region']['precision']>35/241)
    result=dict(baseline=baseline,baseline_uncertainty=baseline_uncertainty,
        fresh=load(EXP/'results/new-seed.json'),frontend=front,egomap27_gate=gate,
        qualification='Single preregistered fresh-seed acquisition versus egomap28. Graph sigma unavailable.')
    controller=rows(EP/'own-controller.jsonl')
    hold=sum(r['command']['kind']=='hold' for r in controller)
    result['hold']=dict(n=hold,total=len(controller),fraction=hold/len(controller),baseline_n=695,baseline_total=891)
    fresh=result['fresh']
    result['recovery_gate']=dict(recorded=fresh['acquisition']['status']=='RECORDED',
        distance=fresh['coverage']['travelled_m']>1.0900284644319769,
        area=fresh['coverage']['footprint_union_m2']>.4850000000000001,
        hold_fraction=hold/len(controller)<695/891,no_contact=fresh['wall_contacts']==0)
    dump(EXP/'results/comparison.json',result)
    dump(RAW/'uncertainty-curve.json',dict(t=[p['t'] for p in poses],error=errors,sigma=sigma,yaw_error_deg=np.degrees(yaw)))
    print(json.dumps(dict(frontend=front,egomap27_gate=gate),indent=2))


if __name__=='__main__':score()
