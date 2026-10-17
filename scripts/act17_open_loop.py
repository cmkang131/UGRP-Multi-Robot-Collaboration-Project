"""Saved-checkpoint action audit on gcp2 L4; no training, physics or rendering.

Report h0 before/after the EXISTING actuator projection separately. All horizons
are also recorded, but a horizon crossing a phase boundary is not relabelled as
the current phase. No acceptance threshold or student input is introduced.
"""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/home/ugrp/ugrp-sim')
ACT_SHA = '3f99d58c5ada0862e669ef4065c0ba957f1b4547'


def read(path, *, lines=False):
    path = Path(path)
    if not path.exists():
        path = Path(str(path) + '.zst')
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)


def phase_group(label):
    if label['skill'] == 'release':
        return 'release'
    phase = label['teacher_phase']
    if phase in ('start', 'fold'):
        return 'setup'
    if phase == 'approach':
        return 'approach'
    if phase in ('align', 'relook', 'ready'):
        return 'alignment'
    return 'grasp'


def quantiles(values):
    values = np.asarray(values, dtype=float)
    if not values.size:
        return dict(n=0, median=None, p90=None)
    return dict(n=int(values.size), median=float(np.median(values)), p90=float(np.percentile(values, 90)))


def action_errors(pred, truth):
    """Encoded command units, NOT measured wheel/robot motion."""
    e = np.abs(np.asarray(pred) - np.asarray(truth))
    return dict(wheel_full_scale=e[..., :4].reshape(-1),
                pulse_ms=(150 * e[..., 4:8]).reshape(-1),
                servo_PWM_counts=(1000 * e[..., 8:13]).reshape(-1),
                gripper_PWM_counts=(1000 * e[..., 8]).reshape(-1))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--arms', nargs='+', default=['A', 'B', 'C', 'D1'])
    a = p.parse_args()
    from act16w_runtime import require_gcp2, frozen_source, sha256
    host = require_gcp2(training=True)
    source = frozen_source(ROOT)
    library = BASE/'src'/ACT_SHA
    frozen_source(library, ACT_SHA)
    sys.path.insert(0, str(library))
    import torch
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import GraspDataset
    from harness.grasp_act_loss import completion_priors, policy_loss
    from act16w_input import Act16wActor, transform_batch
    torch.set_num_threads(4)
    a.out.mkdir(parents=True, exist_ok=False)
    lease = BASE/'leases/act17.json'
    lease_row = read(lease)
    lease_row.update(pid=__import__('os').getpid(), active='open_loop_saved_checkpoint_audit')
    lease.write_text(json.dumps(lease_row))
    dataset = BASE/'runs/act16w-native-dataset-r1/records/dataset'
    manifest = read(dataset/'manifest.json')
    episodes = manifest['episodes']
    datasets = {split: GraspDataset(dataset, split) for split in ('train', 'validation')}
    priors = completion_priors(datasets['train'])
    report = dict(schema='ugrp.act17.open_loop.v1', source_sha=source, host=host,
                  started_utc=datetime.now(timezone.utc).isoformat(), status='running',
                  dataset_manifest_sha256=sha256(dataset/'manifest.json'), rows={},
                  units={'wheel_full_scale':'issued wheel fraction of full scale, dimensionless',
                         'pulse_ms':'issued pulse milliseconds', 'servo_PWM_counts':'servo PWM counts; not measured angle',
                         'gripper_PWM_counts':'gripper PWM counts'}, arms={},
                  physics_steps=0, training_steps=0, rendered_frames=0,
                  scope='offline expert-state predictions; never task success')
    # Metadata is used for report stratification only; it is never in the batch.
    metadata = {}
    raw = {}
    for split, data in datasets.items():
        metadata[split] = []
        for ep in [ep for ep in episodes if ep['split'] == split]:
            labels_path = Path(ep['source_root'])/'raw/teacher-r1.jsonl'
            labels = {row['sample_id']: row for row in read(labels_path, lines=True)}
            samples_path = dataset/ep['path']/'samples.json'
            metadata[split].extend(dict(seed=ep['seed'], **sample,
                teacher_phase=labels[sample['sample_id']]['teacher_phase'],
                stage=phase_group(labels[sample['sample_id']])) for sample in read(samples_path))
            for path in (labels_path, samples_path):
                actual = path if path.exists() else Path(str(path)+'.zst')
                raw[str(actual)] = sha256(actual)
        assert len(metadata[split]) == len(data)
        report['rows'][split] = len(data)
    started = time.monotonic()
    for arm in a.arms:
        checkpoint = BASE/f'runs/act16w-native-training-r1/{arm}/main/step-010000/actor'
        actor = Act16wActor.load(checkpoint, device='cuda')
        result = dict(checkpoint=str(checkpoint), checkpoint_sha256=sha256(checkpoint/'model.safetensors'),
                      history_mode=actor.mode, splits={})
        for split, data in datasets.items():
            groups = defaultdict(lambda: defaultdict(list))
            loss_sums = defaultdict(float)
            transitions = 0
            from gzip import open as gzopen
            with gzopen(a.out/f'{arm}-{split}-frames.jsonl.gz', 'xt') as stream:
                for offset in range(0, len(data), 8):
                    ids = list(range(offset, min(offset+8, len(data))))
                    batch = torch.utils.data.default_collate([data[i] for i in ids])
                    batch = transform_batch({k:v.to('cuda') for k,v in batch.items()}, actor.mode)
                    inputs = {k:v for k,v in batch.items() if k.startswith('observation.')}
                    actor.policy.eval()
                    # CVAE posterior loss is separate from prior-z=0 deployment error.
                    torch.manual_seed(20261017+offset)
                    with torch.inference_mode():
                        prediction = actor.policy.predict_action_chunk(inputs).cpu().numpy()
                        loss, metrics = policy_loss(actor.policy, batch, mode='balanced_bce_v1',
                                                   stats=data.stats, priors=priors)
                    for key,value in {'total_loss':float(loss), **metrics}.items():
                        loss_sums[key] += float(value)*len(ids)
                    prediction = actor.base.decode_predictions(prediction.reshape(-1,14)).reshape(len(ids),8,14)
                    for pred,index in zip(prediction,ids):
                        shard,row = data.index[index]
                        truth = data.shards[shard]['action'][row]
                        valid = ~data.shards[shard]['action_is_pad'][row]
                        previous = data.shards[shard]['state'][row,15*14:16*14-1]
                        meta = metadata[split][index]
                        decoded = c.decode_action(pred[0])
                        decoded = np.asarray(c.encode_action(dict(t=meta['t'], **{k:decoded[k] for k in ('wheels','duration_s','pwm')}), done=decoded['done']))
                        transition = bool(np.any(truth[0,:4] != previous[:4]))
                        transitions += int(transition)
                        stages = ['all', meta['stage'], 'phase:'+meta['teacher_phase']]
                        if transition:
                            stages += ['wheel_transition']
                        for group in stages:
                            for name, p_, target in [('h0_raw',pred[0],truth[0]),('h0_projected',decoded,truth[0]),
                                                      ('persistence',previous,truth[0,:13]),('valid_chunk',pred[valid],truth[valid])]:
                                for unit,values in action_errors(p_,target).items():
                                    groups[group][name+':'+unit].extend(values.tolist())
                            groups[group]['rows'].append(1)
                            groups[group]['teacher_moving'].append(int(np.any(truth[0,:4])))
                            groups[group]['student_projected_moving'].append(int(np.any(decoded[:4])))
                        stream.write(json.dumps(dict(**meta, prediction_h0_encoded=pred[0].tolist(),
                            projected_h0_encoded=decoded.tolist(), teacher_h0_encoded=truth[0].tolist(),
                            valid_horizons=int(valid.sum()),wheel_transition=transition))+'\n')
            result['splits'][split] = dict(rows=len(data), transition_rows=transitions,
                posterior_loss_sample_weighted={k:v/len(data) for k,v in loss_sums.items()},
                stages={stage:dict(rows=len(values['rows']),teacher_moving=sum(values['teacher_moving']),
                    student_projected_moving=sum(values['student_projected_moving']),
                    errors={k:quantiles(v) for k,v in values.items() if ':' in k}) for stage,values in groups.items()})
            report['arms'][arm] = result
            report['wall_s'] = time.monotonic()-started
            (a.out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
        del actor
        torch.cuda.empty_cache()
    report.update(status='complete', complete=True, wall_s=time.monotonic()-started,
                  raw=[dict(path=k,sha256=v) for k,v in raw.items()], reproduce=sys.argv)
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],rows=report['rows'],wall_s=report['wall_s'])))


if __name__ == '__main__':
    main()
