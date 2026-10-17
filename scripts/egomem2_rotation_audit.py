"""Tick-by-tick audit of remembered-target transport during in-place rotation.

Diagnosis only; never imports into the controller and never feeds ground truth
back into control. Runs on the gcp5 original CPU against one recorded run's
saved own inputs (online-trajectory.json) and reads the evaluation-only ground
truth (eval-only.json) strictly to measure the robot's actual heading change
against the applied own-motion increment.

Coordinator request (COORDINATOR_NOTE 2026-10-17): before any further
recording, show in one table per tick the commanded rotation, the remembered
target-direction change, and the actual heading change, so the sign and the
magnitude of the memory inverse-transform can be checked numerically instead
of by argument.

The replay uses the exact MemoryReturn controller with the recording's own
summary flags; any saved-action mismatch aborts.
"""
import argparse
import csv
import math
from collections import Counter
from pathlib import Path
import platform

import numpy as np

from harness.egomem_navigation import MemoryReturn
from harness.egocentric_landmark_memory import wrap
from harness.e2e_rgb_vo import K
from scripts.egomem1_offline import read, dump, digest


def deg(v):
    return math.degrees(float(v))


def wrap_deg(v):
    return math.degrees(wrap(math.radians(float(v))))


def target_of(memories, goal):
    return next((m for m in memories if m['id'] == goal), None)


def observation_midpoint_deg(obs):
    if 'observed_endpoints_m' in obs:
        mid = np.mean(obs['observed_endpoints_m'], axis=0)
    else:
        mid = np.asarray(obs['relative_xy_m'], float)
    return deg(math.atan2(mid[1], mid[0]))


