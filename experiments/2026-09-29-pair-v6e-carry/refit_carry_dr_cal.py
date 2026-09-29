"""Cal-cohort refit of the loaded yaw-drift bias (v6e flag 1), written after the cal honesty gate FAILED.

Why: the first cal cohort (source ece38792/a704ecc6, 40 stage cases, --pf-track) gave mean 3-dof NEES 4.02 (inside
[1.5, 6]) but a yaw +-2 sigma coverage of 82.5 % (< 90 %), because the dev-box bias rate (0.00139 rad/s) is smaller
than the yaw drift seen with two robots holding the beam (lat-/opp, yaw+/same). Pre-registered response: refit on
the CAL raw only; do not read the 33-cell grid or the held-out placements.

Input : the three cal raws (eval-only PF-vs-GT trace of every case). Nothing else.
Rule  : per case and robot, rate = (yaw error at the last PF sample - yaw error at the first) / elapsed [rad/s]
        (the carry is tag-blind, so the PF mean is pure dead reckoning and the error growth is the drift).
        The refit bias std is the cell-balanced RMS of those rates (each cell counts once: PF seeds of the
        nominal cell repeat the same physics, so the three nominal seeds are averaged into one cell weight).
        Only the yaw bias std is changed; x/y terms, the white noise and the gate stay as in carry_dr_fit.json.
Output: carry_dr_fit_cal1.json = carry_dr_fit.json with loeo_range.yaw.bias_rate_std_rad_s[1] replaced.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
P = Path('/Users/changmin/projects/ugrp/outputs')
RAWS = ['pair-stage-probes-ece38792-cal', 'pair-stage-probes-a704ecc6-calB2', 'pair-stage-probes-a704ecc6-calB']


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def main():
    rates, provenance = {}, []
    for name in RAWS:
        root = P/name
        provenance.append({'raw': str(root), 'cases_jsonl_sha256': hashlib.sha256((root/'cases.jsonl').read_bytes()).hexdigest()})
        for line in open(root/'cases.jsonl'):
            c = json.loads(line)
            tr = root/'cases'/c['case_id'].replace('@', '_').replace(':', '_').replace('/', '_')/'eval_only/trace.jsonl'
            rows = [json.loads(x) for x in open(tr)]
            tex = max(c['exit_sim_s'].values()) if c.get('exit_sim_s') else rows[-1]['t']
            pr = [x for x in rows if 'pf' in x and c['entry_sim_s'] <= x['t'] <= tex + 1e-6
                  and all(x['pf'][r].get('initialized') for r in ('r1', 'r2'))]
            for r in ('r1', 'r2'):
                e0 = wrap(pr[0]['robots'][r][2] - pr[0]['pf'][r]['yaw'])
                e1 = wrap(pr[-1]['robots'][r][2] - pr[-1]['pf'][r]['yaw'])
                rates.setdefault(c['cell'], []).append((e1 - e0)/(pr[-1]['t'] - pr[0]['t']))
    per_cell = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in rates.items()}
    balanced = float(np.sqrt(np.mean([v**2 for v in per_cell.values()])))
    fit = json.load(open(HERE/'carry_dr_fit.json'))
    old = fit['loeo_range']['yaw']['bias_rate_std_rad_s']
    fit['loeo_range']['yaw']['bias_rate_std_rad_s'] = [old[0], balanced]
    fit['cal_refit'] = {
        'reason': 'cal honesty gate failed: yaw 2-sigma coverage 82.5 % (< 90 %) with the dev-box bias rate',
        'rule': 'cell-balanced RMS of per-case-robot yaw error growth rate (last minus first PF-vs-GT yaw error over elapsed)',
        'replaced': 'loeo_range.yaw.bias_rate_std_rad_s[1]', 'previous_value': old[1], 'new_value': balanced,
        'per_cell_rms_rad_s': per_cell, 'n_per_cell': {k: len(v) for k, v in rates.items()},
        'inputs': provenance, 'not_read': '33-cell grid, held-out placements'}
    out = HERE/'carry_dr_fit_cal1.json'
    out.write_text(json.dumps(fit, indent=1))
    print(json.dumps(fit['cal_refit'], indent=1))


if __name__ == '__main__':
    main()
