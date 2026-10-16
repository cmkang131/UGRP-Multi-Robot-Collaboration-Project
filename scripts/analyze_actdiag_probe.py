"""Fixed 3 rows/shard across saved ACT checkpoints; inference only, no fitting."""
from pathlib import Path
from collections import defaultdict
import argparse
import json
import time
import numpy as np
import torch
from harness.grasp_act_data import GraspDataset,INPUT_KEYS,write_json,read_json,sha256
from harness.beamact_input import BeamActor,transform_batch
from analyze_actdiag import dataset_view,metrics,decoded,existing


def main():
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=True);torch.set_num_threads(4)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--inference',type=Path,required=True)
    p.add_argument('--checkpoint-names',nargs='+',default=['step300','step5000','step10000'])
    a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    base=Path('/home/ugrp/ugrp-sim/ops-reviews/beamact2')
    root=dataset_view(base/'data-v1/split-v1',a.output)
    stages={r['sample_id']:r['phase'] for r in read_json(existing(base/'data-v1/stages.json'))}
    data=[];splitnames=[];targets=[];phases=[]
    for split in ('train','validation'):
        d=GraspDataset(root,split);offset=0
        for ep in (e for e in d.manifest['episodes'] if e['split']==split):
            n=ep['rows_selected']
            meta=read_json(root/ep['path']/'samples.json')
            for i in sorted({0,n//2,n-1}):
                item=d[offset+i];data.append(item);splitnames.append(split)
                targets.append(item['action'][0]*np.asarray(d.stats['action_std'])+d.stats['action_mean'])
                phases.append(stages[meta[i]['sample_id']])
            offset+=n
    targets=np.asarray(targets);splitnames=np.asarray(splitnames);phases=np.asarray(phases);result={}
    models=[('step300',base/'train/smoke/step-000300/actor'),('step5000',base/'train/main/step-005000/actor'),('step10000',base/'train/main/step-010000/actor')]
    begin=time.monotonic()
    for name,model in models:
        if name not in a.checkpoint_names:continue
        actor=BeamActor.load(model,device='cuda');values=[];role_values=[];image_values=[]
        for start in range(0,len(data),8):
            batch=torch.utils.data.default_collate(data[start:start+8])
            inputs=transform_batch({k:batch[k].to('cuda') for k in INPUT_KEYS},actor.mode)
            with torch.inference_mode():
                prediction=actor.policy.predict_action_chunk(inputs).cpu().numpy()
                values.extend(actor.decode_predictions(prediction)[:,0])
                if name=='step10000':
                    changed={k:v.clone() for k,v in inputs.items()}
                    # Fixed contract role one-hot slots: history224 + skill4 +
                    # kind9 = role offset237; swap teal and blue instruction.
                    changed['observation.state'][:,[237,238]]=changed['observation.state'][:,[238,237]]
                    role_values.extend(actor.decode_predictions(actor.policy.predict_action_chunk(changed).cpu().numpy())[:,0])
                    changed={**inputs,'observation.images.own_history':inputs['observation.images.own_history'].roll(1,0)}
                    image_values.extend(actor.decode_predictions(actor.policy.predict_action_chunk(changed).cpu().numpy())[:,0])
        values=np.asarray(values);result[name]={}
        for split in ('train','validation'):
            mask=splitnames==split
            result[name][split]=dict(ACT_raw=metrics(values[mask],targets[mask]),ACT_decoded=metrics(decoded(values[mask]),targets[mask]))
        if name=='step10000':
            result['posthoc_sensitivity']={}
            for n,v in [('role_swap',role_values),('batch_rgb_roll',image_values)]:
                v=np.asarray(v);result['posthoc_sensitivity'][n]=dict(h0_raw_change=metrics(v,values),
                    baseline=metrics(decoded(values),targets),changed=metrics(decoded(v),targets),
                    per_phase={ph:dict(N=int((phases==ph).sum()),h0_raw_change=metrics(v[phases==ph],values[phases==ph]),
                        baseline=metrics(decoded(values[phases==ph]),targets[phases==ph]),
                        changed=metrics(decoded(v[phases==ph]),targets[phases==ph])) for ph in sorted(set(phases))},
                    scope='post-hoc OOD input sensitivity, not a retrained causal ablation or deployment candidate')
            np.savez_compressed(a.output/'sensitivity.npz',original=values,role_swap=role_values,
                rgb_roll=image_values,target=targets,phase=phases,split=splitnames)
        result[name]['model_sha256']=sha256(model/'model.safetensors')
        del actor;torch.cuda.empty_cache();print(name,'complete',flush=True)
    windows=[]
    logs=[]
    for stage in ('smoke','main'):
        f=base/f'train/{stage}/progress.jsonl';logs.extend(json.loads(l) for l in f.read_text().splitlines())
    for low,high in [(1,300),(301,1000),(1001,3000),(3001,5000),(5001,7000),(7001,9000),(9001,10000)]:
        rows=[r for r in logs if low<=r['step']<=high]
        windows.append(dict(steps=[low,high],logged_N=len(rows),**{k:dict(mean=float(np.mean([r[k] for r in rows])),median=float(np.median([r[k] for r in rows]))) for k in ('loss','movement_l1_loss','done_bce_loss','kld_loss','gradient_norm')}))
    result.update(scope=__doc__,rows=len(data),sample_rule='first/middle/last of every shard; fixed before seeing predictions',
        loss_windows=windows,validation_loss_logged_during_training=False,optimizer_steps=0,wall_s=time.monotonic()-begin,
        effective_train_row_passes=10000*8/60023)
    write_json(a.output/'probe.json',result)


if __name__=='__main__':main()
