"""Predict from own ledger first; separate post-seal GT evaluation. No physics."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,importlib.util,json,math,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-cell-attribution-v1')
PREDICTIONS=RAW/'predictions'
EPISODES={'31001':Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed'),
          '32002':Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')}
sys.path.insert(0,str(ROOT))
from harness.self_wall_validation import validated_grid,OPTION
from harness.self_odom_grid import transform

def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')


def predict():
    for seed,ep in EPISODES.items():
        out=PREDICTIONS/seed
        if out.exists():raise FileExistsError(out)
        expected=load(ep/'artifacts.sha256.json')
        for name in ('grid.json','graph.json','frontend-covariances.jsonl'):
            assert sha(ep/name)==expected[name]
        original=load(ep/'grid.json')
        ledger=[dict(r,robot_id='r3') for r in load(ep/'graph.json')['ledger']]
        off,e=validated_grid(original,None,robot_id='r3')
        assert off is original and e is None
        on,support=validated_grid(original,ledger,robot_id='r3',wall_validation=OPTION)
        out.mkdir(parents=True)
        # Off retains not just numeric values, but the original JSON bytes.
        (out/'off.json').write_bytes((ep/'grid.json').read_bytes())
        dump(out/'on.json',on);dump(out/'support.json',support)
        assert (out/'off.json').read_bytes()==(ep/'grid.json').read_bytes()
        dump(out/'seal.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            episode=str(ep),gt_parsed=False,physics_runs=0,options=dict(wall_validation=OPTION),
            input_hashes={name:expected[name] for name in ('grid.json','graph.json','frontend-covariances.jsonl')},
            files={name:sha(out/name) for name in ('off.json','on.json','support.json')},off_bytes_identical=True))
        print(seed,'sealed',flush=True)


def score():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    spec=importlib.util.spec_from_file_location('old_score',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    figure,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
    all_results={}
    for si,(seed,ep) in enumerate(EPISODES.items()):
        out=PREDICTIONS/seed;seal=load(out/'seal.json')
        for name,digest in seal['files'].items():assert sha(out/name)==digest
        for name,digest in seal['input_hashes'].items():assert sha(ep/name)==digest
        expected=load(ep/'artifacts.sha256.json')
        for name in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','inputs/static_map.json'):
            assert sha(ep/name)==expected[name]
        truth=rows(ep/'eval_only/trajectory.jsonl');first=truth[0]
        origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
        cams=rows(ep/'eval_only/camera.jsonl')
        walls=np.array([r['center_m']+r['half_extents_m'] for r in load(ep/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
        samples=metric.wall_samples(walls);visible=old.in_view(samples,cams,walls)
        pose=rows(ep/'frontend-covariances.jsonl')
        estimated=transform([p['pose'][:2] for p in pose],origin)
        actual=np.array([r['robot_xyz_m'][:2] for r in truth])
        summary=dict(seed=seed,physics=0,pose_replay=False,pose_lineage_unchanged=True,
            source_sha=seal['source_sha'],off_bytes_identical=seal['off_bytes_identical'],
            rgb_frames=len(rows(ep/'robots/r3/frames.jsonl')),controller_frames=len(rows(ep/'own-controller.jsonl')),
            inserted_frames=len(load(ep/'graph.json')['ledger']),potential_visible_samples=int(visible.sum()),total_samples=len(samples),
            recorded_acquisition_footprint_m2=2.39 if seed=='31001' else 2.2675,
            travelled_m=float(np.linalg.norm(np.diff(actual,axis=0),axis=1).sum()),conditions={})
        support=load(out/'support.json')
        summary['support']=dict(candidates=support['candidates'],confirmed=support['confirmed'],
            view_count_histogram=dict(sorted(Counter(c['weight'] for c in support['cells']).items())),
            correlated_hits_skipped=sum(e['correlated_support_skipped'] for e in support['events']),
            cleared=sum(e['cleared_support'] for e in support['events']),
            frames_adding_support=sum(e['new_support']>0 for e in support['events']))
        false=load(RAW/f'{seed}-false-cells.json')
        for i,condition in enumerate(('off','on')):
            grid=load(out/f'{condition}.json')
            cells=np.array([c for c in grid['cells'] if c[2]>0]).reshape(-1,3)
            xy=transform((cells[:,:2]+.5)*.1,origin)
            q,covered=metric.quality(xy,walls,samples)
            region=old.in_view(xy,cams,walls);d=metric.boundary_dist(xy,walls);correct=d<=.15
            kept=set(map(tuple,cells[:,:2].astype(int)))
            counts=Counter(c['category'] for c in false if tuple(c['cell']) in kept)
            result=dict(full=q,occupied_cells=len(cells),correct_cells=int(correct.sum()),
                covered_samples=int(covered.sum()),region=dict(precision=float(correct[region].mean()) if region.any() else None,
                precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
                recall=float(covered[visible].mean()),recalled_samples=int(covered[visible].sum()),visible_samples=int(visible.sum())),
                surviving_false_categories=dict(counts))
            result['absolute_gate']=dict(precision=q['precision_015'] is not None and q['precision_015']>=.90,
                recall=q['wall_coverage']>=.70,wall_rmse=q['wall_error_rmse_m'] is not None and q['wall_error_rmse_m']<=.15)
            summary['conditions'][condition]=result
            ax=axes[si,i]
            for x,y,hx,hy in walls:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.7'))
            ax.plot(actual[:,0],actual[:,1],color='green',lw=.8,label='actual path (eval)')
            ax.plot(estimated[:,0],estimated[:,1],color='orange',lw=.8,label='own estimated path')
            ax.scatter(xy[correct,0],xy[correct,1],s=8,c='navy',label='wall distance <= .15m')
            ax.scatter(xy[~correct,0],xy[~correct,1],s=8,c='crimson',label='false occupied cell')
            precision='NA' if q['precision_015'] is None else f'{q["precision_015"]:.1%}'
            rmse='NA' if q['wall_error_rmse_m'] is None else f'{q["wall_error_rmse_m"]:.3f}'
            ax.set_title(f'{seed} {condition}: P {precision} / R {q["wall_coverage"]:.1%}\nRMSE {rmse}m, cells {len(cells)}, scans {summary["inserted_frames"]}')
            ax.set_aspect('equal');ax.set_xlim(-1.6,6.6);ax.set_ylim(-4.2,2.8)
            ax.set_xlabel('world x (evaluation only), m');ax.set_ylabel('world y, m')
        axes[si,0].legend(fontsize=7,loc='lower left')
        summary['absolute_gate_pass_count']=sum(summary['conditions']['on']['absolute_gate'].values())
        dump(EXP/f'results/{seed}-comparison.json',summary)
        all_results[seed]=summary
        print(json.dumps(summary,indent=2),flush=True)
    figure.savefig(EXP/'figures/maps.png',dpi=140)
    dump(EXP/'results/comparison.json',all_results)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','score']);a=p.parse_args()
    predict() if a.mode=='predict' else score()
