"""Fixed-checkpoint deterministic train/validation action loss, no optimizer.

Deployment uses the ACT zero latent, eval dropout and complete fixed splits.
This excludes the training-only VAE KL and command-history augmentation. Compare
train and validation under this identical estimator, keeping logged training
total (with KL/dropout) separate. Balanced BCE retains TRAIN class priors.
"""
import argparse
import json
from pathlib import Path
import time

from harness.grasp_act_data import GraspDataset, INPUT_KEYS, sha256, write_json
from scripts.grasp_act_training_guard import require_gcp, source_sha


def batch_terms(prediction, batch, stats, priors):
    import torch
    import torch.nn.functional as F
    from harness import grasp_act_contract as c
    valid = ~batch['action_is_pad']
    target = batch['action']
    movement = (prediction[..., :-1] - target[..., :-1]).abs()[valid].sum()
    done = (target[..., -1] * stats['action_std'][-1] + stats['action_mean'][-1]).round().clamp(0, 1)
    task = batch['observation.state'][:, c.HISTORY * 14:c.HISTORY * 14 + len(c.SKILLS)]
    prior = done.new_tensor([priors[c.SKILLS[i]]['positive_fraction'] for i in task.argmax(-1).tolist()])[:, None]
    weights = torch.where(done.bool(), .5 / prior, .5 / (1-prior))
    bce = F.binary_cross_entropy_with_logits(prediction[..., -1], done, reduction='none') * weights
    return {'movement_sum': movement.item(), 'done_sum': bce[valid].sum().item(),
            'valid_actions': int(valid.sum()), 'rows': len(prediction)}


def summarize_terms(parts):
    from harness import grasp_act_contract as c
    n = sum(p['valid_actions'] for p in parts)
    movement = sum(p['movement_sum'] for p in parts) / n / c.ACTION_DIM
    done = sum(p['done_sum'] for p in parts) / n
    return {'rows': sum(p['rows'] for p in parts), 'valid_actions': n,
            'movement_l1': movement, 'balanced_done_bce': done, 'action_loss': movement + done}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'models', 'output'): p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--device', choices=('cpu','cuda'), default='cuda')
    a = p.parse_args()
    host, source = require_gcp(training=a.device=='cuda'), source_sha()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'complete': False, 'source_sha': source, 'host': host,
              'manifest_sha256': sha256(a.dataset/'manifest.json'), 'arms': {},
              'estimator': __doc__, 'physical_runs': 0, 'optimizer_steps': 0}
    write_json(a.output/'summary.json', report)
    begin = time.monotonic()
    try:
        import torch
        from harness.grasp_act_policy import GraspActor
        torch.set_num_threads(4 if a.device=='cuda' else 1)
        for arm in ('p0','p02'):
            root = a.models/arm/'step-010000/actor'
            actor = GraspActor.load(root, device=a.device)
            meta = json.loads((root/'adapter.json').read_text())
            if meta['provenance']['dataset_manifest_sha256'] != report['manifest_sha256']:
                raise ValueError('wrong dataset')
            if actor.done_mode != 'balanced_bce_v1': raise ValueError('ACT13 BCE checkpoint required')
            result = {'model_sha256': sha256(root/'model.safetensors'), 'splits': {}}
            report['arms'][arm] = result
            for split in ('validation','train'):
                data = GraspDataset(a.dataset, split, blank=actor.blank)
                if data.stats != actor.stats: raise ValueError('normalization mismatch')
                episodes, offset, all_terms = [], 0, []
                for e in (e for e in data.manifest['episodes'] if e['split']==split):
                    terms = []
                    for start in range(0,e['rows_selected'],8):
                        batch = torch.utils.data.default_collate([data[offset+i] for i in range(start,min(start+8,e['rows_selected']))])
                        batch = {k:v.to(a.device) for k,v in batch.items()}
                        with torch.inference_mode():
                            prediction = actor.policy.predict_action_chunk({k:batch[k] for k in INPUT_KEYS})
                            if not torch.isfinite(prediction).all(): raise ValueError('nonfinite prediction')
                            terms.append(batch_terms(prediction,batch,actor.stats,meta['provenance']['done_class_counts']))
                    offset += e['rows_selected']; all_terms += terms
                    episodes.append({'seed': e['seed'], **summarize_terms(terms)})
                    write_json(a.output/'progress.json', {'arm':arm,'split':split,'episodes':len(episodes),'rows':offset})
                result['splits'][split] = {**summarize_terms(all_terms),'episodes':episodes}
                write_json(a.output/'summary.json', report)
            result['validation_train_ratio'] = result['splits']['validation']['action_loss']/result['splits']['train']['action_loss']
            del actor
        report.update(status='complete',complete=True)
    except BaseException as exc:
        report.update(status='HOST_ERROR',error_type=type(exc).__name__,error=str(exc));raise
    finally:
        report['wall_s'] = time.monotonic()-begin
        write_json(a.output/'summary.json',report)


if __name__=='__main__':main()
