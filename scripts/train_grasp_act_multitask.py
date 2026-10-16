"""Train one multitask upstream ACT; bounded, resumable and no truth inputs."""
from __future__ import annotations
import argparse,hashlib,importlib.metadata,json,os,platform,random,subprocess,time
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset,DataLoader,WeightedRandomSampler
from harness.grasp_act import make_policy,GraspAct,IMAGE_KEYS,CONTEXT_KEY,tensor,metadata,verify_upstream,PROFILES
from harness.grasp_act_augment import draw as draw_augment,augmented_tensor,RANGES as AUGMENT_RANGES
from harness.grasp_act_seed_splits import check_dataset_splits
from harness.grasp_act_contract import context
from harness.grasp_act_data import validate_splits,sha
from harness.reference_act import UPSTREAM_SHA


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


class Examples(Dataset):
    def __init__(self,entries,profile,*,augment=False,seed=0):
        self.rows=[];self.profile=profile;self.augment=augment;self.seed=seed;self.calls=0
        for root,meta,seq in entries:
            for obs,labels,windows in seq.values():
                self.rows.extend((Path(root),o,w) for o,w in zip(obs,windows))
        self.groups=[(o['object_kind'],o['skill'],o['role'],bool(w['action'][0][-1])) for _,o,w in self.rows]
    def __len__(self):return len(self.rows)
    def __getitem__(self,i):
        root,obs,win=self.rows[i]
        if self.augment:
            # One draw per sample, identical for all history frames (one camera).
            self.calls+=1;params=draw_augment(np.random.default_rng((self.seed,i,self.calls)))
            images={k:augmented_tensor((root/ref['path']).read_bytes(),PROFILES[self.profile],params) for k,ref in zip(IMAGE_KEYS,obs['rgb'])}
        else:
            images={k:tensor((root/ref['path']).read_bytes(),self.profile) for k,ref in zip(IMAGE_KEYS,obs['rgb'])}
        return {**images,
                CONTEXT_KEY:torch.tensor(context(obs),dtype=torch.float32),
                'action':torch.tensor(win['action'],dtype=torch.float32),
                'action_is_pad':torch.tensor(win['action_is_pad'],dtype=torch.bool)}


@torch.no_grad()
def evaluate(policy,loader,device):
    policy.eval();positive=negative=missed=false=0;err=0.;n=0
    for b in loader:
        target=b['action'][:,0];pred=policy.predict_action_chunk({k:v.to(device) for k,v in b.items() if k not in ('action','action_is_pad')}).cpu()[:,0]
        done=target[:,-1]>.5;ready=pred[:,-1]>=.65
        positive+=int(done.sum());negative+=int((~done).sum());missed+=int((done&~ready).sum());false+=int((~done&ready).sum())
        err+=float((pred[:,:-1]-target[:,:-1]).abs().sum());n+=len(target)
    mae=err/max(1,n*9)
    return {'samples':n,'done_N':positive,'missed_done_n':missed,'not_done_N':negative,'false_done_n':false,
        'action_mae':mae,'selection_score':missed/max(1,positive)+4*false/max(1,negative)+mae,
        'scope':'zero-latent first-action offline fitness, not closed-loop success'}


def deployed_done_loss(policy,batch):
    """Use zero latent as at deployment, retain gradients (predict API is no_grad)."""
    was_training=policy.training;policy.eval()
    try:
        b={k:v for k,v in batch.items() if k not in ('action','action_is_pad')}
        b['observation.images']=[b[k] for k in IMAGE_KEYS]
        pred=policy.model(b)[0][:,0,-1]
        target=batch['action'][:,0,-1]
        return ((pred-target).abs()*torch.where(target>.5,2.,1.)).mean()
    finally:policy.train(was_training)


