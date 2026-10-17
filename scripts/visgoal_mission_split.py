#!/usr/bin/env python3
"""Mission-oriented split analysis for a visgoal run: west (behind the wall) vs east.

The mission question is whether a robot that starts **west of the divider wall**
finds the blue destination zone B on the far side.  West starts e00-e07 must
cross the wall gap before any destination search can succeed; east starts
e08-e15 already start on the destination side.  This is a read-only analysis:
truth (eval-only pose cells) is used only to measure where the robot was
relative to zone B, never in a control path, and the run's own verdicts are
recomputed from the raw trace exactly as ``visgoal_recount.py`` does.

Funnel:
  west: starts -> crossed (a gap_cross/gap_forward stage tick) -> colour seen
        after the crossing -> found -> arrived declared -> arrived GT-inside
  east: starts -> colour seen -> found -> arrived declared -> arrived GT-inside

The post-crossing table reports where the west episodes spent time and how
close their trajectory came to zone B (bands are eval-only distances):
whether the search actually visited the south-east area that contains the zone.

Usage:
  python3 scripts/visgoal_mission_split.py <run_dir> [--output analysis-mission.json]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

X0, X1, Y0, Y1 = 4.3, 4.9, -2.8, -1.4
CROSS_STAGES = ('gap_cross', 'gap_forward')
WEST_EPISODES = tuple(range(8))
RANGE_BANDS = ((0.0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0))


def load_json(path):
    return json.loads(Path(path).read_text())


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def zone_range(x, y):
    """Distance from (x,y) to the zone-B rectangle (0 when inside)."""
    dx = max(X0 - x, 0.0, x - X1)
    dy = max(Y0 - y, 0.0, y - Y1)
    return math.hypot(dx, dy)


def stage_runs(trace):
    runs = []
    stage, t0 = None, None
    for r in trace:
        if r['stage'] != stage:
            if stage is not None:
                runs.append(dict(stage=stage, t0=t0, t1=r['t'],
                                 dur=round(r['t'] - t0, 1)))
            stage, t0 = r['stage'], r['t']
    if trace:
        runs.append(dict(stage=stage, t0=t0, t1=trace[-1]['t'],
                         dur=round(trace[-1]['t'] - t0, 1)))
    return runs


def episode_row(ep_dir: Path):
    ep = load_json(ep_dir / 'episode.json')
    trace = load_jsonl(ep_dir / 'trace.jsonl')
    frames = {f['frame_id']: f for f in load_json(ep_dir / 'eval-only.json')['frames']}
    idx = int(ep['episode'])
    west = idx in WEST_EPISODES
    runs = stage_runs(trace)
    cross_rows = [r for r in trace if r['stage'] in CROSS_STAGES]
    cross_t = cross_rows[0]['t'] if cross_rows else None
    crossed = cross_t is not None
    found_ticks = [r['t'] for r in trace if (r.get('action') or {}).get('found')]
    colour_ticks = [r['t'] for r in trace if (r.get('action') or {}).get('colour_seen')]
    arrived = [r for r in trace if (r.get('action') or {}).get('arrived')]
    declared_t = arrived[0]['t'] if arrived else None
    gt = (bool(frames[arrived[0]['frame_id']]['inside_zone_B'])
          if arrived and arrived[0]['frame_id'] in frames else None)
    entered_any = any(f.get('inside_zone_B') for f in frames.values())
    final_pose = ep.get('final_pose_eval_only')
    final_range = (zone_range(final_pose[0], final_pose[1])
                   if final_pose else None)
    post = [r for r in trace if cross_t is not None and r['t'] >= cross_t]
    bands = {f'<= {hi}': 0 for _, hi in RANGE_BANDS}
    min_range = math.inf
    inside_ticks = 0
    for r in post:
        f = frames.get(r['frame_id'])
        if f is None:
            continue
        x, y = f['pose'][0], f['pose'][1]
        rng = zone_range(x, y)
        min_range = min(min_range, rng)
        for _, hi in RANGE_BANDS:
            if rng <= hi:
                bands[f'<= {hi}'] += 1
        if f.get('inside_zone_B'):
            inside_ticks += 1
    post_pose = [frames[r['frame_id']]['pose'] for r in post
                 if r['frame_id'] in frames and r['stage'] != 'orient']
    bbox = (dict(x=[round(min(p[0] for p in post_pose), 2),
                    round(max(p[0] for p in post_pose), 2)],
                 y=[round(min(p[1] for p in post_pose), 2),
                    round(max(p[1] for p in post_pose), 2)])
            if post_pose else None)
    return dict(
        episode=idx, side='west' if west else 'east', status=ep.get('status'),
        sim_s=ep.get('sim_s'), crossed=crossed, cross_t=cross_t,
        colour_after_cross=(bool([t for t in colour_ticks
                                  if cross_t is not None and t >= cross_t])
                            if west else bool(colour_ticks)),
        colour_any=bool(colour_ticks),
        found=bool(found_ticks), found_t_first=found_ticks[0] if found_ticks else None,
        declared=bool(arrived), declared_t=declared_t, gt=gt,
        entered_zone_any=inside_ticks > 0 or entered_any,
        start_visibility_pixels=ep.get('start_visibility_pixels'),
        final_pose_eval_only=final_pose, final_zone_range_m=(
            round(final_range, 3) if final_range is not None else None),
        post_cross_ticks=len(post),
        post_cross_min_zone_range_m=(round(min_range, 3)
                                     if math.isfinite(min_range) else None),
        post_cross_inside_ticks=inside_ticks,
        post_cross_band_ticks=bands,
        post_cross_bbox_eval_only=bbox,
        stage_runs=runs,
        final_stage=runs[-1]['stage'] if runs else None,
    )


def side_funnel(rows, west):
    remaining = list(rows)
    stages = []
    gates = [('starts', lambda r: True)]
    if west:
        gates.append(('crossed_gap', lambda r: r['crossed']))
        gates.append(('colour_seen_after_cross',
                      lambda r: r['crossed'] and r['colour_after_cross']))
    else:
        gates.append(('colour_seen', lambda r: r['colour_any']))
    gates += [('found_metric_or_arrived', lambda r: r['found']),
              ('arrived_declared', lambda r: r['declared']),
              ('arrived_gt', lambda r: r['gt'] is True)]
    for name, cond in gates:
        passed = [r for r in remaining if cond(r)]
        stages.append(dict(stage=name, input_n=len(remaining),
                           cumulative_pass_n=len(passed),
                           rejected_n=len(remaining) - len(passed)))
        remaining = passed
    return stages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('--output', default=None)
    a = ap.parse_args()
    run = Path(a.run_dir)
    rows = [episode_row(d) for d in sorted((run / 'episodes').glob('e[0-9]*'))
            if (d / 'episode.json').exists()]
    west = [r for r in rows if r['side'] == 'west']
    east = [r for r in rows if r['side'] == 'east']
    out = dict(
        schema='ugrp.visgoal.mission_split.v1', run=str(run),
        zone_B=[X0, X1, Y0, Y1],
        split=dict(west=dict(episodes=[r['episode'] for r in west],
                             funnel=side_funnel(west, True),
                             n=len(west)),
                   east=dict(episodes=[r['episode'] for r in east],
                             funnel=side_funnel(east, False),
                             n=len(east))),
        scope=('read-only; the authored setup index defines the side '
               '(e00-e07 west of the divider, e08-e15 east). Truth is read '
               'only in eval-only pose cells (zone distance/inside) and in '
               'the arrival verdict; cargo transport is not part of this run.'),
        episodes=rows)
    text = json.dumps(out, indent=1, ensure_ascii=False) + '\n'
    if a.output:
        Path(a.output).write_text(text)
    print('WEST funnel:', json.dumps(out['split']['west']['funnel']))
    print('EAST funnel:', json.dumps(out['split']['east']['funnel']))
    for r in rows:
        print(json.dumps(dict(ep=r['episode'], side=r['side'], st=r['status'],
                              crossed=r['crossed'], cross_t=r['cross_t'],
                              colour_after=r['colour_after_cross'],
                              found=r['found'], decl=r['declared'], gt=r['gt'],
                              min_zone_range=r['post_cross_min_zone_range_m'],
                              final_zone_range=r['final_zone_range_m'],
                              post_ticks=r['post_cross_ticks'],
                              inside_ticks=r['post_cross_inside_ticks'],
                              final_stage=r['final_stage'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
