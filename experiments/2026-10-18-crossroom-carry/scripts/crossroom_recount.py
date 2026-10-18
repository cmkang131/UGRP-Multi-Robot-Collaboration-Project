#!/usr/bin/env python3
"""Independent recount of a cross-room carry Stage A run from its raw files.

Stage A = unloaded west-side start -> divider door (0.50 m) -> zone B arrival.
The aggregate ``summary.json`` written by the runner is not trusted; this
script recomputes the funnel and every self/GT metric from the per-episode raw
records:

* start_valid        -- admission.json accepted (sim spawn-overlap check)
* input_audit_zero   -- the controller-boundary audit reported no forbidden key
                        attempts and every counter is zero (actual counts, not
                        runner-written constants)
* door_crossed       -- eval-only base x moves from < 2.175 to > 2.225 while y
                        is inside the door opening [-0.20, 0.30]
* post_cross_colour  -- first skill ``colour_seen`` after the crossing tick
* post_cross_found   -- first metric <=1.2 m paint landmark after crossing
* arrived_declared   -- the skill's own arrival test came true
* gt_inside          -- eval-only base xy inside zone B at the declared tick

``cap_end`` is a separate termination label, never a rejection reason.  Truth
is read only in eval-only cells and in the verdict/analysis outputs; it never
enters a control path.  Usage:

  python3 scripts/crossroom_recount.py <run_dir> --output <recount.json>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ZONE = (4.30, 4.90, -2.80, -1.40)          # x0, x1, y0, y1 (eval-only)
DOOR_X = 2.20
DOOR_Y = 0.05
OPENING_Y = (-0.20, 0.30)
ROBOT_RADIUS_M = 0.195
CROSS_ENTER_X = 2.175
CROSS_EXIT_X = 2.225
OBS = 'destination-paint-B'


def load_json(path):
    return json.loads(Path(path).read_text())


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def zone_margin(x, y):
    """Signed distance to zone B: positive inside."""
    return min(x - ZONE[0], ZONE[1] - x, y - ZONE[2], ZONE[3] - y)


def zone_range(x, y):
    dx = max(ZONE[0] - x, 0.0, x - ZONE[1])
    dy = max(ZONE[2] - y, 0.0, y - ZONE[3])
    return math.hypot(dx, dy)


def jamb_gap(y):
    """Clearance between the robot disc and each door jamb (min, m)."""
    return min(y + 0.005, 0.105 - y)


def door_crossing(labels):
    """First door crossing from the eval-only per-tick base poses."""
    pose = [(f['t'], f['pose'][0], f['pose'][1]) for f in labels]
    for i, (t, x, y) in enumerate(pose):
        if x <= CROSS_EXIT_X:
            continue
        j = None
        for k in range(i - 1, -1, -1):
            if pose[k][1] < CROSS_ENTER_X:
                j = k
                break
        if j is None:
            continue
        window = pose[j:i + 1]
        if all(OPENING_Y[0] <= yy <= OPENING_Y[1] for _, _, yy in window):
            return dict(crossed=True, tick=t, frame_id=i,
                        lateral_offset_m=round(y - DOOR_Y, 4),
                        min_jamb_gap_m=round(min(jamb_gap(yy) for _, _, yy in window), 4),
                        crossing_ticks=len(window))
    return dict(crossed=False, tick=None, frame_id=None,
                lateral_offset_m=None, min_jamb_gap_m=None, crossing_ticks=0)


def _stage_sequence(trace):
    seq = []
    for r in trace:
        st = r.get('stage')
        if not seq or seq[-1][0] != st:
            seq.append([st, r['t']])
    if seq:
        seq.append(['end', trace[-1]['t']])
    return seq


def recount_episode(ep_dir: Path):
    ep = load_json(ep_dir / 'episode.json')
    trace = load_jsonl(ep_dir / 'trace.jsonl')
    labels = load_json(ep_dir / 'eval-only.json')['frames']
    admission = (load_json(ep_dir / 'admission.json')
                 if (ep_dir / 'admission.json').is_file() else {})
    frames = {f['frame_id']: f for f in labels}
    door = door_crossing(labels)
    cross_t = door['tick']
    colour_ticks = [r['t'] for r in trace
                    if (r.get('action') or {}).get('colour_seen')]
    found_ticks = [r['t'] for r in trace if (r.get('action') or {}).get('found')]
    mem_ticks = [r['t'] for r in trace
                 for e in (r.get('memory_events') or [])
                 if e.get('observation') == OBS]
    post_colour = [t for t in colour_ticks
                   if cross_t is not None and t > cross_t]
    post_found = sorted(t for t in set(found_ticks + mem_ticks)
                        if cross_t is not None and t > cross_t)
    arrived = [r for r in trace if (r.get('action') or {}).get('arrived')]
    declared_t = arrived[0]['t'] if arrived else None
    declared_frame = frames.get(arrived[0]['frame_id']) if arrived else None
    inside = (bool(declared_frame['inside_zone_B'])
              if declared_frame is not None else None)
    post_pose = [f for f in labels
                 if cross_t is not None and f['t'] > cross_t]
    post_zone = [round(zone_range(f['pose'][0], f['pose'][1]), 3)
                 for f in post_pose]
    # --- Stage B (loaded) own/GT cargo cells, recomputed from the raw trace ---
    box_ticks = [f for f in labels if f.get('box_pose_eval_only') is not None]
    cargo_own_ticks = [r for r in trace if (r.get('cargo_own') is not None)]
    cargo_at_start = (cargo_own_ticks[0]['cargo_own']['state']
                      if cargo_own_ticks else None)
    cargo_at_cross = None
    if cross_t is not None:
        after = [r for r in cargo_own_ticks if r['t'] >= cross_t]
        cargo_at_cross = after[0]['cargo_own']['state'] if after else None
    box_at_declared = None
    if arrived:
        df = frames.get(arrived[0]['frame_id'])
        if df is not None:
            box_at_declared = df.get('box_pose_eval_only')
    cargo_at_arrival = (arrived[0].get('cargo_own') or {}).get('state') if arrived else None
    box_final = box_ticks[-1]['box_pose_eval_only'] if box_ticks else None
    cargo_in_zone_declared = (zone_margin(box_at_declared[0], box_at_declared[1]) >= 0.
                              if box_at_declared else None)
    cargo_margin_declared = (round(zone_margin(box_at_declared[0], box_at_declared[1]), 4)
                             if box_at_declared else None)
    cargo_in_zone_final = (zone_margin(box_final[0], box_final[1]) >= 0.
                           if box_final else None)
    audit = ep.get('input_audit') or {}
    counters = audit.get('counters') or {}
    audit_zero = bool(audit.get('passed')) and not any(counters.values())
    status = ep.get('status')
    cap_end = status == 'cap_end'
    carry_loaded = bool(ep.get('carry_loaded'))
    reason = None
    if not audit_zero:
        reason = 'input_audit_fail'
    elif not admission.get('accepted', True):
        reason = 'start_invalid_overlap'
    elif carry_loaded and cargo_at_start != 'held':
        reason = 'cargo_lost_own'
    elif not door['crossed']:
        reason = 'cap_end' if cap_end else 'door_not_crossed'
    elif carry_loaded and cargo_at_cross != 'held':
        reason = 'cargo_lost_own'
    elif not post_colour and not post_found:
        reason = 'cap_end' if cap_end else 'destination_not_found'
    elif arrived and inside is not True:
        reason = 'false_arrival_outside_zone'
    elif carry_loaded and arrived and cargo_in_zone_declared is not True:
        reason = 'cargo_not_in_zone'
    elif not arrived:
        reason = 'arrival_unverified'
    return dict(
        episode=int(ep['episode']), status=status, cap_end=cap_end,
        start_valid=bool(admission.get('accepted', True)),
        input_audit_zero=audit_zero,
        input_audit=dict(calls=audit.get('calls'), counters=counters,
                         violations=(audit.get('violations') or [])[:3]),
        door_crossed=door['crossed'], door_cross_tick=door['tick'],
        skill_claimed_gap=any(r.get('stage') in ('gap_cross', 'gap_forward')
                              for r in trace),
        stage_runs=_stage_sequence(trace),
        door_cross_t_s=door['tick'],
        door_lateral_offset_m=door['lateral_offset_m'],
        door_min_jamb_gap_m=door['min_jamb_gap_m'],
        door_crossing_ticks=door['crossing_ticks'],
        post_cross_colour_seen=bool(post_colour),
        post_cross_found=bool(post_found),
        post_cross_found_t_s=post_found[0] if post_found else None,
        found_any_pre_cross_reference_only=bool(found_ticks or mem_ticks),
        colour_any=bool(colour_ticks),
        arrived_declared=bool(arrived), declared_t_s=declared_t,
        gt_inside=inside,
        gt_zone_margin_at_declared_m=(round(zone_margin(
            declared_frame['pose'][0], declared_frame['pose'][1]), 4)
            if declared_frame is not None else None),
        gt_post_cross_zone_distance_m=(min(post_zone) if post_zone else None),
        time_to_cross_s=door['tick'],
        time_to_declare_s=declared_t,
        rotation_cmd_rad=ep.get('rotation_cmd_rad'),
        rotation_gt_rad_eval_only=ep.get('rotation_gt_rad_eval_only'),
        start_visibility_pixels=ep.get('start_visibility_pixels'),
        start_paint_reason=ep.get('start_paint_reason'),
        sim_s=ep.get('sim_s'), wall_s=ep.get('wall_s'),
        camera_frames=ep.get('camera_frames'),
        final_pose_eval_only=ep.get('final_pose_eval_only'),
        final_stage=trace[-1].get('stage') if trace else None,
        stage_sequence=_stage_sequence(trace),
        memory_landmarks=ep.get('memory_landmarks'),
        collision_events=(ep.get('collision_events')
                          if ep.get('collision_events') is not None
                          else 'not_measured'),
        carry_loaded=bool(ep.get('carry_loaded')),
        fix_stage=(ep.get('crossroom_stage') in ('A_unloaded_fix',
                                                  'A_unloaded_fix2')),
        fix_stage_v2=(ep.get('crossroom_stage') == 'A_unloaded_fix2'),
        fix_summary=ep.get('fix_summary'),
        paint_filter_counts=ep.get('paint_filter_counts'),
        contact_summary=ep.get('contact_summary'),
        ncon_ticks=(sum(1 for f in labels if f.get('ncon_eval_only'))),
        cargo_held_at_start=cargo_at_start,
        cargo_held_at_cross=cargo_at_cross,
        cargo_held_at_arrival=cargo_at_arrival,
        box_at_declared_eval_only=box_at_declared,
        box_final_pose_eval_only=box_final,
        cargo_in_zone_at_declared_gt=cargo_in_zone_declared,
        cargo_zone_margin_at_declared_gt=cargo_margin_declared,
        cargo_in_zone_final_gt=cargo_in_zone_final,
        evidence=dict(trace=str(ep_dir / 'trace.jsonl'),
                      eval_only=str(ep_dir / 'eval-only.json'),
                      frames=str(ep_dir / 'frames')),
        reason_category=reason,
        blocked_object='not_observed',
        minimum_gap_m=None,
        gap_status='not_measured',
    )


def funnel(rows, carry_loaded=False):
    stages = [
        ('requested_n16', lambda r: True),
        ('input_audit_zero', lambda r: r['input_audit_zero']),
        ('start_valid', lambda r: r['start_valid']),
    ]
    if carry_loaded:
        stages.append(('cargo_held_own_at_start',
                       lambda r: r['cargo_held_at_start'] == 'held'))
    stages.append(('door_crossed', lambda r: r['door_crossed']))
    if carry_loaded:
        stages.append(('cargo_held_own_at_cross',
                       lambda r: r['cargo_held_at_cross'] == 'held'))
    stages += [
        ('post_cross_colour_seen', lambda r: r['post_cross_colour_seen']),
        ('post_cross_found', lambda r: r['post_cross_found']),
        ('arrived_declared', lambda r: r['arrived_declared']),
    ]
    if carry_loaded:
        stages.append(('cargo_held_own_at_arrival',
                       lambda r: r['cargo_held_at_arrival'] == 'held'))
        stages.append(('gt_cargo_in_zone',
                       lambda r: r['cargo_in_zone_at_declared_gt'] is True))
    else:
        stages.append(('gt_inside', lambda r: r['gt_inside'] is True))
    out, remaining = [], list(rows)
    for name, cond in stages:
        passed = [r for r in remaining if cond(r)]
        out.append(dict(stage=name, input_n=len(remaining),
                        cumulative_pass_n=len(passed),
                        rejected_n=len(remaining) - len(passed)))
        remaining = passed
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    summary = load_json(run / 'summary.json') if (run / 'summary.json').is_file() else {}
    dirs = [d for d in sorted((run / 'episodes').glob('e[0-9]*'))
            if (d / 'episode.json').is_file()]
    rows = [recount_episode(d) for d in dirs]
    carry_stage = bool(rows) and rows[0]['carry_loaded']
    fix_stage = bool(rows) and any(r['fix_stage'] for r in rows)
    fix_stage_v2 = bool(rows) and any(r.get('fix_stage_v2') for r in rows)
    n = len(rows)
    ep_summary = {e['episode']: e for e in summary.get('episodes', [])}
    mismatches = []
    for r in rows:
        s = ep_summary.get(r['episode'], {})
        if not s:
            continue
        for field, mine in (('found', r['found_any_pre_cross_reference_only']),
                            ('arrived_declared', r['arrived_declared']),
                            ('arrival_verdict_gt_inside_zone_B', r['gt_inside'])):
            if field in s and bool(s[field]) != bool(mine):
                mismatches.append(dict(episode=r['episode'], field=field))
    reasons = {}
    for r in rows:
        if r['reason_category']:
            reasons[r['reason_category']] = reasons.get(r['reason_category'], 0) + 1
    walls = [float(e.get('wall_s') or 0) for e in summary.get('episodes', [])]
    batch_wall = max(walls) if walls else None
    cap = float(summary.get('sim_cap_s') or 180.0)
    nw = int(summary.get('worlds_per_batch') or n or 1)
    first30 = None
    for pd in sorted(run.glob('episodes/e*/progress.json')):
        try:
            p = load_json(pd)
        except Exception:
            continue
        if abs(float(p.get('t') or 0) - 30.0) < 1e-6 and p.get('wall_s'):
            first30 = float(p['wall_s'])
            break
    if first30 is None:
        import os
        f0 = run / 'episodes' / 'e00' / 'frames' / '00000.jpg'
        f300 = run / 'episodes' / 'e00' / 'frames' / '00300.jpg'
        if f0.is_file() and f300.is_file():
            dt = os.stat(f300).st_mtime - os.stat(f0).st_mtime
            first30 = dt
            first30_source = 'frame mtime delta (estimate; progress t=30 overwritten)'
        else:
            first30_source = None
    else:
        first30_source = 'progress.json t=30'
    stage_label = ('B_loaded' if carry_stage
                   else ('A_unloaded_fix2' if fix_stage_v2
                         else 'A_unloaded_fix' if fix_stage else 'A_unloaded'))
    out = dict(
        schema='ugrp.crossroom_carry.recount.v1',
        stage=stage_label,
        run=str(run),
        summary_status=summary.get('status'),
        source_sha=summary.get('source_sha'),
        n=n,
        funnel=funnel(rows, carry_stage),
        reasons=reasons,
        cap_end_n=sum(1 for r in rows if r['cap_end']),
        carry_stage=('B_loaded' if carry_stage else 'A_unloaded'),
        cargo_held_at_start_n=sum(1 for r in rows
                                  if r['cargo_held_at_start'] == 'held'),
        cargo_held_at_cross_n=sum(1 for r in rows
                                  if r['cargo_held_at_cross'] == 'held'),
        cargo_held_at_arrival_n=sum(1 for r in rows
                                    if r['cargo_held_at_arrival'] == 'held'),
        cargo_in_zone_at_declared_n=sum(
            1 for r in rows if r['cargo_in_zone_at_declared_gt'] is True),
        cargo_in_zone_final_n=sum(
            1 for r in rows if r['cargo_in_zone_final_gt'] is True),
        fix_stage=fix_stage,
        fix_stage_v2=fix_stage_v2,
        gap_claim_false_n=sum(1 for r in rows
                              if r['skill_claimed_gap'] and not r['door_crossed']),
        gap_claims_with_gt_crossing_n=sum(
            1 for r in rows if r['skill_claimed_gap'] and r['door_crossed']),
        gap_rejected_front_missing_n=sum(
            int(((r.get('fix_summary') or {}).get('gap_rejected', 0))) for r in rows),
        gap_confirmed_n=sum(
            int(((r.get('fix_summary') or {}).get('gap_confirmed', 0))) for r in rows),
        door_align_turns_n=sum(
            int(((r.get('fix_summary') or {}).get('align_turns', 0))) for r in rows),
        door_align_uncertain_ticks=sum(
            int(((r.get('fix_summary') or {}).get('align_uncertain_ticks', 0)))
            for r in rows),
        paint_rejected_small_extent_n=sum(
            int(((r.get('paint_filter_counts') or {}).get('rejected', 0))) for r in rows),
        collision_ticks_n=sum(
            int(((r.get('contact_summary') or {}).get('ticks_with_contact', 0)))
            for r in rows),
        contact_events_n=sum(
            len(((r.get('contact_summary') or {}).get('events') or [])) for r in rows),
        door_crossed_n=sum(1 for r in rows if r['door_crossed']),
        post_cross_colour_n=sum(1 for r in rows if r['post_cross_colour_seen']),
        post_cross_found_n=sum(1 for r in rows if r['post_cross_found']),
        arrived_declared_n=sum(1 for r in rows if r['arrived_declared']),
        gt_inside_n=sum(1 for r in rows if r['gt_inside'] is True),
        input_audit_zero_n=sum(1 for r in rows if r['input_audit_zero']),
        start_valid_n=sum(1 for r in rows if r['start_valid']),
        near_wall_n=sum(1 for r in rows if r['episode'] < 8),
        far_wall_n=sum(1 for r in rows if r['episode'] >= 8),
        batch_wall_s=(round(batch_wall, 2) if batch_wall else None),
        wall_per_cap_nworld=(round(batch_wall / (cap * nw), 4)
                             if batch_wall else None),
        first30_wall_s=round(first30, 2) if first30 else None,
        first30_source=first30_source,
        skill_claimed_gap_n=sum(1 for r in rows if r['skill_claimed_gap']),
        skill_claimed_gap_episodes=[r['episode'] for r in rows
                                    if r['skill_claimed_gap']],
        gt_door_crossed_episodes=[r['episode'] for r in rows if r['door_crossed']],
        first30_metric=(round(first30 / (30.0 * nw), 4) if first30 else None),
        mismatches=mismatches,
        episodes=rows,
        rejection_table=dict(
            unit='episode', stage='A_unloaded', run=str(run),
            fields=['episode', 'reason_category', 'blocked_object',
                    'minimum_gap_m', 'gap_status', 'sim_s',
                    'door_lateral_offset_m', 'final_pose_eval_only',
                    'evidence', 'raw_path'],
            rows=[dict(episode=r['episode'], reason_category=r['reason_category'],
                       blocked_object=r['blocked_object'],
                       minimum_gap_m=r['minimum_gap_m'],
                       gap_status=r['gap_status'], sim_s=r['sim_s'],
                       door_lateral_offset_m=r['door_lateral_offset_m'],
                       final_pose_eval_only=r['final_pose_eval_only'],
                       evidence=r['evidence'], raw_path=str(run))
                  for r in rows if r['reason_category']]),
        scope=('raw recount of trace/eval-only; no physics rerun; truth read '
               'only in eval-only cells and in the arrival verdict/analysis. '
               'Stage A measures unloaded destination search after the door; '
               'cargo transport is not part of Stage A.'),
    )
    Path(a.output).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: out[k] for k in
                      ('n', 'funnel', 'door_crossed_n', 'post_cross_colour_n',
                       'post_cross_found_n', 'arrived_declared_n', 'gt_inside_n',
                       'cap_end_n', 'reasons', 'mismatches', 'batch_wall_s',
                       'wall_per_cap_nworld', 'first30_wall_s',
                       'first30_metric')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
