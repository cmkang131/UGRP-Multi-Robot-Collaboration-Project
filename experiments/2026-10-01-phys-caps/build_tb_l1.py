#!/usr/bin/env python3
"""Build derived offline-audit views for the L1 probe cases and export a NEW TensorBoard snapshot.

Reads l1_results.json (from summarize_l1.py) and the raw case files; writes views under outputs/ and a new snapshot.
Never overwrites an existing snapshot (the exporter refuses).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIMARY = Path('/Users/changmin/projects/ugrp')
OUTS = PRIMARY / 'outputs'
WT = HERE.parents[1]
REPORT = json.loads((HERE / 'l1_results.json').read_text())
# usage: build_tb_l1.py [group ...] [--snap NAME --views NAME] ; default = the first snapshot (recheck + probes6, seed 911)
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('groups', nargs='*', default=['recheck', 'probes6'])
ap.add_argument('--snap', default='1001-phys-caps-l1-probes')
ap.add_argument('--views', default='phys-caps-1001-l1-tb-views')
ap.add_argument('--label', default='')
A = ap.parse_args()
REPORT['groups'] = {k: v for k, v in REPORT['groups'].items() if k in A.groups}
VIEWS = OUTS / A.views
SNAP = OUTS / 'tensorboard' / A.snap
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
SRC = REPORT['source_sha']
DEF = ('both L0 and L1 endpoints recorded and each hypot(axial, lateral) <= 100 mm; an exploratory probe gate proxy, '
       'NOT a robot task success and NOT the sealed b-v6h1 confirmatory gate')
VIEWS.mkdir()
paths = []
for gname, g in REPORT['groups'].items():
    for r in g['cases']:
        src = Path(r['case_dir']) / 'result.json'
        sc = {'offline/pass': int(r['gate_L0_L1_le_100mm']), 'offline/legs_recorded': len(r['legs_recorded'])}
        for k in (0, 1):
            if r[f'L{k}_reached']:
                sc[f'offline/l{k}_end_error_mm'] = r[f'L{k}_end_mm']
                sc[f'offline/l{k}_axial_mm'] = r[f'L{k}_axial_mm']
                sc[f'offline/l{k}_lateral_mm'] = r[f'L{k}_lateral_mm']
            sc[f'offline/l{k}_lateral_pred_mm'] = r['pred_lateral_mm'][k]
        if r['commands_identical_to_acceptance_3c4fe30e'] is not None:
            sc['offline/commands_identical_to_3c4fe30e_acceptance'] = int(r['commands_identical_to_acceptance_3c4fe30e'])
        kind = 'blocker-recheck' if gname == 'recheck' else 'lateral-probe'
        name = f"{'B' if gname == 'recheck' else 'P'}{A.label}-{r['cell']}"
        d = VIEWS / name
        d.mkdir()
        view = {'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
                'offline_source': {'path': str(src), 'sha256': sha(src)},
                'offline_scalar_scope': f'one SIM-time chain probe (stop after leg 1) of b-v6h1 at {SRC[:8]}, floor_light_v1, weld OFF, model calls 0; {kind}; '
                                        'lateral_pred is the PR #306 target_ENV_30_prior point model (exploratory)',
                'offline_scalars': sc, 'sim_s': r['sim_s_total'], 'wall_s': r['wall_s'], 'commands': sum(r['command_total'].values()), 'model_calls': 0,
                'success': bool(r['gate_L0_L1_le_100mm']), 'success_definition': DEF,
                'family': 'phys_caps_l1_20261001', 'policy': 'b-v6h1', 'case': r['cell'],
                'condition': f"{kind}, x={r['place_x']} y={r['place_y']} yaw={r['place_yaw_deg']:.2f} {r['prior_id']}, chain-stop-leg 1, seed {r['seed']}{' (seed slip, exploratory)' if gname == 'probes6' else ''}",
                'seed': r['seed'], 'outcome': f"{r['stage_category']}; gate {'met' if r['gate_L0_L1_le_100mm'] else 'not met'}",
                'source_sha': SRC, 'run_id': r['case_id'], 'scope': 'exploratory_probe_not_e2e',
                'hparam_metrics': ['offline/pass', 'offline/l1_end_error_mm', 'offline/l1_lateral_mm', 'offline/l1_lateral_pred_mm'],
                'texts': {'evaluation/summary': {'case_dir': r['case_dir'], 'commands_sha256': r['commands_sha256'],
                                                 'result_sha256': r['result_sha256'], 'group_raw': g['raw'], 'load_at_case': r['loadavg_case'],
                                                 'wall_contact_episodes': r['wall_contact_episodes'], 'outcome_class': r['outcome_class']}}}
        (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=2) + '\n')
        paths.append(d)
args = [sys.executable, 'scripts/export_offline_audit.py']
for d in paths:
    args += ['--source', str(d)]
args += ['--output', str(SNAP)]
subprocess.run(args, cwd=WT, check=True)
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
verified = []
for p in sorted(SNAP.iterdir()):
    if p.is_dir():
        ea = EventAccumulator(str(p))
        ea.Reload()
        verified.append({'run': p.name, 'scalars': {t: ea.Scalars(t)[-1].value for t in ea.Tags()['scalars']}})
out = {'snapshot': str(SNAP), 'collection_sha256': sha(SNAP / 'collection.json'), 'views_dir': str(VIEWS), 'runs': verified}
(HERE / ('tensorboard_verification.json' if A.snap == '1001-phys-caps-l1-probes' else f'tensorboard_verification_{A.snap}.json')).write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
print(len(verified), 'runs verified')
