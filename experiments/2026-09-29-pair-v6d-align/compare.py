#!/usr/bin/env python3
"""Baseline (b-v6c) vs candidate (b-v6d) per-case table for a stage-probe grid, as Markdown (read-only).

  compare.py --baseline <dir with cases.jsonl> --candidate <dir with cases.jsonl> [--baseline-policy b-v6c --policy b-v6d]

Columns: pass / failure category, GT final errors (grip x mm, grip y mm, yaw mrad; worst |value| over r1, r2),
stage SIM seconds and look-command counts (r1+r2). GT errors are the eval-only judgement values of the probe, never
controller inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def rows(path):
    return {json.loads(l)['case_id']: json.loads(l) for l in Path(path, 'cases.jsonl').read_text().splitlines() if l.strip()}


def worst(row, key):
    vals = [abs((row.get('metrics') or {}).get(r, {}).get(key)) for r in ('r1', 'r2')
            if isinstance((row.get('metrics') or {}).get(r, {}).get(key), (int, float))]
    return max(vals) if vals else None


def cell(row):
    if row is None:
        return 'missing'
    verdict = 'PASS' if row['passed'] else row['category']
    parts = [verdict]
    for key, scale, unit in (('grip_x_err_m', 1000, 'mm'), ('grip_y_err_m', 1000, 'mm'), ('yaw_err_rad', 1000, 'mrad')):
        v = worst(row, key)
        parts.append('-' if v is None else f'{v * scale:.0f}')
    sim = row.get('stage_sim_s')
    parts.append('-' if sim is None else f'{sim:.1f}')
    looks = sum((row.get('look_commands') or {}).values())
    parts.append(str(looks))
    return ' | '.join(parts)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--baseline-policy', default='b-v6c')
    p.add_argument('--policy', default='b-v6d')
    a = p.parse_args(argv)
    base = {k: v for k, v in rows(a.baseline).items() if f'@{a.baseline_policy}:' in k}  # a dir may also hold other policies
    cand = rows(a.candidate)
    head = 'verdict | x mm | y mm | yaw mrad | SIM s | look cmds'
    print(f'| case | {a.baseline_policy}: {head} | {a.policy}: {head} |')
    print('|---|' + '---|' * 12)
    for cid in sorted(base):
        other = cid.replace(f'@{a.baseline_policy}:', f'@{a.policy}:', 1)
        short = cid.split(':', 1)[1] if ':' in cid else cid
        print(f'| {short} | {cell(base[cid])} | {cell(cand.get(other))} |')
    bp = sum(1 for r in base.values() if r['passed'])
    cp = sum(1 for r in cand.values() if r['passed'])
    print(f'\n{a.baseline_policy}: {bp}/{len(base)}, {a.policy}: {cp}/{len(cand)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
