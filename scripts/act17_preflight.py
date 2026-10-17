"""Real pilot preprocessing/one-gradient/save/reload preparation; never a research model."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import Dataset,convert,library,read
from act17_policy import Actor,observation_batch,save_actor
from act17_v7 import ROOT,B


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['pilot','gate','protocol','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT);library()
    pilot=read(a.pilot/'gate-recount.json');protocol=read(a.protocol)
    if not pilot['complete'] or pilot['n']!=4 or pilot['N']!=4:raise ValueError('completed successful4 pilot required')
    a.out.mkdir(parents=True,exist_ok=False)
    seeds=pilot['requested_seeds'];micro={**protocol,'schema':'ugrp.act17.pilot_preparation_only.v1',
        'record_seeds':seeds,'train_seeds':seeds,'validation_seeds':[],'validation8_seeds':[]}
    convert(micro,read(a.gate),[a.pilot],a.out/'pilot-dataset')
    import torch
    from harness.grasp_act_policy import make_policy
    from harness.grasp_act_loss import policy_loss
    from harness.act_training import checkpoint_encoder
    torch.set_num_threads(2)
    report=dict(source_sha=source,host=host,scope='PREPARATION_ONLY: real pilot transform parity, one gradient and save/reload; no research model or success claim',
        complete=False,status='running',research_training_updates=0,preparation_gradients=0,models=[],physics_steps=0)
    lease=B/'leases/act17-preflight.json'
    with lease.open('x') as f:json.dump(dict(task='act17',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='three one-gradient preparation probes',concurrency=0),f)
    try:
        for candidate in protocol['candidates']:
            data=Dataset(a.out/'pilot-dataset','train',image_mode=candidate['image_mode']);priors=data.completion_priors(candidate['sampling'])
            first=data.manifest['episodes'][0];observation=next(o for o in read(Path(first['source_capture'])/'student-r1.jsonl',lines=True) if o['sample_id']==data.metadata[0]['sample_id'])
            jpgs=[(Path(first['source_capture'])/r['path']).read_bytes() for r in observation['rgb']]
            deployed=observation_batch(observation,jpgs,data.stats,candidate['image_mode']);training=data[0]
            if any(not np.array_equal(v,training[k]) for k,v in deployed.items()):raise ValueError('actual capture preprocess differs')
            torch.manual_seed(protocol['training']['seed']);policy=make_policy(pretrained=True,device='cuda');optimizer=torch.optim.AdamW(policy.get_optim_params(),lr=1e-5,weight_decay=1e-4)
            generator=torch.Generator().manual_seed(protocol['training']['seed']);ids=data.sample(generator,8,candidate['sampling'])
            batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([data[i] for i in ids]).items()}
            policy.train();optimizer.zero_grad(set_to_none=True)
            with checkpoint_encoder(policy,enabled=True):
                loss,_=policy_loss(policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                if not torch.isfinite(loss):raise ValueError('nonfinite preparation gradient')
                loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True);optimizer.step()
            with tempfile.TemporaryDirectory(prefix='verification-only-',dir=a.out) as temporary:
                actor_path=Path(temporary)/'actor';save_actor(policy,actor_path,data.stats,
                    dict(source_sha=source,synthetic_only=True,preparation_only=True,step=1,training_complete=False),
                    image_mode=candidate['image_mode'],sampling=candidate['sampling'])
                restored=Actor.load(actor_path,device='cuda');policy.eval()
                inputs={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in deployed.items()}
                with torch.inference_mode():equal=torch.equal(policy.predict_action_chunk(inputs),restored.policy.predict_action_chunk(inputs))
                if not equal:raise ValueError('preparation save/reload differs')
                report['models'].append(dict(candidate=candidate['id'],image_mode=candidate['image_mode'],actual_transform_array_equal=True,
                    finite_gradient=True,save_reload_prediction_equal=True,verification_only_checkpoint_sha256=sha256(actor_path/'model.safetensors'),
                    verification_only_checkpoint_retained=False))
            report['preparation_gradients']+=1
            del restored,optimizer,policy,data,batch,inputs;torch.cuda.empty_cache()
        report.update(complete=True,status='complete')
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
