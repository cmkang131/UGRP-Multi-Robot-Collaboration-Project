"""One DAgger aggregation: immutable expert base + labels on student visits.

Student/failed rollout states may supply training rows; physical success is
not an admission condition for DAgger. Expert labels are limited to the valid
pre-hover prefix. Validation episodes remain fixed and are never aggregated.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import (fit_stats, image_array, read_rows, safe_path,
                                    sha256, write_json, GraspDataset)


def existing(path):return path if path.exists() else path.with_suffix(path.suffix+'.zst')


def aggregate(base, runs, output):
    if output.exists():raise FileExistsError(output)
    shutil.copytree(base,output,copy_function=os.link)
    manifest=json.loads((base/'manifest.json').read_text())
    original_manifest=sha256(base/'manifest.json')
    base_seeds=set(manifest['protocol']['train_seeds']+manifest['protocol']['validation_seeds'])
    new_seeds=[];audits=[]
    for run in runs:
        raw=run/'raw' if (run/'raw').exists() else run
        report=json.loads((raw/'summary.json').read_text())
        if not report['complete'] or report['status']!='complete':raise ValueError('unretrieved/HOST_ERROR collection')
        seed=report['seed']
        if seed in base_seeds or seed in new_seeds:raise ValueError('seed leakage')
        new_seeds.append(seed)
        shadow=json.loads((raw/'shadow-progress.json').read_text())
        if (shadow['teacher_actions_executed']!=0 or shadow['input_audit']['invisible_measurements']!=0
                or shadow['input_audit']['held_world_reads']!=0):raise ValueError('teacher boundary violation')
        observations=read_rows(existing(raw/'student-inputs.jsonl'))
        labels=read_rows(existing(raw/'shadow-labels.jsonl'))
        commands=read_rows(existing(raw/'commands.jsonl'))
        if not len(observations)==len(labels)==len(commands)==shadow['rows']:raise ValueError('unpaired collection')
        history=observations[0]['issued'];clock=c.IssuedClock()
        groups=[];group=[]
        for obs,label,command in zip(observations,labels,commands):
            c.validate_observation(obs)
            if obs['issued']!=history or obs['sample_id']!=label['sample_id'] or obs['t']!=label['t']:
                raise ValueError('actual issued history / sample alignment')
            clocks=clock.observe(obs['skill'],obs['t'],history[-1]['pwm'])
            if any(abs(obs[k]-v)>1e-8 for k,v in clocks.items()):raise ValueError('issued clock mismatch')
            history=(history+[c.command(command['command'])])[-c.HISTORY:]
            if label['label_valid']:
                if label['teacher_phase'] not in ('start','fold','approach','align','relook'):
                    raise ValueError('off-policy arm labels forbidden')
                target={'sample_id':obs['sample_id'],'skill':obs['skill'],'object_kind':obs['object_kind'],
                        'done':False,'terminal_reason':None,'clean_teacher_command':c.command(label['teacher_command'])}
                if group and abs(obs['t']-group[-1][0]['t']-c.PERIOD_S)>1e-5:groups.append(group);group=[]
                group.append((obs,target))
            elif group:groups.append(group);group=[]
        if group:groups.append(group)
        pairs=[p for group in groups for p in group]
        if not pairs:raise ValueError('no expert labels')
        folder=output/f'{seed}-r1';folder.mkdir()
        refs={r['path']:r for obs,_ in pairs for r in obs['rgb']}
        ordered=sorted(refs);indices={p:i for i,p in enumerate(ordered)}
        images=np.lib.format.open_memmap(folder/'images.npy',mode='w+',dtype=np.uint8,shape=(len(ordered),3,240,320))
        for i,name in enumerate(ordered):
            source=safe_path(raw,name)
            if sha256(source)!=refs[name]['sha256']:raise ValueError('RGB mismatch')
            images[i]=image_array(source.read_bytes())
        images.flush();del images
        windows=[w for group in groups for w in c.training_windows([p[0] for p in group],[p[1] for p in group])]
        values={'state':np.asarray([c.context(obs) for obs,_ in pairs],np.float32),
                'action':np.asarray([w['action'] for w in windows],np.float32),
                'action_is_pad':np.asarray([w['action_is_pad'] for w in windows],bool),
                'image_index':np.asarray([[indices[r['path']] for r in obs['rgb']] for obs,_ in pairs],np.int64)}
        np.savez_compressed(folder/'tensors.npz',**values)
        with np.load(folder/'tensors.npz',allow_pickle=False) as saved:
            if any(not np.array_equal(saved[k],v) for k,v in values.items()):raise ValueError('tensor readback mismatch')
        write_json(folder/'samples.json',[{k:obs[k] for k in ('sample_id','robot_id','role','object_kind','skill','t')} for obs,_ in pairs])
        write_json(folder/'rgb-provenance.json',[refs[p] for p in ordered])
        sources=[raw/'summary.json',raw/'shadow-progress.json',existing(raw/'shadow-labels.jsonl'),
                 existing(raw/'student-inputs.jsonl'),existing(raw/'commands.jsonl'),raw/'plan.json']
        record={'path':folder.name,'seed':seed,'split':'train','robot_id':'r1','source_root':str(run),
            'source_hashes':{str(p.relative_to(run)):sha256(p) for p in sources},
            'rows_total':len(observations),'rows_selected':len(pairs),'frames':len(ordered),
            'skill_counts':dict(Counter(obs['skill'] for obs,_ in pairs)),'done_counts':{'grasp':0},
            'missing_done_skills':['grasp'],'label_source':'same visible-only ACT11 expert on student visits',
            'student_rollout_success_required':False,
            'files':{p.name:sha256(p) for p in folder.iterdir()}}
        manifest['episodes'].append(record)
        audits.append({'seed':seed,'rows_all_audited':len(observations),'rows_labelled':len(pairs),
                       'shadow_audit':shadow,'source_hashes':record['source_hashes']})
    manifest['protocol']['train_seeds']+=new_seeds
    manifest['protocol']['dagger_rounds']=1
    manifest['protocol']['dagger_seeds']=new_seeds
    manifest['protocol']['closed_loop_eval_seeds']=list(range(91420,91440))+list(range(91500,91520))
    if set(new_seeds)&set(manifest['protocol']['closed_loop_eval_seeds']):raise ValueError('evaluation seed leakage')
    states=[];actions=[];seeds=[]
    for e in manifest['episodes']:
        if e['split']!='train':continue
        with np.load(output/e['path']/'tensors.npz',allow_pickle=False) as data:
            states.extend(data['state'].tolist());actions.extend(data['action'][:,0].tolist());seeds.extend([e['seed']]*len(data['state']))
    write_json(output/'normalization.json',fit_stats(states,actions,seeds))
    manifest['normalization']['sha256']=sha256(output/'normalization.json')
    manifest['dagger']={'rounds':1,'base_manifest_sha256':original_manifest,'base_path':str(base),
        'runs':[str(r) for r in runs],'audit':audits,
        'chunk_label_scope':'expert labels at successive student-visited states; no counterfactual expert continuation',
        'validation_unchanged':True,'expert_actions_executed':0,'teacher_after_hover_labels':0}
    manifest['files']={str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    write_json(output/'manifest.json',manifest)
    # Verify saved inventory and both input-only loaders before training.
    counts={split:len(GraspDataset(output,split)) for split in ('train','validation')}
    return {'complete':True,'base_manifest_sha256':original_manifest,'manifest_sha256':sha256(output/'manifest.json'),
        'new_seeds':new_seeds,'rows':counts,'audits':audits,'expert_actions_executed':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('base','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--runs',nargs='+',type=Path,required=True)
    a=p.parse_args()
    from scripts.grasp_act_training_guard import require_gcp
    require_gcp(training=False)
    report=aggregate(a.base,a.runs,a.output)
    write_json(a.output.parent/(a.output.name+'-audit.json'),report)


if __name__=='__main__':main()
