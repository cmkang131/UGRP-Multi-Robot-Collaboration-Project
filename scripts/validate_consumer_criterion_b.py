"""Offline criterion B scorer for NEW raw collections; never fits parameters.

Run with ``python -m scripts.validate_consumer_criterion_b --raw PATH --output NEW.json``.
v89 is recognized automatically as TRAINING_SMOKE, never held-out validation.
No simulator, renderer, controller, image or model inference is imported/run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from scripts import fit_unloaded_consumer as c
from scripts.fit_unloaded_hammerstein import COLLECTION_SHA, PLAN, RECORD, ROOT, rows, sha, write

FOLDER = ROOT / RECORD
CRITERION = FOLDER / 'consumer_criterion_B.json'
CRITERION_SHA256 = '74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f'
CANDIDATE = FOLDER / 'calibration_candidate_r4.json'
AXES = ('forward', 'left', 'rotate')
COMMAND_AXES = ('forward', 'left', 'turn')


def criterion():
    blob = CRITERION.read_bytes()
    if sha(blob) != CRITERION_SHA256:
        raise ValueError('frozen criterion B hash mismatch')
    return json.loads(blob)


def plan_arrays(plan, n, dt):
    """Return exact issued-input expectation and complete step/PRBS regions."""
    def ticks(seconds):
        k = round(seconds / dt)
        if seconds < 0 or not np.isclose(k * dt, seconds, atol=1e-9, rtol=0):
            raise ValueError('schedule is not on the PF sample grid')
        return k

    cursor = ticks(plan.get('initial_hold_s', plan.get('motion_start_s', 0.)))
    expected = np.zeros((n, 3))
    bounds = []
    for segment in plan['segments']:
        end = cursor + ticks(segment['duration_s'])
        if end <= cursor or end > n or segment['axis'] not in COMMAND_AXES:
            raise ValueError('invalid or truncated schedule')
        if segment['phase'] not in ('step', 'prbs', 'coast'):
            raise ValueError('unknown motion phase')
        value = float(segment['value'])
        if not np.isfinite(value) or abs(value) > .03:
            raise ValueError('unloaded command outside frozen fit range')
        expected[cursor:end, COMMAND_AXES.index(segment['axis'])] = value
        bounds.append((cursor, end, segment))
        cursor = end
    segments = {a: {'steps': [], 'prbs': []} for a in AXES}
    j = 0
    while j < len(bounds):
        start, end, s = bounds[j]
        name = AXES[COMMAND_AXES.index(s['axis'])]
        phase = s['phase']
        if phase == 'coast':
            raise ValueError('unattached coast segment')
        j += 1
        if phase == 'prbs':
            while j < len(bounds) and bounds[j][2]['phase'] == 'prbs' and bounds[j][2]['axis'] == s['axis']:
                end = bounds[j][1]
                j += 1
        if j < len(bounds) and bounds[j][2]['phase'] == 'coast' and bounds[j][2]['axis'] == s['axis']:
            if bounds[j][2]['value'] != 0:
                raise ValueError('coast must issue zero')
            end = bounds[j][1]
            j += 1
        segments[name]['steps' if phase == 'step' else 'prbs'].append((start, end))
    return expected, segments


def load_case(folder, gate):
    """Audit clocks, leases and recorded schedule before any residual scoring."""
    folder = Path(folder)
    inputs = []

    def read(path):
        blob = path.read_bytes()
        inputs.append({'path': str(path.resolve()), 'sha256': sha(blob), 'bytes': len(blob)})
        return blob

    bundle = json.loads(read(folder / 'bundle.json'))
    result = json.loads(read(folder / 'result.json'))
    if result.get('protocol_complete') is not True or result.get('status') != 'COLLECTED_UNQUALIFIED':
        raise ValueError('incomplete collection / HOST_ERROR')
    is_training = bundle.get('execution_bundle_id') == 'zone-final-environment-v89'
    if is_training:
        if bundle.get('check') != 'calibration-motion-v2':
            raise ValueError('wrong v89 collection check')
        plan = json.loads(subprocess.check_output(['git', 'show', f'{COLLECTION_SHA}:{PLAN}'], cwd=ROOT))
    else:
        if (bundle.get('execution_bundle_id') != gate['held_out']['execution_bundle_id']
                or bundle.get('check') != gate['held_out']['check']):
            raise ValueError('criterion B requires a v88 unloaded collection')
        plan = bundle['measurement']
        if plan.get('check') != bundle['check'] or plan.get('map_id') != bundle['map_id']:
            raise ValueError('recorded measurement identity mismatch')
        if not re.fullmatch('[0-9a-f]{40}', str(bundle.get('source_sha', ''))):
            raise ValueError('missing acquisition source SHA')
    if (bundle.get('robot_model') != 'masterpi_v3' or bundle.get('render_profile') != 'floor_light_v1'
            or bundle.get('weld') != 'off' or bundle.get('contact_profile') != 'cargo_noslip_v1'):
        raise ValueError('wrong physical/render configuration')
    dt = gate['pf_step_s']
    if plan['control_period_s'] != dt or plan.get('eval_pose_period_s', dt) != dt:
        raise ValueError('0.05 s commands/poses required')
    pose_blob = read(folder / 'eval_only/r1/pose.jsonl')
    pose = rows(pose_blob)
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
    expected, segments = plan_arrays(plan, len(t)-1, dt)
    commands = rows(read(folder / 'robots/r1/commands.jsonl'))
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
        issued[j] = [row[a] for a in COMMAND_AXES]
    if not np.array_equal(issued, expected):
        raise ValueError('issued commands differ from recorded measurement schedule')
    yaw = np.unwrap(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
    return {'u': issued, 'pose': np.column_stack((xyz[:, :2], yaw)), 'dt': dt,
            'segments': segments, 'map_id': bundle['map_id'], 'folder': str(folder.resolve()),
            'training': is_training, 'pose_sha256': sha(pose_blob), 'inputs': inputs,
            'source_sha': bundle.get('source_sha', COLLECTION_SHA if is_training else None)}


def load_collection(raw, gate):
    raw = Path(raw)
    folders = sorted({p.parents[2] for p in raw.rglob('eval_only/r1/pose.jsonl')})
    if not folders:
        raise ValueError('no raw eval_only/r1/pose.jsonl')
    # Do not silently ignore an unattempted/missing case in a collection root.
    if raw not in folders:
        root_result = json.loads((raw / 'result.json').read_bytes())
        if (root_result.get('status') == 'HOST_ERROR' or root_result.get('unattempted')
                or root_result.get('source_unchanged') is False):
            raise ValueError('incomplete collection root')
        if 'denominator' in root_result and root_result['denominator'] != len(folders):
            raise ValueError('collection denominator differs from raw cases')
    return [load_case(folder, gate) for folder in folders]


def axis_supported(data, axis, gate):
    for split in ('steps', 'prbs'):
        spans = data['segments'][AXES[axis]][split]
        if not spans:
            return False
        driven = np.concatenate([data['u'][a:b, axis] for a, b in spans])
        if not (np.any(driven > 0) and np.any(driven < 0)):
            return False
        if any(not any(b-a >= round(h/data['dt']) for a, b in spans) for h in gate['horizons_s']):
            return False
    return True


def metrics(error, covariance, gate):
    variance = np.diagonal(covariance, axis1=1, axis2=2)
    if (not np.isfinite(error).all() or not np.isfinite(covariance).all()
            or np.any(variance <= 0)):
        raise ValueError('non-finite error or nonpositive process variance')
    sigma = np.sqrt(variance)
    normalized = np.abs(error)/sigma
    p95 = np.percentile(normalized, 95, axis=0)
    coverage2 = np.mean(normalized <= 2., axis=0)
    passed = (p95 <= gate['acceptance']['normalized_abs_error_p95_max']) & (
        coverage2 >= gate['acceptance']['coverage_2sigma_min'])
    return {'n': len(error), 'p95_abs_error': np.percentile(np.abs(error), 95, axis=0).tolist(),
            'sigma_min_median_max': np.percentile(sigma, [0, 50, 100], axis=0).T.tolist(),
            'normalized_abs_error_p95': p95.tolist(),
            'coverage_1sigma': np.mean(normalized <= 1., axis=0).tolist(),
            'coverage_2sigma': coverage2.tolist(),
            'mean_NEES_per_component': np.mean(error**2/variance, axis=0).tolist(),
            'mean_joint_NEES': float(np.mean(np.einsum('ni,ni->n', error,
                np.linalg.solve(covariance, error[..., None])[..., 0]))),
            'component_pass': passed.tolist(), 'numerical_pass': bool(np.all(passed))}


def evaluate_axis(data, axis, profile, gate):
    increments = c.legacy_increments(data, profile)
    summaries = {}
    for split, spans in data['segments'][AXES[axis]].items():
        summaries[split] = {}
        for h in gate['horizons_s']:
            starts, k = c.windows(spans, h, data['dt'])
            predicted, covariance = c.legacy_windows(increments, starts, k, data['dt'], profile, scale=False)
            error = predicted-c.endpoint_targets(data['pose'], starts, k)
            error[:, 2] = np.arctan2(np.sin(error[:, 2]), np.cos(error[:, 2]))
            summaries[split][str(h)] = metrics(error, covariance, gate)
    return summaries


def all_rows(summaries):
    return [row for split in summaries.values() for row in split.values()]


def combine(decisions):
    return False if False in decisions else (None if None in decisions else True)


def score(cases, candidate, gate):
    if candidate['criterion_sha256'] != CRITERION_SHA256 or candidate['status'] != 'CANDIDATE_UNVALIDATED':
        raise ValueError('candidate criterion/status mismatch')
    prior = set(candidate['previously_seen_pose_sha256'])
    results = []
    for data in cases:
        reason = None
        if data['training']:
            reason = 'all v89 data is training, never validation'
        elif data['pose_sha256'] in prior:
            reason = 'previously seen raw pose bytes'
        elif data['map_id'] not in gate['held_out']['allowed_maps']:
            reason = 'not a new held-out map (v89 training map excluded)'
        axes = {}
        for axis, name in enumerate(AXES):
            model = candidate['candidate_axes'][name]
            if model is None or not axis_supported(data, axis, gate):
                axes[name] = {'pass': None, 'metrics': None,
                              'reason': 'no frozen candidate or missing signed steps/PRBS/horizon support'}
                continue
            summary = evaluate_axis(data, axis, model['consumer_fields'], gate)
            numerical = all(row['numerical_pass'] for row in all_rows(summary))
            axes[name] = {'pass': None if reason else numerical, 'metrics': summary,
                          'numerical_pass': numerical, 'reason': reason}
        results.append({'raw': data['folder'], 'map_id': data['map_id'],
                        'scope': 'TRAINING_SMOKE' if data['training'] else ('INELIGIBLE' if reason else 'HELD_OUT'),
                        'eligibility_reason': reason, 'axes': axes})
    decisions = {a: combine([r['axes'][a]['pass'] for r in results]) for a in AXES}
    return {'schema': 'ugrp.consumer_B_validation.v1', 'criterion_sha256': CRITERION_SHA256,
            'criterion_A': 'FAILED_NOT_RESCORED', 'cases': results,
            'axis_pass': decisions, 'pass': combine(list(decisions.values())),
            'candidate_status': 'CANDIDATE_UNVALIDATED',
            'scope_note': 'Offline process-budget coverage only, not PF posterior or robot success. '
                          'A new raw acquisition after criterion freeze is required; hashes cannot prove collection chronology.'}


def verify_inputs(cases):
    for data in cases:
        for item in data['inputs']:
            if sha(Path(item['path']).read_bytes()) != item['sha256']:
                raise ValueError('raw input changed during validation: '+item['path'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.raw.resolve()):
        raise ValueError('output must be outside raw')
    gate = criterion()
    candidate_blob = CANDIDATE.read_bytes()
    frozen_report = json.loads((FOLDER / 'consumer_report_r4.json').read_bytes())
    if sha(candidate_blob) != frozen_report['candidate_sha256']:
        raise ValueError('frozen r4 candidate hash mismatch')
    candidate = json.loads(candidate_blob)
    cases = load_collection(args.raw, gate)
    report = score(cases, candidate, gate)
    verify_inputs(cases)
    report['candidate_sha256'] = sha(candidate_blob)
    report['input_files'] = [f for case in cases for f in case['inputs']]
    write(args.output, report)
    print(json.dumps({'axis_pass': report['axis_pass'], 'pass': report['pass'],
                      'scopes': [case['scope'] for case in report['cases']]}))
    return 1 if report['pass'] is False else (0 if report['pass'] is True else 2)


if __name__ == '__main__':
    raise SystemExit(main())
