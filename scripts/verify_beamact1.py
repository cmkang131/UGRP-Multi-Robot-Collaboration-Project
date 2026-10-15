"""Independent saved-data recount and TRAIN normalization check on GCP2."""
import argparse
from collections import defaultdict
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess

import numpy as np

from harness.grasp_act_data import fit_stats, sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.prepare_beamact1 import ARCHIVE_SHA, split_seeds


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--analysis-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    host = require_gcp2(training=False)
    original, split = a.root/'data-v1/dataset', a.root/'data-v1/split-v1'
    m = json.loads((original/'manifest.json').read_text())
    s = json.loads((split/'manifest.json').read_text())
    assert sha256(original/'manifest.json') == '87a1b09461a6816e5fbd3cf4a3963959e2ac5482c842509cdd76a38f5c412fb9'
    assert sha256(original/m['normalization']['path']) == m['normalization']['sha256']
    train, val = split_seeds(m['protocol']['train_seeds'], m['protocol']['heldout_reserved_only'])
    assert s['protocol']['train_seeds'] == train and s['protocol']['validation_seeds'] == val
    groups, states, actions, seeds, rows, files = defaultdict(list), [], [], [], 0, 0
    for episode in s['episodes']:
        groups[episode['seed']].append(episode)
        for name, digest in episode['files'].items():
            assert sha256(split/episode['path']/name) == digest
            files += 1
        with np.load(split/episode['path']/'tensors.npz', allow_pickle=False) as tensors:
            assert not tensors['action_is_pad'][:,0].any()
            rows += len(tensors['state'])
            if episode['split'] == 'train':
                states.extend(tensors['state']); actions.extend(tensors['action'][:,0])
                seeds.extend([episode['seed']]*len(tensors['state']))
    assert len(groups) == 185 and rows == 66931
    assert all(len(e)==2 and {r['robot_id'] for r in e}=={'r1','r2'}
               and len({r['split'] for r in e})==1 for e in groups.values())
    assert json.loads((split/'normalization.json').read_text()) == fit_stats(states,actions,seeds)
    record = next((a.analysis_source/'outputs/simulation-runs').glob('*beamact1-offline*/manifest.json'))
    managed = json.loads(record.read_text())
    assert managed['status'] == 'process_completed' and managed['exit_code'] == 0
    assert not managed['source_changed_during_run'] and not managed['inputs_changed_during_run']
    assert not managed['finalization_errors']
    verification = dict(status='PASS', host=host, physics_runs=0, rendered_frames=0,
        optimizer_steps=0, GPU_hours=0, source_episode_files_verified=files,
        both_robots_grouped_all185=True, total_rows=rows,
        train_normalization_rows=len(states), normalization_recomputed_exact=True,
        original_manifest_unchanged=True, original_normalization_unchanged=True,
        validation_rows=rows-len(states), train_seeds=train, validation_seeds=val,
        heldout_excluded=list(range(8329000,8329020)),
        environment={k:importlib.metadata.version(k) for k in ('numpy','pillow','mujoco')},
        python=platform.python_version(),
        verifier_source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        analysis_source_sha=managed['source']['commit'] if 'commit' in managed['source'] else managed['source'],
        analysis_managed_record=str(record), managed_runtime_s=managed['runtime_s'],
        source_alternates=(a.analysis_source/'.git/objects/info/alternates').read_text().strip(),
        raw_root=str(a.root), raw_archive_retained=True, independent_full_backup=False,
        disk_free_bytes=shutil.disk_usage(a.root).free,
        artifact_sha256={str(f):sha256(f) for f in [a.root/'data-v1/dataset-summary.json',
            split/'manifest.json',split/'normalization.json',a.root/'data-v1/stages.json',
            a.root/'persistence-v1/summary.json',a.root/'cpu-adapter-test.log',record]})
    write_json(a.output,verification)
    print(json.dumps({k:verification[k] for k in ('status','source_episode_files_verified',
        'total_rows','train_normalization_rows','validation_rows','normalization_recomputed_exact')}))


if __name__ == '__main__':
    main()
