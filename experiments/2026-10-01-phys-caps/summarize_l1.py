#!/usr/bin/env python3
"""Summarize the two L1 stage-probe groups (read-only over outputs/; no simulator imports).

Reuses the endpoint definition of experiments/2026-09-30-l1-lateral-error/extract.py
(signed axial/lateral endpoint error of the later robot boundary, GT is eval-only).
"""
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIMARY = Path('/Users/changmin/projects/ugrp')
OUTS = PRIMARY / 'outputs'
GROUPS = {'recheck': OUTS / 'phys-caps-1001-l1-recheck', 'probes6': OUTS / 'phys-caps-1001-l1-probes6'}
ACCEPT = OUTS / 'v6h1-acceptance-3c4fe30e-claude-20260930'
SRC_SHA = '4c6b439f3f7c9a147c901f8b260a1e214d4eb396'
GATE_MM = 100.0

spec = importlib.util.spec_from_file_location('l1_extract', PRIMARY / 'experiments/2026-09-30-l1-lateral-error/extract.py')
ext = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ext)
samples = json.loads((PRIMARY / 'experiments/2026-09-29-pair-v6e-carry/hR2_samples.json').read_text())['samples']
MODEL = json.loads((PRIMARY / 'experiments/2026-09-30-l1-lateral-error/results/models.json').read_text())['target_ENV_30_prior']
COEF = MODEL['coefficients_L0_L1']
OOF_SD_L1 = MODEL['OOF_residual_L1']['sd']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def predict(yaw_deg, y, prior_yaw_err_deg):
    feats = [1.0, yaw_deg, 1000 * (y - 0.05), prior_yaw_err_deg]
    return [sum(f * COEF[i][leg] for i, f in enumerate(feats)) for leg in (0, 1)]


def load_group(name, d):
    rows = []
    for line in (d / 'cases.jsonl').read_text().splitlines():
        row = json.loads(line)
        cdir = d / 'cases' / row['case_id'].replace('@', '_').replace(':', '_').replace('/', '_')
        case = json.loads((cdir / 'case.json').read_text())
        result = json.loads((cdir / 'result.json').read_text())
        info = ext.prior_info(case, samples)
        base = {'cohort': name, 'case_id': row['case_id'], 'stage': 'chain', 'cell': row['cell'], 'seed': row['seed'],
                'policy': 'b-v6h1', 'stage_category': row.get('category'), 'wall_episodes': (row.get('wall_contact') or {}).get('episodes'),
                **info}
        bp = case['beam_xyyaw']
        legs = {}
        for leg in (row.get('chain') or {}).get('legs', []):
            if not leg.get('recorded'):
                continue
            k = leg['leg']
            starts = [r.get('leg_start', {}).get(str(k)) for r in result['chain_raw'].values()]
            ends = [r.get('leg_end', {}).get(str(k)) for r in result['chain_raw'].values()]
            e = ext.endpoint_row(base, case, result, k, ext.later(starts), ext.later(ends), leg)
            legs[k] = e
        yaw = math.degrees(ext.wrap(bp[2]))
        pred = predict(yaw, bp[1], info['prior_yaw_error_deg'])
        cmd = cdir / 'commands.json'
        out = {'group': name, 'case_id': row['case_id'], 'cell': row['cell'], 'seed': row['seed'],
               'place_x': bp[0], 'place_y': bp[1], 'place_yaw_deg': yaw, 'prior_id': info['prior_id'],
               'prior_yaw_error_deg': info['prior_yaw_error_deg'],
               'stage_category': row.get('category'), 'host_error': row.get('host_error'),
               'entry_sim_s': row.get('entry_sim_s'), 'stage_sim_s': row.get('stage_sim_s'),
               'sim_s_total': (row.get('entry_sim_s') or 0) + (row.get('stage_sim_s') or 0),
               'wall_s': row.get('wall_s'), 'loadavg_case': row.get('loadavg_case'),
               'command_total': row.get('command_total'), 'model_calls': 0,
               'outcome_class': row.get('outcome_class'), 'wall_contact_episodes': (row.get('wall_contact') or {}).get('episodes'),
               'legs_recorded': sorted(legs), 'pred_lateral_mm': pred,
               'commands_sha256': sha(cmd) if cmd.exists() else None, 'case_dir': str(cdir), 'result_sha256': sha(cdir / 'result.json')}
        for k in (0, 1):
            e = legs.get(k)
            out[f'L{k}_reached'] = e is not None
            out[f'L{k}_axial_mm'] = e['axial_mm'] if e else None
            out[f'L{k}_lateral_mm'] = e['lateral_mm'] if e else None
            out[f'L{k}_end_mm'] = e['end_mm'] if e else None
            out[f'L{k}_yaw_drift_deg'] = e['yaw_drift_deg'] if e else None
        for k in (0, 1):
            out[f'L{k}_lateral_resid_obs_minus_pred_mm'] = (out[f'L{k}_lateral_mm'] - pred[k]) if out[f'L{k}_lateral_mm'] is not None else None
        out['gate_L0_L1_le_100mm'] = all(legs.get(k) and legs[k]['end_mm'] <= GATE_MM for k in (0, 1))
        rows.append(out)
    return sorted(rows, key=lambda r: r['cell'])


def main():
    acc = {(r['cell'], r['sanity']): r for r in json.loads((ACCEPT / 'acceptance_receipts.json').read_text())}
    report = {'source_sha': SRC_SHA, 'gate_mm': GATE_MM, 'groups': {}}
    for name, d in GROUPS.items():
        if not (d / 'cases.jsonl').exists():
            continue
        rows = load_group(name, d)
        man = json.loads((d / 'manifest.json').read_text())
        for r in rows:
            a = acc.get((r['cell'], False))
            r['acceptance_3c4fe30e_commands_sha256'] = a['registered_commands_sha256'] if a else None
            r['commands_identical_to_acceptance_3c4fe30e'] = (r['commands_sha256'] == a['registered_commands_sha256']) if a else None
        report['groups'][name] = {'raw': str(d), 'manifest_sha256': sha(d / 'manifest.json'), 'cases_jsonl_sha256': sha(d / 'cases.jsonl'),
                                  'plan_sha256': sha(d / 'plan.json'), 'state': man['state'], 'wall_s_total': man.get('wall_s'),
                                  'source_execution_tree': man['source']['execution_tree']['sha256'], 'source_changed': man.get('source_changed'),
                                  'loadavg_start_end': [man['environment'].get('loadavg_at_start'), man['environment'].get('loadavg_at_end')],
                                  'cases': rows}
    (HERE / 'l1_results.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    for name, g in report['groups'].items():
        print(name, g['state'], g['wall_s_total'])
        for r in g['cases']:
            f = lambda v: 'NA' if v is None else f'{v:.1f}'
            print(f"  {r['cell']:8s} sim={r['sim_s_total']:.1f} cat={r['stage_category']} gate={r['gate_L0_L1_le_100mm']} "
                  f"L0 ax/lat/end={f(r['L0_axial_mm'])}/{f(r['L0_lateral_mm'])}/{f(r['L0_end_mm'])} "
                  f"L1 ax/lat/end={f(r['L1_axial_mm'])}/{f(r['L1_lateral_mm'])}/{f(r['L1_end_mm'])} "
                  f"pred lat={r['pred_lateral_mm'][0]:.1f}/{r['pred_lateral_mm'][1]:.1f} same_cmds={r['commands_identical_to_acceptance_3c4fe30e']}")


if __name__ == '__main__':
    main()
