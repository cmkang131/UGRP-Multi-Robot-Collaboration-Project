"""Apply the sealed analysis AFTER independent review/unblinding authorization.

This command reads raw only when explicitly run. Registration verification and
unit tests never call it on the blinded cohort. The original classifier report
continues to disclose unsealed_stage_probe admission; the separate analysis
summary implements the coordinator's later, blinded analysis seal.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
PREFIX = 'experiments.2026-09-30-pair-v6h-carry.analysis.'


def apply_gate(report, plan, classifier):
    cases = [c for placement in report['placements'] for c in placement['cases']]
    entries = [{'placement': c['cell'], 'seed': c['seed']} for c in plan['cases']]
    _, summary = classifier.summarize(cases, 941, {'cases': entries}, report['attempts'])
    issues = report['summary']['cohort_evidence_issues']
    invalid = bool(issues or report['summary']['invalid_cases'] or summary['unclassified_cases'])
    sigma = classifier.summarize_sigma(cases)
    summary['sigma_criterion_B'] = sigma
    summary['cohort_evidence_issues'] = issues
    if invalid:
        summary['criterion'].update(evaluable=False, verdict='FAIL_OBSERVED_CRITERION'
                                    if summary['hard_limit_chain_cases'] else 'NOT_EVALUABLE')
    summary['full_verdict'] = (
        'FAIL_A_B_SAFETY' if summary['hard_limit_chain_cases'] or summary['criterion']['verdict'] == 'FAIL_OBSERVED_CRITERION'
        or sigma['verdict'] == 'FAIL' else
        'PASS_A_B_SAFETY' if not invalid and summary['criterion']['verdict'] == 'PASS_OBSERVED_CRITERION'
        and sigma['verdict'] == 'PASS' else 'NOT_EVALUABLE')
    summary['registration_timing'] = 'analysis_sealed_after_blinded_recording'
    summary['recorded_admission'] = report['summary']['recorded_admission']
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal-commit', required=True)
    parser.add_argument('--prereg', required=True, type=Path)
    parser.add_argument('--raw', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    seal = importlib.import_module(PREFIX + 'seal_registration')
    value = json.loads(args.prereg.read_bytes())
    seal.verify_seal(value, args.seal_commit)
    # Verification at the seal commit alone cannot bless different loaded code.
    for path, receipt in value['pin_sets']['analysis']['files'].items():
        if seal.sha((ROOT/path).read_bytes()) != receipt['sha256']:
            raise ValueError('checkout the analysis seal commit: ' + path)
    if args.output.exists() or args.output.resolve().is_relative_to(args.raw.resolve()):
        raise ValueError('output must be new and outside raw')
    if str(args.raw.resolve()) != seal.metadata()['RUN_MANIFEST.json']['raw']['path']:
        raise ValueError('raw path differs from committed manifest')
    classifier = importlib.import_module(PREFIX + 'classify_placements')
    manifest = seal.HERE/'analysis/seal/RUN_MANIFEST.json'
    report = classifier.analyse('v6h1', args.raw, 941, recorded_run_manifest=manifest,
                               recorded_run_manifest_sha256=seal.METADATA_HASHES['RUN_MANIFEST.json'])
    summary = apply_gate(report, value, classifier)
    args.output.mkdir(parents=True)
    for name, result in (('classifier.json', report), ('sealed_analysis.json', {
            'seal_commit': args.seal_commit, 'registration_sha256': value['registration_sha256'],
            'summary': summary})):
        (args.output/name).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
