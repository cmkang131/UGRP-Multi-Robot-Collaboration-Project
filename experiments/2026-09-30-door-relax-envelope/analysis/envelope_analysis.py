#!/usr/bin/env python3
"""Envelope-grid analysis of carry-stage stage-probe raws (--env-y ... cases).

Usage: envelope_analysis.py [--json out.json] <label>=<raw dir> ...

One line per case: placement (beam y, heading, stated prior bias), the standard outcome class (stage-probe criteria incl. the
10 cm end-point check), and a second, envelope-specific class that ignores the end-point check:

  TRAVERSED_CLEAN      controller finished the leg, lift/tilt/jaws/leg-length checks hold, no wall contact
  TRAVERSED_CONTACT    same, but the wall tracker saw contact with penetration <= 5 mm and tilt <= 15 deg
  HARD_LIMIT           contact with penetration > 5 mm or tilt > 15 deg (whatever the controller did)
  BLOCKED_BY_CONTACT   finished the schedule without a controller abort, but a robot/beam touched the wall and the leg length
                       check failed (the pair was held back; nothing in the controller noticed)
  STOPPED              the controller (or partner) aborted the leg (cause recorded)
  OTHER_FAIL           finished but a non-end-point check failed

The end-point check (beam end within 10 cm of the planned route point) also fails for a beam that is simply placed far off the
door axis, so the standard class alone cannot tell "unsafe" from "far from the axis".  GT is analysis only.
"""
import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
import door_relax_analysis as dra  # noqa: E402

HARD = {'max_tilt_deg': 15., 'max_penetration_m': .005}
NAME = re.compile(r'E_y([+-][\d.]+)_h([+-][\d.]+)(?:_b([+-][\d.]+)_([+-][\d.]+))?')


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0., c - h), min(1., c + h))


def fmt_ci(k, n):
    lo, hi = wilson(k, n)
    return f'{k}/{n} [{100 * lo:.0f}-{100 * hi:.0f}%]'


def parse_cell(case_id):
    m = NAME.search(case_id)
    y, h, by, byaw = m.groups()
    return {'y': float(y), 'heading_deg': float(h), 'bias_y_m': float(by or 0), 'bias_yaw_deg': float(byaw or 0)}


def variant_of(case_id):
    return case_id.split(':', 1)[0].split('@', 1)[1]


def envelope_class(r):
    wc = r.get('wall_contact') or {}
    pen = wc.get('max_penetration_m', 0.)
    tilt = wc.get('max_tilt_deg_stage')
    hard = pen > HARD['max_penetration_m'] or (tilt is not None and tilt > HARD['max_tilt_deg'])
    if hard:
        return 'HARD_LIMIT'
    ff = r.get('first_failure')
    if ff:
        return 'STOPPED'
    c = dict(r['checks'])
    c.pop('end_error', None)
    if not all(c.values()):
        return 'BLOCKED_BY_CONTACT' if wc.get('episodes') else 'OTHER_FAIL'
    return 'TRAVERSED_CONTACT' if wc.get('episodes') else 'TRAVERSED_CLEAN'


def leg_of(r):
    m = re.search(r':L(\d)', r['case_id'])
    return int(m.group(1)) if m else 0


