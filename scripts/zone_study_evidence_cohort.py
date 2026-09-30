"""Publish P06 frozen-plan summaries; missing/invalid trials remain non-success.

No simulator, provider, discovery-based denominator, or legacy-result fallback.
The plan SHA-256 must come from the preregistration, not from a raw manifest.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from harness.zone_study_contract import digest
from scripts import zone_study_evidence_join as join
from scripts.tensorboard_tools.zone_study import inspect_study, file_digest


def source_hashes(source):
    """Include corrupt/unrecognized records too; never silently prune inputs."""
    if not source.is_dir():
        return {}, {'source': 'missing directory'}
    files, unavailable = {}, {}
    try:
        paths = sorted(source.rglob('*'))
    except OSError as exc:
        return {}, {'source': type(exc).__name__}
    for path in paths:
        relative = str(path.relative_to(source))
        if not path.resolve().is_relative_to(source):
            unavailable[relative] = 'outside source'
            continue
        try:
            if path.is_file():
                files[relative] = file_digest(path)
        except OSError as exc:
            unavailable[relative] = type(exc).__name__
    return files, unavailable


def collect(plan, expected_sha256, sources):
    admitted = join.validate_plan(plan, expected_sha256)
    by_run = {row['key']['run_id']: i for i, row in enumerate(admitted)}
    tables = {name: [] for name in join.TABLES}
    invalid, receipts = {}, []
    for source in sources:
        source = Path(source).resolve()
        hashes, unavailable = source_hashes(source)
        receipt = {'source': str(source), 'inputs_sha256': hashes, 'unavailable_inputs': unavailable}
        try:
            if unavailable:
                raise ValueError('Source has missing/unreadable/escaping input records')
            meta, _, verified = inspect_study(source)
            if meta['plan_sha256'] != expected_sha256:
                raise ValueError('Source frozen plan differs from cohort pin')
            if {k: v['sha256'] for k, v in verified.items()} != hashes:
                raise ValueError('Source changed while collecting cohort')
            for name in join.TABLES:
                tables[name].extend(meta['relations'][name])
            receipt.update(key=meta['evidence_key'], status='VERIFIED')
        except (ValueError, OSError, KeyError, TypeError, AttributeError, IndexError) as exc:
            receipt.update(status='INVALID', reason=str(exc))
            # Naming identifies only the failed slot, never authorizes success.
            # Unknown ownership poisons the cohort conservatively.
            affected = [by_run[source.name]] if source.name in by_run else range(len(admitted))
            for i in affected:
                invalid.setdefault(i, []).append('invalid_source:' + str(source))
        receipts.append(receipt)
    summary = join.aggregate(plan, expected_sha256, tables, invalid=invalid)
    summary['sources'] = sorted(receipts, key=lambda row: (row['source'], digest(row)))
    summary['schema'] = 'ugrp.zone_study_cohort_publication.v1'
    all_inputs = {'frozen_plan': expected_sha256}
    for i, receipt in enumerate(summary['sources']):
        for path, sha in receipt['inputs_sha256'].items():
            all_inputs[f'sources/{i}/{path}'] = sha
        all_inputs[f'sources/{i}/receipt'] = digest(receipt)
    summary['derived'] = join.derivations({k: v for k, v in summary.items()
                                         if k not in ('derived', 'sources')}, all_inputs,
                                         [row['key'] for row in admitted])
    return summary


def verify_summary(summary, plan, expected_sha256, sources):
    current = collect(plan, expected_sha256, sources)
    if digest(current) != digest(summary):
        raise ValueError('Published cohort differs from re-derived exact input records')
    return current


def publish(plan_path, expected_sha256, sources, output, *, allow_synthetic=False):
    from scripts.tensorboard_tools.export import Writer
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    sources = [Path(p).resolve() for p in sources]
    plan_bytes = plan_path.read_bytes()
    plan = join.strict_json(plan_bytes)
    join.validate_plan(plan, expected_sha256)
    if output.exists():
        raise FileExistsError(output)
    if any(output == src or output.is_relative_to(src) for src in sources):
        raise ValueError('Cohort output must be outside every raw source')
    for source in sources:
        path = source / 'result.json'
        try:
            synthetic = json.loads(path.read_text()).get('evidence_kind') == 'synthetic'
        except (OSError, ValueError):
            synthetic = False
        if synthetic and (not allow_synthetic or not output.is_relative_to(Path(tempfile.gettempdir()).resolve())):
            raise ValueError('Synthetic cohort requires explicit temporary-logdir opt-in')
    summary = collect(plan, expected_sha256, sources)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ugrp-cohort-', dir=output.parent) as tmp:
        stage = Path(tmp) / 'publication'
        stage.mkdir()
        w = Writer(stage, time.time())
        try:
            for tag, key in (('cohort/trials', 'admitted_trials'), ('cohort/successes', 'successes'),
                             ('cohort/success_rate', 'success_rate'), ('cohort/invalid_trials', 'invalid_trials')):
                w.scalar(tag, summary[key])
            for i, trial in enumerate(summary['trials']):
                w.scalar(f'trial/{i}/reported_success', int(trial['success']))
                w.text(f'trial/{i}/verdict', trial)
            w.text('provenance/frozen_plan', plan)
            w.text('provenance/derived_numbers', summary['derived'])
        finally:
            w.close()
        path = stage / 'summary.json'
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        verify_summary(json.loads(path.read_text()), plan, expected_sha256, sources)
        if plan_path.read_bytes() != plan_bytes:
            raise ValueError('Frozen plan changed during publication')
        # Nothing is visible as a completed publication until re-derivation passes.
        os.rename(stage, output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True, help='Canonical JSON SHA-256 fixed before execution')
    parser.add_argument('--source', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-synthetic', action='store_true')
    args = parser.parse_args()
    summary = publish(args.plan, args.plan_sha256, args.source, args.output, allow_synthetic=args.allow_synthetic)
    print(json.dumps({k: summary[k] for k in ('admitted_trials', 'successes', 'success_rate', 'invalid_trials')}))


if __name__ == '__main__':
    main()
