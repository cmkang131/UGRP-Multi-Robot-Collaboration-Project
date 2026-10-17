"""Default-off fp32/bf16 paired ACT precision probe on gcp5; probe artifact only.

Runs the registered R100 recipe (chunk100, batch8, seed20261017) for 2,000
sequential updates per arm on the same GPU. The bf16 arm wraps only the
forward/loss in torch.autocast('cuda', dtype=torch.bfloat16); weights,
optimizer state and gradient clipping stay fp32. This is a timing/quality
probe, not a research result, and it never feeds the 100k comparison.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import signal
import sys
import time
from urllib.request import Request, ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import sha256, LEROBOT_ACT_SHA256
from act17_data import library, read
from act17_compact_records import original_sha256
from act18_policy import CANDIDATES, ReferenceDataset, make_policy
from act18_diagnose import write

B = Path('/home/ugrp/ugrp-sim')
ROOT = Path(__file__).resolve().parents[1]
PROBE_STEPS = 2000
BATCH = 8
ARMS = ('fp32', 'bf16_autocast_v1')
GCP5 = {'project_id': 'ugrp-sim-e-1016', 'instance': 'ugrp-act-l4-gcp5',
        'machine_type': 'g2-standard-8'}


def require_gcp5():
    if platform.system() != 'Linux':
        raise RuntimeError('gcp5 L4 probe required; Mac training forbidden')
    base = 'http://169.254.169.254/computeMetadata/v1/'

    def meta(key):
        req = Request(base + key, headers={'Metadata-Flavor': 'Google'})
        with build_opener(ProxyHandler({})).open(req, timeout=3) as response:
            return response.read(4096).decode().strip()

    row = {k: meta(v).rsplit('/', 1)[-1] for k, v in {
        'project_id': 'project/project-id', 'instance': 'instance/name',
        'machine_type': 'instance/machine-type', 'zone': 'instance/zone'}.items()}
    if (row['project_id'] != GCP5['project_id'] or row['instance'] != GCP5['instance']
            or row['machine_type'] != GCP5['machine_type']
            or not row['zone'].startswith('asia-northeast3-')):
        raise ValueError(f'gcp5 L4 required, got {row}')
    return row


def val_loss(policy, val, selected, priors, *, precision, seed):
    import torch
    from torch.utils.data import default_collate
    from harness.grasp_act_loss import policy_loss
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    policy.eval()
    total, rows = 0.0, 0
    with torch.no_grad():
        for start in range(0, len(selected), BATCH):
            ids = selected[start:start + BATCH]
            batch = {k: v.to('cuda') for k, v in default_collate([val[i] for i in ids]).items()}
            with torch.autocast('cuda', dtype=torch.bfloat16, enabled=precision == 'bf16_autocast_v1'):
                loss, _ = policy_loss(policy, batch, mode='balanced_bce_v1',
                                      stats=val.stats, priors=priors)
            if not torch.isfinite(loss):
                raise ValueError('nonfinite validation loss')
            total += float(loss) * len(ids)
            rows += len(ids)
    return total / rows, rows


def run_arm(arm, data, protocol, priors, out, val, selected):
    import numpy as np
    import torch
    from torch.utils.data import default_collate
    from harness.grasp_act_loss import policy_loss
    seed = protocol['seed']
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.set_num_threads(2)
    generator = torch.Generator().manual_seed(seed)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    policy = make_policy(data.chunk, device='cuda', pretrained=True)
    optimizer = torch.optim.AdamW(policy.get_optim_params(), lr=1e-5, weight_decay=1e-4)
    times, losses, nan = [], [], 0
    started = time.monotonic()
    with (out / f'progress-{arm}.jsonl').open('x') as stream:
        for step in range(1, PROBE_STEPS + 1):
            t0 = time.monotonic()
            ids = data.sample(generator, BATCH, 'uniform_episode_v1')
            batch = {k: v.to('cuda') for k, v in default_collate([data[i] for i in ids]).items()}
            policy.train()
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda', dtype=torch.bfloat16, enabled=arm == 'bf16_autocast_v1'):
                loss, metrics = policy_loss(policy, batch, mode='balanced_bce_v1',
                                            stats=data.stats, priors=priors)
            finite = bool(torch.isfinite(loss))
            if finite:
                loss.backward()
                norm = torch.nn.utils.clip_grad_norm_(policy.parameters(), 1., error_if_nonfinite=True)
                optimizer.step()
            else:
                nan += 1
                norm = torch.tensor(float('nan'))
            elapsed = time.monotonic() - t0
            if step > 200:
                times.append(elapsed)
            losses.append(float(loss))
            if step == 1 or step % 50 == 0:
                stream.write(json.dumps(dict(step=step, loss=float(loss), elapsed_s=elapsed,
                                             **{k: float(v) for k, v in metrics.items()},
                                             gradient_norm=float(norm)))+'\n')
                stream.flush()
    peak = int(torch.cuda.max_memory_allocated())
    loss, rows = val_loss(policy, val, selected, priors, precision=arm, seed=protocol['seed'])
    result = dict(arm=arm, steps=PROBE_STEPS, nan_inf_steps=nan,
                  step_median_s=float(np.median(times)), step_p10_s=float(np.percentile(times, 10)),
                  step_p90_s=float(np.percentile(times, 90)),
                  wall_s=time.monotonic() - started, peak_gpu_bytes=peak,
                  loss_last200_mean=float(np.mean(losses[-200:])),
                  loss_last200_min=float(np.min(losses[-200:])), val_loss=loss, val_rows=rows,
                  gpu=torch.cuda.get_device_name(0))
    del policy, optimizer
    torch.cuda.empty_cache()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for name in ('dataset', 'protocol', 'queue', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--candidate', choices=('R100',), default='R100')
    a = p.parse_args()
    if not a.enabled:
        p.error('bf16 probe is default OFF')
    host = require_gcp5()
    library()
    source = None
    try:
        import subprocess
        source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        source = None
    protocol, queue = read(a.protocol), read(a.queue)
    if (protocol.get('schema') != 'ugrp.act18.protocol.v1' or protocol['steps'] != 100000
            or protocol['batch_size'] != BATCH or a.candidate not in queue['candidates']):
        raise ValueError('fixed registered matched queue required')
    data = ReferenceDataset(a.dataset, 'train', chunk=CANDIDATES[a.candidate])
    if (set(data.manifest['eligible_train_seeds']) != set(protocol['train_seeds'])
            or original_sha256(a.dataset / 'manifest.json') != queue['dataset_manifest_sha256']):
        raise ValueError('same complete v7 TRAIN dataset required')
    import torch
    from lerobot.policies.act import modeling_act
    if sha256(Path(modeling_act.__file__)) != LEROBOT_ACT_SHA256:
        raise ValueError('pinned valid-token normalized upstream required')
    if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):
        raise ValueError('L4 required')
    val = ReferenceDataset(a.dataset, 'validation', chunk=CANDIDATES[a.candidate])
    val8 = set(protocol['validation8_seeds'])
    val_eps = [ep for ep in val.manifest['episodes'] if ep['split'] == 'validation']
    if len(val_eps) != len(val.episode_indices):
        raise ValueError('validation episode alignment changed')
    selected = [int(i) for j, ep in enumerate(val_eps) if ep['seed'] in val8
                for i in val.episode_indices[j]]
    if not selected:
        raise ValueError('VAL8 rows required')
    missing = [row['path'] for shard in (data.shards + val.shards) for row in shard['frames']
               if not Path(row['path']).is_file()]
    if missing:
        raise ValueError(f'{len(missing)} dataset images missing, e.g. {missing[0]}')
    priors = data.completion_priors('uniform_episode_v1')
    a.out.mkdir(parents=True, exist_ok=False)
    lease = B / 'leases' / 'act18-bf16-probe.json'
    report = dict(schema='ugrp.act18.bf16_probe.v1', probe=True, research_result=False,
                  host=host, source_sha=source, candidate=a.candidate,
                  dataset_manifest_sha256=queue['dataset_manifest_sha256'],
                  protocol_sha256=sha256(a.protocol), lerobot_act_sha256=LEROBOT_ACT_SHA256,
                  torch=torch.__version__, cuda=torch.version.cuda,
                  val_seeds=sorted(val8), val_rows=len(selected),
                  arms=[], status='running', complete=False,
                  started_utc=datetime.now(timezone.utc).isoformat(), wall_cap=None,
                  default_off=True, pooled_with_research=False,
                  note='probe artifact only; not used for candidate selection or research results')
    with lease.open('x') as f:
        json.dump(dict(task='act18', probe='bf16', pid=os.getpid(),
                       started=report['started_utc'], host=host,
                       expected_end='2x2000 steps; no wall deadline', concurrency=0), f)
    stop = {'requested': False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(requested=True))
    try:
        for arm in ARMS:
            if stop['requested']:
                raise InterruptedError('explicit supervisor stop')
            result = run_arm(arm, data, protocol, priors, a.out, val, selected)
            report['arms'].append(result)
            write(a.out / 'bf16-probe.json', report)
        report.update(status='complete', complete=True)
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error, InterruptedError) else 'HOST_ERROR',
                      error=repr(error), complete=False)
        raise
    finally:
        write(a.out / 'bf16-probe.json', report)
        if lease.exists() and read(lease).get('pid') == os.getpid():
            lease.unlink()


if __name__ == '__main__':
    main()
