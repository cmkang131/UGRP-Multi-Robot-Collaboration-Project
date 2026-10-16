"""Finite saved-input latency measurement, guarded to gcp1; never run on Mac."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from harness.grasp_act_data import read_rows, safe_path, sha256, write_json
from scripts.grasp_act_training_guard import require_gcp, source_sha
from scripts.run_grasp_act_student import response


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('model','inputs','rgb-root','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--threads',type=int,nargs='+',default=[1,2,4,8,16])
    a=p.parse_args()
    host=require_gcp(training=False);source=source_sha()  # before model import/process
    if any(t not in (1,2,4,8,16) for t in a.threads):raise ValueError('bounded CPU thread grid required')
    rows=read_rows(a.inputs)
    if len(rows)<40:raise ValueError('40 distinct saved input rows required')
    selected=np.linspace(0,len(rows)-1,40,dtype=int)
    requests=[]
    for i in selected:
        o=rows[i];jpegs=[]
        for ref in o['rgb']:
            path=safe_path(a.rgb_root,ref['path'])
            if sha256(path)!=ref['sha256']:raise ValueError('saved RGB mismatch')
            jpegs.append(base64.b64encode(path.read_bytes()).decode())
        requests.append(json.dumps({'observation':o,'jpegs':jpegs},allow_nan=False)+'\n')
    report={'schema':'ugrp.act6.latency.v1','complete':False,'source_sha':source,'host':host,
        'model_sha256':sha256(a.model/'model.safetensors'),'inputs_sha256':sha256(a.inputs),
        'physical_runs':0,'training_steps':0,'concurrency':1,'threads':[],
        'scope':'RPC + preprocess + batch1 CPU inference; simulator wall/SIM still needs first30 review'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists():raise FileExistsError(a.output)
    deadline=time.monotonic()+1800.
    try:
        for t in a.threads:
            worker=subprocess.Popen([sys.executable,'-m','scripts.grasp_act_student_worker','--model',str(a.model),
                '--threads',str(t)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True)
            try:
                if response(worker)!={'ready':True}:raise ValueError('worker initialization failed')
                times=[]
                for request in requests:
                    if time.monotonic()>=deadline:raise TimeoutError('finite 1800s deployment benchmark cap')
                    started=time.monotonic();worker.stdin.write(request);worker.stdin.flush()
                    r=response(worker,timeout=min(120.,max(.01,deadline-time.monotonic())));dt=time.monotonic()-started
                    if set(r)!={'chunk'}:raise ValueError('bad worker output')
                    times.append(dt)
                measured=times[8:];p95=float(np.quantile(measured,.95))
                report['threads'].append({'intraop':t,'interop':('library default' if t==1 else 1),'warmup_N':8,'measured_N':32,
                    'median_s':float(np.median(measured)),'p95_s':p95,'maximum_s':max(measured),
                    'samples_s':measured,'refresh_budget_fit':{str(n):p95<=.1*n for n in (1,2,3,4,8)}})
            finally:
                worker.stdin.close()
                try:worker.wait(timeout=10)
                except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=10)
        report['complete']=True
    finally:write_json(a.output,report)


if __name__=='__main__':main()
