"""Preregistered dev sweep -> committed operating points -> one held evaluation.

Prediction reads own RGB/ledger only. GT lives exclusively in Evaluator. No physics.
"""
from pathlib import Path
from collections import Counter
import argparse,hashlib,importlib.util,json,math,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-pr-operating-point-v1')
EPISODES={'31001':Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed'),
          '32002':Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')}
COUNTS=range(1,9)
ANGLES=(0,5,15,30,60)
sys.path.insert(0,str(ROOT))
from harness.self_odom_grid import transform,ray_cells
from harness.self_wall_pr import grid_support,segment_support,apply,OPTION
from harness.self_wall_segment_points import contact_points
from harness.self_wall_segments import build_segment_map
from selection import select,gate,closer

FROZEN_FILES=['harness/self_wall_pr.py','harness/self_wall_validation.py','harness/self_wall_segments.py',
 'harness/self_wall_segment_points.py','harness/active_wall_vision.py','harness/active_camera.py',
 'harness/self_odom_grid.py','harness/self_pose_graph.py','harness/wall_confidence.py',
 'experiments/2026-09-26-markerless-probe/markerless_probe.py',
 'experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py',
 'experiments/2026-10-05-ego-wall-map-probe/code/ego_wall_map.py',
 'experiments/2026-10-05-ego-wall-map-probe/code/odom_grid_replay.py',
 'experiments/2026-10-07-active-wall-map/code/score.py',
 'experiments/2026-10-08-wall-pr-operating-point/code/run.py',
 'experiments/2026-10-08-wall-pr-operating-point/code/selection.py']
def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def head():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def unchanged_committed(path):
    relative=str(path.relative_to(ROOT))
    assert subprocess.check_output(['git','show',f'HEAD:{relative}'],cwd=ROOT)==path.read_bytes(),relative
def verify_prediction(seed):
    folder=RAW/seed;seal=load(folder/'seal.json')
    for name,h in seal['files'].items():assert sha(folder/name)==h,name
    for name,h in seal['input_hashes'].items():assert sha(EPISODES[seed]/name)==h,name
    for name,h in seal['code_hashes'].items():assert sha(ROOT/name)==h,name
    return folder
def frozen():
    path=EXP/'freeze.json';unchanged_committed(path)
    spec=load(path)
    for name,h in spec['code_hashes'].items():assert sha(ROOT/name)==h,name
    assert sha(EXP/'results/development.json')==spec['development_sha256']
    return spec


def predict(seed):
    if seed=='32002':frozen()
    folder=RAW/seed
    if folder.exists():raise FileExistsError(folder)
    ep=EPISODES[seed];expected=load(ep/'artifacts.sha256.json')
    names=['grid.json','graph.json','frontend-covariances.jsonl','robots/r3/frames.jsonl']
    for name in names:assert sha(ep/name)==expected[name],name
    grid=load(ep/'grid.json')
    ledger=[dict(r,robot_id='r3') for r in load(ep/'graph.json')['ledger']]
    frames={r['frame_id']:r for r in rows(ep/'robots/r3/frames.jsonl')}
    covariance={r['frame_id']:r['covariance'] for r in rows(ep/'frontend-covariances.jsonl')}
    import cv2
    observations={};rgb_hashes={}
    for row in ledger:
        frame=frames[row['frame_id']];path=ep/frame['path']
        assert sha(path)==frame['sha256']==expected[frame['path']]
        rgb_hashes[frame['path']]=frame['sha256']
        rgb=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
        servo={int(k):v for k,v in frame['commanded_servo'].items()}
        observations[row['frame_id']]={**contact_points(rgb,servo),'pose_covariance':covariance[row['frame_id']]}
    segments=build_segment_map(ledger,observations,robot_id='r3',wall_map='segments_v1')
    supports={'grid':grid_support(grid,ledger,robot_id='r3'),'segments':segment_support(segments,ledger,robot_id='r3')}
    folder.mkdir()
    (folder/'grid.json').write_bytes((ep/'grid.json').read_bytes())
    dump(folder/'segments.json',segments);dump(folder/'support.json',supports);dump(folder/'observations.json',observations)
    if seed=='32002':
        chosen={}
        for kind,selection in frozen()['selected'].items():
            base=grid if kind=='grid' else segments
            point=selection['operating_point']
            if point is None:
                # Empty dev representation: preserve empty outcome without trying new settings.
                view={**base,'cells':[c for c in base['cells'] if c[2]<=0]} if kind=='grid' else {**base,'segments':[]}
            else:view=apply(base,supports[kind],wall_validation=OPTION,**point)
            dump(folder/f'{kind}-selected.json',view)
            chosen[kind]=point
        dump(folder/'applied-operating-points.json',chosen)
    assert 'mujoco' not in sys.modules
    dump(folder/'seal.json',dict(source_sha=head(),seed=seed,gt_parsed=False,physics=0,
        input_hashes={**{n:expected[n] for n in names},**rgb_hashes},
        code_hashes={p:sha(ROOT/p) for p in FROZEN_FILES},
        ledger_frames=len(ledger),rgb_frames=len(frames),actual_contact_columns=sum(len(o['points']) for o in observations.values()),
        files={f.name:sha(f) for f in sorted(folder.iterdir()) if f.is_file()}))
    print(seed,'own-only prediction sealed',len(ledger),'scans',len(segments['segments']),'segments',flush=True)


class Evaluator:
    """GT/camera/scene data only after prediction seal, never passed to predictor."""
    def __init__(self,seed):
        self.seed=seed;self.ep=EPISODES[seed]
        expected=load(self.ep/'artifacts.sha256.json')
        for name in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','inputs/static_map.json'):
            assert sha(self.ep/name)==expected[name]
        truth=rows(self.ep/'eval_only/trajectory.jsonl')
        self.origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
        self.walls=np.array([w['center_m']+w['half_extents_m'] for w in load(self.ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
        self.cameras=rows(self.ep/'eval_only/camera.jsonl')
        sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
        import odom_grid_replay
        self.metric=odom_grid_replay
        spec=importlib.util.spec_from_file_location('frozen_visibility',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        self.in_view=old.in_view;self.samples=self.metric.wall_samples(self.walls)
        self.visible=self.in_view(self.samples,self.cameras,self.walls);self.cache={}

    def measure(self,local):
        xy=transform(np.asarray(local).reshape(-1,2),self.origin)
        q,cover=self.metric.quality(xy,self.walls,self.samples)
        keys=[tuple(np.round(p,10)) for p in xy]
        missing=sorted(set(keys)-set(self.cache))
        if missing:
            value=self.in_view(np.array(missing),self.cameras,self.walls)
            self.cache.update(zip(missing,value.tolist()))
        region=np.array([self.cache[k] for k in keys],bool)
        correct=self.metric.boundary_dist(xy,self.walls)<=.15
        return dict(full=q,correct_cells=int(correct.sum()),sample_count=len(xy),covered_samples=int(cover.sum()),
            region=dict(precision=float(correct[region].mean()) if region.any() else None,
                correct=int(correct[region].sum()),n=int(region.sum()),recall=float(cover[self.visible].mean()),
                recalled=int(cover[self.visible].sum()),visible=int(self.visible.sum()),total=len(self.samples)))

    def representation(self,kind,value):
        if kind=='grid':
            cells=np.array([c[:2] for c in value['cells'] if c[2]>0]).reshape(-1,2)
            result=self.measure((cells+.5)*.1)
            result['size']=dict(occupied_cells=len(cells))
        else:
            keys=set();dense=[];length=0.
            for line in value['segments']:
                a,b=np.array(line['endpoints_m']);length+=float(np.linalg.norm(b-a))
                keys.update(ray_cells(a,b,.1))
                dense.extend(np.linspace(a,b,max(2,int(math.ceil(np.linalg.norm(b-a)/.05))+1)))
            raster=(np.array(sorted(keys)).reshape(-1,2)+.5)*.1
            result=self.measure(raster);result['continuous']=self.measure(dense)
            result['size']=dict(segments=len(value['segments']),length_m=length,raster_cells=len(raster),continuous_samples=len(dense))
        return result


def dev():
    result_path=EXP/'results/development.json'
    if result_path.exists():raise FileExistsError(result_path)
    folder=verify_prediction('31001');evaluate=Evaluator('31001')
    support=load(folder/'support.json');report={}
    for kind in ('grid','segments'):
        baseline=load(folder/f'{kind}.json')
        assert apply(baseline) is baseline
        baseline_bytes=json.dumps(baseline).encode()
        off=evaluate.representation(kind,baseline);candidates=[]
        for angle in ANGLES:
            for n in COUNTS:
                options=dict(min_views=n,min_angle_deg=angle)
                view=apply(baseline,support[kind],wall_validation=OPTION,**options)
                candidates.append(dict(**options,metrics=evaluate.representation(kind,view)))
        assert json.dumps(baseline).encode()==baseline_bytes
        report[kind]=dict(off=off,candidates=candidates,selection=select(candidates))
        print(kind,report[kind]['selection'],flush=True)
    data=dict(source_sha=head(),development_seed='31001',held_seed_opened=False,representations=report,
        prediction_seal_sha256=sha(folder/'seal.json'),code_hashes=load(folder/'seal.json')['code_hashes'])
    dump(result_path,data)
    dump(EXP/'freeze.json',dict(development_seed='31001',held_seed='32002',previously_seen_held_recording=True,
        development_sha256=sha(result_path),code_hashes=data['code_hashes'],
        selected={k:r['selection'] for k,r in report.items()}))


def held():
    point=frozen();folder=verify_prediction('32002')
    path=EXP/'results/held.json'
    if path.exists():raise FileExistsError(path)
    evaluate=Evaluator('32002');report={}
    for kind in ('grid','segments'):
        off=evaluate.representation(kind,load(folder/f'{kind}.json'))
        on=evaluate.representation(kind,load(folder/f'{kind}-selected.json'))
        report[kind]=dict(selection=point['selected'][kind],off=off,on=on,
            absolute_gate=gate(on['full']),**closer(off['full'],on['full']))
    data=dict(source_sha=head(),selection_freeze_sha256=sha(EXP/'freeze.json'),held_seed='32002',
        selection_committed=True,previously_seen_recording=True,representations=report,
        export_start=any(r['export_start'] for r in report.values()),prediction_seal_sha256=sha(folder/'seal.json'))
    dump(path,data)
    print(json.dumps(data,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['predict-dev','dev','predict-held','held']);a=p.parse_args()
    if a.stage.startswith('predict'):predict('31001' if a.stage=='predict-dev' else '32002')
    elif a.stage=='dev':dev()
    else:held()
