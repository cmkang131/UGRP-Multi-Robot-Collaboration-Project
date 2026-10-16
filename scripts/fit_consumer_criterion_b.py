"""Fit the r4 candidate on ALL v89 data; does not validate or promote it."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import least_squares

from scripts import validate_consumer_criterion_b as b
from scripts.fit_unloaded_hammerstein import require_disjoint_output, sha, write


def profile(axis, parameters, gate):
    gain, running, stopping = parameters
    matrix = np.zeros((3, 3))
    matrix[axis, axis] = gain
    return {'gain': matrix.tolist(), 'tau_s': float(running), 'tau_stop_s': float(stopping),
            'noise_rel': gate['noise']['floor_noise_rel'], 'noise_abs': gate['noise']['floor_noise_abs'],
            'scale_std': 0., 'scale_walk': 0., 'use_scale': False, 'rest_noise': True}


def fit_mean(data, axis, gate):
    samples = []
    for spans in data['segments'][b.AXES[axis]].values():
        for h in gate['horizons_s']:
            starts, k = b.c.windows(spans, h, data['dt'])
            samples.append((starts, k, b.c.endpoint_targets(data['pose'], starts, k)[:, axis]))

    def residual(theta):
        increments = b.c.legacy_increments(data, profile(axis, np.exp(theta), gate))
        p = np.r_[0., np.cumsum(increments[:, axis])]
        return np.concatenate([p[s+k]-p[s]-target for s, k, target in samples])

    lower, upper = np.log([.05, .01, .005]), np.log([4., 4., .5])
    opt = least_squares(residual, np.log([1., .8, .06]), bounds=(lower, upper),
                        max_nfev=150, ftol=1e-10, xtol=1e-10, gtol=1e-10)
    rank = int(np.linalg.matrix_rank(opt.jac))
    boundary = [name for name, val, lo, hi in zip(('gain', 'tau_s', 'tau_stop_s'), opt.x, lower, upper)
                if min(val-lo, hi-val) < 1e-4]
    if not opt.success or rank != 3 or boundary:
        raise ValueError('mean optimizer/rank/boundary failure')
    return {'parameters': dict(zip(('gain', 'tau_s', 'tau_stop_s'), np.exp(opt.x).tolist())),
            'consumer_fields': profile(axis, np.exp(opt.x), gate),
            'scope': 'axis-only unloaded; other mean axes set to zero, not calibrated',
            'allowed_command_axis': b.COMMAND_AXES[axis],
            'optimizer': {'success': bool(opt.success), 'rank': rank, 'boundary': boundary,
                          'nfev': opt.nfev, 'residual_count': len(opt.fun),
                          'rmse': float(np.sqrt(np.mean(opt.fun**2)))},
            'validation': None}


def fit_training(data, gate):
    candidates, training = {}, {}
    for axis, name in enumerate(b.AXES):
        if not b.axis_supported(data, axis, gate):
            candidates[name], training[name] = None, None
            continue
        model = fit_mean(data, axis, gate)
        candidates[name] = model
    noise = minimum_noise(data, candidates, gate)
    for axis, name in enumerate(b.AXES):
        model = candidates[name]
        if model is None:
            continue
        model['consumer_fields']['noise_abs'] = noise['noise_abs']
        model['noise_selection'] = noise
        summaries = b.evaluate_axis(data, axis, model['consumer_fields'], gate)
        minimum = min(min(row['coverage_2sigma']) for row in b.all_rows(summaries))
        if minimum < .95:
            raise ValueError('minimal noise solution failed independent covariance coverage check')
        model['minimum_training_2sigma_coverage'] = minimum
        training[name] = summaries
    return candidates, training


def noise_groups(data, candidates, gate):
    """Quadratic diagonal-variance terms, independent of legacy_windows.

    For a zero-yaw axis-only mean, heading noise from tick r changes position
    at LATER ticks only. This keeps the existing Euler covariance ordering.
    """
    groups = []
    dt = data['dt']
    for axis, name in enumerate(b.AXES):
        if candidates[name] is None:
            continue
        delta = b.c.legacy_increments(data, candidates[name]['consumer_fields'])
        if np.any(delta[:, 2]):
            raise ValueError('r4 analytic minimum supports translation only')
        pos = np.vstack((np.zeros(3), np.cumsum(delta, axis=0)))
        velocity = np.abs(delta/dt)
        sv = np.vstack((np.zeros(3), np.cumsum(velocity, axis=0)))
        sv2 = np.vstack((np.zeros(3), np.cumsum(velocity**2, axis=0)))
        for split, spans in data['segments'][name].items():
            for h in gate['horizons_s']:
                starts, k = b.c.windows(spans, h, dt)
                predicted = pos[starts+k]-pos[starts]
                error = predicted-b.c.endpoint_targets(data['pose'], starts, k)
                heading = np.zeros_like(error)
                for tick in range(k):
                    remaining = pos[starts+k]-pos[starts+tick+1]
                    heading[:, 0] += (dt*remaining[:, 1])**2
                    heading[:, 1] += (dt*remaining[:, 0])**2
                groups.append({'axis': name, 'split': split, 'horizon': h,
                               'error': error, 'sum_v': sv[starts+k]-sv[starts],
                               'sum_v2': sv2[starts+k]-sv2[starts],
                               'heading': heading, 'k': k, 'dt': dt})
    return groups


def minimum_noise(data, candidates, gate):
    """Exact order-statistic solution of the frozen lexicographic minimum."""
    groups = noise_groups(data, candidates, gate)
    relative = np.asarray(gate['noise']['floor_noise_rel'])
    absolute = np.asarray(gate['noise']['floor_noise_abs']).copy()
    certificate = {}
    for component in (2, 0, 1):
        required, limiting = float(absolute[component]), None
        for group in groups:
            dt2 = group['dt']**2
            a = group['k']*dt2
            linear = 2*relative[component]*group['sum_v'][:, component]*dt2
            fixed = relative[component]**2*group['sum_v2'][:, component]*dt2
            fixed += group['heading'][:, component]*absolute[2]**2
            need = np.maximum(group['error'][:, component]**2/4.-fixed, 0.)
            denominator = linear+np.sqrt(linear**2+4*a*need)
            threshold = np.divide(2*need, denominator, out=np.zeros_like(need), where=denominator > 0)
            index = int(np.ceil(.95*len(threshold)))-1
            value = float(np.partition(threshold, index)[index])
            if value > required:
                required = value
                limiting = {k: group[k] for k in ('axis', 'split', 'horizon')}
                limiting.update(n=len(threshold), required_covered=index+1)
        floor = float(absolute[component])
        absolute[component] = required + (1e-12 if required > floor else 0.)
        certificate[str(component)] = {'floor': floor, 'minimum_without_roundoff_slack': required,
                                       'limiting_group': limiting}
    return {'method': 'exact lexicographic minimum; relative floors then yaw/forward/left absolute minima',
            'noise_rel': relative.tolist(), 'noise_abs': absolute.tolist(),
            'certificate': certificate, 'roundoff_slack_if_inflated': 1e-12,
            'claim': 'Pareto minimum under frozen ordering, not a unique componentwise least relative/absolute pair'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require_disjoint_output(args.output, args.raw, b.FOLDER)
    args.output.mkdir(parents=True, exist_ok=False)
    gate = b.criterion()
    cases = b.load_collection(args.raw, gate)
    if len(cases) != 1 or not cases[0]['training']:
        raise ValueError('r4 fit is restricted to the frozen v89 training collection')
    # Enforce the old frozen-plan audit and known training pose bytes too.
    plan = json.loads(subprocess.check_output(['git', 'show', f'{b.COLLECTION_SHA}:{b.PLAN}'], cwd=b.ROOT))
    _, audit = b.c.load_data(args.raw, plan)
    old_manifest = json.loads((b.FOLDER / 'input_manifest_r3.json').read_bytes())
    old_pose = {f['sha256'] for f in old_manifest['files'] if f['path'].endswith('eval_only/r1/pose.jsonl')}
    if cases[0]['pose_sha256'] not in old_pose:
        raise ValueError('not the frozen v89 training pose bytes')
    candidates, training = fit_training(cases[0], gate)
    previous = b.FOLDER / 'calibration_partial_r3.json'
    new = copy.deepcopy(json.loads(previous.read_bytes()))
    prior = set(old_pose)
    for row in csv.DictReader((b.FOLDER / 'input_manifest.tsv').open(), delimiter='\t'):
        if row['path'].endswith('/pose.jsonl') or row['path'].endswith('/camera_labels.jsonl'):
            prior.add(row['sha256'])
    new.update(schema='ugrp.final_environment_measured_calibration.v1',
               status='CANDIDATE_UNVALIDATED', revision='v89-consumer-r4',
               qualification='All v89 data is training; new held-out v88 validation has not run.',
               criterion='consumer_criterion_B.json', criterion_sha256=b.CRITERION_SHA256,
               previous_revision={'path': previous.name, 'sha256': sha(previous.read_bytes())},
               candidate_axes=candidates, axis_validation={a: None for a in b.AXES},
               previously_seen_pose_sha256=sorted(prior))
    # Candidate numbers live apart from active params. Keep unsupported axes/nulls.
    new['params']['motion'] = None
    new['motion_identification'] = {'status': 'CANDIDATE_UNVALIDATED', 'criterion_A': 'FAILED_NOT_RESCORED',
                                  'criterion_B_validation': None, 'training_source_sha': b.COLLECTION_SHA,
                                  'training_map': cases[0]['map_id'], 'all_v89_is_training': True}
    new['loader_requirements'] = [
        'Explicitly admit schema v1 plus CANDIDATE_UNVALIDATED for an offline/opt-in unloaded candidate path; never relabel it MEASURED_SIM.',
        'Resolve candidate_axes.<axis>.consumer_fields rather than params.motion (null); require its criterion and candidate hashes, and preserve null validation.',
        'Admit singular axis-only gain matrices with structural zeros and reject any command on a different axis. Missing rotate remains null, with no M1/v87 fallback.',
        'Select the matching per-axis profile including scalar tau_s and tau_stop_s. The current predictor cannot accept a vector tau_stop_s or a single combined independently fitted stop law; mixed-axis use is unvalidated and unsupported.',
        'Use the existing 0.05 s end-velocity Euler mean and noise_rel/noise_abs law, rest_noise=true, use_scale=false; scale_std=scale_walk=0 so no unvalidated scale covariance is credited.',
        'Limit admission to unloaded axis-only motion on the checked map/configuration; accept missing loaded/fine/camera-loaded/pair fields only on that restricted path. Current final-environment/P03 and v88 pair loaders require complete MEASURED_SIM products and must continue to reject r4.',
        'Keep inherited v87 camera/pan source and hashes distinct from v89 motion training and future v88 validation; resolve the exact new contract/map hashes, never substitute the v88 contract hash for the inherited v87 one.'
    ]
    new['limitations'] = [
        'No held-out data scored. Criterion A remains failed; B is a new post-r3 decision.',
        'Forward/left candidates only; rotate=null, all axis_validation=null, params.motion=null.',
        'No per-axis stop-vector support or mixed-motion claim. No loader/controller changes.',
        'Linearized white process budget from an ideal pose fix; no PF inference, physical/render/model calls.',
        'v87 camera/pan values retain old provenance; loaded/fine remain null.'
    ]
    manifest = {'files': cases[0]['inputs'], 'training_audit': audit,
                'criterion_sha256': b.CRITERION_SHA256, 'source_sha256': {p: sha((b.ROOT/p).read_bytes()) for p in (
                    'scripts/fit_consumer_criterion_b.py', 'scripts/validate_consumer_criterion_b.py',
                    'scripts/fit_unloaded_consumer.py', 'scripts/fit_unloaded_hammerstein.py',
                    'harness/owncam_localizer.py')},
                'execution_base_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=b.ROOT).decode().strip(),
                'source_state': 'implementation hashed before commit; commit only after offline tests',
                'python': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__, 'platform': platform.platform()}
    b.verify_inputs(cases)
    write(args.output / 'input_manifest_r4.json', manifest)
    new['motion_measurement_manifest_sha256'] = sha((args.output/'input_manifest_r4.json').read_bytes())
    write(args.output / 'calibration_candidate_r4.json', new)
    report = b.score(cases, new, gate)
    report.update(training=training, candidate_axes=candidates,
                  candidate_sha256=sha((args.output/'calibration_candidate_r4.json').read_bytes()),
                  input_manifest_sha256=new['motion_measurement_manifest_sha256'],
                  physical_runs=0, rendering_runs=0, model_calls=0)
    write(args.output / 'consumer_report_r4.json', report)
    for name, model in candidates.items():
        print(name, None if model is None else {'mean': model['parameters'], 'noise': model['noise_selection']}, flush=True)


if __name__ == '__main__':
    main()
