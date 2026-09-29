"""Beam-edge slope in the own wrist RGB vs the GT robot-to-beam relative yaw change, over every recorded carry case.

Offline (recorded frames, read-only). Per case and robot: change over the leg of (a) the slope of the lower edge of the
beam band (fit to the hue mask, central columns; every 3rd loaded frame from 3 s after entry) and (b) the eval-only GT
relative yaw (robot yaw - beam yaw, unwrapped). Output: beam_edge_all_cases.json + a summary print.
"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from beam_edge_vs_relative_yaw import edge_line, wrap, OUT
from yaw_direction_dataset import RAWS, case_dir, replay_yaw

HERE = Path(__file__).resolve().parent


def relyaw(x, r):
    a = wrap(x['robots'][r][2] - x['beam_yaw'])
    return a if abs(a) < math.pi/2 else wrap(a - math.pi)      # r2 faces the other way


def main():
    res = []
    for raw in RAWS:
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
            t0 = c['entry_sim_s']; tex = max(c['exit_sim_s'].values()) if c.get('exit_sim_s') else trace[-1]['t']
            rb = json.load(open(d/'robots.json'))
            cmds_all = json.load(open(d/'commands.json'))
            offsets = json.load(open(d/'case.json'))['offsets']
            for r in ('r1', 'r2'):
                ts, sl, yc, dv = [], [], [], []
                for f in rb[r]['frames'][::3]:
                    if f['report'].get('load_state') != 'loaded' or not (t0 + 3. <= f['t'] <= tex):
                        continue
                    el = edge_line(d/f'frames/{r}/{f["frame"]:05d}.jpg')
                    if el is None:
                        continue
                    ts.append(f['t']); sl.append(el[0]); yc.append(el[1])
                    dv.append(relyaw(trace[int(np.argmin(np.abs(tt - f['t'])))], r))
                if len(ts) < 12:
                    continue
                sl, yc, dv = np.array(sl), np.array(yc), np.unwrap(np.array(dv))
                other = 'r2' if r == 'r1' else 'r1'
                ta, tb = ts[0], ts[-1]
                ia, ib = int(np.argmin(np.abs(tt - ta))), int(np.argmin(np.abs(tt - tb)))
                extra = {'t_a': float(tt[ia]), 't_b': float(tt[ib]), 'offsets': offsets,
                         'g_dyaw': wrap(trace[ib]['robots'][r][2] - trace[ia]['robots'][r][2]),
                         'g_dbeam': wrap(trace[ib]['beam_yaw'] - trace[ia]['beam_yaw']),
                         'm_self': replay_yaw(cmds_all[r], float(tt[ia]), float(tt[ib])),
                         'm_partner': replay_yaw(cmds_all[other], float(tt[ia]), float(tt[ib])),
                         'passed': bool(c['passed'])}
                res.append({'raw': raw, 'cell': c['cell'], 'leg': c['leg'], 'robot': r, 'variant': 'cal' if c['case_id'].endswith(':Vcal') else 'base',
                            'n': len(ts), 'T': ts[-1] - ts[0], 'd_relyaw': float(dv[-1] - dv[0]), 'd_slope': float(sl[-1] - sl[0]),
                            'd_yc': float(yc[-1] - yc[0]), 'sl_first': float(np.mean(sl[:4])), 'yc_first': float(np.mean(yc[:4])), 'dev_first': float(dv[0]),
                            **extra, 'fit_resid_slope_std': float(np.std(np.polyfit(dv - dv[0], sl - sl[0], 1)[0]*(dv - dv[0]) - (sl - sl[0]))) if np.std(dv) > 1e-5 else None})
                print(raw, c['cell'], c['leg'], r, 'rel-yaw change %+.2f deg  slope change %+.4f' % (math.degrees(dv[-1] - dv[0]), sl[-1] - sl[0]), flush=True)
    json.dump(res, open(HERE/'beam_edge_all_cases.json', 'w'), indent=0)
    x = np.array([q['d_relyaw'] for q in res]); y = np.array([q['d_slope'] for q in res])
    A = np.polyfit(x, y, 1)
    print('\ncases:', len(res), ' d_slope = %.3f * d_relyaw + %.5f ; corr %.4f ; residual sd %.5f (= %.2f mrad of relative yaw)' %
          (A[0], A[1], np.corrcoef(x, y)[0, 1], np.std(y - np.polyval(A, x)), np.std(y - np.polyval(A, x))/A[0]*1e3))
    big = np.abs(x) > math.radians(0.5)
    print('cases with |relative yaw change| > 0.5 deg: %d; slope/relyaw ratio median %.3f (min %.3f max %.3f)' %
          (big.sum(), np.median(y[big]/x[big]), np.min(y[big]/x[big]), np.max(y[big]/x[big])))
    small = ~big
    print('cases with small relative yaw change: %d, slope change sd %.5f (max %.5f)' % (small.sum(), np.std(y[small]), np.max(np.abs(y[small]))))


if __name__ == '__main__':
    main()
