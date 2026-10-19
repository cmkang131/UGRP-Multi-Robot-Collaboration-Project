#!/usr/bin/env python3
"""Eval-only recount for the nav Step B v230_r3 run (no success claim).

Reads the raw run directory and the admission directory of one
``run_e2e_warp --mode nav`` execution and re-derives every number the Step B
acceptance table needs, from raw rows only:

- source/pin equality (admission queue, run queue, RUN_META, result);
- per-robot detection ticks (any zone_B landmark / fresh this tick), largest
  component, first detection time, forward cap use, drive_reason distribution;
- the r3 arming event, the own-odometry pose/projection direction, the claim
  tick and the projection/path at the claim, and the NO_CLAIM fail-safe record;
- eval-only GT: final base xy and inside/outside the authored zone rectangle,
  plus the armed->claim GT displacement/path next to the odometry displacement
  (diagnostic only, never a controller input);
- boundary audits (top camera, static map, held world reads, noslip, CPU physics),
  wheel/command counts and the 60 s budget markers.

The script writes one JSON report and never writes into the run directory, so the
raw sha256.json stays the run's own.  It never re-enters the run and never claims
physical or E2E success (nav mode has no evaluator).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = 'ugrp.e2ewarp.nav_v230_r3_analysis.v1'
ROBOTS = ('r1', 'r2')
TICK_HZ = 10.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def inside(xy, center, half):
    return bool(abs(float(xy[0]) - float(center[0])) <= float(half[0])
                and abs(float(xy[1]) - float(center[1])) <= float(half[1]))


def component_px(landmark):
    """Bounding-box area of the detector's largest component (raw memory rows).

    ``SelfCentricMemory.as_report`` carries the component bbox, not the pixel
    count; the tight bbox area is the reported size measure (an upper bound on
    the component's pixels, equal to the detector's own ``pixels`` when the
    component fills its box).  The render preflight measures the exact count.
    """
    bbox = (landmark or {}).get('bbox')
    if not bbox or len(bbox) != 4:
        return 0
    left, top, right, bottom = (int(v) for v in bbox)
    return max(0, right - left) * max(0, bottom - top)


def zone_b_largest(row):
    memory = (row.get('own_navigation') or {}).get('self_centric_memory') or []
    hits = [m for m in memory if str(m.get('kind')) == 'zone_B']
    if not hits:
        return None
    return max(hits, key=component_px)


def fresh_zone_b(row):
    memory = (row.get('own_navigation') or {}).get('self_centric_memory') or []
    sim_s = float(row.get('sim_s') or 0.0)
    hits = [m for m in memory if str(m.get('kind')) == 'zone_B'
            and abs(float(m.get('last_seen_s') or 0.0) - sim_s) <= 1e-9]
    return max(hits, key=component_px) if hits else None


def gt_track(run, robot, qpos):
    geometry_path = Path(run) / 'world-00' / 'eval-geometry.json'
    geometry = json.loads(geometry_path.read_text())
    if robot not in geometry['robot_qpos_adr']:
        raise ValueError('robot missing from eval geometry: ' + robot)
    adr = int(geometry['robot_qpos_adr'][robot])
    return geometry, qpos[:, 0, adr:adr + 2]


def first_index(rows, predicate):
    return next((i for i, row in enumerate(rows) if predicate(row)), None)


def robot_report(run, rows, robot, qpos, destination):
    """One robot's raw recount.  ``rows`` are that robot's localization rows."""
    rows = sorted(rows, key=lambda r: float(r['sim_s']))
    geometry, track = gt_track(run, robot, qpos)
    sim = [float(r['sim_s']) for r in rows]
    own = [r.get('own_navigation') or {} for r in rows]
    # detection
    detected = [z is not None for z in (zone_b_largest(r) for r in rows)]
    fresh = [z is not None for z in (fresh_zone_b(r) for r in rows)]
    components = [component_px(zone_b_largest(r)) for r in rows]
    first_detection = next((i for i, hit in enumerate(detected) if hit), None)
    first_fresh = next((i for i, hit in enumerate(fresh) if hit), None)
    first_fresh_row = rows[first_fresh] if first_fresh is not None else None
    first_fresh_mem = fresh_zone_b(first_fresh_row) if first_fresh_row is not None else None
    # arming / claim / fail-safe
    armed_i = first_index(own, lambda o: bool(o.get('arrival_armed')))
    claim_i = first_index(own, lambda o: bool(o.get('destination_arrived')))
    no_claim_i = first_index(own, lambda o: bool(o.get('arrival_no_claim')))
    arrival_modes = sorted({str(o.get('arrival_mode')) for o in own})
    reasons = {}
    for o in own:
        key = str(o.get('drive_reason'))
        reasons[key] = reasons.get(key, 0) + 1
    commands = load_json(Path(run) / 'commands.json') or []
    own_commands = [c for c in commands if str(c.get('robot')) == robot]
    moving = sum(1 for c in own_commands
                 if any(abs(float(w)) > 0.0 for w in (c.get('wheels') or [])))

    def pose_at(i):
        return own[i].get('odom_pose')

    def gt_at(i):
        return track[min(i, len(track) - 1)]

    armed = None
    if armed_i is not None:
        armed_mem = fresh_zone_b(rows[armed_i]) or zone_b_largest(rows[armed_i]) or {}
        armed = dict(index=armed_i, sim_s=sim[armed_i],
                     gt_xy=[round(float(v), 4) for v in gt_at(armed_i)],
                     odom_pose=pose_at(armed_i),
                     u_deg=own[armed_i].get('arrival_u_deg'),
                     bearing_armed_deg=own[armed_i].get('arrival_bearing_armed_deg'),
                     heading_error_deg=own[armed_i].get('arrival_heading_error_deg'),
                     bottom_norm=armed_mem.get('bottom_norm'),
                     height_norm=armed_mem.get('height_norm'),
                     component_px=component_px(armed_mem),
                     detection_fresh=bool(fresh_zone_b(rows[armed_i]) is not None),
                     forward_used_m=own[armed_i].get('forward_used_m'),
                     drive_reason=own[armed_i].get('drive_reason'))
    claim = None
    if claim_i is not None:
        claim = dict(index=claim_i, sim_s=sim[claim_i],
                     gt_xy=[round(float(v), 4) for v in gt_at(claim_i)],
                     inside_gt=inside(gt_at(claim_i), destination['center_m'],
                                      destination['half_extents_m']),
                     odom_pose=pose_at(claim_i),
                     projection_m=own[claim_i].get('arrival_projection_m'),
                     path_m=own[claim_i].get('arrival_path_m'),
                     travel_m=own[claim_i].get('arrival_travel_m'),
                     heading_error_deg=own[claim_i].get('arrival_heading_error_deg'),
                     drive_reason=own[claim_i].get('drive_reason'))
    no_claim = None
    if no_claim_i is not None:
        no_claim = dict(index=no_claim_i, sim_s=sim[no_claim_i],
                        gt_xy=[round(float(v), 4) for v in gt_at(no_claim_i)],
                        projection_m=own[no_claim_i].get('arrival_projection_m'),
                        path_m=own[no_claim_i].get('arrival_path_m'),
                        drive_reason=own[no_claim_i].get('drive_reason'))
    # armed -> claim displacement, odometry vs GT (diagnostic only)
    displacement = None
    if (armed is not None and claim is not None and claim['index'] > armed['index']
            and armed['odom_pose'] is not None and claim['odom_pose'] is not None):
        start, end = armed['index'], claim['index']
        gt_start, gt_end = gt_at(start), gt_at(end)
        gt_path = float(np.linalg.norm(np.diff(track[start:end + 1], axis=0), axis=1).sum())
        odom0, odom1 = armed['odom_pose'], claim['odom_pose']
        odom_dx = float(odom1[0]) - float(odom0[0])
        odom_dy = float(odom1[1]) - float(odom0[1])
        u = math.radians(float(armed['u_deg'] or 0.0))
        gt_dx = float(gt_end[0]) - float(gt_start[0])
        gt_dy = float(gt_end[1]) - float(gt_start[1])
        displacement = dict(
            ticks=end - start, sim_s=round(sim[end] - sim[start], 3),
            gt_dx_m=round(gt_dx, 4), gt_dy_m=round(gt_dy, 4),
            gt_norm_m=round(math.hypot(gt_dx, gt_dy), 4),
            gt_path_m=round(gt_path, 4),
            gt_dot_u_m=round(gt_dx * math.cos(u) + gt_dy * math.sin(u), 4),
            odom_dx_m=round(odom_dx, 4), odom_dy_m=round(odom_dy, 4),
            odom_norm_m=round(math.hypot(odom_dx, odom_dy), 4),
            odom_projection_m=claim['projection_m'],
            odom_path_m=claim['path_m'],
            odom_over_gt_path=round(float(claim['path_m'] or 0.0) / gt_path, 3) if gt_path > 0 else None,
            diagnostic_only=True,
            note='world-frame GT next to the self-odometry displacement; never a controller input')
    final = track[-1]
    west_edge = float(destination['center_m'][0]) - float(destination['half_extents_m'][0])
    post_claim = None
    if claim_i is not None:
        # GT motion between the claim tick and the final tick: the wheels are
        # held after the claim, so any motion here is coasting/slip (diagnostic).
        gt_claim = gt_at(claim_i)
        post_claim = dict(ticks=len(track) - 1 - claim_i,
                          dx_m=round(float(final[0]) - float(gt_claim[0]), 4),
                          dy_m=round(float(final[1]) - float(gt_claim[1]), 4),
                          norm_m=round(float(np.linalg.norm(final - gt_claim)), 4),
                          diagnostic_only=True)
    return dict(
        robot=robot,
        sim_s_span=[round(sim[0], 3), round(sim[-1], 3)] if sim else None,
        localization_rows=len(rows),
        detection_n=sum(detected), detection_ticks=sum(detected),
        fresh_detection_n=sum(fresh), fresh_detection_ticks=sum(fresh),
        max_component_px=max(components) if components else 0,
        max_component_px_fresh=max(
            [component_px(fresh_zone_b(r)) for r in rows], default=0),
        first_detection=({} if first_detection is None else
                         dict(index=first_detection, sim_s=sim[first_detection],
                              pixels=component_px(zone_b_largest(rows[first_detection])))),
        first_fresh_detection=({} if first_fresh is None else
                               dict(index=first_fresh, sim_s=sim[first_fresh],
                                    bottom_norm=(first_fresh_mem or {}).get('bottom_norm'),
                                    height_norm=(first_fresh_mem or {}).get('height_norm'),
                                    pixels=component_px(first_fresh_mem))),
        drive_reason=reasons,
        command_rows=len(own_commands), moving_command_rows=moving,
        forward_used_m=max([float(o.get('forward_used_m') or 0.0) for o in own], default=0.0),
        forward_steps=max([int(o.get('forward_steps') or 0) for o in own], default=0),
        search_steps=max([int(o.get('search_steps') or 0) for o in own], default=0),
        arrival_modes=arrival_modes,
        armed=armed, claim=claim, no_claim=no_claim,
        armed_to_claim=displacement,
        final_gt_xy=[round(float(v), 4) for v in final],
        final_inside_gt=inside(final, destination['center_m'], destination['half_extents_m']),
        gt_path_m=round(float(np.linalg.norm(np.diff(track, axis=0), axis=1).sum()), 4),
        x_margin_to_west_edge_final_m=round(float(final[0]) - west_edge, 4),
        x_margin_to_west_edge_claim_m=(None if claim is None else
                                       round(float(claim['gt_xy'][0]) - west_edge, 4)),
        post_claim_gt_drift=post_claim,
        gt_y_south_drift_claim_m=(None if claim is None else
                                  round(float(claim['gt_xy'][1]) - float(gt_at(armed_i)[1]), 4)
                                  if armed_i is not None else None),
    )


def recount(run_dir, admission_dir, expected_sha):
    run = Path(run_dir).resolve()
    admission = Path(admission_dir).resolve()
    result = load_json(run / 'result.json') or {}
    run_queue = load_json(run / 'queue.json') or {}
    adm_queue = load_json(admission / 'queue.json') or {}
    meta = load_json(run / 'RUN_META.json') or {}
    stack = load_json(admission / 'stack-check.json') or {}
    runtime = load_json(run / 'runtime-applied.json') or {}
    events = load_json(run / 'nav-events.json') or {}
    evaluation = load_json(run / 'nav-evaluation.json')
    rows = load_json(run / 'localization.json') or []
    state = np.load(run / 'evaluation-state.npz')
    qpos = np.asarray(state['qpos'])
    if qpos.ndim != 3:
        raise ValueError('evaluation-state qpos must be [ticks, worlds, nq]')
    geometry = json.loads((run / 'world-00' / 'eval-geometry.json').read_text())
    destination = geometry['destination']
    robots = {}
    for robot in ROBOTS:
        robots[robot] = robot_report(run, [r for r in rows if str(r.get('robot')) == robot],
                                     robot, qpos, destination)
    claim_n = sum(1 for r in robots.values() if r['claim'])
    gt_n = sum(1 for r in robots.values() if r['final_inside_gt'])
    mismatch = sum(1 for r in robots.values()
                   if bool(r['claim']) != bool(r['final_inside_gt']))
    claims_outside = sum(1 for r in robots.values() if r['claim'] and not r['claim']['inside_gt'])
    no_claim_n = sum(1 for r in robots.values() if r['no_claim'])
    ledger = load_json(run / 'llm_ledger.json') or []
    attempts = [a for row in ledger for a in ((row.get('upstream') or {}).get('attempts') or [])]
    ticks = 1 + int(round(float(result.get('sim_s') or 0.0) * TICK_HZ))
    queue_fields = ('nav_gate_mode', 'nav_scene', 'nav_map', 'nav_robots', 'nav_spawn_y',
                    'nav_destination_kind', 'nav_static_map_input', 'nav_cargo_spawned',
                    'nav_sim_budget_s', 'nav_zone_profile', 'nav_acquisition',
                    'nav_forward_cap_m', 'nav_zone_min_component', 'nav_bearing_convention',
                    'nav_acquire_min_height_norm', 'nav_acquire_confirm_ticks',
                    'nav_forward_reacquire', 'nav_arrival_mode',
                    'nav_arrival_odom_projection_m', 'nav_arrival_projection_path_cap_m',
                    'nav_calibration')
    markers = {key: dict(admission=adm_queue.get(key), run=run_queue.get(key),
                         match=adm_queue.get(key) == run_queue.get(key))
               for key in queue_fields}
    boundaries = dict(
        result_input_audit=result.get('input_audit'),
        static_map_input=result.get('static_map_input'),
        nav_static_map_input=run_queue.get('nav_static_map_input'),
        nav_cargo_spawned=run_queue.get('nav_cargo_spawned'),
        camera=runtime.get('camera'),
        gpu_noslip_iterations=runtime.get('gpu_noslip_iterations'),
        cpu_physics_steps=runtime.get('cpu_physics_steps'),
        cpu_render_calls=runtime.get('cpu_render_calls'),
        legacy_equivalence_shims=runtime.get('legacy_equivalence_shims'),
    )
    return dict(
        schema=SCHEMA, eval_only=True, no_pooling=True, research_result=False,
        success_claim='not_available', run=str(run), admission=str(admission),
        expected_source_sha=expected_sha,
        source=dict(
            admission_queue_sha=adm_queue.get('source_sha'),
            run_queue_sha=run_queue.get('source_sha'),
            run_meta_sha=meta.get('sha'),
            result_sha=result.get('source_sha'),
            vm_head_match=bool(adm_queue.get('source_sha') == expected_sha
                               == run_queue.get('source_sha') == meta.get('sha')
                               == result.get('source_sha')),
        ),
        status=result.get('status'), sim_s=result.get('sim_s'), wall_s=result.get('wall_s'),
        ticks_expected=ticks, localization_rows=len(rows),
        expected_localization_rows=len(ROBOTS) * ticks,
        commands_rows=len(load_json(run / 'commands.json') or []),
        moving_wheel_rows=sum(r['moving_command_rows'] for r in robots.values()),
        robots=robots,
        arrival_gt_n=gt_n, arrival_claim_n=claim_n, claim_mismatch_n=mismatch,
        claims_outside_gt_n=claims_outside, no_claim_n=no_claim_n,
        nav_events=events,
        queue_markers=markers,
        queue_markers_all_match=all(v['match'] for v in markers.values()),
        stack_check=dict(ok=stack.get('ok'), rows=len(stack.get('rows') or [])),
        boundaries=boundaries, model_calls=result.get('model_calls'),
        message_dropped_n=result.get('message_dropped_n'),
        llm_attempt_statuses=[a.get('status') for a in attempts],
        calibration=(run_queue.get('nav_calibration') or {}),
        eval_geometry=dict(destination=destination,
                           sha256=sha(run / 'world-00' / 'eval-geometry.json')),
        evaluation_present=bool(evaluation),
        evaluation_summary=(None if not evaluation else
                            {k: evaluation.get(k) for k in
                             ('arrival_gt_n', 'arrival_claim_n', 'claim_mismatch_n', 'status')}),
        scope='eval-only GT recount of raw base qpos next to the own-input claim; '
              'not an E2E or physical-success claim',
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--admission', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    value = recount(a.run, a.admission, a.expected_source_sha)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: value[k] for k in
                      ('status', 'sim_s', 'arrival_gt_n', 'arrival_claim_n',
                       'claim_mismatch_n', 'claims_outside_gt_n', 'no_claim_n',
                       'localization_rows', 'moving_wheel_rows',
                       'queue_markers_all_match')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
