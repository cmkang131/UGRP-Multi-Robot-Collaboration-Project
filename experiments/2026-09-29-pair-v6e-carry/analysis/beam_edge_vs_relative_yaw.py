"""Does the carried-beam edge in the own wrist RGB carry the robot-to-beam relative yaw? (offline, recorded frames)

For carry cases of the cal cohort (frames are recorded, loaded state), fit a line to the lower boundary of the beam band
(hue 40-90 'green' mask of carry_frame_features.py, central columns) and correlate the change of its slope/offset with the
eval-only GT relative yaw (robot yaw - beam yaw) over the same leg. GT is the analysis target only.
"""
import json, math, os, sys
from pathlib import Path
import numpy as np
from PIL import Image

OUT = Path('/Users/changmin/projects/ugrp/outputs')
CASES = [('d08818ef-cal2', 'lat-/opp', 0), ('d08818ef-cal2', 'lat-/opp', 1), ('d08818ef-cal2', 'lat-/opp', 3),
         ('d08818ef-cal2', 'yaw+/same', 0), ('d08818ef-cal2', 'yaw+/same', 1), ('d08818ef-cal2', 'yaw+/same', 3),
         ('d08818ef-cal2', 'nominal', 0), ('d08818ef-cal2', 'nominal', 1), ('d08818ef-cal2', 'nominal', 3)]


def wrap(a):
    return (a + math.pi)%(2*math.pi) - math.pi


def edge_line(path):
    hsv = np.asarray(Image.open(path).convert('HSV')).astype(int)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (H > 25) & (H < 90) & (S > 100) & (V > 60)     # yellow-green beam faces (hue drifts with the lighting)
    cols = np.arange(140, 500, 4)
    xs, ys = [], []
    for c in cols:
        col = green[40:300, c]
        idx = np.flatnonzero(col)
        if len(idx) > 20:
            # lower boundary of the first (top) run
            run_end = idx[0]
            while run_end + 1 < len(col) and col[run_end + 1]:
                run_end += 1
            xs.append(c)
            ys.append(run_end + 40)
    if len(xs) < 20:
        return None
    A = np.polyfit(xs, ys, 1)
    return A[0], A[1] + A[0]*320, len(xs)          # slope (px/px), y at image centre


def main():
    rows = []
    for raw, cell, leg in CASES:
        name = f'carry_b-v6e_teacher_{cell.replace("/", "_")}_s911_pE2E' + (f'_L{leg}' if leg else '') + '_Vcal'
        d = OUT/f'pair-stage-probes-{raw}'/'cases'/name
        if not d.exists():
            print('missing', name); continue
        trace = [json.loads(x) for x in open(d/'eval_only/trace.jsonl')]
        rb = json.load(open(d/'robots.json'))
        case = [json.loads(l) for l in open(OUT/f'pair-stage-probes-{raw}'/'cases.jsonl') if json.loads(l)['case_id'].startswith(f'carry@b-v6e:teacher:{cell}:s911') and json.loads(l)['leg'] == leg][0]
        t0 = case['entry_sim_s']; tex = max(case['exit_sim_s'].values()) if case.get('exit_sim_s') else trace[-1]['t']
        tt = np.array([x['t'] for x in trace])
        for r in ('r1', 'r2'):
            ts, sl, yc, dev = [], [], [], []
            for f in rb[r]['frames']:
                if f['report'].get('load_state') != 'loaded' or not (t0 + 3. <= f['t'] <= tex):
                    continue
                el = edge_line(d/f'frames/{r}/{f["frame"]:05d}.jpg')
                if el is None:
                    continue
                k = int(np.argmin(np.abs(tt - f['t'])))
                x = trace[k]
                ts.append(f['t']); sl.append(el[0]); yc.append(el[1])
                dev.append(wrap(x['robots'][r][2] - x['beam_yaw']))
            if len(ts) < 20:
                print(cell, leg, r, 'too few frames', len(ts)); continue
            ts, sl, yc, dev = map(np.array, (ts, sl, yc, dev))
            dev_c = np.unwrap(dev) - dev[0]
            # per-frame noise of the edge measurement: residual of a linear-in-time fit of the slope over a static stretch is not
            # available; report the raw series statistics instead
            c_sl = np.corrcoef(dev_c, sl)[0, 1] if np.std(dev_c) > 1e-6 else float('nan')
            c_yc = np.corrcoef(dev_c, yc)[0, 1] if np.std(dev_c) > 1e-6 else float('nan')
            beta = np.polyfit(dev_c, sl, 1)[0] if np.std(dev_c) > 1e-6 else float('nan')
            print('%-10s L%d %s n=%3d rel-yaw change %+.2f deg | slope change %+.4f (%.2f deg) std(slope) %.4f | corr(slope) %+.2f corr(yc) %+.2f | d slope/d relyaw %+.2f' %
                  (cell, leg, r, len(ts), math.degrees(dev_c[-1]), sl[-1] - sl[0], math.degrees(math.atan(sl[-1]) - math.atan(sl[0])),
                   np.std(sl), c_sl, c_yc, beta))
            rows.append({'cell': cell, 'leg': leg, 'robot': r, 'n': len(ts), 'dev_change_rad': float(dev_c[-1]),
                         'corr_slope': None if math.isnan(c_sl) else float(c_sl), 'corr_yc': None if math.isnan(c_yc) else float(c_yc),
                         'slope_std': float(np.std(sl)), 'slope_change': float(sl[-1] - sl[0]), 'dslope_drelyaw': None if math.isnan(beta) else float(beta)})
    return rows


if __name__ == '__main__':
    main()
