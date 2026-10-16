"""V92 fixed loaded measurement design. No simulator or outcome input.

All loaded measurements use the HIGH carry candidate (D1-D4, issue #219).
Floor grasp and intermediate arm poses are preparation only. Student adoption
still needs its own versioned loader/controller and rendered acceptance.
"""
from __future__ import annotations

import json

from harness.zone_final_pair_excitation import AXES, CLEARANCE, MAP_ID, prbs31

CHECK = 'calibration-loaded'
CAP_S = 720.
PERIOD_S = .05
ORBIT_RADIUS_M = .4732  # static half beam length .27 + v3 station radius .2032
FROZEN_LEVELS = (.006, .015, .025, .04)
LOW_LEVELS = (.001, .002, .004)
POSES = {
    'floor_grasp': {3: 1269, 4: 2052, 5: 2494, 6: 1500},
    'controller_hover': {3: 807, 4: 1897, 5: 2187, 6: 1500},
    'transition_110': {3: 891, 4: 2036, 5: 2054, 6: 1500},
    'transition_130': {3: 981, 4: 2152, 5: 1917, 6: 1500},
    'edge_view_150': {3: 896, 4: 2035, 5: 1894, 6: 1500},
}


def _segments(start, axis, levels, mode, pose):
    t, result = start, []

    def add(duration, value, phase, role):
        nonlocal t
        result.append({'start_s': t, 'duration_s': duration, 'axis': axis,
                       'value': value, 'phase': phase, 'mode': mode,
                       'pose': pose, 'analysis_role': role})
        t = round(t+duration, 8)

    for magnitude in levels:
        role = 'low_command_diagnostic' if magnitude in LOW_LEVELS else 'fit_steps'
        for sign in (1, -1):
            add(10., magnitude*sign, 'step', role)
            add(1., 0., 'coast', role)
    for bit in prbs31():
        add(.5, .015*bit, 'prbs', 'validate_prbs')
    add(2.5, 0., 'coast', 'validate_prbs')
    return t, result


def design(check=CHECK, map_id=MAP_ID):
    if check != CHECK or map_id != MAP_ID:
        raise ValueError('v92 requires loaded training collection on the two-door map')
    t, segments = 40., []
    for axis in AXES:
        levels = FROZEN_LEVELS if axis == 'turn' else (*LOW_LEVELS, *FROZEN_LEVELS)
        mode = 'common_orbit' if axis == 'turn' else 'world_translation'
        t, block = _segments(t, axis, levels, mode, 'edge_view_150')
        segments.extend(block)
    assert t == 490.
    end, pair = _segments(570., 'turn', FROZEN_LEVELS, 'relative_yaw', 'edge_view_150')
    assert end == 676.
    segments.extend(pair)
    # B-double-prime selects these half-open windows after eight seconds of
    # preparation. B-prime remains unchanged. All transition raw is retained.
    windows = [{'start_s': a, 'end_s': z, 'pose': pose, 'pan_pwm': pan,
                'purpose': purpose, 'requires_offline_lifted_bilateral_grip': True}
               for a, z, pose, pan, purpose in (
                   (32., 40., 'edge_view_150', 1500, 'high_extrinsics'),
                   (498., 506., 'edge_view_150', 1500, 'pan_center_reference'),
                   (514., 522., 'edge_view_150', 1480, 'pan_minus'),
                   (530., 538., 'edge_view_150', 1500, 'pan_center_reference'),
                   (546., 554., 'edge_view_150', 1520, 'pan_plus'),
                   (562., 570., 'edge_view_150', 1500, 'pan_center_reference'),
                   (684., 692., 'edge_view_150', 1500, 'high_return_extrinsics'))]
    return {'schema': 'ugrp.final_pair_loaded_measurement.v92', 'check': check,
            'map_id': map_id, 'basis': 'PR #359 f2fc0cc3d2315e8b4441028a1713a1ba5af23175',
            'control_period_s': PERIOD_S, 'eval_pose_period_s': PERIOD_S,
            'camera_period_s': .2, 'command_lease_s': PERIOD_S,
            'sim_cap_s': CAP_S, 'reset_cap_s': 5., 'total_including_reset_cap_s': CAP_S+5.,
            'clearance': dict(CLEARANCE), 'step_duration_s': 10.,
            'frozen_magnitudes': list(FROZEN_LEVELS), 'additional_translation_magnitudes': list(LOW_LEVELS),
            'prbs': {'polynomial': 'x^5+x^2+1', 'bits': prbs31(), 'chip_s': .5, 'magnitude': .015},
            'orbit_companion': {'left_per_turn': -ORBIT_RADIUS_M,
                'source': 'static formation radius only; raw commands, not calibrated SI velocity',
                'r2_rule': 'same turn AND same companion left; translations outside orbit are opposite'},
            'poses': {name: {str(k): v for k, v in pose.items()} for name, pose in POSES.items()},
            'camera_windows': windows, 'camera_warmup_s': 8.,
            'segments': segments,
            'loaded_pose_scope': {'measurement': ['edge_view_150'],
                'preparation_only': ['floor_grasp', 'controller_hover', 'transition_110', 'transition_130'],
                'student_adoption': 'D1/D2 require new loader/controller bundle and acceptance; no transfer to old student'},
            'qualification': 'COLLECTION DESIGN ONLY; B-double-prime frozen separately; v92 assembler pending; no promotion'}


def action_vector(segment, rid):
    if rid not in ('r1', 'r2'):
        raise ValueError('unknown carrier')
    value = segment['value']
    u = dict.fromkeys(AXES, 0.)
    if segment['mode'] == 'common_orbit':
        # Positive common yaw needs opposite WORLD tangent velocities. With
        # facing robots those are the SAME negative LOCAL left commands.
        u.update(left=round(-ORBIT_RADIUS_M*value, 10), turn=value)
    else:
        u[segment['axis']] = value*(-1 if rid == 'r2' else 1)
    return u


def schedule(check=CHECK):
    plan = design(check)
    visits = [(0., 'prepare_floor_grasp', {**POSES['floor_grasp'], 1: 2000}),
              (2., 'prepare_close', {1: 1500}), (4., 'prepare_controller_hover', POSES['controller_hover']),
              (16., 'prepare_transition_110', POSES['transition_110']),
              (20., 'prepare_transition_130', POSES['transition_130']),
              (24., 'prepare_edge_view_150', POSES['edge_view_150']),
              (506., 'high_pan_minus', {6: 1480}),
              (522., 'high_pan_center', {6: 1500}),
              (538., 'high_pan_plus', {6: 1520}),
              (554., 'high_pan_center_return', {6: 1500}),
              (700., 'post_measurement_lower', POSES['floor_grasp']),
              (714., 'post_measurement_open', {1: 2000})]
    events = []
    for t, phase, pose in visits:
        for rid in ('r1', 'r2'):
            for sid, pulse in pose.items():
                action = ({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                          {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
                events.append({'t': t, 'phase': phase, 'robot_id': rid, 'action': action})
    for segment in plan['segments']:
        for i in range(round(segment['duration_s']/PERIOD_S)):
            for rid in ('r1', 'r2'):
                events.append({'t': round(segment['start_s']+i*PERIOD_S, 8), 'robot_id': rid,
                    'phase': 'loaded_'+segment['mode']+'_'+segment['phase'],
                    'action': {'kind': 'mecanum', **action_vector(segment, rid), 'duration_s': PERIOD_S}})
    return sorted(events, key=lambda event: event['t'])


def schedule_bytes():
    """Exactly scripts.run_final_environment_checks.write's UTF-8 bytes."""
    return (json.dumps(schedule(), ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
