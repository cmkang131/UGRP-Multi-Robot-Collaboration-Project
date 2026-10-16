"""Offline finite-horizon motion calibration; no simulator, renderer or controller imports.

Mean and noise fits use steps only. PRBS is development validation, never a
source of initial velocity, fit parameters or noise inflation. The immutable
criterion file is an input, hashed before any fits. Position fixes are ideal
evaluation anchors, not an additional runtime observation channel.
"""
from __future__ import annotations

import argparse
import copy
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares, minimize

from scripts.fit_unloaded_hammerstein import (
    COLLECTION_SHA, PLAN, RECORD, ROOT, load_translation, require_disjoint_output,
    rows, sha, write,
)

CRITERION = ROOT / RECORD / 'consumer_criterion_r3.json'
MASS_KG = 1.1
MOTOR_TAU_S = .085
WHEEL_RAD_S = 12.
FRICTION_SPEED_M_S = .002  # fixed smooth-contact approximation, not a MuJoCo constant
FROZEN_M1_SHA = '22c84842b507264de496b54b1e8c9217701b9b5c'
MIX = np.array([[1., -1., -1.], [1., 1., 1.], [1., 1., -1.], [1., -1., 1.]])


def load_data(raw, plan):
    _, audit = load_translation(raw, plan)  # frozen-plan/clock/lease/index audit
    folder = raw / 'zone_wide_two_doors_final_v3'
    pose = rows((folder / 'eval_only/r1/pose.jsonl').read_bytes())
    commands = [c for c in rows((folder / 'robots/r1/commands.jsonl').read_bytes())
                if c['kind'] == 'mecanum']
    u = np.array([[c[a] for a in ('forward', 'left', 'turn')] for c in commands])
    rot = np.array([r['base_rotation'] for r in pose])
    xy = np.array([r['base_position_m'][:2] for r in pose])
    yaw = np.unwrap(np.arctan2(rot[:, 1, 0], rot[:, 0, 0]))
    dt = plan['control_period_s']
    bounds, cursor = [], round(plan['initial_hold_s'] / dt)
    for s in plan['segments']:
        end = cursor + round(s['duration_s'] / dt)
        bounds.append((cursor, end, s))
        cursor = end
    segments = {}
    for axis in ('forward', 'left'):
        steps = [(a, bounds[j+1][1]) for j, (a, b, s) in enumerate(bounds)
                 if s['axis'] == axis and s['phase'] == 'step']
        start = min(a for a, b, s in bounds if s['axis'] == axis and s['phase'] == 'prbs')
        end = max(b for a, b, s in bounds if s['axis'] == axis)
        segments[axis] = {'steps': steps, 'prbs': [(start, end)]}
    return dict(u=u, pose=np.column_stack((xy, yaw)), dt=dt, segments=segments), audit


def windows(segments, horizon, dt):
    k = round(horizon / dt)
    if k < 1 or not np.isclose(k * dt, horizon):
        raise ValueError('horizon must be a positive integer number of samples')
    starts = np.concatenate([np.arange(a, b-k+1, dtype=int) for a, b in segments])
    if not len(starts):
        raise ValueError('no complete windows')
    return starts, k


def endpoint_targets(pose, starts, k):
    """Actual endpoint in each start-pose frame, retaining cross drift and yaw."""
    diff = pose[starts+k] - pose[starts]
    c, s = np.cos(pose[starts, 2]), np.sin(pose[starts, 2])
    return np.column_stack((c*diff[:, 0] + s*diff[:, 1],
                            -s*diff[:, 0] + c*diff[:, 1],
                            np.arctan2(np.sin(diff[:, 2]), np.cos(diff[:, 2]))))


def first_order(u, active, dt, parameters):
    """Existing gain + first-order family with a separately fitted stop lag."""
    gain, run_tau, stop_tau = parameters
    p, v = np.zeros(len(u)+1), np.zeros(len(u)+1)
    for j, command in enumerate(u):
        tau = run_tau if active[j] else stop_tau
        a = -np.expm1(-dt/tau)
        target = gain*command
        v[j+1] = v[j] + a*(target-v[j])
        p[j+1] = p[j] + target*dt + (v[j]-target)*tau*a
    return p, v


