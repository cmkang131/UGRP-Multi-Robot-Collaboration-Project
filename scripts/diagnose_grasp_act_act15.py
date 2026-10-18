"""Offline ACT error by teacher phase, at zero latent and actual deployment decode.

Run on gcp1 beside immutable ACT12/14 originals. No rollout or optimizer.
Continuous errors are reported in physical command units; no acceptance
threshold is invented. Horizon zero and the full valid chunk are kept separate.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import time

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import GraspDataset, INPUT_KEYS, read_rows, sha256, write_json


def command_errors(prediction, target):
    p, y = c.decode_action(prediction), c.decode_action(target)
    return {
        'wheel_mae': float(np.abs(np.array(p['wheels'])-y['wheels']).mean()),
        'wheel_sign_mismatch': float((np.sign(p['wheels']) != np.sign(y['wheels'])).mean()),
        'pulse_mae_ms': float(np.abs(np.array(p['duration_s'])-y['duration_s']).mean()*1000),
        'pwm_mae': float(np.abs(np.array(list(p['pwm'].values()))-list(y['pwm'].values())).mean()),
        'pan_abs_error': abs(p['pwm']['6']-y['pwm']['6']),
        'done_mismatch': int(p['done'] != y['done']),
    }


def distribution(rows):
    return {'n': len(rows), **{k: {'mean': float(np.mean([r[k] for r in rows])),
        'p50': float(np.quantile([r[k] for r in rows], .5)),
        'p95': float(np.quantile([r[k] for r in rows], .95)),
        'max': float(max(r[k] for r in rows))} for k in rows[0]}} if rows else {'n': 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'models', 'output'): p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--arms', nargs='+', default=['p0', 'p02'])
    p.add_argument('--splits', nargs='+', default=['validation'])
    p.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    a = p.parse_args()
    from scripts.grasp_act_training_guard import require_gcp, source_sha
    host, source = require_gcp(training=a.device == 'cuda'), source_sha()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'source_sha': source, 'host': host, 'status': 'running', 'complete': False,
              'dataset_manifest_sha256': sha256(a.dataset/'manifest.json'), 'arms': {},
              'estimator': __doc__, 'optimizer_steps': 0, 'physical_runs': 0}
    write_json(a.output/'summary.json', report)
    import torch
    from harness.grasp_act_policy import GraspActor
    torch.set_num_threads(1 if a.device == 'cpu' else 4)
    begin = time.monotonic()
    try:
        for arm in a.arms:
            model = a.models/arm/'step-010000/actor'
            actor = GraspActor.load(model, device=a.device)
            report['arms'][arm] = {'model_sha256': sha256(model/'model.safetensors'), 'splits': {}}
            for split in a.splits:
                data = GraspDataset(a.dataset, split)
                if data.stats != actor.stats: raise ValueError('normalization mismatch')
                summaries, offset = [], 0
                total = defaultdict(list)
                with (a.output/f'{arm}-{split}-rows.jsonl').open('x') as stream:
                    for episode in (e for e in data.manifest['episodes'] if e['split'] == split):
                        folder = a.dataset/episode['path']
                        samples = json.loads((folder/'samples.json').read_text())
                        raw = Path(episode['source_root'])/'raw'
                        label_file = next(raw.glob('teacher-'+episode['robot_id']+'.jsonl*'))
                        labels = {r['sample_id']: r for r in read_rows(label_file)}
                        terms = defaultdict(list)
                        predictions = []
                        for start in range(0, len(samples), 8):
                            batch = torch.utils.data.default_collate([data[offset+i] for i in range(start, min(start+8,len(samples)))])
                            with torch.inference_mode():
                                pred = actor.policy.predict_action_chunk({k:batch[k].to(a.device) for k in INPUT_KEYS}).cpu().numpy()
                            pred = actor.decode_predictions(pred)
                            targets = batch['action'].numpy()*np.asarray(actor.stats['action_std'])+np.asarray(actor.stats['action_mean'])
                            valid = ~batch['action_is_pad'].numpy()
                            for j in range(len(pred)):
                                sample = samples[start+j]; label = labels[sample['sample_id']]
                                phase = label['teacher_phase']
                                errors = command_errors(pred[j,0],targets[j,0])
                                row = {**sample, 'phase': phase, 'prediction':pred[j,0].tolist(),
                                       'target':targets[j,0].tolist(), 'errors':errors}
                                stream.write(json.dumps(row,allow_nan=False)+'\n')
                                terms[phase].append(errors); total[phase].append(errors)
                                for h in np.flatnonzero(valid[j]):
                                    key = phase+'__h'+str(h)
                                    error_h = command_errors(pred[j,h],targets[j,h])
                                    terms[key].append(error_h); total[key].append(error_h)
                            predictions.append(pred)
                        np.savez_compressed(a.output/f'{arm}-{episode["seed"]}-predictions.npz',prediction=np.concatenate(predictions))
                        summaries.append({'seed':episode['seed'],'phases':{k:distribution(v) for k,v in terms.items()},
                                          'label_path':str(label_file),'label_sha256':sha256(label_file)})
                        offset += len(samples)
                        write_json(a.output/'progress.json',{'arm':arm,'split':split,'rows':offset})
                report['arms'][arm]['splits'][split] = {'episodes':summaries,'phases':{k:distribution(v) for k,v in total.items()}}
                write_json(a.output/'summary.json',report)
        report.update(status='complete',complete=True)
    except BaseException as exc:
        report.update(status='HOST_ERROR',error=str(exc));raise
    finally:
        report['wall_s'] = time.monotonic()-begin
        report['files']={str(f.relative_to(a.output)):sha256(f) for f in a.output.iterdir() if f.is_file() and f.name!='summary.json'}
        write_json(a.output/'summary.json',report)


if __name__ == '__main__': main()
