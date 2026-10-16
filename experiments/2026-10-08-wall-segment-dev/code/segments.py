"""Frozen recorded-trajectory representation comparison; GT only after seal."""
import hashlib,importlib.util,json,math,sys,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.active_camera import SEARCH
from harness.self_wall_segment_points import contact_points
from harness.self_wall_segments import build_segment_map
from harness.self_odom_grid import transform,ray_cells
from scripts.run_active_wall_nav2 import dump
EXP=Path(__file__).resolve().parents[1]
OUT=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1')
PRIOR=Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-left-v1')
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed')
def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def predict():
    import cv2
    frozen=load(EXP/'freeze.json')
    assert all(sha(ROOT/p)==h for p,h in frozen['hashes'].items())
    folder=OUT/'segment-predictions'
    folder.mkdir(exist_ok=False)
    cache={}
    frames={r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
    for mode in ('off','on'):
        seal=load(PRIOR/mode/'seal.json')
        assert all(sha(PRIOR/mode/p)==h for p,h in seal['files'].items())
        pred=load(PRIOR/mode/'prediction.json')
        cov={p['frame_id']:p['covariance'] for p in pred['poses']}
        observations={}
        for row in pred['ledger']:
            key=row['frame_id']
            if key not in cache:
                path=RAW/frames[key]['path']
                rgb=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
                cache[key]={**contact_points(rgb,SEARCH),'rgb_sha256':sha(path)}
            observations[key]={**cache[key],'pose_covariance':cov[key]}
        lines=build_segment_map([dict(r,robot_id='r3') for r in pred['ledger']],observations,
                               robot_id='r3',wall_map='segments_v1')
        dump(folder/(mode+'.json'),dict(map=lines,observations=observations,source_prediction_sha256=sha(PRIOR/mode/'prediction.json')))
        print(mode,'sealed',lines['counts'],len(lines['segments']),'lines',flush=True)
    dump(folder/'seal.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        gt_parsed=False,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()}))
    assert 'mujoco' not in sys.modules


def score():
    folder=OUT/'segment-predictions'
    sealed=load(folder/'seal.json')
    assert all(sha(folder/p)==h for p,h in sealed['files'].items())
    spec=importlib.util.spec_from_file_location('eg31_metric',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    truth=rows(RAW/'eval_only/trajectory.jsonl')
    origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    walls=np.array([r['center_m']+r['half_extents_m'] for r in load(RAW/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    samples=metric.wall_samples(walls)
    cameras=rows(RAW/'eval_only/camera.jsonl')
    visible=m.in_view(samples,cameras,walls)
    def quality(local):
        xy=transform(np.asarray(local).reshape(-1,2),origin)
        q,cover=metric.quality(xy,walls,samples)
        view=m.in_view(xy,cameras,walls)
        correct=metric.boundary_dist(xy,walls)<=.15
        return dict(full=q,region=dict(precision=float(correct[view].mean()) if view.any() else None,
            correct=int(correct[view].sum()),n=int(view.sum()),recall=float(cover[visible].mean()),
            recalled=int(cover[visible].sum()),visible=int(visible.sum()),total=len(samples)))
    modes={}
    graphics={}
    for mode in ('off','on'):
        p=load(PRIOR/mode/'prediction.json')
        s=load(folder/(mode+'.json'))
        grid=(np.array([c[:2] for c in p['grid']['cells'] if c[2]>0])+.5)*.1
        dense=[]
        keys=set()
        for seg in s['map']['segments']:
            a,b=np.array(seg['endpoints_m'])
            dense.extend(np.linspace(a,b,max(2,int(math.ceil(np.linalg.norm(b-a)/.05))+1)))
            keys.update(ray_cells(a,b,.1))
        raster=(np.array(sorted(keys)).reshape(-1,2)+.5)*.1
        contacts=[]
        for row in p['ledger']:
            points=s['observations'][str(row['frame_id'])]['points']
            contacts.extend(transform(np.asarray(points).reshape(-1,2),row['pose']))
        qgrid,qseg,qcontinuous,qpoints=[quality(x) for x in (grid,raster,dense,contacts)]
        dist=metric.boundary_dist(transform(grid,origin),walls)
        fp=dist>.15
        bound=.15+.1/math.sqrt(2)
        a,b=qgrid['full'],qseg['full']
        gaps=lambda q:np.array([max(0.,.9-q['precision_015']),max(0.,.7-q['wall_coverage']),max(0.,q['wall_error_rmse_m']-.15)])
        da,db=gaps(a),gaps(b)
        closer=bool(np.all(db<=da) and np.any(db<da))
        modes[mode]=dict(grid=qgrid,segments_raster=qseg,segments_continuous=qcontinuous,raw_contact_points=qpoints,
            segment_count=len(s['map']['segments']),length_m=sum(float(np.linalg.norm(np.diff(x['endpoints_m'],axis=0))) for x in s['map']['segments']),
            counts=s['map']['counts'],raster_cells=len(raster),continuous_samples=len(dense),
            quantization=dict(false_cells=int(fp.sum()),beyond_cell_center_bound=int((dist>bound).sum()),bound_m=bound),
            target_gaps_grid=da,target_gaps_segments=db,closer_for_export_start=closer,
            original_absolute_gate=dict(precision=b['precision_015']>=.9,recall=b['wall_coverage']>=.7,rmse=b['wall_error_rmse_m']<=.15))
        graphics[mode]=(grid,s['map']['segments'],p['poses'])
    report=dict(source=sealed['source_sha'],modes=modes,export_start=all(x['closer_for_export_start'] for x in modes.values()),
        same_recording=True,physical_runs=0,metric_semantics='main comparison: same 0.1m raster / 0.15m wall tolerance; continuous line samples separately')
    dump(EXP/'results/segments.json',report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    for ax,(mode,(grid,segments,poses)) in zip(axes,graphics.items()):
        for x,y,hw,hh in walls:ax.add_patch(Rectangle((x-hw,y-hh),2*hw,2*hh,color='lightgray'))
        xy=transform(grid,origin)
        ax.scatter(*xy.T,s=5,c='darkorange',alpha=.5,label='grid')
        for i,s in enumerate(segments):
            ends=transform(s['endpoints_m'],origin)
            ax.plot(*ends.T,color='navy',alpha=min(1.,.35+.1*s['observations']),label='segments' if i==0 else None)
        xy=transform([p['pose'][:2] for p in poses],origin)
        ax.plot(*xy.T,c='green',lw=.8,label='estimated path')
        ax.set(title=mode+' (same recording)',aspect='equal',xlabel='m',ylabel='m')
        ax.legend(loc='lower right')
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/segments.png',dpi=140)
    print(json.dumps(report,default=lambda a:a.tolist(),indent=2),flush=True)


if __name__=='__main__':
    if sys.argv[1]=='predict':predict()
    elif sys.argv[1]=='score':score()
    else:raise ValueError('predict or score')
