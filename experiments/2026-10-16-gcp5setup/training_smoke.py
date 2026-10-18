"""50-step environment smoke using committed beamact3 modules; no C2 gate claim."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
import urllib.request

source, output = map(Path, sys.argv[1:3])
sys.path.insert(0, str(source))


def meta(key):
    request = urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/' + key,
                                     headers={'Metadata-Flavor': 'Google'})
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.read().decode().strip().split('/')[-1]


host = {k: meta(v) for k, v in dict(project='project/project-id', instance='instance/name',
                                  machine='instance/machine-type').items()}
assert host == dict(project='ugrp-sim-e-1016', instance='ugrp-act-l4-gcp5', machine='g2-standard-8')
reference = json.loads((source/'source-provenance.json').read_text())
for name, digest in reference['files_sha256'].items():
    assert hashlib.sha256((source/name).read_bytes()).hexdigest() == digest, name
sha = reference['source_sha']
output.mkdir(exist_ok=False)
report = dict(status='running', research_result=False, host=host, source_sha=sha,
              steps_requested=50, steps_completed=0, readback_verified=False,
              scope='environment smoke with beamact3 B modules, not C2 training/mission acceptance')
started = time.time()
try:
    import torch
    import scripts.train_grasp_act
    runpy.run_path(str(source/'experiments/2026-10-16-beamact3/train_shared.py'),
                   run_name='gcp5_dependency_import_check')
    from harness.grasp_act_data import GraspDataset, sha256, assert_tensor_keys
    from harness.grasp_act_policy import make_policy
    from harness.beamact3 import install_head, transform_batch, policy_loss, save_actor, Beam3Actor
    from harness.grasp_act_loss import completion_priors
    from harness.act_training import checkpoint_encoder
    assert torch.cuda.is_available() and 'L4' in torch.cuda.get_device_name(0)
    torch.set_num_threads(4)
    torch.manual_seed(20261015)
    torch.cuda.manual_seed_all(20261015)
    torch.backends.cudnn.benchmark = False
    data_root = Path('/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view')
    digest = sha256(data_root/'manifest.json')
    assert digest == 'a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'
    data = GraspDataset(data_root, 'train')
    priors = completion_priors(data)
    policy = install_head(make_policy(pretrained=True, device='cuda'), data.stats)
    optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(20261015)
    with (output/'progress.jsonl').open('x') as log:
        # Explicit requested compute bound. No wall-clock action/planning limit.
        for step in range(1, 51):
            batch = torch.utils.data.default_collate([data[i] for i in torch.randint(len(data), (8,), generator=generator).tolist()])
            assert_tensor_keys(batch, training=True)
            batch = transform_batch({k: v.to('cuda') for k, v in batch.items()}, 'B')
            policy.train()
            optimizer.zero_grad(set_to_none=True)
            with checkpoint_encoder(policy, enabled=True):
                loss, metrics = policy_loss(policy, batch, mode='balanced_bce_v1', stats=data.stats, priors=priors)
                assert torch.isfinite(loss)
                loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
            optimizer.step()
            report['steps_completed'] = step
            if step == 1 or step % 10 == 0:
                log.write(json.dumps(dict(step=step, loss=loss.item(), wall_s=time.time()-started))+'\n')
                log.flush()
    provenance = dict(source_sha=sha, dataset_manifest_sha256=digest, step=50,
                      seed=20261015, run_class='dev', research_result=False)
    save_actor(policy, output/'actor', data.stats, provenance, arm='B')
    torch.save(dict(optimizer=optimizer.state_dict(), rng=torch.get_rng_state(),
                    sampler_rng=generator.get_state()), output/'optimizer.pt')
    restored = Beam3Actor.load(output/'actor', device='cuda')
    optimizer2 = torch.optim.AdamW(restored.policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
    optimizer2.load_state_dict(torch.load(output/'optimizer.pt', map_location='cpu', weights_only=True)['optimizer'])
    probe = data[0]
    inputs = transform_batch({k: torch.from_numpy(v.copy()).unsqueeze(0).to('cuda')
                              for k, v in probe.items() if k.startswith('observation.')}, 'B')
    policy.eval()
    restored.policy.eval()
    with torch.inference_mode():
        expected = policy.predict_action_chunk(inputs)
        actual = restored.policy.predict_action_chunk(inputs)
    assert torch.equal(expected, actual)
    report.update(status='PASS', readback_verified=True, optimizer_reloaded=True,
                  dataset_manifest_sha256=digest, training_rows=len(data),
                  inputs=list(inputs), teacher_input_fields=0,
                  peak_gpu_bytes=torch.cuda.max_memory_allocated(),
                  versions={p: importlib.metadata.version(p) for p in ('torch', 'torchvision', 'lerobot', 'numpy')},
                  files_sha256={str(p.relative_to(output)): sha256(p) for p in output.rglob('*') if p.is_file()})
except BaseException as exc:
    report.update(status='HOST_ERROR', error_type=type(exc).__name__, error=str(exc))
    raise
finally:
    report['wall_s'] = time.time()-started
    (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
