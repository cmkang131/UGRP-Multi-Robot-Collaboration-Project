"""Audit all held-out v7 demonstration frames; no new physics or training."""
from collections import defaultdict
from datetime import datetime,timezone
import argparse
import gzip
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import Dataset,library,read
from act17_compact_records import original_sha256
from act17_policy import Actor
from act17_open_loop import action_errors,quantiles
from act17_v7 import ROOT,B


def audit_candidate(candidate,meta,training,manifest,dataset_sha,model_sha):
    p=meta.get('provenance',{})
    if (p.get('candidate')!=candidate or p.get('cohort')!='act17-v7-native'
            or p.get('contact_profile')!='warp_native_contact_v1'
            or not p.get('training_complete') or not training.get('complete')
            or not training.get('readback_verified') or p.get('step')!=manifest['protocol']['training']['steps_round1']
            or training.get('steps_completed')!=p.get('step')
            or p.get('dataset_manifest_sha256')!=dataset_sha or training.get('checkpoint_sha256')!=model_sha
            or p.get('normalization_sha256')!=manifest['normalization']['sha256']):
        raise ValueError('completed exact-dataset checkpoint and actual readback required for offline audit')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['models-root','dataset','out']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--candidates',nargs='+',choices=['M','F','S'],default=['M','F','S'],help='completed subset only; default all three')
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT);library()
    if len(a.candidates)!=len(set(a.candidates)):raise ValueError('unique audit candidate list required')
    a.out.mkdir(parents=True,exist_ok=False)
    import torch
    from harness import grasp_act_contract as c
    from harness.grasp_act_loss import policy_loss
    torch.set_num_threads(2)
    report=dict(source_sha=source,host=host,complete=False,status='running',cohort='act17-v7-native',arms={},physics_steps=0,training_updates=0,
        dataset_manifest_sha256=original_sha256(a.dataset/'manifest.json'),requested_candidates=a.candidates,
        scope='specified completed-model subset on VAL expert states; not whole M/F/S training completion or closed-loop student success',reproduce=sys.argv)
    lease=B/'leases/act17-open-loop-v7.json'
    with lease.open('x') as f:json.dump(dict(task='act17',pid=os.getpid(),start=datetime.now(timezone.utc).isoformat(),expected_end='finite3xallVALframes',concurrency=0),f)
    started=time.monotonic()
    try:
        for candidate in a.candidates:
            root=a.models_root/candidate/'actor';meta=read(root/'adapter.json');training=read(a.models_root/candidate/'summary.json')
            manifest=read(a.dataset/'manifest.json')
            audit_candidate(candidate,meta,training,manifest,report['dataset_manifest_sha256'],sha256(root/'model.safetensors'))
            actor=Actor.load(root,device='cuda')
            data=Dataset(a.dataset,'validation',image_mode=meta['image_mode'])
            priors=training['TRAIN_completion_priors']
            if meta['provenance']['normalization_sha256']!=data.manifest['normalization']['sha256']:
                raise ValueError('deployment and VAL normalizers differ')
            groups=defaultdict(lambda:defaultdict(list));losses=defaultdict(float)
            with gzip.open(a.out/(candidate+'-VAL-frames.jsonl.gz'),'xt') as stream:
                for offset in range(0,len(data),8):
                    ids=list(range(offset,min(offset+8,len(data))))
                    batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([data[i] for i in ids]).items()}
                    actor.policy.eval()
                    with torch.inference_mode():
                        pred=actor.policy.predict_action_chunk({k:v for k,v in batch.items() if k.startswith('observation.')}).cpu().numpy()
                        loss,metrics=policy_loss(actor.policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                    for key,value in dict(total_loss=float(loss),**metrics).items():losses[key]+=float(value)*len(ids)
                    pred=actor.base.decode_predictions(pred.reshape(-1,14)).reshape(len(ids),8,14)
                    for value,index in zip(pred,ids):
                        shard,row=data.index[index];truth=data.shards[shard]['action'][row];valid=~data.shards[shard]['action_is_pad'][row];metadata=data.metadata[index]
                        projected=c.decode_action(value[0]);projected=np.asarray(c.encode_action(dict(t=metadata['t'],**{k:projected[k] for k in ['wheels','duration_s','pwm']}),done=projected['done']))
                        for stage in ['all',metadata['stage']]:
                            groups[stage]['rows'].append(1)
                            for name,prediction,target in [('h0_raw',value[0],truth[0]),('h0_projected',projected,truth[0]),('valid_chunk',value[valid],truth[valid])]:
                                for unit,values in action_errors(prediction,target).items():groups[stage][name+':'+unit].extend(values.tolist())
                        stream.write(json.dumps(dict(**metadata,prediction_h0_encoded=value[0].tolist(),projected_h0_encoded=projected.tolist(),teacher_h0_encoded=truth[0].tolist()))+'\n')
            logs=read(a.models_root/candidate/'progress.jsonl',lines=True)[-100:]
            report['arms'][candidate]=dict(checkpoint_sha256=sha256(root/'model.safetensors'),rows=len(data),
                actual_optimizer_TRAIN_last100=dict(N=len(logs),loss_mean=float(np.mean([r['loss'] for r in logs])),first_step=logs[0]['step'],last_step=logs[-1]['step']),
                prior_z0_VAL_loss_sample_weighted={k:v/len(data) for k,v in losses.items()},
                stages={stage:dict(rows=len(v['rows']),errors={k:quantiles(x) for k,x in v.items() if ':' in k}) for stage,v in groups.items()})
            (a.out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
            del actor,data;torch.cuda.empty_cache()
        report.update(complete=True,status='complete')
    except BaseException as error:
        report.update(status='HOST_ERROR',complete=False,error=repr(error));raise
    finally:
        report['wall_s']=time.monotonic()-started;(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        if lease.exists() and read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':main()
