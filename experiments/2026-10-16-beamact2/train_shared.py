"""Finite shared-L4 supervisor; leases, smoke readback, exact-resume admission."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

from harness.grasp_act_data import sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT, source_sha

BASE=Path('/home/ugrp/ugrp-sim')
OUT=BASE/'ops-reviews/beamact2'
DATA=OUT/'data-v1/split-v1'
PY=Path('/home/ugrp/ugrp-rl1b-act-env/bin/python')


def gpu():
    return dict(gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.total,memory.used,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True).strip(),
        processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory,process_name',
        '--format=csv,noheader,nounits'],text=True).strip())


def main():
    host=require_gcp2(training=True);source=source_sha()
    lease=BASE/'leases/beamact2.json'
    with lease.open('x') as f:
        json.dump(dict(task='beamact2',pid=os.getpid(),started=datetime.now(timezone.utc).isoformat(),
            expected_end=(datetime.now(timezone.utc)+timedelta(hours=7)).isoformat(),
            stage='smoke300 then main10000',source_sha=source,concurrency=0,gpu_shared=True),f)
    started=time.monotonic()
    report=dict(status='running',source_sha=source,host=host,gpu_load_label='shared-load',
        speed_judgment_eligible=False,stages=[],gpu_before=gpu())
    OUT.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONPATH':str(ROOT),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'4'}
    def execute(stage,steps,extra):
        dest=OUT/'train'/stage
        command=[str(PY),'-m','scripts.sim_cli','workflow','run','beamact1-train','--',
            '--dataset',str(DATA),'--stage',stage,'--steps',str(steps),'--max-wall-s',
            '1800' if stage=='smoke' else '21600','--seed','20261015',
            '--execution-host-profile','beamact1_gcp2','--history-causal-split-v1','wheel_pulse_train_mean',
            '--command-history-dropout','0','--done-loss','balanced_bce_v1','--profile-timing',
            '--checkpoint-every','5000','--run-class','milestone','--output',str(dest),*extra]
        log=(OUT/(stage+'.log')).open('x')
        proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        row=dict(stage=stage,pid=proc.pid,command=command,gpu_samples=[])
        report['stages'].append(row)
        while proc.poll() is None:
            row['gpu_samples'].append(dict(elapsed_s=time.monotonic()-started,**gpu()))
            write_json(OUT/'training-supervisor.json',report)
            time.sleep(30)
        log.close();row['exit']=proc.returncode
        if proc.returncode:raise RuntimeError(stage+' nonzero exit')
        result=json.loads((dest/'summary.json').read_text())
        if not (result['complete'] and result['readback_verified'] and result['steps_completed']==steps):
            raise RuntimeError(stage+' incomplete or readback failed')
        row['summary_sha256']=sha256(dest/'summary.json')
        return dest,result
    try:
        # Resource-only admission: ACT's measured 2GiB reservation versus actual
        # free bytes. Allow another full measured reservation for readback load.
        free=int(report['gpu_before']['gpu'].split(',')[2].strip())*1024**2
        if free<2*2057306112:raise RuntimeError('insufficient shared L4 memory; await warp3 lease release')
        smoke,smoke_report=execute('smoke',300,[])
        approval=OUT/'main-admission.json'
        write_json(approval,dict(approved=True,stage='main',source_sha=source,
            dataset_manifest_sha256=sha256(DATA/'manifest.json'),smoke_summary_sha256=sha256(smoke/'summary.json'),
            steps=10000,blank_images=False,command_history_dropout=0.,
            history_causal_split_v1='wheel_pulse_train_mean',gate_promotion_authorized_if_all_conditions_pass=False,
            authority='explicit user beamact2 training after matching smoke readback; shared L4 permitted'))
        main_dir,main_report=execute('main',10000,['--resume',str(smoke/'step-000300'),
            '--approval',str(approval),'--smoke-summary',str(smoke/'summary.json')])
        model=main_dir/'step-010000/actor'
        offline=OUT/'offline-v1'
        command=[str(PY),'-m','scripts.sim_cli','workflow','run','beamact1-offline','--',
            '--dataset',str(DATA),'--stages',str(OUT/'data-v1/stages.json'),
            '--model',str(model),'--output',str(offline)]
        with (OUT/'offline.log').open('x') as log:
            subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        report.update(status='complete',model=str(model),offline=str(offline),
            model_sha256=sha256(model/'model.safetensors'))
    except BaseException as exc:
        report.update(status='HOST_ERROR',error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        report.update(gpu_after=gpu(),wall_s=time.monotonic()-started,
            other_leases=[p.name for p in (BASE/'leases').glob('*.json') if p!=lease],
            vm_stop_performed=False,vm_stop_reason='supervisor never stops shared VM; root checks final leases/processes')
        write_json(OUT/'training-supervisor.json',report)
        lease.unlink()


if __name__=='__main__':main()
