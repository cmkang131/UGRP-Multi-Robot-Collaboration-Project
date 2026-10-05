"""Loaded pair REST calibration acquisition contract (v104); a copy of the v102 contract with a rest-only program.

Purpose (#363 (가), coordinator decision 2026-10-05): decide ``params.motion_loaded.rest_noise`` by the SAME measured
rule the v101 unloaded calibration used (scripts/fit_unloaded_gain_calibration.py ``rest_rms`` + ``ACCEPT
['rest_noise_rms_m'] = 1 mm``: RMS of the model-free 1 s xy displacement over windows that start >= 5 stop lags after
the command went to zero). The v102 raw cannot host that rule (1.5 s coasts: 5 x 0.1004 s + 1 s does not fit), so each
run here is v92 preparation -> one short fit step (3 s, |u| 0.03) -> 12 s of explicit zero commands -> 3 s end hold.
Same world, contact profile, preparation, HIGH carry pose, port and guard as v102; only the program, seeds and IDs
differ. Ground truth is an offline calibration output only; it never reaches a command table or a student.
"""
from __future__ import annotations

import math

from harness import zone_final_pair_contract as pair
from harness import zone_final_pair_loaded_schedule as v92
from harness.zone_final_environment import ROOT, digest, local_path, read, sha
from sim.camera_robot_port import validate_raw_action

CONFIG = 'configs/final_pair_loaded_rest_v104.json'
WORKFLOW = 'configs/simulation_workflows.d/final_pair_loaded_rest_v104.json'
WORKFLOW_ID = 'zone-final-pair-loaded-restcal-v104'
WORKFLOW_VERSION = '1.0.0'
BUNDLE_ID = 'zone-final-pair-loaded-restcal-v104'
CHECK = 'calibration-loaded'          # keeps the v88 pair backend/guard code paths (check-gated) valid
MAP_ID = v92.MAP_ID
SCHEMA = 'ugrp.final_pair_loaded_rest.v104'
AXES = ('forward', 'left')            # turn is deferred: the recorded HIGH carry issues no turn command
RESERVED_SEEDS = (911, 1101, 1102, 1103, 1104, 1105, 1106, 1201, 1202, 1203, 1204)
HALF_PI = math.pi / 2

CONTROL_PERIOD_S = .1                 # live carry cadence ...
COMMAND_LEASE_S = .15                 # ... with a 0.15 s lease (recorded fcc5215f commands)
TICK_S = .05
PREP_END_S = 40.                      # v92 preparation (floor grasp -> edge_view_150) ends; motion starts here
STEP_S = 7.
COAST_S = 1.5
END_HOLD_S = 3.
REST_STEP = {'value': .03, 'duration_s': 3.}   # one short fit step so the rest starts from a real stop
REST_S = 12.                          # explicit zero commands: >= 5 stop lags + many 1 s windows
RESET_CAP_S = 5.

LEFT_FIT = (.0125, .020, .030, .050, .070, .100)
LEFT_HELD = (.025, .040, .085)
# Pair translation along r1 forward needs r2 = -u, and the port caps reverse forward at -0.05: |u| <= 0.05 is the
# operating range of pair forward translation. (Left is capped at +-0.10 for both carriers.)
FORWARD_FIT = (.0125, .020, .030, .050)
FORWARD_HELD = (.025, .040)
# Exact recorded fcc5215f command trains: 128 ticks (12.8 s) left -0.0622 and 133 ticks (13.3 s) forward +0.0443 at 0.1 s.
LEG = {'left': {'value': .0622, 'duration_s': 12.8}, 'forward': {'value': .0443, 'duration_s': 13.3}}
DURATION_SERIES = {'left': ((.030, (3., 12.)), (.070, (3., 9.))),
                   'forward': ((.030, (3., 12.)), (.050, (3., 8.)))}

# Nominal plant used ONLY to size return legs and to bound the excursion (NOT a fitted result). Affine static map
# v = g (|u| - u0) from the three v92 steady levels 0.015/0.025/0.04 (collinear to 1e-5 m/s), lag 0.97 s, stop lag 0.085 s.
NOMINAL = {'forward': {'g': 1.5709, 'u0': .00557}, 'left': {'g': 1.1746, 'u0': .00725},
           'tau_s': .97, 'tau_stop_s': .085}
