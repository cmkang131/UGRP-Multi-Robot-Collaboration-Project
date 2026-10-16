"""egomap42 causal prefix maps / disjoint suffix predictions. No GT access."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math, subprocess, sys
import cv2
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
EXP = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/own-map-causal-landmarks-v1')
EP = Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
POINTS = Path('/Users/changmin/projects/ugrp/outputs/wall-contact-types-v1/32002/off/points.jsonl')
OLD = ROOT/'experiments/2026-10-08-own-map-utility'
spec=importlib.util.spec_from_file_location('egomap41_replay', OLD/'code/replay.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
from harness.self_map_causal import before, after, snapshot_before, own_landmarks_before, landmark_object
from harness.self_map_landmark_sensor import Sensor
from harness.self_map_relocalize import Relocalizer, plan_to_remembered_goal
from harness.own_map_amcl_vendor import landmarks as lm
from harness.self_pose_graph import between
from harness.self_odom_grid import transform
from harness.self_pulse_rotation import RotationPulseOdometry
load, rows, sha, head, dump = old.load, old.rows, old.sha, old.head, old.dump


def snapshot_path(condition, trial):
    return RAW/f'maps/{condition}-{trial}.json'


def source_files():
    return [Path(__file__), OLD/'code/replay.py',
        *[ROOT/'harness'/n for n in ['self_map_causal.py','self_map_landmark_sensor.py',
            'self_map_relocalize.py','self_pulse_rotation.py','self_pulse_odom.py','rbpf_rejection.py',
            'active_wall_vision.py','active_camera.py','servo_camera_fk.py','visual_arm.py','zone_color_boxes.py']],
        ROOT/'harness/data/servo_camera_v3_chain.json',
        ROOT/'experiments/2026-09-26-markerless-probe/markerless_probe.py',
        *[ROOT/'sim'/n for n in ['masterpi_camera_profile.py','masterpi_camera_review_v3.py',
            'masterpi_camera_review_v1.py','masterpi_model_v3.py','masterpi_dynamics_v2.py','masterpi_geometry_v3.py']],
        *sorted((ROOT/'harness/own_map_amcl_vendor').glob('*.py'))]


def prepare():
    # Upstream fixed_robot's XML string builder imports this package but does
    # not instantiate it. Block all model/data/render/physics entry points.
    import mujoco
    def forbidden(*a, **k):
        raise RuntimeError('OFFLINE_NATIVE_CALL_FORBIDDEN')
    for name in ('MjModel','MjData','Renderer','mj_step','mj_forward','mj_kinematics'):
        setattr(mujoco, name, forbidden)
    if (RAW/'prepared.json').exists(): raise ValueError('PREPARATION_ALREADY_SEALED')
    names = ['online-maps.jsonl','frontend-covariances.jsonl','own-controller.jsonl',
             'robots/r3/frames.jsonl','robots/r3/commands.jsonl','inputs/static_map.json']
    expected = load(EP/'artifacts.sha256.json')
    for n in names: assert sha(EP/n)==expected[n],n
    frames = {f['frame_id']: {k:f[k] for k in ('frame_id','sim_time','path','sha256','commanded_servo')}
              for f in rows(EP/'robots/r3/frames.jsonl')}
    columns = rows(POINTS)
    # Only color vocabulary, no static geometry enters this own RGB detector.
    static = load(EP/'inputs/static_map.json')
    hues = lm.MapFeatures(static).hues
    sensor = Sensor(hues)
    commands = rows(EP/'robots/r3/commands.jsonl')
    odom = RotationPulseOdometry(commands[0]['t'])
    ci=0; previous=np.zeros(3); sequence=[]; measurements=[]
    for i, row in enumerate(columns):
        frame=frames[row['frame_id']];path=EP/frame['path'];assert sha(path)==frame['sha256']
        t=row['t'];servo={int(k):v for k,v in frame['commanded_servo'].items()}
        features=sensor.measure(cv2.imread(str(path)),servo,row)
        measurements.append(dict(robot_id='r3',t=t,frame_id=row['frame_id'],
            frame_sha256=frame['sha256'],features=features))
        while ci<len(commands) and commands[ci]['t']<=t+1e-8:
            odom.command(commands[ci]);ci+=1
        nominal=np.array(odom.advance(t));delta=between(previous,nominal);previous=nominal
        sequence.append(dict(t=t,frame_id=row['frame_id'],points=row['points'],
            delta=delta.tolist(),servo=servo,features=features))
        if i%100==0:print('own RGB features',i,'/',len(columns),flush=True)
    dump(RAW/'own-inputs.json',sequence)
    dump(RAW/'own-measurements.json',measurements)
    snapshots=rows(EP/'online-maps.jsonl');poses=rows(EP/'frontend-covariances.jsonl')
    controller=rows(EP/'own-controller.jsonl');start_t=min(f['sim_time'] for f in frames.values())
    cuts=[]
    mapped_static=lm.MapFeatures(static)
    static_features=dict(edges=mapped_static.edges,doors=mapped_static.doors,frame='authored_static_world')
    for trial,elapsed in enumerate([60.,90.,120.]):
        cut=start_t+elapsed;snap=snapshot_before(snapshots,cut,robot_id='r3')
        goal=old.remembered_goal([r for r in controller if before(r['t'],cut)],frames)
        landmarks=own_landmarks_before(measurements,poses,cut,robot_id='r3')
        dump(snapshot_path('own',trial),snap['grid'])
        dump(RAW/f'maps/own-{trial}-ledger.json',snap['ledger'])
        dump(RAW/f'maps/own-{trial}-landmarks.json',landmarks)
        dump(snapshot_path('static',trial),old.static_grid(static))
        dump(RAW/f'maps/static-{trial}-landmarks.json',static_features)
        cuts.append(dict(trial=trial,elapsed_s=elapsed,cut_t=cut,snapshot_t=snap['t'],
            snapshot_frame_id=snap['frame_id'],scans=len(snap['ledger']),
            last_scan_t=max(r['t'] for r in snap['ledger']),own_goal=goal,
            own_floor_lines=len(landmarks['edges']),own_doors=len(landmarks['doors']),
            maps={c:sha(snapshot_path(c,trial)) for c in ('own','static')},
            landmarks={c:sha(RAW/f'maps/{c}-{trial}-landmarks.json') for c in ('own','static')}))
    dump(RAW/'prepared.json',dict(source_sha=head(),preregistration='9c5ee9c3',cuts=cuts,
        static_goal=dict(entity=dict(kind='floor_zone',id='B'),center_m=static['regions']['zone_B']['center_m'],
                         source='authored_static_map'),
        own_inputs_sha256=sha(RAW/'own-inputs.json'),start_t=start_t,final_t=sequence[-1]['t'],
        source_code_hashes={str(f.relative_to(ROOT)):sha(f) for f in source_files()},
        input_hashes={str(EP/n):sha(EP/n) for n in names}|{str(POINTS):sha(POINTS)},
        shared_color_hues=hues,shared_geometry=False,physics=0,model_calls=0,gt_inputs=False))
    print('PREPARED causal snapshots, original S2 measurements and command-only motion',flush=True)


def predict(condition, mode, trial):
    out=RAW/f'{condition}-{mode}-{trial}.json'
    if out.exists():raise ValueError('TRIAL_ALREADY_SEALED')
    prepared=load(RAW/'prepared.json');cut=prepared['cuts'][trial]
    for name,digest in prepared['source_code_hashes'].items():assert sha(ROOT/name)==digest,name
    assert sha(RAW/'own-inputs.json')==prepared['own_inputs_sha256']
    assert sha(snapshot_path(condition,trial))==cut['maps'][condition]
    landmark_file=RAW/f'maps/{condition}-{trial}-landmarks.json'
    assert sha(landmark_file)==cut['landmarks'][condition]
    seq=[r for r in load(RAW/'own-inputs.json') if after(r['t'],cut['cut_t'])]
    grid=load(snapshot_path(condition,trial))
    goal=cut['own_goal'] if condition=='own' else prepared['static_goal']
    option='off' if mode=='off' else lm.OPTION
    pf=Relocalizer(grid,seed=41001+trial,sensor_landmarks=option,
        landmark_map=landmark_object(load(landmark_file)) if mode=='on' else None)
    output=[];streak=0;plan=None
    for i,r in enumerate(seq):
        result=pf.step(t=r['t'],points=r['points'],delta=r['delta'] if i else [0.,0.,0.],
            servo={int(k):v for k,v in r['servo'].items()},features=r['features'])
        streak=streak+1 if result['resolved'] else 0
        result.update(frame_id=r['frame_id'],stable_resolved=streak>=5,
            declared_goal=bool(streak>=5 and goal and np.linalg.norm(np.array(result['pose'][:2])-goal['center_m'])<=.20),
            landmark_count=len(r['features']) if mode=='on' else 0)
        if streak>=5 and plan is None:
            plan=dict(t=r['t'],pose=result['pose'],
                **plan_to_remembered_goal(grid,result['pose'],None if goal is None else goal['center_m']))
        output.append(result)
        if i%100==0:print(condition,mode,trial,i,'/',len(seq),'particles',pf.n,flush=True)
    dump(out,dict(source_sha=head(),condition=condition,mode=mode,sensor_landmarks=option,trial=trial,seed=41001+trial,
        prepared_sha256=sha(RAW/'prepared.json'),input_frames=len(seq),points=sum(len(r['points']) for r in seq),
        features=sum(len(r['features']) for r in seq) if mode=='on' else 0,
        feature_frames=sum(bool(r['features']) for r in seq) if mode=='on' else 0,
        measured_features=sum(len(r['features']) for r,q in zip(seq,output) if q['updated']) if mode=='on' else 0,
        start_t=seq[0]['t'],cut_t=cut['cut_t'],goal=goal,plan=plan,rows=output,gt_inputs=False,
        source_code_hashes={str(f.relative_to(ROOT)):sha(f) for f in source_files()}))
    print('SEALED',out.name,sha(out),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','predict'])
    p.add_argument('--condition',choices=['own','static']);p.add_argument('--mode',choices=['off','on'])
    p.add_argument('--trial',type=int,choices=range(3));a=p.parse_args()
    if a.stage=='prepare':prepare()
    else:predict(a.condition,a.mode,a.trial)
    if a.stage == 'predict': assert 'mujoco' not in sys.modules
