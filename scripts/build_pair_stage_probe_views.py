#!/usr/bin/env python3
"""Stage-probe raw -> offline-audit derived views for TensorBoard (read-only).

One view per case plus one aggregate per (stage, source). Each view points at
its original file by absolute path + SHA-256 (scripts/export_offline_audit.py
refuses changed originals). Stage probe verdicts, NOT E2E success.

  build_pair_stage_probe_views.py --raw <probe output> [--raw ...] --output <new dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'ugrp.offline_audit_view.v1'
DEFINITION = ('stage probe verdict, NOT E2E success: both robots reached the stage exit by their own controller '
              'state, no in-stage failure, and the eval-only GT stage criteria held (harness/pair_stage_probe.py CRITERIA)')
SHORT = {'align': 'al', 'grasp_lift': 'gl', 'carry': 'ca', 'setdown': 'sd',
         'teacher_grid': 't', 'e2e_checkpoint': 'e2e', 'tolerance_boundary': 'bd'}
DIAG_SHORT = {'fix_age_round': '', 'loaded_yaw_gate_wide': 'G', 'pf_rest_no_abs_noise': 'N', 'rest_noise_off_and_gate_wide': 'NG',
              'image_valid_off': 'V'}
IK_ENVELOPE_TEXT = 'outside the calibrated 14.5..18.0 cm grasp envelope'   # harness.pair_stage_probe.STAGING_IK_ENVELOPE_TEXT
POLICY_SHORT = {'v5h': '', 'b-only': 'B', 'a+b': 'AB', 'b-v6c': 'C'}   # C = v6c (exact clock + grasp-range entry)


def _run_tag(raw):
    """Distinguish several raw runs from one source sha (e.g. -diagC, -bound2); '' for the first grids."""
    tail = raw.name.rsplit('-', 1)[-1]
    return '' if tail in ('grid1', 's45') else '-' + tail


def _pol(policy):
    return POLICY_SHORT[policy] + '-' if POLICY_SHORT[policy] else ''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slug(text):
    return re.sub(r'[^A-Za-z0-9_+-]+', '_', text).strip('_')


def write(out, name, view):
    d = out / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    return name


def staging_infeasible(row, result):
    if row.get('staging_infeasible') or row.get('cause') == 'STAGING_IK_ENVELOPE':
        return True
    return row.get('category', '').startswith('HOST_ERROR') and IK_ENVELOPE_TEXT in str((result.get('host_error') or {}).get('message'))


def case_view(raw, row, manifest):
    d = raw / 'cases' / re.sub(r'[^A-Za-z0-9_.+-]+', '_', row['case_id'])
    src = d / 'result.json'
    result = json.loads(src.read_text())
    cmds = json.loads((d / 'commands.json').read_text()) if (d / 'commands.json').exists() else {}
    commands = sum(1 for r in ('r1', 'r2') for c in cmds.get(r, []) if c['kind'] in ('arm', 'look', 'drive', 'mecanum'))
    scalars = {'offline/stage_pass': int(row['passed'])}
    for rid, n in (row.get('look_commands') or {}).items():
        scalars[f'offline/look_commands/{rid}'] = n
    m = row.get('metrics') or {}
    for rid in ('r1', 'r2'):
        for k in ('grip_x_err_m', 'grip_y_err_m', 'yaw_err_rad'):
            if isinstance(m.get(rid), dict) and m[rid].get(k) is not None:
                scalars[f'gate/{k}/{rid}'] = m[rid][k]
    for k in ('lift_m', 'tilt_deg', 'shift_m', 'beam_travel_m', 'end_error_m', 'cross_track_m', 'along_error_m',
              'yaw_drift_deg'):
        if isinstance(m.get(k), (int, float)):
            scalars[f'gate/{k}'] = m[k]
    for rid, v in (row.get('sigma_yaw_max') or {}).items():          # own-report yaw sigma over the stage (0.4.0 rows)
        if v is not None:
            scalars[f'own/sigma_yaw_max/{rid}'] = v
    for rid, v in ((row.get('own_at_entry') or {}).items()):
        if v and v.get('std_yaw_rad') is not None:
            scalars[f'own/sigma_yaw_entry/{rid}'] = v['std_yaw_rad']
    for rid, n in (row.get('base_motion_commands') or {}).items():
        scalars[f'offline/base_motion_commands/{rid}'] = n
    for rid, rem in (row.get('remaining_at_stop') or {}).items():
        for k in ('grip_x_err_m', 'grip_y_err_m', 'yaw_err_rad'):
            if rem.get(k) is not None:
                scalars[f'gate/stop_{k}/{rid}'] = rem[k]
    for rid, calls in (row.get('relook_calls') or {}).items():
        scalars[f'offline/relook_calls/{rid}'] = len(calls)
    for rid, n in (row.get('localizer_replaced') or {}).items():
        scalars[f'offline/localizer_replaced/{rid}'] = n
    policy = row.get('pair_policy', 'v5h')
    infeasible = staging_infeasible(row, result)
    if infeasible:
        row = {**row, 'cause': 'STAGING_IK_ENVELOPE', 'cause_sub': None}   # 0.4.1 raws recorded HOST_ERROR; the message says why
        scalars['offline/staging_infeasible'] = 1
    view = {'schema': SCHEMA, 'derived_view_only': True,
            'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': ('one stage-probe case (stage probe, not E2E success). Staged from GT/teacher '
                                     'or an E2E checkpoint; controller inputs own RGB/static map/own commands/prior.'),
            'offline_scalars': scalars, 'success': bool(row['passed']), 'success_definition': DEFINITION,
            'model_calls': 0, 'commands': commands,
            'family': 'pair_stage_probe', 'policy': policy, 'case': row['cell'],
            'condition': f"{row['stage']}/{row['source']}", 'seed': row['seed'], 'outcome': row['category'],
            'source_sha': manifest['source']['source_sha'], 'run_id': row['case_id'],
            'contact_profile': 'cargo_noslip_v1', 'scope': 'stage_probe_not_e2e',
            'limits': 'dev; weld OFF; seeds change only the PF RNG (physics repeats are not independent evidence)',
            'texts': {'evaluation/checks': {'checks': row.get('checks'), 'first_failure': row.get('first_failure'),
                                            'final_states': row.get('final_states'), 'metrics': m},
                      'evaluation/labels': {'labels': row['labels']}},
            'hparam_metrics': ['offline/stage_pass']}
    if row.get('stage_sim_s') is not None:
        view['sim_s'] = row['stage_sim_s']
    if row.get('wall_s') is not None:
        view['wall_s'] = row['wall_s']
    diag = ('-pE' if row['case_id'].endswith(':pE2E') or ':pE2E:' in row['case_id'] else '') + \
        ('-dx' + DIAG_SHORT.get(row['diag_patch'], '') if row.get('diag_patch') else '')
    if row.get('diag_patch'):
        view['condition'] += f" diag:{row['diag_patch']}"
    if row.get('leg') is not None:                                  # 0.4.0: route leg (carry k / setdown 'end')
        leg = row['leg']
        view['condition'] += ' dest' if row['stage'] == 'setdown' else f' leg{leg}'   # setdown 'end' = the route destination
        diag += f'-L{leg}' if row['stage'] == 'carry' else '-Lend'
    if row.get('cause'):
        view['cause'] = row['cause'] + (f"/{row['cause_sub']}" if row.get('cause_sub') else '')
        view['outcome'] = f"{row['category']} [{view['cause']}]"
    name = (f"{_pol(policy)}{SHORT[row['stage']]}-{SHORT[row['source']]}-{slug(row['cell'].replace('v6-', ''))}"
            f"-s{row['seed']}{diag}")
    return name, view


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    a.output.mkdir(parents=True, exist_ok=False)
    names = []
    for raw in a.raw:
        manifest = json.loads((raw / 'manifest.json').read_text())
        rows = [json.loads(line) for line in (raw / 'cases.jsonl').read_text().splitlines() if line]
        for row in rows:
            name, view = case_view(raw, row, manifest)
            names.append(write(a.output, name, view))
        summary = raw / 'summary.json'
        s = json.loads(summary.read_text())
        infeasible_ids = {r['case_id'] for r in rows if staging_infeasible(
            r, json.loads((raw / 'cases' / re.sub(r'[^A-Za-z0-9_.+-]+', '_', r['case_id']) / 'result.json').read_text()))}
        for stage, st0 in s['stages'].items():
            for policy, st in (st0.get('by_policy') or {'v5h': st0}).items():
                for source, bs in st['by_source'].items():
                    n_inf = sum(1 for r in rows if r['case_id'] in infeasible_ids and r['stage'] == stage
                                and r['source'] == source and r.get('pair_policy', 'v5h') == policy)
                    view = {'schema': SCHEMA, 'derived_view_only': True,
                            'offline_source': {'path': str(summary), 'sha256': sha(summary)},
                            'offline_scalar_scope': f'aggregate of {bs["cases"]} stage-probe cases ({stage}, {source}); '
                                                    'stage probe, not E2E success',
                            'offline_scalars': {'offline/cases': bs['cases'], 'offline/passed': bs['passed'],
                                                'offline/pass_rate': bs['passed'] / bs['cases'],
                                                'offline/staging_infeasible': n_inf, 'offline/staged_cases': bs['cases'] - n_inf,
                                                'offline/staged_pass_rate': (bs['passed'] / (bs['cases'] - n_inf)
                                                                             if bs['cases'] > n_inf else 0.)},
                            'success': bs['passed'] == bs['cases'], 'success_definition': 'all cases of this group passed; ' + DEFINITION,
                            'model_calls': 0, 'family': 'pair_stage_probe_aggregate', 'policy': policy,
                            'case': 'all', 'condition': f'{stage}/{source}{_run_tag(raw)}', 'outcome': json.dumps(st['failures']),
                            'source_sha': manifest['source']['source_sha'], 'run_id': raw.name,
                            'scope': 'stage_probe_not_e2e', 'texts': {'evaluation/summary': st},
                            'hparam_metrics': ['offline/pass_rate', 'offline/staged_pass_rate', 'offline/cases']}
                    names.append(write(a.output, f'ALL-{_pol(policy)}{SHORT[stage]}-{SHORT[source]}-{manifest["source"]["source_sha"][:8]}{_run_tag(raw)}', view))
    index = {'views': names, 'raw': [str(r) for r in a.raw],
             'raw_summary_sha256': {str(r): sha(r / 'summary.json') for r in a.raw}}
    (a.output / 'index.json').write_text(json.dumps(index, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'output': str(a.output)}))


if __name__ == '__main__':
    main()
