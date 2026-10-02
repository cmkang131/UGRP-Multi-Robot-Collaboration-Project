"""Versioned, offline criterion B adapter for the committed v91 acquisition.

No fitting, simulator, renderer, model call, or raw mutation. Optional GitHub
re-fetch is read-only and fails closed if requested but unavailable.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import subprocess

from scripts import validate_consumer_criterion_b as frozen

ROOT = frozen.ROOT
RECORD = ROOT / 'experiments/2026-10-03-critb-v91'
SNAPSHOT = RECORD / 'commitment.json'
CONTRACT = RECORD / 'acquisition_contract.json'
SOURCE = '04043e274af7351f3d35cb6be77d948cac1b8c6a'
BUNDLE = 'zone-final-pair-v91'
WORKFLOW = 'zone-final-pair-heldout-v91'
VERSION = '3.3.0'
COMMENT_API = 'repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/5958329647'
ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False, 'teacher_only': True}
FROZEN_HASHES = {
    str(frozen.CRITERION.relative_to(ROOT)): frozen.CRITERION_SHA256,
    str(frozen.CANDIDATE.relative_to(ROOT)): 'fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071',
    'scripts/validate_consumer_criterion_b.py': '8d2a693a6e3bbca79a8214fd388bff79a0609400f07de831ad9be3cf22e85a88',
    'configs/zone_final_pair_v91.json': 'a07d412ced2e5e301c327a07f61ca5ab6bc4cfe1f2c8b7b7f33740e4b3a29307',
}
PINNED = {
    SNAPSHOT: '7c4238238f4e7d660841abf50975b27492fd7beec461a4f08da9e72ae88a35b8',
    CONTRACT: 'a60ff44849d296e334dd60ff00f81ed91da3b259fd2521636f9243faa74640e8',
    ROOT / 'scripts/fit_unloaded_consumer.py': '63c7e1298ae6ccf63d2552e23f9fcb2cef09b26d55092f3a6c92ed0fadd5c350',
    ROOT / 'scripts/fit_unloaded_hammerstein.py': 'fe1a327ad060a9bbac8b9c25292e823e0b2b73319e16559d876e9d1a4dbc7677',
}


def canonical_sha(value):
    return frozen.sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def read_json(path, inputs):
    value = json.loads(frozen.read_input(path, inputs))
    if not isinstance(value, dict):
        raise ValueError(f'expected JSON object: {path}')
    return value


def utc(value):
    if not isinstance(value, str):
        raise ValueError('UTC timestamp must be an explicit UTC string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError('missing or non-UTC timezone')
    return parsed


def verify_commitment(inputs, *, refetch=False):
    for path, expected in PINNED.items():
        if frozen.sha(frozen.read_input(path, inputs)) != expected:
            raise ValueError(f'pinned evidence hash mismatch: {path.name}')
    snapshot = read_json(SNAPSHOT, inputs)
    if snapshot['listed_sha256'] != FROZEN_HASHES or snapshot['collection_source_sha'] != SOURCE:
        raise ValueError('commitment listed hashes/source mismatch')
    if (snapshot['id'] != 5958329647 or snapshot['updated_at'] != snapshot['created_at']
            or frozen.sha(snapshot['body'].encode()) != snapshot['body_sha256']):
        raise ValueError('commitment identity/body/edit mismatch')
    for name, expected in FROZEN_HASHES.items():
        if expected not in snapshot['body'] or frozen.sha(frozen.read_input(ROOT / name, inputs)) != expected:
            raise ValueError(f'commitment actual byte hash mismatch: {name}')
    if refetch:
        try:
            remote = json.loads(subprocess.check_output(
                ['gh', 'api', COMMENT_API], text=True, timeout=30, stderr=subprocess.PIPE))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ValueError('requested GitHub re-fetch unavailable') from exc
        for key in ('id', 'html_url', 'created_at', 'updated_at', 'body'):
            if remote.get(key) != snapshot[key]:
                raise ValueError(f'GitHub commitment changed: {key}')
    utc(snapshot['created_at'])
    return snapshot


def collection_root(raw):
    raw = Path(raw).resolve()
    return raw.parent if (raw / 'bundle.json').is_file() or (raw / 'eval_only').is_dir() else raw


def require_fields(value, expected, label):
    # JSON true/false must not be accepted as integer 1/0 (or the reverse).
    for key, wanted in expected.items():
        if type(value.get(key)) is not type(wanted) or value[key] != wanted:
            raise ValueError(f'{label} identity mismatch: {key}')


def start_records(records):
    """All supported start fields, including v91's conservative lock lower bounds.

    04043e27 has no direct started_utc: its plan/result host_start records the
    already-acquired physics/SIM locks. Those Unix seconds are runner-clock UTC
    lower bounds on acquisition, not measured collection start times.
    """
    stamps = []
    for path, record in records:
        before = len(stamps)
        for key in ('started_utc', 'start_utc'):
            if key in record:
                stamps.append((utc(record[key]), str(path), key, record[key], 'start_utc'))
        host = record.get('host_start')
        if not isinstance(host, dict):
            raise ValueError(f'missing host_start: {path}')
        for key in ('started_utc', 'start_utc'):
            if key in host:
                stamps.append((utc(host[key]), str(path), 'host_start.'+key, host[key], 'start_utc'))
        holders = [('physics_holder', host.get('physics_holder'))]
        concurrent = host.get('concurrent_holders')
        if not isinstance(concurrent, list):
            raise ValueError('missing host_start concurrent_holders')
        holders += [(f'concurrent_holders[{i}]', h) for i, h in enumerate(concurrent)]
        for field, holder in holders:
            if not isinstance(holder, dict):
                raise ValueError('missing host_start holder')
            value = holder.get('acquired_unix')
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('missing/invalid host_start acquired_unix')
            stamps.append((datetime.fromtimestamp(value, timezone.utc), str(path),
                           'host_start.'+field+'.acquired_unix', value, 'lock_acquisition_lower_bound'))
        if len(stamps) == before:
            raise ValueError(f'no recorded collection start evidence: {path}')
    return [{'utc': t.isoformat(), 'path': p, 'field': f, 'recorded_value': v, 'kind': k}
            for t, p, f, v, k in sorted(stamps)]


def load_collection(raw, gate, contract, inputs):
    root = collection_root(raw)
    plan = read_json(root / 'plan.json', inputs)
    result = read_json(root / 'result.json', inputs)
    require_fields(plan, {**ROLE, 'execution_bundle_id': BUNDLE, 'check': 'calibration-unloaded',
                         'source_sha': SOURCE, 'seed': 911, 'execution_started': True,
                         'denominator': 1, 'runnable': True, 'blocked_on': []}, 'plan')
    require_fields(result, {**ROLE, 'denominator': 1}, 'collection result')
    folders = sorted({p.parents[2] for p in root.rglob('eval_only/r1/pose.jsonl')})
    if len(folders) != 1 or folders[0].parent != root:
        raise ValueError('v91 requires exactly one direct case per map collection')
    folder = folders[0]
    bundle = read_json(folder / 'bundle.json', inputs)
    case_result = read_json(folder / 'result.json', inputs)
    map_id = bundle.get('map_id')
    if map_id not in gate['held_out']['allowed_maps'] or map_id == gate['held_out']['training_map']:
        raise ValueError('training/unregistered map is not held-out')
    require_fields(bundle, {**ROLE, 'execution_bundle_id': BUNDLE, 'workflow_id': WORKFLOW,
                           'workflow_version': VERSION, 'source_sha': SOURCE, 'seed': 911}, 'bundle')
    require_fields(case_result, ROLE, 'case result')
    digest = canonical_sha(bundle)
    if digest != contract['bundle_canonical_sha256'][map_id]:
        raise ValueError('bundle differs from exact v91 source contract (relabelled/altered raw)')
    if plan['bundles_sha256'] != [digest] or plan['cases'] != [bundle['case']]:
        raise ValueError('plan/bundle binding mismatch')
    schedule = frozen.read_input(folder / 'inputs/schedule.json', inputs)
    if frozen.sha(schedule) != contract['schedule_sha256']:
        raise ValueError('recorded v91 schedule byte hash mismatch')
    # Adapt only acquisition ID for the frozen loader; scoring sees the original B.
    loader_gate = copy.deepcopy(gate)
    loader_gate['held_out']['execution_bundle_id'] = BUNDLE
    cases = frozen.load_collection(raw, loader_gate)
    for case in cases:
        inputs.extend(case['inputs'])
    artifacts = read_json(folder / 'artifacts.sha256.json', inputs)
    for item in inputs:
        path = Path(item['path'])
        if path.is_relative_to(folder) and path.name != 'artifacts.sha256.json':
            if artifacts.get(str(path.relative_to(folder))) != item['sha256']:
                raise ValueError('raw artifact receipt mismatch: '+str(path))
    stamps = start_records([(root / 'plan.json', plan), (root / 'result.json', result),
                            (folder / 'result.json', case_result)])
    return cases, stamps


def score(cases, candidate, gate, *, chronology_verified=False):
    """Use the frozen score verbatim; lift ONLY its missing-chronology veto."""
    report = frozen.score(cases, candidate, gate)
    if chronology_verified:
        for case in report['cases']:
            if case['eligibility_reason'] != (
                    'unverified acquisition chronology: no proof bound to criterion B, candidate and raw hashes'):
                continue
            case.update(scope='HELD_OUT_VALIDATION', eligibility_reason=None)
            for axis in case['axes'].values():
                if axis['metrics'] is not None:
                    axis['pass'] = axis['numerical_pass']
                    axis['reason'] = None
        report['axis_pass'] = {a: frozen.combine([r['axes'][a]['pass'] for r in report['cases']])
                               for a in frozen.AXES}
        report['pass'] = frozen.combine(list(report['axis_pass'].values()))
    report['schema'] = 'ugrp.consumer_B_validation.v91'
    report['scope_note'] = ('Frozen B offline process-budget coverage only; no candidate promotion, '
        'PF posterior, student control or physical success. Chronology relies on GitHub server time '
        'versus runner-recorded UTC, including pre-start lock-acquisition lower bounds; not signed raw.')
    return report


def ineligible(reason):
    return {'schema': 'ugrp.consumer_B_validation.v91', 'criterion_sha256': frozen.CRITERION_SHA256,
            'criterion_A': 'FAILED_NOT_RESCORED', 'candidate_status': 'CANDIDATE_UNVALIDATED',
            'scope': 'INELIGIBLE', 'eligibility_reason': reason, 'cases': [],
            'axis_pass': dict.fromkeys(frozen.AXES), 'pass': None}


def validate(raws, *, refetch=False):
    inputs, cases, stamps = [], [], []
    evidence = {'verified': False, 'github_check': 'requested' if refetch else 'snapshot_only'}
    try:
        snapshot = verify_commitment(inputs, refetch=refetch)
        evidence.update(comment_id=snapshot['id'], html_url=snapshot['html_url'],
                        created_at=snapshot['created_at'], body_sha256=snapshot['body_sha256'],
                        github_check='matched' if refetch else 'snapshot_only')
        contract = read_json(CONTRACT, inputs)
        gate = frozen.criterion()
        candidate = read_json(frozen.CANDIDATE, inputs)
        if not raws:
            raise ValueError('no raw collections')
        for raw in raws:
            loaded, recorded = load_collection(raw, gate, contract, inputs)
            cases.extend(loaded)
            stamps.extend(recorded)
        maps = [case['map_id'] for case in cases]
        if len(maps) != len(set(maps)):
            raise ValueError('duplicate held-out map collection')
        if any(case['pose_sha256'] in candidate['previously_seen_pose_sha256'] for case in cases):
            raise ValueError('previously seen raw pose bytes')
        earliest = min(stamps, key=lambda s: utc(s['utc']))
        evidence.update(recorded_starts=stamps, earliest=earliest)
        if not utc(snapshot['created_at']) < utc(earliest['utc']):
            raise ValueError('commitment is not strictly before earliest recorded collection start/lower bound')
        report = score(cases, candidate, gate, chronology_verified=True)
        # Preserve both the raw and evidence hashes, and check again AFTER scoring.
        frozen.verify_inputs([{'inputs': inputs}])
        evidence['verified'] = True
        report['scope'] = ('HELD_OUT_VALIDATION' if all(r['scope'] == 'HELD_OUT_VALIDATION'
                           for r in report['cases']) else 'INELIGIBLE')
        report['maps_observed'] = maps
        report['maps_not_supplied'] = sorted(set(gate['held_out']['allowed_maps']) - set(maps))
        report['candidate_sha256'] = FROZEN_HASHES[str(frozen.CANDIDATE.relative_to(ROOT))]
    except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
        report = ineligible(str(exc))
        evidence['verified'] = False
    report['ordering_evidence'] = evidence
    report['input_files'] = list({(i['path'], i['sha256']): i for i in inputs}.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, action='append', required=True,
                        help='one completed map collection (repeat for both maps)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refetch-commitment', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if any(output.is_relative_to(collection_root(raw)) for raw in args.raw):
        raise ValueError('output must be outside every raw collection, including case parents')
    report = validate(args.raw, refetch=args.refetch_commitment)
    frozen.write(output, report)  # exclusive create; never overwrite
    print(json.dumps({k: report[k] for k in ('scope', 'axis_pass', 'pass')}))
    return 1 if report['pass'] is False else (0 if report['pass'] is True else 2)


if __name__ == '__main__':
    raise SystemExit(main())
