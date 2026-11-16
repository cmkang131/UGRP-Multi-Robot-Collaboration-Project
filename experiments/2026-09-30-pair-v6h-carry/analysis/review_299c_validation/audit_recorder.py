#!/usr/bin/env python3
"""Read ONLY the explicitly public acceptance replay; never run its driver.

Reproduce with the existing Python environment, --output a NEW json path.
No imports of the runner, simulator or controller; classifier math only.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]
RAW = Path('/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-3c4fe30e-claude-20260930')
REGISTERED = '4c6b439f3f7c9a147c901f8b260a1e214d4eb396'
CLASSIFIER = 'f32d5fd9afc54ca57ed49860843f54d6b5ca174d'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    spec = importlib.util.spec_from_file_location('review299c_classifier', Path(__file__).parents[1] / 'classify_placements.py')
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    hashes = {}

    def read(path, lines=False):
        data = path.read_bytes()
        hashes[str(path.relative_to(RAW))] = hashlib.sha256(data).hexdigest()
        return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)

    manifest = read(RAW / 'manifest.json')
    rows = read(RAW / 'cases.jsonl', lines=True)
    plan = read(RAW / 'plan.json')
    runner_path = 'scripts/run_pair_stage_probes.py'
    acceptance_source = subprocess.check_output(['git', 'show', f"{manifest['source_sha']}:{runner_path}"], cwd=ROOT)
    registered_source = subprocess.check_output(['git', 'show', f'{REGISTERED}:{runner_path}'], cwd=ROOT)
    runner_hash = hashlib.sha256(registered_source).hexdigest()
    fingerprint = next(x['sha256'] for x in manifest['source_fingerprint']['files'] if x['path'] == runner_path)
    cases = []
    for row in sorted(rows, key=lambda r: r['case_id']):
        directory = cp.ca.dra.case_dir(RAW, row['case_id'])
        result = read(directory / 'result.json')
        trace = read(directory / 'eval_only/trace.jsonl', lines=True)
        case = read(directory / 'case.json')
        missing = ['result.' + k for k in ('evidence_sha256', 'execution_identity', 'evaluation_coverage') if k not in result]
        if 'coverage' not in result['wall_contact']:
            missing.append('result.wall_contact.coverage')
        historical = cp.adjudicate_attempt(row, result, trace, confirmatory=False)
        strict = cp.adjudicate_attempt(row, result, trace, confirmatory=True)
        handover = cp.handover_checks(row['chain'], trace)
        window = cp.validate_end_window(row, result, {leg['leg']: leg for leg in row['chain']['legs']})
        sigma = cp.sigma_case(row, trace)
        # Direct field/type checks beyond the first short-circuiting coverage
        # error. This inventories what IS recorded, without inventing coverage.
        cp.validate_required_record(row, result)
        for leg in row['chain']['legs']:
            cp.validate_leg(leg)
        for sample in trace:
            cp.finite(sample.get('lift_m'), 'lift')
            cp.jaws_valid(sample.get('jaws'))
        cases.append({
            'case_id': row['case_id'], 'cell': row['cell'], 'seed': row['seed'],
            'sanity_lag_off': 'lag-off-sanity' in row['case_id'],
            'missing_required': missing,
            'case_missing_seal_fields': [k for k in ('source_sha', 'bundle_id', 'prior_id') if k not in case],
            'result_row_matches_cases': result['row'] == row,
            'historical_class': historical['class'], 'strict_state': strict['state'],
            'strict_class': strict['class'], 'strict_issues': strict['hard_limit_chain']['evidence_issues'],
            'remaining_required_row_fields_valid': True,
            'trace_count': len(trace), 'trace_first_s': trace[0]['t'], 'trace_last_s': trace[-1]['t'],
            'trace_max_gap_s': max(b['t'] - a['t'] for a, b in zip(trace, trace[1:])),
            'handover': handover, 'end_window': window,
            'all_reached_pf_pairs_valid': all(all(leg['signed'].get(r) is not None for r in cp.ROBOTS)
                                              for leg in sigma.values() if leg['reached']),
        })
    stable = all(hashlib.sha256((RAW / path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
    assert stable
    output = {
        'reviewed_classifier_sha': CLASSIFIER, 'registered_runner_sha': REGISTERED,
        'acceptance_raw': str(RAW), 'acceptance_source_sha': manifest['source_sha'],
        'runner_byte_identical': acceptance_source == registered_source,
        'runner_file_sha256': runner_hash, 'runner_matches_recorded_fingerprint': runner_hash == fingerprint,
        'source_changed': manifest['source_changed'], 'manifest_state': manifest['state'],
        'acceptance_manifest_keys': sorted(manifest),
        'acceptance_plan_keys': sorted(plan),
        'case_count': len(cases), 'cases': cases,
        'input_sha256': hashes, 'input_hashes_stable_after_audit': stable,
        'scope': 'Read-only public acceptance inventory and classifier calls; no physics, no hidden cohort access. '
                 'Missing coverage/receipts are not fabricated. Historical PASS is not confirmatory PASS.',
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': len(cases), 'historical_pass': sum(c['historical_class'] in cp.PASS for c in cases),
                      'strict_invalid': sum(c['strict_state'] == 'INVALID' for c in cases),
                      'runner_identical': output['runner_byte_identical'],
                      'runner_fingerprint_match': output['runner_matches_recorded_fingerprint'],
                      'input_files': len(hashes), 'hashes_stable': stable}))


if __name__ == '__main__':
    main()