def motor_projection(commands, dt):
    """ABAB command mixing, clipping and known lag, projected back to body axes."""
    wheel_command = np.clip(np.asarray(commands) @ MIX.T, -1., 1.)
    state = np.zeros((len(commands)+1, 4))
    a = -np.expm1(-dt/MOTOR_TAU_S)
    for i, command in enumerate(wheel_command):
        state[i+1] = state[i] + a*(command-state[i])
    # Projection of wheel velocity targets; units rad/s, NOT body velocity.
    return WHEEL_RAD_S*(state @ MIX/4.)


def grey_box(u, active, dt, parameters, *, rtol=2e-7):
    """Reduced physically parameterized predictor, not contact/physics replay.

    m*v_dot = drive_sign * wheel_target - D(command)*v - Fc*tanh(v/v_eps)
    Wheel_target follows the exact .085 s motor lag. Effective drive gain
    absorbs the known wrench plus unobserved wheel/contact traction. Mass is
    fixed; run/stop damping starts at 1.4/18 but is fitted. Contact geometry,
    measured wheel speed and simulator state are never accessed.
    """
    plus, minus, running, stopping, friction = parameters
    n = len(u)
    p, v = np.zeros(n+1), np.zeros(n+1)
    motor = 0.
    edges = np.r_[0, np.flatnonzero((np.diff(u) != 0) | (np.diff(active) != 0))+1, n]
    for a, b in zip(edges[:-1], edges[1:]):
        command, m0 = u[a], motor
        damping = running if active[a] else stopping
        duration = (b-a)*dt

        def rhs(t, state):
            target = WHEEL_RAD_S*(command+(m0-command)*np.exp(-t/MOTOR_TAU_S))
            drive = np.where(target >= 0, plus, minus)*target
            velocity = state[1]
            acceleration = (drive-damping*velocity
                            - friction*np.tanh(velocity/FRICTION_SPEED_M_S))/MASS_KG
            return [velocity, acceleration]

        times = np.arange(1, b-a+1)*dt
        times[-1] = duration
        sol = solve_ivp(rhs, (0., duration), [p[a], v[a]], t_eval=times,
                        rtol=rtol, atol=rtol*1e-5)
        if not sol.success:
            raise ValueError('grey-box integration failed: '+sol.message)
        p[a+1:b+1], v[a+1:b+1] = sol.y
        motor = command+(m0-command)*np.exp(-duration/MOTOR_TAU_S)
    return p, v


def predict(data, axis, kind, parameters, **kwargs):
    u = data['u'][:, axis]
    active = np.any(np.abs(data['u']) >= 1e-6, axis=1)
    if kind == 'gain_first_order':
        return first_order(u, active, data['dt'], parameters)
    if kind == 'grey_box':
        # This collection is axis-separated and unclipped: the ABAB inverse
        # is exactly u, so the scalar lag equals motor_projection's axis.
        if np.max(np.abs(data['u'] @ MIX.T)) > 1.:
            raise ValueError('grey-box scalar reduction forbids clipped commands')
        return grey_box(u, active, data['dt'], parameters, **kwargs)
    raise ValueError('unknown predictor')


