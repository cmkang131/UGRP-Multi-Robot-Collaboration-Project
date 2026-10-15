"""Finite GCP L4 pilot. JSON logs, fixed final step, resumable local checkpoints."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import signal
import time

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import GraspDataset, assert_tensor_keys, sha256, write_json, write_summary
from scripts.grasp_act_training_guard import authorize_main, require_gcp, source_sha
from harness.grasp_act_loss import DONE_MODES, completion_priors, policy_loss


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stage', choices=('smoke', 'main'), required=True)
    p.add_argument('--steps', type=int, required=True)
    p.add_argument('--max-wall-s', type=int, default=1800)
    p.add_argument('--seed', type=int, default=20261015)
    p.add_argument('--resume', type=Path)
    p.add_argument('--approval', type=Path)
    p.add_argument('--smoke-summary', type=Path)
    p.add_argument('--blank-images', action='store_true')
    p.add_argument('--done-loss', choices=DONE_MODES, default='legacy_l1')
    p.add_argument('--done-loss-weight', type=float, default=1.)
    a = p.parse_args()
    if not math.isfinite(a.done_loss_weight) or a.done_loss_weight <= 0:
        p.error('completion loss weight must be finite and positive')
    if not 1 <= a.max_wall_s <= 7 * 3600 or not 1 <= a.steps <= 100000:
        p.error('finite steps and <=7h process budget required')
    if a.stage == 'smoke' and (a.steps > 500 or a.max_wall_s > 1800 or a.resume):
        p.error('smoke: <=500 steps, <=1800s, fresh initialization')
    host, source = require_gcp(training=True), source_sha()
    dataset_hash = sha256(a.dataset / 'manifest.json')
    if a.stage == 'main':
        smoke_hash = sha256(a.smoke_summary) if a.smoke_summary else None
        smoke = json.loads(a.smoke_summary.read_text()) if a.smoke_summary else {}
        if (smoke.get('status') != 'complete' or smoke.get('stage') != 'smoke'
                or smoke.get('dataset_manifest_sha256') != dataset_hash
                or smoke.get('source_sha') != source or not smoke.get('readback_verified')
                or smoke.get('blank_images') != a.blank_images
                or smoke.get('done_loss', 'legacy_l1') != a.done_loss
                or smoke.get('done_loss_weight', 1.) != a.done_loss_weight):
            raise ValueError('completed matching smoke with checkpoint readback required')
        authorize_main(a.approval, source=source, dataset_hash=dataset_hash,
                       smoke_hash=smoke_hash, steps=a.steps, blank=a.blank_images)
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'complete': False, 'stage': a.stage,
        'source_sha': source, 'dataset_manifest_sha256': dataset_hash, 'host': host,
        'steps_requested': a.steps, 'steps_completed': 0, 'seed': a.seed,
        'blank_images': a.blank_images, 'done_loss': a.done_loss, 'done_loss_weight': a.done_loss_weight,
        'batch_size': 8, 'readback_verified': False,
        'gate_promotion_authorized_if_all_conditions_pass': False,
        'selection': 'fixed final step; validation never selects checkpoint'}
    write_summary(a.output / 'summary.json', report)
    write_json(a.output / 'RUN_META.json', {'class': 'milestone', 'sha': source})
    started, last_checkpoint = time.monotonic(), None
    stop = {'requested': False}
    def request_stop(signum, frame):
        stop['requested'] = True
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        import torch
        from harness.act_training import checkpoint_encoder
        from harness.grasp_act_policy import GraspActor, make_policy, save_actor
        if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):
            raise RuntimeError('CUDA NVIDIA L4 required')
        torch.manual_seed(a.seed)
        torch.cuda.manual_seed_all(a.seed)
        torch.set_num_threads(4)
        torch.backends.cudnn.benchmark = False
        data = GraspDataset(a.dataset, 'train', blank=a.blank_images)
        priors = completion_priors(data) if a.done_loss != 'legacy_l1' else None
        report['done_class_counts'] = priors
        policy = make_policy(pretrained=not bool(a.resume), device='cuda')
        optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
        generator = torch.Generator().manual_seed(a.seed)
        step = 0
        if a.resume:
            resume = json.loads((a.resume / 'resume.json').read_text())
            for k, v in {'source_sha': source, 'dataset_manifest_sha256': dataset_hash,
                         'blank_images': a.blank_images, 'seed': a.seed,
                         'done_loss': a.done_loss, 'done_loss_weight': a.done_loss_weight}.items():
                if resume.get(k, {'done_loss': 'legacy_l1', 'done_loss_weight': 1.}.get(k)) != v:
                    raise ValueError('resume provenance mismatch: ' + k)
            if sha256(a.resume / 'optimizer.pt') != resume['optimizer_sha256']:
                raise ValueError('resume optimizer hash mismatch')
            actor = GraspActor.load(a.resume / 'actor', device='cuda')
            if actor.done_mode != a.done_loss:
                raise ValueError('resume completion output mismatch')
            policy.load_state_dict(actor.policy.state_dict(), strict=True)
            del actor
            state = torch.load(a.resume / 'optimizer.pt', map_location='cpu', weights_only=True)
            optimizer.load_state_dict(state['optimizer'])
            torch.set_rng_state(state['rng'])
            torch.cuda.set_rng_state_all(state['cuda_rng'])
            generator.set_state(state['sampler_rng'])
            step = resume['step']
        if step >= a.steps:
            raise ValueError('resume already reached requested steps')
        # Replacement sampler is regenerated per step: exact saved RNG, no
        # prefetched sampler positions to lose when resuming a finite session.
        report['environment'] = {k: importlib.metadata.version(k) for k in ('torch', 'torchvision', 'lerobot', 'numpy')}
        report['training_rows'] = len(data)
        report['gpu'] = torch.cuda.get_device_name(0)
        report['cuda'] = torch.version.cuda
        report['python'] = sys.version
        report['backbone_initialization'] = 'ResNet18_Weights.IMAGENET1K_V1; fine-tuned; no freeze/cache'
        report['activation_checkpointing'] = 'harness.act_training.checkpoint_encoder'
        initial_step = step

        def checkpoint():
            nonlocal last_checkpoint
            if last_checkpoint is not None and last_checkpoint.name == f'step-{step:06d}':
                return
            folder = a.output / f'step-{step:06d}'
            folder.mkdir()
            provenance = {'source_sha': source, 'dataset_manifest_sha256': dataset_hash,
                          'blank_images': a.blank_images, 'seed': a.seed, 'step': step,
                          'done_loss': a.done_loss, 'done_loss_weight': a.done_loss_weight,
                          'done_class_counts': priors}
            save_actor(policy, folder / 'actor', data.stats, provenance, blank=a.blank_images, done_mode=a.done_loss)
            torch.save({'optimizer': optimizer.state_dict(), 'rng': torch.get_rng_state(),
                        'cuda_rng': torch.cuda.get_rng_state_all(), 'sampler_rng': generator.get_state()},
                       folder / 'optimizer.pt')
            write_json(folder / 'resume.json', {**provenance, 'optimizer_sha256': sha256(folder / 'optimizer.pt')})
            last_checkpoint = folder
            report['last_checkpoint'] = str(folder)

        with (a.output / 'progress.jsonl').open('x') as log:
            while step < a.steps:
                if stop['requested'] or time.monotonic() - started > a.max_wall_s:
                    break
                if (a.output / 'SUPERVISOR_STOP.json').exists():
                    stop['requested'] = True
                    break
                indices = torch.randint(len(data), (8,), generator=generator).tolist()
                batch = torch.utils.data.default_collate([data[i] for i in indices])
                assert_tensor_keys(batch, training=True)
                batch = {k: v.to('cuda') for k, v in batch.items()}
                policy.train()
                optimizer.zero_grad(set_to_none=True)
                # Existing upstream-compatible activation checkpoint helper.
                with checkpoint_encoder(policy, enabled=True):
                    loss, metrics = policy_loss(policy, batch, mode=a.done_loss,
                        stats=data.stats, priors=priors, weight=a.done_loss_weight)
                    if not torch.isfinite(loss):
                        raise ValueError('nonfinite training loss')
                    loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
                optimizer.step()
                step += 1
                if step == initial_step + 1 or step % 10 == 0:
                    elapsed = time.monotonic() - started
                    row = {'step': step, 'loss': loss.item(), **metrics, 'gradient_norm': float(norm),
                           'wall_s': elapsed, 'steps_per_s': (step - initial_step) / elapsed,
                           'peak_gpu_bytes': torch.cuda.max_memory_allocated()}
                    log.write(json.dumps(row, allow_nan=False) + '\n')
                    log.flush()
                    report.update(steps_completed=step, latest=row)
                    write_summary(a.output / 'summary.json', report)
                if step % (100 if a.stage == 'smoke' else 500) == 0:
                    checkpoint()
            checkpoint()
        # Verify saved weights load and reproduce a held TRAINING input chunk.
        restored = GraspActor.load(last_checkpoint / 'actor', device='cuda')
        probe = data[0]
        inputs = {k: torch.from_numpy(v.copy()).unsqueeze(0).to('cuda')
                  for k, v in probe.items() if k.startswith('observation.')}
        assert_tensor_keys(inputs)
        with torch.inference_mode():
            expected = policy.predict_action_chunk(inputs)
            actual = restored.policy.predict_action_chunk(inputs)
        if not torch.equal(expected, actual):
            raise ValueError('saved model prediction readback mismatch')
        report.update(status='complete' if step == a.steps else 'interrupted' if stop['requested'] else 'WALL_CAP',
                      complete=step == a.steps, steps_completed=step, readback_verified=True)
    except BaseException as exc:
        report.update(status='HOST_ERROR', complete=False, error_type=type(exc).__name__)
        raise
    finally:
        report['wall_s'] = time.monotonic() - started
        report['artifacts'] = {str(f.relative_to(a.output)): sha256(f) for f in a.output.rglob('*')
                               if f.is_file() and f.name != 'summary.json'}
        write_summary(a.output / 'summary.json', report)


if __name__ == '__main__':
    main()
