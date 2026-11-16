"""Yaw-direction analysis, step 1: per case and robot table of yaw change vs the registered loaded-plant prediction.

Offline only. Reads recorded raw (read-only) under /Users/changmin/projects/ugrp/outputs/pair-stage-probes-*; no physics
is run, no source file is changed. GT yaw (``eval_only/trace.jsonl``) is used ONLY as the analysis target; whether a
later model may use a column is decided in ``yaw_direction_models.py`` (columns named ``know_*`` are quantities the
controller has or could measure; ``gt_*`` and placement identity are leaks).

For every carry case and robot it records
  * window: [entry_sim_s, exit] (stop time for failed cases), as in refit_carry_dr_cal.py;
  * GT yaw change of the robot and of the beam over that window;
  * the registered loaded-plant prediction of the yaw change, by replaying the robot's own recorded mecanum commands
    through ``motion_loaded`` of calibration_loop_v2.json (first-order lag, tau 0.8 s / stop 0.05 s, gain row 3);
    where the run tracked the PF (cal cohorts) the PF mean yaw change is stored too, to validate the replay;
  * commands (mean forward / left per second of the window, moving time) and the staged offsets (own frame).
Output: yaw_direction_dataset.json (rows) and a validation print.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = Path('/Users/changmin/projects/ugrp/outputs')
CAL = json.load(open(ROOT/'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'))['params']
MP = CAL['motion_loaded']
GAIN = np.asarray(MP['gain'], float)
TAU, TAU_STOP = float(MP['tau_s']), float(MP['tau_stop_s'])
STEP = .05

# raw -> label. Only b-v6e cal cohorts (PF tracked) and the physical full-leg diagnostic runs (sigma held / all three
# patches: the commands are open loop, the physics is the same). Baseline b-v6c and the gate-wide runs stop at ~3 s.
RAWS = {
    'ece38792-cal': 'cal1', 'a704ecc6-calB2': 'cal1', 'a704ecc6-calB': 'cal1', 'd08818ef-cal2': 'cal2',
    'a704ecc6-smokeC': 'smoke',
    'e1c99f99-dxSigma': 'sig', 'e1c99f99-dxSigB': 'sig', 'e1c99f99-dxSigC': 'sig', 'e1c99f99-dxSigD': 'sig',
    'e1c99f99-dxSigE': 'sig', '3061a66e-dxAllC': 'all3', '64767041-dxAllC2': 'all3', '64767041-dxAllD': 'all3',
    '64767041-dxAllS': 'all3', 'cc84a791-postAllL3': 'all3',
}


def wrap(a):
    return (a + math.pi)%(2*math.pi) - math.pi


def case_dir(raw, cid):
    return OUT/f'pair-stage-probes-{raw}'/'cases'/cid.replace('@', '_').replace(':', '_').replace('/', '_')


def replay_yaw(cmds, t0, t1):
    """Yaw change [rad] of the registered loaded plant over [t0, t1] for the recorded command list."""
    seq = [c for c in cmds if c['kind'] in ('mecanum', 'hold', 'drive')]
    seq.sort(key=lambda c: c['t'])
    vel = np.zeros(3)
    cmd, expires, yaw, i = np.zeros(3), -1., 0., 0
    t = t0
    # state at t0: the last command issued before t0 (its remaining life) - the leg starts at entry
    while i < len(seq) and seq[i]['t'] <= t0 + 1e-9:
        c = seq[i]
        if c['kind'] == 'mecanum':
            cmd, expires = np.array([c['forward'], c['left'], c['turn']], float), c['t'] + float(c['duration_s'])
        elif c['kind'] == 'drive':
            cmd, expires = np.array([c['forward'], 0., c['turn']], float), c['t'] + float(c['duration_s'])
        else:
            cmd, expires = np.zeros(3), -1.
        i += 1
    while t < t1 - 1e-9:
        while i < len(seq) and seq[i]['t'] <= t + 1e-9:
            c = seq[i]
            if c['kind'] == 'mecanum':
                cmd, expires = np.array([c['forward'], c['left'], c['turn']], float), c['t'] + float(c['duration_s'])
            elif c['kind'] == 'drive':
                cmd, expires = np.array([c['forward'], 0., c['turn']], float), c['t'] + float(c['duration_s'])
            else:
                cmd, expires = np.zeros(3), -1.
            i += 1
        dt = min(STEP, t1 - t)
        u = cmd if t < expires - 1e-9 else np.zeros(3)
        tau = TAU_STOP if not np.any(u) else TAU
        vel = vel + (1. - math.exp(-dt/tau))*(GAIN@u - vel)
        yaw += vel[2]*dt
        t += dt
    return yaw


def command_summary(cmds, t0, t1):
    """Mean forward / left command per second of live time, and the union time [s] a nonzero drive command is live.

    Commands are re-issued every ~0.1 s with a 0.15 s duration, so the live time is the union of the intervals
    (a 'hold' ends the previous command)."""
    seq = sorted((c for c in cmds if c['kind'] in ('mecanum', 'hold')), key=lambda c: c['t'])
    ivs, f, l = [], 0., 0.
    for i, c in enumerate(seq):
        if c['kind'] != 'mecanum' or not (abs(c['forward']) > 1e-3 or abs(c['left']) > 1e-3):
            continue
        end = c['t'] + float(c['duration_s'])
        if i + 1 < len(seq):
            end = min(end, seq[i + 1]['t'])       # the next command (or hold) replaces this one
        a, b = max(c['t'], t0), min(end, t1)
        if b > a:
            ivs.append((a, b))
            f += c['forward']*(b - a)
            l += c['left']*(b - a)
    live = sum(b - a for a, b in ivs)
    return (f/live if live else 0.), (l/live if live else 0.), live


def build():
    rows = []
    for raw, group in RAWS.items():
        root = OUT/f'pair-stage-probes-{raw}'
        if not (root/'cases.jsonl').exists():
            continue
        for line in open(root/'cases.jsonl'):
            c = json.loads(line)
            if c.get('stage') != 'carry' or c.get('host_error') or c.get('category') == 'STAGING_IK_ENVELOPE':
                continue
            d = case_dir(raw, c['case_id'])
            tr = d/'eval_only/trace.jsonl'
            if not tr.exists():
                continue
            case = json.load(open(d/'case.json'))
            trace = [json.loads(x) for x in open(tr)]
            cmds_all = json.load(open(d/'commands.json'))
            t0 = float(c['entry_sim_s'])
            t1 = max(c['exit_sim_s'].values()) if c.get('exit_sim_s') else trace[-1]['t']
            win = [x for x in trace if t0 - 1e-6 <= x['t'] <= t1 + 1e-6]
            if len(win) < 5:
                continue
            a, b = win[0], win[-1]
            T = b['t'] - a['t']
            for r in ('r1', 'r2'):
                f, l, live = command_summary(cmds_all[r], a['t'], b['t'])
                if live < 5.:
                    continue          # the leg did not really move (stopped in the alignment interval)
                gt = wrap(b['robots'][r][2] - a['robots'][r][2])
                beam = wrap(b['beam_yaw'] - a['beam_yaw'])
                pred = replay_yaw(cmds_all[r], a['t'], b['t'])
                pf, pa, pb = None, None, None
                pfrows = [x for x in win if 'pf' in x and x['pf'][r].get('initialized')]
                if len(pfrows) >= 2:
                    pa, pb = pfrows[0], pfrows[-1]
                    pf = wrap(pb['pf'][r]['yaw'] - pa['pf'][r]['yaw'])
                    pf_T = pb['t'] - pa['t']
                # heading-relative to the own facing so r2's world yaw ~pi does not matter (wrap handled above)
                rows.append({
                    'raw': raw, 'group': group, 'case_id': c['case_id'], 'variant': 'cal' if c['case_id'].endswith(':Vcal') else 'base',
                    'cell': c['cell'], 'seed': c['seed'], 'leg': c['leg'], 'robot': r, 'passed': bool(c['passed']),
                    'category': c['category'], 'T_s': T, 'live_s': live, 'cmd_fwd_mean': f, 'cmd_left_mean': l,
                    'gt_dyaw': gt, 'gt_dbeam': beam, 'model_dyaw': pred, 'pf_dyaw': pf,
                    'offsets': case['offsets'],
                    'std_yaw_entry': (pa['pf'][r]['std_yaw_rad'] if pa else None),
                    'std_yaw_end': (pb['pf'][r]['std_yaw_rad'] if pb else None),
                    'gt_dyaw_pfwin': (wrap(pb['robots'][r][2] - pa['robots'][r][2]) if pa else None),
                    'pf_T_s': (pf_T if pa else None), 'pf_t0': (pa['t'] if pa else None),
                })
    return rows


if __name__ == '__main__':
    rows = build()
    (HERE/'yaw_direction_dataset.json').write_text(json.dumps(rows, indent=0))
    print('rows', len(rows))
    by = defaultdict(int)
    for r in rows:
        by[(r['group'], r['variant'])] += 1
    print(dict(by))
    v = [(r['model_dyaw'], r['pf_dyaw']) for r in rows if r['pf_dyaw'] is not None]
    m, p = np.array(v).T
    print('replay vs PF mean yaw change: n=%d, RMS diff %.5f rad, max %.5f, corr %.4f' %
          (len(v), np.sqrt(np.mean((m - p)**2)), np.max(np.abs(m - p)), np.corrcoef(m, p)[0, 1]))
