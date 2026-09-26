"""Collect the round-3 dev variants (metrics, configs, rule decisions) into dev_variants_v3.json (record, not a result).

Applies the selection rule registered in ``dev_plan_v3.json`` mechanically:
walk the fixes in priority order from b0; a fix is adopted iff against the
current base L and P each rise by <= 0.3 cm AND (A or lost decreases, or L or P
decreases by >= 0.3 cm); a4 / a5 are two parameterisations of one fix, ranked
by (lost, L, A) with ties (0.2 cm, 1 % of frames) going to a4.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRID = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926/r3/dev-grid')
KEYS = ('n', 'pos_p50_m', 'pos_p90_m', 'pos_p99_m', 'lat_abs_p99_m', 'yaw_p90_deg')
GROUPS = ('all', 'door_zone', 'door_loaded', 'loaded', 'unloaded')
ORDER = ('b0_w6_legacy', 'a1_open', 'a2_open_scale', 'a3_open_scale_stuck')
AMCL = ('a4_open_scale_stuck_amcl', 'a5_open_scale_stuck_amcl_local')
RISE_MAX, GAIN_MIN, TIE_M, TIE_SHARE = .003, .003, .002, .01


def load(name: str, filt: str = 'vision') -> dict:
    path = GRID/name/'metrics.json'
    m = json.loads(path.read_text())
    pooled = m['pooled'][filt]
    rec = m['recovery_pooled'][filt]
    return {'metrics_file': str(path), 'metrics_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'config': f'dev_configs_v3/{name}.json',
            'config_sha256': hashlib.sha256((HERE/'dev_configs_v3'/f'{name}.json').read_bytes()).hexdigest(),
            'episodes': list(m['episodes']), 'filter': filt,
            'pooled': {g: {k: pooled.get(g, {}).get(k) for k in KEYS} for g in GROUPS},
            'recovery': rec, 'per_episode_door_loaded': {
                ep: {k: d[filt].get('door_loaded', {}).get(k) for k in ('n', 'pos_p90_m', 'lat_abs_p99_m', 'yaw_p90_deg')}
                for ep, d in m['episodes'].items() if filt in d},
            'per_episode_all_p90_m': {ep: d[filt]['all']['pos_p90_m'] for ep, d in m['episodes'].items() if filt in d},
            'per_episode_recovery': {ep: r.get(filt) for ep, r in m['recovery'].items()},
            'false_detections': m.get('false_detections', {}).get('pooled')}


def lpa(v: dict) -> tuple:
    d, a = v['pooled']['door_loaded'], v['pooled']['all']
    return d['lat_abs_p99_m'], d['pos_p90_m'], a['pos_p90_m'], v['recovery']['lost_frames'], a['n']


def adopt(base: dict, cand: dict) -> tuple[bool, str]:
    L0, P0, A0, lost0, _ = lpa(base)
    L1, P1, A1, lost1, _ = lpa(cand)
    if L1 - L0 > RISE_MAX or P1 - P0 > RISE_MAX:
        return False, f'L {L0:.4f}->{L1:.4f} or P {P0:.4f}->{P1:.4f} rose by > {RISE_MAX} m'
    better = A1 < A0 or lost1 < lost0 or L0 - L1 >= GAIN_MIN or P0 - P1 >= GAIN_MIN
    why = f'L {L0:.4f}->{L1:.4f}, P {P0:.4f}->{P1:.4f}, A {A0:.4f}->{A1:.4f}, lost {lost0}->{lost1}'
    return better, ('adopted: ' if better else 'not adopted (no gain): ') + why


def rank_amcl(a: dict, b: dict) -> tuple[str, str]:
    La, _, Aa, lost_a, n = lpa(a)
    Lb, _, Ab, lost_b, _ = lpa(b)
    if abs(lost_a - lost_b) > TIE_SHARE*n:
        return ('a4' if lost_a < lost_b else 'a5'), f'lost {lost_a} vs {lost_b}'
    if abs(La - Lb) > TIE_M:
        return ('a4' if La < Lb else 'a5'), f'L {La:.4f} vs {Lb:.4f}'
    if abs(Aa - Ab) > TIE_M:
        return ('a4' if Aa < Ab else 'a5'), f'A {Aa:.4f} vs {Ab:.4f}'
    return 'a4', 'tie -> a4 (Nav2 structure)'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--output', default=str(HERE/'dev_variants_v3.json'))
    ap.add_argument('--extra', nargs='*', default=[], help='further registered variants (name) to record')
    args = ap.parse_args(argv)
    names = ORDER + AMCL + tuple(args.extra)
    rows = {n: load(n) for n in names}
    oracle = {n: load(n, 'oracle') for n in names if 'oracle' in json.loads((GRID/n/'metrics.json').read_text())['pooled']}
    steps, base = [], 'b0_w6_legacy'
    for n in ORDER[1:]:
        ok, why = adopt(rows[base], rows[n])
        steps.append({'step': n, 'base': base, 'adopted': ok, 'reason': why})
        if ok:
            base = n
    pick, why = rank_amcl(rows[AMCL[0]], rows[AMCL[1]])
    cand = AMCL[0] if pick == 'a4' else AMCL[1]
    steps.append({'step': 'augmented MCL: a4 vs a5', 'candidate': cand, 'reason': why})
    if base == ORDER[-1]:
        ok, why = adopt(rows[base], rows[cand])
        steps.append({'step': cand, 'base': base, 'adopted': ok, 'reason': why})
        if ok:
            base = cand
    else:
        steps.append({'step': cand, 'base': base, 'adopted': False,
                      'reason': 'a4/a5 build on a3; a3 was not adopted, so they are not comparable to the base'})
    out = {'schema': 'ugrp.vision_loc.dev_variants.v3', 'plan': 'dev_plan_v3.json',
           'plan_sha256': hashlib.sha256((HERE/'dev_plan_v3.json').read_bytes()).hexdigest(),
           'variants': rows, 'oracle': oracle, 'rule_steps': steps, 'selected': base}
    Path(args.output).write_text(json.dumps(out, indent=1) + '\n')
    for n, r in rows.items():
        L, P, A, lost, _ = lpa(r)
        print(f"{n:32s} L={L} P={P} Y={r['pooled']['door_loaded']['yaw_p90_deg']} A={A} lost={lost} "
              f"inj={r['recovery']['injection_frames']} false={r['recovery']['injection_frames_while_ok']}")
    print(json.dumps(steps, indent=1))
    print('selected:', base)


if __name__ == '__main__':
    main()
