"""Markdown tables from ``segment_score.py`` runs named ``<tag>-<config>-sag<off|on>-<gate>``. Refs #216.

Usage: ``python segment_table.py --dir <outputs>/seg --tags main s912 s913 --configs A C D``
Offline, reads the ``summary.json`` files only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pct(x):
    return '-' if x is None else f'{100*x:.0f}%'


def load(d: Path, tag, cfg, sag, gate):
    p = d/f'{tag}-{cfg}-sag{sag}-{gate}'/'summary.json'
    return json.loads(p.read_text()) if p.exists() else None


def row(label, s):
    seg = s['segments_visible_frames']
    ax = seg['axis_error_deg_median_p90']
    pos = seg['position_error_m_median_p90']
    return (f"| {label} | {seg['segments']} | {pct(seg['correct_share_tol_0.10'])} / {pct(seg['correct_share'])} / "
            f"{pct(seg['correct_share_tol_0.25'])} | {'-' if pos is None else f'{pos[0]:.3f}'} | {'-' if ax is None else f'{ax[0]:.1f}'} | "
            f"{pct(s['gt_faces']['found_share_of_all'])} | {pct(s['map_coverage']['covered_share_of_seen_in_any_frame'])} | "
            f"{s['false_on_invisible_frames']['segments']} | {s['records']} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--tags', nargs='+', required=True)
    ap.add_argument('--configs', nargs='+', default=['A', 'C', 'D'])
    ap.add_argument('--gate', default='none')
    a = ap.parse_args()
    d = Path(a.dir)
    head = ('| options | segments | correct at 0.10 / 0.15 / 0.25 m | position error median (m) | axis error median (deg) | '
            'GT faces found | wall cells covered | segments on invisible frames | records |\n|---|---|---|---|---|---|---|---|---|')
    for tag in a.tags:
        print(f'\n{tag} (gate {a.gate})\n\n{head}')
        for cfg in a.configs:
            for sag in ('off', 'on'):
                s = load(d, tag, cfg, sag, a.gate)
                if s:
                    print(row(f'{cfg}, sag {sag}', s))


if __name__ == '__main__':
    main()
