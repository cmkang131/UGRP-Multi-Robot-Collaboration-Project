"""Check CVAE posterior/prior gap without any parameter or buffer update.

Eight first TRAIN rows per oracle phase are a fixed inference computation
budget. Posterior uses target actions only as an evaluation diagnostic; it is
never an allowed student input or a new controller.
"""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import argparse
import json
import numpy as np
import torch
from harness.grasp_act_data import GraspDataset,read_json,write_json,sha256
from harness.beamact_input import BeamActor,transform_batch
from analyze_actdiag import arrays,existing,metrics,decoded


def main():
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=True);torch.set_num_threads(4);torch.manual_seed(20261015)
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    b=Path('/home/ugrp/ugrp-sim/ops-reviews');root=b/'actdiag/infer-final-v1/dataset-view'
    stages={r['sample_id']:r['phase'] for r in read_json(existing(b/'beamact2/data-v1/stages.json'))}
    stats=read_json(root/'normalization.json');counts=Counter();items=[];phases=[];targets=[]
    for ep,s,m in arrays(root,'train'):
        chosen=[i for i,r in enumerate(m) if counts[stages[r['sample_id']]]<8]
        if not chosen:continue
        s['images']=np.load(root/ep['path']/'images.npy',mmap_mode='r')
        for i,r in enumerate(m):
            ph=stages[r['sample_id']]
            if counts[ph]>=8:continue
            thin=SimpleNamespace(shards=[s],index=[(0,i)],stats=stats,blank=False)
            items.append(GraspDataset.__getitem__(thin,0));counts[ph]+=1;phases.append(ph);targets.append(s['action'][i,0])
    actor=BeamActor.load(b/'beamact2/train/main/step-010000/actor',device='cuda')
    before={k:v.detach().cpu().clone() for k,v in actor.policy.state_dict().items()};capture=[]
    handle=actor.policy.model.register_forward_hook(lambda module,args,out:capture.append(out[0].detach().cpu().numpy()))
    results={}
    for mode in ('prior_z0','posterior_target_conditioned'):
        predictions=[];kl=[]
        for start in range(0,len(items),8):
            batch=torch.utils.data.default_collate(items[start:start+8]);batch={k:v.to('cuda') for k,v in batch.items()}
            batch=transform_batch(batch,actor.mode);actor.policy.eval()
            # Only the ACT container's branch flag changes. All dropout and BN
            # submodules remain eval. There is no backward/optimizer call.
            actor.policy.model.training=(mode=='posterior_target_conditioned');capture.clear()
            with torch.inference_mode():loss,terms=actor.policy(batch)
            predictions.extend(actor.decode_predictions(capture[-1])[:,0]);kl.append(terms.get('kld_loss'))
        pred=np.asarray(predictions);y=np.asarray(targets);ph=np.asarray(phases)
        results[mode]=dict(raw=metrics(pred,y),decoded=metrics(decoded(pred),y),
            per_phase={p:metrics(decoded(pred[ph==p]),y[ph==p]) for p in sorted(set(ph))},kld=kl)
    handle.remove();actor.policy.eval()
    equal=all(torch.equal(v.detach().cpu(),before[k]) for k,v in actor.policy.state_dict().items());assert equal
    a.output.mkdir(exist_ok=False,parents=True)
    write_json(a.output/'latent.json',dict(scope=__doc__,phase_counts=dict(counts),results=results,
        parameter_and_buffer_unchanged=equal,optimizer_steps=0,torch_seed=20261015))
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
