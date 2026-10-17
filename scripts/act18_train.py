"""Default-off, fixed 100k reference ACT comparison on existing v7 data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256, LEROBOT_ACT_SHA256, ACT_SHA
from act17_data import library, read
from act17_compact_records import original_sha256
from act17_policy import observation_batch
from act18_policy import CANDIDATES, ReferenceDataset, make_policy, save_actor, Actor
from act18_diagnose import write

B = Path('/home/ugrp/ugrp-sim')
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--candidate', choices=tuple(CANDIDATES), required=True)
    for name in ('dataset','protocol','out','queue'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled:
        p.error('reference ACT candidate is default OFF')
    host = require_gcp2(training=True)
    source = frozen_source(ROOT)
    library()
    protocol, queue = read(a.protocol), read(a.queue)
    if (protocol.get('schema')!='ugrp.act18.protocol.v1' or queue.get('source_sha')!=source
            or protocol['steps']!=100000 or protocol['batch_size']!=8
            or a.candidate not in queue['candidates']):
        raise ValueError('fixed registered matched queue required')
    data = ReferenceDataset(a.dataset, 'train', chunk=CANDIDATES[a.candidate])
    if (set(data.manifest['eligible_train_seeds'])!=set(protocol['train_seeds'])
            or original_sha256(a.dataset/'manifest.json')!=queue['dataset_manifest_sha256']):
        raise ValueError('same complete v7 TRAIN dataset required')
    import torch
    from harness.grasp_act_loss import policy_loss
    from lerobot.policies.act import modeling_act
    if sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256:
        raise ValueError('pinned valid-token normalized upstream required')
    if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):
        raise ValueError('L4 required')
    torch.set_num_threads(2)
    torch.manual_seed(protocol['seed'])
    torch.cuda.manual_seed_all(protocol['seed'])
    torch.backends.cudnn.benchmark=False
    generator=torch.Generator().manual_seed(protocol['seed'])
    policy=make_policy(data.chunk,device='cuda',pretrained=True)
    optimizer=torch.optim.AdamW(policy.get_optim_params(),lr=1e-5,weight_decay=1e-4)
    priors=data.completion_priors('uniform_episode_v1')
    first=next(ep for ep in data.manifest['episodes'] if ep['split']=='train')
    obs=next(o for o in read(Path(first['source_capture'])/'student-r1.jsonl',lines=True)
             if o['sample_id']==data.metadata[0]['sample_id'])
    jpgs=[(Path(first['source_capture'])/r['path']).read_bytes() for r in obs['rgb']]
    own=observation_batch(obs,jpgs,data.stats,'current_full_v1')
    if any(not __import__('numpy').array_equal(v,data[0][k]) for k,v in own.items()):
        raise ValueError('real training/deployment transforms differ')
    a.out.mkdir(parents=True,exist_ok=False)
    config=dict(source_sha=source,cohort='act18-v7-reference',candidate=a.candidate,
        host=host,contact_profile='warp_native_contact_v1',chunk=data.chunk,seed=protocol['seed'],
        steps_requested=protocol['steps'],batch_size=8,lr=1e-5,kl_weight=10.,
        normalization_sha256=data.manifest['normalization']['sha256'],
        dataset_manifest_sha256=queue['dataset_manifest_sha256'],protocol_sha256=sha256(a.protocol),
        lerobot_act_sha256=LEROBOT_ACT_SHA256,act_library_source_sha=ACT_SHA,
        done_loss='balanced_bce_v1',image_mode='current_full_v1',sampling='uniform_episode_v1',
        train_inference_transform_identical=True,gradient_checkpointing=False,
        static_map_use='none',wall_cap=None,optimizer_recipe='LeRobot AdamW defaults; no implicit resume')
    report=dict(**config,status='running',complete=False,steps_completed=0,
        started_utc=datetime.now(timezone.utc).isoformat(),TRAIN_rows=len(data),
        TRAIN_starts=len(data.episode_indices),readback_verified=False,checkpoints=[])
    lease=B/'leases'/('act18-train-'+a.candidate+'.json')
    with lease.open('x') as f:
        json.dump(dict(task='act18',candidate=a.candidate,pid=os.getpid(),start=report['started_utc'],
            expected_end='finite100000updates; no wall deadline',concurrency=0),f)
    stop={'requested':False}
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.update(requested=True))
    started=time.monotonic()
    try:
        with (a.out/'progress.jsonl').open('x') as stream:
            for step in range(1,protocol['steps']+1):
                if stop['requested']:
                    raise InterruptedError('explicit supervisor stop')
                ids=data.sample(generator,8,'uniform_episode_v1')
                batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([data[i] for i in ids]).items()}
                policy.train()
                optimizer.zero_grad(set_to_none=True)
                loss,metrics=policy_loss(policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                if not torch.isfinite(loss):
                    raise ValueError('nonfinite loss')
                loss.backward()
                # Same existing LeRobot training gradient clip1.0; no new motion/acceptance threshold.
                norm=torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True)
                optimizer.step()
                if step==1 or step%100==0:
                    row=dict(step=step,loss=float(loss),**metrics,gradient_norm=float(norm),wall_s=time.monotonic()-started)
                    stream.write(json.dumps(row)+'\n');stream.flush()
                    report.update(steps_completed=step,latest=row)
                    write(a.out/'summary.json',report)
                # Standard100k endpoint; intermediate10k/50k allow exact prior-z0
                # TRAIN diagnosis, never selection on FINAL or hidden VAL outcomes.
                if step in (10000,50000,100000):
                    folder=a.out/('step-'+str(step))
                    save_actor(policy,folder,data.stats,dict(**config,step=step,training_complete=step==protocol['steps']))
                    restored=Actor.load(folder,device='cuda')
                    inputs={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in own.items()}
                    policy.eval()
                    with torch.inference_mode():
                        if not torch.equal(policy.predict_action_chunk(inputs),restored.policy.predict_action_chunk(inputs)):
                            raise ValueError('saved prediction readback changed')
                    del restored
                    report['checkpoints'].append(dict(step=step,path=str(folder),sha256=sha256(folder/'model.safetensors'),readback_verified=True))
                    write(a.out/'summary.json',report)
        report.update(status='complete',complete=True,readback_verified=True,
            checkpoint=report['checkpoints'][-1]['path'],checkpoint_sha256=report['checkpoints'][-1]['sha256'],
            peak_gpu_bytes=torch.cuda.max_memory_allocated())
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',error=repr(error),complete=False)
        raise
    finally:
        report['wall_s']=time.monotonic()-started
        write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():
            lease.unlink()


if __name__=='__main__':
    main()