CORNERS = {'gain_scale': (.85, 1.25), 'u0_scale': (0., 2.), 'tau_s': (.6, 1.6)}
EXCURSION_MARGIN_M = .10
RUNS = [
    {'id': 'restL', 'axis': 'left', 'seed': 1301, 'beam_xy_yaw': [3.55, -1.05, 0.], 'order': 'up', 'sign_first': 1},
    {'id': 'restF', 'axis': 'forward', 'seed': 1302, 'beam_xy_yaw': [3.80, -1.05, HALF_PI], 'order': 'up',
     'sign_first': 1},
]

def _seg(axis, phase, role, duration, value, level=None):
    return {'axis': axis, 'phase': phase, 'role': role, 'duration_s': float(duration), 'value': float(value),
            'level': None if level is None else float(level)}


def nominal_displacement(axis, value, duration, *, scale=1., u0_scale=1., tau=None, dt=.01, coast=COAST_S):
    """Along-axis displacement (m) of one step + coast under the nominal affine plant (design only)."""
    tau = NOMINAL['tau_s'] if tau is None else tau
    p = NOMINAL[axis]
    drive = math.copysign(max(abs(value) - p['u0'] * u0_scale, 0.), value) * p['g'] * scale
    v = x = 0.
    for _ in range(round(duration / dt)):
        v += (drive - v) / tau * dt
        x += v * dt
    for _ in range(round(coast / dt)):
        v += (0. - v) / NOMINAL['tau_stop_s'] * dt
        x += v * dt
    return x


def _pair(axis, level, role, sign_first, duration):
    out = []
    for sign in (sign_first, -sign_first):
        out += [_seg(axis, 'step', role, duration, sign * level, level), _seg(axis, 'coast', 'coast', COAST_S, 0.)]
    return out


def _levels(axis):
    fit, held = (LEFT_FIT, LEFT_HELD) if axis == 'left' else (FORWARD_FIT, FORWARD_HELD)
    return sorted([(u, 'fit') for u in fit] + [(u, 'heldout') for u in held])


def _program(run):
    """One fit step, then REST_S of explicit zero commands (role coast) for the v101 rest rule."""
    axis = run['axis']
    return [_seg(axis, 'step', 'fit', REST_STEP['duration_s'], run['sign_first'] * REST_STEP['value'],
                 REST_STEP['value']),
            _seg(axis, 'coast', 'coast', REST_S, 0.)]


def stations(beam_xy_yaw):
    """Carrier stations for a beam pose (x, y, yaw): the standard grasp offsets rotated into the beam frame."""
    from sim.zone_model_conventions import station_offset
    static = pair.resolve(MAP_ID)[0]
    x, y, psi = beam_xy_yaw
    out = {}
    for rid, role in zip(pair.ROBOTS, ('end_neg', 'end_pos')):
        dx, dy, oy = station_offset(static, 'long_beam', role)
        c, s = math.cos(psi), math.sin(psi)
        out[rid] = [x + c * dx - s * dy, y + s * dx + c * dy, oy + psi]
    return out


def build_plan(*, root=ROOT):
    runs = []
    for row in RUNS:
        segs = _program(row)
        motion = sum(s['duration_s'] for s in segs)
        cap = round(PREP_END_S + motion + END_HOLD_S, 6)
        runs.append(dict(row, segments=segs, motion_s=round(motion, 6), sim_cap_s=cap,
                         total_including_reset_cap_s=round(cap + RESET_CAP_S, 6)))
    return {'schema': SCHEMA, 'status': 'DEV_DIAGNOSTIC_COMMANDS', 'load_state': 'loaded_high_carry',
            'map_id': MAP_ID, 'axes': list(AXES), 'control_period_s': CONTROL_PERIOD_S,
            'command_lease_s': COMMAND_LEASE_S, 'eval_pose_period_s': TICK_S, 'prep_end_s': PREP_END_S,
            'step_s': STEP_S, 'coast_s': COAST_S, 'end_hold_s': END_HOLD_S,
            'reset_cap_s': RESET_CAP_S, 'images': 'none: no camera capture in this acquisition',
            'preparation': 'v92 floor grasp -> controller hover -> transition 110/130 -> edge_view_150 (HIGH carry), '
                           'identical servo visits; the beam must be lifted and rigid before PREP_END_S (offline gate)',
            'translation_convention': 'r1 = +u, r2 = -u (the pair translates along r1 forward/left; as v92 and fcc5215f)',
            'rest_program': {'step': REST_STEP, 'rest_s': REST_S,
                             'rule': 'v101 rest_rms (1 s windows from >= 5 stop lags after the zero command), 1 mm'},
            'nominal_design_plant': NOMINAL, 'excursion_corners': {k: list(v) for k, v in CORNERS.items()},
            'clearance': dict(v92.CLEARANCE), 'reserved_seeds': list(RESERVED_SEEDS), 'runs': runs}


