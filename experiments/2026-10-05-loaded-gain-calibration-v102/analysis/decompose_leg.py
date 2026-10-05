#!/usr/bin/env python3
"""Where does the recorded +7.2% lateral-leg overshoot come from: static gain map, lag, or the contact profile?

Offline, descriptive (reads fit.json/heldout.json and the raw eval-only trajectory of the v102 left runs; no selection
decision depends on it). The recorded fcc5215f left leg (command -0.0622 x 128 ticks, window [start, end + 1 s]) is replayed
by the PF's own predictor with four hybrids of the as-recorded loaded model and the fitted affine model; the displacement
is compared with the SIM truth of the same leg in the v102 collection (same cargo_noslip_v1 contact, same pair, same
commands).  usage: decompose_leg.py RAW FIT_JSON
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness import final_pair_loaded_gain_v102 as env  # noqa: E402
from scripts import fit_loaded_gain_calibration as F  # noqa: E402

RAW, FIT = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
plan = env.protocol()
runs = [r for r in F.load_all(RAW, plan) if r['run']['id'] == 'latA']
r = runs[0]
w = [x for x in F.windows(r['run']) if x['role'] == 'heldout_leg' and x['value'] < 0][0]
truth = abs(float(r['s'][w['b_leg']] - r['s'][w['a']]))
cur = F.CURRENT_LOADED
fa = dict(zip(FIT['forms']['A']['names'], FIT['forms']['A']['params']))
R0_cur = {'g': cur['gain']['left'], 'tau': cur['tau_axis_s']['left'], 'shape': {'u1': cur['u1']['left']}}
A_fit = {'g': fa['left.g'], 'tau': fa['left.tau'], 'shape': {'u0': fa['left.u0']}}
cases = {
    'as recorded (ramp, tau .968, stop .085)': ('R0', R0_cur, cur['tau_stop_s']),
    'recorded static map + fitted lag':        ('R0', {**R0_cur, 'tau': A_fit['tau']}, fa['tau_stop']),
    'fitted affine map + recorded lag':        ('A', {**A_fit, 'tau': R0_cur['tau']}, cur['tau_stop_s']),
    'fitted affine map + fitted lag (v102)':   ('A', A_fit, fa['tau_stop']),
}
print(f"SIM truth of the leg (v102 latA, left -0.0622 x 128 ticks, window [start, end+1 s]): {truth:.4f} m   (fcc5215f recorded: {F.FCC_LEFT_LEG_M} m)")
steady = [x for x in json.loads(Path(sys.argv[2]).read_text())['steady_table'] if x['axis'] == 'left' and abs(x['value'] - .05) < 1e-9]
print(f"{'model':44s}{'D_leg m':>9s}{'vs truth':>10s}   steady speed at |u|=.0622 m/s")
for name, (form, a, ts) in cases.items():
    x = F.simulate(r['run'], form, {'g': a['g'], 'tau': a['tau'], 'shape': a['shape']}, ts)
    d = abs(float(x[w['b_leg']] - x[w['a']]))
    v = a['g'] * abs(F.u_eff(form, .0622, a['shape']))
    print(f"{name:44s}{d:9.4f}{100*(d/truth-1):+9.2f}%   {v:.5f}")
