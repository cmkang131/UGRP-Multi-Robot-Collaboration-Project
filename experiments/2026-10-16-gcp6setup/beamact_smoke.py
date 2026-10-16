"""50-step real-data environment probe; existing B adapter, not a C2 result.

The managed research trainer still admits gcp2 only. This installation check
uses the same public library and versioned module functions, validates gcp6's
own metadata, and never patches or invokes the managed trainer's host guard.
"""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import runpy
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'beamact3-runtime'
sys.path.insert(0, str(SOURCE))
request = lambda k: urllib.request.Request(
    'http://metadata.google.internal/computeMetadata/v1/'+k, headers={'Metadata-Flavor':'Google'})
host = {}
for name, key in [('project','project/project-id'),('instance','instance/name'),('machine','instance/machine-type')]:
    with urllib.request.urlopen(request(key), timeout=3) as response:
        host[name] = response.read().decode().strip().split('/')[-1]
assert host == dict(project='ugrp-sim-f-1016',instance='ugrp-act-l4-gcp6',machine='g2-standard-8')
source_manifest = json.loads((SOURCE/'SOURCE.json').read_text())
for name, digest in source_manifest['files_sha256'].items():
    assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() == digest
runpy.run_path(str(SOURCE/'experiments/2026-10-16-beamact3/train_shared.py'), run_name='dependency_probe')

import torch
from harness.grasp_act_data import GraspDataset, assert_tensor_keys, sha256
from harness.grasp_act_policy import make_policy
from harness.grasp_act_loss import completion_priors
from harness.act_training import checkpoint_encoder
from harness.beamact3 import install_head, policy_loss, transform_batch, save_actor, Beam3Actor
from lerobot.policies.act import modeling_act

assert sha256(Path(modeling_act.__file__)) == '8d622935319af7d03f1efd95d51e726af2921010f7e4f5ec3742f62280493111'
assert torch.cuda.is_available() and 'L4' in torch.cuda.get_device_name(0)
torch.set_num_threads(4)
torch.manual_seed(20261015)
torch.cuda.manual_seed_all(20261015)
torch.backends.cudnn.benchmark = False
started = time.monotonic()
data_root = Path('/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view')
manifest_hash = sha256(data_root/'manifest.json')
assert manifest_hash == 'a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'
data = GraspDataset(data_root, 'train')
priors = completion_priors(data)
policy = install_head(make_policy(pretrained=True, device='cuda'), data.stats)
optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
generator = torch.Generator().manual_seed(20261015)
out = ROOT/'beamact3-environment-smoke'
out.mkdir(exist_ok=False)
losses = []
for step in range(1, 51):
    indices = torch.randint(len(data), (8,), generator=generator).tolist()
    batch = torch.utils.data.default_collate([data[i] for i in indices])
    assert_tensor_keys(batch, training=True)
    batch = transform_batch({k:v.to('cuda') for k,v in batch.items()}, 'B')
    policy.train()
    optimizer.zero_grad(set_to_none=True)
    with checkpoint_encoder(policy, enabled=True):
        loss, _ = policy_loss(policy, batch, mode='balanced_bce_v1', stats=data.stats, priors=priors)
        assert torch.isfinite(loss)
        loss.backward()
    torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
    optimizer.step()
    losses.append(loss.item())
    if step % 10 == 0:
        (ROOT/'act-progress.json').write_text(json.dumps({'step':step,'loss':loss.item()})+'\n')
save_actor(policy, out/'actor', data.stats, dict(source_sha=source_manifest['source_sha'],step=50,
           dataset_manifest_sha256=manifest_hash,research_result=False,purpose='installation only'), arm='B')
torch.save({'optimizer':optimizer.state_dict(),'step':50,'sampler_rng':generator.get_state()},out/'optimizer.pt')
restored = Beam3Actor.load(out/'actor', device='cuda')
state = torch.load(out/'optimizer.pt', map_location='cuda', weights_only=True)
restored_optimizer = torch.optim.AdamW(restored.policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
restored_optimizer.load_state_dict(state['optimizer'])
assert state['step'] == 50 and all(float(v['step']) == 50 for v in restored_optimizer.state.values())
assert all(torch.equal(v, restored.policy.state_dict()[k]) for k,v in policy.state_dict().items())
policy.eval()
inputs = {k:v for k,v in batch.items() if k.startswith('observation.')}
with torch.inference_mode():
    expected, actual = policy.predict_action_chunk(inputs), restored.policy.predict_action_chunk(inputs)
assert torch.isfinite(actual).all() and torch.equal(expected,actual)
result = dict(status='PASS',scope='real-data installation check only; existing B compatibility, not C2',
              research_result=False,host=host,source_sha=source_manifest['source_sha'],
              dataset_manifest_sha256=manifest_hash,training_rows=len(data),batch_size=8,
              optimizer_steps=50,losses=losses,model_state_equal=True,optimizer_step_restored=True,
              predictions_bitwise_equal=True,train_shared_dependencies_imported=True,
              versions={k:metadata.version(k) for k in ('torch','torchvision','lerobot','numpy')},
              cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(0),wall_s=time.monotonic()-started,
              peak_gpu_bytes=torch.cuda.max_memory_allocated(),
              artifacts={str(p.relative_to(out)):sha256(p) for p in out.rglob('*') if p.is_file()})
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