def fit_mean(data, axis, kind, criterion):
    axis_name = ('forward', 'left')[axis]
    samples = []
    for h in criterion['horizons_s']:
        starts, k = windows(data['segments'][axis_name]['steps'], h, data['dt'])
        samples.append((starts, k, endpoint_targets(data['pose'], starts, k)[:, axis]))
    if kind == 'gain_first_order':
        initial, low, high = [1., .8, .06], [.05, .01, .005], [4., 4., .5]
        names = ['gain', 'tau_run_s', 'tau_stop_s']
    else:
        initial = [(2.2 if axis == 0 else 1.65)/12.]*2+[1.4, 18., .01]
        low, high = [.02, .02, .2, 2., 1e-7], [.6, .6, 8., 50., .05]
        names = ['drive_plus_N_per_rad_s', 'drive_minus_N_per_rad_s',
                 'running_damping_N_s_m', 'stop_damping_N_s_m', 'friction_N']

    def residual(theta):
        p, _ = predict(data, axis, kind, np.exp(theta))
        return np.concatenate([p[s+k]-p[s]-y for s, k, y in samples])

    opt = least_squares(residual, np.log(initial), bounds=(np.log(low), np.log(high)),
                        max_nfev=100, ftol=1e-8, xtol=1e-8, gtol=1e-9)
    rank = int(np.linalg.matrix_rank(opt.jac))
    values = np.exp(opt.x)
    boundary = [names[i] for i, x in enumerate(opt.x)
                if min(x-np.log(low[i]), np.log(high[i])-x) < 1e-4]
    return dict(kind=kind, parameters=values.tolist(), named_parameters=dict(zip(names, values.tolist())),
                free_parameters=len(values), optimizer_success=bool(opt.success),
                nfev=int(opt.nfev), mean_jacobian_rank=rank, boundary_parameters=boundary,
                fit_residual_count=len(opt.fun), fit_rmse_m=float(np.sqrt(np.mean(opt.fun**2))),
                eligible=bool(opt.success and rank == len(values) and not boundary))


def legacy_increments(data, mp):
    """Deterministic mean of the current end-velocity Euler PF, no PF execution."""
    velocity = np.zeros(3)
    out = []
    for command in data['u']:
        tau = mp.get('tau_axis_s', mp['tau_s']) if np.any(command) else mp.get('tau_stop_s', mp['tau_s'])
        alpha = -np.expm1(-data['dt']/np.asarray(tau))
        velocity = velocity + alpha*(np.asarray(mp['gain']) @ command - velocity)
        out.append(velocity*data['dt'])
    return np.asarray(out)


def legacy_windows(increments, starts, k, dt, mp, *, scale):
    """Linearized pose/scale process covariance under the actual .05 s law.

    Persistent scale uncertainty is correlated across steps. Its random walk
    is added AFTER each step, matching the consumer. Initial pose is exact;
    optional initial scales have the calibration prior variance, not an
    invented measured posterior. White-only covariance is the strict budget.
    """
    n = len(starts)
    mean = np.zeros((n, 3))
    covariance = np.zeros((n, 6, 6))
    if scale and mp.get('use_scale', True):
        covariance[:, 3:, 3:] = np.eye(3)*mp['scale_std']**2
    for i in range(k):
        delta = increments[starts+i]
        c, s = np.cos(mean[:, 2]), np.sin(mean[:, 2])
        rotation = np.zeros((n, 3, 3))
        rotation[:, 0, 0] = rotation[:, 1, 1] = c
        rotation[:, 0, 1], rotation[:, 1, 0] = -s, s
        rotation[:, 2, 2] = 1.
        world = np.einsum('nij,nj->ni', rotation, delta)
        f = np.broadcast_to(np.eye(6), (n, 6, 6)).copy()
        f[:, 0, 2], f[:, 1, 2] = -world[:, 1], world[:, 0]
        if scale and mp.get('use_scale', True):
            f[:, :3, 3:] = rotation*delta[:, None, :]
        covariance = f @ covariance @ f.transpose(0, 2, 1)
        std = np.asarray(mp['noise_rel'])*np.abs(delta/dt)+np.asarray(mp['noise_abs'])
        q = (rotation*(std*dt)[:, None, :])
        covariance[:, :3, :3] += q @ q.transpose(0, 2, 1)
        if scale and mp.get('use_scale', True):
            moving = np.any(np.abs(delta/dt) > 1e-6, axis=1)
            covariance[:, 3:, 3:] += moving[:, None, None]*np.eye(3)*mp['scale_walk']**2*dt
        mean += world
    return mean, covariance[:, :3, :3]


