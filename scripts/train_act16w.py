"""Finite gcp2 L4 ACT16 trainer using frozen ACT library, default-off changes.

Based on train_grasp_act.py at 3f99d58c. Upstream ACT, optimizer, batch8,
chunk8, 10Hz, completion loss and backbone are retained. Changes are serialized
train/inference history intervention and a separate TRAIN-only curriculum.
No simulation, teacher action execution, RGB rendering or model API is used.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256, training_admission
from act16w_input import MODES, Act16wActor, save_actor, transform_batch, contract_check
from act16w_curriculum import StartCurriculum


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('act-source', 'dataset', 'output', 'admission'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--stage', choices=('smoke', 'main'), required=True)
    p.add_argument('--steps', type=int, required=True)
    p.add_argument('--schedule-steps', type=int, default=10000,
                   help='fixed total curriculum schedule, identical in smoke and main')
    p.add_argument('--seed', type=int, default=20261015)
    p.add_argument('--max-wall-s', type=float, required=True, help='resource cap only; fixed steps define training')
    p.add_argument('--history-causal-split-v1', choices=MODES, default='off')
    p.add_argument('--curriculum-starts-v1', type=Path)
    p.add_argument('--resume', type=Path)
    p.add_argument('--smoke-summary', type=Path)
    a = p.parse_args()
    if not 0 < a.max_wall_s <= 8*3600 or not 1 <= a.steps <= a.schedule_steps <= 100000:
        p.error('finite <=8h resource cap and optimizer steps required')
    if a.stage == 'smoke' and (a.steps > 500 or a.max_wall_s > 1800 or a.resume):
        p.error('smoke: <=500 steps, <=1800s, fresh initialization')
    host = require_gcp2(training=True)  # Before torch, checkpoint or metadata inputs.
    source = frozen_source(ROOT)
    library = frozen_source(a.act_source, ACT_SHA)
    admission = training_admission(a.admission, source=source, dataset=a.dataset, act_source=library)
    sys.path.insert(0, str(a.act_source.resolve()))
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import GraspDataset, assert_tensor_keys
    from harness.grasp_act_policy import make_policy
    from harness.grasp_act_loss import completion_priors, policy_loss
    contract_check(c)
    configuration = {'source_sha': source, 'act_source_sha': library,
        'dataset_manifest_sha256': sha256(a.dataset / 'manifest.json'), 'seed': a.seed,
        'history_causal_split_v1': a.history_causal_split_v1,
        'curriculum_starts_sha256': sha256(a.curriculum_starts_v1) if a.curriculum_starts_v1 else None,
        'done_loss': 'balanced_bce_v1', 'batch_size': 8, 'chunk': 8, 'period_s': .1,
        'schedule_steps': a.schedule_steps}
    if a.stage == 'main':
        smoke = json.loads(a.smoke_summary.read_text()) if a.smoke_summary else {}
        if (smoke.get('stage') != 'smoke' or not smoke.get('complete') or not smoke.get('readback_verified')
                or any(smoke.get(k) != v for k, v in configuration.items()) or not a.resume
                or a.resume.resolve() != Path(smoke['last_checkpoint']).resolve()):
            raise ValueError('matching completed smoke and exact checkpoint required')
    a.output.mkdir(parents=True, exist_ok=False)
    report = {**configuration, 'status': 'running', 'complete': False, 'stage': a.stage, 'host': host,
        'steps_requested': a.steps, 'steps_completed': 0, 'readback_verified': False,
        'selection': 'fixed final optimizer step; no final evaluation checkpoint selection',
        'admission_sha256': sha256(a.admission), 'teacher_gate': {
            k: admission[k] for k in ('teacher_success_n', 'teacher_attempts_N')},
        'class': 'dev', 'research_result': False}
    write(a.output / 'summary.json', report)
    started, last_checkpoint, step = time.monotonic(), None, 0
    stop = {'requested': False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(requested=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(requested=True))
    try:
        import torch
        from harness.act_training import checkpoint_encoder
        if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):
            raise RuntimeError('CUDA NVIDIA L4 required')
        torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
        torch.set_num_threads(4); torch.backends.cudnn.benchmark = False
        data = GraspDataset(a.dataset, 'train')
        priors = completion_priors(data)
        curriculum = StartCurriculum(data, json.loads(a.curriculum_starts_v1.read_text())) if a.curriculum_starts_v1 else None
        policy = make_policy(pretrained=not bool(a.resume), device='cuda')
        optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
        generator = torch.Generator().manual_seed(a.seed)
        if a.resume:
            resume = json.loads((a.resume / 'resume.json').read_text())
            if any(resume.get(k) != v for k, v in configuration.items()):
                raise ValueError('resume provenance mismatch')
            if sha256(a.resume / 'optimizer.pt') != resume['optimizer_sha256']:
                raise ValueError('optimizer hash mismatch')
            restored = Act16wActor.load(a.resume / 'actor', device='cuda')
            policy.load_state_dict(restored.policy.state_dict(), strict=True)
            del restored
            state = torch.load(a.resume / 'optimizer.pt', map_location='cpu', weights_only=True)
            optimizer.load_state_dict(state['optimizer']); torch.set_rng_state(state['rng'])
            torch.cuda.set_rng_state_all(state['cuda_rng']); generator.set_state(state['sampler_rng'])
            step = resume['step']
        if step >= a.steps:
            raise ValueError('resume already reached requested steps')
        report.update(environment={k: importlib.metadata.version(k) for k in ('torch','torchvision','lerobot','numpy')},
                      gpu=torch.cuda.get_device_name(0), cuda=torch.version.cuda, training_rows=len(data),
                      done_class_counts=priors)
        initial_step = step
        def checkpoint():
            nonlocal last_checkpoint
            folder = a.output / f'step-{step:06d}'
            if folder == last_checkpoint:
                return
            folder.mkdir()
            save_actor(policy, folder / 'actor', data.stats, {**configuration, 'step': step},
                       mode=a.history_causal_split_v1)
            torch.save({'optimizer': optimizer.state_dict(), 'rng': torch.get_rng_state(),
                        'cuda_rng': torch.cuda.get_rng_state_all(), 'sampler_rng': generator.get_state()},
                       folder / 'optimizer.pt')
            write(folder / 'resume.json', {**configuration, 'step': step,
                                          'optimizer_sha256': sha256(folder / 'optimizer.pt')})
            last_checkpoint = folder; report['last_checkpoint'] = str(folder)
        with (a.output / 'progress.jsonl').open('x') as log:
            while step < a.steps:
                if stop['requested'] or time.monotonic()-started >= a.max_wall_s or (a.output/'SUPERVISOR_STOP.json').exists():
                    break
                eligible = curriculum.eligible(step/a.schedule_steps) if curriculum else None
                indices = torch.randint(len(eligible) if curriculum else len(data), (8,), generator=generator).tolist()
                if curriculum:
                    indices = eligible[indices].tolist()
                batch = torch.utils.data.default_collate([data[i] for i in indices])
                assert_tensor_keys(batch, training=True)
                batch = transform_batch({k: v.to('cuda') for k, v in batch.items()}, a.history_causal_split_v1)
                policy.train(); optimizer.zero_grad(set_to_none=True)
                with checkpoint_encoder(policy, enabled=True):
                    loss, metrics = policy_loss(policy, batch, mode='balanced_bce_v1', stats=data.stats, priors=priors)
                    if not torch.isfinite(loss):
                        raise ValueError('nonfinite loss')
                    loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
                optimizer.step(); step += 1
                if step == initial_step+1 or step % 10 == 0:
                    row = {'step': step, 'loss': loss.item(), **metrics, 'gradient_norm': float(norm),
                           'wall_s': time.monotonic()-started,
                           'eligible_rows': len(eligible) if curriculum else len(data)}
                    log.write(json.dumps(row, allow_nan=False)+'\n'); log.flush()
                    report.update(steps_completed=step, latest=row); write(a.output/'summary.json', report)
                if step % 5000 == 0:
                    checkpoint()
            checkpoint()
        restored = Act16wActor.load(last_checkpoint/'actor', device='cuda')
        probe = data[0]
        inputs = transform_batch({k: torch.from_numpy(v.copy()).unsqueeze(0).to('cuda')
                                  for k,v in probe.items() if k.startswith('observation.')}, a.history_causal_split_v1)
        assert_tensor_keys(inputs); policy.eval()
        with torch.inference_mode():
            if not torch.equal(policy.predict_action_chunk(inputs), restored.policy.predict_action_chunk(inputs)):
                raise ValueError('checkpoint prediction readback mismatch')
        report.update(status='complete' if step == a.steps else 'SUPERVISOR_STOP' if stop['requested'] else 'RESOURCE_CAP',
                      complete=step == a.steps, steps_completed=step, readback_verified=True,
                      peak_gpu_bytes=torch.cuda.max_memory_allocated(),
                      input_audit={'keys': sorted(inputs), 'teacher_input_fields': 0,
                                   'train_inference_same_transform': True})
    except BaseException as exc:
        report.update(status='HOST_ERROR', complete=False, error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['wall_s'] = time.monotonic()-started
        report['artifacts'] = {str(f.relative_to(a.output)):sha256(f) for f in a.output.rglob('*')
                               if f.is_file() and f.name != 'summary.json'}
        write(a.output/'summary.json', report)


if __name__ == '__main__':
    main()
