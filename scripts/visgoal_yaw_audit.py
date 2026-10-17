#!/usr/bin/env python3
"""Audit own-command yaw against the eval-only ground-truth yaw.

The runner predicts the robot's per-tick motion from its own issued command
(``command_delta`` -> ``CommandPrior``).  When the exact issued signature
matches the calibrated turn pulse the prior returns the calibrated delta;
otherwise it falls back to the analytic wheel model.  That model can
over-estimate yaw, so this audit compares both predictions with the recorded
eval-only yaw, grouped by exact issued signature.

Ground truth (eval-only poses) is read only for this audit; it is never a
controller input.

Usage:
  python3 scripts/visgoal_yaw_audit.py <run_dir> [<run_dir> ...] \
      --calibration <own-command-calibration-r2.json> --output <audit.json>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

DT = 0.1
GAIN = .0325 * 150 * 2 * math.pi / 60
WHEEL_RADIUS_M = .1255


def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))


def analytic_dyaw(command):
    a, b, c, d = [w * min(DT, t) for w, t in zip(command['wheels'],
                                                 command['duration_s'])]
    return GAIN * (-a + b - c + d) / (4 * WHEEL_RADIUS_M)


def audit_episode(ep_dir: Path):
    cmds = json.loads((ep_dir / 'commands.json').read_text())
    rows = [json.loads(line) for line in
            (ep_dir / 'trace.jsonl').read_text().splitlines() if line.strip()]
    ev = json.loads((ep_dir / 'eval-only.json').read_text())
    n = min(len(cmds), len(rows), len(ev['frames']))
    yaws = [f['pose'][2] for f in ev['frames']]
    groups = {}
    for i in range(1, n):
        cmd = cmds[i - 1]
        key = (tuple(round(x, 3) for x in cmd['wheels']),
               tuple(round(x, 4) for x in cmd['duration_s']),
               rows[i].get('command_motion_source'))
        g = groups.setdefault(key, dict(n=0, gt=0.0, prior=0.0, analytic=0.0))
        g['n'] += 1
        g['gt'] += wrap(yaws[i] - yaws[i - 1])
        g['prior'] += rows[i]['command_delta'][2]
        g['analytic'] += analytic_dyaw(cmd)
    out = []
    for (wheels, duration, source), g in sorted(groups.items(),
                                                key=lambda x: -x[1]['n']):
        n_g = g['n']
        row = dict(wheels=list(wheels), duration_s=list(duration), source=source,
                   n=n_g,
                   gt_sum=round(g['gt'], 6), prior_sum=round(g['prior'], 6),
                   analytic_sum=round(g['analytic'], 6),
                   gt_per_pulse=round(g['gt'] / n_g, 6),
                   prior_per_pulse=round(g['prior'] / n_g, 6),
                   analytic_per_pulse=round(g['analytic'] / n_g, 6))
        row['prior_ratio'] = (round(g['prior'] / g['gt'], 4)
                              if abs(g['gt']) > 1e-9 else None)
        row['analytic_ratio'] = (round(g['analytic'] / g['gt'], 4)
                                 if abs(g['gt']) > 1e-9 else None)
        out.append(row)
    return dict(ticks=n, signatures=out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dirs', nargs='+')
    ap.add_argument('--calibration', required=True)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    cal = json.loads(Path(a.calibration).read_text())
    runs = {}
    for run in a.run_dirs:
        run = Path(run)
        eps = {}
        for d in sorted((run / 'episodes').glob('e*')):
            if (d / 'episode.json').exists():
                eps[d.name] = audit_episode(d)
        runs[str(run)] = dict(
            summary_status=(json.loads((run / 'summary.json').read_text())
                            .get('status') if (run / 'summary.json').exists() else None),
            episodes=eps)
    out = dict(
        schema='ugrp.visgoal.yaw_audit.v1',
        calibration=dict(path=str(a.calibration),
                         wheels=cal.get('wheels'),
                         duration_s=cal.get('duration_s'),
                         interval_s=cal.get('interval_s'),
                         mean_delta=cal.get('mean_delta'),
                         qualified_servo=cal.get('qualified_servo')),
        runs=runs,
        scope='eval-only yaw used for the audit only; no controller input; '
              'signed per-signature sums over consecutive frames',
    )
    Path(a.output).write_text(json.dumps(out, indent=1) + '\n')
    for run, d in runs.items():
        print(run, d['summary_status'])
        for ep, e in d['episodes'].items():
            for s in e['signatures']:
                if s['n'] >= 3:
                    print(f"  {ep} n={s['n']:4d} src={s['source']:28s} "
                          f"gt={s['gt_per_pulse']:.5f} prior={s['prior_per_pulse']:.5f} "
                          f"ratio={s['prior_ratio']} analytic={s['analytic_per_pulse']:.5f} "
                          f"aratio={s['analytic_ratio']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