def make_windows(data, axis, model, split, criterion):
    name = ('forward', 'left')[axis]
    p, _ = predict(data, axis, model['kind'], model['parameters'])
    travel = np.r_[0., np.cumsum(np.abs(np.diff(p)))]
    order = [axis, 1-axis, 2]  # along, cross, yaw in start-body frame
    result = {}
    for h in criterion['horizons_s']:
        starts, k = windows(data['segments'][name][split], h, data['dt'])
        target = endpoint_targets(data['pose'], starts, k)[:, order]
        pred = np.column_stack((p[starts+k]-p[starts], np.zeros((len(starts), 2))))
        command = data['u'][:, axis]
        stop_prefix = np.r_[0, np.cumsum(command == 0)]
        reverse = np.r_[False, command[1:]*command[:-1] < 0]
        reverse_prefix = np.r_[0, np.cumsum(reverse)]
        result[str(h)] = dict(starts=starts, k=k, residual=pred-target,
                             features=np.column_stack((np.full(len(starts), h),
                                                        (travel[starts+k]-travel[starts])**2)),
                             contains_stop=stop_prefix[starts+k] > stop_prefix[starts],
                             contains_reversal=reverse_prefix[starts+k] > reverse_prefix[starts])
    return result


def fit_noise(window_data):
    features = np.concatenate([w['features'] for w in window_data.values()])
    errors = np.concatenate([w['residual'] for w in window_data.values()])
    parameters, diagnostics = [], []
    for j in range(3):
        square = errors[:, j]**2
        scaling = np.maximum(np.mean(square)/(2*np.mean(features, axis=0)), 1e-24)

        def nll(z):
            variance = np.maximum(features @ (scaling*np.exp(z)), 1e-30)
            return .5*np.mean(np.log(variance)+square/variance)

        opt = minimize(nll, np.zeros(2), method='L-BFGS-B', bounds=[(-24., 24.)]*2,
                       options={'ftol': 1e-12, 'gtol': 1e-7})
        parameters.append((scaling*np.exp(opt.x)).tolist())
        diagnostics.append(dict(success=bool(opt.success), message=str(opt.message),
                                nll=float(opt.fun), boundary=bool(np.any(np.abs(opt.x) > 23.99))))
    p = np.array(parameters)
    return dict(q_per_s=p[:, 0].tolist(), alpha1=float(p[0, 1]), alpha_lateral=float(p[1, 1]),
                alpha3=float(p[2, 1]), alpha2=None, alpha4=None,
                coefficients_along_cross_yaw=parameters, optimizer=diagnostics,
                translation_feature_rank=int(np.linalg.matrix_rank(features)),
                turn_feature_rank=0, fit_windows=len(features),
                method='zero-mean Gaussian quasi-MLE; uncentered residuals; steps only',
                scope='finite-horizon mecanum adaptation; alpha2/alpha4 unidentifiable without turns')


def noise_variance(window, noise):
    return np.maximum(window['features'] @ np.asarray(noise['coefficients_along_cross_yaw']).T, 1e-30)


def calibration_metrics(error, variance):
    z = error/np.sqrt(variance)
    return dict(coverage_1sigma=np.mean(np.abs(z) <= 1., axis=0).tolist(),
                coverage_2sigma=np.mean(np.abs(z) <= 2., axis=0).tolist(),
                mean_nees_per_dimension=np.mean(z*z, axis=0).tolist(),
                mean_nees_3d=float(np.mean(np.sum(z*z, axis=1))),
                normalized_abs_error_p95=np.percentile(np.abs(z), 95, axis=0).tolist())


def distribution(error):
    return dict(n=len(error), bias=error.mean(axis=0).tolist(),
                rmse=np.sqrt(np.mean(error**2, axis=0)).tolist(),
                abs_error_quantiles={str(q): np.percentile(np.abs(error), q, axis=0).tolist()
                                     for q in (50, 90, 95, 99, 100)},
                position_norm_p95_m=float(np.percentile(np.linalg.norm(error[:, :2], axis=1), 95)),
                yaw_abs_p95_deg=float(np.degrees(np.percentile(np.abs(error[:, 2]), 95))))


