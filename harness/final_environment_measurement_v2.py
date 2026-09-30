"""Static v89 unloaded motion acquisition contract; no physics imports."""
from __future__ import annotations

import math

from harness import zone_final_environment_floor_light as parent
from harness.zone_final_environment import ROOT, digest, local_path, read, sha
from sim.camera_robot_port import validate_raw_action

CONFIG = 'configs/final_environment_measurement_v2.json'
WORKFLOW = 'configs/simulation_workflows.d/final_environment_measurement_v89.json'
WORKFLOW_ID = 'zone-final-environment-floor-light-v2-check'
WORKFLOW_VERSION = '2.21.0'
BUNDLE_ID = 'zone-final-environment-v89'
CHECK = 'calibration-motion-v2'
MAP_ID = 'zone_wide_two_doors_final_v3'


def rectangles(static):
    """Reject unsupported geometry instead of treating it as free space."""
    bounds = static['bounds_m']
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError('invalid static bounds')
    if bounds[0] >= bounds[1] or bounds[2] >= bounds[3] or static.get('terrain'):
        raise ValueError('unsupported floor geometry')
    result = []
    if not static['obstacles']:
        raise ValueError('missing static walls')
    for obstacle in static['obstacles']:
        if obstacle.get('kind') != 'wall' or obstacle.get('yaw_rad', 0) != 0:
            raise ValueError('unsupported static obstacle')
        x, y = obstacle['center_m']
        hx, hy = obstacle['half_extents_m']
        if not all(math.isfinite(v) for v in (x, y, hx, hy)) or min(hx, hy) <= 0:
            raise ValueError('invalid static obstacle')
        result.append((x - hx, x + hx, y - hy, y + hy))
    return result


def free_floor_area(static):
    """Exact union of clipped, axis-aligned wall rectangles (square metres)."""
    x0, x1, y0, y1 = static['bounds_m']
    rects = [(max(x0, a), min(x1, b), max(y0, c), min(y1, d)) for a, b, c, d in rectangles(static)]
    rects = [r for r in rects if r[0] < r[1] and r[2] < r[3]]
    xs = sorted({x0, x1, *(v for r in rects for v in r[:2])})
    blocked = 0.
    for a, b in zip(xs, xs[1:]):
        intervals = sorted((c, d) for l, r, c, d in rects if l < (a + b) / 2 < r)
        end, height = y0, 0.
        for c, d in intervals:
            height += max(0., d - max(c, end))
            end = max(end, d)
        blocked += (b - a) * height
    return (x1 - x0) * (y1 - y0) - blocked


def clearance(static, xy, radius):
    """Distance from a conservative robot disc to walls and map boundary."""
    x, y = xy
    if not all(math.isfinite(v) for v in (x, y, radius)) or radius <= 0:
        raise ValueError('missing/non-finite clearance measurement')
    x0, x1, y0, y1 = static['bounds_m']
    distances = [x - x0, x1 - x, y - y0, y1 - y]
    for a, b, c, d in rectangles(static):
        distances.append(math.hypot(max(a - x, 0., x - b), max(c - y, 0., y - d)))
    return min(distances) - radius


def require_clearance(static, xy, plan):
    safety = plan['clearance']
    gap = clearance(static, xy, safety['robot_radius_bound_m'])
    if gap < safety['minimum_m'] + safety['abort_buffer_m'] - 1e-10:
        raise ValueError('CLEARANCE_ABORT: static-map wall margin not available')
    return gap


def action_at(plan, step):
    """Fixed 50 ms leases; no pose, contact, success or teacher argument."""
    t = step * plan['control_period_s'] - plan['initial_hold_s']
    action = {'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': 0.,
              'duration_s': plan['command_lease_s']}
    for segment in plan['segments']:
        if -1e-8 <= t < segment['duration_s'] - 1e-8:
            action[segment['axis']] = segment['value']
            break
        t -= segment['duration_s']
    return action


