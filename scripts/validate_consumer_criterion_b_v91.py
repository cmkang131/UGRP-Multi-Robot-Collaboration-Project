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

import numpy as np

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
    CONTRACT: 'a947308083a03fcb5af3bc6d7155e0727317acb98084027d051bd93f9161c2eb',
    ROOT / 'scripts/fit_unloaded_consumer.py': '63c7e1298ae6ccf63d2552e23f9fcb2cef09b26d55092f3a6c92ed0fadd5c350',
    ROOT / 'scripts/fit_unloaded_hammerstein.py': 'fe1a327ad060a9bbac8b9c25292e823e0b2b73319e16559d876e9d1a4dbc7677',
}
ROTATION_RECORD = ROOT / 'experiments/2026-10-03-critb-rotation'
ROTATION_ADDENDUM = ROTATION_RECORD / 'consumer_criterion_B_rotation.json'
ROTATION_CANDIDATE = ROTATION_RECORD / 'calibration_candidate_r5_yaw.json'
ROTATION_MANIFEST = ROTATION_RECORD / 'input_manifest_r5_yaw.json'
ROTATION_SNAPSHOT = ROOT / 'experiments/2026-10-03-critb-v91-yaw/commitment.json'
ROTATION_SNAPSHOT_SHA256 = 'cad257ab12c41b786e36a1688ef522ee512551460ec91dc8e1b44a162fe450ca'
ROTATION_HASHES = {
    str(ROTATION_ADDENDUM.relative_to(ROOT)): '6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08',
    str(ROTATION_CANDIDATE.relative_to(ROOT)): '978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97',
}
ROTATION_COMMENT_API = 'repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/5966135675'
INVALID = (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError, OverflowError)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def rotation_profile(addendum, candidate, r4, gate):
    """Check the axis-only offline contract; never admit r5 to a runtime loader."""
    require_fields(addendum, {'status': 'FROZEN_CANDIDATE_BEFORE_V91_SCORING'}, 'rotation addendum')
    require_fields(candidate, {'status': 'CANDIDATE_UNVALIDATED',
                               'criterion_sha256': frozen.CRITERION_SHA256}, 'rotation candidate')
    if (addendum['original_criterion']['sha256'] != frozen.CRITERION_SHA256
            or addendum['original_r4']['sha256'] != FROZEN_HASHES[str(frozen.CANDIDATE.relative_to(ROOT))]
            or addendum['candidate']['sha256'] != ROTATION_HASHES[str(ROTATION_CANDIDATE.relative_to(ROOT))]
            or candidate['axis_validation'] != dict.fromkeys(frozen.AXES)
            or candidate['params']['motion'] is not None):
        raise ValueError('rotation criterion/candidate validation state mismatch')
    for axis in ('forward', 'left'):
        if candidate['candidate_axes'][axis] != r4['candidate_axes'][axis]:
            raise ValueError('r5 changed r4 '+axis+' profile')
    if (addendum['fit']['pf_step_s'] != .05 or gate['pf_step_s'] != .05
            or addendum['held_out']['horizons_s'] != gate['horizons_s']
            or addendum['held_out']['acceptance'] != gate['acceptance']
            or set(addendum['held_out']['allowed_maps']) != set(gate['held_out']['allowed_maps'])):
        raise ValueError('rotation changed frozen B rules')
    model = candidate['candidate_axes']['rotate']
    if model is None:
        return None
    require_fields(model, {'allowed_command_axis': 'turn', 'validation': None}, 'rotation axis')
    profile = model['consumer_fields']
    require_fields(profile, {'rest_noise': True, 'use_scale': False}, 'rotation profile')
    for key in ('tau_s', 'tau_stop_s', 'scale_std', 'scale_walk'):
        value = profile[key]
        if (type(value) not in (float, int) or not math.isfinite(value)
                or (value <= 0 if key.startswith('tau') else value != 0)):
            raise ValueError('invalid rotation scalar '+key)
    gain = np.asarray(profile['gain'], dtype=float)
    if (gain.shape != (3, 3) or not np.isfinite(gain).all() or gain[2, 2] <= 0
            or np.count_nonzero(gain) != 1):
        raise ValueError('rotation requires positive turn-only gain')
    for name in ('noise_rel', 'noise_abs'):
        noise = np.asarray(profile[name], dtype=float)
        if (noise.shape != (3,) or not np.isfinite(noise).all()
                or np.any(noise < gate['noise']['floor_'+name])):
            raise ValueError('rotation noise below M1 floor or malformed')
    return profile