def rejection_reasons(model, noise, summary, gate):
    reasons = []
    if not model['eligible']:
        reasons.append('mean fit nonconverged, rank deficient or at bound')
    if noise['translation_feature_rank'] != 2 or not all(o['success'] for o in noise['optimizer']):
        reasons.append('noise fit nonconverged or rank deficient')
    for horizon, record in summary.items():
        if record['n'] < gate['minimum_validation_windows_per_horizon']:
            reasons.append(horizon+': insufficient complete windows')
        for metric, limits in (('coverage_1sigma', gate['coverage_1sigma_range']),
                               ('coverage_2sigma', gate['coverage_2sigma_range']),
                               ('mean_nees_per_dimension', gate['mean_nees_per_dimension_range'])):
            values = record['calibrated_noise'][metric]
            for j, value in enumerate(values):
                if not limits[0] <= value <= limits[1]:
                    reasons.append(f'{horizon}: {metric}[{j}] outside {limits}')
        if max(record['existing_white']['normalized_abs_error_p95']) > gate['existing_white_sigma_normalized_abs_error_p95_max']:
            reasons.append(horizon+': p95 error exceeds existing 2-sigma process budget')
        if max(record['new_to_existing_white_sigma_ratio_p95']) > gate['new_to_existing_white_sigma_ratio_p95_max']:
            reasons.append(horizon+': new noise exceeds existing process budget')
    return reasons


def evaluate(data, axis, model, noise, split, criterion, legacy, mp, arrays):
    result = {}
    order = [axis, 1-axis, 2]
    for h, window in make_windows(data, axis, model, split, criterion).items():
        error = window['residual']
        variance = noise_variance(window, noise)
        old_mean, white = legacy_windows(legacy, window['starts'], window['k'], data['dt'], mp, scale=False)
        _, scaled = legacy_windows(legacy, window['starts'], window['k'], data['dt'], mp, scale=True)
        white_diag = np.diagonal(white, axis1=1, axis2=2)[:, order]
        scaled_diag = np.diagonal(scaled, axis1=1, axis2=2)[:, order]
        old_error = (old_mean-endpoint_targets(data['pose'], window['starts'], window['k']))[:, order]
        result[h] = {**distribution(error), 'calibrated_noise': calibration_metrics(error, variance),
                     'existing_white': calibration_metrics(error, white_diag),
                     'existing_with_prior_scale': calibration_metrics(error, scaled_diag),
                     'old_consumer_mean': distribution(old_error),
                     'white_sigma_median': np.median(np.sqrt(white_diag), axis=0).tolist(),
                     'prior_scale_sigma_median': np.median(np.sqrt(scaled_diag), axis=0).tolist(),
                     'new_sigma_median': np.median(np.sqrt(variance), axis=0).tolist(),
                     'new_to_existing_white_sigma_ratio_p95': np.percentile(np.sqrt(variance/white_diag), 95, axis=0).tolist()}
        result[h]['strata'] = {}
        for name in ('contains_stop', 'contains_reversal'):
            mask = window[name]
            result[h]['strata'][name] = ({**distribution(error[mask]),
                'calibrated_noise': calibration_metrics(error[mask], variance[mask])} if mask.any() else {'n': 0})
        prefix = f'{axis}_{model["kind"]}_{split}_{h}'
        arrays[prefix] = np.column_stack((window['starts']*data['dt'], error, variance, white_diag,
                                          window['contains_stop'], window['contains_reversal']))
    return result


