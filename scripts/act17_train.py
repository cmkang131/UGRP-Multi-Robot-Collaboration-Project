"""Finite matched ACT17 v7 training; no simulator, renderer or LLM client."""
from datetime import datetime,timezone
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,LEROBOT_ACT_SHA256,ACT_SHA
from act17_data import Dataset,library,read
from act17_compact_records import original_sha256
from act17_policy import save_actor,Actor,observation_batch

ROOT=Path(__file__).resolve().parents[1]
B=Path('/home/ugrp/ugrp-sim')


def write(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['dataset','protocol','out']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--candidate',choices=['M','F','S'],required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT);library()
    protocol=read(a.protocol);candidate=next(c for c in protocol['candidates'] if c['id']==a.candidate)
    if protocol.get('schema')!='ugrp.act17.v7.protocol.v1' or len(protocol['train_seeds'])!=200 or len(protocol['validation_seeds'])!=40:
        raise ValueError('registered v7 research protocol required; pilot preparation is not research training')
    data=Dataset(a.dataset,'train',image_mode=candidate['image_mode'])
    if data.manifest['protocol']!=protocol or set(data.manifest['eligible_train_seeds'])!=set(protocol['train_seeds']):
        raise ValueError('all preregistered200 TRAIN demonstrations must be valid before this comparison')
    a.out.mkdir(parents=True,exist_ok=False)
    import torch
    from harness.grasp_act_policy import make_policy
    from harness.grasp_act_loss import policy_loss
    from lerobot.policies.act import modeling_act
    if sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256:raise ValueError('pinned valid-normalized ACT runtime required')
    if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):raise ValueError('gcp2 L4 required')
    torch.manual_seed(protocol['training']['seed']);torch.cuda.manual_seed_all(protocol['training']['seed'])
    torch.set_num_threads(2);torch.backends.cudnn.benchmark=False
    generator=torch.Generator().manual_seed(protocol['training']['seed'])
    policy=make_policy(pretrained=True,device='cuda')
    optimizer=torch.optim.AdamW(policy.get_optim_params(),lr=1e-5,weight_decay=1e-4)
    priors=data.completion_priors(candidate['sampling'])
    # Actual capture -> tensor parity, not a synthetic shape-only check.
    first=data.manifest['episodes'][0]
    first=next(ep for ep in data.manifest['episodes'] if ep['split']=='train')
    metadata=data.metadata[0]
    observations=read(Path(first['source_capture'])/'student-r1.jsonl',lines=True)
    obs=next(o for o in observations if o['sample_id']==metadata['sample_id'])
    jpgs=[(Path(first['source_capture'])/ref['path']).read_bytes() for ref in obs['rgb']]
    own=observation_batch(obs,jpgs,data.stats,candidate['image_mode'])
    train=data[0]
    if any(not __import__('numpy').array_equal(value,train[key]) for key,value in own.items()):
        raise ValueError('recorded TRAIN and deployment preprocessing differ')
    config=dict(source_sha=source,cohort='act17-v7-native',host=host,contact_profile='warp_native_contact_v1',
        dataset_manifest_sha256=original_sha256(a.dataset/'manifest.json'),protocol_sha256=sha256(a.protocol),
        normalization_sha256=data.manifest['normalization']['sha256'],candidate=a.candidate,**candidate,
        steps_requested=protocol['training']['steps_round1'],batch_size=8,chunk=8,period_s=.1,
        seed=protocol['training']['seed'],done_loss='balanced_bce_v1',lerobot_act_sha256=LEROBOT_ACT_SHA256,
        act_library_source_sha=ACT_SHA,data_conversion_source_sha=data.manifest['source_sha'],
        provenance_note='new v7 data only; no v4 teacher states or checkpoints',
        train_inference_transform_identical=True)
    report={**config,'status':'running','complete':False,'steps_completed':0,'readback_verified':False,
        'TRAIN_rows':len(data),'TRAIN_starts':len(data.episode_indices),'TRAIN_stage_counts':{k:len(v) for k,v in data.stage_indices.items()},
        'environment':{k:importlib.metadata.version(k) for k in ['torch','torchvision','lerobot','numpy']},
        'gpu':torch.cuda.get_device_name(0),'started_utc':datetime.now(timezone.utc).isoformat(),
        'raw_optimizer_state_saved':False,'optimizer_note':'final weights and exact training recipe retained; no implicit resume or additional updates',
        'student_input_keys':sorted(own),'teacher_phase_policy_input':False}
    report['TRAIN_completion_priors']=priors
    lease=B/'leases'/('act17-train-'+a.candidate+'.json')
    with lease.open('x') as f:json.dump(dict(task='act17',candidate=a.candidate,pid=os.getpid(),concurrency=0,start=report['started_utc'],expected_end='finite10000updates, no wall cap'),f)
    stop={'requested':False}
    for sig in [signal.SIGINT,signal.SIGTERM]:signal.signal(sig,lambda *_:stop.update(requested=True))
    started=time.monotonic();step=0
    try:
        from harness.act_training import checkpoint_encoder
        with (a.out/'progress.jsonl').open('x') as stream:
            while step<config['steps_requested']:
                if stop['requested']:break
                ids=data.sample(generator,8,candidate['sampling'])
                batch=torch.utils.data.default_collate([data[i] for i in ids])
                batch={k:v.to('cuda') for k,v in batch.items()}
                policy.train();optimizer.zero_grad(set_to_none=True)
                with checkpoint_encoder(policy,enabled=True):
                    loss,metrics=policy_loss(policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                    if not torch.isfinite(loss):raise ValueError('nonfinite training loss')
                    loss.backward()
                norm=torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True)
                optimizer.step();step+=1
                if step==1 or step%10==0:
                    row=dict(step=step,loss=float(loss),**metrics,gradient_norm=float(norm),wall_s=time.monotonic()-started)
                    stream.write(json.dumps(row)+'\n');stream.flush()
                    report.update(steps_completed=step,latest=row);write(a.out/'summary.json',report)
        provenance={**config,'step':step,'training_complete':step==config['steps_requested']}
        save_actor(policy,a.out/'actor',data.stats,provenance,image_mode=candidate['image_mode'],sampling=candidate['sampling'])
        restored=Actor.load(a.out/'actor',device='cuda')
        inputs={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in own.items()}
        policy.eval()
        with torch.inference_mode():
            if not torch.equal(policy.predict_action_chunk(inputs),restored.policy.predict_action_chunk(inputs)):
                raise ValueError('saved model prediction changed')
        report.update(status='complete' if step==config['steps_requested'] else 'SUPERVISOR_STOP',complete=step==config['steps_requested'],
            steps_completed=step,readback_verified=True,checkpoint=str(a.out/'actor'),
            checkpoint_sha256=sha256(a.out/'actor/model.safetensors'),peak_gpu_bytes=torch.cuda.max_memory_allocated())
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        report['wall_s']=time.monotonic()-started;write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