def train(dataset,out,*,steps=10000,seed=20261014,profile='standard',device='cuda',batch_size=8,
          max_wall_s=8.5*3600,resume=None,pretrained=True,augment=True,allow_no_heldout=False):
    verify_upstream()  # exact ACT/config bytes also verifies offline wheels without VCS direct_url
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA required by selected training job')
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.set_num_threads(2)
    data=json.loads(Path(dataset).read_text());base=Path(dataset).parent
    # Final holdouts are not opened during model selection.
    entries={k:[base/x for x in data[k]] for k in ('train','development')}
    # Registered seed ranges + held-out map check over ALL declared splits,
    # metadata only (holdout samples are not opened).
    if allow_no_heldout:split_check={'skipped':'explicit --allow-no-heldout (pipeline smoke only; not a reportable model)'}
    else:split_check=check_dataset_splits(data,base)
    checked=validate_splits(entries)
    trainset=Examples(checked['train'],profile,augment=augment,seed=seed);devset=Examples(checked['development'],profile)
    if not len(trainset) or not len(devset):raise ValueError('nonempty episode splits required')
    from collections import Counter
    counts=Counter(trainset.groups);weights=torch.tensor([1/counts[g] for g in trainset.groups],dtype=torch.double)
    generator=torch.Generator().manual_seed(seed)
    policy=make_policy(profile,pretrained=pretrained and resume is None).to(device)
    backbone=list(policy.model.backbone.parameters());backbone_ids={id(p) for p in backbone}
    optimizer=torch.optim.AdamW([{'params':backbone,'lr':1e-5},
        {'params':[p for p in policy.parameters() if id(p) not in backbone_ids],'lr':1e-4}],weight_decay=1e-4)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    dataset_sha=sha(dataset);step0=0;best=float('inf');best_state=None
    if resume:
        ck=torch.load(resume,map_location='cpu',weights_only=True)
        if ck['dataset_sha256']!=dataset_sha or ck['adapter']!=metadata(profile):raise ValueError('resume provenance mismatch')
        policy.load_state_dict(ck['model']);optimizer.load_state_dict(ck['optimizer']);step0=ck['step'];best=ck['best'];best_state=ck['best_model']
        torch.set_rng_state(ck['torch_rng']);generator.set_state(ck['sampler_rng'])
        if device=='cuda' and ck['cuda_rng']:torch.cuda.set_rng_state_all(ck['cuda_rng'])
    sampler=WeightedRandomSampler(weights,(steps-step0)*batch_size,replacement=True,generator=generator)
    loader=DataLoader(trainset,batch_size=batch_size,sampler=sampler,num_workers=0)
    devloader=DataLoader(devset,batch_size=batch_size,shuffle=False,num_workers=0)
    report={'complete':False,'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'dataset_sha256':dataset_sha,'dataset_path':str(Path(dataset).resolve()),'upstream_sha':UPSTREAM_SHA,
        'adapter':metadata(profile),'seed':seed,'target_steps':steps,'resumed_from':str(resume) if resume else None,
        'train_episodes':data['train'],'development_episodes':data['development'],'train_samples':len(trainset),'dev_samples':len(devset),
        'selection':'dev missed done + 4*false done + action MAE; no final holdout',
        'augmentation':{'enabled':augment,'ranges':AUGMENT_RANGES,'scope':'train split only; development/inference unaugmented; camera geometry unchanged'},
        'split_check':split_check,
        'environment':{'platform':platform.platform(),'device':device,**{k:importlib.metadata.version(k) for k in ('torch','torchvision','lerobot')}},'progress':[]}
    started=time.monotonic();write(out/'report.json',report)
    step=step0
    for step,b in enumerate(loader,step0+1):
        b={k:v.to(device) for k,v in b.items()};policy.train();optimizer.zero_grad()
        loss,details=policy(b);done_loss=deployed_done_loss(policy,b);total=loss+2*done_loss
        if not torch.isfinite(total):raise RuntimeError('nonfinite training loss')
        total.backward();torch.nn.utils.clip_grad_norm_(policy.parameters(),1.);optimizer.step()
        stopping=time.monotonic()-started>=max_wall_s
        if step==step0+1 or step%250==0 or step==steps or stopping:
            metrics=evaluate(policy,devloader,device);event={'step':step,'loss':float(total.detach()),'done_loss':float(done_loss.detach()),'development':metrics,'elapsed_s':time.monotonic()-started}
            if metrics['selection_score']<best:
                best=metrics['selection_score'];best_state={k:v.detach().cpu().clone() for k,v in policy.state_dict().items()};report['selected_step']=step
            report['progress'].append(event);write(out/'report.json',report);print(json.dumps(event),flush=True)
            ck={'model':policy.state_dict(),'optimizer':optimizer.state_dict(),'step':step,'best':best,'best_model':best_state,
                'dataset_sha256':dataset_sha,'adapter':metadata(profile),'torch_rng':torch.get_rng_state(),'sampler_rng':generator.get_state(),
                'cuda_rng':torch.cuda.get_rng_state_all() if device=='cuda' else []}
            tmp=out/'resume.tmp';torch.save(ck,tmp);tmp.replace(out/'resume.pt')
            if stopping:break
    if best_state is None:raise ValueError('no trained checkpoint')
    policy.load_state_dict(best_state);actor=GraspAct(policy,profile);actor.save(out/'act')
    loaded=GraspAct.load(out/'act',device=device)
    probes=[]
    for root,obs,_ in [trainset.rows[0],trainset.rows[-1],devset.rows[0],devset.rows[-1]]:
        jpegs=[(root/x['path']).read_bytes() for x in obs['rgb']]
        expected=actor.predict_chunk(obs,jpegs);actual=loaded.predict_chunk(obs,jpegs)
        # Discrete commands must agree; tiny done-score floating differences are separately bounded.
        for x,y in zip(expected,actual):
            if any(x[k]!=y[k] for k in ('drive','duration_s','pwm','done')) or abs(x['done_score']-y['done_score'])>1e-5:
                raise ValueError('deployed checkpoint readback mismatch')
        probes.append(obs['sample_id'])
    report.update(complete=step==steps,steps_finished=step,readback_samples=probes,model_sha256=sha(out/'act/model.safetensors'),
        wall_s=time.monotonic()-started,independent_student_success='not evaluated')
    write(out/'report.json',report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--steps',type=int,default=10000);p.add_argument('--seed',type=int,default=20261014);p.add_argument('--batch-size',type=int,default=8)
    p.add_argument('--profile',choices=('smoke','standard'),default='standard');p.add_argument('--device',choices=('cpu','mps','cuda'),default='cuda')
    p.add_argument('--max-wall-s',type=float,default=30600);p.add_argument('--resume',type=Path);p.add_argument('--no-pretrained',action='store_true')
    p.add_argument('--augment',choices=('on','off'),default='on',help='training image augmentation (default on for new data)')
    p.add_argument('--allow-no-heldout',action='store_true',help='pipeline smoke only; skips registered split/held-out map check');a=p.parse_args()
    if not 1<=a.steps<=100000 or not 0<a.max_wall_s<=30600:raise ValueError('finite training budget required')
    train(a.dataset,a.out,steps=a.steps,seed=a.seed,profile=a.profile,device=a.device,batch_size=a.batch_size,max_wall_s=a.max_wall_s,resume=a.resume,pretrained=not a.no_pretrained,
          augment=a.augment=='on',allow_no_heldout=a.allow_no_heldout)
if __name__=='__main__':main()
