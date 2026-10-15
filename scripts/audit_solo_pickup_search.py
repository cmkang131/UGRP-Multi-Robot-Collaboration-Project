"""Offline evidence/FK audit. No model construction, physics, render or submission.

Truth is read ONLY here for evaluation. Controller search receives static
pickup geometry and its authored prior. Projections are nominal commanded FK,
not recovered measured joints; recorded visible_n is the actual run's gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from scripts.audit_grasp_act_visibility import read
from scripts.make_solo_teacher_plan import line_of_sight
from scripts.zone_teacher import FOLDED
from sim.grasp_act_solo_lookback import transforms
from sim.grasp_act_solo_teacher import primitives
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D
from sim.solo_carry_pose import CommandPose, task_start
from sim.solo_pickup_search import PickupSearch
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects
from harness.zone_environment_registry import load_scenario


def probes(xyz):
    center = np.asarray(xyz, float)
    return np.array([center, *[center+np.eye(3)[a]*s*.8*h
                    for a, h in enumerate((.017, .020, .016)) for s in (-1, 1)]])


def projection(points, pose, pwm, margin=0.):
    x, y, yaw = pose; c, s = math.cos(yaw), math.sin(yaw)
    body = (np.asarray(points)-[x, y, 0.]) @ np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    _, camera = transforms({int(k): v for k, v in pwm.items()})
    optical = (body-camera[:3, 3]) @ camera[:3, :3]
    k = scaled_camera_matrix(640, 480)
    pinhole = optical[:, :2]/np.maximum(optical[:, 2:], 1e-12)*np.diag(k)[:2]+k[:2, 2]
    raw = cv2.fisheye.projectPoints(optical.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                   k, np.asarray(CAMERA_FISHEYE_D))[0].reshape(-1, 2)
    inside = optical[:, 2] > .01
    for pixels in (pinhole, raw):
        inside &= ((pixels >= margin) & (pixels < np.array([640, 480])-margin)).all(axis=1)
    axis = camera[:3, 2]
    return {'in_frame_n': int(inside.sum()), 'N': len(points),
            'center_pinhole_px': pinhole[0].tolist(), 'center_raw_px': raw[0].tolist(),
            'camera_body_yaw_deg': math.degrees(math.atan2(axis[1], axis[0])),
            'camera_pitch_deg': math.degrees(math.asin(axis[2]))}


def scan_views(static):
    loc = CommandPose(task_start(static)); search = PickupSearch(static, loc, primitives())
    pwm = dict(FOLDED)
    for i in range(600):
        loc.now = i*.1  # stationary commanded base, no physics
        pwm, failure = search.step(loc.now, pwm)
        if failure:
            assert failure == 'pickup_search_exhausted'
            return search.views
    raise AssertionError('static search cannot finish within its 60 s phase budget')


def geometry_coverage(plan):
    rows = []
    for e in plan['episodes']:
        static = resolve(e['map_id'])[0]; views = scan_views(static)
        x, y, _, yaw = e['spawns']['r1']; points = probes([*e['cargo_pose_m'][:2], .016])
        witnesses = []
        for view in views:
            p = projection(points, (x, y, yaw), view['pwm'], margin=8.)
            if p['in_frame_n'] >= 3:
                witnesses.append({**view, **p})
        prior = task_start(static)['pose_m_rad']
        corners = [[prior[0]+dx, prior[1]+dy, prior[2]+da]
                   for dx in (-.02, .02) for dy in (-.02, .02)
                   for da in (-math.radians(2.), math.radians(2.))]
        robust = sum(any(projection(points, pose, v['pwm'], margin=8.)['in_frame_n'] >= 3
                         for v in views) for pose in corners)
        setup = load_scenario(e['scenario_id'])['eval']['setup']
        others = [p for p in setup['placements'] if p['item_id'] != e['item_id']]
        los = line_of_sight((x, y), e['cargo_pose_m'][:2], keepout_rects(static, perimeter=True), others)
        # Conservative planar parked-peer check, evaluation only.
        a = np.array([x, y]); d = points[0, :2]-a
        peers_clear = all(np.linalg.norm(np.array(p[:2])-(a+np.clip(
            (np.array(p[:2])-a)@d/(d@d), 0., 1.)*d)) > .18
            for rid, p in e['spawns'].items() if rid != 'r1')
        rows.append({'seed': e['seed'], 'condition_source_seed': e.get('condition_source_seed', e['seed']),
            'kind': e['kind'], 'scenario_id': e['scenario_id'], 'map_id': e['map_id'],
            'setup_pose': [x, y, yaw], 'cargo_eval_xyz': points[0].tolist(),
            'start_range_m': math.dist((x, y), points[0, :2]),
            'initial_bearing_deg': math.degrees(math.atan2(points[0, 1]-y, points[0, 0]-x)-yaw),
            'in_search_fov': bool(witnesses), 'jitter_corner_fov_n': robust, 'jitter_corner_N': 8,
            'map_and_other_cargo_planar_los': los, 'parked_peers_planar_clear': bool(peers_clear),
            'first_completed_view_witness': witnesses[0] if witnesses else None,
            'full_scan_views': len(views), 'full_scan_s': views[-1]['end_t']})
    return {'N': len(rows), 'fov_n': sum(r['in_search_fov'] for r in rows),
            'fov_and_planar_los_n': sum(r['in_search_fov'] and r['map_and_other_cargo_planar_los']
                                      and r['parked_peers_planar_clear'] for r in rows),
            'scope': 'offline commanded FK, pinhole AND fisheye with 8px margin; seven probes, >=3 required; '
                     'planar LOS only, not physical visibility, recognition or mission success',
            'rows': rows}


def inspect_raw(root, csv_path):
    trace = read(root/'teacher-commands.jsonl', True); ev = read(root/'eval-only.jsonl', True)
    assert len(trace) == len(ev)
    rows = []
    for i, (t, e) in enumerate(zip(trace, ev)):
        assert abs(t['t']-e['t']) < 1e-8
        base = e['base_xyz']; yaw = t['map_pose']['pose_estimate'][2]-e['map_pose_error_yaw_rad']
        delta = np.array(e['cargo_xyz'])-np.r_[base[:2], 0.]
        rel = [math.cos(yaw)*delta[0]+math.sin(yaw)*delta[1],
               -math.sin(yaw)*delta[0]+math.cos(yaw)*delta[1], delta[2]]
        # Camera was captured BEFORE issuing this row's command.
        pwm = trace[max(0, i-1)]['command']['pwm']
        p = projection(probes(e['cargo_xyz']), [*base[:2], yaw], pwm)
        rows.append({'tick': i, 't': t['t'], 'sim_s': t['t']-trace[0]['t'], 'phase': t['phase'],
            'base_x': base[0], 'base_y': base[1], 'base_yaw_deg': math.degrees(yaw),
            'relative_x': rel[0], 'relative_y': rel[1], 'range_m': math.hypot(*rel[:2]),
            'bearing_deg': math.degrees(math.atan2(rel[1], rel[0])),
            'wheel_nonzero': any(t['command']['wheels']), 'visible_n': e['visible_n'],
            'probe_N': e['probe_N'], 'fk_in_frame_n': p['in_frame_n'],
            'camera_body_yaw_deg': p['camera_body_yaw_deg'], 'camera_pitch_deg': p['camera_pitch_deg'],
            **{f'previous_pwm_{k}': v for k, v in pwm.items()}})
    with csv_path.open('x') as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator='\n'); w.writeheader(); w.writerows(rows)
    plan = read(root/'plan.json')
    return {'N': len(rows), 'phase_counts': dict(Counter(r['phase'] for r in rows)),
        'actual_visible_ticks': sum(r['visible_n'] >= math.ceil(r['probe_N']/3) for r in rows),
        'command_fk_in_frame_ticks': sum(r['fk_in_frame_n'] >= 3 for r in rows),
        'wheel_nonzero_ticks': sum(r['wheel_nonzero'] for r in rows),
        'command_pan_range': [min(t['command']['pwm']['6'] for t in trace), max(t['command']['pwm']['6'] for t in trace)],
        'base_displacement_max_m': max(math.dist(ev[0]['base_xyz'][:2], e['base_xyz'][:2]) for e in ev),
        'first_tick': rows[0], 'last_tick': rows[-1], 'plan_spawn': plan['spawns']['r1'],
        'task_start': plan['task_start'],
        'plan_jitter_xy_m': math.dist(plan['spawns']['r1'][:2], plan['task_start']['pose_m_rad'][:2]),
        'eval_start_vs_spawn_xy_m': math.dist(ev[0]['base_xyz'][:2], plan['spawns']['r1'][:2]),
        'input_audit': read(root/'result.json')['input_audit'],
        'raw_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (root/'plan.json', root/'result.json', root/'teacher-commands.jsonl.zst', root/'eval-only.jsonl.zst', root/'scene.xml')},
        'tick_csv_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        'fk_limit': 'previous issued PWM + evaluation base xy/yaw; measured arm joints/base roll/pitch unavailable'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    result = {'inspection': inspect_raw(a.raw, a.out/'ticks.csv'),
              'geometry': geometry_coverage(read(a.plan)), 'new_physics_runs': 0}
    (a.out/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result['geometry'][k] for k in ('N', 'fov_n', 'fov_and_planar_los_n')}))


if __name__ == '__main__':
    main()
