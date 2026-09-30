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
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
PREFIX = 'experiments.2026-09-30-pair-v6h-carry.analysis.'
classifier = importlib.import_module(PREFIX + 'classify_placements')
INVENTORY_SCHEMA = 'ugrp.v6h1.acquisition_inventory.v1'


class AcquisitionReader(classifier.EvidenceReader):
    """Admit only bytes bound to the sealed acquisition, before consumption.

    The committed run manifest and acquisition inventory are the two trust
    roots. Every other input must be listed in that inventory. The inherited
    reader still hashes the exact parsed bytes and detects mid-analysis edits.
    """
    def __init__(self, raw, manifest, manifest_sha256):
        super().__init__(Path(raw).resolve())
        self.manifest = Path(manifest).resolve()
        self.expected = {self.name(self.manifest): manifest_sha256}
        self.trust_roots = {self.manifest}

    def name(self, path):
        return str(path.relative_to(self.raw)) if path.is_relative_to(self.raw) else str(path)

    def bind_inputs(self, files):
        """Install normalized (relative path, SHA-256) inventory entries."""
        seen = set()
        for name, digest in files:
            path = Path(name) if isinstance(name, str) else None
            if (path is None or not name or path.is_absolute() or '..' in path.parts
                    or path.as_posix() != name or name in seen or name in self.expected
                    or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                raise classifier.EvidenceError('INVALID_ACQUISITION_ENTRY:' + str(name))
            seen.add(name)
            self.expected[name] = digest
        if not seen:
            raise classifier.EvidenceError('EMPTY_ACQUISITION_INVENTORY')

    def load_inventory(self, inventory, pin):
        """Read the generator's v1 format without walking the acquisition tree."""
        if inventory is None:
            raise classifier.EvidenceError('MISSING_ACQUISITION_INVENTORY')
        if not isinstance(pin, dict):
            raise classifier.EvidenceError('MISSING_ACQUISITION_PIN')
        inventory = Path(inventory).resolve()
        if inventory.is_relative_to(self.raw) or inventory in self.trust_roots:
            raise classifier.EvidenceError('INVALID_ACQUISITION_INVENTORY_PATH')
        self.trust_roots.add(inventory)
        self.expected[self.name(inventory)] = pin.get('inventory_sha256')
        doc, _ = self.read(inventory)
        if (doc.get('schema') != INVENTORY_SCHEMA or pin.get('schema') != INVENTORY_SCHEMA
                or doc.get('raw') != str(self.raw) or pin.get('raw') != str(self.raw)):
            raise classifier.EvidenceError('INVALID_ACQUISITION_SCHEMA_OR_RAW_PATH')
        files = doc.get('files')
        if not isinstance(files, list) or not all(isinstance(f, dict) for f in files):
            raise classifier.EvidenceError('INVALID_ACQUISITION_FILES')
        for key in ('file_count', 'total_bytes'):
            if type(doc.get(key)) is not int or type(pin.get(key)) is not int or doc[key] != pin[key]:
                raise classifier.EvidenceError('ACQUISITION_TOTAL_MISMATCH:' + key)
        if (doc['file_count'] != len(files) or not files
                or any(type(f.get('bytes')) is not int or f['bytes'] < 0 for f in files)
                or doc['total_bytes'] != sum(f['bytes'] for f in files)):
            raise classifier.EvidenceError('ACQUISITION_TOTAL_MISMATCH:files')
        times = [doc.get('created_unix'), doc.get('driver_end_unix'), *(f.get('mtime') for f in files)]
        if (any(type(t) not in (int, float) or not math.isfinite(t) for t in times)
                or type(doc.get('files_modified_after_driver_end')) is not int
                or not 0 <= doc['files_modified_after_driver_end'] <= len(files)):
            raise classifier.EvidenceError('INVALID_ACQUISITION_TIMESTAMPS')
        # These mtimes describe acquisition provenance, not proof of prior bytes.
        self.bind_inputs((f.get('path'), f.get('sha256')) for f in files)
        return doc

    def read(self, path, *, lines=False):
        path = Path(path).absolute()
        name = self.name(path)
        expected = self.expected.get(name)
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise classifier.EvidenceError('UNLISTED_ACQUISITION_INPUT:' + name)
        if path not in self.trust_roots and not path.resolve().is_relative_to(self.raw):
            raise classifier.EvidenceError('ACQUISITION_PATH_ESCAPE:' + name)
        value, issues = super().read(path, lines=lines)
        if issues:
            raise classifier.EvidenceError('; '.join(issues))
        if self.hashes.get(name) != expected:
            raise classifier.EvidenceError('ACQUISITION_HASH_MISMATCH:' + name)
        return value, []

    def verify(self):
        issues = super().verify()
        if issues:
            raise classifier.EvidenceError('; '.join(issues))
        return []


def analyse_acquisition(raw, plan, manifest, manifest_sha256, inventory, inventory_pin):
    """Single sealed entry point; never emit a gate verdict on integrity failure."""
    reader = AcquisitionReader(raw, manifest, manifest_sha256)
    try:
        reader.load_inventory(inventory, inventory_pin)
        recorded, _ = reader.read(reader.manifest)
        if recorded.get('raw', {}).get('path') != str(reader.raw):
            raise classifier.EvidenceError('RECORDED_RAW_PATH_MISMATCH')
        # The driver manifest is only run status. Require both its inventory hash
        # and the independently sealed RUN_MANIFEST digest before classification.
        reader.read(reader.raw / 'manifest.json')
        if reader.hashes['manifest.json'] != recorded['raw'].get('raw_manifest_json_sha256'):
            raise classifier.EvidenceError('RAW_MANIFEST_HASH_MISMATCH')
        report = classifier.analyse('v6h1', reader.raw, 941, recorded_run_manifest=reader.manifest,
            recorded_run_manifest_sha256=manifest_sha256, evidence_reader=reader)
        reader.verify()
        summary = apply_gate(report, plan, classifier)
        reader.verify()  # retain the change check through gate calculation too
    except classifier.EvidenceError as error:
        return None, {'status': 'INVALID', 'analysis_status': 'NOT_ANALYSED', 'reason': str(error)}
    return report, {'status': 'ANALYSED', 'summary': summary}


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
    parser.add_argument('--inventory', type=Path, help='required acquisition inventory; omission fails closed')
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
    manifest = seal.HERE/'analysis/seal/RUN_MANIFEST.json'
    report, outcome = analyse_acquisition(args.raw, value, manifest,
        seal.METADATA_HASHES['RUN_MANIFEST.json'], args.inventory, value.get('acquisition_inventory'))
    args.output.mkdir(parents=True)
    results = {'sealed_analysis.json': {
        'seal_commit': args.seal_commit, 'registration_sha256': value['registration_sha256'], **outcome}}
    if report is not None:
        results['classifier.json'] = report
    for name, result in results.items():
        (args.output/name).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return 0 if outcome['status'] == 'ANALYSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