def revision(previous, report):
    new = copy.deepcopy(previous)
    new.update(schema='ugrp.final_environment_measured_calibration.v3', revision='v89-consumer-r3',
               previous_revision=dict(path='calibration_partial_r2.json', sha256=report['r2_sha256']))
    new['params']['motion'] = None
    new['params']['motion_hammerstein'] = {k: None for k in ('forward', 'left', 'rotate')}
    new['params']['motion_consumer'] = {
        axis: report['axes'][axis]['selected'] for axis in ('forward', 'left')}
    new['params']['motion_consumer']['rotate'] = None
    new['motion_measurement_manifest_sha256'] = report['input_manifest_sha256']
    new['motion_identification'] = dict(report='consumer_report_r3.json',
        report_sha256=report['report_sha256'], criterion='consumer_criterion_r3.json',
        criterion_sha256=report['criterion_sha256'], input_manifest='input_manifest_r3.json',
        input_manifest_sha256=report['input_manifest_sha256'],
        status='PARTIAL_AXIS_VALIDATION' if any(new['params']['motion_consumer'].values()) else 'REJECTED',
        reasons={a: report['axes'][a].get('reasons') for a in ('forward', 'left', 'rotate')},
        existing_consumer_unchanged=False, reason='schema/status refused; finite-horizon covariance not implemented by consumer')
    new['limitations'] = [
        'Previously inspected v89 unloaded deterministic development data; no independent repetition or new confirmation.',
        'Ideal start-pose fixes; command-only hidden states. No camera measurement accuracy/availability is validated.',
        'No turn excitation: rotation mean, alpha2 and alpha4 remain null; heading drift under translation is not turn validation.',
        'Only complete windows within step or PRBS segments; no extrapolation beyond +/-0.01..0.03 or beyond 3.2 seconds.',
        'Camera and pan retain v87 provenance. Loaded/fine remain unavailable; PARTIAL_UNLOADED_SIM, no P03 qualification.',
        'All overlapping-window NEES/coverage is descriptive, not independent-sample statistical confidence.',
    ]
    return new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require_disjoint_output(args.output, args.raw, ROOT/RECORD)
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = []

    def track(path):
        data = path.read_bytes()
        inputs.append(dict(path=str(path.resolve()), sha256=sha(data), bytes=len(data)))
        return data

    criterion_bytes = track(CRITERION)
    criterion = json.loads(criterion_bytes)
    print('criterion sha256', sha(criterion_bytes), flush=True)
    old1 = track(ROOT/RECORD/'calibration_partial.json')
    old2 = track(ROOT/RECORD/'calibration_partial_r2.json')
    for p in sorted(args.raw.rglob('*')):
        if p.is_file():
            track(p)
    sources = ('scripts/fit_unloaded_consumer.py', 'scripts/fit_unloaded_hammerstein.py',
               'tests/test_unloaded_consumer.py', 'scripts/run_ci_tests.py',
               'harness/owncam_localizer.py', 'harness/owncam_drive.py', 'harness/owncam_drive_shared.py',
               'harness/vision_pose_source_p03.py', 'harness/zone_final_environment.py',
               'harness/vision_motion_init.py', 'scripts/run_m1_owncam.py', 'scripts/run_m2_pair.py',
               'experiments/2026-09-26-vision-loc/vision_motion.py',
               'experiments/2026-09-26-vision-loc/vision_pf.py',
               'experiments/2026-09-26-vision-loc/selected_config_v3.json',
               'experiments/2026-09-26-markerless-probe/markerless_probe.py',
               'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json')
    for p in sources:
        track(ROOT/p)
    plan_bytes = subprocess.check_output(['git', 'show', f'{COLLECTION_SHA}:{PLAN}'], cwd=ROOT)
    plan = json.loads(plan_bytes)
    git_inputs = []
    for rev, path in ((FROZEN_M1_SHA, 'harness/owncam_localizer.py'),
                      (COLLECTION_SHA, 'sim/multi_masterpi_production.py'),
                      (COLLECTION_SHA, 'sim/masterpi_dynamics_v2.py'),
                      (COLLECTION_SHA, 'sim/camera_robot_port.py')):
        blob = subprocess.check_output(['git', 'show', f'{rev}:{path}'], cwd=ROOT)
        git_inputs.append(dict(git_ref=rev, path=path, sha256=sha(blob), bytes=len(blob)))
    if git_inputs[0]['sha256'] != '0304d7c491dfe6ae68cea6550f7a13e3c99e8e1d3f8e8b6c4b7b1d06893b1d63':
        raise ValueError('frozen consumer identity changed')
    data, audit = load_data(args.raw, plan)
    mp = json.loads((ROOT/criterion['consumer']['noise_source']).read_bytes())['params']['motion']
    legacy = legacy_increments(data, mp)
    report = dict(schema='ugrp.offline_consumer_calibration.v1', collection_sha=COLLECTION_SHA,
                  execution_source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  source_state='uncommitted implementation hashed in input manifest; commit only after offline tests',
                  criterion_sha256=sha(criterion_bytes), r1_sha256=sha(old1), r2_sha256=sha(old2),
                  criterion=criterion, audit=audit, existing_consumer_motion=mp,
                  frozen_consumer=git_inputs[0],
                  consumer_note='P03 uses the hash-frozen M1 predict_to, whose unloaded mean/noise law matches the current localizer. Robust stuck is disabled in selected_config_v3. VIS4 exact integration is opt-in, not the scored P03 default.',
                  numerical_model=dict(mass_kg=MASS_KG, motor_tau_s=MOTOR_TAU_S,
                      wheel_target_scale_rad_s=WHEEL_RAD_S, friction_smoothing_speed_m_s=FRICTION_SPEED_M_S,
                      contact_scope='smooth effective force; not an exact MuJoCo contact solver'),
                  environment=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__, platform=platform.platform()),
                  axes={}, external_model_calls=0, physics_runs=0, rendering_runs=0)
    arrays = {}
    for axis, name in enumerate(('forward', 'left')):
        models, selected = [], None
        for kind in criterion['candidate_order']:
            print('fit', name, kind, flush=True)
            model = fit_mean(data, axis, kind, criterion)
            training = make_windows(data, axis, model, 'steps', criterion)
            noise = fit_noise(training)
            model['noise'] = noise
            for split in ('steps', 'prbs'):
                model[split] = evaluate(data, axis, model, noise, split, criterion, legacy, mp, arrays)
            model['reasons'] = rejection_reasons(model, noise, model['prbs'], criterion['acceptance'])
            if kind == 'grey_box':
                p, _ = predict(data, axis, kind, model['parameters'])
                tight, _ = predict(data, axis, kind, model['parameters'], rtol=2e-9)
                model['integration_tolerance_max_position_change_m'] = float(np.max(np.abs(p-tight)))
                if model['integration_tolerance_max_position_change_m'] > 1e-6:
                    model['reasons'].append('integration tolerance sensitivity exceeds 1 micrometre')
            model['passes_A'] = not model['reasons']
            if selected is None and model['passes_A']:
                selected = dict(kind=kind, parameters=model['named_parameters'], noise=noise,
                                accepted_horizons_s=criterion['horizons_s'], scope='axis-only unloaded development')
            models.append(model)
            print(name, kind, 'pass', model['passes_A'], 'reasons', len(model['reasons']), flush=True)
        report['axes'][name] = dict(models=models, selected=selected,
            reasons=None if selected else {m['kind']: m['reasons'] for m in models})
    report['axes']['rotate'] = dict(selected=None, reasons=['v89 has zero nonzero turn commands',
        'v87 two signed single-amplitude steps provide no independent turn PRBS validation'],
        alpha2=None, alpha4=None)
    np.savez_compressed(args.output/'window_residuals_r3.npz', **arrays)
    report['windows_artifact'] = dict(path=str((args.output/'window_residuals_r3.npz').resolve()),
        sha256=sha((args.output/'window_residuals_r3.npz').read_bytes()), keys=len(arrays),
        columns=['start_sim_s', 'error_along_m', 'error_cross_m', 'error_yaw_rad',
                 'new_var_along', 'new_var_cross', 'new_var_yaw', 'white_var_along',
                 'white_var_cross', 'white_var_yaw', 'contains_stop', 'contains_reversal'])
    for inp in inputs:
        if sha(Path(inp['path']).read_bytes()) != inp['sha256']:
            raise RuntimeError('input changed: '+inp['path'])
    write(args.output/'input_manifest_r3.json', dict(files=inputs, git_inputs=git_inputs, local_inputs_unchanged=True,
        frozen_plan=dict(git_ref=COLLECTION_SHA, path=PLAN, sha256=sha(plan_bytes))))
    report['input_manifest_sha256'] = sha((args.output/'input_manifest_r3.json').read_bytes())
    write(args.output/'consumer_report_r3.json', report)
    report['report_sha256'] = sha((args.output/'consumer_report_r3.json').read_bytes())
    write(args.output/'calibration_partial_r3.json', revision(json.loads(old2), report))
    print('completed', args.output, flush=True)


if __name__ == '__main__':
    main()
