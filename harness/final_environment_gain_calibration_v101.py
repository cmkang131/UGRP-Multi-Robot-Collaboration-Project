"""Static unloaded gain/lag calibration acquisition contract (v101); no physics imports.

Purpose (Borenstein & Feng 1996, "measure the systematic error, then correct it in the model"): measure the unloaded
steady-state gain and time constants of the plant at the command amplitudes the approach actually uses, for
forward / left / turn, from SELF-ISSUED open-loop commands and SIM ground-truth displacement. The ground truth is an
offline calibration output only (like the registered r4/r5 measured noise); it never reaches a command scheduler,
a provider or a student. Every command is a pre-authored table; the physics owner may only ABORT.

Separate from the v89 collection (seed 911, spawn (3.25, -0.85, yaw 0), amplitudes <= 0.03) and from the recorded v98
probe (other map, seeds, starts): different seeds, different starts, different amplitudes.
"""
from __future__ import annotations

import math

from harness import zone_final_environment_floor_light as parent
from harness.zone_final_environment import ROOT, digest, local_path, read, sha
from harness.final_environment_measurement_v2 import clearance, rectangles, require_clearance
from sim.camera_robot_port import validate_raw_action

CONFIG = 'configs/final_environment_gain_calibration_v101.json'
INPUTS = 'configs/final_environment_gain_calibration_v101_inputs.json'
WORKFLOW = 'configs/simulation_workflows.d/final_environment_gain_calibration_v101.json'
WORKFLOW_ID = 'zone-final-environment-gaincal-v101'
WORKFLOW_VERSION = '1.0.0'
BUNDLE_ID = 'zone-final-environment-gaincal-v101'
CHECK = 'calibration-gain-v101'
MAP_ID = 'zone_wide_two_doors_final_v3'
SCHEMA = 'ugrp.final_environment_gain_calibration.v101'
AXES = ('forward', 'left', 'turn')

CONTROL_PERIOD_S = .1       # live cadence: a new command every 0.10 s ...
COMMAND_LEASE_S = .15       # ... with a 0.15 s lease
EVAL_POSE_PERIOD_S = .05
INITIAL_HOLD_S = 1.5
STEP_S = 4.
COAST_S = 1.5
RESET_CAP_S = 5.
HALF_PI = math.pi / 2

FIT_LEVELS = {'forward': [.03, .06, .09, .12], 'left': [.02, .04, .06, .08], 'turn': [.02, .05, .08, .10]}
HELD_LEVELS = {'forward': [.045, .075, .105], 'left': [.03, .05, .07], 'turn': [.035, .065, .09]}

# Held-out mixed-axis, live-like segments (fixed bytes; 4 s each, linear ramps between start and end).
# (forward, left, turn) start -> end.
MIXED = [((.10, -.04, .0), (.10, -.04, .0)),
         ((.06, .05, -.03), (.06, .05, -.03)),
         ((.0, -.06, .08), (.0, -.06, .08)),
         ((.0, .03, -.10), (.0, .03, -.10)),
         ((.12, .02, .02), (.04, .07, -.02)),
         ((.0, -.08, -.05), (.0, .0, .05)),
         ((.0, .0, .05), (.0, .0, .05)),
         ((.04, -.05, -.02), (.10, .03, -.06))]

# Run table. Starts are in the EMPTY east room (r2/r3/cargo sit in the west room), chosen by the static corner
# preflight below; none equals the v89 spawn or a recorded probe start. Seeds differ from 911.
RUNS = [
    {'id': 'fitA1', 'role': 'fit', 'seed': 1101, 'spawn_xy_yaw': [3.775, -2.3, HALF_PI], 'program': 'blocks_up'},
    {'id': 'fitA2', 'role': 'fit', 'seed': 1102, 'spawn_xy_yaw': [3.8, .6, -HALF_PI], 'program': 'blocks_down'},
    {'id': 'heldA3', 'role': 'heldout', 'seed': 1103, 'spawn_xy_yaw': [3.6, -2.3, HALF_PI], 'program': 'blocks_held'},
    {'id': 'heldM1', 'role': 'heldout', 'seed': 1104, 'spawn_xy_yaw': [3.95, .6, -HALF_PI], 'program': 'mixed'},
    {'id': 'heldP1', 'role': 'heldout', 'seed': 1105, 'spawn_xy_yaw': [3.3, -2.3, HALF_PI], 'program': 'replay_r1'},
    {'id': 'heldP2', 'role': 'heldout', 'seed': 1106, 'spawn_xy_yaw': [3.5, -2.3, HALF_PI], 'program': 'replay_r2'},
]

