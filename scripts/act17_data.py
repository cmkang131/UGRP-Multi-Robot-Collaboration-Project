"""ACT17 JPEG-backed tensors; keep native10Hz originals, no expanded image NPY.

Camera/image transforms and action normalization reuse frozen ACT functions.
Phase/episode metadata affects TRAIN sampling only and is never a policy tensor.
"""
from collections import Counter
from functools import lru_cache
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA
from act17_open_loop import read,phase_group
from act17_compact_records import original_sha256

ROOT=Path(__file__).resolve().parents[1]
B=Path('/home/ugrp/ugrp-sim')


def library():
    path=B/'src'/ACT_SHA
    sys.path.insert(0,str(path))
    return path


def pack_json(path,value):
    raw=json.dumps(value,separators=(',',':')).encode()
    if len(raw)>65536:
        target=Path(str(path)+'.zst')
        result=subprocess.run(['zstd','-q','-3','-o',str(target)],input=raw,check=True)
        if subprocess.check_output(['zstd','-dc',str(target)])!=raw:
            raise ValueError('JSON compression roundtrip changed bytes')
    else:
        target=path;target.write_bytes(raw)
    return target


@lru_cache(maxsize=1024)
def raw_image(path,digest,half):
    from PIL import Image
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError('source JPEG changed')
    with Image.open(io.BytesIO(data)) as image:
        if image.size!=(640,480):raise ValueError('native camera dimensions changed')
        image=image.convert('RGB')
        if half:image=image.resize((320,240),Image.Resampling.BILINEAR)
        return np.asarray(image,dtype=np.uint8).transpose(2,0,1).copy()


class Dataset:
    def __init__(self,root,split,*,image_mode='history_montage_v1'):
        library()
        if split not in ('train','validation') or image_mode not in ('history_montage_v1','current_full_v1'):
            raise ValueError('unknown dataset split or image mode')
        self.root,self.split,self.image_mode=Path(root),split,image_mode
        self.manifest=read(self.root/'manifest.json')
        if self.manifest.get('schema')!='ugrp.act17.jpeg_dataset.v1' or not self.manifest.get('complete'):
            raise ValueError('complete v7 audited dataset required')
        norm=self.manifest['normalization']
        if sha256(self.root/norm['path'])!=norm['sha256']:raise ValueError('normalization hash mismatch')
        self.stats=read(self.root/norm['path']);self.shards=[];self.index=[];self.metadata=[];self.episode_indices=[]
        for ep in self.manifest['episodes']:
            if ep['split']!=split:continue
            folder=self.root/ep['path']
            for name,digest in ep['files'].items():
                if sha256(folder/name)!=digest:raise ValueError('tensor metadata hash mismatch')
            with np.load(folder/'tensors.npz') as archive:shard={k:archive[k] for k in archive.files}
            shard['frames']=read(folder/'frames.json');metadata=read(folder/'samples.json')
            first=len(self.index);j=len(self.shards)
            self.index.extend((j,i) for i in range(len(shard['state'])))
            self.episode_indices.append(np.arange(first,len(self.index),dtype=np.int64))
            self.metadata.extend(metadata);self.shards.append(shard)
        if not self.index or len(self.index)!=len(self.metadata):raise ValueError('empty/misaligned split')
        self.stage_indices={name:np.array([i for i,m in enumerate(self.metadata) if m['stage']==name],dtype=np.int64)
                            for name in ('approach','alignment','grasp','release')}
        if split=='train' and any(not len(v) for v in self.stage_indices.values()):raise ValueError('four TRAIN strata required')

    def __len__(self):return len(self.index)

    def __getitem__(self,index):
        from harness.grasp_act_data import IMAGE_KEYS,history_image,normalized_image,assert_tensor_keys
        j,i=self.index[index];s=self.shards[j];refs=[s['frames'][k] for k in s['image_index'][i]]
        if self.image_mode=='current_full_v1':
            image=normalized_image(raw_image(refs[-1]['path'],refs[-1]['sha256'],False))
        else:
            image=history_image([raw_image(r['path'],r['sha256'],True) for r in refs])
        batch={IMAGE_KEYS[0]:image,'observation.state':
               (s['state'][i]-np.asarray(self.stats['state_mean'],np.float32))/np.asarray(self.stats['state_std'],np.float32),
               'action':(s['action'][i]-np.asarray(self.stats['action_mean'],np.float32))/np.asarray(self.stats['action_std'],np.float32),
               'action_is_pad':s['action_is_pad'][i].copy()}
        batch['action'][batch['action_is_pad']]=0.
        assert_tensor_keys(batch,training=True)
        return batch

    def sample(self,generator,batch_size,sampling):
        import torch
        if self.split!='train':raise ValueError('only TRAIN sampling is permitted')
        if sampling=='uniform_episode_v1':
            bins=self.episode_indices
        elif sampling=='uniform_stage_v1':
            bins=list(self.stage_indices.values())
        else:raise ValueError('unknown sampler')
        selected=torch.randint(len(bins),(batch_size,),generator=generator).tolist()
        return [int(bins[j][int(torch.randint(len(bins[j]),(1,),generator=generator))]) for j in selected]

    def completion_priors(self,sampling):
        """Exact TRAIN class fractions under the declared sampling measure.

        The inherited balanced BCE requires P(done|skill). Derive it from the
        actual episode/stage sampler, without changing action/state statistics
        or estimating any fraction from VAL. No new class-weight constant.
        """
        from harness import grasp_act_contract as c
        bins=self.episode_indices if sampling=='uniform_episode_v1' else list(self.stage_indices.values()) if sampling=='uniform_stage_v1' else None
        if bins is None or self.split!='train':raise ValueError('declared TRAIN sampler required')
        mass=np.zeros(len(self),dtype=np.float64)
        for indices in bins:mass[indices]+=1/len(bins)/len(indices)
        totals={skill:dict(mass=0.,positive_mass=0.,positive_n=0,rows_N=0) for skill in c.SKILLS}
        for index,(shard,row) in enumerate(self.index):
            skill=self.metadata[index]['skill'];value=totals[skill];positive=float(self.shards[shard]['action'][row,0,-1])
            if positive not in (0.,1.):raise ValueError('binary TRAIN completion required')
            value['mass']+=mass[index];value['positive_mass']+=mass[index]*positive
            value['positive_n']+=int(positive);value['rows_N']+=1
        return {skill:{**v,'positive_fraction':v['positive_mass']/v['mass'],
            'source':'unique TRAIN h0 labels weighted by exact declared sampler; not VAL'}
            for skill,v in totals.items() if v['rows_N'] and 0<v['positive_mass']<v['mass']}


