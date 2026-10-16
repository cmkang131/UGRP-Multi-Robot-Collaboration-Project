#!/usr/bin/env python3
"""Door-guard relaxation analysis of stage-probe raws (eval-only GT is the analysis target, never a controller input).

Usage: door_relax_analysis.py [--json out.json] <label>=<raw dir> [<label>=<raw dir> ...]

Per raw: pass / contact-recovered / hard-limit / fail counts by leg, failure causes, per-case contact facts
(who touched which wall geom, max penetration), the smallest GT clearance of the beam and the chassis to the door
posts, and the PF honesty numbers (NEES, +-2 sigma coverage) at the last sample of every case-robot.
Rows without an outcome_class (raws recorded without --contact-track) are classed PASS / FAIL only.
"""
import argparse
import collections
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness import zone_own_guards as guards  # noqa: E402

MAP = json.loads((ROOT / 'maps/zones/zone_wide_door_tags_v2_dock_v3.json').read_text())
ALL_BOXES = guards.static_boxes(MAP)
POSTS = [b for b in ALL_BOXES if b['id'].startswith('post_door')]
BEAM_HALF = (0.30, 0.02)
CHASSIS_X, CHASSIS_Y = guards.CHASSIS_X_M, guards.CHASSIS_Y_M


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def case_dir(root, cid):
    return root / 'cases' / cid.replace('@', '_').replace(':', '_').replace('/', '_')


def min_dist_to_posts(points, boxes=None):
    return min(guards._rect_distance(b, x, y) for b in (POSTS if boxes is None else boxes) for x, y in points)