# Independent dev bounds for the static preflight (NOT a safety guarantee; the physics-owner abort is the interlock).
# Evidence: v89 deadband fit (forward 1.576, lateral 1.180 effective gain), r5 rotate 1.0725, DEV code default 1.40
# for turn; upper bounds are 1.3x the largest measured value (turn: the 1.40 code default x 1.3), lower bounds about
# half the smallest. Yaw drift allowance 0.05 rad covers the unmodelled cross-coupling.
CORNER_BOUNDS = {'gain_lo': [.8, .6, .5], 'gain_hi': [2.05, 1.55, 1.8], 'tau_drive_s': [.1, 1.6], 'tau_stop_s': .1,
                 'initial_yaw_error_rad': .05}
CORNER_EVIDENCE = {
    'experiments/2026-10-01-calib-motion-v89-physics/fit_check_output.txt': None,   # filled in config (sha)
    'experiments/2026-10-03-critb-rotation/calibration_candidate_r5_yaw.json':
        '978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97'}
PREFLIGHT_MARGIN_M = .10


def _seg(axis, phase, duration, start, end=None):
    return {'axis': axis, 'phase': phase, 'duration_s': float(duration),
            'start': [float(v) for v in start], 'end': [float(v) for v in (start if end is None else end)]}


def _unit(axis, value):
    v = [0., 0., 0.]
    v[AXES.index(axis)] = float(value)
    return v


def _blocks(levels, *, forward_order, pair_order, sign_first):
    segs = []
    f = FIT_LEVELS['forward'] if levels is FIT_LEVELS else HELD_LEVELS['forward']
    for u in (f if forward_order == 'up' else f[::-1]):
        segs += [_seg('forward', 'step', STEP_S, _unit('forward', u)), _seg('forward', 'coast', COAST_S, [0, 0, 0])]
    for axis in ('left', 'turn'):
        lv = levels[axis]
        for u in (lv if pair_order == 'up' else lv[::-1]):
            for s in sign_first:
                segs += [_seg(axis, 'step', STEP_S, _unit(axis, s * u)), _seg(axis, 'coast', COAST_S, [0, 0, 0])]
    return segs


def _program(name, inputs):
    if name == 'blocks_up':
        return _blocks(FIT_LEVELS, forward_order='up', pair_order='up', sign_first=(1, -1))
    if name == 'blocks_down':
        return _blocks(FIT_LEVELS, forward_order='down', pair_order='down', sign_first=(-1, 1))
    if name == 'blocks_held':
        return _blocks(HELD_LEVELS, forward_order='up', pair_order='up', sign_first=(1, -1))
    if name == 'mixed':
        segs = []
        for a, b in MIXED:
            segs += [_seg('mixed', 'mixed', STEP_S, a, b), _seg('mixed', 'coast', COAST_S, [0, 0, 0])]
        return segs
    if name in ('replay_r1', 'replay_r2'):
        leg = inputs['replay_legs'][name[-2:]]
        dt = leg['grid_dt_s']
        segs = [_seg('replay', 'replay', dt, c) for c in leg['commands']]
        return segs + [_seg('replay', 'coast', 3., [0, 0, 0])]
    raise ValueError(f'unknown program: {name}')


def build_plan(*, root=ROOT):
    """Deterministic plan; the committed config must equal it byte for byte (a changed generator is detected)."""
    inputs = read(local_path(INPUTS, root=root))
    runs = []
    for row in RUNS:
        segs = _program(row['program'], inputs)
        duration = INITIAL_HOLD_S + sum(s['duration_s'] for s in segs)
        runs.append(dict(row, segments=segs, sim_cap_s=round(duration, 6),
                         total_including_reset_cap_s=round(duration + RESET_CAP_S, 6)))
    evidence = dict(CORNER_EVIDENCE)
    evidence['experiments/2026-10-01-calib-motion-v89-physics/fit_check_output.txt'] = sha(
        local_path('experiments/2026-10-01-calib-motion-v89-physics/fit_check_output.txt', root=root))
    return {'schema': SCHEMA, 'status': 'DEV_DIAGNOSTIC_COMMANDS', 'robot_id': 'r1', 'load_state': 'unloaded',
            'map_id': MAP_ID, 'axes': list(AXES), 'control_period_s': CONTROL_PERIOD_S,
            'command_lease_s': COMMAND_LEASE_S, 'eval_pose_period_s': EVAL_POSE_PERIOD_S,
            'initial_hold_s': INITIAL_HOLD_S, 'reset_cap_s': RESET_CAP_S, 'step_s': STEP_S, 'coast_s': COAST_S,
            'images': 'none: no camera capture in this acquisition',
            'arm_pose': 'standard reset servo pulses 1:2000 3:740 4:2320 5:1320 pan 1500 (same as the v98 probe '
                        'while driving unloaded)',
            'fit_levels': FIT_LEVELS, 'heldout_levels': HELD_LEVELS,
            'clearance': {'minimum_m': .3, 'abort_buffer_m': .05, 'robot_radius_bound_m': .35,
                          'max_substep_displacement_m': .01},
            'preflight': {'margin_m': PREFLIGHT_MARGIN_M, 'corner_bounds': CORNER_BOUNDS,
                          'corner_evidence_sha256': evidence},
            'inputs_sha256': sha(local_path(INPUTS, root=root)),
            'runs': runs}


