"""Saved ACT15 own-input replay on CPU gcp2, no physics or learning.

Compare the new raw-chunk/zero-residual client with actually issued ACT15
commands. Replay twice while changing an unused private canary copy, leaving
all original evaluation/teacher evidence untouched. This is CPU actor evidence,
not GPU/Warp reset or task-success evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.simalt_host import gcp2_identity
from scripts.rl_act_actor import FrozenACT


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    host=gcp2_identity()
    if host['instance']!='ugrp-sim-gcp2':
        p.error('CPU gcp2 only')
    a.output.mkdir(parents=True,exist_ok=False)
    lease=Path('/home/ugrp/ugrp-sim/leases/rl1b.json')
    token=dict(task='rl1b',pid=os.getpid(),started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        expected_end_utc=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),
        purpose='CPU saved zero-residual inference audit; no training/physics/GPU')
    with lease.open('x') as f:json.dump(token,f)
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        observations=read(a.run/'student-inputs.jsonl')
        expected=read(a.run/'commands.jsonl')
        if len(observations)!=len(expected):raise ValueError('saved causal length mismatch')
        passes=[]
        for repeat in range(2):
            torch.manual_seed(20261016)
            canary=a.output/'private-canary.json'
            canary.write_text(json.dumps(dict(fake_world_xy=[repeat*1000,-repeat*1000],
                stable_lift=bool(repeat),note='audit-only copy; never supplied to actor'))+'\n')
            actor=FrozenACT(a.source,a.checkpoint,1,device='cpu')
            commands=hashlib.sha256();features_hash=hashlib.sha256()
            mismatches=[]
            for index,(obs,baseline) in enumerate(zip(observations,expected)):
                item=SimpleNamespace(observation=obs,jpegs=tuple((a.run/r['path']).read_bytes() for r in obs['rgb']))
                features,raw=actor.prepare([item])
                issued,_=actor.issue([item],raw,np.zeros((1,14)),np.zeros(14))
                actual=issued[0]
                expected_row=dict(command=baseline['command'],done=baseline['done_requested'])
                if actual!=expected_row:
                    if len(mismatches)<5:mismatches.append(dict(index=index,actual=actual,expected=expected_row))
                commands.update(json.dumps(actual,sort_keys=True,separators=(',',':')).encode())
                features_hash.update(features.tobytes())
            passes.append(dict(repeat=repeat,requests=len(observations),
                command_sha256=commands.hexdigest(),features_sha256=features_hash.hexdigest(),
                matches_saved=len(observations) if not mismatches else None,first_mismatches=mismatches))
            del actor
        report=dict(schema='ugrp.rl1b.zero-residual-audit.v1',status='complete',host=host,
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            actor_source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
            checkpoint_sha256=sha(a.checkpoint/'model.safetensors'),passes=passes,
            canary_mutation_command_invariance=passes[0]['command_sha256']==passes[1]['command_sha256'],
            canary_mutation_feature_invariance=passes[0]['features_sha256']==passes[1]['features_sha256'],
            forbidden_loaded_modules=[n for n in sys.modules if n=='mujoco' or n.startswith(('mujoco.','mujoco_warp','scripts.rl_act_reward','scripts.rl_act_env','scripts.rl_act_learning'))],
            sources={str(a.run/name):sha(a.run/name) for name in ('student-inputs.jsonl','commands.jsonl')},
            scope='CPU saved own-input inference; private canary never supplied; actual Warp/GPU audit pending',
            physics_runs=0,training_runs=0,gpu_seconds=0)
        (a.output/'zero-residual-audit.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    except BaseException as error:
        (a.output/'analysis-error.json').write_text(json.dumps(dict(status='ANALYSIS_ERROR',
            error_type=type(error).__name__,error=str(error),physics_runs=0,training_runs=0,gpu_seconds=0),indent=2)+'\n')
        raise
    finally:
        if lease.exists() and json.loads(lease.read_text())==token:lease.unlink()


if __name__=='__main__':main()
