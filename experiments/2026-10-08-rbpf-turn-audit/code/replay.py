"""One sealed replay per condition. Graph finalized before separate GT scoring."""
import argparse,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/baseline')
OUT=Path('/Users/changmin/projects/ugrp/outputs/rbpf-turn-audit-v1')
BASE=Path('/Users/changmin/projects/ugrp/outputs/rbpf-insertion-v1/on/prediction.json')
from harness.active_wall_mapping import OPTIONS
from harness.self_wall_memory_robust import SelfWallMemory
from harness.rbpf_motion_gate import install as motion,OPTION as MOTION
from harness.rbpf_insertion import install as insertion,OPTION as INSERT
from harness.rbpf_rejection import install as selective,OPTION as SELECTIVE
from harness.rbpf_composition import install as compose,OPTION as COMPOSE,SEARCH
from harness.rbpf_manhattan import install as manhattan,OPTION as MANHATTAN
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
MODES=('off','all','wide')
def load(p):return json.loads(p.read_text())
def rows(p):
    with p.open() as f:
        for line in f:yield json.loads(line)
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def predict(mode):
    for name,digest in load(RAW/'artifacts.sha256.json').items():assert sha(RAW/name)==digest,name
    out=OUT/mode;out.mkdir(exist_ok=False)
    commands=sorted(rows(RAW/'robots/r3/commands.jsonl'),key=lambda r:r['t'])
    memory=SelfWallMemory('r3',**OPTIONS,self_map_options={'start_time':commands[0]['t']})
    g=motion(memory.self_map,rbpf_update=MOTION)
    if mode=='off':compose(insertion(g,rbpf_insertion=INSERT))
    else:
        selective(g,rbpf_rejection=SELECTIVE)
        compose(g,rbpf_composition=COMPOSE,rbpf_search=SEARCH if mode=='wide' else 'off')
        manhattan(g,yaw_prior=MANHATTAN)
    cursor=0;poses=[]
    for row in rows(RAW/'own-contacts.jsonl'):
        t=row['t']
        while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
            memory.command(commands[cursor]);cursor+=1
        g.odom.advance(t)
        if row['segments']:
            g.observe_contacts_confident(t=t,frame_id=row['frame_id'],robot_id='r3',segments=row['segments'],features=row['features'],camera_xy=row['camera'])
        poses.append(dict(robot_id='r3',t=t,pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
        if len(poses)%200==0:print(mode,len(poses),'frames',len(g.ledger),'inserted',flush=True)
    prediction=dict(grid=g.export(),poses=poses,decisions=g.decisions,ledger=g.ledger)
    dump(out/'prediction.json',prediction)
    if mode=='off':
        assert (out/'prediction.json').read_bytes()==BASE.read_bytes(),'DEFAULT_BYTES_CHANGED'
        dump(out/'byte-verification.json',dict(equal=True,reference=str(BASE),sha256=sha(BASE)))
    # Switchable constraints are a postprocessing result, never fed to the RBPF.
    graph=memory.finalize_pose_graph([{k:p[k] for k in ('robot_id','t','pose')} for p in poses])
    dump(out/'graph.json',dict(grid=memory._graph_view.export(),**graph))
    dump(out/'seal.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        gt_read=False,files={name:sha(out/name) for name in ('prediction.json','graph.json')},
        inputs={name:sha(RAW/name) for name in ('own-contacts.jsonl','robots/r3/commands.jsonl')}))
    assert 'mujoco' not in sys.modules
    print(mode,'sealed frontend + switchable graph',flush=True)


def score():
    for mode in MODES:
        for name,digest in load(OUT/mode/'seal.json')['files'].items():assert sha(OUT/mode/name)==digest
    # Only after all three predictions and graph outputs are sealed.
    spec=importlib.util.spec_from_file_location('visibility',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metrics
    truth={round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
    start=truth[min(truth)];origin=[*start['robot_xyz_m'][:2],start['robot_yaw_rad']]
    walls=np.array([w['center_m']+w['half_extents_m'] for w in load(RAW/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
    samples=metrics.wall_samples(walls);cameras=list(rows(RAW/'eval_only/camera.jsonl'))
    visible=old.in_view(samples,cameras,walls)
    result=dict(modes={},physical_runs=0,coverage=load(ROOT/'experiments/2026-10-07-rbpf-motion-gate/results/baseline.json')['coverage'],
                qualifications=['Same recorded DEV acquisition; not a new control run.','Potential visibility uses GT camera FOV, 4m and wall-only occlusion.','Graph covariance unavailable; no graph e/sigma or fake posterior reported.'])
    curves={}
    def evaluate(pred,graph=False):
        poses=pred['poses'];g=pred['grid'];times=[p['t'] for p in poses]
        actual=np.array([truth[round(t,6)]['robot_xyz_m'][:2] for t in times])
        estimated=transform([p['pose'][:2] for p in poses],origin)
        error=np.linalg.norm(estimated-actual,axis=1)
        yaw=wrap(np.array([p['pose'][2]+origin[2]-truth[round(p['t'],6)]['robot_yaw_rad'] for p in poses]))
        cells=np.array([c for c in g['cells'] if c[2]>0]).reshape(-1,3)
        occupied=transform((cells[:,:2]+.5)*.1,origin)
        quality,cover=metrics.quality(occupied,walls,samples)
        region=old.in_view(occupied,cameras,walls);correct=metrics.boundary_dist(occupied,walls)<=.15
        r=dict(endpoint_error_m=float(error[-1]),path_rmse_m=float(np.sqrt(np.mean(error**2))),
            yaw_end_deg=float(np.degrees(yaw[-1])),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw**2)))),
            occupied_cells=len(cells),inserted_frames=len(pred['ledger']),full_map=quality,
            region=dict(precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
                precision=float(correct[region].mean()) if region.any() else None,
                recall_samples=int(cover[visible].sum()),visible_samples=int(visible.sum()),total_samples=len(samples),
                recall=float(cover[visible].mean())))
        if not graph:
            sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.array(p['covariance'])[:2,:2]).max()) for p in poses])
            r.update(sigma_xy_m=float(sigma[-1]),error_sigma_ratio=float(error[-1]/sigma[-1]),over_2sigma=int((error>2*sigma).sum()),pose_n=len(poses),
                resamples=g['resamples'],neff=float(1/np.sum(np.square(g['weights']))),
                rejected_resamples=sum(d.get('resampled',False) for d in pred['decisions'] if d['status']=='rejected'),
                rejected_sensor_updates=sum(d.get('sensor_weight_update',False) for d in pred['decisions'] if d['status']=='rejected'),
                reasons=dict(Counter(d['reason'] for d in pred['decisions'])))
        return r,dict(t=times,yaw_error_deg=np.degrees(yaw).tolist(),xy_error_m=error.tolist())
    for mode in MODES:
        pred=load(OUT/mode/'prediction.json');graph=load(OUT/mode/'graph.json')
        front,c=evaluate(pred);back,bc=evaluate(graph,True)
        result['modes'][mode]=dict(frontend=front,graph=back,graph_diagnostics=graph['diagnostics'],seal=load(OUT/mode/'seal.json'))
        curves[mode]=dict(frontend=c,graph=bc)
    baseline=result['modes']['off']['frontend']
    for mode in ('all','wide'):
        r=result['modes'][mode];f=r['frontend']
        r['software_gate']=dict(insertion_55=f['inserted_frames']==55,rejected_weight_zero=f['rejected_sensor_updates']==0,rejected_resample_zero=f['rejected_resamples']==0)
        r['performance_gate']=dict(within_2sigma=f['error_sigma_ratio']<=2.,precision_improves=f['region']['precision'] is not None and f['region']['precision']>baseline['region']['precision'])
    dump(EXP/'results/comparison.json',result);dump(OUT/'curves.json',curves)
    for mode,r in result['modes'].items():print(mode,json.dumps({k:v for k,v in r.items() if k not in ('graph_diagnostics','seal')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=[*MODES,'score']);a=p.parse_args()
    score() if a.mode=='score' else predict(a.mode)
