"""Evaluator-only matched-label comparison; never imported by a controller."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np


def compare(baseline, candidate):
    def read(path):
        return json.loads(path.read_text() if path.exists() else
                          subprocess.check_output(['zstd', '-dc', str(path)+'.zst']))

    def index(rows):
        result = defaultdict(list)
        for row in rows:
            result[(row['t'], row['target'], row['kind'])].append(row)
        return result

    def stats(values):
        return (dict(n=len(values), median=float(np.median(values)), p95=float(np.percentile(values, 95)))
                if values else dict(n=0, median=None, p95=None))

    baseline, candidate = Path(baseline), Path(candidate)
    old = index(read(baseline/'frame-errors.json'))
    new = index(read(candidate/'frame-errors.json'))
    shared = set(old) & set(new)
    unique = [key for key in sorted(shared) if len(old[key]) == len(new[key]) == 1]
    by_kind = {}
    for kind in sorted({key[2] for key in unique}):
        keys = [key for key in unique if key[2] == kind]
        before = [old[key][0]['error_m'] for key in keys]
        after = [new[key][0]['error_m'] for key in keys]
        by_kind[kind] = dict(baseline_m=stats(before), candidate_m=stats(after),
                             candidate_lower_n=sum(b > a for b, a in zip(before, after)))
    sources = [directory/name for directory in (baseline, candidate)
               for name in ('frame-errors.json', 'summary.json', 'prediction-seal.json')]
    return dict(status='OFFLINE_NOT_READY',
                baseline=read(baseline/'summary.json'), candidate=read(candidate/'summary.json'),
                pairing='exact (SIM timestamp, evaluator birth-label ID, kind), unique in both; ambiguous duplicates excluded',
                limitation='birth-label uses nearest same-appearance truth geometry; wrong labels/associations remain possible; this is not navigational reacquisition',
                matched_error_by_kind=by_kind,
                rejection_table=dict(unit='baseline_label_timestamp_keys', funnel=[
                    dict(stage='baseline_label_timestamp', input_n=len(old), cumulative_pass_n=len(old), rejected_n=0),
                    dict(stage='present_in_candidate', input_n=len(old), cumulative_pass_n=len(shared), rejected_n=len(old)-len(shared)),
                    dict(stage='unique_in_both', input_n=len(shared), cumulative_pass_n=len(unique), rejected_n=len(shared)-len(unique))],
                    reason_categories=dict(candidate_memory_absent=len(old)-len(shared), duplicate_label_memory=len(shared)-len(unique)),
                    blocked_object='not_observed', minimum_gap_m=None, gap_status='not_measured',
                    raw=[str(baseline),str(candidate)], reproduction=sys.argv),
                sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
                actual_reacquisition_trials=0, actual_reacquisition_rate=None,
                physical_success=False, student_success=False, llm_success=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ORIGINAL_ONLY')
    with args.output.open('x') as stream:
        json.dump(compare(args.baseline,args.candidate),stream,indent=2,allow_nan=False)
