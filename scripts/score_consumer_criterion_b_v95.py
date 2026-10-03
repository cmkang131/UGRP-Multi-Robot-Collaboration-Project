"""Criterion B scoring adapter for the v95 acquisition: 새 시작점 검증 (new-start validation).

Offline only: no fitting, simulator, renderer, model call or raw mutation.
Frozen B (74c312b5...), r4, r5 and the rotation addendum are used unchanged;
every numerical step is a call into ``scripts.validate_consumer_criterion_b``
(``score``, ``evaluate_axis``, ``axis_supported``, ``combine``) with no copy.

Fail-closed provenance chain, all checked BEFORE any residual is computed:
1. #219 commitment (5968608872) and gate record (5968809408): committed
   snapshots pinned by sha256, live GitHub re-fetch must match (unedited).
2. Commitment body lists the full sha256 of the precheck ``binding.json``,
   ``precheck.json`` and ``SHA256SUMS.json``; actual bytes must match.
   ``binding.frozen_sha256`` carries the full B/r4/r5/addendum/validator
   hashes, which must equal the current bytes (recorded bytes only; the live
   ``binding()`` is never recomputed).
3. Each raw bundle digest / schedule bytes equal binding's per-map values; the
   four (map, robot) traces equal the precheck kinematic hashes; case
   ``result.json`` and ``artifacts.sha256.json`` bytes are listed in the gate record.
4. Chronology: commitment created before the earliest recorded collection
   start (including lock-acquisition lower bounds); gate record and the
   adapter-hash comment created before raw reading starts. The adapter-hash
   comment must be written by the repository owner and carry exactly one
   marker line ``V95_SCORING_ADAPTER_SHA256: <sha256 of this file>``.
4b. Every source file recorded in ``binding.source_sha256`` (271 files: the
   overlap module, v95 gate validator, exclusion list, v91 adapter,
   fit_unloaded_consumer, ...) is re-hashed against current bytes; the
   scoring checkout HEAD and ``git status --porcelain`` are recorded.
5. The frozen v95 kinematic gate (vs 38 priors) and the 6 mutual pairs are
   re-run in-process; any overlap is ineligible.

r2 loading is new code (``load_robot``). It mirrors the frozen r1 loader and is
checked at run time to reproduce ``frozen.load_case`` exactly for r1. Commands
are compared to ``measurement_by_robot[rid]`` as recorded; no loaded-era sign
change is applied to any robot.

Claims are limited to new start poses (world position, start yaw, axis order,
PRBS phase, both robots driven). The two maps share one command schedule and
are not independent samples. Not PF posterior, student control or physical success.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np

from harness import kinematic_overlap as ko
from scripts import validate_consumer_criterion_b as frozen
from scripts import validate_consumer_criterion_b_v91 as v91
from scripts import validate_consumer_criterion_b_v95 as gate95

ROOT = frozen.ROOT
RECORD = ROOT / 'experiments/2026-10-03-critb-v95-score'
REPO_API = 'repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/'
ISSUE_SUFFIX = '/repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219'
VALIDATION_KIND = '새 시작점 검증 (new-start validation)'
SOURCE = '2fe14826fc6b79f0121cfe6d7e6d8b4a1722957b'
BUNDLE = 'zone-final-pair-v95'
WORKFLOW = 'zone-final-pair-heldout-v95'
VERSION = '3.7.0'
MAPS = ('zone_wide_door_geometry_v3', 'zone_wide_corridor_final_v3')
ROBOTS = ('r1', 'r2')
ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False, 'teacher_only': True}
SNAPSHOTS = {
    'commitment': (RECORD / 'commitment_comment.json', 5968608872,
                   '3c441a391daee2105ed1edb22ad6c6e1b076e9e4bfeece1a90022aa490974040'),
    'gate': (RECORD / 'gate_comment.json', 5968809408,
             '12047fa7b93fdd70a7735c8be639692ada808bc4fa9b9f097f668d7106c7193b'),
}
FROZEN_FULL = {
    'experiments/2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json':
        '74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f',
    'experiments/2026-10-01-final-env-v87-calibration-fit/calibration_candidate_r4.json':
        'fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071',
    'experiments/2026-10-03-critb-rotation/calibration_candidate_r5_yaw.json':
        '978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97',
    'experiments/2026-10-03-critb-rotation/consumer_criterion_B_rotation.json':
        '6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08',
    'scripts/validate_consumer_criterion_b.py':
        '8d2a693a6e3bbca79a8214fd388bff79a0609400f07de831ad9be3cf22e85a88',
}
OWNER_LOGIN = 'cmkang131'
ADAPTER_MARKER = 'V95_SCORING_ADAPTER_SHA256:'
REQUIRED_SOURCES = ('harness/kinematic_overlap.py', 'scripts/validate_consumer_criterion_b_v95.py',
                    'configs/criterion_b_prior_kinematics_v95.json', 'scripts/validate_consumer_criterion_b_v91.py',
                    'scripts/fit_unloaded_consumer.py', 'scripts/fit_unloaded_hammerstein.py',
                    'scripts/validate_consumer_criterion_b.py')
UNVERIFIED = 'unverified acquisition chronology: no proof bound to criterion B, candidate and raw hashes'
INVALID = v91.INVALID


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def fetch_comment(comment_id):
    """Read-only GitHub fetch; any failure is a refusal, never a pass."""
    try:
        return json.loads(subprocess.check_output(['gh', 'api', REPO_API+str(comment_id)],
                                                  text=True, timeout=30, stderr=subprocess.PIPE))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError(f'GitHub comment {comment_id} unavailable') from exc


def check_comment(value, comment_id, label):
    if (value.get('id') != comment_id or not str(value.get('issue_url', '')).endswith(ISSUE_SUFFIX)
            or value.get('created_at') != value.get('updated_at')
            or not isinstance(value.get('body'), str)):
        raise ValueError(f'{label} comment identity/issue/edit mismatch')
    v91.utc(value['created_at'])


def verify_snapshot(role, inputs, fetch):
    path, comment_id, expected = SNAPSHOTS[role]
    blob = frozen.read_input(path, inputs)
    if frozen.sha(blob) != expected:
        raise ValueError(f'{role} snapshot hash mismatch')
    snap = json.loads(blob)
    check_comment(snap, comment_id, role)
    if frozen.sha(snap['body'].encode()) != snap['body_sha256']:
        raise ValueError(f'{role} snapshot body hash mismatch')
    remote = fetch(comment_id)
    for key in ('id', 'html_url', 'issue_url', 'created_at', 'updated_at', 'body'):
        if remote.get(key) != snap[key]:
            raise ValueError(f'GitHub {role} comment changed: {key}')
    check_owner(remote, role)
    return snap


def check_owner(value, label):
    if (value.get('author_association') != 'OWNER'
            or (value.get('user') or {}).get('login') != OWNER_LOGIN):
        raise ValueError(f'{label} comment is not by the repository owner')


def verify_adapter_comment(comment_id, fetch):
    """The owner posts ``V95_SCORING_ADAPTER_SHA256: <sha>`` on #219 before scoring."""
    remote = fetch(comment_id)
    check_comment(remote, comment_id, 'adapter')
    check_owner(remote, 'adapter')
    own = frozen.sha(Path(__file__).resolve().read_bytes())
    markers = [line.strip() for line in remote['body'].splitlines()
               if line.strip().startswith(ADAPTER_MARKER)]
    if markers != [f'{ADAPTER_MARKER} {own}']:
        raise ValueError('adapter comment needs exactly one marker line with this adapter sha256')
    return ({k: remote[k] for k in ('id', 'html_url', 'created_at', 'updated_at', 'author_association')}
            | {'author': remote['user']['login'], 'adapter_sha256': own})


