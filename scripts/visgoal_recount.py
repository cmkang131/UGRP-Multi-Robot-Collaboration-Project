#!/usr/bin/env python3
"""Independent recount of a visgoal run from its raw per-episode files.

The aggregate ``summary.json`` is written by the runner itself.  This script
recomputes the funnel from the raw episode records instead of trusting those
aggregates:

* found            -- first trace tick whose skill action has ``found`` (a
                      metric <=1.2 m floor-paint landmark was formed); the
                      memory-observation ledger is cross-checked separately.
* colour seen      -- any trace tick whose skill action has ``colour_seen``
                      (a zone-sized destination-colour component was seen).
* arrived declared -- first trace tick whose skill action has ``arrived``.
* GT arrival       -- ``inside_zone_B`` of the eval-only frame at that tick.
                      This evaluation cell is the only place truth is read.
* entered zone     -- any eval-only frame inside zone B (also for failures).
* cap_end          -- episode status, reported separately, never as a failure.

Usage:
  python3 scripts/visgoal_recount.py <run_dir> --output <recount.json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OBS = 'destination-paint-B'
CONTROL_FIELDS = ('static_map_control', 'spawn_control', 'truth_control',
                  'top_camera_frames', 'held_world_reads')


def load_json(path):
    return json.loads(Path(path).read_text())


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def recount_episode(ep_dir: Path, hz: float = 10.0):
    ep = load_json(ep_dir / 'episode.json')
    trace = load_jsonl(ep_dir / 'trace.jsonl')
    ev = load_json(ep_dir / 'eval-only.json')
    frames = {f['frame_id']: f for f in ev['frames']}
    events = load_json(ep_dir / 'events.json') if (ep_dir / 'events.json').exists() else []

    found_ticks = [r['t'] for r in trace if (r.get('action') or {}).get('found')]
    colour_ticks = [r['t'] for r in trace if (r.get('action') or {}).get('colour_seen')]
    arrived_rows = [r for r in trace if (r.get('action') or {}).get('arrived')]
    declared_tick = arrived_rows[0]['t'] if arrived_rows else None
    declared_frame = frames.get(arrived_rows[0]['frame_id']) if arrived_rows else None
    gt_inside_declared = (bool(declared_frame['inside_zone_B'])
                          if declared_frame is not None else None)
    entered_any = any(f.get('inside_zone_B') for f in ev['frames'])
    mem_events = [e for r in trace for e in (r.get('memory_events') or [])
                  if e.get('observation') == OBS]
    mem_ids = {e.get('memory_id') for e in mem_events}

    status = ep.get('status')
    cap_end = status == 'cap_end'
    final_stage = trace[-1].get('stage') if trace else None
    last_event = events[-1] if isinstance(events, list) and events else None
    frames_dir = ep_dir / 'frames'
    frame_files = len(list(frames_dir.glob('*.jpg'))) if frames_dir.is_dir() else 0

    # Cross-checks against the runner-written per-episode record.
    checks = {
        'found_matches_memory_observation': bool(found_ticks) == bool(mem_events),
        'found_field_matches_trace': bool(ep.get('found')) == bool(found_ticks),
        'colour_field_matches_trace': bool(ep.get('colour_seen')) == bool(colour_ticks),
        'declared_field_matches_trace': bool(ep.get('arrived_declared')) == bool(arrived_rows),
        'gt_verdict_matches_eval_frame': (ep.get('arrival_verdict_gt_inside_zone_B')
                                          == gt_inside_declared),
        'entered_any_matches_eval': bool(ep.get('entered_zone_gt_any')) == bool(entered_any),
        'trace_ticks_match_camera_frames': len(trace) == int(ep.get('camera_frames', -1)),
        'control_fields_zero': all(int(ep.get(f, -1)) == 0 for f in CONTROL_FIELDS),
        'noslip_zero': int(ep.get('noslip_iterations', -1)) == 0,
        'eval_frames_match_camera_frames': len(ev['frames']) == int(ep.get('camera_frames', -1)),
    }

    return dict(
        episode=ep.get('episode'),
        status=status,
        cap_end=cap_end,
        found=bool(found_ticks),
        found_t_first=found_ticks[0] if found_ticks else None,
        memory_observation_n=len(mem_events),
        memory_landmarks=len(mem_ids),
        colour_seen=bool(colour_ticks),
        arrived_declared=bool(arrived_rows),
        declared_t=declared_tick,
        arrival_verdict_gt_inside_zone_B=gt_inside_declared,
        entered_zone_gt_any=bool(entered_any),
        start_visibility_pixels=ep.get('start_visibility_pixels'),
        sim_s=ep.get('sim_s'),
        wall_s=ep.get('wall_s'),
        rotation_cmd_rad=ep.get('rotation_cmd_rad'),
        final_pose_eval_only=ep.get('final_pose_eval_only'),
        final_stage=final_stage,
        last_event=last_event,
        terminal_ring_frames=(len(ep.get('terminal_ring', {}).get('indices', []))
                              if isinstance(ep.get('terminal_ring'), dict) else 0),
        frame_files=frame_files,
        checks=checks,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    summary_path = run / 'summary.json'
    summary = load_json(summary_path) if summary_path.exists() else {}
    all_dirs = sorted((run / 'episodes').glob('e*'))
    partial = [d.name for d in all_dirs if not (d / 'episode.json').exists()]
    ep_dirs = [d for d in all_dirs if (d / 'episode.json').exists()]
    episodes = [recount_episode(d) for d in ep_dirs]

    n = len(episodes)
    found_n = sum(1 for e in episodes if e['found'])
    colour_n = sum(1 for e in episodes if e['colour_seen'])
    declared_n = sum(1 for e in episodes if e['arrived_declared'])
    gt_n = sum(1 for e in episodes if e['arrival_verdict_gt_inside_zone_B'] is True)
    entered_n = sum(1 for e in episodes if e['entered_zone_gt_any'])
    cap_n = sum(1 for e in episodes if e['cap_end'])
    invisible_n = sum(1 for e in episodes if not (e['start_visibility_pixels'] or 0))
    invisible_found_n = sum(1 for e in episodes
                            if not (e['start_visibility_pixels'] or 0) and e['found'])
    invisible_gt_n = sum(1 for e in episodes
                         if not (e['start_visibility_pixels'] or 0)
                         and e['arrival_verdict_gt_inside_zone_B'] is True)
    status_counts = {}
    for e in episodes:
        status_counts[e['status']] = status_counts.get(e['status'], 0) + 1

    mismatches = []
    for e in episodes:
        for name, ok in e['checks'].items():
            if not ok:
                mismatches.append(dict(episode=e['episode'], check=name))
    aggregate_checks = {
        'n_matches_summary': n == summary.get('n', n),
        'found_matches_summary': found_n == summary.get('found_n', found_n),
        'declared_matches_summary': declared_n == summary.get('arrived_declared_n', declared_n),
        'gt_matches_summary': gt_n == summary.get('arrived_gt_n', gt_n),
        'source_sha_matches_summary': len({json.loads((d / 'episode.json').read_text())['source_sha']
                                           for d in ep_dirs}) <= 1,
    }

    failures = [e for e in episodes
                if not (e['status'] == 'ARRIVED_DECLARED'
                        and e['arrival_verdict_gt_inside_zone_B'] is True)]

    out = dict(
        schema='ugrp.visgoal.recount.v1',
        run=str(run),
        summary_status=summary.get('status'),
        source_sha=summary.get('source_sha'),
        n=n,
        found_n=found_n,
        colour_seen_n=colour_n,
        arrived_declared_n=declared_n,
        arrived_gt_n=gt_n,
        entered_zone_gt_any_n=entered_n,
        cap_end_n=cap_n,
        initially_invisible_n=invisible_n,
        initially_invisible_found_n=invisible_found_n,
        initially_invisible_gt_n=invisible_gt_n,
        status_counts=status_counts,
        partial_episode_dirs=partial,
        failures=failures,
        aggregate_checks=aggregate_checks,
        mismatches=mismatches,
        episodes=episodes,
        scope='raw recount of trace/eval-only; no physics rerun; truth read only '
              'in the arrival verdict cell',
    )
    Path(a.output).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: out[k] for k in ('n', 'found_n', 'arrived_declared_n',
                                          'arrived_gt_n', 'cap_end_n',
                                          'initially_invisible_n', 'mismatches',
                                          'aggregate_checks')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
