#!/usr/bin/env python3
"""Verify consumer expectations against ONLY the 11 public producer outputs.

Consumer-field projections are reproducible CI fixtures, not replacement raw.
The approved expected classifications are fixed independently of the consumer.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3c4fe30e-claude-20260930')
AUDIT = HERE / 'review_299c_validation/recorder_audit.json'
SPEC = importlib.util.spec_from_file_location('contract_classifier', HERE / 'classify_placements.py')
cp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp)


def pick(value, keys):
    return {k: value[k] for k in keys.split() if k in value}


def project(row, result, trace, case):
    """Only omit fields the consumer never reads; no rounding or new fields."""
    r = pick(row, 'case_id stage cell seed stop_sim_s category host_error final_states chain wall_contact first_failure submit_t')
    s = pick(result, 'case_id stage cell seed row wall_contact failures final_states termination host_error '
             'teacher gt_at_entry gt_at_stop gt_at_end chain_raw exits max_tilt_deg submit_t')
    s['row'] = pick(result['row'], 'case_id stage cell seed stop_sim_s category host_error final_states chain wall_contact first_failure submit_t')
    # Keep all safety witnesses, including asynchronous GT and planned legs.
    t = [pick(x, 't tilt_deg lift_m jaws robots pf') for x in trace]
    for x in t:
        if 'robots' in x:
            x['robots'] = {r: x['robots'][r] for r in cp.ROBOTS}
        if 'pf' in x:
            x['pf'] = {r: pick(p, 'initialized t x y yaw cov') for r, p in x['pf'].items()}
    return {'row': r, 'result': s, 'trace': t, 'case': case}


def compact_write(path, value):
    path.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture-dir', type=Path, help='new directory only; never raw')
    args = parser.parse_args()
    if args.output.exists() or (args.fixture_dir and args.fixture_dir.exists()):
        parser.error('outputs must be new')
    if args.output.resolve().is_relative_to(RAW) or (args.fixture_dir and args.fixture_dir.resolve().is_relative_to(RAW)):
        parser.error('cannot write inside raw')
    audit = json.loads(AUDIT.read_text())
    def hashes():
        return {p: cp.sha256(RAW / p) for p in audit['input_sha256']}
    before = hashes()
    assert before == audit['input_sha256']
    runner = cp.rv.RECORDER_PATH
    producer = subprocess.check_output(['git', 'show', f'{audit["registered_runner_sha"]}:{runner}'], cwd=ROOT)
    acceptance = subprocess.check_output(['git', 'show', f'{audit["acceptance_source_sha"]}:{runner}'], cwd=ROOT)
    assert producer == acceptance
    assert hashlib.sha256(producer).hexdigest() == cp.rv.RECORDER_SHA256
    manifest = json.loads((RAW / 'manifest.json').read_text())
    manifest_projection = pick(manifest, 'source_sha source_fingerprint source_changed state')
    rows = [json.loads(x) for x in (RAW / 'cases.jsonl').read_text().splitlines()]
    outputs = []
    if args.fixture_dir:
        args.fixture_dir.mkdir(parents=True)
    for index, row in enumerate(sorted(rows, key=lambda r: r['case_id'])):
        directory = cp.ca.dra.case_dir(RAW, row['case_id'])
        result = json.loads((directory / 'result.json').read_text())
        trace = [json.loads(x) for x in (directory / 'eval_only/trace.jsonl').read_text().splitlines()]
        case = json.loads((directory / 'case.json').read_text())
        expected = 'FAIL' if 'lag-off-sanity' in row['case_id'] else 'PASS_CLEAN'
        outcome = cp.adjudicate_attempt(row, result, trace, confirmatory=True,
                                        recorder_context={'manifest': manifest, 'case': case})
        assert outcome['class'] == expected and outcome['evidence_valid'], outcome
        projected = project(row, result, trace, case)
        projected_out = cp.adjudicate_attempt(projected['row'], projected['result'], projected['trace'],
            confirmatory=True, recorder_context={'manifest': manifest_projection, 'case': case})
        assert projected_out == outcome, row['case_id']
        name = f'case_{index:02d}.json'
        if args.fixture_dir:
            compact_write(args.fixture_dir / name, projected)
        outputs.append({'file': name, 'case_id': row['case_id'], 'expected_class': expected,
                        'class': outcome['class'], 'state': outcome['state'], 'evidence_valid': outcome['evidence_valid'],
                        'confirmatory_evidence_checked': outcome['confirmatory_evidence_checked'],
                        'coverage': outcome['recorder_contract']['coverage'],
                        'wall_contact': outcome['recorder_contract']['wall_contact'],
                        'projection_sha256': cp.value_hash(projected)})
    assert len(outputs) == 11 and sum(o['class'] in cp.PASS for o in outputs) == 10
    after = hashes()
    assert after == before
    provenance = {'raw': str(RAW), 'registered_runner_sha': audit['registered_runner_sha'],
                  'acceptance_source_sha': audit['acceptance_source_sha'], 'recorder_sha256': cp.rv.RECORDER_SHA256,
                  'manifest': manifest_projection, 'input_sha256': before, 'cases': outputs}
    if args.fixture_dir:
        compact_write(args.fixture_dir / 'provenance.json', provenance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({**provenance, 'input_hashes_stable': after == before,
        'scope': 'consumer contract and golden classifications, not confirmatory cohort admission or new physics'}, indent=2) + '\n')
    print(json.dumps({'cases': 11, 'lag_on_pass': 10, 'lag_off_fail': 1, 'input_files_unchanged': len(before),
                      'producer_byte_identical': True, 'projection_matches_full_raw': True}))


if __name__ == '__main__':
    main()
