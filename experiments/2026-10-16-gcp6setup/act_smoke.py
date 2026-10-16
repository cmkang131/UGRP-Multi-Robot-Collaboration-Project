"""Synthetic CUDA ACT installation probe, never a research checkpoint or dataset.

Architecture/input shapes follow grasp_act_policy.py at 3f99d58c and the gcp2
act16w environment. Batch 1 is an installation probe, not the research batch 8.
The 50 optimizer steps are the requested infrastructure check, not a success gate.
"""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
import time

import torch
from lerobot.configs.types import FeatureType, PolicyFeature
from lerobot.policies.act.configuration_act import ACTConfig
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.act import modeling_act

ROOT = Path(__file__).resolve().parent
UPSTREAM = '89236ea0f4f81a81ca566081e20dd1ff5f823cbe'
SOURCE_SHA256 = '8d622935319af7d03f1efd95d51e726af2921010f7e4f5ec3742f62280493111'
direct = json.loads(metadata.distribution('lerobot').read_text('direct_url.json'))
assert direct['vcs_info']['commit_id'] == UPSTREAM
assert hashlib.sha256(Path(modeling_act.__file__).read_bytes()).hexdigest() == SOURCE_SHA256
assert torch.cuda.is_available() and 'L4' in torch.cuda.get_device_name(0)
torch.set_num_threads(4)
torch.manual_seed(20261016)
torch.cuda.manual_seed_all(20261016)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
torch.backends.cudnn.benchmark = False

config = ACTConfig(
    input_features={
        'observation.images.own_history': PolicyFeature(type=FeatureType.VISUAL, shape=(3, 480, 640)),
        'observation.state': PolicyFeature(type=FeatureType.STATE, shape=(252,)),
    },
    output_features={'action': PolicyFeature(type=FeatureType.ACTION, shape=(14,))},
    chunk_size=8, n_action_steps=8, temporal_ensemble_coeff=None,
    vision_backbone='resnet18', pretrained_backbone_weights=None,
    dim_model=512, n_heads=8, dim_feedforward=3200, n_encoder_layers=4,
    n_decoder_layers=1, n_vae_encoder_layers=4, latent_dim=32,
    kl_weight=10., dropout=.1, optimizer_lr=1e-5, optimizer_lr_backbone=1e-5,
    optimizer_weight_decay=1e-4, device='cuda',
)
policy = ACTPolicy(config).to('cuda')
optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
batch = {
    'observation.images.own_history': torch.rand(1, 3, 480, 640, device='cuda'),
    'observation.state': torch.rand(1, 252, device='cuda'),
    'action': torch.rand(1, 8, 14, device='cuda'),
    'action_is_pad': torch.zeros(1, 8, dtype=torch.bool, device='cuda'),
}
initial = next(policy.parameters()).detach().clone()
losses = []
started = time.monotonic()
for step in range(1, 51):
    policy.train()
    optimizer.zero_grad(set_to_none=True)
    loss, _ = policy(batch)
    assert torch.isfinite(loss)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
    optimizer.step()
    losses.append(loss.item())
    if step % 10 == 0:
        (ROOT/'act-progress.json').write_text(json.dumps({'step': step, 'loss': loss.item()})+'\n')
assert not torch.equal(initial, next(policy.parameters()))
policy.eval()
observations = {k: v for k, v in batch.items() if k.startswith('observation.')}
with torch.inference_mode():
    expected = policy.predict_action_chunk(observations).clone()
checkpoint = ROOT/'synthetic-act-smoke.pt'
torch.save({'model': policy.state_dict(), 'optimizer': optimizer.state_dict(), 'step': 50}, checkpoint)
state = torch.load(checkpoint, map_location='cuda', weights_only=True)
restored = ACTPolicy(config).to('cuda')
restored.load_state_dict(state['model'], strict=True)
restored_optimizer = torch.optim.AdamW(restored.get_optim_params(), lr=1e-5, weight_decay=1e-4)
restored_optimizer.load_state_dict(state['optimizer'])
assert state['step'] == 50
assert all(torch.equal(v, restored.state_dict()[k]) for k, v in policy.state_dict().items())
assert all(float(v['step']) == 50 for v in restored_optimizer.state.values())
restored.eval()
with torch.inference_mode():
    actual = restored.predict_action_chunk(observations)
assert torch.isfinite(actual).all() and torch.equal(expected, actual)
digest = hashlib.file_digest(checkpoint.open('rb'), 'sha256').hexdigest()
result = dict(status='PASS', scope='synthetic installation check only', research_result=False,
              data='synthetic random tensors; no act16w data copied', batch_size=1,
              optimizer_steps=50, losses=losses, parameters_updated=True,
              model_state_equal=True, optimizer_step_restored=True, predictions_bitwise_equal=True,
              checkpoint=str(checkpoint), checkpoint_bytes=checkpoint.stat().st_size,
              checkpoint_sha256=digest, upstream_commit=UPSTREAM, upstream_modeling_sha256=SOURCE_SHA256,
              reference_policy_source='3f99d58c5ada0862e669ef4065c0ba957f1b4547',
              versions={k: metadata.version(k) for k in ('torch','torchvision','lerobot','numpy','safetensors')},
              cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(0),
              wall_s=time.monotonic()-started, peak_gpu_bytes=torch.cuda.max_memory_allocated())
Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
