#!/usr/bin/env python3
"""Reclassify all 308 published historical cases + partial tX1; never run physics."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('classify_review', HERE / 'classify_placements.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False, parents=True)
    source = HERE / 'validation_20260930/published_count_checks.json'
    expectations = json.loads(source.read_text())
    checks, completed = [], 0
    for entry in expectations:
        label = entry['cohort']
        report = cp.analyse(label, Path(entry['raw']), primary_seed=911)
        s = report['summary']
        actual = [s['n_cases'], s['cases_pass']]
        if label == 'tX1':
            actual += [len(s['unclassified_cases']), s['n_placements'], s['n_classified_primary']]
        else:
            actual += [s['placements_all_recorded_seeds_pass'], s['n_placements']]
            actual += [sum(c.get('legs', {}).get(f'L{k}', {}).get('standard_pass', False)
                           for p in report['placements'] for c in p['cases']) for k in (0, 1)]
            completed += s['n_cases']
        checked = {**entry, 'recomputed': actual, 'match': (actual == entry['published_expected']
                             and s['pass_placements'] == entry['primary911_pass']
                             and s['hard_limit_chain_cases'] == entry['hard_limit_cases']
                             and report['source_sha'] == entry['source_sha']),
                   'recomputed_primary911_pass': s['pass_placements'],
                   'recomputed_hard_limit_cases': s['hard_limit_chain_cases'],
                   'raw_hash_unchanged': report['input_sha256']['cases.jsonl'] == entry['cases_sha256'],
                   'full_input_sha256': report['input_sha256']}
        previous = json.loads((HERE / 'review_validation_20260930' / f'{label}.json').read_text())
        old_cases = {c['case_id']: c for p in previous['placements'] for c in p['cases']}
        checked['case_changes'] = [
            {'case_id': c['case_id'], 'old_class': old_cases.get(c['case_id'], {}).get('class'),
             'new_class': c['class'], 'reason_code': c['reason_code'],
             'evidence_issues': c['hard_limit_chain']['evidence_issues']}
            for p in report['placements'] for c in p['cases']
            if c['class'] != old_cases.get(c['case_id'], {}).get('class')]
        checked['admitted_denominator'] = s['denominator']
        checks.append(checked)
        (args.output / f'{label}.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(label, actual, 'MATCH' if checked['match'] else 'MISMATCH', flush=True)
        (args.output / 'published_count_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
        if not checked['raw_hash_unchanged']:
            raise SystemExit(f'STOP: {label}; raw hash changed')
    assert completed == 308
    print(f'RECONCILED: {completed} completed cases; {sum(not c["match"] for c in checks)} changed cohorts; raw hashes unchanged')


if __name__ == '__main__':
    main()
