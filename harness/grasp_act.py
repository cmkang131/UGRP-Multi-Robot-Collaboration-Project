"""Color/skill-conditioned upstream ACT. Own RGB history and issued PWM only."""
from __future__ import annotations
import io,json,hashlib,importlib.util
from pathlib import Path
import numpy as np
import torch
import draccus
from PIL import Image
from safetensors.torch import save_file,load_file
from lerobot.configs.types import FeatureType,PolicyFeature
from lerobot.policies.act.configuration_act import ACTConfig
from lerobot.policies.act.modeling_act import ACTPolicy
from harness.reference_act import UPSTREAM_SHA
from harness.grasp_act_contract import SCHEMA,ACTION_DIM,CONTEXT_DIM,CHUNK,context,decode_action,SKILLS,KINDS,ROLES,RGB_HISTORY,RGB_LAGS_S,HISTORY,DESTINATIONS

IMAGE_KEYS=tuple('observation.images.own_t'+str(i) for i in range(RGB_HISTORY))
CONTEXT_KEY='observation.environment_state'
PROFILES={'smoke':96,'standard':224}


def verify_upstream():
    expected={'lerobot.policies.act.configuration_act':'35a60c0dd3c811b137b5eb035bdbd40d40e2c24ba0cda61756052e6e1c829282',
              'lerobot.policies.act.modeling_act':'2ea0acbdf210acee9d08f1f306afbda1e935bce0604b3b67b8d87c57c3f79a19'}
    for name,digest in expected.items():
        if hashlib.sha256(Path(importlib.util.find_spec(name).origin).read_bytes()).hexdigest()!=digest:
            raise ValueError('fixed upstream ACT source / two device patches required')
    return expected


def make_policy(profile='standard',*,pretrained=False):
    verify_upstream()
    size=PROFILES[profile]
    cfg=ACTConfig(input_features={**{k:PolicyFeature(type=FeatureType.VISUAL,shape=(3,size,size)) for k in IMAGE_KEYS},
        CONTEXT_KEY:PolicyFeature(type=FeatureType.ENV,shape=(CONTEXT_DIM,))},
        output_features={'action':PolicyFeature(type=FeatureType.ACTION,shape=(ACTION_DIM,))},
        chunk_size=CHUNK,n_action_steps=CHUNK,pretrained_backbone_weights=None,device='cpu',push_to_hub=False)
    if profile=='smoke':
        cfg.dim_model=64;cfg.n_heads=4;cfg.dim_feedforward=256;cfg.n_encoder_layers=2
        cfg.n_vae_encoder_layers=1;cfg.latent_dim=8;cfg.dropout=0.
    model=ACTPolicy(cfg)
    if pretrained:
        from torchvision.models import resnet18,ResNet18_Weights
        weights=resnet18(weights=ResNet18_Weights.IMAGENET1K_V1).state_dict()
        model.model.backbone.load_state_dict({k:weights[k] for k in model.model.backbone.state_dict()},strict=True)
    return model


def tensor(jpeg,profile):
    with Image.open(io.BytesIO(jpeg)) as image:
        a=np.array(image.convert('RGB').resize((PROFILES[profile],)*2,Image.Resampling.BILINEAR),dtype=np.float32)/255.
    value=torch.from_numpy(a).permute(2,0,1)
    return (value-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]


def batch(observation,jpegs,profile):
    ctx=context(observation)
    if len(jpegs)!=RGB_HISTORY:raise ValueError('fixed own image history required')
    return {**{k:tensor(v,profile).unsqueeze(0) for k,v in zip(IMAGE_KEYS,jpegs)},
            CONTEXT_KEY:torch.tensor([ctx],dtype=torch.float32)}


def metadata(profile):
    return {'schema':'ugrp.grasp_act.adapter.v5','action_contract':SCHEMA,
            'actuator_port':'real_range_per_wheel_duty_v1',
            'upstream_sha':UPSTREAM_SHA,'profile':profile,
            'image_keys':list(IMAGE_KEYS),'rgb_lags_s':list(RGB_LAGS_S),'command_history':HISTORY,
            'skills':list(SKILLS),'object_kinds':list(KINDS),'roles':list(ROLES),'destinations':list(DESTINATIONS),'context_dim':CONTEXT_DIM,
            'action_dim':ACTION_DIM,'chunk':CHUNK,'truth_at_inference':False,'measured_joints':False}


class GraspAct:
    def __init__(self,policy,profile='standard'):
        self.policy=policy.eval();self.profile=profile
    @torch.inference_mode()
    def predict_chunk(self,observation,jpegs):
        device=next(self.policy.parameters()).device
        b={k:v.to(device) for k,v in batch(observation,jpegs,self.profile).items()}
        return [decode_action(v) for v in self.policy.predict_action_chunk(b)[0].cpu().tolist()]
    def save(self,root):
        root=Path(root);root.mkdir(parents=True,exist_ok=False)
        save_file({k:v.detach().cpu().contiguous() for k,v in self.policy.state_dict().items()},str(root/'model.safetensors'))
        cfg=draccus.encode(self.policy.config);cfg['device']='cpu'
        (root/'config.json').write_text(json.dumps(cfg,indent=2))
        (root/'adapter.json').write_text(json.dumps(metadata(self.profile),indent=2))
    @classmethod
    def load(cls,root,device='cpu'):
        root=Path(root);meta=json.loads((root/'adapter.json').read_text());profile=meta['profile']
        if meta!=metadata(profile):raise ValueError('wrong ACT adapter')
        model=make_policy(profile)
        if json.loads((root/'config.json').read_text())!=json.loads(json.dumps(draccus.encode(model.config))):
            raise ValueError('wrong ACT configuration')
        model.load_state_dict(load_file(str(root/'model.safetensors')),strict=True)
        return cls(model.to(device),profile)