def prepare_rotation(inputs, *, refetch=False):
    """Snapshot and public hashes are checked before this invocation reads raw."""
    blob = frozen.read_input(ROTATION_SNAPSHOT, inputs)
    if frozen.sha(blob) != ROTATION_SNAPSHOT_SHA256:
        raise ValueError('rotation commitment snapshot hash mismatch')
    snapshot = json.loads(blob)
    expected_url = ('https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/'
                    'issues/219#issuecomment-5966135675')
    if (snapshot['id'] != 5966135675 or snapshot['html_url'] != expected_url
            or snapshot['created_at'] != snapshot['updated_at']
            or snapshot['listed_sha256'] != ROTATION_HASHES
            or frozen.sha(snapshot['body'].encode()) != snapshot['body_sha256']):
        raise ValueError('rotation commitment identity/body/edit mismatch')
    for name, expected in ROTATION_HASHES.items():
        if expected not in snapshot['body'] or frozen.sha(frozen.read_input(ROOT / name, inputs)) != expected:
            raise ValueError('rotation commitment actual byte hash mismatch: '+name)
    if refetch:
        try:
            remote = json.loads(subprocess.check_output(
                ['gh', 'api', ROTATION_COMMENT_API], text=True, timeout=30, stderr=subprocess.PIPE))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ValueError('requested rotation GitHub re-fetch unavailable') from exc
        for key in ('id', 'html_url', 'created_at', 'updated_at', 'body'):
            if remote.get(key) != snapshot[key]:
                raise ValueError('GitHub rotation commitment changed: '+key)
    utc(snapshot['created_at'])
    addendum = read_json(ROTATION_ADDENDUM, inputs)
    candidate = read_json(ROTATION_CANDIDATE, inputs)
    manifest_blob = frozen.read_input(ROTATION_MANIFEST, inputs)
    if (frozen.sha(manifest_blob) != addendum['training']['manifest']['sha256']
            or candidate['yaw_measurement_manifest_sha256'] != frozen.sha(manifest_blob)):
        raise ValueError('rotation training manifest hash mismatch')
    manifest = json.loads(manifest_blob)
    if manifest['files'] != addendum['training']['inputs']:
        raise ValueError('rotation training manifest inputs mismatch')
    # Read only the committed manifest, never reopen its training raw paths.
    prior = set(candidate['previously_seen_pose_sha256'])
    prior.update(item['sha256'] for item in manifest['files'] if item['path'].endswith('/pose.jsonl'))
    source_path = Path(__file__).resolve()
    source = {'path': str(source_path), 'sha256': frozen.sha(frozen.read_input(source_path, inputs))}
    return {'snapshot': snapshot, 'addendum': addendum, 'candidate': candidate,
            'prior': prior, 'scoring_source': source}


def rotation_ineligible(reason):
    return {'schema': 'ugrp.consumer_B_validation.v91.rotation_addendum.v1',
            'scope': 'INELIGIBLE', 'eligibility_reason': reason, 'cases': [], 'pass': None,
            'candidate_status': 'CANDIDATE_UNVALIDATED', 'criterion_A': 'FAILED_NOT_RESCORED'}


def score_rotation(cases, profile, prior, gate):
    """The frozen evaluator is the only numerical implementation for yaw."""
    if not cases:
        raise ValueError('no rotation raw cases')
    maps = [case['map_id'] for case in cases]
    if len(maps) != len(set(maps)):
        raise ValueError('duplicate rotation map')
    for case in cases:
        if (case['training'] or case['map_id'] not in gate['held_out']['allowed_maps']
                or case['dt'] != .05):
            raise ValueError('rotation training, map or sample interval ineligible')
    results = []
    for case in cases:
        result = {'raw': case['folder'], 'map_id': case['map_id'], 'pass': None,
                  'metrics': None, 'reason': 'no frozen candidate or missing signed steps/PRBS/horizon support'}
        # Frozen B excludes prior bytes per case with a null validation decision.
        # Do not let an excluded case suppress another map's yaw evaluation.
        if case['pose_sha256'] in prior:
            result.update(reason='PREVIOUSLY_SEEN_POSE_BYTES', pose_sha256=case['pose_sha256'])
        elif profile is not None and frozen.axis_supported(case, 2, gate):
            summary = frozen.evaluate_axis(case, 2, profile, gate)
            passed = all(row['numerical_pass'] for row in frozen.all_rows(summary))
            result.update({'metrics': summary, 'numerical_pass': passed, 'pass': passed, 'reason': None})
        results.append(result)
    missing = sorted(set(gate['held_out']['allowed_maps']) - set(maps))
    scored = [r['map_id'] for r in results if r['metrics'] is not None]
    not_scored = sorted(set(gate['held_out']['allowed_maps']) - set(scored))
    # Preserve the two-map gate: a remaining-map pass cannot fill an exclusion.
    decisions = [r['pass'] for r in results] + [None for _ in missing]
    return {'schema': 'ugrp.consumer_B_validation.v91.rotation_addendum.v1',
            'scope': 'HELD_OUT_VALIDATION' if not not_scored else 'PARTIAL_MAPS',
            'cases': results, 'maps_observed': maps, 'maps_not_supplied': missing,
            'maps_scored': scored, 'maps_not_scored': not_scored,
            'pass': frozen.combine(decisions), 'candidate_status': 'CANDIDATE_UNVALIDATED',
            'criterion_A': 'FAILED_NOT_RESCORED'}


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


