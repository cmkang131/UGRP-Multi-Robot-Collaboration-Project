"""egomap43 exact egomap42 LM-on inputs, S2 fixed alpha=.5. No GT reads."""
from pathlib import Path
import argparse, importlib.util, sys, json, math
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-map-closed-loop-v1/offline')
CACHE=Path('/Users/changmin/projects/ugrp/outputs/own-map-causal-landmarks-v1')
source=ROOT/'experiments/2026-10-08-own-map-causal-landmarks/code/replay.py'
spec=importlib.util.spec_from_file_location('causal_replay',source)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
load,rows,sha,head,dump=base.load,base.rows,base.sha,base.head,base.dump
EP=base.EP
from harness.self_map_relocalize import Relocalizer,plan_to_remembered_goal
from harness.self_map_causal import after,landmark_object
from harness.self_odom_grid import transform
from harness.own_map_amcl_vendor import landmarks as lm

def snapshot_path(c,i):return CACHE/f'maps/{c}-{i}.json'
def source_files():return [Path(__file__),*base.source_files()]

def predict(condition, mode, trial):
    out=RAW/f'{condition}-{mode}-{trial}.json'
    if out.exists():raise ValueError('TRIAL_ALREADY_SEALED')
    prepared=load(CACHE/'prepared.json');cut=prepared['cuts'][trial]
    assert sha(CACHE/'own-inputs.json')==prepared['own_inputs_sha256']
    assert sha(snapshot_path(condition,trial))==cut['maps'][condition]
    landmark_file=CACHE/f'maps/{condition}-{trial}-landmarks.json'
    assert sha(landmark_file)==cut['landmarks'][condition]
    seq=[r for r in load(CACHE/'own-inputs.json') if after(r['t'],cut['cut_t'])]
    grid=load(snapshot_path(condition,trial))
    goal=cut['own_goal'] if condition=='own' else prepared['static_goal']
    option='off' if mode=='off' else lm.OPTION
    pf=Relocalizer(grid,seed=41001+trial,sensor_landmarks=option,
        landmark_map=landmark_object(load(landmark_file)),likelihood_tempering='pr_likelihood_half_v1')
    output=[];streak=0;plan=None
    for i,r in enumerate(seq):
        result=pf.step(t=r['t'],points=r['points'],delta=r['delta'] if i else [0.,0.,0.],
            servo={int(k):v for k,v in r['servo'].items()},features=r['features'])
        streak=streak+1 if result['resolved'] else 0
        result.update(frame_id=r['frame_id'],stable_resolved=streak>=5,
            declared_goal=bool(streak>=5 and goal and np.linalg.norm(np.array(result['pose'][:2])-goal['center_m'])<=.20),
            landmark_count=len(r['features']) if mode=='tempered' else 0)
        if streak>=5 and plan is None:
            plan=dict(t=r['t'],pose=result['pose'],
                **plan_to_remembered_goal(grid,result['pose'],None if goal is None else goal['center_m']))
        output.append(result)
        if i%100==0:print(condition,mode,trial,i,'/',len(seq),'particles',pf.n,flush=True)
    dump(RAW/f'audit-{condition}-{trial}.json',pf.tempering_audit)
    dump(out,dict(source_sha=head(),condition=condition,mode=mode,sensor_landmarks=option,trial=trial,seed=41001+trial,
        prepared_sha256=sha(CACHE/'prepared.json'),input_frames=len(seq),points=sum(len(r['points']) for r in seq),
        features=sum(len(r['features']) for r in seq) if mode=='tempered' else 0,
        feature_frames=sum(bool(r['features']) for r in seq) if mode=='tempered' else 0,
        measured_features=sum(len(r['features']) for r,q in zip(seq,output) if q['updated']) if mode=='tempered' else 0,
        start_t=seq[0]['t'],cut_t=cut['cut_t'],goal=goal,plan=plan,rows=output,gt_inputs=False,
        source_code_hashes={str(f.relative_to(ROOT)):sha(f) for f in source_files()}))
    print('SEALED',out.name,sha(out),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--condition',choices=['own','static']);p.add_argument('--trial',type=int,choices=range(3));a=p.parse_args()
    predict(a.condition,'tempered',a.trial)
    assert 'mujoco' not in sys.modules