def verify_sources(binding, inputs):
    """Re-hash every committed binding source; any drift refuses scoring."""
    recorded = binding.get('source_sha256')
    if not isinstance(recorded, dict) or not set(REQUIRED_SOURCES) <= set(recorded):
        raise ValueError('committed binding lacks required source hashes')
    changed = [name for name, expected in sorted(recorded.items())
               if frozen.sha(frozen.read_input(ROOT / name, inputs)) != expected]
    if changed:
        raise ValueError('source changed since the committed precheck: '+', '.join(changed[:5]))
    return len(recorded)


def checkout_state():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=30)
    try:
        return {'head': git('rev-parse', 'HEAD').strip(),
                'status_porcelain': git('status', '--porcelain', '--untracked-files=all').splitlines()}
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('scoring checkout state unavailable') from exc


def verify_precheck(directory, commitment_body, inputs):
    directory = Path(directory).resolve()
    blobs = {name: frozen.read_input(directory / name, inputs)
             for name in ('precheck.json', 'binding.json', 'SHA256SUMS.json')}
    hashes = {name: frozen.sha(blob) for name, blob in blobs.items()}
    for name, digest in hashes.items():
        if digest not in commitment_body:
            raise ValueError(f'precheck {name} sha256 not in #219 commitment')
    sums = json.loads(blobs['SHA256SUMS.json'])
    if sums.get('precheck.json') != hashes['precheck.json'] or sums.get('binding.json') != hashes['binding.json']:
        raise ValueError('precheck SHA256SUMS does not bind precheck/binding')
    precheck, binding = json.loads(blobs['precheck.json']), json.loads(blobs['binding.json'])
    v91.require_fields(precheck, {'schema': 'ugrp.heldout_v95_precheck.v1', 'status': 'PRECHECK_PASS',
                                  'collection': False, 'rendering': False}, 'precheck')
    if precheck.get('criterion_B_pass') is not None or set(precheck['maps']) != set(MAPS):
        raise ValueError('precheck scope mismatch')
    if precheck.get('binding_sha256') != hashes['binding.json']:
        raise ValueError('precheck/binding hash mismatch')
    for name, expected in FROZEN_FULL.items():
        if binding['frozen_sha256'].get(name) != expected:
            raise ValueError('committed binding lacks frozen hash: '+name)
        if frozen.sha(frozen.read_input(ROOT / name, inputs)) != expected:
            raise ValueError('frozen file changed: '+name)
    return precheck, binding, hashes


