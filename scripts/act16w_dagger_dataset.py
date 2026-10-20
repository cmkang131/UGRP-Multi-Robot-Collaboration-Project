"""Append audited h0-only DAgger targets with exactly the D0 normalization.

Base tensors/frames are hardlinked into a new immutable dataset. Originals
are never edited. No teacher future along a student trajectory is invented.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import numpy as np
from act16w_runtime import ACT_SHA,require_gcp2,frozen_source,sha256
from act16w_dagger import prepare_single_step


def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def lines(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true')
    for k in ('base-root','starts','act-source','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--collections',type=Path,nargs='+',required=True);a=p.parse_args()
    if not a.enabled:p.error('DAgger data aggregation default OFF')
    require_gcp2();source=frozen_source(Path(__file__).resolve().parents[1]);frozen_source(a.act_source,ACT_SHA)
    sys.path.insert(0,str(a.act_source))
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import GraspDataset,image_array,IMAGE_HW,safe_path
    base=a.base_root/'dataset';manifest=read(base/'manifest.json')
    if not manifest['complete']:raise ValueError('completed D0 required')
    starts=read(a.starts)['seeds'];train=set(manifest['protocol']['train_seeds'])
    if len(starts)!=20 or len(set(starts))!=20 or not set(starts)<=train:raise ValueError('frozen20 unique TRAIN starts required')
    a.out.mkdir(parents=True,exist_ok=False);dest=a.out/'dataset';dest.mkdir()
    for f in base.rglob('*'):
        if f.is_file() and f.name not in ('manifest.json','RUN_META.json'):
            target=dest/f.relative_to(base);target.parent.mkdir(parents=True,exist_ok=True);os.link(f,target)
    episodes=list(manifest['episodes']);seen=set();tables=[];accepted_total=0;checkpoint=None
    for root in a.collections:
        summary=read(root/'summary.json');audit=read(root/'owner/oracle-audit.json')
        if (not summary['complete'] or summary.get('interface_probe_only') or summary['status']!='prefix_complete'
                or any(audit.get(k)!=0 for k in ('invisible_measurements','held_world_reads','teacher_actions_executed'))
                or audit.get('integration_and_actor_inputs_unchanged') is not True):raise ValueError('completed audited non-executing collection required')
        if checkpoint is None:checkpoint=summary['checkpoint_sha256']
        if checkpoint!=summary['checkpoint_sha256']:raise ValueError('one frozen student checkpoint per DAgger round')
        plans=read(root/'initial-plans.json')['episodes']
        for i,plan in enumerate(plans):
            seed=plan['seed'];raw=root/f'world-{i:03d}'
            if seed in seen or seed not in starts:raise ValueError('DAgger seed overlap/outside preregistered TRAIN starts')
            seen.add(seed);obs=lines(raw/'student-r1.jsonl');labels=lines(raw/'teacher-r1.jsonl');commands=lines(raw/'student-actions.jsonl')
            if len(obs)!=len(commands):raise ValueError('student command trace mismatch')
            for j in range(1,len(obs)):
                if obs[j]['issued'][-1]!=commands[j-1]['command']:raise ValueError('own history not from actual student action')
            targets,table=prepare_single_step(obs,labels,contract=c,audit=audit);table.update(seed=seed,raw=str(raw));tables.append(table)
            if not targets:continue
            folder=dest/f'dagger1-{seed}-r1';folder.mkdir();refs={}
            for row in targets:
                for ref in obs[row['observation_index']]['rgb']:
                    if refs.setdefault(ref['path'],ref)!=ref:raise ValueError('conflicting RGB provenance')
            ordered=sorted(refs);lookup={name:j for j,name in enumerate(ordered)}
            images=np.lib.format.open_memmap(folder/'images.npy',mode='w+',dtype=np.uint8,shape=(len(ordered),3,*IMAGE_HW))
            for j,name in enumerate(ordered):
                file=safe_path(raw,name)
                if sha256(file)!=refs[name]['sha256']:raise ValueError('DAgger actual JPEG changed')
                images[j]=image_array(file.read_bytes())
            images.flush();del images
            states=[];actions=[];pads=[];indices=[];samples=[];counts=Counter()
            for row in targets:
                observation=obs[row['observation_index']]
                states.append(c.context(observation));actions.append(row['action']);pads.append(row['action_is_pad']);indices.append([lookup[r['path']] for r in observation['rgb']]);counts[observation['skill']]+=1
                samples.append({**{k:observation[k] for k in ('robot_id','role','object_kind','skill','t')},'sample_id':'dagger1-'+observation['sample_id'],'source_sample_id':observation['sample_id']})
            np.savez_compressed(folder/'tensors.npz',state=np.asarray(states,np.float32),action=np.asarray(actions,np.float32),action_is_pad=np.asarray(pads,bool),image_index=np.asarray(indices,np.int64))
            write(folder/'samples.json',samples);write(folder/'rgb-provenance.json',[refs[k] for k in ordered])
            episodes.append(dict(path=folder.name,seed=seed,split='train',robot_id='r1',source_root=str(root),rows_total=len(obs),rows_selected=len(targets),frames=len(refs),skill_counts=dict(counts),done_counts={k:0 for k in counts},missing_done_skills=sorted(counts),horizons='h0 valid;7 padded',files={p.name:sha256(p) for p in folder.iterdir()}));accepted_total+=len(targets)
    table=dict(funnel=[dict(gate='registered_TRAIN_starts',passed=20,rejected=0),dict(gate='collected_starts',passed=len(seen),rejected=20-len(seen)),dict(gate='current_state_valid_teacher_targets',passed=accepted_total,rejected=sum(t['funnel'][0]['passed']-t['funnel'][1]['passed'] for t in tables))],per_episode=tables,raw=[str(x) for x in a.collections],reproduce=sys.argv,teacher_actions_executed=0)
    write(a.out/'dagger-rejection_table.json',table)
    if seen!=set(starts) or not accepted_total:raise ValueError('complete20-start coverage and nonempty valid labels required')
    derived={**manifest,'episodes':episodes,'protocol':{**manifest['protocol'],'dagger_v1':dict(round=1,starts=starts,student_checkpoint_sha256=checkpoint,normalization='D0 unchanged',valid_horizons=1)},'source_sha':source,'base_manifest_sha256':sha256(base/'manifest.json')}
    write(dest/'RUN_META.json',{'scope':'D0 plus student-induced h0-only teacher labels','class':'milestone','teacher_actions_executed':0})
    derived['files']={str(f.relative_to(dest)):sha256(f) for f in dest.rglob('*') if f.is_file() and f.name!='manifest.json'};write(dest/'manifest.json',derived)
    data=GraspDataset(dest,'train')
    if sha256(dest/'normalization.json')!=sha256(base/'normalization.json'):raise ValueError('D0 normalization changed')
    for name in ('fresh-recording-gate.json','rejection_table.json'):os.link(a.base_root/name,a.out/name)
    audit={**read(a.base_root/'dataset-audit.json'),'manifest_sha256':sha256(dest/'manifest.json'),'source_sha':source,'dagger_rows':accepted_total,'base_teacher_gate_not_pooled_with_student_prefixes':True,'D0_normalization_sha256':sha256(base/'normalization.json'),'valid_future_action_targets_verified':True,'dagger_valid_horizons_per_sample':1,'dagger_rejection_table':str(a.out/'dagger-rejection_table.json')}
    write(a.out/'dataset-audit.json',audit);print(json.dumps(dict(status='complete',D1_train_rows=len(data),dagger_rows=accepted_total,normalization_unchanged=True)))


if __name__=='__main__':main()
