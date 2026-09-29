"""Cal-cohort fit of the yaw flags (carry_pair_yaw, carry_beam_edge): slope-to-yaw ratio and the per-variant yaw bias std.

Input : the three cal1 raws (recorded frames, own commands, eval-only GT trace) of the b-v6e cal cohort, the same
        raws refit_carry_dr_cal.py used. The 33-cell grid, the held-out placements and the cal2 replicate are NOT read
        by the fit (cal2 is only printed as an out-of-fit replicate check, never written into the fit file).
Method: the implemented estimator is replayed per case and robot over the window [entry, exit]:
          own model  : registered loaded plant replayed on the own recorded commands (analysis replay_yaw; matches the
                       PF mean, corr 0.998, RMS 1.5 mrad over a leg)
          partner    : the same replay of the MIRRORED own commands (the plan-derived partner command; no partner data)
          edge       : harness.own_beam_edge.BeamEdgeTracker on the recorded own frames (recorded servo/load state)
        variants: pm = mean(own, mirrored partner); edge = own + edge total; pm+edge = pm + edge total.
        GT (eval-only trace) is the calibration target ONLY: per case-robot rate = (GT yaw change - estimate)/window.
Rule  : b(variant) = cell-balanced RMS of those rates (each cell once, as refit_carry_dr_cal.py); the slope-to-yaw ratio
        is the through-origin least squares slope of the tracker's smoothed slope change on the GT relative yaw change.
Output: carry_pair_fit.json (read by harness/owncam_carry_v6e.py).
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE/'analysis'))
from harness.own_beam_edge import BeamEdgeTracker  # noqa: E402
from yaw_direction_dataset import case_dir, replay_yaw, wrap  # noqa: E402

FIT_RAWS = ['ece38792-cal', 'a704ecc6-calB2', 'a704ecc6-calB']
REPLICATE_RAWS = ['d08818ef-cal2']
OUT = Path('/Users/changmin/projects/ugrp/outputs')
MIN_WINDOW_S = 8.


def rel_yaw(x, rid):
    a = wrap(x['robots'][rid][2] - x['beam_yaw'])
    return a if abs(a) < math.pi/2 else wrap(a - math.pi)      # r2 faces the other way


def mirrored(cmds):
    """The partner's command of a carry leg from the plan: the own leg command with its direction sign flipped."""
    out = []
    for c in cmds:
        if c['kind'] == 'mecanum' and not c['turn'] and (c['forward'] or c['left']):
            c = {**c, 'forward': -c['forward'], 'left': -c['left']}
        out.append(c)
    return out


def track(d, rid, rb, t_lo, t_hi, ratio):
    """Run the tracker over the recorded own frames of one robot; returns (tracker, first ref time, last applied time)."""
    tr = BeamEdgeTracker(ratio)
    first = last = None
    for f in rb[rid]['frames']:
        if not (t_lo <= f['t'] <= t_hi):
            continue
        servo = {int(k): int(v) for k, v in f['commanded_servo'].items()}
        loaded = f['report'].get('load_state') == 'loaded'
        before = tr.stats['applied']
        rgb = None
        # decode only when the tracker will look at the frame (it ignores earlier ones anyway)
        rgb = np.asarray(Image.open(d/'frames'/rid/f'{f["frame"]:05d}.jpg').convert('RGB'))
        tr.observe(f['t'], rgb, servo, loaded)
        if tr.stats['applied'] > before:
            first = f['t'] if first is None else first
            last = f['t']
    return tr, first, last


def rows_for(raws, ratio):
    rows = []
    for raw in raws:
        root = OUT/f'pair-stage-probes-{raw}'
        for line in open(root/'cases.jsonl'):
            c = json.loads(line)
            if c.get('stage') != 'carry' or c.get('host_error') or c.get('category') == 'STAGING_IK_ENVELOPE' or c['seed'] != 911:
                continue
            d = case_dir(raw, c['case_id'])
            if not (d/'robots.json').exists():
                continue
            trace = [json.loads(x) for x in open(d/'eval_only/trace.jsonl')]
            tt = np.array([x['t'] for x in trace])
            t0 = c['entry_sim_s']
            tex = max(c['exit_sim_s'].values()) if c.get('exit_sim_s') else trace[-1]['t']
            win = [i for i, x in enumerate(trace) if t0 <= x['t'] <= tex + 1e-6]
            if len(win) < 2 or trace[win[-1]]['t'] - trace[win[0]]['t'] < MIN_WINDOW_S:
                continue
            ia, ib = win[0], win[-1]
            T = trace[ib]['t'] - trace[ia]['t']
            rb = json.load(open(d/'robots.json'))
            cmds = json.load(open(d/'commands.json'))
            for rid in ('r1', 'r2'):
                tr, ref_t, last_t = track(d, rid, rb, trace[ia]['t'], trace[ib]['t'], ratio)
                ms = replay_yaw(cmds[rid], trace[ia]['t'], trace[ib]['t'])
                mp = replay_yaw(mirrored(cmds[rid]), trace[ia]['t'], trace[ib]['t'])
                g = wrap(trace[ib]['robots'][rid][2] - trace[ia]['robots'][rid][2])
                d_rel = None
                if ref_t is not None and last_t is not None and last_t > ref_t:
                    ka, kb = int(np.argmin(np.abs(tt - ref_t))), int(np.argmin(np.abs(tt - last_t)))
                    d_rel = float(wrap(rel_yaw(trace[kb], rid) - rel_yaw(trace[ka], rid)))
                rows.append({'raw': raw, 'cell': c['cell'], 'leg': c['leg'], 'robot': rid, 'T': T, 'g': g, 'ms': ms, 'mp': mp,
                             'edge': tr.total_rad, 'd_slope_total': tr.total_rad*ratio, 'd_rel_gt': d_rel,
                             'stats': dict(tr.stats)})
                print(raw, c['cell'], c['leg'], rid, 'T %.1f own %+.2f pm %+.2f edge %+.2f gt %+.2f deg' %
                      (T, math.degrees(ms), math.degrees((ms + mp)/2), math.degrees(tr.total_rad), math.degrees(g)), flush=True)
    return rows