def audit(raw):
    summary = read(raw / 'summary.json')
    rows = read(raw / 'online-trajectory.json')
    gt = {f['frame_id']: f['pose'] for f in read(raw / 'eval-only.json')['frames']}
    if len(gt) != len(rows):
        raise ValueError('FRAME_GT_JOIN_REQUIRED')
    c = MemoryReturn(sweep_steps=summary['work_cap']['phase_steps'],
                     footprint_diameter_m=summary['geometric_departure_distance_floor_m'],
                     horizontal_half_fov_rad=math.atan(320 / K[0, 0]),
                     strict_return=summary.get('strict_reacquisition', False),
                     translated_return=summary.get('translated_return', False),
                     observed_segment_aim=summary.get('observed_segment_aim', False))
    half_fov_deg = deg(c.half_fov)
    table = []
    previous_bearing = None
    previous_rho_sign = None
    previous_gt_theta = None
    rho_flips = []
    gate_rows = []
    for row in rows:
        phase = c.stage
        memories = row['memory']['memories']
        target = target_of(memories, c.goal)
        action = c.step(row['t'], row['motion_delta'], memories, row['observations'],
                        colour_pixels=row['colour_component_pixels'])
        if action != row['action']:
            raise ValueError('SAVED_ACTION_REPLAY_MISMATCH:' + str(row['t']))
        mode = 'forward' if action[0] else 'turn' if action[2] else 'stop'
        applied = deg(row['motion_delta'][2])
        pose = gt[row['frame_id']]
        gt_delta = None
        if previous_gt_theta is not None:
            gt_delta = deg(wrap(pose[2] - previous_gt_theta))
        previous_gt_theta = pose[2]
        bearing = None
        rho = None
        aim_deg = None
        obs_mid = None
        matching = False
        reobserved = False
        if target is not None:
            bearing = deg(target['bearing_rad'])
            if target['representation'] == 'oriented_line':
                rho = float(target['measurement_state'][0])
            obs_match = [o for o in row['observations']
                         if o['kind'] == 'zone_boundary' and o['signature'] == target['signature']]
            matching = bool(obs_match)
            if obs_match:
                obs_mid = observation_midpoint_deg(obs_match[0])
            reobserved = any(e.get('reason') == 'reobserved' and e.get('memory_id') == target['id']
                             for e in row['memory']['events'])
        if c.aim is not None:
            aim_deg = deg(math.atan2(c.aim[1], c.aim[0]))
        angle = aim_deg if aim_deg is not None else bearing
        gate = None
        if matching and target is not None:
            gates = {
                'visual_exit': c.visual_exit,
                'colour_visible': bool(row['colour_component_pixels']),
                'memory_heading': angle is not None and abs(angle) <= half_fov_deg,
                'translated': (not c.translated_return or c.return_path >= c.diameter),
            }
            gate = next((k for k, v in gates.items() if not v), 'all_passed')
            gate_rows.append(dict(t=row['t'], mode=mode, first_reject=gate, gates=gates,
                                  target_bearing_deg=bearing, aim_deg=aim_deg,
                                  observed_mid_deg=obs_mid, rho=rho,
                                  own_return_path_m=c.return_path))
        flip = None
        if rho is not None:
            sign = rho >= 0
            if previous_rho_sign is not None and previous_rho_sign != sign:
                flip = True
                rho_flips.append(dict(t=row['t'], rho_m=rho, bearing_deg=bearing,
                                      applied_dtheta_deg=applied, mode=mode))
            previous_rho_sign = sign
        delta_bearing = None
        if bearing is not None and previous_bearing is not None:
            delta_bearing = wrap_deg(bearing - previous_bearing)
        previous_bearing = bearing
        other_updates = sum(1 for e in row['memory']['events']
                            if e.get('reason') == 'reobserved'
                            and (target is None or e.get('memory_id') != target['id']))
        table.append(dict(
            frame_id=row['frame_id'], t=row['t'], stage=phase, mode=mode,
            action_forward=row['action'][0], action_turn=row['action'][2],
            applied_dtheta_deg=applied, gt_dtheta_deg=gt_delta,
            motion_source=row.get('command_motion_source') or row['lk']['status'],
            lk_status=row['lk']['status'],
            target_id=target['id'] if target is not None else None,
            target_rep=target['representation'] if target is not None else None,
            target_bearing_deg=bearing, delta_bearing_deg=delta_bearing, rho=rho,
            rho_flip=flip, aim_deg=aim_deg, observed_mid_deg=obs_mid,
            matching_boundary=matching, reobserved=reobserved, other_updates=other_updates,
            gate_first_reject=gate,
            colour_pixels=bool(row['colour_component_pixels']),
            return_path_m=c.return_path))

    def phase_stats(phase):
        ticks = [r for r in table if r['stage'] == phase]
        if not ticks:
            return None
        turn = [r for r in ticks if r['mode'] == 'turn']
        transport = [r for r in ticks
                     if r['delta_bearing_deg'] is not None
                     and not r['reobserved'] and not r['rho_flip']
                     and previous_rep_ok(r)]
        residual = [wrap_deg(r['delta_bearing_deg'] + r['applied_dtheta_deg']) for r in transport]
        nonzero = [dict(t=r['t'], residual_deg=wrap_deg(r['delta_bearing_deg'] + r['applied_dtheta_deg']),
                        other_landmark_updates=r['other_updates'])
                   for r in transport
                   if abs(wrap_deg(r['delta_bearing_deg'] + r['applied_dtheta_deg'])) >= 1e-6]
        flips = [dict(t=r['t'], residual_deg=wrap_deg(r['delta_bearing_deg'] + r['applied_dtheta_deg']),
                      rho=r['rho'])
                 for r in ticks if r['rho_flip'] and r['delta_bearing_deg'] is not None]
        direct = [dict(t=r['t'], residual_deg=wrap_deg(r['delta_bearing_deg'] + r['applied_dtheta_deg']))
                  for r in ticks if r['reobserved'] and r['delta_bearing_deg'] is not None]
        gt_pairs = [(r['applied_dtheta_deg'], r['gt_dtheta_deg']) for r in ticks
                    if r['gt_dtheta_deg'] is not None]
        err = [wrap_deg(a - g) for a, g in gt_pairs]
        sum_applied = sum(r['applied_dtheta_deg'] for r in ticks)
        sum_gt = sum(g for _, g in gt_pairs)
        bearings = [r['target_bearing_deg'] for r in ticks if r['target_bearing_deg'] is not None]
        return dict(
            t_first=ticks[0]['t'], t_last=ticks[-1]['t'], ticks=len(ticks),
            turn_ticks=len(turn), forward_ticks=sum(r['mode'] == 'forward' for r in ticks),
            stop_ticks=sum(r['mode'] == 'stop' for r in ticks),
            sum_action_turn=sum(r['action_turn'] for r in ticks),
            sum_applied_dtheta_deg=sum_applied, sum_gt_dtheta_deg=sum_gt,
            applied_over_gt=sum_applied / sum_gt if sum_gt else None,
            target_bearing_first_deg=bearings[0] if bearings else None,
            target_bearing_last_deg=bearings[-1] if bearings else None,
            transport_ticks=len(transport),
            transport_exact_ticks=sum(abs(x) < 1e-6 for x in residual),
            transport_max_abs_residual_deg=max((abs(x) for x in residual), default=None),
            transport_residual_mean_deg=float(np.mean(residual)) if residual else None,
            nonzero_residual_ticks=nonzero,
            rho_flip_ticks=flips,
            direct_target_update_ticks=direct,
            gt_error_median_abs_deg=float(np.median(np.abs(err))) if err else None,
            gt_error_p95_abs_deg=float(np.percentile(np.abs(err), 95)) if err else None,
            gt_error_bias_deg=float(np.mean(err)) if err else None,
            motion_source_counts=dict(Counter(r['motion_source'] for r in ticks)),
        )

    def previous_rep_ok(r):
        return r['target_id'] is not None

    stats = {phase: phase_stats(phase) for phase in ('look', 'depart_turn', 'depart', 'return')}
    return dict(
        status='ROTATION_TRANSPORT_AUDIT',
        source_sha=summary.get('source_sha'),
        raw=str(raw), frames=len(table), half_fov_deg=half_fov_deg,
        observed_segment_aim=bool(c.observed_segment_aim),
        phases={k: v for k, v in stats.items() if v is not None},
        rho_flips=rho_flips,
        matching_frames=gate_rows,
        rejection_distribution=dict(Counter(r['first_reject'] for r in gate_rows)),
        table=table,
        note='applied dtheta is the own-motion increment the memory transport used '
             '(LK when qualified, own command model otherwise); gt dtheta is the '
             'evaluation-only actual heading delta used solely as the measuring stick',
        sha256=dict(trace=digest(raw / 'online-trajectory.json'),
                    eval_only=digest(raw / 'eval-only.json')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    result = audit(args.input)
    table = result.pop('table')
    dump(args.output, result)
    with args.csv.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)
    print(f"frames={result['frames']} rejection={result['rejection_distribution']}")
    for phase, s in result['phases'].items():
        print(phase, {k: s[k] for k in ('ticks', 'turn_ticks', 'sum_applied_dtheta_deg',
                                        'sum_gt_dtheta_deg', 'applied_over_gt',
                                        'transport_ticks', 'transport_exact_ticks',
                                        'transport_max_abs_residual_deg',
                                        'gt_error_median_abs_deg')})


if __name__ == '__main__':
    main()
