"""GCP2 artifact-only ACT diagnosis. Never fits a model or runs a simulator.

All sample limits are computation budgets, not acceptance thresholds. The final
checkpoint is evaluated on every unique TRAIN and validation row. Phase labels
are evaluation-only oracle strata; the visual NN never receives command state.
"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json
import os
import subprocess
import time

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json, read_rows, sha256, write_json


def existing(p):
    return p if p.exists() else p.with_name(p.name + '.zst')


def dataset_view(root, output):
    """Read compressed artifacts through a new metadata-only view, preserving raw."""
    if (root/'manifest.json').exists():
        return root
    view=output/'dataset-view';view.mkdir(exist_ok=True)
    manifest=read_json(existing(root/'manifest.json'))
    paths=['manifest.json','normalization.json']
    paths.extend(str(Path(e['path'])/n) for e in manifest['episodes'] for n in e['files'])
    for rel in paths:
        dest=view/rel
        if dest.is_symlink():dest.unlink()  # only this script's disposable view
        if dest.exists():continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        src=root/rel
        if src.exists():os.link(src,dest)  # safe_path rejects external symlinks
        else:dest.write_bytes(subprocess.check_output(['zstd','-qdc',str(existing(src))]))
    return view


def arrays(root, split=None):
    manifest = read_json(root / 'manifest.json')
    for e in manifest['episodes']:
        if split and e['split'] != split:
            continue
        folder = root / e['path']
        with np.load(folder / 'tensors.npz', allow_pickle=False) as f:
            a = {k: f[k] for k in f.files}
        yield e, a, read_json(folder / 'samples.json')


def metrics(p, y):
    d = np.abs(np.asarray(p) - y)
    return dict(N=len(y), wheel_mae=float(d[..., :4].mean()),
                pulse_mae_ms=float(d[..., 4:8].mean()*150),
                pwm_mae=float(d[..., 8:13].mean()*1000))


def quantiles(x):
    return dict(zip(('min','p10','p25','p50','p75','p90','p99','max'),
                    np.quantile(x, [0,.1,.25,.5,.75,.9,.99,1]).tolist())) if len(x) else {}


def nearest(train,query):
    """Exact L2 retrieval, 128-query memory budget; no learned parameters."""
    t2=np.square(train).sum(1);result=[]
    for start in range(0,len(query),128):
        q=query[start:start+128]
        distance=np.square(q).sum(1,keepdims=True)+t2[None,:]-2*q@train.T
        result.extend(distance.argmin(1))
    return np.asarray(result,dtype=np.int64)


def decoded(x):
    # Exact contract projection, including completion-induced stop.
    return np.asarray([c.encode_action(dict(t=0., **{k:r[k] for k in
        ('wheels','duration_s','pwm')}), done=r['done'])
        for r in map(c.decode_action, np.asarray(x,dtype=float).reshape(-1,14))]).reshape(np.shape(x))


def pulse_distribution(y, episodes):
    w = y[:,:4]
    runs = []
    for start, end in episodes:
        for j in range(4):
            signs=np.sign(w[start:end,j]); edges=np.r_[0,np.flatnonzero(signs[1:]!=signs[:-1])+1,len(signs)]
            runs.extend(int(b-a) for a,b in zip(edges[:-1],edges[1:]) if signs[a])
    vals,counts=np.unique(w,return_counts=True)
    dt=y[:,4:8]*150
    return dict(rows=len(y), wheel_zero_fraction=float((w==0).mean()),
        all_wheels_zero_fraction=float((w==0).all(1).mean()),
        wheel_unique_values=[dict(value=float(v),N=int(n)) for v,n in zip(vals,counts)],
        pulse_unique_values_rounded_us=int(len(np.unique(np.round(dt*1000)))),
        pulse_ms_nonzero=quantiles(dt[w!=0]),
        nonzero_same_sign_run_ticks=quantiles(runs),
        nonzero_run_one_tick_fraction=float(np.mean(np.asarray(runs)==1)),
        nonzero_runs_N=len(runs), run_definition='same-sign wheel run, reset at shard boundary; ticks*0.1s; separate from within-tick pulse width')


def audit(a):
    from harness.grasp_act_data import fit_stats, image_array, history_image
    from harness.grasp_act_policy import observation_batch
    from harness.beamact_input import transform_batch, MASK_COLUMNS
    from scripts.evaluate_beamact1 import persistence
    stages={r['sample_id']:r['phase'] for r in read_json(existing(a.stages))}
    stats=read_json(a.dataset/'normalization.json')
    allrows=defaultdict(list); bounds=defaultdict(list); offsets=Counter(); errors=Counter()
    xs=[];ys=[];seeds=[];raw_checks=[];dataset_checks=[]
    own_refs=0; align_N=0; chunk_N=0; chunk_bad=0; prev_bad=0; image_equal=0
    for ep,s,meta in arrays(a.dataset):
        split=ep['split']; target=s['action'][:,0]; base=persistence(s['state'])
        pos=sum(len(x) for x in allrows[split]);bounds[split].append((pos,pos+len(meta)))
        allrows[split].append(target)
        phase=[stages[m['sample_id']] for m in meta]
        dataset_checks.append(dict(path=ep['path'],split=split,N=len(meta),
            phases=dict(Counter(phase)),roles=dict(Counter(m['role'] for m in meta)),
            persistence=metrics(base,target)))
        if split=='train':
            xs.extend(s['state']);ys.extend(target);seeds.extend([ep['seed']]*len(meta))
        ts=np.array([m['t'] for m in meta]);
        for h in range(8):
            for i in np.flatnonzero(~s['action_is_pad'][:,h]):
                j=i+h;chunk_N+=1
                if j>=len(meta) or abs(ts[j]-ts[i]-h*.1)>1e-5 or not np.array_equal(s['action'][i,h],target[j]):chunk_bad+=1
        raw=Path(ep['source_root'])/'raw'
        obs=read_rows(existing(raw/f"student-{ep['robot_id']}.jsonl"))
        labels=read_rows(existing(raw/f"teacher-{ep['robot_id']}.jsonl"))
        obs={r['sample_id']:r for r in obs};labels={r['sample_id']:r for r in labels}
        # Check all stored sample/action/context identities against original raw.
        for i,m in enumerate(meta):
            o,l=obs[m['sample_id']],labels[m['sample_id']];align_N+=1
            errors['context']+=not np.array_equal(np.asarray(c.context(o),np.float32),s['state'][i])
            errors['h0']+=not np.array_equal(np.asarray(c.encode_action(l['clean_teacher_command'],done=l['done']),np.float32),target[i])
            errors['label_time']+=abs(l['clean_teacher_command']['t']-o['t'])>1e-6
            own_refs+=len(o['rgb']);errors['cross_robot_rgb']+=sum(r['robot_id']!=o['robot_id'] for r in o['rgb'])
            errors['future_rgb']+=sum(r['t']>o['t']+1e-7 for r in o['rgb'])
            offsets[round(o['t']-o['issued'][-1]['t'],6)]+=1
        # Pixel and normalized tensor equality at start/middle/end of each shard.
        images=np.load(a.dataset/ep['path']/'images.npy',mmap_mode='r')
        for i in sorted({0,len(meta)//2,len(meta)-1}):
            o=obs[meta[i]['sample_id']]
            jpg=[(raw/r['path']).read_bytes() for r in o['rgb']]
            online=transform_batch(observation_batch(o,jpg,stats),'wheel_pulse_train_mean')
            offline={'observation.state':(s['state'][i]-np.asarray(stats['state_mean'],np.float32))/np.asarray(stats['state_std'],np.float32),
                'observation.images.own_history':history_image([images[k] for k in s['image_index'][i]])}
            offline=transform_batch(offline,'wheel_pulse_train_mean')
            equal=all(np.array_equal(online[k],offline[k]) for k in online)
            image_equal+=equal;errors['train_online_tensor']+=not equal
        print('audit',ep['path'],flush=True)
    fitted=fit_stats(xs,ys,seeds)
    stats_error={k:float(np.max(np.abs(np.asarray(stats[k])-np.asarray(fitted[k])))) for k in ('state_mean','state_std','action_mean','action_std')}
    roundtrip=max(float(np.max(np.abs(((np.asarray(y)-stats['action_mean'])/stats['action_std'])*stats['action_std']+stats['action_mean']-y))) for y in allrows['train'])
    report=dict(status='complete',scope='all beam TRAIN/validation source sample and horizon audit; no optimization',
        manifest_sha256=sha256(a.dataset/'manifest.json'),rows=align_N,own_rgb_references=own_refs,
        errors=dict(errors),valid_chunk_targets=chunk_N,chunk_alignment_errors=chunk_bad,
        last_issued_age_s_hist=dict(offsets),normalization_max_error=stats_error,
        normalization_roundtrip_max_abs=roundtrip,online_offline_equal_probes=image_equal,
        mask_columns=len(MASK_COLUMNS),mask_applied='same transform_batch to normalized train and deployment state',
        distribution={k:pulse_distribution(np.concatenate(v),bounds[k]) for k,v in allrows.items()},episodes=dataset_checks)
    write_json(a.output/'data-audit.json',report)


def infer(a):
    import torch
    from harness.grasp_act_data import GraspDataset,INPUT_KEYS
    from harness.beamact_input import BeamActor,transform_batch
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=True);torch.set_num_threads(4)
    actor=BeamActor.load(a.model,device='cuda');saved_features=[]
    def hook(module,args,out):
        z=list(out.values())[-1] if isinstance(out,dict) else out
        if hasattr(z,'tensors'):z=z.tensors
        # Current frame is the lower-right montage quadrant. A pooled 512-D
        # descriptor uses RGB only, with existing trained backbone weights.
        saved_features.append(z[:,:,z.shape[-2]//2:,z.shape[-1]//2:].mean((-2,-1)).detach().cpu().numpy())
    handle=actor.policy.model.backbone.register_forward_hook(hook)
    begin=time.monotonic();completed=0;results=[]
    for split in ('validation','train'):
        data=GraspDataset(a.dataset,split)
        assert actor.stats==data.stats
        offset=0
        for ep,s,meta in arrays(a.dataset,split):
            dest=a.output/(ep['path']+'.npz')
            if dest.exists():
                offset+=len(meta);continue
            pred=[];features=[]
            for start in range(0,len(meta),a.batch):
                ids=list(range(start,min(start+a.batch,len(meta))))
                batch=torch.utils.data.default_collate([data[offset+i] for i in ids])
                inputs=transform_batch({k:batch[k].to('cuda') for k in INPUT_KEYS},actor.mode)
                saved_features.clear()
                with torch.inference_mode():
                    p=actor.policy.predict_action_chunk(inputs).cpu().numpy()
                pred.append(actor.decode_predictions(p));features.append(saved_features[-1]);completed+=len(ids)
            np.savez_compressed(dest,prediction=np.concatenate(pred).astype(np.float32),feature=np.concatenate(features).astype(np.float32))
            offset+=len(meta)
            row=dict(path=ep['path'],split=split,N=len(meta),rows_completed=completed,wall_s=time.monotonic()-begin)
            results.append(row);write_json(a.output/'progress.json',row);print(json.dumps(row),flush=True)
    handle.remove()
    write_json(a.output/'inference.json',dict(status='complete',model_sha256=sha256(a.model/'model.safetensors'),
        dataset_manifest_sha256=sha256(a.dataset/'manifest.json'),wall_s=time.monotonic()-begin,
        optimizer_steps=0,physical_runs=0,rows=completed,batch=a.batch,episodes=results,
        gpu_peak_bytes=torch.cuda.max_memory_allocated()))


def report(a):
    from scripts.evaluate_beamact1 import persistence,refresh_grid
    stages={r['sample_id']:r['phase'] for r in read_json(existing(a.stages))}
    splits={}
    for split in ('train','validation'):
        rows=defaultdict(list);off=0
        for ep,s,m in arrays(a.dataset,split):
            p=np.load(a.predictions/(ep['path']+'.npz'))
            rows['prediction'].append(p['prediction']);rows['feature'].append(p['feature'])
            rows['target'].append(s['action'][:,0]);rows['base'].append(persistence(s['state']))
            rows['phase'].extend(stages[x['sample_id']] for x in m);rows['role'].extend(x['role'] for x in m)
            rows['refresh'].extend(refresh_grid(m));rows['seed'].extend([ep['seed']]*len(m));rows['robot'].extend([ep['robot_id']]*len(m))
        splits[split]={k:np.concatenate(v) if k in ('prediction','feature','target','base') else np.asarray(v) for k,v in rows.items()}
    result={};train=splits['train'];val=splits['validation'];basis={}
    for name,d in splits.items():
        pred=d['prediction'][:,0];y=d['target'];base=d['base'];pr=decoded(pred)
        # Diagnostic only: nearest TRAIN-supported wheel class. Boundaries are
        # exact midpoints between the three observed target values, no tuning.
        classes=np.unique(train['target'][:,:4]);q=pred.copy()
        q[:,:4]=classes[np.abs(q[:,:4,None]-classes).argmin(-1)]
        quantized=decoded(q)
        no_done=pred.copy();no_done[:,-1]=0.;no_done=decoded(no_done)
        out={}
        masks={'all':np.ones(len(y),bool),'refresh':d['refresh'].astype(bool)}
        masks.update({'phase_'+p:d['phase']==p for p in sorted(set(d['phase']))})
        masks.update({'robot_'+p:d['robot']==p for p in sorted(set(d['robot']))})
        masks.update({'role_'+p:d['role']==p for p in sorted(set(d['role']))})
        masks['target_moving']=(y[:,:4]!=0).any(1)
        masks['target_changed']=(np.abs(y[:,:4]-base[:,:4])>0).any(1)
        masks['target_unchanged']=~masks['target_changed']
        for key,mask in masks.items():
            if mask.any():out[key]=dict(ACT_decoded=metrics(pr[mask],y[mask]),ACT_raw=metrics(pred[mask],y[mask]),persistence=metrics(base[mask],y[mask]))
        w=pred[:,:4];t=y[:,:4]
        out['projection']=dict(predicted_deadband_fraction=float((np.abs(w)<.155).mean()),
            moving_target_to_zero_fraction=float(((pr[:,:4]==0)&(t!=0)).sum()/max(1,(t!=0).sum())),
            raw_abs_wheel=quantiles(np.abs(w).ravel()),done_over_065=float((pred[:,-1]>=.65).mean()))
        out['projection'].update(nearest_train_wheel_class=metrics(quantized,y),
            ignore_done_for_motion_only=metrics(no_done,y),
            scope='post-hoc output diagnostics only; not deployed or tuned on reserved student20')
        result[name]=out
    # TRAIN-only summaries; oracle phase is never an executable policy input.
    for mode in ('mean','median'):
        p=np.empty_like(val['target'])
        for phase in sorted(set(val['phase'])):
            mask=train['phase']==phase
            value=getattr(np,mode)(train['target'][mask],axis=0)
            p[val['phase']==phase]=value
        basis['phase_'+mode+'_oracle']=dict(all=metrics(p,val['target']),refresh=metrics(p[val['refresh']],val['target'][val['refresh']]))
    # Frozen RGB-only nearest neighbor, no parameter fitting or state input.
    for grouping in ('role','phase_role'):
        p=np.empty_like(val['target']);neighbors=np.empty(len(p),np.int64)
        keys=val['role'] if grouping=='role' else np.char.add(np.char.add(val['phase'],'/'),val['role'])
        tkeys=train['role'] if grouping=='role' else np.char.add(np.char.add(train['phase'],'/'),train['role'])
        for key in sorted(set(keys)):
            ti=np.flatnonzero(tkeys==key);vi=np.flatnonzero(keys==key)
            # L2-normalization makes Euclidean NN equivalent to cosine NN.
            tf=train['feature'][ti];vf=val['feature'][vi]
            tf=tf/np.maximum(np.linalg.norm(tf,axis=1,keepdims=True),np.finfo(np.float32).tiny)
            vf=vf/np.maximum(np.linalg.norm(vf,axis=1,keepdims=True),np.finfo(np.float32).tiny)
            ix=nearest(tf,vf);p[vi]=train['target'][ti[ix]];neighbors[vi]=ti[ix]
        basis['visual_1nn_'+grouping]=dict(all=metrics(p,val['target']),refresh=metrics(p[val['refresh']],val['target'][val['refresh']]),
            oracle_phase=grouping=='phase_role',per_phase={ph:metrics(p[val['phase']==ph],val['target'][val['phase']==ph]) for ph in sorted(set(val['phase']))},
            train_validation_seed_overlap=len(set(train['seed'])&set(val['seed'])))
    # Aligned query h0 versus neighboring teacher timesteps: same shard only.
    lag_errors=defaultdict(list);deployment=defaultdict(list);dtargets=[]
    horizon_errors=defaultdict(list);horizon_base=defaultdict(list)
    effective=defaultdict(list)
    for ep,s,m in arrays(a.dataset,'validation'):
        chunks=np.load(a.predictions/(ep['path']+'.npz'))['prediction']
        p=decoded(chunks[:,0]);base=persistence(s['state']);y=s['action'][:,0]
        for h in range(c.CHUNK):
            valid=~s['action_is_pad'][:,h]
            horizon_errors[h].append(np.abs(decoded(chunks[:,h])[valid]-s['action'][valid,h]))
            horizon_base[h].append(np.abs(base[valid]-s['action'][valid,h]))
        grid=refresh_grid(m);start=0;fixed=[];ensemble=[]
        for i in range(len(m)):
            if i==0 or abs(m[i]['t']-m[i-1]['t']-.1)>1e-5:start=i
            origin=i-(i-start)%c.CHUNK
            fixed.append(chunks[origin,i-origin])
            origins=list(range(max(start,i-c.CHUNK+1),i+1))
            weights=np.exp(-.01*np.arange(len(origins))) # original ACT coefficient
            ensemble.append(np.average([chunks[j,i-j] for j in origins],axis=0,weights=weights))
        fixed=decoded(fixed);ensemble=decoded(ensemble)
        for key,value in [('chunk8',fixed),('h0_every_tick',p),('ensemble001',ensemble)]:
            deployment[key].append(value)
            impulse=value[:,:4]*value[:,4:8]*1.5
            truth=y[:,:4]*y[:,4:8]*1.5
            effective[key].append(np.abs(impulse-truth))
        effective['persistence'].append(np.abs(base[:,:4]*base[:,4:8]*1.5-y[:,:4]*y[:,4:8]*1.5))
        dtargets.append(y)
        for lag in range(-8,9):
            ii=np.arange(max(0,-lag),min(len(m),len(m)-lag));jj=ii+lag
            valid=np.array([abs(m[j]['t']-m[i]['t']-lag*.1)<1e-5 for i,j in zip(ii,jj)])
            lag_errors[lag].append(np.abs(p[ii[valid],:4]-s['action'][jj[valid],0,:4]))
    result['lag_sweep']={str(k):dict(N=sum(len(x) for x in v),wheel_mae=float(np.concatenate(v).mean())) for k,v in lag_errors.items()}
    result['teacher_path_deployment_proxy']={k:metrics(np.concatenate(v),np.concatenate(dtargets)) for k,v in deployment.items()}
    result['effective_duty_mae']={k:float(np.concatenate(v).mean()) for k,v in effective.items()}
    result['effective_duty_scope']='wheel * pulse_seconds / 0.1; commanded duty surrogate, never measured speed/displacement'
    result['horizon_mae']={str(h):{'ACT':metrics(np.concatenate(v),np.zeros_like(np.concatenate(v))),
        'persistence':metrics(np.concatenate(horizon_base[h]),np.zeros_like(np.concatenate(horizon_base[h])))} for h,v in horizon_errors.items()}
    result['baselines']=basis
    result['scope']='fixed final checkpoint; unique TRAIN/validation h0 rows; no model optimization; oracle-stage results not deployable'
    write_json(a.output/'metrics.json',result)
    print(json.dumps({k:result[k]['all'] for k in ('train','validation')},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('audit','infer','report'))
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--stages',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--model',type=Path)
    p.add_argument('--predictions',type=Path);p.add_argument('--batch',type=int,default=8)
    a=p.parse_args()
    import platform
    if platform.system()!='Linux':raise RuntimeError('analysis runs on GCP2 only')
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=a.mode=='infer')
    a.output.mkdir(parents=True,exist_ok=True)
    a.dataset=dataset_view(a.dataset,a.output)
    lease=Path('/home/ugrp/ugrp-sim/leases/actdiag.json')
    info=read_json(lease);info.update(pid=os.getpid(),mode=a.mode);write_json(lease,info)
    globals()[a.mode](a)


if __name__=='__main__':main()
