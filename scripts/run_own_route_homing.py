"""egomap68: own-RGB homing, fixed four conditions x six checkpoints."""
import argparse
import hashlib
import json
import os
import pickle
import platform
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from harness.active_camera import bind,SEARCH
from harness.own_route_reference import Options,install as route_install
from harness.own_route_homing import install as homing_install
from harness.own_rgb_homing import OPTION,PARAMS,Memory
from harness.own_teach_capture import vertex_decision
from harness.self_pose_graph import between
from scripts import run_own_route_traversed as previous

ref=previous.ref
ROOT=ref.ROOT
PLAN=ROOT/'experiments/2026-10-11-own-rgb-homing/prereg.json'
CONDITIONS={k:Options(return_own_free_astar=k!='baseline') for k in ('baseline','traversed','homing','loopclosure')}


def registration():return json.loads(PLAN.read_text())


def bank_root():
    return Path.home()/'ugrp-sim/runs/egomap68-banks/data'


def homing_on(condition):return condition in ('homing','loopclosure')


def build_banks(out):
    """Offline own RGB only. No checkpoint unpickle, model or simulator import."""
    if platform.system()!='Linux' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':
        raise RuntimeError('ORACLE_ONLY_OFFLINE_RGB')
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    for cp in registration()['checkpoints']:
        source=Path(cp['path']).parents[1]
        trace=[r for r in ref.rows(source/'own-controller.jsonl') if r['t']<=cp['sim_s']]
        images={r['frame_id']:r for r in ref.rows(source/'robots/r3/frames.jsonl') if r['sim_time']<=cp['sim_s']}
        m=Memory()
        for row in trace:
            if m.frames and vertex_decision(between(m.frames[-1].pose,row['local_pose']))=='candidate':continue
            info=images[row['frame_id']];p=source/info['path']
            data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=info['sha256']:raise ValueError('OWN_RGB_PREFIX_HASH')
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
            m.add(m.extract(rgb,SEARCH,row['local_pose'],row['t'],row['frame_id'],info['sha256']),force=True)
        payload=pickle.dumps(dict(frames=m.frames,home=[f.frame_id for f in m.home],triangulated=m.triangulated),protocol=5)
        target=out/f"bank-{cp['seed']}.npz"
        np.savez_compressed(target,payload=np.frombuffer(payload,np.uint8))
        record=dict(seed=cp['seed'],source=str(source),cutoff_sim_s=cp['sim_s'],last_frame=max(f.frame_id for f in m.frames),
                    checkpoint_sha256=cp['sha256'],sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,
                    **m.snapshot())
        ref.old.dump(out/f"bank-{cp['seed']}.json",record)
        records.append(record)
        print(json.dumps({k:record[k] for k in ('seed','frames','home_frames','points','bytes')}),flush=True)
    ref.old.dump(out/'manifest.json',dict(source_sha=ROOT.name,params=PARAMS,banks=records,gt_input=False))
    return 0


def load_memory(seed):
    root=bank_root();record=json.loads((root/f'bank-{seed}.json').read_text())
    p=root/f'bank-{seed}.npz'
    if hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('OWN_BANK_HASH')
    cp=next(x for x in registration()['checkpoints'] if x['seed']==seed)
    if cp['sha256']!=record['checkpoint_sha256'] or record['cutoff_sim_s']!=cp['sim_s']:
        raise ValueError('OWN_BANK_CAUSAL_CUTOFF')
    with np.load(p,allow_pickle=False) as z:data=pickle.loads(z['payload'].tobytes())
    m=Memory();m.frames=data['frames'];m.home=[f for f in m.frames if f.frame_id in data['home']]
    m.triangulated=data['triangulated']
    return m


def bundle(seed,source,condition,mode):
    b=ref.previous.bundle(seed,source,'baseline',mode)
    b['execution_bundle_id']=f'egomap68-{mode}-{condition}-{seed}-v1'
    b['options'].update({k:'on_v1' if v else 'off' for k,v in asdict(CONDITIONS[condition]).items()})
    b['options'].update(traversed_free='off' if condition=='baseline' else 'footprint_history_v1',
                        visual_homing=OPTION if homing_on(condition) else 'off',
                        visual_loop=OPTION if condition=='loopclosure' else 'off')
    b['host_alarm_s']=registration()['host_alarm_s']
    b['homing_parameters']=PARAMS
    b['admission']='egomap68 same6 DEV, own-prefix RGB only; no new seed confirmation or E2E claim'
    return b


