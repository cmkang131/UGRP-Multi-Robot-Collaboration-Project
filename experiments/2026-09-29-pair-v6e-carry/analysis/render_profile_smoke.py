#!/usr/bin/env python3
"""Stage R smoke check of the floor_light_v1 images: beam colour mask, dark frames, beam-edge tracker (offline, recorded frames).

Usage: render_profile_smoke.py <new raw> [<new raw> ...] --old <raw>   (old = the shadow-profile raw with the same case ids)
Per case-robot over the loaded carry window: mean beam-mask pixels (H 25-90, S>100, V>60, the carry_frame_features mask), fraction of
dark frames (mean V < 8), tracker stats (no_edge / rejected / applied) and the tracker slope change vs the eval-only GT relative yaw
change (ratio through origin). GT is the analysis target only.
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parents[2]))
import fit_carry_pair_yaw as pfit  # noqa: E402
from yaw_direction_dataset import case_dir  # noqa: E402


def frame_stats(raw, case_id, rid, t_lo, t_hi):
    d = case_dir(raw, case_id)
    rb = json.load(open(d/'robots.json'))
    px, dark, n = [], 0, 0
    for f in rb[rid]['frames']:
        if f['report'].get('load_state') != 'loaded' or not (t_lo <= f['t'] <= t_hi):
            continue
        hsv = np.asarray(Image.open(d/'frames'/rid/f'{f["frame"]:05d}.jpg').convert('HSV')).astype(int)
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        px.append(int(((H > 25) & (H < 90) & (S > 100) & (V > 60)).sum())); dark += int(V.mean() < 8); n += 1
    return (float(np.mean(px)) if px else float('nan')), (dark/n if n else float('nan')), n


def rows(raws):
    out = []
    for r in pfit.rows_for([x for x in raws], 1.):
        out.append(r)
    return out


def main():
    a = sys.argv[1:]
    old = a[a.index('--old')+1:] if '--old' in a else []
    new = a[:a.index('--old')] if '--old' in a else a
    rn = rows(new)
    ids = {(r['cell'], r['leg']) for r in rn}
    ro = [r for r in rows(old) if (r['cell'], r['leg']) in ids] if old else []

    def ratio(rs):
        p = [(r['d_slope_total'], r['d_rel_gt']) for r in rs if r['d_rel_gt'] is not None and abs(r['d_rel_gt']) > math.radians(.5)]
        if len(p) < 2:
            return float('nan'), len(p)
        s, y = np.array([q[0] for q in p]), np.array([q[1] for q in p])
        return float(s@y/(y@y)), len(p)
    for name, rs in (('new floor_light_v1', rn), ('old shadow profile (same case ids)', ro)):
        if not rs:
            continue
        stats = {k: sum(r['stats'].get(k, 0) for r in rs) for k in ('frames', 'no_edge', 'rejected', 'applied', 'resets')}
        rt, n = ratio(rs)
        print(f'{name}: case-robots {len(rs)}  tracker {stats}  slope->yaw ratio {rt:.3f} (n {n})')
    print('mean beam-mask px per frame / dark-frame fraction (new | old), per case-robot:')
    for r in rn:
        cid = None
    def cases(raws):
        m = {}
        for raw in raws:
            for l in open(pfit.OUT/f'pair-stage-probes-{raw}'/'cases.jsonl'):
                c = json.loads(l)
                if c.get('stage') == 'carry' and not c.get('host_error') and c['seed'] == 911:
                    m[(c['cell'], c['leg'])] = (raw, c)
        return m
    cn, co = cases(new), cases(old)
    for k in sorted(cn, key=lambda x: (x[0], x[1])):
        raw, c = cn[k]
        for rid in ('r1', 'r2'):
            t0 = c['entry_sim_s']; tex = max(c['exit_sim_s'].values())
            pn = frame_stats(raw, c['case_id'], rid, t0, tex)
            po = frame_stats(*[co[k][0], co[k][1]['case_id']], rid, co[k][1]['entry_sim_s'], max(co[k][1]['exit_sim_s'].values())) if k in co else (float('nan'),)*3
            print(f'  {k[0]:9s} L{k[1]} {rid}: px {pn[0]:8.0f} | {po[0]:8.0f}  ratio {pn[0]/po[0] if po[0] else float("nan"):.2f}   dark {pn[1]:.2f} | {po[1]:.2f}  frames {pn[2]} | {po[2]}')


if __name__ == '__main__':
    main()
