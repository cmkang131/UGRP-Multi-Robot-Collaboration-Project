"""Frozen own RGB/commands in; posterior records out. No simulator import/step.

Truth is opened only AFTER the controller is closed, for the separate report.
Head planning uses saved belief; absent counterfactual RGB is never fabricated.
"""
import argparse
import base64
import collections
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np
from PIL import Image

from harness import zone_s3_no_prior_contract as old
from harness.zone_s3_continue import solo_factory
from harness.zone_s3_global_diversity import rank_views, OPTION, HEAD_OPTION
from harness.zone_pair_highpose_exact_speedups import install


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def evaluate(raw, rid, record):
    truth = raw/f'eval_only/{rid}/trajectory.jsonl'
    rows = lines(truth if truth.exists() else raw/'eval_only/trajectory.jsonl')
    times = [q['t'] for q in rows]
    xy = np.array([q['robot_xyz_m'][:2] for q in rows])
    yaw = np.unwrap([q['robot_yaw_rad'] for q in rows])
    def error(p):
        t=p['t_est']; dy=p['yaw']-np.interp(t,times,yaw)
        return dict(t=p['t'], elapsed_s=p['t']-record['poses'][0]['t'],
            xy_error_m=math.dist([p['x'],p['y']],[np.interp(t,times,xy[:,j]) for j in (0,1)]),
            yaw_error_deg=abs(math.degrees(math.atan2(math.sin(dy),math.cos(dy)))),
            sigma_xy_m=p['std_xy_m'],sigma_yaw_deg=math.degrees(p['std_yaw_rad']))
    first = qualified = None; false = 0
    for p in record['poses']:
        if p['std_xy_m']<=.05 and p['std_yaw_rad']<=math.radians(5):
            e=error(p);e['correct']=e['xy_error_m']<=.25 and e['yaw_error_deg']<=15
            if first is None:
                first=e;false=int(not e['correct'])
        if qualified is None and p.get('convergence_certificate',{}).get('qualified'):
            qualified=error(p)
    return dict(first_sigma=first,first_certificate=qualified,false_first_convergence=false,
                last=error(record['poses'][-1]),evaluation_only=True)


def replay(raw, out, rid, seed, candidate):
    out.mkdir(parents=True,exist_ok=False)
    b=read(raw/'bundle.json')
    config=copy.deepcopy(b.get('controller_config') or old.controller_config())
    config['options']['localization_certification']='posterior_consensus_v1'
    if candidate:
        config['options'].update(global_diversity=OPTION,mode_head_look=HEAD_OPTION)
    static=old.hp.resolve(b['map_id'])[0]
    _,undo=install('v98-exact-v6');own=None
    start=time.monotonic();used=[];rankings=[]
    try:
        own=solo_factory(config)(static,old.ROOT/old.old.solo.CALIBRATION,
            b['calibration_sha256'],seed=seed,robot_id=rid,pickup_slot='P1-2',destination='B')
        commands=lines(raw/f'robots/{rid}/commands.jsonl');by=collections.defaultdict(list)
        for row in commands[1:]:by[round(row['t'],9)].append(row)
        first=commands[0]
        # Raw MuJoCo reset time can be 1.3000000000000007 while capture logs
        # use 1.3. Match the existing replay clock normalization, not a delay.
        own.initial_commands(round(first['t'],9),{rid:{int(k):v for k,v in first['pulses'].items()}})
        pf=own.pose.provider.loc._pf;last_updates=0
        for frame in lines(raw/f'robots/{rid}/frames.jsonl'):
            now=frame['sim_time']
            if now>14.+1e-8:break
            jpeg=(raw/frame['path']).read_bytes()
            assert hashlib.sha256(jpeg).hexdigest()==frame['sha256']
            obs={k:v for k,v in frame.items() if k not in ('path','commanded_servo')}
            obs['image']=base64.b64encode(jpeg).decode()
            own.on_frames(now,{rid:(obs,np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))})
            used.append(dict(t=now,path=frame['path'],sha256=frame['sha256']))
            if candidate and len(own.global_policy.rows)>last_updates:
                rankings.append(dict(t=now,rank=rank_views(pf,[1500,1230,970,1770,2030,700,2300]),
                    counterfactual_only=True,new_observation=False))
            last_updates=len(own.global_policy.rows)
            for row in by[round(now,9)]:
                own.on_command(rid,now,{k:v for k,v in row.items() if k!='t'})
        record=own.record()
    finally:
        if own:own.close()
        undo()
    result=evaluate(raw,rid,record)  # AFTER close: evaluator cannot affect control
    result.update(raw=str(raw),robot=rid,seed=seed,candidate=candidate,until=14.,
        physical_runs=0,controller_inputs=['own RGB','own issued commands','static map'],
        wall_s=time.monotonic()-start,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        options=config['options'],head_closed_loop_verified=False,
        updates=record['global_localization']['updates'])
    for name,value in [('record',record),('result',result),('frames',used),('head-ranking',rankings)]:
        (out/(name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('robot','seed','candidate','first_sigma','last','wall_s')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--case',choices=['r1']+[str(i) for i in range(1065,1071)],required=True)
    p.add_argument('--candidate',action='store_true');a=p.parse_args()
    root=Path('/Users/changmin/projects/ugrp/outputs')
    if a.case=='r1':
        raw=root/'s3-host-heading-3daa830f-s14201-v146';rid='r1';seed=14201
    else:
        raw=root/f's2-realism-99d81d8c-s{a.case}-v141-graduation';rid='r3';seed=int(a.case)
    replay(raw,a.out,rid,seed,a.candidate)
