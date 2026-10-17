"""Finite one-arm shared-L4 stage. Never changes cloud lifecycle or peers."""
import argparse
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from harness.grasp_act_data import read_json,sha256,write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT,source_sha

BASE=Path('/home/ugrp/ugrp-sim');OUT=BASE/'ops-reviews/beamact3'
DATA=BASE/'ops-reviews/actdiag/infer-final-v1/dataset-view'
PY=Path('/home/ugrp/ugrp-rl1b-act-env/bin/python')
MANIFEST='a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'


def gpu():
    return dict(gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.total,memory.used,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True).strip(),
        processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory,process_name',
        '--format=csv,noheader,nounits'],text=True).strip())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm',choices=('A','B'),required=True)
    p.add_argument('--stage',choices=('smoke','main','offline'),required=True)
    p.add_argument('--attempt',type=int,default=1)
    p.add_argument('--max-wall-s',type=int,required=True)
    p.add_argument('--resume',type=Path)
    p.add_argument('--smoke-summary',type=Path)
    p.add_argument('--model',type=Path)
    a=p.parse_args()
    if not 1<=a.max_wall_s<=7*3600:raise ValueError('finite <=7h segment')
    host=require_gcp2(training=True);source=source_sha()
    if sha256(DATA/'manifest.json')!=MANIFEST:raise ValueError('dataset manifest mismatch')
    OUT.mkdir(exist_ok=True);armroot=OUT/a.arm;armroot.mkdir(exist_ok=True)
    dest=armroot/(a.stage+f'-attempt{a.attempt}')
    if dest.exists():raise ValueError('never overwrite attempt')
    lease=BASE/f'leases/beamact3-{a.arm}.json'
    started=time.monotonic();stamp=datetime.now(timezone.utc)
    with lease.open('x') as f:json.dump(dict(task='beamact3-'+a.arm,pid=os.getpid(),start=stamp.isoformat(),
        expected_end=(stamp+timedelta(seconds=a.max_wall_s)).isoformat(),source_sha=source,stage=a.stage,
        concurrency=0,gpu_shared=True),f)
    record=dict(status='running',arm=a.arm,stage=a.stage,attempt=a.attempt,source_sha=source,host=host,
        gpu_load_label='shared-load',speed_judgment_eligible=False,gpu_before=gpu(),
        other_leases={q.name:read_json(q) for q in (BASE/'leases').glob('*.json') if q!=lease})
    proc=None
    def stop(sig,frame):
        record['supervisor_stop_signal']=sig
        if proc is not None and proc.poll() is None:proc.send_signal(signal.SIGTERM)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        import shutil
        free=shutil.disk_usage(BASE).free
        # Per stage final actor+optimizer measured 622MB in beamact2; reserve
        # two checkpoints and logs, while keeping project 8GiB floor. DATA is
        # shared immutable view, no duplicate 20GiB images.
        record['storage']=dict(free_bytes=free,reserved_bytes=2*622*1024**2,floor_bytes=8*1024**3)
        if free<8*1024**3+2*622*1024**2:raise RuntimeError('storage admission failed')
        if int(record['gpu_before']['gpu'].split(',')[2].strip())*1024**2<2*2057306112:
            raise RuntimeError('shared L4 memory admission failed')
        mask='off' if a.arm=='A' else 'wheel_pulse_train_mean'
        if a.stage=='offline':
            if not a.model:raise ValueError('fixed final model required')
            command=[str(PY),'-m','scripts.sim_cli','workflow','run','beamact3-offline','--',
                '--dataset',str(DATA),'--stages',str(BASE/'ops-reviews/beamact2/data-v1/stages.json.zst'),
                '--model',str(a.model),'--beamact3-v1',a.arm,'--output',str(dest)]
        else:
            steps=300 if a.stage=='smoke' else 20000
            command=[str(PY),'-m','scripts.sim_cli','workflow','run','beamact3-train','--',
                '--dataset',str(DATA),'--stage',a.stage,'--steps',str(steps),'--max-wall-s',str(a.max_wall_s),
                '--seed','20261015','--execution-host-profile','beamact1_gcp2','--beamact3-v1',a.arm,
                '--history-causal-split-v1',mask,'--command-history-dropout','0','--done-loss','balanced_bce_v1',
                '--checkpoint-every','5000','--profile-timing','--run-class','milestone','--output',str(dest)]
            if a.stage=='main':
                if not a.resume or not a.smoke_summary:raise ValueError('exact resume and smoke required')
                smoke=read_json(a.smoke_summary)
                if not(smoke['complete'] and smoke['readback_verified'] and smoke['beamact3_v1']==a.arm):
                    raise ValueError('completed matching smoke readback required')
                approval=armroot/f'admission-attempt{a.attempt}.json'
                write_json(approval,dict(approved=True,stage='main',source_sha=source,
                    dataset_manifest_sha256=MANIFEST,smoke_summary_sha256=sha256(a.smoke_summary),steps=20000,
                    blank_images=False,command_history_dropout=0.,history_causal_split_v1=mask,beamact3_v1=a.arm,
                    gate_promotion_authorized_if_all_conditions_pass=False,
                    authority='explicit user beamact3 A/B20k; separate finite attempts; no threshold or heldout tuning'))
                command+=['--resume',str(a.resume),'--approval',str(approval),'--smoke-summary',str(a.smoke_summary)]
        env={**os.environ,'PYTHONPATH':str(ROOT),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'4'}
        record.update(command=command,gpu_samples=[])
        logpath=armroot/(a.stage+f'-attempt{a.attempt}.log')
        with logpath.open('x') as log:
            proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            record['pid']=proc.pid
            while proc.poll() is None:
                record['gpu_samples'].append(dict(elapsed_s=time.monotonic()-started,**gpu()))
                write_json(armroot/(a.stage+f'-attempt{a.attempt}-supervisor.json'),record)
                # The trainer has a graceful checkpointing wall guard. Offline
                # also has a finite supervisor guard; only our process group.
                if time.monotonic()-started>a.max_wall_s+300:
                    os.killpg(proc.pid,signal.SIGTERM)
                time.sleep(30)
        record['exit']=proc.returncode
        if proc.returncode:raise RuntimeError('managed stage nonzero exit')
        result=read_json(dest/'summary.json')
        record.update(status=result['status'],summary_sha256=sha256(dest/'summary.json'),output=str(dest))
        if a.stage!='offline':record.update(steps_completed=result['steps_completed'],readback_verified=result['readback_verified'],
            checkpoint=result.get('last_checkpoint'),complete=result['complete'])
        else:record.update(complete=result['status']=='complete',model=str(a.model))
    except BaseException as exc:
        record.update(status='HOST_ERROR',error_type=type(exc).__name__,error=str(exc));raise
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=300)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        record.update(gpu_after=gpu(),wall_s=time.monotonic()-started,
            other_leases=[q.name for q in (BASE/'leases').glob('*.json') if q!=lease],vm_stop_performed=False)
        write_json(armroot/(a.stage+f'-attempt{a.attempt}-supervisor.json'),record)
        lease.unlink()


if __name__=='__main__':main()
