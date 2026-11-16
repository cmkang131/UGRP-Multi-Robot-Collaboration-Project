#!/usr/bin/env python3
"""Independent tabulation of the b-v6h1 sealed-analysis cohort (read-only; does NOT re-run the analysis).

Reads only ``classifier.json`` (sealed v2 output) and the blinded raw's ``cases.jsonl`` and writes
``per_case.csv`` (72 rows) and ``distributions.json`` next to this file (or to --output-dir).
"""
import argparse
import csv
import json
import statistics as st
from pathlib import Path

RAW = Path('/Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930')
SEALED = Path('/Users/changmin/projects/ugrp/outputs/v6h1-sealed-analysis-v2-20261001')
GATE_YAW_RAD = 3 * 3.141592653589793 / 180  # harness.zone_own_guards.GATE_LOADED (52.4 mrad)


def q(v, p):
    v = sorted(v)
    k = (len(v) - 1) * p
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def dist(v):
    return {'n': len(v), 'min': min(v), 'median': st.median(v), 'p90': q(v, .9), 'max': max(v)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent)
    a = ap.parse_args()
    cl = json.loads((SEALED / 'classifier.json').read_text())
    raw = {}
    for line in (RAW / 'cases.jsonl').read_text().splitlines():
        r = json.loads(line)
        raw[r['case_id']] = r
    out = []
    for att in sorted(cl['attempts'], key=lambda x: (x['seed'], x['placement'])):
        r = raw[att['case_id']]
        c = r['chain']['curves']
        sg = max(r['sigma_yaw_max'].values())
        miss = [f"{leg}/{rb}/{ax}" for leg, d in att['sigma'].items() for rb, s in d['signed'].items()
                for i, ax in enumerate(('x', 'y', 'yaw')) if abs(s['e'][i]) > 2 * s['sd'][i]]
        out.append({
            'case': att['placement'], 'seed': att['seed'], 'class': att['class'],
            'sim_stop_s': r['stop_sim_s'], 'stage_sim_s': r['stage_sim_s'], 'chain_sim_s': att['end_window']['L1_end_sim_s'] - r['entry_sim_s'],
            'wall_s': r['wall_s'], 'cmd_r1': r['command_total']['r1'], 'cmd_r2': r['command_total']['r2'],
            'cmd_pair': r['command_total']['r1'] + r['command_total']['r2'],
            'end_err_L0_m': c['end_error_m'][0], 'end_err_L1_m': c['end_error_m'][1],
            'yaw_drift_L0_deg': c['yaw_drift_deg'][0], 'yaw_drift_L1_deg': c['yaw_drift_deg'][1],
            'max_tilt_deg': att['hard_limit_chain']['max_tilt_deg'], 'max_pen_m': att['hard_limit_chain']['max_pen_m'],
            'contact_episodes': att['contact_episodes_whole_chain'], 'sigma_yaw_max_rad': sg, 'sigma_yaw_gate_margin_rad': GATE_YAW_RAD - sg,
            'grasp_events_r1': sum(1 for x in r['chain']['timelines']['r1'] if x[2] == 'grasp'),
            'localizer_resets': r['localizer_resets_stat']['r1'] + r['localizer_resets_stat']['r2'],
            'sigma_2sigma_misses': ';'.join(miss),
        })
    a.output_dir.mkdir(parents=True, exist_ok=True)
    with open(a.output_dir / 'per_case.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    cols = ('sim_stop_s', 'stage_sim_s', 'chain_sim_s', 'wall_s', 'cmd_pair', 'cmd_r1', 'cmd_r2', 'end_err_L0_m', 'end_err_L1_m',
            'max_tilt_deg', 'max_pen_m', 'contact_episodes', 'sigma_yaw_max_rad', 'sigma_yaw_gate_margin_rad')
    dists = {}
    for name, sel in (('seed941', lambda x: x['seed'] == 941), ('seed943', lambda x: x['seed'] == 943), ('all72', lambda x: True)):
        rows = [x for x in out if sel(x)]
        dists[name] = {c: dist([x[c] for x in rows]) for c in cols}
        dists[name]['classes'] = {k: sum(x['class'] == k for x in rows) for k in sorted({x['class'] for x in rows})}
    dists['sigma_2sigma_misses'] = [(x['case'], x['seed'], x['sigma_2sigma_misses']) for x in out if x['sigma_2sigma_misses']]
    (a.output_dir / 'distributions.json').write_text(json.dumps(dists, indent=1) + '\n')
    print(json.dumps({'rows': len(out), 'classes': dists['all72']['classes']}))


if __name__ == '__main__':
    main()
