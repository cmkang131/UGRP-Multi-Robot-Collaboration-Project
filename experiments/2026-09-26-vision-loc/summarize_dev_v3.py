"""Collect the round-3 dev variants (metrics, configs, rule decisions) into dev_variants_v3.json (record, not a result).

Applies the selection rule of ``dev_plan_v3.json`` with its amendments 1-3
mechanically: a fix is adopted iff against the current base L and P each rise
by <= 0.3 cm AND (A or lost decreases, or L or P decreases by >= 0.3 cm).
Order: a1 (open ends), a2 (slip scales on load changes), stuck step on the
base (s1 / s2, amendment 3), AMCL step on the resulting base (Nav2 / local).
Two parameterisations of one step are ranked by (lost, L, A); ties within 1 %
of frames / 0.2 cm go to the registered default. a2-based variants are
recorded as diagnostics only.
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
DIAGNOSTIC = ('a3_open_scale_stuck', 'a3b_open_scale_stuck_low', 'a3c_open_scale_stuck_low_dom',
              'a3d_open_scale_stuck_dom', 'a4_open_scale_stuck_amcl', 'a5_open_scale_stuck_amcl_local')
RISE_MAX, GAIN_MIN, TIE_M, TIE_SHARE = .003, .003, .002, .01
# amendment 3: AMCL candidates on each possible base (Nav2 first)
AMCL_ON = {'a1_open': ('m1_open_amcl', 'm2_open_amcl_local'),
           's1_open_stuck_low': ('s1n_open_stuck_low_amcl', 's1l_open_stuck_low_amcl_local'),
           's2_open_stuck_low_dom': ('s2n_open_stuck_low_dom_amcl', 's2l_open_stuck_low_dom_amcl_local')}


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


def better(a: dict, b: dict, tie: str) -> tuple[str, str]:
    """'a' or 'b' by (lost, then L, then A); ties within 1 % of frames / 0.2 cm go to ``tie``."""
    La, _, Aa, lost_a, n = lpa(a)
    Lb, _, Ab, lost_b, _ = lpa(b)
    if abs(lost_a - lost_b) > TIE_SHARE*n:
        return ('a' if lost_a < lost_b else 'b'), f'lost {lost_a} vs {lost_b}'
    if abs(La - Lb) > TIE_M:
        return ('a' if La < Lb else 'b'), f'L {La:.4f} vs {Lb:.4f}'
    if abs(Aa - Ab) > TIE_M:
        return ('a' if Aa < Ab else 'b'), f'A {Aa:.4f} vs {Ab:.4f}'
    return tie, f'tie -> {tie}'


def complete(name: str) -> bool:
    return (GRID/name/'metrics.json').exists()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--output', default=str(HERE/'dev_variants_v3.json'))
    ap.add_argument('--extra', nargs='*', default=[], help='further registered variants (name) to record')
    args = ap.parse_args(argv)
    rows = {n: load(n) for n in ('b0_w6_legacy', 'a1_open', 'a2_open_scale') + tuple(args.extra)}
    steps, base = [], 'b0_w6_legacy'
    for n in ('a1_open', 'a2_open_scale'):                      # dev_plan_v3 priority order
        ok, why = adopt(rows[base], rows[n])
        steps.append({'step': n, 'base': base, 'adopted': ok, 'reason': why})
        base = n if ok else base
    if base != 'a1_open':
        raise SystemExit(f'amendment 3 assumes the base a1 after the a2 step, got {base}')
    # amendment 3: stuck step on a1 (s1 mean pose vs s2 dominant-mode pose), then the AMCL step
    for n in ('s1_open_stuck_low', 's2_open_stuck_low_dom'):
        rows[n] = load(n)
    pick, why = better(rows['s1_open_stuck_low'], rows['s2_open_stuck_low_dom'], 'b')
    cand = 's1_open_stuck_low' if pick == 'a' else 's2_open_stuck_low_dom'
    steps.append({'step': 'stuck: s1 vs s2', 'candidate': cand, 'reason': why})
    ok, why = adopt(rows[base], rows[cand])
    steps.append({'step': cand, 'base': base, 'adopted': ok, 'reason': why})
    base = cand if ok else base
    amcl = AMCL_ON.get(base)
    if amcl and all(complete(n) for n in amcl):
        for n in amcl:
            rows[n] = load(n)
        pick, why = better(rows[amcl[0]], rows[amcl[1]], 'a')
        cand = amcl[0] if pick == 'a' else amcl[1]
        steps.append({'step': f'AMCL: {amcl[0]} vs {amcl[1]}', 'candidate': cand, 'reason': why})
        ok, why = adopt(rows[base], rows[cand])
        steps.append({'step': cand, 'base': base, 'adopted': ok, 'reason': why})
        base = cand if ok else base
    else:
        steps.append({'step': 'AMCL', 'pending': amcl})
    for n in DIAGNOSTIC + ('m1_open_amcl', 'm2_open_amcl_local'):
        if n not in rows and complete(n):
            rows[n] = load(n)
    oracle = {n: load(n, 'oracle') for n in rows
              if 'oracle' in json.loads((GRID/n/'metrics.json').read_text())['pooled']}
    plans = ('dev_plan_v3.json', 'dev_plan_v3_amendment1.json', 'dev_plan_v3_amendment2.json',
             'dev_plan_v3_amendment3.json')
    out = {'schema': 'ugrp.vision_loc.dev_variants.v3', 'plan': list(plans),
           'plan_sha256': {p: hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in plans},
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