def balanced(rows, est):
    per = {}
    for r in rows:
        per.setdefault(r['cell'], []).append((r['g'] - est(r))/r['T'])
    p = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in per.items()}
    return float(np.sqrt(np.mean([v**2 for v in p.values()]))), p, {k: len(v) for k, v in per.items()}


ESTIMATORS = {'e0_registered': lambda r: r['ms'],
              'pm': lambda r: (r['ms'] + r['mp'])/2,
              'edge': lambda r: r['ms'] + r['edge'],
              'pm+edge': lambda r: (r['ms'] + r['mp'])/2 + r['edge']}


def main():
    # pass 1: ratio = 1 (the tracker then returns the smoothed slope change itself)
    rows1 = rows_for(FIT_RAWS, 1.)
    pairs = [(r['d_slope_total'], r['d_rel_gt']) for r in rows1 if r['d_rel_gt'] is not None]
    s, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    ratio = float(s @ y/(y @ y))
    resid = s - ratio*y
    print('\nslope = ratio x relative yaw: n %d ratio %.4f corr %.4f residual sd %.2f mrad of yaw' %
          (len(pairs), ratio, np.corrcoef(s, y)[0, 1], 1e3*np.std(resid)/ratio))
    # pass 2: the estimator with the fitted ratio (the edge totals are the slope totals divided by the ratio)
    for r in rows1:
        r['edge'] = r['d_slope_total']/ratio
    out = {'slope_to_yaw_ratio': ratio, 'b_rad_s': {}, 'estimators': {}}
    for name, f in ESTIMATORS.items():
        b, per, n = balanced(rows1, f)
        out['estimators'][name] = {'balanced_rms_rad_s': b, 'per_cell_rms_rad_s': per, 'n_per_cell': n}
        if name != 'e0_registered':
            out['b_rad_s'][name] = b
        print('  %-14s b = %.5f  per cell %s' % (name, b, {k: round(v*1e3, 2) for k, v in per.items()}))
    rep = rows_for(REPLICATE_RAWS, 1.)
    for r in rep:
        r['edge'] = r['d_slope_total']/ratio
    out['replicate_check_not_in_fit'] = {name: balanced(rep, f)[0] for name, f in ESTIMATORS.items()}
    print('replicate (cal2, not in fit):', {k: round(v*1e3, 2) for k, v in out['replicate_check_not_in_fit'].items()})
    reg = json.load(open(HERE/'carry_dr_fit_cal1.json'))['loeo_range']['yaw']['bias_rate_std_rad_s'][1]
    out['registered_v6e_b_rad_s'] = reg
    out['rule'] = ('b(variant) = cell-balanced RMS over cal1 case-robots of (GT yaw change - replayed estimate)/window, '
                   'window = [entry, exit]; ratio = through-origin LS slope of tracker slope change on GT relative yaw change')
    out['inputs'] = [{'raw': f'pair-stage-probes-{raw}',
                      'cases_jsonl_sha256': hashlib.sha256((OUT/f'pair-stage-probes-{raw}'/'cases.jsonl').read_bytes()).hexdigest()}
                     for raw in FIT_RAWS]
    out['not_read'] = '33-cell grid, held-out placements; cal2 only as a printed replicate check'
    out['n_case_robots'] = len(rows1)
    (HERE/'carry_pair_fit.json').write_text(json.dumps(out, indent=1))
    json.dump(rows1, open(HERE/'carry_pair_fit_rows.json', 'w'), indent=0)


if __name__ == '__main__':
    main()