def action_at(run, step, plan):
    """Fixed leases from a pre-authored table; no pose, contact, success or teacher argument."""
    t = step * plan['control_period_s'] - plan['initial_hold_s']
    action = {'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': 0., 'duration_s': plan['command_lease_s']}
    for seg in run['segments']:
        d = seg['duration_s']
        if -1e-8 <= t < d - 1e-8:
            frac = 0. if d <= 0 else max(0., t) / d
            for i, axis in enumerate(AXES):
                action[axis] = round(seg['start'][i] + (seg['end'][i] - seg['start'][i]) * frac, 9)
            return action
        t -= d
    return action


def command_table(run, plan):
    """Pre-authored command per control step as an (n, 3) array (forward, left, turn)."""
    import numpy as np
    n = round(run['sim_cap_s'] / plan['control_period_s'])
    table = np.zeros((n, 3))
    for i in range(n):
        a = action_at(run, i, plan)
        table[i] = [a['forward'], a['left'], a['turn']]
    return table


def corner_paths(run, plan, table=None, *, dt=.05):
    """Open-loop PF-form plant over every bound corner at once; returns xs, ys of shape (corners, steps + 1)."""
    import itertools
    import numpy as np
    b = plan['preflight']['corner_bounds']
    table = command_table(run, plan) if table is None else table
    corners = [(np.array(g), tau, ye) for g in itertools.product(*zip(b['gain_lo'], b['gain_hi']))
               for tau in b['tau_drive_s'] for ye in (-b['initial_yaw_error_rad'], b['initial_yaw_error_rad'])]
    gain = np.array([c[0] for c in corners])                      # (C, 3)
    alpha_drive = 1. - np.exp(-dt / np.array([c[1] for c in corners]))
    alpha_stop = 1. - math.exp(-dt / b['tau_stop_s'])
    n = round(run['sim_cap_s'] / dt)
    per = round(plan['control_period_s'] / dt)
    x = np.full(len(corners), run['spawn_xy_yaw'][0])
    y = np.full(len(corners), run['spawn_xy_yaw'][1])
    yaw = run['spawn_xy_yaw'][2] + np.array([c[2] for c in corners])
    vel = np.zeros((len(corners), 3))
    xs, ys = np.empty((len(corners), n + 1)), np.empty((len(corners), n + 1))
    xs[:, 0], ys[:, 0] = x, y
    for k in range(n):
        u = table[min(k // per, len(table) - 1)]
        alpha = (alpha_drive if np.any(u) else np.full(len(corners), alpha_stop))[:, None]
        vel = vel + alpha * (gain * u - vel)
        c, s = np.cos(yaw), np.sin(yaw)
        x = x + (c * vel[:, 0] - s * vel[:, 1]) * dt
        y = y + (s * vel[:, 0] + c * vel[:, 1]) * dt
        yaw = yaw + vel[:, 2] * dt
        xs[:, k + 1], ys[:, k + 1] = x, y
    return xs, ys, corners


def corner_clearance(static, run, plan, table=None):
    """Smallest predicted wall clearance (disc radius subtracted) over every bound corner of the plant."""
    import numpy as np
    xs, ys, corners = corner_paths(run, plan, table)
    x0, x1, y0, y1 = static['bounds_m']
    d = np.minimum.reduce([xs - x0, x1 - xs, ys - y0, y1 - ys])
    for a, c, e, f in rectangles(static):
        d = np.minimum(d, np.hypot(np.maximum(np.maximum(a - xs, 0.), xs - c), np.maximum(np.maximum(e - ys, 0.), ys - f)))
    per_corner = d.min(axis=1) - plan['clearance']['robot_radius_bound_m']
    i = int(np.argmin(per_corner))
    gain, tau, ye = corners[i]
    return float(per_corner[i]), {'gain': [float(v) for v in gain], 'tau_drive_s': float(tau), 'yaw_error_rad': float(ye)}


def other_objects_clear(setup, run, plan):
    """Margin from every bounded corner path point to r2/r3/cargo, minus the disc radius (east room is empty)."""
    import numpy as np
    xs, ys, _ = corner_paths(run, plan)
    pts = np.column_stack((xs.ravel(), ys.ravel()))
    others = [v[:2] for k, v in setup['spawns'].items() if k != 'r1']
    others += [o['position_m'][:2] for o in setup.get('objects', {}).values()]
    nearest = min(float(np.min(np.linalg.norm(pts - np.asarray(o), axis=1))) for o in others)
    return nearest - plan['clearance']['robot_radius_bound_m']


def validate(plan, *, root=ROOT, for_execution=True):
    expected = build_plan(root=root)
    if plan != expected:
        raise ValueError('gain calibration v101 contract changed: plan differs from the registered generator')
    if len({r['id'] for r in plan['runs']}) != len(plan['runs']) or any(r['seed'] == 911 for r in plan['runs']):
        raise ValueError('run ids must be unique and seed 911 (v89/probe) is reserved')
    if any(abs(r['spawn_xy_yaw'][0] - 3.25) < 1e-9 and abs(r['spawn_xy_yaw'][1] + .85) < 1e-9 for r in plan['runs']):
        raise ValueError('v89 spawn reused')
    maps = {mid: parent.resolve(mid, root=root)[0] for mid in parent.registry(root=root)['maps']}
    static = maps[MAP_ID]
    report = {}
    for run in plan['runs']:
        for i in range(round(run['sim_cap_s'] / plan['control_period_s'])):
            validate_raw_action(action_at(run, i, plan), allow_reverse=True, allow_mecanum=True)
        start = require_clearance(static, run['spawn_xy_yaw'][:2], plan)
        worst, where = corner_clearance(static, run, plan)
        report[run['id']] = {'start_clearance_m': start, 'predicted_min_clearance_m': worst, 'worst_corner': where,
                             'admitted': worst >= plan['clearance']['minimum_m'] + plan['clearance']['abort_buffer_m']
                             + plan['preflight']['margin_m']}
        if for_execution and not report[run['id']]['admitted']:
            raise ValueError(f"PREFLIGHT_CLEARANCE_REJECTED: {run['id']}")
    return report


def protocol(*, root=ROOT):
    plan = read(local_path(CONFIG, root=root))
    validate(plan, root=root, for_execution=False)
    return plan


def run_row(plan, run_id):
    rows = [r for r in plan['runs'] if r['id'] == run_id]
    if len(rows) != 1:
        raise ValueError(f'unknown run id: {run_id}')
    return rows[0]


def bundle(run_id, *, root=ROOT):
    from harness.python_source_closure import source_closure
    plan = protocol(root=root)
    run_row(plan, run_id)
    ancestor = parent.bundle(MAP_ID, check='calibration', root=root)
    paths = [CONFIG, INPUTS, WORKFLOW, 'harness/final_environment_gain_calibration_v101.py',
             'scripts/run_final_environment_gain_calibration_v101.py', 'sim/final_environment_gain_calibration_v101.py']
    files = set(source_closure(root, paths)) | set(paths) | set(ancestor['source_sha256'])
    value = dict(ancestor)
    run = run_row(plan, run_id)
    value.update(schema='ugrp.final_environment_bundle.v101', execution_bundle_id=BUNDLE_ID,
                 workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, check=CHECK, run_id=run_id,
                 caps={'cases': 1, 'per_case_sim_cap_s': run['sim_cap_s'], 'total_sim_cap_s': run['sim_cap_s'],
                       'total_including_reset_cap_s': run['total_including_reset_cap_s'], 'student_control': False},
                 parent_execution_bundle_id=parent.BUNDLE_ID, parent_bundle_sha256=digest(ancestor),
                 measurement=plan, measurement_sha256=sha(local_path(CONFIG, root=root)),
                 clearance_preflight=validate(plan, root=root, for_execution=False), controller_inputs=[],
                 source_sha256={p: sha(local_path(p, root=root)) for p in sorted(files)})
    value['runnable'] = all(v['admitted'] for v in value['clearance_preflight'].values())
    return value