def validate(raws, *, refetch=False, rotation_addendum=False):
    inputs, cases, stamps = [], [], []
    evidence = {'verified': False, 'github_check': 'requested' if refetch else 'snapshot_only'}
    rotation_inputs, prepared, raw_read_started = [], None, None
    if rotation_addendum:
        rotation_evidence = {
            'verified': False, 'kind': 'PRE_SCORING_AND_READING_NOT_PRE_COLLECTION',
            'original_B_ordering_kind': 'PRE_COLLECTION', 'pre_collection_claim': False,
            'v91_collection_precedes_commitment': True,
            'github_check': 'requested' if refetch else 'snapshot_only',
            'prior_access_declaration': 'Public commitment body and implementation work record; '
                'not cryptographic proof of all participants historical non-access.',
            'work_record': 'experiments/2026-10-03-critb-v91-yaw/README.md',
            'clock_limit': 'GitHub server UTC versus scoring host UTC; clock synchronization is not proven.',
        }
        try:
            prepared = prepare_rotation(rotation_inputs, refetch=refetch)
            rotation_evidence.update(commitment=prepared['snapshot'],
                                     github_check='matched' if refetch else 'snapshot_only')
            if not utc(prepared['snapshot']['created_at']) < utc(now_utc()):
                raise ValueError('rotation commitment is not strictly before raw reading/scoring')
            rotation_report = None
        except INVALID as exc:
            prepared = None
            rotation_report = rotation_ineligible(str(exc))
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
        if rotation_addendum:
            raw_read_started = now_utc()
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
    except INVALID as exc:
        report = ineligible(str(exc))
        evidence['verified'] = False
    if rotation_addendum:
        if prepared is not None:
            try:
                if report['scope'] != 'HELD_OUT_VALIDATION':
                    raise ValueError('original v91 input/commitment audit ineligible: '+str(report.get('eligibility_reason')))
                scoring_started = now_utc()
                rotation_evidence.update(raw_read_started_at=raw_read_started, scoring_started_at=scoring_started)
                committed = utc(prepared['snapshot']['created_at'])
                if not (committed < utc(raw_read_started) <= utc(scoring_started)):
                    raise ValueError('rotation commitment is not strictly before raw reading/scoring')
                profile = rotation_profile(prepared['addendum'], prepared['candidate'], candidate, gate)
                prior = prepared['prior'] | set(candidate['previously_seen_pose_sha256'])
                rotation_report = score_rotation(cases, profile, prior, gate)
                frozen.verify_inputs([{'inputs': rotation_inputs}])
                rotation_evidence['verified'] = True
            except INVALID as exc:
                rotation_report = rotation_ineligible(str(exc))
            rotation_report.update(
                addendum_sha256=ROTATION_HASHES[str(ROTATION_ADDENDUM.relative_to(ROOT))],
                candidate_sha256=ROTATION_HASHES[str(ROTATION_CANDIDATE.relative_to(ROOT))],
                scoring_source=prepared['scoring_source'])
        # A raw/B-evidence mutation during yaw invalidates BOTH reports.
        try:
            frozen.verify_inputs([{'inputs': inputs}])
        except INVALID as exc:
            report = ineligible(str(exc))
            evidence['verified'] = False
            rotation_report = rotation_ineligible(str(exc))
            rotation_evidence['verified'] = False
        rotation_report['ordering_evidence'] = rotation_evidence
        rotation_report['input_files'] = list({(i['path'], i['sha256']): i
                                              for i in inputs + rotation_inputs}.values())
        report['rotation_addendum'] = rotation_report
        report['with_rotation_addendum'] = {
            'axis_pass': {**report['axis_pass'], 'rotate': rotation_report['pass']},
            'pass': frozen.combine([report['axis_pass']['forward'], report['axis_pass']['left'],
                                    rotation_report['pass']]),
            'rotation_scope': rotation_report['scope'],
            'rotation_maps_scored': rotation_report.get('maps_scored', []),
            'rotation_maps_not_scored': rotation_report.get('maps_not_scored', []),
            'scope_note': 'Separate B+r5 summary; forward/left PRE_COLLECTION, yaw '
                'PRE_SCORING_AND_READING_NOT_PRE_COLLECTION. Original B/r4 rotation remains null.',
        }
    report['ordering_evidence'] = evidence
    report['input_files'] = list({(i['path'], i['sha256']): i for i in inputs}.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, action='append', required=True,
                        help='one completed map collection (repeat for both maps)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refetch-commitment', action='store_true')
    parser.add_argument('--rotation-addendum', action='store_true',
                        help='also score the frozen r5 yaw addendum, with separate pre-scoring ordering')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if any(output.is_relative_to(collection_root(raw)) for raw in args.raw):
        raise ValueError('output must be outside every raw collection, including case parents')
    report = validate(args.raw, refetch=args.refetch_commitment, rotation_addendum=args.rotation_addendum)
    frozen.write(output, report)  # exclusive create; never overwrite
    print(json.dumps({k: report[k] for k in ('scope', 'axis_pass', 'pass')}))
    if args.rotation_addendum:
        print(json.dumps({'with_rotation_addendum': report['with_rotation_addendum']}))
    passed = report['with_rotation_addendum']['pass'] if args.rotation_addendum else report['pass']
    return 1 if passed is False else (0 if passed is True else 2)


if __name__ == '__main__':
    raise SystemExit(main())
