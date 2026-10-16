"""Compose audited original/recovery shards and refit TRAIN-only normalization.

Original validation seeds calibrated DART and are excluded from the fresh
validation denominator. Raw tensors/images are copied without transformation.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import numpy as np
from harness.grasp_act_data import DATA_SCHEMA, fit_stats, read_json, safe_path, sha256, write_json


def merge(original, recovery, output):
    output=Path(output)
    roots=list(map(Path,(original,recovery)))
    manifests=[json.loads((r/'manifest.json').read_text()) for r in roots]
    for root,m in zip(roots,manifests):
        if m.get('schema')!=DATA_SCHEMA or not m.get('complete') or m.get('done_label')!='last_local_row_v1':
            raise ValueError('complete matching audited datasets required')
        for e in m['episodes']:
            for name,digest in e['files'].items():
                if sha256(safe_path(root,e['path'])/name)!=digest:raise ValueError('corrupt source shard')
    source_hosts=[]
    for m in manifests:
        for episode in m['episodes']:
            raw=Path(episode['source_root'])/'raw'
            result=raw/'result.json.zst' if (raw/'result.json.zst').exists() else raw/'result.json'
            host=read_json(result).get('execution_host')
            if not host:raise ValueError('source execution host unavailable')
            source_hosts.append(host)
    if any(h!=source_hosts[0] for h in source_hosts):raise ValueError('mixed simulation hosts/machine types')
    if manifests[0]['camera']!=manifests[1]['camera']:raise ValueError('camera mismatch')
    if any(m.get('input_audit')!={'forbidden_input_fields':0,'teacher_input_fields':0} for m in manifests):
        raise ValueError('input audit mismatch')
    seen=set();episodes=[];xs=[];ys=[];train=[];validation=[]
    output.mkdir(parents=True,exist_ok=False)
    report={'schema':DATA_SCHEMA,'complete':False,'status':'running','done_label':'last_local_row_v1',
        'input_keys':manifests[0]['input_keys'],'image_hw':manifests[0]['image_hw'],
        'camera':manifests[0]['camera'],'execution_host':source_hosts[0],'input_audit':manifests[0]['input_audit'],
        'composition':[{'root':str(r),'manifest_sha256':sha256(r/'manifest.json')} for r in roots],
        'excluded_calibration_seeds':manifests[0]['protocol']['validation_seeds']}
    try:
        for source_index,(root,m) in enumerate(zip(roots,manifests)):
            for e in m['episodes']:
                # Do not call previously consulted calibration data a fresh holdout.
                if source_index==0 and e['split']=='validation':continue
                if e['seed'] in seen:raise ValueError('duplicate seed across sources')
                seen.add(e['seed']);item=deepcopy(e);item['source_dataset']=source_index
                folder=safe_path(output,e['path']);shutil.copytree(safe_path(root,e['path']),folder)
                for name,digest in e['files'].items():
                    if sha256(folder/name)!=digest:raise ValueError('composed shard copy mismatch')
                episodes.append(item)
                if e['split']=='train':
                    with np.load(folder/'tensors.npz',allow_pickle=False) as a:
                        if a['action_is_pad'][:,0].any():raise ValueError('padded first target')
                        xs.extend(a['state']);ys.extend(a['action'][:,0]);train.extend([e['seed']]*len(a['state']))
                elif e['split']=='validation':validation.append(e['seed'])
                else:raise ValueError('unsupported source split')
        if set(train)&set(validation) or not validation:raise ValueError('fresh validation required')
        stats=fit_stats(xs,ys,train);write_json(output/'normalization.json',stats)
        report.update(complete=True,status='complete',episodes=episodes,
            protocol={'train_seeds':sorted(set(train)),'validation_seeds':sorted(validation),
                      'done_label':'last_local_row_v1','composition':'original train + recovery train; fresh recovery validation only'},
            normalization={'path':'normalization.json','sha256':sha256(output/'normalization.json')})
    except BaseException as e:
        report.update(status='HOST_ERROR',error_type=type(e).__name__)
        raise
    finally:write_json(output/'manifest.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('original','recovery','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();merge(a.original,a.recovery,a.output)


if __name__=='__main__':main()
