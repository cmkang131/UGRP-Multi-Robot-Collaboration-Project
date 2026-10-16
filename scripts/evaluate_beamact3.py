"""GCP2 offline ACT A/B metrics and slot-only intervention; no physics."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import GraspDataset, INPUT_KEYS, read_json, sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import source_sha
from scripts.evaluate_beamact1 import persistence, refresh_grid, decoded, errors


def stratified(prediction, baseline, target, phases, refresh):
    actor=decoded(prediction)
    stable=np.isclose(baseline[:,:4],target[:,:4],atol=1e-7,rtol=0).all(-1)
    result={}
    for grid,mask in [('all_h0',np.ones(len(target),bool)),('refresh_h0',refresh)]:
        result[grid]={}
        for segment,which in [('all',np.ones(len(target),bool)),('stable',stable),('transition',~stable)]:
            result[grid][segment]={}
            for phase in ['all',*sorted(set(phases))]:
                chosen=mask&which&(np.ones(len(target),bool) if phase=='all' else np.asarray(phases)==phase)
                if not chosen.any():continue
                a,b=errors(actor[chosen],target[chosen]),errors(baseline[chosen],target[chosen])
                result[grid][segment][phase]=dict(ACT=a,persistence=b,
                    wheel_improvement_percent=100*(1-a['wheel_mae']/b['wheel_mae']) if b['wheel_mae'] else None)
    return result


def wheel_motion(v):
    w=np.asarray(c.decode_action(v)['wheels'])
    return [(w[0]+w[1]+w[2]+w[3])/4,(-w[0]+w[1]+w[2]-w[3])/4,(-w[0]+w[1]-w[2]+w[3])/4]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--stages',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--beamact3-v1',choices=('off','A','B'),default='off')
    a=p.parse_args()
    if a.beamact3_v1=='off':raise ValueError('explicit candidate arm required')
    host=require_gcp2(training=True);source=source_sha()
    import torch
    from harness.beamact3 import Beam3Actor,transform_batch
    torch.set_num_threads(4)
    actor=Beam3Actor.load(a.model,device='cuda')
    if actor.arm!=a.beamact3_v1:raise ValueError('offline arm mismatch')
    a.output.mkdir(parents=True,exist_ok=False)
    stage_rows=read_json(a.stages)
    stages={r['sample_id']:r for r in stage_rows}
    report=dict(status='running',source_sha=source,host=host,arm=actor.arm,
        model_sha256=sha256(a.model/'model.safetensors'),dataset_manifest_sha256=sha256(a.dataset/'manifest.json'),
        physical_runs=0,metrics={},role_interventions=[],checkpoint_selection='fixed final20000; never validation/heldout selection')
    for split in ('train','validation'):
        data=GraspDataset(a.dataset,split)
        if actor.stats!=data.stats:raise ValueError('normalization mismatch')
        preds=[];bases=[];targets=[];phases=[];grids=[];offset=0
        for ep,shard in zip((e for e in data.manifest['episodes'] if e['split']==split),data.shards):
            metadata=read_json(a.dataset/ep['path']/'samples.json')
            phase=[stages[r['sample_id']]['phase'] for r in metadata]
            predicted=[]
            for start in range(0,len(metadata),8):
                ids=list(range(start,min(start+8,len(metadata))))
                batch=torch.utils.data.default_collate([data[offset+i] for i in ids])
                inputs=transform_batch({k:batch[k].to('cuda') for k in INPUT_KEYS},actor.arm)
                with torch.inference_mode():values=actor.policy.predict_action_chunk(inputs).cpu().numpy()
                predicted.extend(actor.decode_predictions(values)[:,0])
            predicted=np.asarray(predicted)
            np.savez_compressed(a.output/(ep['path']+'.npz'),prediction=predicted.astype(np.float32))
            preds.extend(predicted);bases.extend(persistence(shard['state']));targets.extend(shard['action'][:,0])
            phases.extend(phase);grids.extend(refresh_grid(metadata))
            if split=='validation':
                probes=[('initial',0)]
                if 'approach' in phase:probes.append(('first_approach',phase.index('approach')))
                for name,index in probes:
                    sample=data[offset+index]
                    inputs={k:torch.from_numpy(sample[k].copy()).unsqueeze(0).to('cuda') for k in INPUT_KEYS}
                    state=inputs['observation.state'].clone();begin=c.HISTORY*14+len(c.SKILLS)+len(c.KINDS)
                    before=state[:,begin:begin+len(c.ROLES)].clone()
                    if before[0,:2].sum()!=1:raise ValueError('beam role must be teal/blue')
                    state[:,begin:begin+2]=state[:,begin:begin+2].flip(-1)
                    swapped=transform_batch({**inputs,'observation.state':state},actor.arm)
                    with torch.inference_mode():out=actor.policy.predict_action_chunk(swapped).cpu().numpy()
                    other=actor.decode_predictions(out)[0,0]
                    orig=predicted[index];u=np.array(wheel_motion(orig));v=np.array(wheel_motion(other))
                    report['role_interventions'].append(dict(seed=ep['seed'],robot=ep['robot_id'],probe=name,
                        t=metadata[index]['t'],phase=phase[index],original_role=metadata[index]['role'],
                        swapped_role='blue' if metadata[index]['role']=='teal' else 'teal',
                        original_motion=u.tolist(),swapped_motion=v.tolist(),
                        wheel_class_changed=not np.array_equal(decoded(orig[None])[0,:4],decoded(other[None])[0,:4]),
                        translation_dot=float(u[:2]@v[:2]),translation_reversed=bool(u[:2]@v[:2]<0),
                        original_stationary=bool(not np.any(u)),swapped_stationary=bool(not np.any(v)),
                        decoded_action_mae=float(np.abs(decoded(orig[None])-decoded(other[None])).mean()),
                        scope='only fixed role token swapped; same RGB/history/clocks; offline sensitivity, not causal closed-loop success'))
            offset+=len(metadata)
            write_json(a.output/'progress.json',dict(split=split,rows=offset,episode=ep['path']))
        report['metrics'][split]=stratified(np.asarray(preds),np.asarray(bases),np.asarray(targets),phases,np.asarray(grids))
        write_json(a.output/'summary.json',report)
    report['role_summary']={name:dict(N=len(rows),wheel_class_changed=sum(x['wheel_class_changed'] for x in rows),
        translation_reversed=sum(x['translation_reversed'] for x in rows),
        original_stationary=sum(x['original_stationary'] for x in rows),swapped_stationary=sum(x['swapped_stationary'] for x in rows))
        for name in ('initial','first_approach') if (rows:=[x for x in report['role_interventions'] if x['probe']==name])}
    report['status']='complete'
    report['artifacts']={f.name:sha256(f) for f in a.output.glob('*.npz')}
    write_json(a.output/'summary.json',report)


if __name__=='__main__':main()
