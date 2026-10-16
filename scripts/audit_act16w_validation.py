"""Teacher-forced validation action audit; never closed-loop task success.

Uses only the declared validation tensors, full valid horizons and the same
serialized input transform as deployment. Persistence uses the actual last
issued command for evaluation only, including in the masked-history arm.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256, evaluation_seed_guard
from act16w_input import Act16wActor,transform_batch,HISTORY,STRIDE


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    for k in ('act-source','dataset','checkpoint','protocol','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:p.error('validation action audit default OFF')
    host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1]);frozen_source(a.act_source,ACT_SHA)
    sys.path.insert(0,str(a.act_source))
    import torch
    from harness.grasp_act_data import GraspDataset,assert_tensor_keys
    data=GraspDataset(a.dataset,'validation');meta=json.loads((a.checkpoint/'adapter.json').read_text())
    model_hash=sha256(a.checkpoint/'model.safetensors');manifest=json.loads((a.dataset/'manifest.json').read_text())
    if meta['provenance']['dataset_manifest_sha256']!=sha256(a.dataset/'manifest.json'):raise ValueError('validation dataset differs from training provenance')
    seeds=manifest['protocol']['validation_seeds']
    evaluation_seed_guard(meta['provenance'],seeds,split='validation',protocol=json.loads(a.protocol.read_text()),model_sha256=model_hash)
    actor=Act16wActor.load(a.checkpoint,device='cuda');torch.set_num_threads(4)
    a.out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    report=dict(status='running',complete=False,source_sha=source,host=host,checkpoint_sha256=model_hash,validation_seeds=seeds,
        scope='teacher-forced prediction on validation5; not task success, not final40, no checkpoint/policy selection',history_mode=actor.mode)
    sums=dict(wheel=0.,persistence_wheel=0.,continuous=0.,transition_wheel=0.,transition_persistence=0.,done_brier_h0=0.)
    counts=dict(rows=0,valid_horizons=0,transition_rows=0,done_positives_h0=0)
    try:
        for offset in range(0,len(data),8):
            ids=list(range(offset,min(len(data),offset+8)))
            batch=torch.utils.data.default_collate([data[i] for i in ids]);assert_tensor_keys(batch,training=True)
            inputs=transform_batch({k:v.to('cuda') for k,v in batch.items() if k.startswith('observation.')},actor.mode)
            with torch.inference_mode():pred=actor.policy.predict_action_chunk(inputs).cpu().numpy()
            pred=actor.base.decode_predictions(pred.reshape(-1,14)).reshape(len(ids),8,14)
            for prediction,index in zip(pred,ids):
                shard,row=data.index[index];s=data.shards[shard];valid=~s['action_is_pad'][row];truth=s['action'][row]
                previous=s['state'][row,(HISTORY-1)*STRIDE:HISTORY*STRIDE-1];error=np.abs(prediction[:,:13]-truth[:,:13])
                sums['wheel']+=float(error[valid,:4].sum());sums['continuous']+=float(error[valid].sum())
                sums['persistence_wheel']+=float(np.abs(previous[:4]-truth[valid,:4]).sum());counts['valid_horizons']+=int(valid.sum())
                if not valid[0]:raise ValueError('missing current-action supervision')
                if np.any(truth[0,:4]!=previous[:4]):
                    counts['transition_rows']+=1;sums['transition_wheel']+=float(error[0,:4].sum());sums['transition_persistence']+=float(np.abs(previous[:4]-truth[0,:4]).sum())
                counts['done_positives_h0']+=int(truth[0,-1]);sums['done_brier_h0']+=float((prediction[0,-1]-truth[0,-1])**2);counts['rows']+=1
            report.update(counts=counts,wall_s=time.monotonic()-started);(a.out/'progress.json').write_text(json.dumps(report)+'\n')
        else:report.update(status='complete',complete=True)
        n=counts['valid_horizons'];t=counts['transition_rows'];r=counts['rows']
        report['metrics']=dict(wheel_MAE=sums['wheel']/(4*n) if n else None,persistence_wheel_MAE=sums['persistence_wheel']/(4*n) if n else None,
            continuous13_MAE=sums['continuous']/(13*n) if n else None,transition_h0_wheel_MAE=sums['transition_wheel']/(4*t) if t else None,
            transition_h0_persistence_MAE=sums['transition_persistence']/(4*t) if t else None,done_Brier_h0=sums['done_brier_h0']/r if r else None)
    except BaseException as error:report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        report.update(counts=counts,wall_s=time.monotonic()-started);(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
