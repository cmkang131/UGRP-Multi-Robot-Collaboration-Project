"""Read GCP2-only evidence availability and compare saved GCP1 fingerprints.

Never connect to GCP1. Original dataset filenames follow the committed converter
layout, not a recovered original manifest. Pixel fingerprints are available only
at ACT15's saved review slots; they do not certify the missing full trajectory.
"""
import argparse
from pathlib import Path

from harness.grasp_act_data import read_json, sha256, write_json
from scripts.analyze_grasp_act_act16a import require_cpu


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--batch',type=Path,help='reconciled batch with retry paths')
    a=p.parse_args();host=require_cpu();a.output.mkdir(exist_ok=False,parents=True)
    original=Path('/home/ugrp/ugrp-sim/act15-1535c8a3/dataset')
    files=[original/'manifest.json',original/'normalization.json']
    for seed in [*range(86820,86870),*range(87020,87040)]:
        files.extend(original/f'{seed}-r1'/name for name in ('images.npy','tensors.npz','samples.json','rgb-provenance.json'))
    raw_fields=('summary.json','student-inputs.jsonl','commands.jsonl','chunk-predictions.jsonl','eval-only.jsonl','rgb/r1/*.jpg')
    summary=read_json(a.source/'experiments/2026-10-15-act-train/act15-summary.json')
    missing_eval=[dict(run=r['run'],raw=r['raw'],required_files_or_patterns=list(raw_fields),
        actual_original_directory_present_on_gcp2=Path(r['raw']).exists()) for r in summary['primary_runs']]
    write_json(a.output/'missing-data.json',dict(host=host,gcp1_accessed=False,
        original_dataset=dict(root=str(original),manifest_sha256=summary['dataset']['manifest_sha256'],
            required_files=282,inventory_basis='70 episodes x4 converter files plus manifest and normalization; original manifest not recovered',
            files=[dict(path=str(f),present_on_gcp2=f.exists()) for f in files],
            optional_metadata=str(original/'RUN_META.json'),
            train_mean_available='Release actor/adapter.json contains TRAIN normalization; original normalization file unavailable'),
        original_evaluation_raw=missing_eval,
        status='GCP1-only original raw/dataset remain unavailable and prohibited; GCP2 outputs are new provenance',
        retrieval_policy='Mac receives summary/montage/failure frames only; full raw remains GCP2, no complete independent backup'))
    review=read_json(a.source/'experiments/2026-10-15-act-train/act15-frame-review.json')
    raw_paths={r['seed']:Path(r['raw']) for r in read_json(a.batch/'batch-summary.json')['results']} if a.batch else {}
    comparisons=[]
    for record in review['runs']:
        seed=int(record['run'].split('-')[2])
        raw=raw_paths.get(seed,Path(f'/home/ugrp/ugrp-sim/runs/act16a-gcp2-{seed}-b4db8ba2/raw'))
        for frame in record['frames']:
            f=raw/'rgb/r1'/Path(frame['source']).name
            comparisons.append(dict(seed=seed,t=frame['t'],original_sha256=frame['sha256'],
                regenerated_path=str(f),present=f.exists(),
                regenerated_sha256=sha256(f) if f.exists() else None,
                same=sha256(f)==frame['sha256'] if f.exists() else None))
    write_json(a.output/'reproduction-fingerprints.json',dict(host=host,original_slots=240,
        present=sum(r['present'] for r in comparisons),matching=sum(r['same'] is True for r in comparisons),
        differing=sum(r['same'] is False for r in comparisons),comparisons=comparisons,
        scope='Six saved image fingerprints per run only. Original full commands/evaluation bytes cannot be checked; cohorts never pooled.'))


if __name__=='__main__':main()
