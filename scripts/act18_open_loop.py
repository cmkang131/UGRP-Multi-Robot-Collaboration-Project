"""Prior-z0 expert-state errors, same purpose for TRAIN and permitted VAL."""
import argparse
from collections import defaultdict
import gzip
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import library,read
from act17_policy import Actor as OldActor
from act17_open_loop import action_errors,quantiles
from act18_policy import Actor,ReferenceDataset
from act18_diagnose import write,confusion
from act18_evaluate import allowed_seeds


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--baseline-act17',action='store_true')
    p.add_argument('--stage',choices=['train','validation'],default='train')
    p.add_argument('--selection',type=Path)
    for name in ('dataset','checkpoint','protocol','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:
        p.error('reference diagnostic is default OFF')
    host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1]);library()
    import torch
    from harness import grasp_act_contract as c
    torch.set_num_threads(2)
    meta=read(a.checkpoint/'adapter.json');digest=sha256(a.checkpoint/'model.safetensors')
    protocol=read(a.protocol)
    wanted=allowed_seeds(protocol,a.stage,read(a.selection) if a.selection else {},digest)
    if a.baseline_act17 and a.stage!='train':
        raise ValueError('baseline only diagnoses TRAIN')
    actor=(OldActor if a.baseline_act17 else Actor).load(a.checkpoint,device='cuda')
    chunk=8 if a.baseline_act17 else meta['chunk']
    data=ReferenceDataset(a.dataset,'train' if a.stage=='train' else 'validation',chunk=chunk)
    ids=[i for i,m in enumerate(data.metadata) if m['seed'] in wanted]
    if {data.metadata[i]['seed'] for i in ids}!=wanted:
        raise ValueError('exact registered diagnostic seeds missing')
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(source_sha=source,host=host,stage=a.stage,seeds=sorted(wanted),complete=False,
        checkpoint_sha256=digest,step=meta['provenance']['step'],candidate=meta['provenance']['candidate'],
        rows=len(ids),physics_steps=0,training_updates=0,reproduce=sys.argv,stages={})
    groups=defaultdict(lambda:defaultdict(list));wheel=defaultdict(lambda:defaultdict(list))
    started=time.monotonic()
    try:
        with gzip.open(a.out/'frames.jsonl.gz','xt') as stream:
            import json
            for offset in range(0,len(ids),8):
                selected=ids[offset:offset+8]
                batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([data[i] for i in selected]).items() if k.startswith('observation.')}
                with torch.inference_mode():
                    predictions=actor.policy.predict_action_chunk(batch).cpu().numpy()
                predictions=actor.base.decode_predictions(predictions) if a.baseline_act17 else actor.decode(predictions)
                for i,pred in zip(selected,predictions):
                    j,k=data.index[i];truth=data.shards[j]['action'][k,0];metadata=data.metadata[i]
                    decoded=c.decode_action(pred[0]);projected=np.asarray(c.encode_action(dict(t=metadata['t'],**{k:decoded[k] for k in ('wheels','duration_s','pwm')}),done=decoded['done']))
                    for stage in ('all',metadata['stage']):
                        groups[stage]['rows'].append(1)
                        for mode,value in [('raw',pred[0]),('projected',projected)]:
                            for unit,error in action_errors(value,truth).items():
                                groups[stage][mode+':'+unit].extend(error.tolist())
                        for key,value in [('truth',truth[:4]),('raw',pred[0,:4]),('projected',projected[:4])]:
                            wheel[stage][key].extend(value.tolist())
                    stream.write(json.dumps(dict(**metadata,teacher=truth.tolist(),prediction=pred[0].tolist(),projected=projected.tolist()))+'\n')
        report.update(complete=True,status='complete',
            stages={s:dict(rows=len(v['rows']),errors={k:quantiles(x) for k,x in v.items() if ':' in k},wheel_confusion=confusion(**wheel[s])) for s,v in groups.items()})
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error))
        raise
    finally:
        report['wall_s']=time.monotonic()-started
        write(a.out/'summary.json',report)


if __name__=='__main__':
    main()
