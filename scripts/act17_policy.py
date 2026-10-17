"""Serialized ACT17 image adapter; own RGB/history/task/issued-state only."""
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from act17_data import library
from act16w_runtime import sha256,LEROBOT_ACT_SHA256

IMAGE_MODES=('history_montage_v1','current_full_v1')


def observation_batch(observation,jpegs,stats,image_mode):
    library()
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import IMAGE_KEYS,history_image,image_array,normalized_image,assert_tensor_keys
    c.validate_observation(observation)
    if image_mode not in IMAGE_MODES or len(jpegs)!=4:raise ValueError('serialized image mode and own history required')
    for ref,jpeg in zip(observation['rgb'],jpegs):
        if hashlib.sha256(jpeg).hexdigest()!=ref['sha256']:raise ValueError('inference RGB hash mismatch')
    if image_mode=='history_montage_v1':image=history_image([image_array(j) for j in jpegs])
    else:
        from PIL import Image
        with Image.open(io.BytesIO(jpegs[-1])) as frame:
            if frame.size!=(640,480):raise ValueError('native camera dimensions changed')
            image=normalized_image(np.asarray(frame.convert('RGB'),np.uint8).transpose(2,0,1))
    value={IMAGE_KEYS[0]:image,'observation.state':
        (np.asarray(c.context(observation),np.float32)-np.asarray(stats['state_mean'],np.float32))/np.asarray(stats['state_std'],np.float32)}
    assert_tensor_keys(value)
    return value


def save_actor(policy,root,stats,provenance,*,image_mode,sampling):
    library()
    from harness.grasp_act_policy import save_actor as base_save
    if image_mode not in IMAGE_MODES or sampling not in ('uniform_episode_v1','uniform_stage_v1'):
        raise ValueError('known training/image candidates required')
    base_save(policy,root,stats,provenance,done_mode='balanced_bce_v1')
    root=Path(root);meta=json.loads((root/'adapter.json').read_text())
    meta.update(schema='ugrp.act17.adapter.v1',image_mode=image_mode,sampling=sampling,
        cohort='act17-v7-native',student_input_contract='own RGB history + own issued commands + task tokens/clocks',
        image_normalization='RGB/255 then ImageNet mean/std once',teacher_phase_policy_input=False)
    if image_mode=='current_full_v1':
        meta.update(image_hw=[480,640],history_layout='current_frame_only_from_own_history_contract')
    (root/'adapter.json').write_text(json.dumps(meta,indent=2)+'\n')
    (root/'SHA256.json').write_text(json.dumps({n:sha256(root/n) for n in ['model.safetensors','config.json','adapter.json']},indent=2)+'\n')


class Actor:
    def __init__(self,base,image_mode):
        self.base,self.image_mode=base,image_mode
        self.policy,self.stats=base.policy,base.stats

    def predict(self,observation,jpegs):
        import torch
        batch=observation_batch(observation,jpegs,self.stats,self.image_mode)
        batch={k:torch.from_numpy(v.copy()).unsqueeze(0).to(self.base.device) for k,v in batch.items()}
        with torch.inference_mode():values=self.policy.predict_action_chunk(batch)[0].cpu().numpy()
        values=self.base.decode_predictions(values)
        if values.shape!=(8,14) or not np.isfinite(values).all():raise ValueError('invalid ACT output; no fallback')
        return values.tolist()

    @classmethod
    def load(cls,root,*,device='cpu'):
        library()
        import draccus
        from safetensors.torch import load_file
        from lerobot.policies.act import modeling_act
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import make_policy,GraspActor,UPSTREAM_SHA
        root=Path(root);hashes=json.loads((root/'SHA256.json').read_text())
        if set(hashes)!={'model.safetensors','config.json','adapter.json'} or any(sha256(root/k)!=v for k,v in hashes.items()):
            raise ValueError('ACT17 checkpoint inventory/hash mismatch')
        meta=json.loads((root/'adapter.json').read_text())
        if (meta.get('schema')!='ugrp.act17.adapter.v1' or meta.get('image_mode') not in IMAGE_MODES
                or meta.get('cohort')!='act17-v7-native' or meta.get('done_mode')!='balanced_bce_v1'
                or meta.get('blank_images') or meta.get('upstream_sha')!=UPSTREAM_SHA
                or meta.get('contract_sha256')!=sha256(Path(c.__file__)) or sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256):
            raise ValueError('ACT17 adapter/source mismatch; legacy loader cannot deploy this model')
        expected_hw=[480,640] if meta['image_mode']=='current_full_v1' else [240,320]
        if meta.get('image_hw')!=expected_hw or meta.get('model_image_hw')!=[480,640]:
            raise ValueError('serialized preprocessing resolution differs')
        policy=make_policy(device=device)
        saved=json.loads((root/'config.json').read_text());actual=json.loads(json.dumps(draccus.encode(policy.config)))
        saved['device']=actual['device']
        if saved!=actual:raise ValueError('frozen ACT architecture differs')
        policy.load_state_dict(load_file(str(root/'model.safetensors')),strict=True)
        return cls(GraspActor(policy,meta['stats'],device=device,done_mode='balanced_bce_v1'),meta['image_mode'])
