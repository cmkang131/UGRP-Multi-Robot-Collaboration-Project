"""Opt-in gcp2 synthetic CUDA plumbing check; excluded from ACT16 training.

One artificial optimizer update checks the real batch8/chunk8 input shapes,
balanced completion loss, activation checkpointing, v3 causal adapter, model
save/reload and optimizer state. No episode, teacher, simulator or heldout data
is accessed. This temporary random-input checkpoint is never evaluated or
registered as a research model; it is a preparation test, not an ACT16 arm.
"""
import argparse
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import signal
import sys
import time

from act16w_runtime import ACT_SHA,require_gcp2,frozen_source,sha256


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--act-source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if not a.enabled:p.error('synthetic CUDA preflight is default OFF')
    host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1]);library=frozen_source(a.act_source,ACT_SHA)
    a.out.mkdir(parents=True,exist_ok=False);start=time.monotonic();lease=Path('/home/ugrp/ugrp-sim/leases/act16w-cuda-preflight.json')
    report=dict(status='running',research_result=False,research_optimizer_steps=0,synthetic_optimizer_steps=0,host=host,source_sha=source,act_source_sha=library)
    with lease.open('x') as f:json.dump(dict(task='act16w-cuda-preflight',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end=(datetime.now(timezone.utc)+timedelta(minutes=3)).isoformat(),concurrency=0,stage='synthetic CUDA plumbing only'),f)
    def cap(*_):raise TimeoutError('synthetic resource cap180s')
    signal.signal(signal.SIGALRM,cap);signal.alarm(180)
    try:
        sys.path.insert(0,str(a.act_source))
        import torch
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import make_policy
        from harness.grasp_act_data import IMAGE_KEYS,MODEL_IMAGE_HW,assert_tensor_keys
        from harness.grasp_act_loss import policy_loss
        from harness.act_training import checkpoint_encoder
        from act16w_input import transform_batch,save_actor,Act16wActor,contract_check
        contract_check(c)
        torch.manual_seed(20261015);torch.cuda.manual_seed_all(20261015);torch.set_num_threads(4);torch.backends.cudnn.benchmark=False
        stats=dict(state_mean=[0.]*c.CONTEXT_DIM,state_std=[1.]*c.CONTEXT_DIM,action_mean=[0.]*c.ACTION_DIM,action_std=[1.]*c.ACTION_DIM,fit_scope='SYNTHETIC_PREFLIGHT_ONLY')
        state=torch.ones((8,c.CONTEXT_DIM),device='cuda');state[:,c.HISTORY*14:c.HISTORY*14+len(c.SKILLS)]=0.;state[:,c.HISTORY*14]=1.
        batch={'observation.state':state,IMAGE_KEYS[0]:torch.zeros((8,3,*MODEL_IMAGE_HW),device='cuda'),
               'action':torch.zeros((8,c.CHUNK,c.ACTION_DIM),device='cuda'),'action_is_pad':torch.zeros((8,c.CHUNK),dtype=torch.bool,device='cuda')}
        batch['action'][::2,:,-1]=1.
        assert_tensor_keys(batch,training=True);batch=transform_batch(batch,'wheel_pulse_train_mean')
        policy=make_policy(pretrained=True,device='cuda');optimizer=torch.optim.AdamW(policy.get_optim_params(),lr=1e-5,weight_decay=1e-4)
        policy.train();optimizer.zero_grad(set_to_none=True)
        with checkpoint_encoder(policy,enabled=True):
            loss,metrics=policy_loss(policy,batch,mode='balanced_bce_v1',stats=stats,priors={c.SKILLS[0]:{'positive_fraction':.5}})
            if not torch.isfinite(loss):raise ValueError('nonfinite synthetic loss')
            loss.backward()
        norm=torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True);optimizer.step()
        report.update(synthetic_optimizer_steps=1,loss=float(loss),gradient_norm=float(norm))
        save_actor(policy,a.out/'actor',stats,dict(synthetic_only=True,research_result=False,source_sha=source,act_source_sha=library),mode='wheel_pulse_train_mean')
        torch.save({'optimizer':optimizer.state_dict(),'rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all()},a.out/'optimizer.pt')
        loaded=Act16wActor.load(a.out/'actor',device='cuda');saved_optimizer=torch.load(a.out/'optimizer.pt',map_location='cpu',weights_only=True)
        optimizer.load_state_dict(saved_optimizer['optimizer'])
        probe={k:v[:1] for k,v in batch.items() if k.startswith('observation.')};assert_tensor_keys(probe);policy.eval()
        with torch.inference_mode():
            expected=policy.predict_action_chunk(probe);actual=loaded.policy.predict_action_chunk(probe)
        if not torch.equal(expected,actual):raise ValueError('synthetic model readback differs')
        report.update(status='complete',passed=True,batch=8,chunk=c.CHUNK,model_input_hw=list(MODEL_IMAGE_HW),adapter_mode=loaded.mode,readback_exact=True,optimizer_reload=True,peak_gpu_bytes=torch.cuda.max_memory_allocated(),gpu=torch.cuda.get_device_name(0),metrics=metrics)
    except BaseException as error:
        report.update(status='cap_end' if isinstance(error,TimeoutError) else 'HOST_ERROR',error=repr(error));raise
    finally:
        signal.alarm(0);report['wall_s']=time.monotonic()-start
        report['files']={str(x.relative_to(a.out)):sha256(x) for x in a.out.rglob('*') if x.is_file() and x.name!='summary.json'}
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()

if __name__=='__main__':main()