def _controls(run):
    """Per control tick (0.1 s) value of the active segment (0 outside) for the motion window."""
    values = []
    for seg in run['segments']:
        values += [seg['value']] * round(seg['duration_s'] / CONTROL_PERIOD_S)
    return values


def action_for(run, rid, k):
    """Fixed lease from the pre-authored table; no pose, contact, success or teacher argument."""
    values = _controls(run)
    u = values[k] if k < len(values) else 0.
    action = {'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': 0., 'duration_s': COMMAND_LEASE_S}
    action[run['axis']] = round(u * (-1 if rid == 'r2' else 1), 9)
    return action


def prep_events():
    """The v92 preparation servo visits (same poses and times), without the pan/camera windows."""
    visits = [(0., 'prepare_floor_grasp', {**v92.POSES['floor_grasp'], 1: 2000}),
              (2., 'prepare_close', {1: 1500}), (4., 'prepare_controller_hover', v92.POSES['controller_hover']),
              (16., 'prepare_transition_110', v92.POSES['transition_110']),
              (20., 'prepare_transition_130', v92.POSES['transition_130']),
              (24., 'prepare_edge_view_150', v92.POSES['edge_view_150'])]
    events = []
    for t, phase, pose in visits:
        for rid in pair.ROBOTS:
            for sid, pulse in pose.items():
                action = ({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                          {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
                events.append({'t': t, 'phase': phase, 'robot_id': rid, 'action': action})
    return events


def events(run):
    out = prep_events()
    values = _controls(run)
    roles = []
    for seg in run['segments']:
        roles += [seg['phase']] * round(seg['duration_s'] / CONTROL_PERIOD_S)
    for k in range(len(values)):
        for rid in pair.ROBOTS:
            out.append({'t': round(PREP_END_S + k * CONTROL_PERIOD_S, 8), 'robot_id': rid,
                        'phase': f'loaded_gain_{roles[k]}', 'action': action_for(run, rid, k)})
    return sorted(out, key=lambda e: e['t'])


def run_row(plan, run_id):
    rows = [r for r in plan['runs'] if r['id'] == run_id]
    if len(rows) != 1:
        raise ValueError(f'unknown run id: {run_id}')
    return rows[0]


def segment_times(run):
    """(start_s, end_s) of every segment relative to the motion start (PREP_END_S), for offline scoring."""
    t, out = 0., []
    for seg in run['segments']:
        out.append((round(t, 8), round(t + seg['duration_s'], 8)))
        t += seg['duration_s']
    return out


def excursion(run, *, scale=1., u0_scale=1., tau=None):
    """(min, max) along-axis displacement over the whole program under one plant corner (design bound)."""
    x, lo, hi = 0., 0., 0.
    for seg in run['segments']:
        x += nominal_displacement(run['axis'], seg['value'], seg['duration_s'], scale=scale, u0_scale=u0_scale,
                                  tau=tau, coast=0.) if seg['phase'] != 'coast' else 0.
        lo, hi = min(lo, x), max(hi, x)
    return lo, hi


def free_travel(static, beam_xy_yaw, direction, *, step=.02, limit=5.):
    """Distance the pair can shift along ``direction`` before a conservative disc (carriers .40+.30, beam) hits a wall."""
    from harness.final_environment_measurement_v2 import clearance
    from sim.zone_cargo import CATALOGUE
    half = CATALOGUE['long_beam'].landing_half_extents_m
    beam_r = math.hypot(*half) + .30
    st = stations(beam_xy_yaw)
    ux, uy = direction
    d = 0.
    while d < limit:
        pts = [(s[0] + ux * d, s[1] + uy * d, .70) for s in st.values()]
        pts.append((beam_xy_yaw[0] + ux * d, beam_xy_yaw[1] + uy * d, beam_r))
        if any(clearance(static, (x, y), r) <= 0 for x, y, r in pts):
            break
        d += step
    return round(d - step, 6)


def corner_excursions(run):
    out = []
    for scale in CORNERS['gain_scale']:
        for u0 in CORNERS['u0_scale']:
            for tau in CORNERS['tau_s']:
                out.append(((scale, u0, tau), excursion(run, scale=scale, u0_scale=u0, tau=tau)))
    return out


def preflight(plan, *, root=ROOT):
    """Static start gate (v92 rules) + nominal-plant corner excursion vs conservative free travel; advisory bound."""
    from harness.zone_final_pair_clearance import start_pose_check
    from sim.zone_cargo import CATALOGUE
    static = pair.resolve(MAP_ID)[0]
    report = {}
    for run in plan['runs']:
        beam = {'pose': run['beam_xy_yaw'], 'half_extents_m': CATALOGUE['long_beam'].landing_half_extents_m}
        start = start_pose_check(static, stations(run['beam_xy_yaw']), beam=beam)
        c, s = math.cos(run['beam_xy_yaw'][2]), math.sin(run['beam_xy_yaw'][2])
        axis_dir = (c, s) if run['axis'] == 'forward' else (-s, c)         # r1 forward / left in the world
        pos, neg = (free_travel(static, run['beam_xy_yaw'], axis_dir),
                    free_travel(static, run['beam_xy_yaw'], (-axis_dir[0], -axis_dir[1])))
        corners = corner_excursions(run)
        lo, hi = min(e[0] for _, e in corners), max(e[1] for _, e in corners)
        report[run['id']] = {'start_pose_check': start, 'free_travel_pos_m': pos, 'free_travel_neg_m': neg,
                             'corner_excursion_min_m': lo, 'corner_excursion_max_m': hi,
                             'admitted': bool(start['admitted'] and hi + EXCURSION_MARGIN_M <= pos
                                              and -lo + EXCURSION_MARGIN_M <= neg)}
    return report


def validate(plan, *, root=ROOT, for_execution=True):
    expected = build_plan(root=root)
    if plan != expected:
        raise ValueError('loaded rest v104 contract changed: plan differs from the registered generator')
    if (len({r['id'] for r in plan['runs']}) != len(plan['runs'])
            or len({r['seed'] for r in plan['runs']}) != len(plan['runs'])
            or any(r['seed'] in RESERVED_SEEDS for r in plan['runs'])):
        raise ValueError('run ids/seeds must be unique and outside the reserved v89/v92/v98/v101/v102 seeds')
    if any(r['beam_xy_yaw'][:2] == [3.55, -.85] for r in plan['runs']):
        raise ValueError('v92 beam start reused')
    for run in plan['runs']:
        for e in events(run):
            validate_raw_action(e['action'], allow_reverse=True, allow_mecanum=True)
        if run['sim_cap_s'] + RESET_CAP_S != run['total_including_reset_cap_s']:
            raise ValueError('cap arithmetic')
    report = preflight(plan, root=root)
    if for_execution and not all(v['admitted'] for v in report.values()):
        raise ValueError('PREFLIGHT_CLEARANCE_REJECTED: ' + ', '.join(k for k, v in report.items() if not v['admitted']))
    return report


def protocol(*, root=ROOT):
    plan = read(local_path(CONFIG, root=root))
    validate(plan, root=root, for_execution=False)
    return plan


def bundle(run_id, *, root=ROOT):
    from harness.python_source_closure import source_closure
    plan = protocol(root=root)
    run = run_row(plan, run_id)
    ancestor = pair.bundle(MAP_ID, CHECK)
    paths = [CONFIG, WORKFLOW, 'harness/final_pair_loaded_rest_v104.py', 'scripts/run_final_pair_loaded_rest_v104.py',
             'sim/final_pair_loaded_rest_v104.py']
    files = set(source_closure(root, paths)) | set(paths) | set(ancestor['source_sha256'])
    value = dict(ancestor)
    value.update(schema='ugrp.final_pair_bundle.v104', execution_bundle_id=BUNDLE_ID, workflow_id=WORKFLOW_ID,
                 workflow_version=WORKFLOW_VERSION, check=CHECK, run_id=run_id, seed=run['seed'],
                 collection_role='CALIBRATION_TRAINING', training_eligible=True, teacher_only=True,
                 controller_family='teacher_fixed_schedule', controller_variant='v104-loaded-rest',
                 controller_inputs=[], measurement=plan, measurement_sha256=sha(local_path(CONFIG, root=root)),
                 caps={'reset_per_case_s': RESET_CAP_S, 'per_case_s': run['sim_cap_s'], 'default_cases': 1,
                       'total_including_reset_s': run['total_including_reset_cap_s']},
                 clearance_preflight=validate(plan, root=root, for_execution=False),
                 parent_execution_bundle_id=pair.BUNDLE_ID, parent_bundle_sha256=digest(ancestor),
                 revision='v104 loaded rest collection (copy of v102 with a rest-only program); v92 preparation and HIGH carry pose; no camera capture',
                 calibration_selection='none: raw teacher collection, offline fit only',
                 source_sha256={p: sha(local_path(p, root=root)) for p in sorted(files)})
    value['runnable'] = all(v['admitted'] for v in value['clearance_preflight'].values())
    return value
