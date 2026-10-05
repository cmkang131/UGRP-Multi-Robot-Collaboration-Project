"""DEV_PILOT_C0_ZERO_v1: non-confirmatory dev calibration from the v92 HIGH loaded collection.

Coordinator decision 2026-10-03 (user may veto): unblock an LLM-in-the-loop carry DEV pilot
without changing frozen B''. This script is NOT the frozen assembler and its output is NEVER
MEASURED_SIM (the v92 loader rejects any other status).

Dev rule (the ONLY deviations from frozen B'' / the 257953ec assembler path):
  D1. Loaded deadband start c0 is fixed at 0 for all three axes (no deadband) instead of
      being a free parameter in [c0_lower, c0_upper]. The shared fit then has 10 free
      parameters (3 gains, 3 run taus, 1 shared stop tau, 3 u1); u1 keeps the B'' bounds.
  D2. Because c0 = 0, the B'' deadband support check no longer requires an observed command
      level below c0 ("positive stop level"). It still requires >=2 ramp levels (0<|u|<u1)
      and >=1 saturated level (|u|>=u1), each signed, at every horizon.
Everything else is the unchanged code path: same optimizer settings (max_nfev=150, tol 1e-9),
convergence/rank/no-active-bound check and interior distance on the free parameters, B'
noise selection, B'' PRBS validation gates, spread, pair model, fine profile and camera/pan.
Fine profile, camera models and pan are copied programmatically from the measured v92
assembly output (already accepted there); nothing is hand-edited. The unloaded combined
profile has no legitimate candidate and stays missing.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from scripts import assemble_final_pair_calibration_v92 as A
from scripts import fit_consumer_criterion_b as r4
from scripts import validate_consumer_criterion_b as b
from scripts.final_pair_calibration_motion import (
    split_data, increments, path_of, window_groups, verify_fit, budget_groups,
    minimum_noise, evaluate, fit_spread,
)
from scripts.final_pair_calibration_v92_io import Inputs, load_collection, loaded_mask, selected_segments
from scripts.final_pair_calibration_v92_camera import pair_rows, fit_pair

RULE = 'DEV_PILOT_C0_ZERO_v1'
ROOT = Path(__file__).resolve().parents[2]
UNLOADED_REASON = ('no legitimate unloaded combined candidate: r4 (forward/left) and r5 (rotate) are axis-only '
                   'with different stop taus (0.0890/0.0885/0.0374 s) while the loader needs one scalar '
                   'tau_stop_s; frozen B overall pass is null (rotate PARTIAL_MAPS, door map excluded); '
                   'the v92 assembler has no acceptance path. Needs a new shared-stop fit plus held-out B '
                   'validation (new rotation data) or an explicit rule change.')


def support_c0_zero(data, profile, gate):
    """B'' deadband_support with c0 = 0: no stop role; ramp and saturation roles unchanged."""
    support = {}
    for axis, name in enumerate(b.AXES):
        spans = data['segments'][name]['steps']
        driven = np.concatenate([data['u'][a:z, axis] for a, z in spans])
        levels = sorted(set(np.abs(driven)) - {0.})
        c0, u1 = (profile['deadband'][key][axis] for key in ('c0', 'u1'))
        assert c0 == 0.
        roles = {'ramp': [v for v in levels if c0 < v < u1], 'saturation': [v for v in levels if v >= u1]}
        if len(roles['ramp']) < 2 or not roles['saturation']:
            raise ValueError(name + ': observed levels do not give two ramps and saturation')
        rows = []
        for h in gate['horizons_s']:
            starts, k = b.c.windows(spans, h, data['dt'])
            for role, magnitudes in roles.items():
                for magnitude in magnitudes:
                    for sign in (-1, 1):
                        command = sign * magnitude
                        outside = np.r_[0, np.cumsum(data['u'][:, axis] != command)]
                        keep = starts[outside[starts + k] == outside[starts]]
                        if not len(keep):
                            raise ValueError(f'{name}: missing signed {role} {command:+g} at {h:g}s')
                        actual = b.c.endpoint_targets(data['pose'], keep, k)[:, axis] / h
                        rows.append({'role': role, 'command': command, 'horizon_s': h,
                                     'windows': len(keep), 'observed_rate_median': float(np.median(actual))})
        support[name] = rows
    return support


def fit_shared_c0_zero(data_list, gate, bounds):
    """final_pair_calibration_v92_motion.fit_shared with c0 removed from the free parameters."""
    cached = []
    for data in data_list:
        for axis, name in enumerate(b.AXES):
            if not b.axis_supported(data, axis, gate):
                raise ValueError(f'{name}: both signed steps/PRBS and complete horizons required')
        groups = [(axis, s, k, b.c.endpoint_targets(data['pose'], s, k)[:, axis])
                  for axis, _, _, s, k in window_groups(split_data(data, 'steps'), gate)]
        cached.append((data, groups))
    c0 = [0., 0., 0.]

    def profile(theta):
        value = np.exp(theta[:7])
        p = r4.profile(0, [value[0], value[3], value[6]], gate)
        p.update(gain=np.diag(value[:3]).tolist(), tau_axis_s=value[3:6].tolist())
        p['deadband'] = {'c0': list(c0), 'u1': theta[7:10].tolist()}
        return p

    def residual(theta):
        p = profile(theta)
        errors = []
        for data, groups in cached:
            path = path_of(increments(data, p))
            for axis, starts, k, actual in groups:
                error = b.c.endpoint_targets(path, starts, k)[:, axis] - actual
                if axis == 2:
                    error = np.arctan2(np.sin(error), np.cos(error))
                errors.append(error)
        return np.concatenate(errors)

    initial = list(np.log([1., 1., 1., .8, .8, .8, .06])) + bounds['initial_u1']
    lower = list(np.log([.05] * 3 + [.01] * 3 + [.005])) + bounds['u1_lower']
    upper = list(np.log([4.] * 6 + [.5])) + bounds['u1_upper']
    opt = least_squares(residual, initial, bounds=(lower, upper), max_nfev=150,
                        ftol=1e-9, xtol=1e-9, gtol=1e-9)
    report = verify_fit(opt, len(initial))
    distance = np.minimum(opt.x - np.asarray(lower), np.asarray(upper) - opt.x)
    report.update(status=int(opt.status), message=str(opt.message), free_parameters=len(initial),
                  interior_distance_min=float(distance.min()))
    if np.any(distance < bounds['interior_distance_min']):
        raise ValueError('dev shared fit touches parameter bounds')
    fitted = profile(opt.x)
    report['deadband_support'] = [support_c0_zero(data, fitted, gate) for data in data_list]
    return fitted, report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--loaded-root', type=Path, required=True)
    ap.add_argument('--measured-calibration', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    inputs = Inputs()
    inputs.protect(args.loaded_root)
    blob = A.CRITERION.read_bytes()
    if hashlib.sha256(blob).hexdigest() != A.CRITERION_SHA256:
        raise ValueError('frozen B-double-prime hash mismatch')
    inputs.add(A.CRITERION)
    prime = json.loads(blob)
    gate = prime['parent_text']
    measured_blob = args.measured_calibration.read_bytes()
    measured = json.loads(measured_blob)
    inputs.add(args.measured_calibration)
    measured_missing = {m['field'] for m in measured['missing']}

    col = load_collection(args.loaded_root, 'loaded', inputs)
    valid, selection = loaded_mask(col, inputs, prime['loaded_selection'])
    col['valid_load'] = valid
    for robot in col['robots'].values():
        robot['segments'] = selected_segments(col['segments'], valid)
    robots = list(col['robots'].values())

    report = {'rule': RULE, 'load_selection': selection}
    sections = {}
    sections[('pair_model',)] = {'accepted': False, 'reason': 'not computed: no dev loaded mean'}
    motion_ok = False
    try:
        profile, optimizer = fit_shared_c0_zero(robots, gate, prime['loaded_motion_bounds'])
        groups = [g for d in robots for g in budget_groups(split_data(d, 'steps'), profile, gate)]
        profile['noise_abs'], certificate = minimum_noise(groups, gate)
        training = [evaluate(d, profile, gate, 'steps') for d in robots]
        validation = [evaluate(d, profile, gate, 'prbs') for d in robots]
        rows = [row for res in validation for axis in res.values() for row in b.all_rows(axis)]
        motion_ok = all(row['numerical_pass'] for row in rows)
        report['motion'] = {'candidate': profile, 'accepted_under_dev_rule': motion_ok, 'optimizer': optimizer,
                            'noise_certificate': certificate, 'training': training, 'validation': validation,
                            'validation_rows_pass': [sum(r['numerical_pass'] for r in rows), len(rows)],
                            'training_rows_pass': [sum(r['numerical_pass'] for res in training for ax in res.values()
                                                       for r in b.all_rows(ax)),
                                                   sum(1 for res in training for ax in res.values() for r in b.all_rows(ax))]}
        sections[A.MOTION['loaded']] = {'value': profile, 'accepted': motion_ok,
                                        'reason': 'dev c0=0 loaded mean rejected by unchanged B-double-prime PRBS gates'}
    except (ValueError, KeyError, TypeError, FloatingPointError) as exc:
        report['motion'] = {'error': str(exc)}
        sections[A.MOTION['loaded']] = {'accepted': False, 'reason': 'dev motion identification: ' + str(exc)}
    if A.MOTION['loaded'] in sections and 'value' in sections[A.MOTION['loaded']]:
        try:
            spread, score = fit_spread(robots, profile, gate)
            report['spread'] = {'candidate': spread, **score}
            for key, value in spread.items():
                sections[A.MOTION['loaded'] + (key,)] = {'value': value, 'accepted': score['accepted'] and motion_ok,
                                                         'reason': 'spread requires an accepted loaded mean'}
        except (ValueError, KeyError, TypeError) as exc:
            report['spread'] = {'error': str(exc)}
        try:
            rows_, excluded = pair_rows(col, profile, valid, inputs, prime['pair_model'])
            pair, score = fit_pair(rows_, prime['pair_model'])
            report['pair'] = {'candidate': pair, **score, 'excluded': excluded, 'rows': len(rows_)}
            sections[('pair_model',)] = {'value': pair, 'accepted': score['accepted'] and motion_ok,
                                         'reason': 'pair PRBS validation or loaded mean rejected'}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            report['pair'] = {'error': str(exc)}
            sections[('pair_model',)] = {'accepted': False, 'reason': 'pair: ' + str(exc)}
    sections[A.MOTION['unloaded']] = {'accepted': False, 'reason': UNLOADED_REASON}

    cal = {k: copy.deepcopy(measured[k]) for k in (
        'schema', 'loader_contract_version', 'contract_sha256', 'maps', 'loaded_measurement_bundle_id',
        'loaded_pose_id', 'loaded_camera_scope', 'loaded_schedule_sha256', 'criterion_sha256',
        'robot_model', 'render_profile', 'criterion_B_double_prime_sha256', 'criterion_B_sha256',
        'collection_sources')}
    cal.update({'status': 'DEV_PILOT', 'dev_rule': RULE, 'confirmatory': False,
                'measured_parent': {'path': str(args.measured_calibration.resolve()),
                                    'sha256': hashlib.sha256(measured_blob).hexdigest(),
                                    'status': measured['status']}})
    missing, provenance = [], {}
    for path in A.required_fields():
        label = A.label(path)
        matches = [(p, r) for p, r in sections.items() if path[:len(p)] == p]
        if matches:
            prefix, result = max(matches, key=lambda item: len(item[0]))
            value = A.at(result.get('value'), path[len(prefix):])
            ok = result.get('accepted') is True and value is not None
            source = 'dev_refit_' + RULE
            if not ok:
                missing.append({'field': label, 'reason': result.get('reason', 'dev measurement absent')})
                value = None
        else:
            value = A.at(measured, path)
            ok = value is not None and label not in measured_missing
            source = 'copied_from_measured_v92_assembly'
            if not ok:
                missing.append({'field': label, 'reason': 'not accepted in measured v92 assembly'})
                value = None
        if value is not None:
            json.dumps(value, allow_nan=False)
            provenance[label] = source
        A.put(cal, path, copy.deepcopy(value))
    cal['missing'] = missing
    cal['field_provenance'] = provenance
    cal['qualification'] = ('NON-CONFIRMATORY DEV PILOT ONLY. Not MEASURED_SIM; rejected by the v92 loader. '
                            'v92 loaded data were already inspected before this rule; confirmation needs a '
                            're-collection under a newly frozen rule. No task-success claim.')
    manifest = {'schema': 'ugrp.v92_dev_pilot_inputs.v1', 'files': sorted(inputs.files.values(), key=lambda r: r['path']),
                'execution_source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'python': platform.python_version(), 'numpy': np.__version__}
    inputs.verify()
    manifest_blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    cal['source_sha'] = manifest['execution_source_sha']
    cal['dev_manifest_sha256'] = hashlib.sha256(manifest_blob.encode()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'input_manifest_dev.json').write_text(manifest_blob)
    (output / 'calibration_dev_pilot.json').write_text(json.dumps(cal, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (output / 'fit_report_dev.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                           default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)) + '\n')
    print(json.dumps({'status': cal['status'], 'missing': len(missing), 'motion_accepted': motion_ok,
                      'output': str(output)}))


if __name__ == '__main__':
    main()
