"""Fixed detector on/off at recorded poses and insertion times. No pose replay."""
from common import *
from harness.active_wall_vision import observe
from harness.wall_contact_detector import OPTION
from harness.wall_floor_boundary import CONFIG
from harness.wall_confidence import confidence
from harness.self_pose_graph import rebuild
from harness.self_wall_segments import build_segment_map

FROZEN_FILES=['harness/active_wall_vision.py','harness/self_wall_segment_points.py',
 'harness/wall_contact_detector.py','harness/wall_floor_boundary.py','harness/active_camera.py',
 'harness/self_wall_segments.py','harness/wall_confidence.py','harness/self_pose_graph.py',
 'experiments/2026-10-05-ego-wall-map-probe/code/height_free_wall.py',
 'experiments/2026-10-08-wall-contact-types/code/common.py',
 'experiments/2026-10-08-wall-contact-types/code/compare.py']

def frozen():
    path=EXP/'freeze.json';spec=load(path)
    assert subprocess.check_output(['git','show','HEAD:'+str(path.relative_to(ROOT))],cwd=ROOT)==path.read_bytes()
    for name,h in spec['code_hashes'].items():assert sha(ROOT/name)==h,name
    assert sha(EXP/'results/31001-comparison.json')==spec['development_sha256']
    return spec

def predict(seed):
    if seed=='32002':frozen()
    ep=EPISODES[seed];out=RAW/seed/'comparison'
    if out.exists():raise FileExistsError(out)
    oldseal=load(RAW/seed/'off/seal.json')
    assert sha(RAW/seed/'off/points.jsonl')==oldseal['files']['points.jsonl']
    expected=load(ep/'artifacts.sha256.json')
    names=['graph.json','frontend-covariances.jsonl','robots/r3/frames.jsonl','own-contacts.jsonl','grid.json']
    for n in names:assert sha(ep/n)==expected[n]
    ledger=[dict(r,robot_id='r3') for r in load(ep/'graph.json')['ledger']]
    admit={r['frame_id']:r for r in ledger}
    own=rows(ep/'own-contacts.jsonl');frames={r['frame_id']:r for r in rows(ep/'robots/r3/frames.jsonl')}
    cov={r['frame_id']:r for r in rows(ep/'frontend-covariances.jsonl')}
    observations={'off':{r['frame_id']:r for r in rows(RAW/seed/'off/points.jsonl')},'on':{}}
    newledger={'off':[],'on':[]};out.mkdir(parents=True)
    with (out/'on-points.jsonl').open('w') as stream:
        for ix,old in enumerate(own):
            frame=old['frame_id'];f=frames[frame];servo={int(k):v for k,v in f['commanded_servo'].items()}
            image=rgb(ep,f)
            pt=contact_points(image,servo,wall_detector=OPTION)
            pt.update(frame_id=frame,t=f['sim_time'],uv=uv_of(pt['points'],servo).tolist())
            stream.write(json.dumps(pt,allow_nan=False)+'\n');observations['on'][frame]=pt
            if frame in admit:
                for condition in ('off','on'):
                    opt='off' if condition=='off' else OPTION
                    detected=observe(image,servo,body_settling=old['features'][0]['body_settling'],wall_detector=opt)
                    if condition=='off':assert detected=={k:v for k,v in old.items() if k not in ('t','frame_id')},'OFF_OBSERVATION_CHANGED'
                    pose=admit[frame]['pose'];uncertainty=cov[frame]['covariance']
                    weighted=[confidence(s,detected['camera'],features,uncertainty,pose[2]) for s,features in zip(detected['segments'],detected['features'])]
                    row=dict(admit[frame],segments=detected['segments'],camera=detected['camera'],
                        insertion_weights=[c['weight'] for c in weighted],wall_confidence=weighted)
                    newledger[condition].append(row)
                    observations[condition][frame]['pose_covariance']=uncertainty
            if ix%200==0:print(seed,'new detector',ix,flush=True)
    for condition in ('off','on'):
        ll=newledger[condition]
        grid=rebuild('r3',ll).export()
        segments=build_segment_map(ll,observations[condition],robot_id='r3',wall_map='segments_v1')
        dump(out/f'{condition}-grid.json',grid);dump(out/f'{condition}-segments.json',segments)
        dump(out/f'{condition}-ledger.json',ll)
    (out/'historical-grid.json').write_bytes((ep/'grid.json').read_bytes())
    assert 'mujoco' not in sys.modules
    dump(out/'seal.json',dict(source_sha=head(),option=OPTION,configuration=CONFIG,seed=seed,physics=0,gt_parsed=False,
        paired_covariance='saved post-observation covariance for BOTH off/on, not original pre-scan covariance',
        code_hashes={n:sha(ROOT/n) for n in FROZEN_FILES},
        input_hashes={**{n:expected[n] for n in names},**oldseal['rgb_hashes']},
        off_points_sha256=sha(RAW/seed/'off/points.jsonl'),
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))