def beam_points(xyz, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for u in np.linspace(-BEAM_HALF[0], BEAM_HALF[0], 31):
        for v in (-BEAM_HALF[1], BEAM_HALF[1]):
            pts.append((xyz[0] + c * u - s * v, xyz[1] + s * u + c * v))
    return pts


def chassis_points(g):
    x, y, yaw = g
    c, s = math.cos(yaw), math.sin(yaw)
    x0, x1 = CHASSIS_X
    pts = [(bx, by) for bx in np.linspace(x0, x1, 6) for by in (-CHASSIS_Y, CHASSIS_Y)]
    pts += [(bx, by) for bx in (x0, x1) for by in np.linspace(-CHASSIS_Y, CHASSIS_Y, 5)]
    return [(x + c * bx - s * by, y + s * bx + c * by) for bx, by in pts]


def case_facts(root, r):
    d = case_dir(root, r['case_id'])
    out = {'min_clear_beam_mm': None, 'min_clear_chassis_mm': None, 'min_clear_any_beam_mm': None,
           'min_clear_any_chassis_mm': None, 'pf': None}
    tp = d / 'eval_only/trace.jsonl'
    if r.get('entry_sim_s') is None or not tp.exists():
        return out
    tr = [json.loads(x) for x in open(tp)]
    t0 = r.get('submit_t') or r['entry_sim_s']
    t1 = max(r['exit_sim_s'].values()) if r.get('exit_sim_s') else (r.get('stop_sim_s') or tr[-1]['t'])
    win = [x for x in tr if t0 <= x['t'] <= t1 + 1e-6]
    if win:
        out['min_clear_beam_mm'] = round(1000 * min(min_dist_to_posts(beam_points(x['beam_xyz'], x['beam_yaw'])) for x in win), 1)
        out['min_clear_chassis_mm'] = round(1000 * min(min_dist_to_posts(chassis_points(x['robots'][rid]))
                                                        for x in win for rid in ('r1', 'r2')), 1)
        out['min_clear_any_beam_mm'] = round(1000 * min(min_dist_to_posts(beam_points(x['beam_xyz'], x['beam_yaw']), ALL_BOXES) for x in win), 1)
        out['min_clear_any_chassis_mm'] = round(1000 * min(min_dist_to_posts(chassis_points(x['robots'][rid]), ALL_BOXES)
                                                            for x in win for rid in ('r1', 'r2')), 1)
    pf_rows = [x for x in win if 'pf' in x]
    pf = {}
    for rid in ('r1', 'r2'):
        last = None
        for x in pf_rows:
            p = x['pf'][rid]
            if not p.get('initialized'):
                continue
            g = x['robots'][rid]
            e = np.array([g[0] - p['x'], g[1] - p['y'], wrap(g[2] - p['yaw'])])
            C = np.array(p['cov'])
            last = (float(e @ np.linalg.solve(C, e)), np.abs(e) / np.sqrt(np.diag(C)), p['std_xy_m'], p['std_yaw_rad'], e)
        if last:
            pf[rid] = {'nees': last[0], 'z': [float(v) for v in last[1]], 'std_xy_m': last[2],
                       'std_yaw_deg': math.degrees(last[3]), 'err_y_mm': 1000 * float(last[4][1]),
                       'err_yaw_deg': math.degrees(float(last[4][2]))}
    out['pf'] = pf
    return out


def leg_of(r):
    m = re.search(r':L(\d)', r['case_id'])
    return int(m.group(1)) if m else 0


def cls_of(r):
    if 'outcome_class' in r:
        return r['outcome_class']
    return 'PASS' if r['passed'] else 'FAIL'


def analyse(label, root):
    rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
    rows.sort(key=lambda r: (leg_of(r), r['case_id']))
    man = json.load(open(root / 'manifest.json'))
    bylg = collections.defaultdict(list)
    for r in rows:
        bylg[leg_of(r)].append(r)
    print(f'\n== {label}: {root.name}  n={len(rows)}  pass(standard)={sum(r["passed"] for r in rows)}'
          f'  load start/end={[round(v, 1) for v in man["environment"].get("loadavg_at_start", [])]}/'
          f'{[round(v, 1) for v in man["environment"].get("loadavg_at_end", [])]}  source={man["source"]["source_sha"][:8]}'
          f'  source_changed={man.get("source_changed")}')
    print('leg | n | PASS_CLEAN | PASS_CONTACT_RECOVERED | FAIL_HARD_LIMIT | FAIL (causes)')
    summary = {'label': label, 'raw': str(root), 'legs': {}, 'cases': []}
    for k in sorted(bylg):
        rs = bylg[k]
        c = collections.Counter(cls_of(r) for r in rs)
        causes = collections.Counter((r['cause'] + (':' + r['cause_sub'] if r.get('cause_sub') else '')) for r in rs if not r['passed'])
        print(f' L{k} | {len(rs)} | {c.get("PASS_CLEAN", c.get("PASS", 0))} | {c.get("PASS_CONTACT_RECOVERED", 0)} | '
              f'{c.get("FAIL_HARD_LIMIT", 0)} | {c.get("FAIL", 0)} {dict(causes) if causes else ""}')
        summary['legs'][f'L{k}'] = {'n': len(rs), **{key: c.get(key, 0) for key in
                                                    ('PASS_CLEAN', 'PASS_CONTACT_RECOVERED', 'FAIL_HARD_LIMIT', 'FAIL', 'PASS')},
                                    'causes': dict(causes)}
    ends = []
    print('case | outcome | first failure | contact (who, walls, max pen mm, first t) | min clear beam/chassis to door posts (mm) | to any wall/post beam/chassis (mm) | overrides | NEES r1/r2')
    for r in rows:
        f = case_facts(root, r)
        wc = r.get('wall_contact') or {}
        ff = r.get('first_failure') or {}
        tag = r['case_id'].split(':', 2)[2]
        nees = '/'.join('%.1f' % f['pf'][rid]['nees'] if f['pf'] and rid in f['pf'] else '-' for rid in ('r1', 'r2'))
        print(' ', tag, '|', cls_of(r), '|', (f"{ff.get('robot_id')} {ff.get('reason')} @{ff.get('sim_s')}" if ff else '-'), '|',
              (f"{wc.get('who')} {wc.get('wall_geoms')} {1000 * wc.get('max_penetration_m', 0):.2f} mm t={wc.get('first_contact_sim_s')}"
               if wc.get('episodes') else 'none' if wc else 'n/a'), '|', f['min_clear_beam_mm'], '/', f['min_clear_chassis_mm'], '|', f['min_clear_any_beam_mm'], '/', f['min_clear_any_chassis_mm'],
              '|', r.get('door_relax_overrides', '-'), '|', nees)
        summary['cases'].append({'case': tag, 'leg': leg_of(r), 'outcome': cls_of(r), 'cause': r['cause'], 'first_failure': ff,
                                 'wall_contact': wc, 'stage_sim_s': r.get('stage_sim_s'), 'overrides': r.get('door_relax_overrides'),
                                 'metrics': r.get('metrics'), **f})
        for rid, p in (f['pf'] or {}).items():
            ends.append(p)
    if ends:
        n = np.array([e['nees'] for e in ends])
        z = np.array([e['z'] for e in ends])
        cov = (z <= 2).mean(0)
        summary['pf_honesty'] = {'n': len(ends), 'mean_nees': float(n.mean()), 'median_nees': float(np.median(n)),
                                 'cov2sigma_x': float(cov[0]), 'cov2sigma_y': float(cov[1]), 'cov2sigma_yaw': float(cov[2])}
        print(f'PF honesty at the last sample of every case-robot (stage window): n={len(ends)} meanNEES={n.mean():.2f} '
              f'median={np.median(n):.2f} cov2sigma x/y/yaw={cov.round(3).tolist()}')
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    out = []
    for spec in a.raws:
        label, _, path = spec.partition('=')
        out.append(analyse(label, Path(path)))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=float))


if __name__ == '__main__':
    main()
