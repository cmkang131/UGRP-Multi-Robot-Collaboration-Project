#!/usr/bin/env python3
"""Predicted pass fraction of the planned confirmatory cohort under each proposal (OFFLINE: no new physics).

The along-track part is deterministic and known exactly (plant_model.py, residual < 1 mm against 136 recorded chains): a timed forward
leg of duration T moves the beam F(T); the only free variables are the placement/sheet offset dx and the tick phase of the schedule.
The cross-track part is not deterministic in this offline setting: it comes from the heading left by the open-loop alignment pulse
and the PF yaw error (y_bias_phases.py D), which is modelled from the recorded chains as
    signed y at the leg end = a + b1 * placement yaw + b2 * (placement y - 0.05)   +  bootstrap residual
(fitted on the 68 gain-fix cases: cB, rB, sB). The cross-track model is the weakest link and is reported with a sensitivity range.

A chain passes (the part of the standard leg check this analysis can see) if the end error against the route point
 sqrt(along^2 + cross^2) <= 100 mm at BOTH the L0 end and the L1 end. Contacts, sigma gates and set-down are not modelled: in all
recorded gain-fix cohorts every failure was MOTION_ERROR (end_error); no gate or contact stop occurred.

Usage: predict_pass.py --table <leg_table.json> --placements <placements_confirmatory_DRAFT.json>
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plant_model as pm  # noqa: E402

GATE = 0.100
B_LABELS = ('cB', 'rB', 'sB')
PHASE_F = (0.49, 1.0)     # tick phase of the L1 schedule start, consistent with T_plan 18.351 -> 184 ticks


def const_scale_for_l1():
    """A single CARRY_ODOM_SCALE['axial'] that makes the 0.85 m leg exact under the measured plant."""
    lo, hi = 0.5, 1.2
    for _ in range(60):
        mid = .5 * (lo + hi)
        lo, hi = (lo, mid) if pm.F(0.85 / (pm.SPEED * mid)) < 0.85 else (mid, hi)
    return .5 * (lo + hi)


SCALE_C = const_scale_for_l1()

VARIANTS = {
    'P0 registered (0.772 timed scale)': lambda d: pm.T_registered(d),
    'P1a lag plan, registered PF plant (1.4004): WRONG': lambda d: pm.T_lag(d, pm.PF_GAIN),
    'P1b lag plan, PF plant x kappa (1.3281)  [recommended]': lambda d: pm.T_lag(d, pm.PF_GAIN * pm.KAPPA),
    f'P1c one constant CARRY_ODOM_SCALE axial {SCALE_C:.3f} (exact for 0.85 m only)': lambda d: d / (pm.SPEED * SCALE_C),
    'P2 lag plan, fully recalibrated plant (1.3417, 0.898, 0.006)': lambda d: pm.T_lag(d, pm.GAIN_TRUE, pm.PLANT['tau'], pm.PLANT['tau_stop']),
}


def durations(variant, sheet_x, f):
    d0, d1 = pm.ROUTE_X[1] - sheet_x, pm.ROUTE_X[2] - pm.ROUTE_X[1]
    return pm.ticks_l0(VARIANTS[variant](d0)), pm.ticks_l1(VARIANTS[variant](d1), f)


def snap_y(L):
    s = max([L[k]['end'] for k in ('r1', 'r2')], key=lambda s: s['t'])
    return s['gt_beam'][1] - 0.05


def training(rows):
    X, Y0, Y1, meta = [], [], [], []
    for r in rows:
        if r['label'] not in B_LABELS or len(r['legs']) < 2 or not all(L.get('cmd') for L in r['legs']):
            continue
        X.append([1., math.degrees(r['beam_place'][2]), 1000 * (r['beam_place'][1] - 0.05)])
        Y0.append(1000 * snap_y(r['legs'][0]))
        Y1.append(1000 * snap_y(r['legs'][1]))
        meta.append(r)
    return np.array(X), np.array(Y0), np.array(Y1), meta


def fit_cross(X, Y0, Y1):
    b0 = np.linalg.lstsq(X, Y0, rcond=None)[0]
    b1 = np.linalg.lstsq(X, Y1, rcond=None)[0]
    res = np.column_stack([Y0 - X @ b0, Y1 - X @ b1])
    return b0, b1, res


def pass_case(dx, sheet_x, T0, T1, y0_mm, y1_mm):
    e0, e1 = pm.along_errors(dx, T0, T1, sheet_x)
    end0, end1 = math.hypot(e0, y0_mm / 1000), math.hypot(e1, y1_mm / 1000)
    return end0 <= GATE and end1 <= GATE, end0, end1


F_GRID = np.linspace(PHASE_F[0] + 0.005, PHASE_F[1] - 0.005, 40)


def along_table(variant, sheet_x, dx):
    """Signed along errors [m] at the L0 and L1 end, shape (len(F_GRID), n, 2), for every tick phase of the L1 schedule."""
    out = np.zeros((len(F_GRID), len(sheet_x), 2))
    for a, f in enumerate(F_GRID):
        for i in range(len(sheet_x)):
            T0, T1 = durations(variant, sheet_x[i], f)
            out[a, i] = pm.along_errors(dx[i], T0, T1, sheet_x[i])
    return out


def pf_x_errors(meta):
    """Pair-mean PF x error (estimate - truth, m) at the start of the L0 forward window, and the r1 - r2 difference, gain-fix cases."""
    mean, diff = [], []
    for r in meta:
        t0 = r['legs'][0]['cmd']['t0']
        e = []
        for rid in ('r1', 'r2'):
            best = None
            for p in r['pf_err']:
                if p['t'] <= t0 + 1e-6 and rid in p:
                    best = p[rid]
            e.append(best[0])
        mean.append((e[0] + e[1]) / 2)
        diff.append(e[0] - e[1])
    return np.array(mean), np.array(diff)


def simulate_p3(off, feats, X, Y0, Y1, keys, ex, draws, rng, cross_scale=1.0):
    """P3 (analytic): the first leg length comes from the own PF x, so the along error is the negative PF x error instead of dx."""
    n = off.shape[0]
    uniq = sorted(set(keys))
    by = {u: [i for i, k in enumerate(keys) if k == u] for u in uniq}
    counts = np.zeros(draws, int)
    for j in range(draws):
        pick = [uniq[k] for k in rng.integers(0, len(uniq), len(uniq))]
        idx = np.array([i for u in pick for i in by[u]])
        b0, b1, res = fit_cross(X[idx], Y0[idx], Y1[idx])
        r = res[rng.integers(0, len(res), n)]
        y0 = cross_scale * (feats @ b0 + r[:, 0]) / 1000
        y1 = cross_scale * (feats @ b1 + r[:, 1]) / 1000
        e = off - ex[rng.integers(0, len(ex), n)][:, None]
        counts[j] = ((np.hypot(e[:, 0], y0) <= GATE) & (np.hypot(e[:, 1], y1) <= GATE)).sum()
    return counts


def unit_keys(meta):
    return [(r['label'], r['cell']) for r in meta]


def simulate(al, feats, X, Y0, Y1, keys, draws, rng, drop_yaw_slope=False, cross_scale=1.0, param_boot=True):
    """MC over (tick phase, training-set bootstrap by placement, residual bootstrap). Returns pass counts per draw."""
    n = al.shape[1]
    uniq = sorted(set(keys))
    by = {u: [i for i, k in enumerate(keys) if k == u] for u in uniq}
    counts = np.zeros(draws, int)
    pi = np.zeros(n)
    for j in range(draws):
        if param_boot:
            pick = [uniq[k] for k in rng.integers(0, len(uniq), len(uniq))]
            idx = np.array([i for u in pick for i in by[u]])
        else:
            idx = np.arange(len(Y0))
        b0, b1, res = fit_cross(X[idx], Y0[idx], Y1[idx])
        mu0, mu1 = feats @ b0, feats @ b1
        if drop_yaw_slope:
            mu0, mu1 = mu0 - feats[:, 1] * b0[1], mu1 - feats[:, 1] * b1[1]
        r = res[rng.integers(0, len(res), n)]
        y0 = cross_scale * (mu0 + r[:, 0]) / 1000
        y1 = cross_scale * (mu1 + r[:, 1]) / 1000
        e = al[rng.integers(0, len(F_GRID))]
        ok = (np.hypot(e[:, 0], y0) <= GATE) & (np.hypot(e[:, 1], y1) <= GATE)
        counts[j] = ok.sum()
        pi += ok
    return counts, pi / draws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--table', required=True)
    ap.add_argument('--placements', required=True)
    ap.add_argument('--draws', type=int, default=3000)
    ap.add_argument('--json')
    a = ap.parse_args()
    rows = json.load(open(a.table))['rows']
    plc = json.load(open(a.placements))
    out = []
    P = out.append
    rng = np.random.default_rng(20261001)

    X, Y0, Y1, meta = training(rows)
    keys = unit_keys(meta)
    b0, b1, res = fit_cross(X, Y0, Y1)
    P(f'cross-track model (gain-fix cases, n={len(Y0)}, {len(set(keys))} placements): signed y at the L0 end = {b0[0]:+.1f} {b0[1]:+.2f}*yaw_deg {b0[2]:+.2f}*(y-0.05)[mm];'
      f' L1 end = {b1[0]:+.1f} {b1[1]:+.2f}*yaw {b1[2]:+.2f}*(y-0.05)')
    P(f'  residual sd L0 {res[:, 0].std():.1f} mm, L1 {res[:, 1].std():.1f} mm, corr {np.corrcoef(res.T)[0, 1]:.2f}; R2 L1 {1 - res[:, 1].var() / Y1.var():.2f}')
    P(f'  recorded |y| at the L1 end: mean {np.abs(Y1).mean():.1f} mm, 90th percentile {np.percentile(np.abs(Y1), 90):.1f} mm, max {np.abs(Y1).max():.1f} mm')
    P(f'  the yaw slope {b1[1]:+.1f} mm/deg is what an alignment pulse that achieves ~0.6 of the commanded rotation predicts (0.4 * 1.45 m * pi/180 = 10 mm/deg)')

    # ---- (0) back-test of the along+cross model on the recorded baseline: leave one cohort out
    P('\n== 0. back-test of the model on the recorded baseline (P0), leave one cohort out; expected vs recorded pass (placements)')
    for held in B_LABELS:
        tr = [i for i, r in enumerate(meta) if r['label'] != held]
        te = [i for i, r in enumerate(meta) if r['label'] == held]
        bb0, bb1, rr = fit_cross(X[tr], Y0[tr], Y1[tr])
        exp = 0.0
        for i in te:
            sx = meta[i]['sheet'][0]
            dx_ = meta[i]['beam_place'][0] - sx
            T0, T1 = durations('P0 registered (0.772 timed scale)', sx, 0.75)
            e0, e1 = pm.along_errors(dx_, T0, T1, sx)
            m0, m1 = X[i] @ bb0, X[i] @ bb1
            k = np.mean([math.hypot(e0, (m0 + q[0]) / 1000) <= GATE and math.hypot(e1, (m1 + q[1]) / 1000) <= GATE for q in rr])
            exp += k
        rec = sum(1 for i in te if all(x['end_error_m'] <= GATE for x in meta[i]['legs']))
        P(f'  hold out {held}: model expects {exp:5.1f} of {len(te)} cases to pass, recorded {rec}/{len(te)}')

    # ---- (1) replay of the recorded gain-fix chains
    P('\n== 1. REPLAY on the recorded gain-fix chains (recorded cross-track kept, variant applied to the recorded placement; tick phase f swept)')
    P(f'  {"variant":72s} cases pass   placements pass   worst L1 end error [mm]')
    recorded_pass = sum(1 for r in meta if all(x['end_error_m'] <= GATE for x in r['legs']))
    P(f'  {"recorded run (physics)":72s} {recorded_pass}/{len(meta)}')
    replay = {}
    for v in VARIANTS:
        pc, worst = [], []
        per_pl = {}
        for f in F_GRID[::4]:
            cnt = 0
            for r in meta:
                sx = r['sheet'][0]
                T0, T1 = durations(v, sx, f)
                ok, e0, e1 = pass_case(r['beam_place'][0] - sx, sx, T0, T1, 1000 * snap_y(r['legs'][0]), 1000 * snap_y(r['legs'][1]))
                cnt += ok
                worst.append(e1)
                per_pl.setdefault((r['label'], r['cell']), []).append(ok)
            pc.append(cnt)
        npl = len(per_pl)
        replay[v] = {'cases': float(np.mean(pc)), 'placements': float(np.mean([np.mean(x) for x in per_pl.values()]) * npl), 'worst_mm': 1000 * max(worst)}
        P(f'  {v:72s} {np.mean(pc):5.1f}/{len(meta)}    {replay[v]["placements"]:5.1f}/{npl}          {1000 * max(worst):5.0f}')
    P('  (exact for P0; for the other variants the recorded cross-track is assumed unchanged. P4 is not replayable this way, see 2.)')

    # ---- (2) the planned confirmatory placements
    P(f'\n== 2. the {len(plc)} planned confirmatory placements (placements_confirmatory_DRAFT.json), Monte Carlo ({a.draws} draws over tick phase, training-set bootstrap, residual bootstrap)')
    xs = np.array([p['x'] for p in plc])
    sh = np.array([pm.sheet_of(x) for x in xs])
    dx = xs - sh
    P(f'  order sheets: {dict((float(k), int(v)) for k, v in zip(*np.unique(sh, return_counts=True)))} ; dx = x - sheet: min {1000 * dx.min():+.0f} max {1000 * dx.max():+.0f} mm ;'
      f' rule of the draft (dx <= +33 mm): {int((dx <= .033).sum())}/{len(plc)} = {(dx <= .033).mean():.3f}')
    feats = np.array([[1., p['yaw_deg'], 1000 * (p['y'] - 0.05)] for p in plc])
    results = {}
    tables = {v: along_table(v, sh, dx) for v in VARIANTS}
    P(f'  {"variant":72s} expected pass   along only   P(>=48/60)  P(>=54/60)   count 5/50/95%')
    for v in VARIANTS:
        counts, p_i = simulate(tables[v], feats, X, Y0, Y1, keys, a.draws, rng)
        e = tables[v]
        along_only = float(np.mean(np.all(np.abs(e) <= GATE, axis=2)))
        results[v] = {'expected_pass_fraction': float(counts.mean() / len(plc)), 'along_only_fraction': along_only,
                      'P_ge_48': float((counts >= 48).mean()), 'P_ge_54': float((counts >= 54).mean()),
                      'count_p05_p50_p95': [float(np.percentile(counts, q)) for q in (5, 50, 95)], 'per_placement_pass_prob': p_i.tolist()}
        P(f'  {v:72s} {100 * results[v]["expected_pass_fraction"]:6.1f}%        {100 * along_only:6.1f}%     {results[v]["P_ge_48"]:.3f}       {results[v]["P_ge_54"]:.3f}      {results[v]["count_p05_p50_p95"]}')
    vb = [k for k in VARIANTS if k.startswith('P1b')][0]
    counts, p_i = simulate(tables[vb], feats, X, Y0, Y1, keys, a.draws, rng, drop_yaw_slope=True)
    name = 'P4 = P1b + alignment turn gain fixed (analytic: yaw slope of the cross-track removed)'
    results[name] = {'expected_pass_fraction': float(counts.mean() / len(plc)), 'P_ge_48': float((counts >= 48).mean()), 'P_ge_54': float((counts >= 54).mean()),
                     'count_p05_p50_p95': [float(np.percentile(counts, q)) for q in (5, 50, 95)], 'per_placement_pass_prob': p_i.tolist()}
    P(f'  {name:72s} {100 * results[name]["expected_pass_fraction"]:6.1f}%           -         {results[name]["P_ge_48"]:.3f}       {results[name]["P_ge_54"]:.3f}      {results[name]["count_p05_p50_p95"]}')

    exm, exd = pf_x_errors(meta)
    off = np.array([pm.along_errors(0., *durations(vb, sh[i], 0.75), sh[i]) for i in range(len(plc))])
    counts = simulate_p3(off, feats, X, Y0, Y1, keys, exm, a.draws, rng)
    name3 = 'P3 = P1b + first leg length from the own PF x (analytic; needs a physics check)'
    results[name3] = {'expected_pass_fraction': float(counts.mean() / len(plc)), 'P_ge_48': float((counts >= 48).mean()), 'P_ge_54': float((counts >= 54).mean()),
                      'count_p05_p50_p95': [float(np.percentile(counts, q)) for q in (5, 50, 95)],
                      'pf_x_error_mm': {'pair_mean_sd': float(1000 * exm.std()), 'pair_mean_max': float(1000 * abs(exm).max()), 'r1_minus_r2_mean': float(1000 * exd.mean()),
                                        'r1_minus_r2_sd': float(1000 * exd.std()), 'r1_minus_r2_max': float(1000 * abs(exd).max())}}
    P(f'  {name3:72s} {100 * results[name3]["expected_pass_fraction"]:6.1f}%           -         {results[name3]["P_ge_48"]:.3f}       {results[name3]["P_ge_54"]:.3f}      {results[name3]["count_p05_p50_p95"]}')
    P(f'      (PF x error at the L0 forward start, n={len(exm)}: pair mean sd {1000 * exm.std():.1f} mm, max {1000 * abs(exm).max():.1f} mm; r1-r2 difference {1000 * exd.mean():+.1f} +- {1000 * exd.std():.1f} mm, max {1000 * abs(exd).max():.1f} mm = the timing mismatch between the two robots: {1000 * abs(exd).max() / 51.23:.2f} s at most)')

    # ---- (3) sensitivity
    P('\n== 3. sensitivity to the cross-track assumption (expected pass %, P(>=48/60), P(>=54/60))')
    for label, tb, kw in (('P0 baseline', tables['P0 registered (0.772 timed scale)'], {}), ('P1b', tables[vb], {})):
        for cname, cs in (('cross-track as modelled', 1.0), ('cross-track x 1.5', 1.5), ('cross-track x 2.0', 2.0)):
            counts, _ = simulate(tb, feats, X, Y0, Y1, keys, 1500, rng, cross_scale=cs)
            P(f'  {label:12s} {cname:26s} expected {100 * counts.mean() / len(plc):5.1f}%   P(>=48) {(counts >= 48).mean():.3f}   P(>=54) {(counts >= 54).mean():.3f}')
    counts, _ = simulate(tables[vb], feats, X, Y0, Y1, keys, 1500, rng, cross_scale=2.0, drop_yaw_slope=True)
    P(f'  {"P4":12s} {"cross-track x 2.0":26s} expected {100 * counts.mean() / len(plc):5.1f}%   P(>=48) {(counts >= 48).mean():.3f}   P(>=54) {(counts >= 54).mean():.3f}')

    # ---- (4) what is left
    P('\n== 4. what remains after P1b')
    e = tables[vb][:, :, 1]
    P(f'  along L1 error after P1b: mean {1000 * e.mean():+.1f} mm, per-placement range {1000 * e.min():+.0f} ... {1000 * e.max():+.0f} mm (this is dx, the 0.1 m sheet rounding: |dx| <= 50 mm by construction)')
    pp = np.array(results[vb]['per_placement_pass_prob'])
    for i in np.argsort(pp)[:6]:
        P(f'  lowest pass probability {pp[i]:.2f}: {plc[i]["name"]} x {plc[i]["x"]:.3f} sheet {sh[i]:.1f} dx {1000 * dx[i]:+.0f} mm  yaw {plc[i]["yaw_deg"]:+.2f} y {plc[i]["y"]:+.3f}')
    P('  the dx term is not correctable from the order sheet alone (it is what the sheet does not say); it needs the robots to use their own PF x (see README, option P3)')
    P('  the cross-track term is bounded by the PF yaw error at the alignment pulse (sd ~0.9 deg -> 26 mm over 1.45 m) and by the pulse gain (P4)')
    txt = '\n'.join(out) + '\n'
    print(txt)
    if a.json:
        Path(a.json).write_text(json.dumps({'variants': results, 'replay': replay,
                                            'cross_model': {'L0': b0.tolist(), 'L1': b1.tolist(), 'resid_sd_mm': res.std(0).tolist()},
                                            'dx_mm': (1000 * dx).tolist(), 'sheet_x': sh.tolist()}, indent=1))


if __name__ == '__main__':
    main()
