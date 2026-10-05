#!/usr/bin/env python3
"""Offline fit / held-out evaluation of the v102 loaded pair gain and lag calibration.

Never imports a simulator, renderer or controller. Ground truth (``eval_only/trajectory.jsonl``) is read ONLY here, as an
offline calibration product; it never reaches a command table. Rules: experiments/2026-10-05-loaded-gain-calibration-v102/
PREREGISTRATION.md (+ ADDENDUM_fit_definitions.md, written before any fit).

Stages (each writes a new directory; nothing is overwritten):
  fit       fit-role segments only -> fit.json (three static-map forms per axis, descriptive steady-state table)
  evaluate  frozen fit.json + held-out segments -> heldout.json (per-axis selection by the registered rule)
  product   fit.json + heldout.json -> new calibration file (base calibration with ``motion_loaded`` replaced)

The model is the particle filter's own predictor (harness/owncam_localizer.py ``predict_to``): 0.05 s steps, first-order
velocity lag per axis while a command is active, one shared stop lag when every axis is commanded zero, position integrated
from the updated velocity. Static maps: R0 ramp(c0=0), R1 ramp(c0 free), A affine dead zone (subtract u0).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import final_pair_loaded_gain_v102 as env  # noqa: E402  (static plan only)

DT = .05
FORMS = ('R0', 'R1', 'A')
AXES = env.AXES                       # ('forward', 'left')
FIT_ROLES = ('fit', 'fit_duration')
HELD_ROLES = ('heldout', 'heldout_leg')
WEIGHT_FLOOR_M = .10                  # residual / max(|D_truth|, 0.10 m)  (addendum)
BEAM_Z_MIN_M, SEPARATION_M, SEPARATION_TOL_M = .10, .944, .02
ACCEPT = {'step_rel': .03, 'leg_rel': .025, 'min_d_m': .10, 'rms_ratio': 1.5}
BOUNDS = {'g': (.05, 4.), 'tau': (.03, 3.), 'tau_stop': (.01, .5), 'u1': (1e-3, .2), 'c0': (0., .05), 'u0': (0., .05)}
INTERIOR_FRAC = .005                  # a variable closer than this fraction of its range to a bound is not interior
FCC_LEFT_LEG_M = .7698                # recorded fcc5215f left leg (-0.0622, 128 ticks), r1 local-left displacement
CURRENT_LOADED = {'gain': {'forward': 1.3550711149042434, 'left': .9642052319923683},
                  'tau_axis_s': {'forward': .9659095671490097, 'left': .9677901571181826},
                  'tau_stop_s': .08517977552355656,
                  'u1': {'forward': .026556708949971457, 'left': .028235672526345113}}
V92_EXPLORATORY = {'forward': {'g': 1.5709, 'u0': .00557}, 'left': {'g': 1.1746, 'u0': .00725}}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def write_new(path, obj):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False, sort_keys=True) + '\n')
    (path.parent / (path.name + '.sha256')).write_text(sha_file(path) + '\n')


def git_clean_sha():
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip()
    return sha, not dirty


# ----------------------------------------------------------------------------------------------------------- data
def qyaw(w, x, y, z):
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def load_run(raw, run_id, plan):
    """Truth along the commanded axis (r1 body axis at motion start), time grid, validity gate. Offline only."""
    run = env.run_row(plan, run_id)
    folder = Path(raw) / run_id
    result = json.loads((folder / 'result.json').read_text())
    case = result['cases'][0] if 'cases' in result else result
    complete = bool(case.get('protocol_complete')) and case.get('status') == 'COLLECTED_UNQUALIFIED'
    rows = [json.loads(l) for l in (folder / run_id / 'eval_only' / 'trajectory.jsonl').read_text().splitlines()]
    t = np.array([r['t'] for r in rows])
    q = np.array([r['qpos'] for r in rows])
    z = np.array([r['beam_xyz_m'][2] for r in rows])
    if len(t) > 1 and not np.allclose(np.diff(t), DT, atol=1e-6):
        raise ValueError(f'{run_id}: pose log is not on the 0.05 s grid')
    p1, p2 = q[:, 0:2], q[:, 17:19]
    yaw1 = np.array([qyaw(*q[i, 3:7]) for i in range(len(q))])
    yaw2 = np.array([qyaw(*q[i, 20:24]) for i in range(len(q))])
    i0 = round(env.PREP_END_S / DT)
    c, s = math.cos(yaw1[i0]), math.sin(yaw1[i0])
    axis_vec = np.array([c, s]) if run['axis'] == 'forward' else np.array([-s, c])
    s1 = (p1[i0:] - p1[i0]) @ axis_vec
    c2, s2_ = math.cos(yaw2[i0]), math.sin(yaw2[i0])
    axis2 = np.array([c2, s2_]) if run['axis'] == 'forward' else np.array([-s2_, c2])
    s2 = -(p2[i0:] - p2[i0]) @ axis2                      # r2 commands -u: its own axis is reversed
    sep = np.linalg.norm(p1 - p2, axis=1)[i0:]
    valid = (z[i0:] >= BEAM_Z_MIN_M) & (np.abs(sep - SEPARATION_M) <= SEPARATION_TOL_M)
    return {'run': run, 'complete': complete, 's': s1, 's_r2': s2, 'valid': valid, 'beam_z_min': float(z[i0:].min()),
            'sep_min': float(sep.min()), 'sep_max': float(sep.max()), 'n': len(s1) - 1,
            'yaw_drift_rad': float(yaw1[-1] - yaw1[i0]), 'raw_sha256': sha_file(folder / run_id / 'eval_only' / 'trajectory.jsonl')}


def windows(run):
    """Per step: grid indices [a, b] (relative to motion start) covering step + its coast, and bookkeeping."""
    out, t = [], 0.
    segs = run['segments']
    for i, seg in enumerate(segs):
        if seg['phase'] == 'step':
            coast = segs[i + 1]['duration_s'] if i + 1 < len(segs) and segs[i + 1]['phase'] == 'coast' else 0.
            out.append({'index': i, 'role': seg['role'], 'axis': seg['axis'], 'value': seg['value'],
                        'level': abs(seg['value']), 'duration_s': seg['duration_s'],
                        'a': round(t / DT), 'b': round((t + seg['duration_s'] + coast) / DT),
                        'b_step': round((t + seg['duration_s']) / DT), 'b_leg': round((t + seg['duration_s'] + 1.) / DT)})
        t += seg['duration_s']
    return out


# ----------------------------------------------------------------------------------------------------------- model
def u_eff(form, u, shape):
    a = abs(u)
    if form == 'A':
        return math.copysign(max(a - shape['u0'], 0.), u)
    c0 = shape.get('c0', 0.)
    return u * (1. if shape['u1'] <= c0 else min(max((a - c0) / max(shape['u1'] - c0, 1e-9), 0.), 1.))


def simulate(run, form, axis_params, tau_stop):
    """Along-axis displacement at every 0.05 s grid point, exact per-segment recursion of the PF predictor."""
    g, tau, shape = axis_params['g'], axis_params['tau'], axis_params['shape']
    v = x = 0.
    out = [0.]
    for seg in run['segments']:
        n = round(seg['duration_s'] / DT)
        u = seg['value']
        tgt = g * u_eff(form, u, shape) if u != 0 else 0.
        alpha = 1. - math.exp(-DT / max(tau if u != 0 else tau_stop, 1e-6))
        k = np.arange(1, n + 1)
        vk = tgt + (v - tgt) * (1. - alpha) ** k
        xs = x + DT * np.cumsum(vk)
        out.extend(xs.tolist())
        v, x = float(vk[-1]), float(xs[-1])
    return np.array(out)


def split(form, p):
    """Unpack the flat vector: per axis [g, shape..., tau] then tau_stop."""
    k = {'R0': 1, 'R1': 2, 'A': 1}[form]
    per, axes = k + 2, {}
    for i, axis in enumerate(AXES):
        q = p[i * per:(i + 1) * per]
        shape = ({'R0': {'u1': q[1]}, 'R1': {'c0': q[1], 'u1': q[2]}, 'A': {'u0': q[1]}})[form]
        axes[axis] = {'g': q[0], 'tau': q[-1], 'shape': shape}
    return axes, p[-1]


def bounds_for(form):
    lo, hi = [], []
    for _ in AXES:
        lo.append(BOUNDS['g'][0]); hi.append(BOUNDS['g'][1])
        if form == 'R0':
            lo.append(BOUNDS['u1'][0]); hi.append(BOUNDS['u1'][1])
        elif form == 'R1':
            lo += [BOUNDS['c0'][0], BOUNDS['u1'][0]]; hi += [BOUNDS['c0'][1], BOUNDS['u1'][1]]
        else:
            lo.append(BOUNDS['u0'][0]); hi.append(BOUNDS['u0'][1])
        lo.append(BOUNDS['tau'][0]); hi.append(BOUNDS['tau'][1])
    lo.append(BOUNDS['tau_stop'][0]); hi.append(BOUNDS['tau_stop'][1])
    return np.array(lo), np.array(hi)


def names_for(form):
    out = []
    for axis in AXES:
        out += [f'{axis}.g'] + {'R0': [f'{axis}.u1'], 'R1': [f'{axis}.c0', f'{axis}.u1'], 'A': [f'{axis}.u0']}[form] + [f'{axis}.tau']
    return out + ['tau_stop']


def start_points(form, ref):
    """Several starts (never derived from held-out data): current loaded model, v92 exploratory affine, scaled variants."""
    starts = []
    for gs in (.9, 1., 1.15):
        for us in (.5, 1., 2.):
            p = []
            for axis in AXES:
                g0 = ref['g'][axis] * gs
                if form == 'R0':
                    p += [g0, ref['u1'][axis] * us]
                elif form == 'R1':
                    p += [g0, .003 * us, ref['u1'][axis] * us + .02]
                else:
                    p += [g0, V92_EXPLORATORY[axis]['u0'] * us]
                p.append(ref['tau'][axis])
            starts.append(np.array(p + [ref['tau_stop']]))
    return starts


def reference():
    return {'g': {'forward': 1.3, 'left': 1.0}, 'tau': {'forward': .95, 'left': .95}, 'u1': {'forward': .03, 'left': .03},
            'tau_stop': .085}


def collect_windows(runs, roles):
    items = []
    for r in runs:
        for w in windows(r['run']):
            if w['role'] in roles:
                items.append((r, w))
    return items


def residuals(form, p, items, sims_cache=None):
    axes, tau_stop = split(form, p)
    out = []
    cache = {}
    for r, w in items:
        rid = r['run']['id']
        if rid not in cache:
            cache[rid] = simulate(r['run'], form, axes[r['run']['axis']], tau_stop)
        x = cache[rid]
        s = r['s']
        a, b = w['a'], min(w['b'], len(s) - 1)
        d_truth = s[b] - s[a]
        weight = 1. / max(abs(d_truth), WEIGHT_FLOOR_M)
        out.append(((s[a:b + 1] - s[a]) - (x[a:b + 1] - x[a])) * weight)
    return np.concatenate(out)


def fit_form(form, items):
    lo, hi = bounds_for(form)
    best = None
    for p0 in start_points(form, reference()):
        p0 = np.clip(p0, lo + 1e-6, hi - 1e-6)
        res = least_squares(lambda p: residuals(form, p, items), p0, bounds=(lo, hi), x_scale='jac', method='trf',
                            xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=400)
        if best is None or res.cost < best.cost:
            best = res
    frac = np.minimum(best.x - lo, hi - best.x) / (hi - lo)
    return {'params': best.x.tolist(), 'names': names_for(form), 'cost': float(best.cost),
            'rms_weighted_residual': float(math.sqrt(2 * best.cost / max(len(best.fun), 1))), 'status': int(best.status),
            'nfev': int(best.nfev), 'converged': bool(best.status > 0),
            'interior': bool(np.all(frac > INTERIOR_FRAC)), 'min_bound_fraction': float(frac.min()),
            'n_residuals': int(len(best.fun)), 'n_params': int(len(best.x))}


# ------------------------------------------------------------------------------------------------ descriptive tables
def steady_and_tau(r, w):
    """Per-step steady speed (m/s, last 2 s of the step) and time constant from s(t) = v (dt - tau (1 - exp(-dt/tau)))."""
    s = r['s']
    a, b = w['a'], w['b_step']
    seg = s[a:b + 1] - s[a]
    t = np.arange(len(seg)) * DT
    v_ss = float((seg[-1] - seg[-1 - round(2. / DT)]) / 2.) if len(seg) > round(2. / DT) + 1 else float('nan')
    tau = float('nan')
    if len(seg) > 2 and abs(v_ss) > 1e-4:
        grid = np.linspace(.05, 2.5, 120)
        errs = [float(np.sum((seg - v_ss * (t - tt * (1 - np.exp(-t / tt)))) ** 2)) for tt in grid]
        tau = float(grid[int(np.argmin(errs))])
    return v_ss, tau


def steady_table(runs, roles=None):
    rows = []
    for r in runs:
        for w in windows(r['run']):
            if roles is not None and w['role'] not in roles:
                continue
            v, tau = steady_and_tau(r, w)
            rows.append({'run': r['run']['id'], 'axis': w['axis'], 'role': w['role'], 'value': w['value'],
                         'duration_s': w['duration_s'], 'v_ss': v, 'tau_step': tau,
                         'displacement_m': float(r['s'][min(w['b'], len(r['s']) - 1)] - r['s'][w['a']])})
    return rows


def affine_summary(rows):
    out = {}
    for axis in AXES:
        pts = [(abs(x['value']), abs(x['v_ss'])) for x in rows if x['axis'] == axis and x['role'] == 'fit'
               and abs(x['value']) >= .02 and x['duration_s'] >= 6.]
        if len(pts) >= 3:
            u, v = np.array(sorted(pts)).T
            g, b = np.polyfit(u, v, 1)
            out[axis] = {'g': float(g), 'u0': float(-b / g), 'max_abs_resid_m_s': float(np.abs(v - (g * u + b)).max()),
                         'n': len(pts)}
    return out


def tau_spread(rows):
    out = {}
    for axis in AXES:
        taus = [x['tau_step'] for x in rows if x['axis'] == axis and x['role'] in ('fit', 'heldout') and abs(x['value']) >= .025
                and x['duration_s'] >= 6. and not math.isnan(x['tau_step'])]
        out[axis] = {'n': len(taus), 'median': float(np.median(taus)), 'min': float(min(taus)), 'max': float(max(taus)),
                     'relative_spread': float((max(taus) - min(taus)) / np.median(taus))} if taus else {'n': 0}
    return out


def repeatability(rows):
    """Same axis/level/sign/duration/role between the A and B run of an axis: relative displacement difference."""
    out, by = [], {}
    for x in rows:
        by.setdefault((x['axis'], round(x['value'], 6), x['duration_s'], x['role']), {})[x['run']] = x['displacement_m']
    for key, d in by.items():
        if len(d) == 2:
            a, b = d.values()
            if abs(a) > 1e-3:
                out.append({'axis': key[0], 'value': key[1], 'duration_s': key[2], 'role': key[3], 'rel_diff': abs(a - b) / abs(a)})
    return out


# --------------------------------------------------------------------------------------------------------- stages
def load_all(raw, plan, run_ids=None):
    runs = []
    for row in plan['runs']:
        if run_ids and row['id'] not in run_ids:
            continue
        runs.append(load_run(raw, row['id'], plan))
    return runs


def gate(runs):
    report = {}
    for r in runs:
        valid = bool(r['valid'].all())
        report[r['run']['id']] = {'complete': r['complete'], 'carry_valid_all_samples': valid,
                                  'invalid_samples': int((~r['valid']).sum()), 'beam_z_min': r['beam_z_min'],
                                  'sep_min': r['sep_min'], 'sep_max': r['sep_max'], 'yaw_drift_rad': r['yaw_drift_rad']}
    return report


def stage_fit(args):
    plan = env.protocol()
    runs = load_all(args.raw, plan)
    g = gate(runs)
    if not all(v['complete'] and v['carry_valid_all_samples'] for v in g.values()):
        raise ValueError(f'validity gate failed: {json.dumps(g)}')
    items = collect_windows(runs, FIT_ROLES)
    forms = {f: fit_form(f, items) for f in FORMS}
    rows = steady_table(runs, FIT_ROLES)                       # held-out windows are never summarised in the fit stage
    sha, clean = git_clean_sha()
    fit = {'schema': 'ugrp.loaded_gain_fit.v102', 'plan_sha256': sha_file(ROOT / env.CONFIG), 'source_sha': sha,
           'tree_clean': clean, 'scipy': scipy.__version__, 'numpy': np.__version__, 'python': sys.version.split()[0],
           'gate': g, 'forms': forms, 'fit_roles': list(FIT_ROLES), 'n_fit_windows': len(items),
           'raw_sha256': {r['run']['id']: r['raw_sha256'] for r in runs},
           'steady_table': rows, 'affine_on_fit_steps': affine_summary(rows), 'weight_floor_m': WEIGHT_FLOOR_M,
           'held_out_windows_used': False}
    write_new(Path(args.output) / 'fit.json', fit)
    print(json.dumps({f: {k: v[k] for k in ('rms_weighted_residual', 'converged', 'interior')} for f, v in forms.items()}, indent=1))


def predict_window(form, params, r, w, axes_params, tau_stop):
    x = simulate(r['run'], form, axes_params, tau_stop)
    return x


def eval_form(form, p, runs, roles):
    axes, tau_stop = split(form, np.asarray(p, float))
    rows = []
    cache = {}
    for r in runs:
        axis = r['run']['axis']
        key = r['run']['id']
        cache[key] = simulate(r['run'], form, axes[axis], tau_stop)
        for w in windows(r['run']):
            if w['role'] not in roles:
                continue
            s, x = r['s'], cache[key]
            b = min(w['b'], len(s) - 1)
            d_t, d_m = float(s[b] - s[w['a']]), float(x[b] - x[w['a']])
            rows.append({'run': key, 'axis': axis, 'role': w['role'], 'value': w['value'], 'duration_s': w['duration_s'],
                         'd_truth_m': d_t, 'd_model_m': d_m, 'abs_err_m': abs(d_m - d_t),
                         'rel_err': abs(d_m - d_t) / abs(d_t) if abs(d_t) > 1e-9 else float('nan')})
    return rows


def current_model_params():
    """The as-recorded loaded model packed in the R0 layout (comparator only)."""
    p = []
    for axis in AXES:
        p += [CURRENT_LOADED['gain'][axis], CURRENT_LOADED['u1'][axis], CURRENT_LOADED['tau_axis_s'][axis]]
    return p + [CURRENT_LOADED['tau_stop_s']]


def passes(rows):
    big = [x for x in rows if abs(x['d_truth_m']) >= ACCEPT['min_d_m']]
    if not big:
        return False, {}
    worst_step = max(x['rel_err'] for x in big if x['role'] == 'heldout') if any(x['role'] == 'heldout' for x in big) else float('nan')
    worst_leg = max(x['rel_err'] for x in big if x['role'] == 'heldout_leg') if any(x['role'] == 'heldout_leg' for x in big) else float('nan')
    rms = math.sqrt(sum(x['rel_err'] ** 2 for x in big) / len(big))
    ok = (worst_step <= ACCEPT['step_rel'] and worst_leg <= ACCEPT['leg_rel'])
    return bool(ok), {'worst_step_rel': worst_step, 'worst_leg_rel': worst_leg, 'rms_rel': rms, 'n': len(big)}


def select_axis(per_form):
    """Registered rule: converge+interior, then pass (3% steps, 2.5% legs), prefer R0 > R1 > A within 1.5x best RMS."""
    cand = {f: v for f, v in per_form.items() if v['usable'] and v['passes']}
    if not cand:
        return None
    best = min(v['metrics']['rms_rel'] for v in cand.values())
    for f in FORMS:                                           # code-change order
        if f in cand and cand[f]['metrics']['rms_rel'] <= ACCEPT['rms_ratio'] * best:
            return f
    return None


def stage_evaluate(args):
    fit_path = Path(args.fit)
    if sha_file(fit_path) != (fit_path.parent / (fit_path.name + '.sha256')).read_text().strip():
        raise ValueError('fit.json hash mismatch')
    fit = json.loads(fit_path.read_text())
    plan = env.protocol()
    runs = load_all(args.raw, plan)
    per_axis = {}
    for axis in AXES:
        axis_runs = [r for r in runs if r['run']['axis'] == axis]
        per_form = {}
        for f in FORMS:
            rows = [x for x in eval_form(f, fit['forms'][f]['params'], axis_runs, HELD_ROLES)]
            ok, metrics = passes(rows)
            usable = fit['forms'][f]['converged'] and fit['forms'][f]['interior']
            per_form[f] = {'usable': usable, 'passes': ok, 'metrics': metrics, 'rows': rows}
        cur = eval_form('R0', current_model_params(), axis_runs, HELD_ROLES)
        _, cur_metrics = passes(cur)
        per_axis[axis] = {'forms': per_form, 'chosen_form': select_axis(per_form),
                          'current_model': {'metrics': cur_metrics, 'rows': cur}}
    fcc = None
    legs = []
    for r in runs:
        if r['run']['axis'] != 'left':
            continue
        for w in windows(r['run']):
            if w['role'] == 'heldout_leg':
                legs.append({'run': r['run']['id'], 'value': w['value'],
                             'displacement_m': float(abs(r['s'][min(w['b_leg'], len(r['s']) - 1)] - r['s'][w['a']]))})
    if legs:
        fcc = {'recorded_fcc5215f_m': FCC_LEFT_LEG_M, 'new': legs,
               'max_rel_diff': max(abs(x['displacement_m'] - FCC_LEFT_LEG_M) / FCC_LEFT_LEG_M for x in legs),
               'h3_supported': all(abs(x['displacement_m'] - FCC_LEFT_LEG_M) / FCC_LEFT_LEG_M <= .02 for x in legs)}
    chosen = {a: per_axis[a]['chosen_form'] for a in AXES}
    status = 'VALIDATED_DEV' if all(chosen.values()) else 'REJECTED_NO_FORM_PASSES'
    rows_all = steady_table(runs)
    held = {'schema': 'ugrp.loaded_gain_heldout.v102', 'fit_sha256': sha_file(fit_path), 'status': status,
            'chosen_form': chosen, 'per_axis': per_axis, 'acceptance': ACCEPT, 'h3_fcc_leg': fcc,
            'steady_table_all': rows_all, 'tau_spread': tau_spread(rows_all), 'repeatability': repeatability(rows_all),
            'affine_v92_exploratory': V92_EXPLORATORY,
            'raw_sha256': {r['run']['id']: r['raw_sha256'] for r in runs}}
    write_new(Path(args.output) / 'heldout.json', held)
    print(json.dumps({'status': status, 'chosen': chosen, 'h3': fcc and fcc['h3_supported']}, indent=1))


def stage_product(args):
    fit_path, held_path = Path(args.fit), Path(args.heldout)
    for p in (fit_path, held_path):
        if sha_file(p) != (p.parent / (p.name + '.sha256')).read_text().strip():
            raise ValueError(f'{p.name} hash mismatch')
    fit, held = json.loads(fit_path.read_text()), json.loads(held_path.read_text())
    if held['status'] != 'VALIDATED_DEV':
        raise ValueError('held-out acceptance failed; no registered product is written')
    if held['fit_sha256'] != sha_file(fit_path):
        raise ValueError('heldout.json does not belong to this fit.json')
    base = Path(args.base)
    if sha_file(base) != args.base_sha256:
        raise ValueError('base calibration hash mismatch')
    sha, clean = git_clean_sha()
    if not clean:
        raise ValueError('product requires a clean committed tree')
    cal = json.loads(base.read_text())
    ml = cal['params']['motion_loaded']
    gain = [[ml['gain'][i][j] for j in range(3)] for i in range(3)]
    tau_axis, c0, u1, u0 = list(ml['tau_axis_s']), list(ml['deadband']['c0']), list(ml['deadband']['u1']), [0., 0., 0.]
    tau_stop = []
    for i, axis in enumerate(AXES):
        form = held['chosen_form'][axis]
        axes, ts = split(form, np.asarray(fit['forms'][form]['params'], float))
        a = axes[axis]
        gain[i][i], tau_axis[i] = a['g'], a['tau']
        tau_stop.append(ts)
        if form == 'A':
            u0[i], c0[i], u1[i] = a['shape']['u0'], 0., 0.     # subtract-u0 form; ramp disabled for this axis
        elif form == 'R0':
            c0[i], u1[i] = 0., a['shape']['u1']
        else:
            c0[i], u1[i] = a['shape']['c0'], a['shape']['u1']
    ml.update(gain=gain, tau_s=tau_axis[0], tau_axis_s=tau_axis, tau_stop_s=float(np.mean(tau_stop)))
    ml['deadband'] = {'c0': c0, 'u1': u1}
    if any(u0):
        ml['deadband']['u0'] = u0
    ranges = {}
    for axis in AXES:
        ok = [x for x in held['per_axis'][axis]['forms'][held['chosen_form'][axis]]['rows']]
        ranges[axis] = {'max_level_validated': max(abs(x['value']) for x in ok)}
    for f in ('gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'deadband'):
        cal['field_provenance'][f'params.motion_loaded.{f}'] = 'measured_loaded_gain_calibration_v102'
    cal['source_sha'] = sha
    cal['dev_rule'] = args.rule
    cal['loaded_gain_calibration'] = {
        'bundle_id': env.BUNDLE_ID, 'forms': held['chosen_form'], 'fit_sha256': sha_file(fit_path),
        'heldout_sha256': sha_file(held_path), 'heldout_status': held['status'], 'validated_levels': ranges,
        'tau_stop_note': 'shared PF stop lag = mean of the per-axis fitted values',
        'qualification': 'DEV_PILOT loaded HIGH-carry profile (edge_view_150, long_beam, cargo_noslip_v1) measured over the carry command '
                         'range (left 0.0125-0.10, pair forward 0.0125-0.05); NOT MEASURED_SIM, not a confirmation sample; turn, '
                         'noise, load transition and drift unchanged from the parent'}
    cal['parent_calibration'] = {'path': str(base), 'sha256': args.base_sha256}
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 'ugrp.v92_dev_pilot_inputs.v1', 'execution_source_sha': sha, 'working_tree_dirty': False,
                'script_sha256': sha_file(__file__), 'purpose': 'loaded gain calibration v102',
                'fit_sha256': sha_file(fit_path), 'heldout_sha256': sha_file(held_path)}
    write_new(out / 'input_manifest_dev.json', manifest)
    cal['dev_manifest_sha256'] = sha_file(out / 'input_manifest_dev.json')
    write_new(out / 'calibration_dev_pilot_loaded_v102.json', cal)
    print(json.dumps({'product': sha_file(out / 'calibration_dev_pilot_loaded_v102.json'), 'forms': held['chosen_form']}, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='stage', required=True)
    f = sub.add_parser('fit')
    f.add_argument('--raw', required=True, type=Path)
    f.add_argument('--output', required=True, type=Path)
    e = sub.add_parser('evaluate')
    e.add_argument('--raw', required=True, type=Path)
    e.add_argument('--fit', required=True, type=Path)
    e.add_argument('--output', required=True, type=Path)
    q = sub.add_parser('product')
    q.add_argument('--fit', required=True, type=Path)
    q.add_argument('--heldout', required=True, type=Path)
    q.add_argument('--base', required=True, type=Path)
    q.add_argument('--base-sha256', required=True)
    q.add_argument('--rule', default='DEV_PILOT_LOADED_GAIN_V102_v1')
    q.add_argument('--output', required=True, type=Path)
    args = p.parse_args(argv)
    {'fit': stage_fit, 'evaluate': stage_evaluate, 'product': stage_product}[args.stage](args)


if __name__ == '__main__':
    main()
