"""Slot-only counterfactuals on the SAME saved beamact2 cold-start own inputs.

No labels, truth, simulator, rendering, model selection or local Mac inference.
These known20 states are a diagnostic, not a fresh confirmation set.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import json
import os
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json,read_rows,sha256,write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import source_sha


def vectors(chunk):
    commands=[c.decode_action(v) for v in chunk]
    # Undo normalization roundoff using the ACT head's exact observed label
    # alphabet, not a fitted movement threshold. A nominal pure turn has zero
    # translation; ~1e-9 decode residue must not count as an end reversal.
    values=np.asarray([-.35,0.,.35])
    raw=np.asarray([v['wheels'] for v in commands])
    classes=np.abs(raw[...,None]-values).argmin(-1)
    canonical=values[classes]
    dose=[]
    for command,wheels in zip(commands,canonical):
        w=wheels*np.asarray(command['duration_s'])/c.PERIOD_S
        dose.append([(w[0]+w[1]+w[2]+w[3])/4,(-w[0]+w[1]+w[2]-w[3])/4,(-w[0]+w[1]-w[2]+w[3])/4])
    return np.asarray(dose),classes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--arm',choices=('A','B'),required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=False);source=source_sha()
    import torch
    from harness.beamact3 import Beam3Actor
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    actor=Beam3Actor.load(a.model,device='cpu')
    if actor.arm!=a.arm:raise ValueError('arm mismatch')
    base=Path('/home/ugrp/ugrp-sim');raw=base/'ops-reviews/beamact2/heldout20-v1'
    lease=base/f'leases/beamact3-{a.arm}-role-probe.json'
    with lease.open('x') as f:json.dump(dict(task='beamact3-'+a.arm+'-role-probe',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='finite80 own-RGB cold-start inferences',concurrency=0),f)
    try:
        rows=[]
        for seed in range(8329000,8329020):
            run=raw/f'seed-{seed}';trace=run/'student-inputs.jsonl.zst'
            observations=read_rows(trace);first={};initial=read_json(run/'initial-issued.json')
            for obs in observations:
                if obs['robot_id'] not in first:first[obs['robot_id']]=obs
                if len(first)==2:break
            if set(first)!={'r1','r2'}:raise ValueError('both own cold-start inputs required')
            for rid,obs in first.items():
                if abs(obs['t']-initial[rid]['t'])>1e-7:
                    raise ValueError('require first control observation at initial issued clock')
                images=[(run/ref['path']).read_bytes() for ref in obs['rgb']]
                other=deepcopy(obs);other['role']='blue' if obs['role']=='teal' else 'teal'
                one=np.asarray(actor.predict(obs,images));two=np.asarray(actor.predict(other,images))
                u,uw=vectors(one);v,vw=vectors(two)
                # Commanded body-axis dose from the existing mecanum wheel mix;
                # no claim that issued commands equal physical displacement.
                first_dot=float(u[0,:2]@v[0,:2]);chunk_dot=float(u[:,:2].sum(0)@v[:,:2].sum(0))
                rows.append(dict(seed=seed,robot=rid,t=obs['t'],sim_start_s=0.,role=obs['role'],swapped_role=other['role'],
                    source_trace=str(trace),source_trace_sha256=sha256(trace),rgb_sha256=[r['sha256'] for r in obs['rgb']],
                    original_first_motion=u[0].tolist(),swapped_first_motion=v[0].tolist(),
                    original_chunk_motion=u.sum(0).tolist(),swapped_chunk_motion=v.sum(0).tolist(),
                    first_translation_reversed=first_dot<0,chunk_translation_reversed=chunk_dot<0,
                    first_turn_sign_flipped=bool(u[0,2]*v[0,2]<0),chunk_turn_sign_flipped=bool(u[:,2].sum()*v[:,2].sum()<0),
                    first_wheel_classes_changed=not np.array_equal(uw[0],vw[0]),
                    chunk_wheel_classes_changed=not np.array_equal(uw,vw),
                    original_wheel_classes=uw.tolist(),swapped_wheel_classes=vw.tolist(),
                    original_first_stationary=bool(not np.any(u[0])),swapped_first_stationary=bool(not np.any(v[0])),
                    decoded_chunk_l1=float(np.abs(one-two).mean())))
        metrics={key:sum(r[key] for r in rows) for key in ('first_translation_reversed','chunk_translation_reversed',
            'first_turn_sign_flipped','chunk_turn_sign_flipped','first_wheel_classes_changed','chunk_wheel_classes_changed',
            'original_first_stationary','swapped_first_stationary')}
        write_json(a.output,dict(complete=True,arm=a.arm,host=host,source_sha=source,model_sha256=sha256(a.model/'model.safetensors'),
            N=len(rows),metrics=metrics,rows=rows,input_change='role token only; own RGB/issued history/task clocks identical',
            no_truth_or_labels=True,new_physical_runs=0,checkpoint_selection='fixed final20000; probe never selects model',
            motion_units='wheel * pulse_seconds /0.1 body-axis command dose, never measured pose/speed',
            roundoff_policy='wheel classes mapped to exact data alphabet -0.35/0/+0.35 before body-axis sums; no fitted deadband',
            scope='saved baseline same20 cold-start counterfactual; not proof of correct end selection in closed loop'))
        print(json.dumps(dict(arm=a.arm,N=len(rows),metrics=metrics)),flush=True)
    finally:lease.unlink()


if __name__=='__main__':main()
