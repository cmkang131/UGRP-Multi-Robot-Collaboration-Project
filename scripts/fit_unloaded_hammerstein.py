"""Offline output-error identification. Never import a simulator or controller.

Unit-DC-gain dynamics remove the Hammerstein gain ambiguity. The static block
owns output units; inputs are dimensionless motor-command fractions, not m/s.
All sequence states start at rest; no measured velocity initializes prediction.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'experiments/2026-10-01-final-env-v87-calibration-fit'
COLLECTION_SHA = 'eaeaaff05553ea02c649b4db9ff82470fe6372b5'
PR348_SHA = 'dba873d4b0e77e017373e5539ac077abb7c6f4b1'
PLAN = 'configs/final_environment_measurement_v2.json'
SCALE = .02
THRESHOLD = .05
STATICS = ('linear', 'deadband', 'deadband_quadratic', 'deadband_pwl')
DELAYS = (0, 1, 2, 3, 4)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, obj):
    with Path(path).open('x') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def require_disjoint_output(output, *inputs):
    output = Path(output).resolve()
    for source in inputs:
        source = Path(source).resolve()
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('input and output trees must be disjoint')


def rows(data):
    return [json.loads(line) for line in data.decode().splitlines() if line.strip()]


def integrated_step(t, order, theta):
    """Exact integral of a unit step through stable unit-gain velocity dynamics.

    Order 1: 1/(tau*s+1). Order 2: 1/(tau^2*s^2+2*zeta*tau*s+1).
    tau is 1/omega_n for order 2, not either of its pole time constants.
    """
    t = np.maximum(t, 0.)
    tau = np.exp(theta[0])
    if order == 1:
        return t + tau * np.expm1(-t / tau)
    zeta = np.exp(theta[1])
    if abs(zeta - 1.) < 1e-6:
        return t - 2*tau + (t + 2*tau)*np.exp(-t/tau)
    root = np.sqrt(complex(zeta*zeta - 1))
    r1, r2 = (-zeta + root)/tau, (-zeta - root)/tau
    return np.real(((np.expm1(r1*t)/r1 - t)/r1
                    - (np.expm1(r2*t)/r2 - t)/r2) / (tau*tau*(r1-r2)))


def static_basis(u, kind, deadbands):
    u = np.asarray(u)
    cols = []
    for sign, deadband in zip((1, -1), deadbands):
        x = np.maximum(np.abs(u)/SCALE - deadband, 0.)
        mask = (u*sign > 0).astype(float)*sign
        cols.append(mask*x)
        if kind == 'deadband_quadratic':
            cols.append(mask*x*x)
        elif kind == 'deadband_pwl':
            # Fixed knot at |u|=.02, with a continuous hinge above the deadband.
            cols.append(mask*np.maximum(np.abs(u)/SCALE-1., 0.))
    return np.column_stack(cols)


def design(sequence, kind, order, delay, theta):
    u, dt = sequence['u'], sequence['dt']
    deadbands = theta[order:] if kind != 'linear' else (0., 0.)
    basis = static_basis(u, kind, deadbands)
    delta = np.diff(basis, axis=0, prepend=np.zeros((1, basis.shape[1])))
    ix = np.flatnonzero(np.any(delta != 0, axis=1))
    # A command at index k acts on [k*dt,(k+1)*dt); output samples at endpoints.
    elapsed = ((np.arange(1, len(u)+1)[:, None] - ix[None, :])*dt
               - delay*sequence.get('control_dt', dt))
    return integrated_step(elapsed, order, theta) @ delta[ix]


def fit(sequences, kind, order, delay, *, weights=None, start=None):
    y = np.concatenate([s['y'][1:] for s in sequences])
    w = np.ones(len(y)) if weights is None else np.sqrt(weights)
    lower = [np.log(.005)] + ([np.log(.15)] if order == 2 else [])
    upper = [np.log(5.)] + ([np.log(5.)] if order == 2 else [])
    if kind != 'linear':
        lower += [0., 0.]
        upper += [.499, .499]  # d < smallest driven magnitude .01

    def solve(theta):
        x = np.concatenate([design(s, kind, order, delay, theta) for s in sequences])
        beta, _, rank, _ = np.linalg.lstsq(x*w[:, None], y*w, rcond=None)
        return (x@beta-y)*w, beta, int(rank), x

    starts = [start] if start is not None else [
        [np.log(t)] + ([np.log(z)] if order == 2 else [])
        + ([.25, .25] if kind != 'linear' else [])
        for t, z in ((.15, .7), (.8, 1.5), (1.5, 3.))]
    opts = [least_squares(lambda th: solve(th)[0], np.clip(s, lower, upper),
                          bounds=(lower, upper), max_nfev=180,
                          ftol=1e-9, xtol=1e-9, gtol=1e-10) for s in starts]
    opt = min(opts, key=lambda o: np.sum(o.fun**2))
    residual, beta, rank, x = solve(opt.x)
    k = len(opt.x)+len(beta)+1+1  # residual variance + selected discrete delay
    sse = float(residual@residual)
    n = int(np.count_nonzero(w))
    # Nominal iid-Gaussian scores only: deterministic, correlated residuals.
    likelihood = n*np.log(max(sse/n, 1e-30))
    d = opt.x[order:] if kind != 'linear' else (0., 0.)
    sv = np.linalg.svd(opt.jac, compute_uv=False)
    return dict(static=kind, order=order, delay_steps=delay, theta=opt.x.tolist(),
                control_period_s=sequences[0].get('control_dt', sequences[0]['dt']),
                observation_period_s=sequences[0]['dt'],
                coefficients=beta.tolist(), deadband_command=(np.array(d)*SCALE).tolist(),
                tau_or_inverse_wn_s=float(np.exp(opt.x[0])),
                zeta=float(np.exp(opt.x[1])) if order == 2 else None,
                static_rank=rank, static_columns=x.shape[1],
                nonlinear_jacobian_rank=int(np.linalg.matrix_rank(opt.jac)),
                nonlinear_jacobian_condition=float(sv[0]/max(sv[-1], 1e-30)),
                optimizer_success=bool(opt.success), k=k, n=n, sse=sse,
                aic=float(likelihood+2*k), bic=float(likelihood+k*np.log(n)),
                boundary_parameters=[i for i, v in enumerate(opt.x)
                                     if min(v-lower[i], upper[i]-v) < 1e-4])


def predict(sequence, model):
    return np.r_[0., design(sequence, model['static'], model['order'],
                           model['delay_steps'], model['theta']) @ model['coefficients']]


def metrics(sequences, model):
    ys, origins, es, vs, ves = [], [], [], [], []
    for s in sequences:
        p = predict(s, model)
        y = s['y']
        ys.append(y[1:]-y[1:].mean())
        origins.append(y[1:])
        es.append(p[1:]-y[1:])
        vs.append(np.diff(y)/s['dt'])
        ves.append(np.diff(p-y)/s['dt'])
    y, e, v, ve = map(np.concatenate, (ys, es, vs, ves))
    nr = float(np.linalg.norm(e)/max(np.linalg.norm(y), 1e-15))
    return dict(n=len(e), rmse=float(np.sqrt(np.mean(e**2))), nrmse=nr,
                fit_percent=100*(1-nr),
                origin_normalized_rmse=float(np.linalg.norm(e)/max(np.linalg.norm(np.concatenate(origins)), 1e-15)),
                velocity_nrmse=float(np.linalg.norm(ve)/max(np.linalg.norm(v-v.mean()), 1e-15)),
                max_abs_error=float(np.max(np.abs(e))))


def select(candidates):
    """Cross-validation ranks candidates; BIC breaks numerical ties only."""
    return min(candidates, key=lambda c: (round(c['validation']['nrmse'], 6), c['bic']))


def admissible(model):
    d = np.array(model['deadband_command'])/SCALE
    u = np.linspace(-.03, .03, 601)
    velocity = static_basis(u, model['static'], d) @ model['coefficients']
    return bool(model['optimizer_success'] and np.all(np.diff(velocity) >= -1e-9)
                and model['static_rank'] == model['static_columns'])


def adoption(directions):
    """Fail closed; both directions must excite the same complete structure."""
    passing = []
    for m in directions['steps_to_prbs']['candidates']:
        reverse = next(r for r in directions['prbs_to_steps']['candidates']
                       if all(m[k] == r[k] for k in ('static','order','delay_steps')))
        if (all(c['identifiable_static'] and admissible(c)
                and c['validation']['nrmse'] <= THRESHOLD for c in (m,reverse))):
            passing.append(m)
    return select(passing) if passing else None


def bootstrap(sequences, model, count, seed, *, mode):
    """Cluster bootstrap; loss weights preserve every original time history.

    Steps: resample the six full drive+coast segments (missing-sign replicates
    counted, not invented). PRBS: resample circular 5-chip/2.5s residual blocks;
    no sequence splicing or state resets at chips. Conditional on selected delay
    and structure, so intervals are sensitivity, not independent-trial coverage.
    """
    rng = np.random.default_rng(seed)
    lengths = [len(s['u']) for s in sequences]
    parameters, full_support_parameters, failed = [], [], 0
    full_support = 0
    for _ in range(count):
        if mode == 'steps':
            counts = np.bincount(rng.integers(len(lengths), size=len(lengths)), minlength=len(lengths))
            w = np.concatenate([np.full(n, c) for n, c in zip(lengths, counts)])
            required = {'linear':1, 'deadband':2, 'deadband_quadratic':3, 'deadband_pwl':3}[model['static']]
            support = np.concatenate([s['u'] for s, c in zip(sequences, counts) if c])
            identified = all(len(np.unique(np.abs(support[support*sign>0]))) >= required
                             for sign in (1,-1))
        else:
            n, block = sum(lengths), 50
            ix = np.concatenate([(rng.integers(n)+np.arange(block)) % n
                                 for _ in range(int(np.ceil(n/block)))])[:n]
            w = np.bincount(ix, minlength=n)
            identified = model['static'] == 'linear'
        m = fit(sequences, model['static'], model['order'], model['delay_steps'],
                weights=w, start=model['theta'])
        if not m['optimizer_success'] or m['static_rank'] < m['static_columns']:
            failed += 1
            continue
        sample = ([m['tau_or_inverse_wn_s']]
                          + ([m['zeta']] if m['order'] == 2 else [])
                          + m['deadband_command'] + m['coefficients'])
        parameters.append(sample)
        if identified:
            full_support += 1
            full_support_parameters.append(sample)
    names = ['tau_or_inverse_wn_s'] + (['zeta'] if model['order'] == 2 else [])
    names += ['deadband_positive', 'deadband_negative']
    names += [f'coefficient_{i}' for i in range(len(model['coefficients']))]
    return dict(requested=count, retained=len(parameters), rank_or_optimizer_rejected=failed,
                complete_excitation_replicates=full_support,
                seed=seed, mode=mode, conditional_structure_and_delay=True,
                # Retain unstable parameter spread, explicitly not a confidence interval.
                sensitivity_percentiles={name: np.percentile(np.array(parameters)[:, i], [2.5, 50, 97.5]).tolist()
                           for i, name in enumerate(names)} if parameters else {},
                intervals={name: np.percentile(np.array(full_support_parameters)[:, i], [2.5, 50, 97.5]).tolist()
                           for i, name in enumerate(names)} if full_support >= 20 and
                           not (mode == 'steps' and len(sequences) < 3) else None,
                limitation='segment sensitivity only; one deterministic run, no independent repeats; '
                           'fixed structure/delay and amplitude coverage can understate uncertainty')


def load_translation(raw, plan):
    folder = raw/'zone_wide_two_doors_final_v3'
    pose = rows((folder/'eval_only/r1/pose.jsonl').read_bytes())
    commands = [r for r in rows((folder/'robots/r1/commands.jsonl').read_bytes()) if r['kind']=='mecanum']
    dt = plan['control_period_s']
    t = np.array([r['t'] for r in pose])
    p = np.array([r['base_position_m'][:2] for r in pose])
    r = np.array([r['base_rotation'] for r in pose])
    yaw = np.unwrap(np.arctan2(r[:, 1, 0], r[:, 0, 0]))
    if len(pose) != len(commands)+1 or not np.allclose(np.diff(t), dt, atol=1e-8, rtol=0):
        raise ValueError('missing or irregular pose samples')
    if [v['sample_index'] for v in pose] != list(range(len(pose))):
        raise ValueError('pose indices differ')
    expected = [[0., 0., 0.]]*round(plan['initial_hold_s']/dt)
    bounds, cursor = [], len(expected)
    for seg in plan['segments']:
        n = round(seg['duration_s']/dt)
        u = [seg['value'] if seg['axis']==a else 0. for a in ('forward', 'left', 'turn')]
        expected.extend([u]*n)
        bounds.append((cursor, cursor+n, seg))
        cursor += n
    issued = np.array([[c[a] for a in ('forward', 'left', 'turn')] for c in commands])
    if not np.array_equal(issued, expected):
        raise ValueError('issued commands differ from frozen plan')
    if not np.allclose([c['t'] for c in commands], t[:-1], atol=1e-8, rtol=0):
        raise ValueError('command/pose clocks differ')
    if any(abs(c['duration_s']-dt)>1e-9 for c in commands):
        raise ValueError('command leases differ')
    # Integrate displacement increments in midpoint body yaw, not the initial
    # world frame: small accumulated yaw must not masquerade as lateral gain.
    mid = .5*(yaw[1:]+yaw[:-1])
    dp = np.diff(p, axis=0)
    body = np.column_stack((np.cos(mid)*dp[:,0]+np.sin(mid)*dp[:,1],
                            -np.sin(mid)*dp[:,0]+np.cos(mid)*dp[:,1]))
    signals = np.vstack((np.zeros(2), np.cumsum(body, axis=0)))
    result = {}
    for ax, name in enumerate(('forward', 'left')):
        steps, prbs = [], []
        for j, (a, b, seg) in enumerate(bounds):
            if seg['axis'] != name or seg['phase'] != 'step':
                continue
            end = bounds[j+1][1]  # include full 1s coast
            steps.append(dict(name=f'{name}:{seg["value"]}', u=issued[a:end, ax],
                              y=signals[a:end+1, ax]-signals[a, ax], dt=dt))
        pb = [(a,b) for a,b,s in bounds if s['axis']==name and s['phase']=='prbs']
        a = pb[0][0]
        end = max(b for a,b,s in bounds if s['axis']==name)
        prbs.append(dict(name=f'{name}:prbs', u=issued[a:end, ax],
                         y=signals[a:end+1, ax]-signals[a, ax], dt=dt))
        result[name] = (steps, prbs)
    audit = dict(commands=len(commands), poses=len(pose), dt_s=dt,
                 command_plan_mismatches=0, rotation_command_nonzero=int(np.count_nonzero(issued[:,2])),
                 yaw_span_deg=float(np.degrees(np.ptp(yaw))),
                 frame='integrated midpoint-yaw body-frame increments; eval_only targets',
                 initial_state='zero at each complete step+coast and PRBS sequence; no measured velocity')
    return result, audit


def compare(steps, prbs, *, bootstrap_count, seed):
    directions = {}
    for name, training, validation in (('steps_to_prbs', steps, prbs), ('prbs_to_steps', prbs, steps)):
        candidates = []
        for kind in STATICS:
            for order in (1, 2):
                for delay in DELAYS:
                    m = fit(training, kind, order, delay)
                    m['training'] = metrics(training, m)
                    m['validation'] = metrics(validation, m)
                    m['identifiable_static'] = (name=='steps_to_prbs' or kind=='linear')
                    m['admissible'] = admissible(m)
                    m['information_criteria_regular_model'] = m['identifiable_static']
                    candidates.append(m)
        best = select(candidates)
        # PRBS at one magnitude cannot distinguish deadband/slope/curvature.
        # Keep all fits as explicit minimum-norm extrapolation diagnostics.
        identifiable = select([c for c in candidates if c['identifiable_static'] and admissible(c)])
        directions[name] = dict(candidates=candidates, best_cv=best,
                                identifiable_comparison=identifiable,
                                bootstrap=bootstrap(training, identifiable, bootstrap_count,
                                                    seed, mode='steps' if name=='steps_to_prbs' else 'prbs'),
                                missing_excitation=None if name=='steps_to_prbs' else
                                'PRBS has only +/-0.02: deadband and magnitude curve are unidentifiable; '
                                'nonlinear inverse-CV fits use a minimum-norm extension, not recovered parameters')
    return directions


def revision(old, report, manifest_hash):
    new = copy.deepcopy(old)
    new['schema'] = 'ugrp.final_environment_measured_calibration.v2'
    new['revision'] = 'v89-hammerstein-r2'
    new['previous_revision'] = dict(path='calibration_partial.json', sha256=report['old_calibration_sha256'])
    new['motion_measurement_manifest_sha256'] = manifest_hash
    new['motion_source_sha'] = COLLECTION_SHA
    new['legacy_v87_limitations'] = new.pop('limitations', [])
    new['limitations'] = [
        'v89: one deterministic r1 unloaded run; 0.05 s eval_only poses; no new confirmatory data.',
        'Both translational Hammerstein CV gates failed; PRBS uses one magnitude and cannot identify the static curve.',
        'Rotation has only v87 two-sign steps at 0.2 s sampling and no PRBS; no accepted rotation model.',
        'Camera models and map_spread diagnostics retain v87 provenance and limitations; loaded/fine unavailable.',
        'No controller consumes schema v2; PARTIAL_UNLOADED_SIM remains inadmissible for P03.'
    ]
    # Legacy numeric rotation was exploratory, not independently validated.
    # In r2 no active legacy parameter is allowed to bypass the new gate.
    new['params']['motion'] = None
    selected = {axis: adoption(report['axes'][axis]) for axis in ('forward','left')}
    new['params']['motion_hammerstein'] = {**selected, 'rotate': None}
    new['motion_identification'] = dict(report='hammerstein_report.json', threshold_nrmse=THRESHOLD,
        control_period_s=.05, command_units='dimensionless motor fraction',
        velocity_units=dict(forward='m/s', left='m/s', rotate='rad/s'),
        status='REJECTED' if not any(selected.values()) else 'PARTIAL_AXIS_VALIDATION', reason='Only axes passing both CV directions can be populated; '
        'rotation PRBS absent. Candidate coefficients exist only in the diagnostic report.',
        legacy_motion='calibration_partial.json params.motion preserved byte-for-byte in the old revision')
    return new


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raw', type=Path, required=True)
    ap.add_argument('--v87-raw', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--bootstrap', type=int, default=100)
    args = ap.parse_args()
    if args.bootstrap < 1:
        raise ValueError('bootstrap count must be positive')
    require_disjoint_output(args.output, args.raw, args.v87_raw)
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = []
    def tracked(path):
        data = path.read_bytes()
        inputs.append(dict(path=str(path.resolve()), sha256=sha(data), bytes=len(data), kind='file'))
        return data
    def git_input(rev, path):
        data = subprocess.check_output(['git','show',f'{rev}:{path}'], cwd=ROOT)
        inputs.append(dict(path=f'git:{rev}:{path}', sha256=sha(data), bytes=len(data), kind='git_blob'))
        return data
    for path in sorted(args.raw.rglob('*')):
        if path.is_file():
            tracked(path)
    plan = json.loads(git_input(COLLECTION_SHA, PLAN))
    measure_head = subprocess.check_output(['git','rev-parse','origin/codex/calib-measure-v2'],cwd=ROOT).decode().strip()
    plan_branch = git_input(measure_head, PLAN)
    if json.loads(plan_branch) != plan:
        raise ValueError('measurement branch plan changed since collection')
    for path in ('README.md','fit_check_v89.py','fit_check_output.txt','raw_sha256_manifest.tsv.gz','run_v89.sh','run_v89_log.txt'):
        git_input(PR348_SHA, 'experiments/2026-10-01-calib-motion-v89-physics/'+path)
    for path in ('sim/camera_robot_port.py','sim/masterpi_dynamics_v2.py','sim/multi_masterpi_production.py',
                 'sim/masterpi_geometry_v3.py','sim/zone_final_v3_scene.py','sim/final_environment_measurement_v2.py',
                 'sim/masterpi_dynamics_calibration.json','sim/dispatch_contact_profile.py',
                 'sim/zone_cargo_contact.py','sim/final_environment_checks.py',
                 'harness/final_environment_measurement_v2.py','scripts/run_final_environment_measurement_v2.py'):
        git_input(COLLECTION_SHA, path)
    for path in ('scripts/fit_unloaded_hammerstein.py','scripts/fit_final_environment_unloaded.py',
                 'experiments/2026-09-26-vision-loc/vision_motion.py','harness/vision_motion_init.py',
                 'tests/test_unloaded_hammerstein.py','requirements-test.txt',
                 'harness/zone_final_environment.py','scripts/run_ci_tests.py',
                 'experiments/2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py',
                 RECORD+'/fit_report.json', RECORD+'/input_manifest.tsv'):
        tracked(ROOT/path)
    old_bytes = tracked(ROOT/RECORD/'calibration_partial.json')
    old = json.loads(old_bytes)
    data, audit = load_translation(args.raw, plan)
    # Rotation uses one v87 map only: the three copies are the same trajectory.
    from scripts.fit_final_environment_unloaded import motion_windows
    v87 = args.v87_raw/'zone_wide_two_doors_final_v3'
    commands = rows(tracked(v87/'robots/r1/commands.jsonl'))
    labels = rows(tracked(v87/'eval_only/r1/camera_labels.jsonl'))
    rotation = []
    for w in motion_windows(commands, labels):
        if w['axis'] == 2:
            u = np.where(w['times'][:-1] < w['duration']-1e-8, w['u'][2], 0.)
            rotation.append(dict(name=f'rotate:{w["u"][2]}', dt=.2, control_dt=.25, u=u, y=w['body'][:,2]))
    report = dict(schema='ugrp.offline_hammerstein_fit.v1', status='EXPLORATORY_REJECTED',
                  collection_sha=COLLECTION_SHA, old_calibration_sha256=sha(old_bytes),
                  gate=dict(nrmse_max=THRESHOLD, fit_percent_min=95.,
                            metric='norm(prediction-observation)/norm(observation-per-sequence mean)',
                            requirements=['both CV directions <=5%', 'static excitation identifiable',
                                          'no invalid or nonconverged model', 'axis-specific PRBS available']),
                  audit=audit, environment=dict(python=sys.version, platform=platform.platform(),
                  numpy=np.__version__, scipy=__import__('scipy').__version__), axes={})
    report['information_criteria_scope'] = ('Nominal iid Gaussian output-error AIC/BIC, with n raw position samples '
        'and k=nonlinear parameters+static coefficients+variance+one selected delay. '
        'Autocorrelated deterministic residuals violate iid assumptions. Rank-deficient reverse nonlinear '
        'fits have nominal scores only, not regular likelihood comparisons. Selection uses CV first.')
    report['selection_scope'] = ('Previously inspected v89 development data; validation is used to compare '
        'structures, not a fresh confirmatory test. No independent replicate or physical validation.')
    for i, (axis, (steps, prbs)) in enumerate(data.items()):
        print('fit', axis, flush=True)
        report['axes'][axis] = compare(steps, prbs, bootstrap_count=args.bootstrap, seed=911+i)
        print(axis, {k:v['best_cv']['validation']['nrmse'] for k,v in report['axes'][axis].items()}, flush=True)
    candidates = []
    for order in (1, 2):
        for delay in DELAYS:
            m = fit(rotation, 'linear', order, delay)
            m['training'] = metrics(rotation, m)
            m['validation'] = None
            candidates.append(m)
    report['axes']['rotate'] = dict(status='INSUFFICIENT_EXCITATION', v89_nonzero_commands=0,
        v87_unique_segments=2, v87_dt_s=.2, magnitudes=[.03],
        cv_nrmse=None, cv_fit_percent=None, candidates=candidates,
        bootstrap=bootstrap(rotation, min(candidates,key=lambda c:c['bic']), args.bootstrap, 913, mode='steps'),
        limitation='one magnitude per sign; no PRBS. Deadband/curvature not identifiable. '
                   'Map copies are not independent repeats; in-sample rotation fits cannot qualify.')
    # Raw and local sources must remain unchanged for the complete offline run.
    for inp in inputs:
        if inp['kind']=='file' and sha(Path(inp['path']).read_bytes()) != inp['sha256']:
            raise RuntimeError('input changed: '+inp['path'])
    write(args.output/'input_manifest_v89.json', dict(schema='ugrp.offline_input_manifest.v1', files=inputs,
          local_inputs_unchanged=True, collection_sha=COLLECTION_SHA))
    manifest_hash = sha((args.output/'input_manifest_v89.json').read_bytes())
    report['input_manifest_sha256'] = manifest_hash
    write(args.output/'hammerstein_report.json', report)
    write(args.output/'calibration_partial_r2.json', revision(old, report, manifest_hash))
    print(args.output, flush=True)


if __name__ == '__main__':
    main()
