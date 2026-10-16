"""Existing ACT16a student-visit labels: diagnostic baselines, no optimizer.

Reference = original same20 visits, query = separate new20 visits. These are
not recovered ACT15 TRAIN data, so the split cannot estimate TRAIN MAE or be
pooled with beam demonstration-validation MAE. Phase is an oracle diagnostic.
"""
from pathlib import Path
from collections import defaultdict,Counter
import argparse
import json
import io
import numpy as np
from PIL import Image

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json,read_rows,write_json,sha256
from analyze_actdiag import existing,metrics,pulse_distribution,nearest


def main():
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=False)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    b=Path('/home/ugrp/ugrp-sim/act16a')
    jobs=read_json(b/'recovery1/batch-summary.json')['results']
    groups=defaultdict(lambda:defaultdict(list));files=[];allrows=[];bounds=[];visible=Counter()
    for job in jobs:
        raw=Path(job['raw']);obs=read_rows(existing(raw/'student-inputs.jsonl'))
        labels=read_rows(existing(raw/'shadow-labels.jsonl'))
        commands=read_rows(existing(raw/'commands.jsonl'))
        query={x['sample_id'] for x in read_rows(existing(raw/'chunk-predictions.jsonl'))}
        assert len(obs)==len(labels)==len(commands)
        yall=[]
        for o,l,u in zip(obs,labels,commands):
            if not l['label_valid'] or l['teacher_command'] is None:continue
            y=np.array(c.encode_action(l['teacher_command']));yall.append(y)
            visible['visible' if l['target_visible'] else 'not_visible']+=1
            if o['sample_id'] not in query:continue
            group=groups['reference_same20' if job['seed']<91500 else 'query_new20']
            group['y'].append(y);group['base'].append(c.encode_action(o['issued'][-1]))
            group['act'].append(c.encode_action(u['command']))
            group['phase'].append(l['teacher_phase']);group['kind'].append(o['object_kind'])
            group['visible'].append(l['target_visible']);group['seed'].append(job['seed'])
            jpg=(raw/o['rgb'][-1]['path']).read_bytes()
            assert sha256(raw/o['rgb'][-1]['path'])==o['rgb'][-1]['sha256']
            # Fixed 16x12 RGB descriptor is a small computation budget, not a
            # tuned visibility threshold or a new policy image preprocessing.
            image=np.asarray(Image.open(io.BytesIO(jpg)).convert('RGB').resize((16,12),Image.Resampling.BILINEAR),np.float32).ravel()/255
            group['feature'].append(image)
        start=sum(len(x) for x in allrows);bounds.append((start,start+len(yall)));allrows.append(np.asarray(yall))
        files.append(dict(seed=job['seed'],raw=str(raw),valid_rows=len(yall)))
    ds={k:{n:np.asarray(v) for n,v in rows.items()} for k,rows in groups.items()}
    train=ds['reference_same20'];val=ds['query_new20'];result={}
    for group,d in ds.items():
        result[group]=dict(rows=len(d['y']),seed_count=len(set(d['seed'])),ACT=metrics(d['act'],d['y']),persistence=metrics(d['base'],d['y']),
            visibility={str(key):dict(ACT=metrics(d['act'][d['visible']==key],d['y'][d['visible']==key]),persistence=metrics(d['base'][d['visible']==key],d['y'][d['visible']==key])) for key in (True,False) if (d['visible']==key).any()})
    baselines={}
    for mode in ('mean','median','visual_1nn'):
        pred=np.empty_like(val['y']);missing=0
        for phase in sorted(set(val['phase'])):
            vi=np.flatnonzero(val['phase']==phase);ti=np.flatnonzero(train['phase']==phase)
            if not len(ti):ti=np.arange(len(train['y']));missing+=len(vi)
            if mode=='visual_1nn':
                ix=nearest(train['feature'][ti],val['feature'][vi])
                pred[vi]=train['y'][ti[ix]]
            else:pred[vi]=getattr(np,mode)(train['y'][ti],axis=0)
        baselines[mode+'_phase_oracle']=dict(metrics=metrics(pred,val['y']),missing_phase_rows=missing,
            per_phase={ph:metrics(pred[val['phase']==ph],val['y'][val['phase']==ph]) for ph in sorted(set(val['phase']))})
    result.update(status='complete',scope=__doc__,baselines=baselines,files=files,
        all_valid_rows_visibility=dict(visible),distribution=pulse_distribution(np.concatenate(allrows),bounds),
        optimizer_steps=0,reference_query_seed_overlap=len(set(train['seed'])&set(val['seed'])))
    write_json(a.output/'solo.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','distribution','scope')},indent=2))


if __name__=='__main__':main()