def evaluator(seed):
    oldcode=ROOT/'experiments/2026-10-08-wall-pr-operating-point/code'
    sys.path.insert(0,str(oldcode))
    spec=importlib.util.spec_from_file_location('frozen_pr_evaluator',oldcode/'run.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod.Evaluator(seed)

def score(seed):
    if seed=='32002':frozen()
    out=RAW/seed/'comparison';seal=load(out/'seal.json');target=EXP/f'results/{seed}-comparison.json'
    if target.exists():raise FileExistsError(target)
    for name,h in seal['files'].items():assert sha(out/name)==h
    for name,h in seal['code_hashes'].items():assert sha(ROOT/name)==h
    for name,h in seal['input_hashes'].items():assert sha(EPISODES[seed]/name)==h
    assert seal['off_points_sha256']==sha(RAW/seed/'off/points.jsonl')
    evaluate=evaluator(seed);ep=EPISODES[seed]
    truth={round(r['t'],6):r for r in rows(ep/'eval_only/trajectory.jsonl')}
    admitted={r['frame_id'] for r in load(ep/'graph.json')['ledger']}
    report={}
    for condition,path in [('off',RAW/seed/'off/points.jsonl'),('on',out/'on-points.jsonl')]:
        errors=[];inserted=[];nonempty=0;inserted_nonempty=0
        for row in rows(path):
            gt=truth[round(row['t'],6)]
            xy=transform(np.asarray(row['points']).reshape(-1,2),[*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
            error=metric.boundary_dist(xy,evaluate.walls);errors.extend(error.tolist());nonempty+=bool(len(xy))
            if row['frame_id'] in admitted:inserted.extend(error.tolist());inserted_nonempty+=bool(len(xy))
        def point_metrics(e):
            return dict(points=len(e),correct=sum(x<=.15 for x in e),precision=float(np.mean(np.array(e)<=.15)) if e else None,
                wall_rmse_m=float(np.sqrt(np.mean(np.square(e)))) if e else None)
        report[condition]=dict(points=point_metrics(errors),inserted_points=point_metrics(inserted),
            nonempty_frames=nonempty,inserted_nonempty_frames=inserted_nonempty,
            grid=evaluate.representation('grid',load(out/f'{condition}-grid.json')),
            segments=evaluate.representation('segments',load(out/f'{condition}-segments.json')))
    from selection import gate
    for condition in report.values():
        condition['map_gates']={kind:gate(condition[kind]['full']) for kind in ('grid','segments')}
    off,on=report['off']['points']['precision'],report['on']['points']['precision']
    result=dict(seed=seed,source_sha=seal['source_sha'],option=OPTION,conditions=report,
        detector_gate=on is not None and on>=.9 and on>=off,
        historical_grid=evaluate.representation('grid',load(out/'historical-grid.json')),
        paired_covariance=seal['paired_covariance'],frames=891,original_insertions=len(admitted),
        source_seal_sha256=sha(out/'seal.json'),code_hashes=seal['code_hashes'],physics=0)
    dump(target,result)
    if seed=='31001':dump(EXP/'freeze.json',dict(option=OPTION,configuration=CONFIG,code_hashes=seal['code_hashes'],
        development_sha256=sha(target),development_seed='31001',held_seed='32002',retuning=False))
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['predict','score']);p.add_argument('seed',choices=EPISODES)
    a=p.parse_args();(predict if a.stage=='predict' else score)(a.seed)
