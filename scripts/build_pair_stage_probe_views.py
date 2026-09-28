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
         'teacher_grid': 't', 'e2e_checkpoint': 'e2e'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slug(text):
    return re.sub(r'[^A-Za-z0-9_+-]+', '_', text).strip('_')


def write(out, name, view):
    d = out / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    return name


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
    for k in ('lift_m', 'tilt_deg', 'shift_m', 'beam_travel_m'):
        if isinstance(m.get(k), (int, float)):
            scalars[f'gate/{k}'] = m[k]
    view = {'schema': SCHEMA, 'derived_view_only': True,
            'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': ('one stage-probe case (stage probe, not E2E success). Staged from GT/teacher '
                                     'or an E2E checkpoint; controller inputs own RGB/static map/own commands/prior.'),
            'offline_scalars': scalars, 'success': bool(row['passed']), 'success_definition': DEFINITION,
            'model_calls': 0, 'commands': commands,
            'family': 'pair_stage_probe', 'policy': 'v5h', 'case': row['cell'],
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
    name = f"{SHORT[row['stage']]}-{SHORT[row['source']]}-{slug(row['cell'].replace('v6-', ''))}-s{row['seed']}"
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
        for stage, st in s['stages'].items():
            for source, bs in st['by_source'].items():
                view = {'schema': SCHEMA, 'derived_view_only': True,
                        'offline_source': {'path': str(summary), 'sha256': sha(summary)},
                        'offline_scalar_scope': f'aggregate of {bs["cases"]} stage-probe cases ({stage}, {source}); '
                                                'stage probe, not E2E success',
                        'offline_scalars': {'offline/cases': bs['cases'], 'offline/passed': bs['passed'],
                                            'offline/pass_rate': bs['passed'] / bs['cases']},
                        'success': bs['passed'] == bs['cases'], 'success_definition': 'all cases of this group passed; ' + DEFINITION,
                        'model_calls': 0, 'family': 'pair_stage_probe_aggregate', 'policy': 'v5h',
                        'case': 'all', 'condition': f'{stage}/{source}', 'outcome': json.dumps(st['failures']),
                        'source_sha': manifest['source']['source_sha'], 'run_id': raw.name,
                        'scope': 'stage_probe_not_e2e', 'texts': {'evaluation/summary': st},
                        'hparam_metrics': ['offline/pass_rate', 'offline/cases']}
                names.append(write(a.output, f'ALL-{SHORT[stage]}-{SHORT[source]}-{manifest["source"]["source_sha"][:8]}', view))
    index = {'views': names, 'raw': [str(r) for r in a.raw],
             'raw_summary_sha256': {str(r): sha(r / 'summary.json') for r in a.raw}}
    (a.output / 'index.json').write_text(json.dumps(index, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'output': str(a.output)}))


if __name__ == '__main__':
    main()