def run(a):
    a.stage_schedule=ref.SCHEDULE;a.profile='baseline'
    b=bundle(a.seed,ROOT.name,a.condition,a.mode)
    bank=load_memory(a.seed) if homing_on(a.condition) else None
    audit=[];controller=[]
    def load(path,out):
        backend,c,start,tick,cp=ref.old.checkpoint_load(path,out)
        route_install(c,CONDITIONS[a.condition],traversed_free=b['options']['traversed_free'])
        homing_install(c,visual_homing=b['options']['visual_homing'],visual_loop=b['options']['visual_loop'],memory=bank)
        controller.append(c);ref.arrival_audit(c,audit)
        def emit(row):
            row['visual_homing']=getattr(c,'_homing_calls',None)
            row['visual_path']=getattr(c,'_homing_executed',None)
            if homing_on(a.condition):
                row['valid']=row['valid'] and row['visual_homing']==row['call'] and row['visual_path'].get('receive',False)
            with (out/'execution-path.jsonl').open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
            if not row['valid']:raise RuntimeError('HOMING_RECEIVE_NOT_EXECUTED')
        previous.execution_audit(c,CONDITIONS[a.condition],emit)
        return backend,c,start,tick,cp
    def alarm(n):return signal.alarm(b['host_alarm_s'] if n else 0)
    r=bind(ref.old.run,bundle=lambda *args:b,checkpoint_load=load,server_slot=ref.server_slot,
        install=ref.previous.previous.install,signal=SimpleNamespace(**{**vars(signal),'alarm':alarm}))(a)
    ref.old.dump(a.output/'arrival-gates.json',audit)
    if bank is not None:
        ref.old.dump(a.output/'visual-homing.json',dict(**bank.snapshot(),corrections=controller[0]._homing_corrections if controller else []))
    return r


def jobs(out):
    return [dict(name=f'egomap68-{c["seed"]}-{condition}',seed=c['seed'],condition=condition,profile='baseline',status='QUEUED',
        checkpoint=c['path'],checkpoint_sha256=c['sha256'],output=str(Path(out)/f'egomap68-{c["seed"]}-{condition}'),
        command=[sys.executable,'-m','scripts.run_own_route_homing','--mode','stage','--seed',str(c['seed']),
                 '--condition',condition,'--output',str(Path(out)/f'egomap68-{c["seed"]}-{condition}')])
        for c in registration()['checkpoints'] for condition in CONDITIONS]


def score_batch(plan,out):
    reports=bind(ref.score_batch,aggregate=bind(ref.aggregate,CONDITIONS=CONDITIONS))(plan,out,round_name='egomap68')
    for r in reports:
        p=Path(r['raw'])/'visual-homing.json'
        d=json.loads(p.read_text()) if p.exists() else {}
        attempts=d.get('attempts',[])
        from collections import Counter
        r['visual_matching']=dict(attempts=len(attempts),accepted=sum(x['status']=='accepted' for x in attempts),
            reasons=dict(Counter(x['reason'] for x in attempts)),corrections=len(d.get('corrections',[])),
            home_attempts=sum(x['scope']=='home' for x in attempts),home_accepted=sum(x['scope']=='home' and x['status']=='accepted' for x in attempts))
    ref.old.dump(out/'scores.json',reports)
    aggregate=bind(ref.aggregate,CONDITIONS=CONDITIONS)(reports)
    for c in CONDITIONS:
        a=[r['visual_matching'] for r in reports if r['condition']==c]
        aggregate[c]['visual_matching']={k:sum(x[k] for x in a) for k in ('attempts','accepted','corrections','home_attempts','home_accepted')}
    ref.old.dump(out/'summary.json',dict(round='egomap68',host='oracle-x86',source_sha=ROOT.name,registered=24,conditions=aggregate,
        runs=reports,thresholds_changed=False,raw_root=str(out),scores_sha256=hashlib.sha256((out/'scores.json').read_bytes()).hexdigest()))


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('banks','stage','smoke','batch'),required=True)
    p.add_argument('--condition',choices=tuple(CONDITIONS),default='baseline');p.add_argument('--seed',type=int,default=63001)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='banks':return build_banks(a.output)
    if a.mode=='batch':
        return bind(ref.batch,jobs=jobs,registration=registration,early_check=previous.early_check,score_batch=score_batch)(a,required_free_gib=20)
    a.checkpoint=Path(next(c['path'] for c in registration()['checkpoints'] if c['seed']==a.seed))
    if a.mode=='smoke':a.mode='smoke_resume'
    r=run(a);print(json.dumps(r),flush=True)
    return 0 if r['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