def validate(plan, *, root=ROOT):
    # Reject widened caps/limits/sampling and arbitrary command schedules.
    expected = {'schema': 'ugrp.final_environment_measurement.v2', 'status': 'DRAFT_DIAGNOSTIC_COMMANDS',
                'robot_id': 'r1', 'load_state': 'unloaded', 'map_id': MAP_ID,
                'axes': ['forward', 'left'], 'control_period_s': .05, 'eval_pose_period_s': .05,
                'camera_period_s': 5., 'reset_cap_s': 5., 'initial_hold_s': 2.,
                'sim_cap_s': 230., 'total_including_reset_cap_s': 235., 'command_lease_s': .05,
                'spawn_xy_yaw': [3.25, -.85, 0.], 'magnitudes': [.01, .02, .03],
                'step_duration_s': 15., 'max_design_drive_tau_s': 3.,
                'design_drive_tau_s': {'forward': 1.44, 'left': 3.},
                'clearance': {'minimum_m': .3, 'abort_buffer_m': .05, 'robot_radius_bound_m': .35,
                              'max_substep_displacement_m': .01}}
    if any(plan.get(k) != v for k, v in expected.items()):
        raise ValueError('measurement v2 contract changed: caps/sampling/clearance/identity')
    bits = [1] * 5
    for i in range(26):
        bits.append(bits[i + 2] ^ bits[i])
    bits = [2 * b - 1 for b in bits]
    if plan['prbs'] != {'polynomial': 'x^5+x^2+1', 'initial_bits': [1] * 5,
                        'bits': bits, 'chip_s': .5, 'magnitude': .02}:
        raise ValueError('PRBS differs from fixed excitation')
    expected_segments = []
    for axis in plan['axes']:
        for magnitude in plan['magnitudes']:
            for sign in (1, -1):
                expected_segments += [{'axis': axis, 'duration_s': 15., 'value': magnitude * sign, 'phase': 'step'},
                                      {'axis': axis, 'duration_s': 1., 'value': 0., 'phase': 'coast'}]
        expected_segments += [{'axis': axis, 'duration_s': .5, 'value': .02 * b, 'phase': 'prbs'} for b in bits]
        expected_segments.append({'axis': axis, 'duration_s': 2.5, 'value': 0., 'phase': 'coast'})
    if plan['segments'] != expected_segments:
        raise ValueError('measurement segments differ from validated design')
    duration = sum(s['duration_s'] for s in plan['segments']) + plan['initial_hold_s']
    if duration != plan['sim_cap_s'] or duration + plan['reset_cap_s'] > 240:
        raise ValueError('total SIM cap exceeded')
    if any(plan['eval_pose_period_s'] > tau / 10 for tau in plan['design_drive_tau_s'].values()):
        raise ValueError('pose sampling too slow for design drive tau')
    for i in range(round(duration / plan['control_period_s'])):
        validate_raw_action(action_at(plan, i), allow_reverse=True, allow_mecanum=True)
    maps = {mid: parent.resolve(mid, root=root)[0] for mid in parent.registry(root=root)['maps']}
    areas = {mid: free_floor_area(m) for mid, m in maps.items()}
    if max(areas, key=areas.get) != MAP_ID:
        raise ValueError('selected map no longer has most free floor')
    start_clearance = require_clearance(maps[MAP_ID], plan['spawn_xy_yaw'][:2], plan)
    return {'free_floor_area_m2': areas, 'spawn_wall_clearance_m': start_clearance,
            'pose_samples_including_initial': round(duration / .05) + 1}


def protocol(*, root=ROOT):
    plan = read(local_path(CONFIG, root=root))
    validate(plan, root=root)
    return plan


def bundle(*, root=ROOT):
    from harness.python_source_closure import source_closure
    plan = protocol(root=root)
    ancestor = parent.bundle(MAP_ID, check='calibration', root=root)
    paths = [CONFIG, WORKFLOW, 'harness/final_environment_measurement_v2.py',
             'scripts/run_final_environment_measurement_v2.py', 'sim/final_environment_measurement_v2.py']
    files = set(source_closure(root, paths)) | set(paths) | set(ancestor['source_sha256'])
    value = dict(ancestor)
    value.update(schema='ugrp.final_environment_bundle.v89', execution_bundle_id=BUNDLE_ID,
                 workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, check=CHECK,
                 caps={'cases': 1, 'per_case_sim_cap_s': 230., 'total_sim_cap_s': 230.,
                       'total_including_reset_cap_s': 235., 'student_control': False},
                 parent_execution_bundle_id=parent.BUNDLE_ID, parent_bundle_sha256=digest(ancestor),
                 measurement=plan, measurement_sha256=sha(local_path(CONFIG, root=root)),
                 clearance_preflight=validate(plan, root=root), controller_inputs=[],
                 source_sha256={p: sha(local_path(p, root=root)) for p in sorted(files)})
    return value
