"""Full held-out input interventions on GCP; offline inference only, no physics."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import GraspDataset, INPUT_KEYS, sha256, write_summary
from scripts.analyze_grasp_act_memory import VARIANTS, change_metrics, intervene
from scripts.analyze_grasp_act_predictions import metrics
from scripts.grasp_act_training_guard import require_gcp, source_sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'model', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    host, source = require_gcp(training=True), source_sha()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'ugrp.grasp_act.memory_heldout.v1', 'status': 'running', 'complete': False,
        'source_sha': source, 'host': host, 'physical_runs': 0, 'training_runs': 0,
        'dataset_manifest_sha256': sha256(a.dataset/'manifest.json'),
        'model_sha256': sha256(a.model/'model.safetensors'), 'episodes': []}
    write_summary(a.output/'summary.json', report)
    try:
        import torch
        from harness.grasp_act_policy import GraspActor
        actor = GraspActor.load(a.model, device='cuda')
        data = GraspDataset(a.dataset, 'validation', blank=actor.blank)
        meta = json.loads((a.model/'adapter.json').read_text())
        if (actor.stats != data.stats or meta['provenance']['dataset_manifest_sha256'] !=
                report['dataset_manifest_sha256'] or actor.blank):
            raise ValueError('requires matching nonblank baseline and dataset')
        offset = batches = 0
        # Compress directly; permanent raw predictions remain lossless.
        archive = a.output/'predictions.jsonl.zst'
        with subprocess.Popen(['zstd', '-q', '-c'], stdin=subprocess.PIPE,
                              stdout=archive.open('xb')) as compressor:
            try:
                for episode in (e for e in data.manifest['episodes'] if e['split'] == 'validation'):
                    metadata = json.loads((a.dataset/episode['path']/'samples.json').read_text())
                    preds = {v: [] for v in VARIANTS}; targets = []; pads = []
                    for start in range(0, episode['rows_selected'], 8):
                        count = min(8, episode['rows_selected']-start)
                        items = [data[offset+start+i] for i in range(count)]
                        inputs = [{k: item[k] for k in INPUT_KEYS} for item in items]
                        local = {}
                        for variant in VARIANTS:
                            batch = torch.utils.data.default_collate([intervene(b, variant, actor.stats) for b in inputs])
                            with torch.inference_mode():
                                value = actor.policy.predict_action_chunk({k: v.to('cuda') for k, v in batch.items()})
                            local[variant] = actor.decode_predictions(value.cpu().numpy())
                            preds[variant].extend(local[variant]); batches += 1
                        for i, item in enumerate(items):
                            target = item['action']*np.array(actor.stats['action_std'])+np.array(actor.stats['action_mean'])
                            targets.append(target); pads.append(item['action_is_pad'])
                            compressor.stdin.write((json.dumps({'sample_id': metadata[start+i]['sample_id'],
                                'prediction': {v: local[v][i].tolist() for v in VARIANTS},
                                'target': target.tolist(), 'action_is_pad': pads[-1].tolist()}, allow_nan=False)+'\n').encode())
                    targets, pads = np.asarray(targets), np.asarray(pads)
                    preds = {v: np.asarray(x) for v, x in preds.items()}
                    by_skill = {}
                    for skill in sorted({m['skill'] for m in metadata}):
                        selected = np.array([m['skill'] == skill for m in metadata])
                        by_skill[skill] = {v: {
                            'first_action_error': metrics(x[selected, :1], targets[selected, :1], pads[selected, :1]),
                            'first_action_change': change_metrics(x[selected, 0], preds['baseline'][selected, 0]),
                            'all_valid_horizons_change': change_metrics(x[selected][~pads[selected]],
                                preds['baseline'][selected][~pads[selected]])} for v, x in preds.items()}
                    report['episodes'].append({'seed': episode['seed'], 'rows': len(metadata), 'by_skill': by_skill})
                    offset += episode['rows_selected']
            finally:
                compressor.stdin.close()
            if compressor.wait() != 0:
                raise RuntimeError('prediction compression failed')
        subprocess.run(['zstd', '-tq', str(archive)], check=True)
        if offset != len(data):
            raise ValueError('heldout row coverage mismatch')
        report.update(status='complete', complete=True, unique_rows=offset, inference_batches=batches,
            predictions_sha256=sha256(archive), prediction_encoding='lossless zstd JSONL')
    except BaseException as exc:
        report.update(status='HOST_ERROR', error_type=type(exc).__name__)
        raise
    finally:
        write_summary(a.output/'summary.json', report)


if __name__ == '__main__':
    main()