def load_robot(folder, gate, rid):
    """Frozen ``load_case`` checks for one robot (r2 path is new code).

    Must equal ``frozen.load_case`` for r1; ``score`` asserts this at run time.
    Issued commands are compared to the recorded per-robot measurement as is.
    """
    if rid not in ROBOTS:
        raise ValueError('unknown robot')
    folder = Path(folder)
    inputs = []

    def read(path):
        return frozen.read_input(path, inputs)

    bundle = json.loads(read(folder / 'bundle.json'))
    result = json.loads(read(folder / 'result.json'))
    frozen.check_completion(result)
    if (bundle.get('execution_bundle_id') != gate['held_out']['execution_bundle_id']
            or bundle.get('check') != gate['held_out']['check']):
        raise ValueError('criterion B requires the registered unloaded collection')
    plan = bundle['measurement_by_robot'][rid]
    if rid == 'r1' and plan != bundle['measurement']:
        raise ValueError('r1 per-robot measurement differs from bundle measurement')
    if (plan.get('check') != bundle['check'] or plan.get('map_id') != bundle['map_id']
            or plan.get('robot_id', rid) != rid):
        raise ValueError('recorded measurement identity mismatch')
    if not frozen.re.fullmatch('[0-9a-f]{40}', str(bundle.get('source_sha', ''))):
        raise ValueError('missing acquisition source SHA')
    if result.get('check') != bundle['check'] or result.get('case', {}).get('map_id') != bundle['map_id']:
        raise ValueError('case result / measurement identity mismatch')
    for record in (bundle, plan, result):
        if 'case' in record and record['case'].get('map_id') != bundle['map_id']:
            raise ValueError('nested case map identity mismatch')
        if 'map_id' in record and record['map_id'] != bundle['map_id']:
            raise ValueError('recorded map identity mismatch')
        if 'load_state' in record and record['load_state'] != 'unloaded':
            raise ValueError('recorded load condition mismatch')
    if (bundle.get('robot_model') != 'masterpi_v3' or bundle.get('render_profile') != 'floor_light_v1'
            or bundle.get('weld') != 'off' or bundle.get('contact_profile') != 'cargo_noslip_v1'):
        raise ValueError('wrong physical/render configuration')
    dt = gate['pf_step_s']
    if plan['control_period_s'] != dt or plan.get('eval_pose_period_s', dt) != dt:
        raise ValueError('0.05 s commands/poses required')
    pose_blob = read(folder / f'eval_only/{rid}/pose.jsonl')
    pose = frozen.rows(pose_blob)
    for row in pose:
        if (row.get('requested_check') != bundle['check']
                or ('map_id' in row and row['map_id'] != bundle['map_id'])
                or ('load_state' in row and row['load_state'] != 'unloaded')):
            raise ValueError('pose collection identity mismatch')
    t = np.asarray([r['t'] for r in pose], float)
    xyz = np.asarray([r['base_position_m'] for r in pose], float)
    rotation = np.asarray([r['base_rotation'] for r in pose], float)
    if (len(t) < 2 or not np.isfinite(t).all() or xyz.shape != (len(t), 3)
            or rotation.shape != (len(t), 3, 3) or not np.isfinite(xyz).all()
            or not np.isfinite(rotation).all()
            or not np.allclose(rotation.transpose(0, 2, 1) @ rotation, np.eye(3), atol=1e-5)
            or not np.allclose(np.linalg.det(rotation), 1., atol=1e-5)
            or [r['sample_index'] for r in pose] != list(range(len(t)))
            or not np.allclose(np.diff(t), dt, atol=1e-8, rtol=0)):
        raise ValueError('invalid / missing / irregular pose samples')
    if not np.isclose(t[-1]-t[0], result['check_sim_s'], atol=1e-6, rtol=0):
        raise ValueError('pose duration differs from completion record')
    expected, segments, required_ticks = frozen.plan_arrays(plan, len(t)-1, dt, include_required_ticks=True)
    commands = frozen.rows(read(folder / f'robots/{rid}/commands.jsonl'))
    issued, seen = np.zeros_like(expected), set()
    for row in commands:
        if row['kind'] != 'mecanum':
            continue
        tick = (float(row['t'])-t[0])/dt
        j = round(tick)
        if (not np.isclose(tick, j, atol=2e-6, rtol=0) or j in seen or not 0 <= j < len(issued)
                or not np.isclose(row['duration_s'], dt, atol=1e-9, rtol=0)):
            raise ValueError('duplicate/off-grid command, invalid lease or command clock')
        seen.add(j)
        issued[j] = [row[a] for a in frozen.COMMAND_AXES]
    if not required_ticks.issubset(seen):
        raise ValueError('missing scheduled command ticks (including zero/coast)')
    if not np.array_equal(issued, expected):
        raise ValueError('issued commands differ from recorded measurement schedule')
    yaw = np.unwrap(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
    return {'u': issued, 'pose': np.column_stack((xyz[:, :2], yaw)), 'dt': dt,
            'segments': segments, 'map_id': bundle['map_id'], 'folder': str(folder.resolve()),
            'training': False, 'pose_sha256': frozen.sha(pose_blob), 'inputs': inputs,
            'source_sha': bundle.get('source_sha'), 'robot_id': rid}


def same_case(a, b):
    return (np.array_equal(a['u'], b['u']) and np.array_equal(a['pose'], b['pose'])
            and a['segments'] == b['segments'] and a['pose_sha256'] == b['pose_sha256']
            and a['map_id'] == b['map_id'] and a['dt'] == b['dt'])


def loader_gate(gate):
    adapted = copy.deepcopy(gate)
    adapted['held_out']['execution_bundle_id'] = BUNDLE
    return adapted


def load_map(raw, gate, binding, precheck, precheck_sha, commitment, gate_body, inputs):
    root = v91.collection_root(raw)
    plan = v91.read_json(root / 'plan.json', inputs)
    result = v91.read_json(root / 'result.json', inputs)
    v91.require_fields(plan, {**ROLE, 'execution_bundle_id': BUNDLE, 'check': 'calibration-unloaded',
                              'source_sha': SOURCE, 'seed': 911, 'execution_started': True,
                              'denominator': 1, 'runnable': True, 'blocked_on': []}, 'plan')
    v91.require_fields(result, {**ROLE, 'denominator': 1}, 'collection result')
    if (plan.get('precheck_sha256') != precheck_sha
            or plan.get('commitment', {}).get('id') != commitment['id']
            or plan['commitment'].get('created_at') != commitment['created_at']):
        raise ValueError('collection plan does not bind the committed precheck/#219 commitment')
    folders = sorted({p.parents[2] for p in root.rglob('eval_only/r1/pose.jsonl')})
    if len(folders) != 1 or folders[0].parent != root:
        raise ValueError('v95 requires exactly one direct case per map collection')
    folder = folders[0]
    bundle = v91.read_json(folder / 'bundle.json', inputs)
    case_blob = frozen.read_input(folder / 'result.json', inputs)
    case_result = json.loads(case_blob)
    map_id = bundle.get('map_id')
    if map_id not in MAPS or map_id not in gate['held_out']['allowed_maps']:
        raise ValueError('unregistered map is not held-out')
    v91.require_fields(bundle, {**ROLE, 'execution_bundle_id': BUNDLE, 'workflow_id': WORKFLOW,
                                'workflow_version': VERSION, 'source_sha': SOURCE, 'seed': 911}, 'bundle')
    v91.require_fields(case_result, ROLE, 'case result')
    bare = {k: v for k, v in bundle.items() if k not in ('source_sha', 'case')}
    if ko.digest(bare) != binding['bundle_sha256'][map_id]:
        raise ValueError('raw bundle differs from the committed precheck binding')
    if plan['bundles_sha256'] != [ko.digest(bundle)] or plan['cases'] != [bundle['case']]:
        raise ValueError('plan/bundle binding mismatch')
    schedule = frozen.read_input(folder / 'inputs/schedule.json', inputs)
    if frozen.sha(schedule) != binding['schedule_sha256'][map_id]:
        raise ValueError('recorded schedule bytes differ from the committed binding')
    artifacts_blob = frozen.read_input(folder / 'artifacts.sha256.json', inputs)
    for label, blob in (('case result.json', case_blob), ('artifacts.sha256.json', artifacts_blob)):
        if frozen.sha(blob) not in gate_body:
            raise ValueError(f'{label} sha256 not in #219 gate record')
    adapted = loader_gate(gate)
    reference = frozen.load_collection(raw, adapted)
    if len(reference) != 1:
        raise ValueError('frozen loader case count mismatch')
    cases = []
    for rid in ROBOTS:
        case = load_robot(folder, adapted, rid)
        if rid == 'r1' and not same_case(case, reference[0]):
            raise ValueError('r1 loader differs from frozen load_case')
        trace = ko.read_trace(folder / f'eval_only/{rid}/pose.jsonl')
        if trace.sha256 != precheck['maps'][map_id]['motion'][rid]['kinematic_sha256']:
            raise ValueError(f'{map_id}/{rid} trajectory differs from the committed precheck')
        case['trace'] = trace
        cases.append(case)
    for case in cases + reference:
        inputs.extend(case['inputs'])
    artifacts = json.loads(artifacts_blob)
    for item in inputs:
        path = Path(item['path'])
        if path.is_relative_to(folder) and path.name != 'artifacts.sha256.json':
            if artifacts.get(str(path.relative_to(folder))) != item['sha256']:
                raise ValueError('raw artifact receipt mismatch: '+str(path))
    stamps = v91.start_records([(root / 'plan.json', plan), (root / 'result.json', result),
                                (folder / 'result.json', case_result)])
    return cases, stamps


def kinematic_gate(cases):
    traces = [case['trace'] for case in cases]
    prior = gate95.load_prior()
    against_prior = ko.audit(traces, prior)
    mutual = [{'a': a.source, 'b': b.source, 'witness': ko.overlap(a, b)}
              for a, b in itertools.combinations(traces, 2)]
    status = ('DISJOINT' if against_prior['status'] == 'DISJOINT' and not any(m['witness'] for m in mutual)
              else 'PREVIOUSLY_SEEN')
    return {'status': status, 'prior_comparisons': len(against_prior['comparisons']),
            'prior_status': against_prior['status'], 'mutual_pairs': len(mutual),
            'mutual_overlaps': [m for m in mutual if m['witness']], 'policy': ko.POLICY}


def score(cases, candidate, gate, *, chronology_verified):
    """Frozen score verbatim per (map, robot); lift ONLY its chronology veto."""
    report = frozen.score(cases, candidate, gate)
    for data, case in zip(cases, report['cases']):
        case['robot_id'] = data['robot_id']
        if chronology_verified and case['eligibility_reason'] == UNVERIFIED:
            case.update(scope='HELD_OUT_VALIDATION', eligibility_reason=None)
            for axis in case['axes'].values():
                if axis['metrics'] is not None:
                    axis['pass'] = axis['numerical_pass']
                    axis['reason'] = None
        for axis in case['axes'].values():
            if axis['metrics'] is not None:
                axis['split_pass'] = {split: all(r['numerical_pass'] for r in rows.values())
                                      for split, rows in axis['metrics'].items()}
    report['axis_pass'] = {a: frozen.combine([r['axes'][a]['pass'] for r in report['cases']])
                           for a in frozen.AXES}
    report['pass'] = frozen.combine(list(report['axis_pass'].values()))
    return report


def score_rotation(cases, profile, prior, gate):
    results = []
    for case in cases:
        row = {'raw': case['folder'], 'map_id': case['map_id'], 'robot_id': case['robot_id'],
               'pass': None, 'metrics': None,
               'reason': 'no frozen candidate or missing signed steps/PRBS/horizon support'}
        if case['pose_sha256'] in prior:
            row.update(reason='PREVIOUSLY_SEEN_POSE_BYTES')
        elif profile is not None and frozen.axis_supported(case, 2, gate):
            summary = frozen.evaluate_axis(case, 2, profile, gate)
            passed = all(r['numerical_pass'] for r in frozen.all_rows(summary))
            row.update({'metrics': summary, 'numerical_pass': passed, 'pass': passed, 'reason': None,
                        'split_pass': {s: all(r['numerical_pass'] for r in rows.values())
                                       for s, rows in summary.items()}})
        results.append(row)
    return {'cases': results, 'pass': frozen.combine([r['pass'] for r in results])}


def ineligible(reason):
    return {'schema': 'ugrp.consumer_B_validation.v95', 'validation_kind': VALIDATION_KIND,
            'criterion_sha256': frozen.CRITERION_SHA256, 'criterion_A': 'FAILED_NOT_RESCORED',
            'candidate_status': 'CANDIDATE_UNVALIDATED', 'scope': 'INELIGIBLE',
            'eligibility_reason': reason, 'cases': [], 'axis_pass': dict.fromkeys(frozen.AXES),
            'pass': None, 'with_rotation_addendum': {'axis_pass': dict.fromkeys(frozen.AXES), 'pass': None}}


def validate(raws, precheck_dir, adapter_comment_id, *, fetch=fetch_comment):
    inputs, evidence = [], {'verified': False}
    try:
        commitment = verify_snapshot('commitment', inputs, fetch)
        gate_record = verify_snapshot('gate', inputs, fetch)
        adapter = verify_adapter_comment(adapter_comment_id, fetch)
        precheck, binding, precheck_hashes = verify_precheck(precheck_dir, commitment['body'], inputs)
        source_count = verify_sources(binding, inputs)
        checkout = checkout_state()
        gate = frozen.criterion()
        candidate = v91.read_json(frozen.CANDIDATE, inputs)
        r5 = v91.read_json(ROOT / 'experiments/2026-10-03-critb-rotation/calibration_candidate_r5_yaw.json', inputs)
        addendum = v91.read_json(ROOT / 'experiments/2026-10-03-critb-rotation/consumer_criterion_B_rotation.json', inputs)
        profile = v91.rotation_profile(addendum, r5, candidate, gate)
        raw_read_started = now_utc()
        for label, stamp in (('gate record', gate_record['created_at']),
                             ('adapter comment', adapter['created_at'])):
            if not v91.utc(stamp) < v91.utc(raw_read_started):
                raise ValueError(f'{label} is not strictly before raw reading')
        if len(raws) != len(MAPS):
            raise ValueError('both v95 map collections are required')
        cases, stamps = [], []
        for raw in raws:
            loaded, recorded = load_map(raw, gate, binding, precheck, precheck_hashes['precheck.json'],
                                        commitment, gate_record['body'], inputs)
            cases.extend(loaded)
            stamps.extend(recorded)
        keys = [(c['map_id'], c['robot_id']) for c in cases]
        if sorted(keys) != sorted(itertools.product(MAPS, ROBOTS)):
            raise ValueError('need exactly one case per (map, robot)')
        earliest = min(stamps, key=lambda s: v91.utc(s['utc']))
        if not v91.utc(commitment['created_at']) < v91.utc(earliest['utc']):
            raise ValueError('commitment is not strictly before the earliest recorded collection start')
        kinematics = kinematic_gate(cases)
        if kinematics['status'] != 'DISJOINT':
            raise ValueError('PREVIOUSLY_SEEN_KINEMATICS')
        prior = set(candidate['previously_seen_pose_sha256']) | set(r5['previously_seen_pose_sha256'])
        if any(c['pose_sha256'] in prior for c in cases):
            raise ValueError('previously seen raw pose bytes')
        evidence.update(commitment={k: commitment[k] for k in ('id', 'html_url', 'created_at')},
                        gate_record={k: gate_record[k] for k in ('id', 'html_url', 'created_at')},
                        adapter_comment=adapter, precheck_sha256=precheck_hashes,
                        raw_read_started=raw_read_started, recorded_starts=stamps, earliest=earliest,
                        kinematic_gate=kinematics, rotation_ordering='PRE_COLLECTION',
                        sources_rehashed=source_count, scoring_checkout=checkout,
                        clock_limit='GitHub server UTC versus runner/scoring host UTC; not signed raw.')
        report = score(cases, candidate, gate, chronology_verified=True)
        rotation = score_rotation(cases, profile, prior, gate)
        frozen.verify_inputs([{'inputs': inputs}])
        evidence['verified'] = True
        report.update(schema='ugrp.consumer_B_validation.v95', validation_kind=VALIDATION_KIND,
                      scope=('HELD_OUT_VALIDATION' if all(r['scope'] == 'HELD_OUT_VALIDATION'
                             for r in report['cases']) else 'INELIGIBLE'),
                      candidate_sha256=FROZEN_FULL[str(frozen.CANDIDATE.relative_to(ROOT))],
                      rotation_addendum=rotation,
                      with_rotation_addendum={
                          'axis_pass': {**report['axis_pass'], 'rotate': rotation['pass']},
                          'pass': frozen.combine([report['axis_pass']['forward'],
                                                  report['axis_pass']['left'], rotation['pass']])},
                      scope_note=('Frozen B offline process-budget coverage on four new-start trajectories '
                                  '(2 maps x 2 robots), decided per (map, robot) and per split/horizon, never pooled. '
                                  'Both maps share one command schedule and are not independent samples; command '
                                  'levels equal training. r5 (yaw) was fitted on v88 unloaded r1, so yaw는 새 명령이 '
                                  '아니라 새 세계 좌표·시작 yaw·순서·위상의 검증이다. Not PF posterior, student control '
                                  'or physical success.'))
    except INVALID as exc:
        report = ineligible(str(exc))
        evidence['verified'] = False
    report['ordering_evidence'] = evidence
    report['input_files'] = list({(i['path'], i['sha256']): i for i in inputs}.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, action='append', required=True,
                        help='one completed v95 map collection (repeat for both maps)')
    parser.add_argument('--precheck', type=Path, required=True)
    parser.add_argument('--adapter-comment', type=int, required=True,
                        help='#219 comment id that lists this adapter sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if any(output.is_relative_to(v91.collection_root(raw)) for raw in args.raw):
        raise ValueError('output must be outside every raw collection')
    report = validate(args.raw, args.precheck, args.adapter_comment)
    frozen.write(output, report)  # exclusive create; never overwrite
    summary = {'scope': report['scope'], 'validation_kind': VALIDATION_KIND,
               'axis_pass': report['axis_pass'], 'pass': report['pass'],
               'with_rotation_addendum': report['with_rotation_addendum']}
    print(json.dumps(summary, ensure_ascii=False))
    passed = report['with_rotation_addendum']['pass']
    return 1 if passed is False else (0 if passed is True else 2)


if __name__ == '__main__':
    raise SystemExit(main())
