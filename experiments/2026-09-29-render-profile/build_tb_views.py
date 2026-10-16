#!/usr/bin/env python3
"""Render-profile A/B raw -> offline-audit derived views for TensorBoard (read-only on the raw).

Reuses scripts/build_pair_stage_probe_views.case_view (one view per case) and prefixes the run name with the
run label (S1, N1, ...) so both arms of the same case stay separate; the render profile goes into `condition`.
Adds the frame-gate / detector numbers of experiments/2026-09-29-render-profile/analysis-stage1.json (offline,
from saved frames) and the /usr/bin/time -l CPU seconds of the probe invocation. Stage probe verdicts, NOT E2E success.

  build_tb_views.py --raw-root <outputs/render-profile-ab-20260929> --output <new dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import build_pair_stage_probe_views as B          # noqa: E402
from scripts.analyze_render_profile_ab import parse_time_l      # noqa: E402

# label -> (profile, raw dir name); stage 0 / smoke use the first entry of their single case
RUNS = {}
for arm, prof in (('shadows', 'shadows_v1'), ('noshadow', 'noshadow_v1')):
    for sub in ('align-grasp', 'carry-L0', 'setdown-Lend'):
        RUNS[f'ST1-{"SH" if arm == "shadows" else "NS"}-{sub}'] = (prof, f'st1-{arm}-{sub}')
for lab, prof in (('S1', 'shadows_v1'), ('N1', 'noshadow_v1'), ('N2', 'noshadow_v1'), ('S2', 'shadows_v1'),
                  ('N3', 'noshadow_v1'), ('S3', 'shadows_v1')):
    for sub in ('align-grasp', 'carry-L0', 'setdown-Lend'):
        if (lab in ('N3', 'S3') and sub == 'setdown-Lend'):
            continue
        RUNS[f'T2-{lab}-{sub}'] = (prof, f'st2-{lab}-{sub}')
RUNS['S0-none'] = ('none', 's0e-none')
RUNS['S0-shadows_v1'] = ('shadows_v1', 's0e-shadows')
RUNS['S0-noshadow_v1'] = ('noshadow_v1', 'smoke-noshadow-e')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--analysis', type=Path, default=Path(__file__).with_name('analysis-stage1.json'))
    a = p.parse_args(argv)
    analysis = json.loads(a.analysis.read_text()) if a.analysis.is_file() else {'runs': {}}
    frame_stats = {}                                   # (arm run dir name) -> case_id -> per-robot frame stats
    for name, run in (analysis.get('runs') or {}).items():
        frame_stats[Path(run['dir']).name] = {cid: c.get('frames') for cid, c in run['cases'].items()}
    a.output.mkdir(parents=True, exist_ok=False)
    names = []
    for label, (profile, dirname) in RUNS.items():
        raw = a.raw_root / dirname
        manifest = json.loads((raw / 'manifest.json').read_text())
        rows = [json.loads(line) for line in (raw / 'cases.jsonl').read_text().splitlines() if line]
        time_l = parse_time_l((a.raw_root / f'{dirname}.time').read_text()) if (a.raw_root / f'{dirname}.time').is_file() else {}
        for row in rows:
            name, view = B.case_view(raw, row, manifest)
            view['condition'] += f' {profile}'
            view['limits'] = ('dev; weld OFF; render-profile A/B ' + profile + '; frame stats are offline (saved frames, '
                              'analysis-stage1.json); seeds change only the PF RNG; one CPU-seconds value per probe invocation')
            sc = view['offline_scalars']
            if time_l:
                sc['offline/invocation_cpu_s'] = round(time_l['cpu_s'], 2)
                sc['offline/invocation_real_s'] = round(time_l['real_s'], 2)
            for rid, st in ((frame_stats.get(dirname) or {}).get(row['case_id']) or {}).items():
                if st and st.get('frames'):
                    sc[f'gate/frame_gate_pass_rate/{rid}'] = st['gate_pass'] / st['frames']
                    sc[f'gate/mean_v/{rid}'] = st['mean_v']
                    sc[f'gate/beam_visible_rate/{rid}'] = st['beam_visible'] / st['frames']
            view['hparam_metrics'] = ['offline/stage_pass'] + [k for k in sc if k.startswith('gate/frame_gate_pass_rate')]
            view['run_id'] = f'{label}:{row["case_id"]}'
            names.append(B.write(a.output, f'{label}--{name}', view))
    index = {'views': names, 'raw_root': str(a.raw_root), 'runs': {k: v[1] for k, v in RUNS.items()}}
    (a.output / 'index.json').write_text(json.dumps(index, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'output': str(a.output)}))


if __name__ == '__main__':
    main()