def analyse(label, root):
    rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
    man = json.load(open(root / 'manifest.json'))
    print(f'\n== {label}: {root.name} n={len(rows)} load {[round(v, 1) for v in man["environment"].get("loadavg_at_start", [])]}/'
          f'{[round(v, 1) for v in man["environment"].get("loadavg_at_end", [])]} source={man["source"]["source_sha"][:8]} changed={man.get("source_changed")}')
    out = {'label': label, 'raw': str(root), 'cases': []}
    print('variant | leg | y | heading | bias y/yaw | standard | envelope class | first failure | contact (who; max pen mm; walls) | cross-track mm | sigma_yaw max deg | min clr beam/chassis mm')
    for r in sorted(rows, key=lambda r: (variant_of(r['case_id']), leg_of(r), parse_cell(r['case_id'])['y'],
                                         parse_cell(r['case_id'])['heading_deg'], parse_cell(r['case_id'])['bias_y_m'],
                                         parse_cell(r['case_id'])['bias_yaw_deg'])):
        cell = parse_cell(r['case_id'])
        f = dra.case_facts(root, r)
        wc = r.get('wall_contact') or {}
        std = r.get('outcome_class') or ('PASS' if r['passed'] else 'FAIL')
        ecls = envelope_class(r)
        ff = r.get('first_failure') or {}
        m = r.get('metrics') or {}
        sy = r.get('sigma_yaw_max') or {}
        sy_max = max(sy.values()) if sy else None
        item = {'variant': variant_of(r['case_id']), 'leg': leg_of(r), **cell, 'standard': std, 'envelope': ecls, 'cause': r['cause'],
                'first_failure': ff.get('reason'), 'contact': {k: wc.get(k) for k in ('episodes', 'who', 'max_penetration_m', 'wall_geoms', 'first_contact_sim_s')},
                'cross_track_m': m.get('cross_track_m'), 'end_error_m': m.get('end_error_m'), 'yaw_drift_deg': m.get('yaw_drift_deg'),
                'sigma_yaw_max_deg': None if sy_max is None else math.degrees(sy_max), 'min_clear_beam_mm': f['min_clear_beam_mm'],
                'min_clear_chassis_mm': f['min_clear_chassis_mm'], 'stage_sim_s': r.get('stage_sim_s'),
                'nees': {rid: p['nees'] for rid, p in (f['pf'] or {}).items()}}
        out['cases'].append(item)
        print(f" {item['variant']} | L{item['leg']} | {cell['y']:+.3f} | {cell['heading_deg']:+.1f} | {cell['bias_y_m']:+.2f}/{cell['bias_yaw_deg']:+.0f} | "
              f"{std} | {ecls} | {ff.get('reason') or '-'} | "
              f"{(wc.get('who'), round(1000 * wc.get('max_penetration_m', 0), 2), wc.get('wall_geoms')) if wc.get('episodes') else 'none'} | "
              f"{None if item['cross_track_m'] is None else round(1000 * item['cross_track_m'])} | "
              f"{None if sy_max is None else round(item['sigma_yaw_max_deg'], 2)} | {f['min_clear_beam_mm']}/{f['min_clear_chassis_mm']}")
    by = collections.defaultdict(collections.Counter)
    for it in out['cases']:
        by[(it['variant'], it['leg'])][it['envelope']] += 1
        by[(it['variant'], it['leg'])]['std_' + it['standard']] += 1
    print('\nvariant | leg | n | standard PASS_CLEAN (Wilson) | envelope TRAVERSED_CLEAN (Wilson) | TRAVERSED_CONTACT | HARD_LIMIT | BLOCKED | STOPPED | OTHER_FAIL')
    out['tally'] = {}
    for (v, k), c in sorted(by.items()):
        n = sum(c[e] for e in ('TRAVERSED_CLEAN', 'TRAVERSED_CONTACT', 'HARD_LIMIT', 'BLOCKED_BY_CONTACT', 'STOPPED', 'OTHER_FAIL'))
        print(f" {v} | L{k} | {n} | {fmt_ci(c['std_PASS_CLEAN'] + c['std_PASS'], n)} | {fmt_ci(c['TRAVERSED_CLEAN'], n)} | {c['TRAVERSED_CONTACT']} | "
              f"{c['HARD_LIMIT']} | {c['BLOCKED_BY_CONTACT']} | {c['STOPPED']} | {c['OTHER_FAIL']}")
        out['tally'][f'{v}/L{k}'] = dict(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    res = []
    for spec in a.raws:
        label, _, path = spec.partition('=')
        res.append(analyse(label, Path(path)))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
