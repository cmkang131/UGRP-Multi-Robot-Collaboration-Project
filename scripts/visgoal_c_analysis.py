#!/usr/bin/env python3
"""Read-only candidate-C analysis: lawnmower schedule, long stroke, arrival aim.

Truth is used only in analysis cells (eval-only poses/zone), never in control.

Usage:
  python3 scripts/visgoal_c_analysis.py <run_dir> --output <analysis.json>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

X0, X1, Y0, Y1 = 4.3, 4.9, -2.8, -1.4
EXPECTED_SCHEDULE = (20, 344, 60, 300, 60)


def margin(x, y):
    return min(x - X0, X1 - x, y - Y0, Y1 - y)


def load_episode(ep_dir):
    ep = json.loads((ep_dir / 'episode.json').read_text())
    trace = [json.loads(line) for line in (ep_dir / 'trace.jsonl').read_text().splitlines()
             if line.strip()]
    frames = json.loads((ep_dir / 'eval-only.json').read_text())['frames']
    return ep, trace, frames


def forward_runs(trace, frames):
    """Contiguous leg_forward ticks with a forward command, with GT displacement."""
    pose = {f['frame_id']: f['pose'] for f in frames}
    rows = [r for r in trace if r['stage'] == 'leg_forward']
    runs, cur = [], []
    for r in rows:
        if (r.get('action') or {}).get('forward', 0) > 0:
            cur.append(r)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    out = []
    for run in runs:
        p0, p1 = pose[run[0]['frame_id']], pose[run[-1]['frame_id']]
        d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        out.append(dict(ticks=len(run), dist_m=round(d, 4),
                        m_per_tick=round(d / len(run), 5),
                        t0=run[0]['t'], t1=run[-1]['t']))
    return out


def leg_turns(trace, events=None):
    """Distinct search_leg_turn events from events.json (or the trace subset)."""
    src = events if events is not None else [
        e for r in trace for e in ((r.get('action') or {}).get('events') or [])]
    seen, out = set(), []
    for e in src:
        if e.get('reason') != 'search_leg_turn':
            continue
        key = (e.get('t'), e.get('leg_reason'), e.get('leg'), e.get('leg_len_ticks'))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(t=e.get('t'), leg=e.get('leg'),
                        leg_reason=e.get('leg_reason'),
                        leg_len_ticks=e.get('leg_len_ticks'),
                        turn_sign=e.get('turn_sign')))
    return out


def declared_row(trace, frames):
    pose = {f['frame_id']: f for f in frames}
    rows = [r for r in trace if (r.get('action') or {}).get('arrived')]
    if not rows:
        return None
    r = rows[0]
    f = pose.get(r['frame_id'])
    ev = [e for e in ((r.get('action') or {}).get('events') or [])
          if e.get('reason', '').startswith('arrival')]
    mem = [m for m in (r.get('memory') or []) if m.get('id') == 'm1']
    return dict(t=r.get('t'), frame_id=r.get('frame_id'),
                base_pose=[round(v, 4) for v in f['pose']] if f else None,
                base_margin_m=round(margin(f['pose'][0], f['pose'][1]), 4) if f else None,
                inside_zone_B=bool(f.get('inside_zone_B')) if f else None,
                memory_range_m=float(math.hypot(*mem[0]['relative_xy_m']))
                if mem else None,
                memory_margin_m=(round(margin(
                    f['pose'][0] + mem[0]['relative_xy_m'][0] * math.cos(f['pose'][2])
                    - mem[0]['relative_xy_m'][1] * math.sin(f['pose'][2]),
                    f['pose'][1] + mem[0]['relative_xy_m'][0] * math.sin(f['pose'][2])
                    + mem[0]['relative_xy_m'][1] * math.cos(f['pose'][2])), 4)
                    if mem and f else None),
                events=ev)


def episode_row(ep_dir):
    ep, trace, frames = load_episode(ep_dir)
    runs = forward_runs(trace, frames)
    long = max(runs, key=lambda r: r['ticks']) if runs else None
    events = (json.loads((ep_dir / 'events.json').read_text())
              if (ep_dir / 'events.json').is_file() else None)
    turns = leg_turns(trace, events)
    decl = declared_row(trace, frames)
    return dict(
        episode=ep.get('episode'), status=ep.get('status'),
        found=bool(ep.get('found')), colour_seen=bool(ep.get('colour_seen')),
        arrived_declared=bool(ep.get('arrived_declared')),
        gt_inside=ep.get('arrival_verdict_gt_inside_zone_B'),
        cap_end=ep.get('status') == 'cap_end',
        max_x=round(max(f['pose'][0] for f in frames), 3),
        min_zone_range_m=round(min(math.hypot(
            min(max(f['pose'][0], X0), X1) - f['pose'][0],
            min(max(f['pose'][1], Y0), Y1) - f['pose'][1]) for f in frames), 3),
        final_pose_eval_only=ep.get('final_pose_eval_only'),
        forward_runs_n=len(runs),
        longest_forward_run=long,
        leg_turns_n=len(turns),
        leg_turn_lengths=[t['leg_len_ticks'] for t in turns],
        schedule_matches_expected=(EXPECTED_SCHEDULE in
                                   tuple(t['leg_len_ticks'] for t in turns)),
        declared=decl,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    rows = [episode_row(d) for d in sorted((run / 'episodes').glob('e[0-9]*'))
            if (d / 'episode.json').exists()]
    n = len(rows)
    out = dict(
        schema='ugrp.visgoal.c_analysis.v1', run=str(run),
        scope='read-only; truth read only in eval-only analysis cells',
        expected_schedule_ticks=list(EXPECTED_SCHEDULE),
        n=n,
        found_n=sum(r['found'] for r in rows),
        colour_seen_n=sum(r['colour_seen'] for r in rows),
        declared_n=sum(r['arrived_declared'] for r in rows),
        gt_inside_n=sum(r['gt_inside'] is True for r in rows),
        cap_end_n=sum(r['cap_end'] for r in rows),
        false_arrival_n=sum(r['arrived_declared'] and r['gt_inside'] is not True
                            for r in rows),
        schedule_matched_n=sum(r['schedule_matches_expected'] for r in rows),
        reached_x_gt_1p2_n=sum(r['max_x'] > 1.2 for r in rows),
        episodes=rows,
    )
    Path(a.output).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: out[k] for k in
                      ('n', 'found_n', 'colour_seen_n', 'declared_n', 'gt_inside_n',
                       'cap_end_n', 'false_arrival_n', 'schedule_matched_n',
                       'reached_x_gt_1p2_n')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