def convert(protocol,gate,records,output):
    host=require_gcp2(training=True);source=frozen_source(ROOT);library()
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import paired_segments,fit_stats
    if (gate.get('cohort')!='act17-v7-native' or not gate.get('passed') or gate.get('N')!=40 or
            gate.get('n',0)<38 or gate.get('training_rgb') is not False or gate.get('input_audit_violations')!=0):
        raise ValueError('new native v7 camera-off gate40 required')
    for r in gate['raw_results']:
        if sha256(r['path'])!=r['sha256']:raise ValueError('v7 gate raw hash mismatch')
    locations={};checked_capture_roots=set();recording_receipts=[]
    for root in records:
        report=read(root/'gate-recount.json')
        if report.get('cohort')!='act17-v7-native' or not report.get('complete'):
            raise ValueError('completed v7 recording results required')
        recording_receipts.append(dict(path=str(root/'gate-recount.json'),sha256=sha256(root/'gate-recount.json'),
            n=report['n'],N=report['N'],source_sha=report['source_sha']))
        for group in root.glob('group-*'):
            capture_root=group/'capture'
            if capture_root not in checked_capture_roots:
                capture=read(capture_root/'summary.json')
                if capture.get('status')!='recording_complete' or capture.get('error'):
                    raise ValueError('capture/pairing incomplete')
                for name,digest in capture['sha256'].items():
                    if original_sha256(capture_root/name)!=digest:raise ValueError('raw capture manifest changed')
                checked_capture_roots.add(capture_root)
            for folder in (group/'capture').glob('world-*'):
                controller=group/'controller'/folder.name;plan=read(controller/'plan.json')
                if plan['seed'] in locations:raise ValueError('duplicate recording seed')
                locations[plan['seed']]=(folder,controller,plan)
    if set(locations)!=set(protocol['record_seeds']):raise ValueError('every preregistered recording seed must be accounted for')
    output.mkdir(parents=True,exist_ok=False)
    report=dict(schema='ugrp.act17.jpeg_dataset.v1',source_sha=source,host=host,cohort='act17-v7-native',
        complete=False,protocol=protocol,contact_profile='warp_native_contact_v1',episodes=[],rejections=[],
        storage='raw JPEG references; no copied or expanded image arrays',normalization=None,
        native_gate={k:gate[k] for k in ['source_sha','n','N','training_rgb','input_audit_violations','raw_results','runtime_profiles']},
        recording_receipts=recording_receipts)
    train_x=[];train_y=[];train_seeds=[];counts=Counter()
    for seed in protocol['record_seeds']:
        raw,controller,plan=locations[seed];score=read(controller/'result.json')
        if not score.get('physical_success') or score['status']!='complete' or score.get('cap_end'):
            report['rejections'].append(dict(seed=seed,reason_category='unsuccessful_teacher_recording',
                blocked_object='not_attributed',minimum_gap_m=None,minimum_gap_status='not_measured',raw=str(controller)));continue
        if any(score['input_audit'][k] for k in ['invisible_measurements','held_world_reads']):
            raise ValueError('teacher input boundary violation')
        scene=read(controller/'scene.json')
        if scene.get('act17_v7',{}).get('scenario_version')!='v7':raise ValueError('v7 scene receipt missing')
        observations=read(raw/'student-r1.jsonl',lines=True);labels=read(raw/'teacher-r1.jsonl',lines=True)
        groups=paired_segments(observations,labels,done_label='last_local_row_v1',include_initial_approach_v1=True)
        selected=[p for group in groups for p in group];frames={};states=[];actions=[];pads=[];images=[];metadata=[]
        split='validation' if seed in protocol['validation_seeds'] else 'train'
        for group in groups:
            windows=c.training_windows([v[0] for v in group],[v[1] for v in group])
            for (obs,label,_),window in zip(group,windows):
                state=c.context(obs);states.append(state);actions.append(window['action']);pads.append(window['action_is_pad'])
                refs=[]
                for ref in obs['rgb']:
                    path=(raw/ref['path']).resolve()
                    if sha256(path)!=ref['sha256']:raise ValueError('recorded RGB hash mismatch')
                    key=str(path)
                    if key not in frames:frames[key]=dict(path=key,sha256=ref['sha256'],index=len(frames))
                    refs.append(frames[key]['index'])
                images.append(refs)
                stage=phase_group(label)
                if stage=='setup':stage='approach'
                metadata.append(dict(seed=seed,sample_id=obs['sample_id'],t=obs['t'],skill=obs['skill'],stage=stage,teacher_phase=label['teacher_phase']))
                counts[split+':'+stage]+=1
                if split=='train':
                    train_x.append(state);train_y.append(c.encode_action(label['clean_teacher_command'],done=label['done']));train_seeds.append(seed)
        folder=output/str(seed);folder.mkdir()
        np.savez_compressed(folder/'tensors.npz',state=np.asarray(states,np.float32),action=np.asarray(actions,np.float32),
            action_is_pad=np.asarray(pads,bool),image_index=np.asarray(images,np.int64))
        frame_file=pack_json(folder/'frames.json',[{k:v for k,v in r.items() if k!='index'} for r in frames.values()])
        samples_file=pack_json(folder/'samples.json',metadata)
        files={p.name:sha256(p) for p in [folder/'tensors.npz',frame_file,samples_file]}
        report['episodes'].append(dict(seed=seed,kind=plan['kind'],split=split,path=folder.name,rows=len(states),frames=len(frames),
            source_capture=str(raw),source_controller=str(controller),files=files))
    if not train_x:raise ValueError('no valid TRAIN demonstrations')
    stats=fit_stats(train_x,train_y,train_seeds)
    norm=output/'normalization.json';norm.write_text(json.dumps(stats,indent=2)+'\n')
    report.update(complete=True,status='complete',normalization=dict(path=norm.name,sha256=sha256(norm)),stage_counts=dict(counts),
        eligible_train_seeds=stats['train_seeds'],selected_episode_counts=dict(Counter(e['split']+':'+e['kind'] for e in report['episodes'])))
    pack_json(output/'manifest.json',report)
    (output/'rejection_table.json').write_text(json.dumps(dict(funnel=[dict(gate='requested_recordings',passed=len(protocol['record_seeds']),rejected=0),
        dict(gate='successful_audited_recordings',passed=len(report['episodes']),rejected=len(report['rejections'])),
        dict(gate='selected_frame_pairs',passed=sum(e['rows'] for e in report['episodes']),rejected=0)],rejections=report['rejections'],
        raw=[str(r) for r in records],reproduce=sys.argv),indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['protocol','gate','out']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--records',type=Path,nargs='+',required=True)
    a=p.parse_args();convert(read(a.protocol),read(a.gate),a.records,a.out)


if __name__=='__main__':main()
