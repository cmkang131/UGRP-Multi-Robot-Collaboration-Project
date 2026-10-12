"""Frozen egomap19 mapping path plus a same-observation v122 DR baseline.

The prediction process never loads eval_only or static_map. Scoring is separate.
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/arena-wall-map-v1')
spec=importlib.util.spec_from_file_location('egomap19_map',ROOT/'experiments/2026-10-07-servo-stiffness/code/map_short.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
c=m.c


def configure(case):
    m.CASE=case
    m.EPISODE=RAW/case
    m.OUT=RAW/'predictions'/case
    m.OUT.parent.mkdir(exist_ok=True)
    return m.EPISODE,m.OUT


def predict(case):
    ep,out=configure(case)
    assert all(c.sha(ROOT/p)==h for p,h in c.read(EXP/'freeze.json')['files'].items())
    # Original defaults/100 particles/keyframes/graph/confidence, no changes.
    m.predict()
    from harness.self_pulse_odom import command_odometry
    from harness.self_odom_grid import OdomGrid,transform
    from harness.wall_confidence import confidence,weighted_insert
    fs,cs=c.old.own_inputs(ep,'r3')
    contacts={r['frame_id']:r for r in c.old.base.read_rows(out/'contacts.jsonl')}
    odom=command_odometry(fs[0]['sim_time'],motion_model='s2_pulse_v122')
    odom.command(dict(t=fs[0]['sim_time'],kind='initial_servo_command',pulses=fs[0]['commanded_servo']))
    grid=OdomGrid('r3')
    cursor=0
    poses=[]
    ledger=[]
    for f in fs:
        t=f['sim_time']
        while cursor<len(cs) and cs[cursor]['t']<t-1e-8:
            odom.command(cs[cursor])
            cursor+=1
        odom.advance(t)
        pose=odom.pose
        poses.append(dict(robot_id='r3',t=t,pose=pose))
        if f['frame_id'] in contacts:
            r=contacts[f['frame_id']]
            weights=[confidence(s,r['camera'],features,odom.covariance,pose[2])['weight']
                     for s,features in zip(r['segments'],r['features'])]
            weighted_insert(grid,transform([r['camera']],pose)[0],
                            [transform(s,pose) for s in r['segments']],weights)
            ledger.append(dict(t=t,frame_id=f['frame_id'],pose=pose,camera=r['camera'],
                               segments=r['segments'],insertion_weights=weights))
    c.old.rows(out/'dr-poses.jsonl',poses)
    c.old.rows(out/'dr-ledger.jsonl',ledger)
    c.dump(out/'dr-grid.json',grid.export())
    c.dump(out/'baseline-prediction.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='baseline-prediction.json'},
        interpretation='same own detections, v122 and inverse_sensor weighting; no matching or graph'))
    assert 'mujoco' not in sys.modules
    print(case,'candidate and DR predictions sealed',flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('case',choices=['forward','reverse'])
    predict(p.parse_args().case)
