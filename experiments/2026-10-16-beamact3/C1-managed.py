"""C1/C2 step-bounded training; no wall/VM limit, no cloud credentials."""
import argparse
from datetime import datetime,timezone
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess

from harness.grasp_act_data import sha256,read_json,write_json,GraspDataset
from scripts.grasp_act_training_guard import source_sha,ROOT

BASE=Path('/home/ugrp/ugrp-sim')
DATA=BASE/'ops-reviews/actdiag/infer-final-v1/dataset-view'
PY='/home/ugrp/ugrp-rl1b-act-env/bin/python'
MANIFEST='a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'

def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=('C1','C2'),required=True);a=p.parse_args()
    candidate=importlib.import_module('harness.C1-beamact3c')
    host=candidate.require_training_host(a.arm);source=source_sha()
    if sha256(DATA/'manifest.json')!=MANIFEST:raise ValueError('wrong dataset')
    out=BASE/'ops-reviews/beamact3c'/a.arm
    out.mkdir(parents=True,exist_ok=False)
    lease=BASE/'leases'/('beamact3c-'+a.arm+'.json');lease.parent.mkdir(exist_ok=True)
    with lease.open('x') as f:json.dump(dict(task='beamact3c-'+a.arm,pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end=None,concurrency=0,source_sha=source,host=host,stage='300smoke + total20000'),f)
    record=dict(status='running',host=host,arm=a.arm,source_sha=source,wall_cap=None,vm_cap=None,stages=[])
    proc=None
    def stop(sig,frame):
        if proc and proc.poll() is None:proc.send_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        import shutil
        if shutil.disk_usage(BASE).free<8*1024**3+5*700*1024**2:raise RuntimeError('checkpoint storage floor')
        env={**os.environ,'PYTHONPATH':str(ROOT),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'4'}
        for stage,steps in [('smoke',300),('main',20000)]:
            command=[PY,'-m','scripts.C1-train_beamact3c','--dataset',str(DATA),'--stage',stage,'--steps',str(steps),'--seed','20261015','--beamact3-v1',a.arm,'--done-loss','balanced_bce_v1','--checkpoint-every','5000','--profile-timing','--run-class','milestone','--output',str(out/stage)]
            if stage=='main':
                smoke=read_json(out/'smoke/summary.json')
                if not smoke['complete'] or not smoke['readback_verified']:raise RuntimeError('smoke incomplete')
                approval=out/'admission.json'
                write_json(approval,dict(approved=True,stage='main',source_sha=source,dataset_manifest_sha256=MANIFEST,smoke_summary_sha256=sha256(out/'smoke/summary.json'),steps=20000,blank_images=False,command_history_dropout=smoke['command_history_dropout'],history_causal_split_v1='off',beamact3_v1=a.arm,gate_promotion_authorized_if_all_conditions_pass=False,authority='2026-10-16 explicit user C1/C2 parallel20000; no heldout tuning',rejection_table=str(ROOT/'experiments/2026-10-16-beamact3/C1-prior-rejection-table.json')))
                command+=['--resume',smoke['last_checkpoint'],'--smoke-summary',str(out/'smoke/summary.json'),'--approval',str(approval)]
            record['stage']=stage;record['command']=command;write_json(out/'managed.json',record)
            with (out/(stage+'.log')).open('x') as log:
                proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                record['pid']=proc.pid;write_json(out/'managed.json',record)
                code=proc.wait()
            result=read_json(out/stage/'summary.json')
            record['stages'].append(dict(stage=stage,exit=code,complete=result['complete'],summary_sha256=sha256(out/stage/'summary.json')))
            if code or not result['complete'] or not result['readback_verified']:raise RuntimeError('stage failed '+stage)
        record['status']='complete'
    except BaseException as exc:
        record.update(status='HOST_ERROR',error_type=type(exc).__name__,error=str(exc));raise
    finally:
        if proc and proc.poll() is None:proc.send_signal(signal.SIGTERM);proc.wait()
        write_json(out/'managed.json',record)
        lease.unlink()
if __name__=='__main__':main()
