"""V95 teacher-only acquisition: new starts and signed excitation of BOTH robots.

V88/89/91, criterion B and the r4/r5 candidates stay byte-identical. No fitted
candidate is a runtime input. This schedule preserves the training family and
levels, with a new order, PRBS phase and independent authored world starts.
"""
from __future__ import annotations

import copy

from harness import zone_final_pair_contract as previous
from harness.zone_final_pair_excitation import design as training_design, AXES, PERIOD_S
from harness.zone_final_pair_calibration import schedule as training_schedule

BUNDLE_ID = 'zone-final-pair-v95'
WORKFLOW_ID = 'zone-final-pair-heldout-v95'
WORKFLOW_VERSION = '3.7.0'
REGISTRY = 'configs/zone_final_pair_v95.json'
WORKFLOW = 'configs/simulation_workflows.d/final_pair_v95.json'
CHECK = 'calibration-unloaded'
MAPS = ('zone_wide_door_geometry_v3', 'zone_wide_corridor_final_v3')
ROBOTS = ('r1', 'r2')
SEED = 911
ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False, 'teacher_only': True}
STARTS = {
    MAPS[0]: {'r1': [3.75, -1.85, .35], 'r2': [.65, -1.55, -.55]},
    MAPS[1]: {'r1': [4.15, -1.40, -.35], 'r2': [.85, -1.10, .55]},
}


def registry():
    value = previous.base.read(previous.ROOT / REGISTRY)
    expected = {'schema': 'ugrp.final_pair_heldout.v95', 'execution_bundle_id': BUNDLE_ID,
        'status': 'DRAFT_UNSEALED', 'workflow_id': WORKFLOW_ID, 'workflow_version': WORKFLOW_VERSION,
        'check': CHECK, 'maps': list(MAPS), 'robots': list(ROBOTS), 'seed': SEED, **ROLE,
        'start_xy_yaw': STARTS, 'schedule_family': 'v88 unloaded 10s signed steps + PRBS31',
        'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
        'contact_profile': 'cargo_noslip_v1', 'weld': 'off', 'sensors': {'ultrasonic_front': 'off'}}
    if value != expected:
        raise ValueError('v95 registry differs from the authored acquisition')
    return value


def selected(check, map_id):
    return check == CHECK and map_id in MAPS


def design(check, map_id, robot_id='r1'):
    if not selected(check, map_id) or robot_id not in ROBOTS:
        raise ValueError('v95 requires unloaded collection on registered maps and robots')
    plan = training_design(check)
    segments = []
    order = ('left', 'turn', 'forward') if robot_id == 'r1' else ('forward', 'turn', 'left')
    phase = 7 if robot_id == 'r1' else 13
    bits = plan['prbs']['bits']
    bits = bits[phase:]+bits[:phase]
    for axis in order:
        for magnitude in plan['magnitudes']:
            for sign in (-1, 1):
                segments += [{'axis': axis, 'duration_s': 10., 'value': sign*magnitude, 'phase': 'step'},
                             {'axis': axis, 'duration_s': 1., 'value': 0., 'phase': 'coast'}]
        segments += [{'axis': axis, 'duration_s': .5, 'value': .02*bit, 'phase': 'prbs'} for bit in bits]
        segments.append({'axis': axis, 'duration_s': 2.5, 'value': 0., 'phase': 'coast'})
    return {**plan, 'schema': 'ugrp.final_pair_measurement.v95', 'map_id': map_id,
            'robot_id': robot_id, 'start_xy_yaw': list(STARTS[map_id][robot_id]),
            'segments': segments, 'axis_order': list(order),
            'prbs': {**plan['prbs'], 'bits': bits, 'cyclic_phase': phase},
            'qualification': 'New authored held-out schedule; precheck is not collection or B scoring'}


def schedule(check=CHECK, map_id=MAPS[0]):
    events = []
    # Preserve the training arm/camera schedule for each robot, including late
    # postures. Driving r2 never silently inherits a stationary camera schedule.
    camera = [e for e in training_schedule(check) if e['action']['kind'] != 'mecanum']
    for rid in ROBOTS:
        events.extend({**copy.deepcopy(e), 'robot_id': rid} for e in camera)
        plan = design(check, map_id, rid)
        step = round(plan['motion_start_s']/PERIOD_S)
        for segment in plan['segments']:
            for _ in range(round(segment['duration_s']/PERIOD_S)):
                action = {'kind': 'mecanum', **dict.fromkeys(AXES, 0.), 'duration_s': PERIOD_S}
                action[segment['axis']] = segment['value']
                events.append({'t': round(step*PERIOD_S, 8), 'robot_id': rid,
                               'phase': 'unloaded_'+segment['phase'], 'action': action})
                step += 1
    return sorted(events, key=lambda e: (e['t'], e['robot_id']))


def cases(check, map_id):
    design(check, map_id)
    return [{'id': map_id, 'map_id': map_id, 'checkpoint': None, 'sim_cap_s': 370.}]


def require_seed(bundle, seed):
    if seed != SEED or bundle.get('seed') != SEED:
        raise ValueError('v95 requires seed 911')


def record(bundle):
    return dict(ROLE) if bundle['execution_bundle_id'] == BUNDLE_ID else {}


def path_preflight(check, map_id):
    from harness.zone_final_pair_clearance import start_pose_check, runtime_interlock
    design(check, map_id)
    start = start_pose_check(previous.resolve(map_id)[0], STARTS[map_id])
    return {'admitted': start['admitted'], 'scope': 'SIMULATION_ONLY_TEACHER_CALIBRATION',
            'reason': 'START_POSE_CLEAR_INTERLOCK_REQUIRED' if start['admitted'] else 'START_POSE_TOO_CLOSE_TO_WALL',
            'start_pose_check': start, 'runtime_interlock': runtime_interlock(),
            'full_path': 'mandatory v95 headless precheck plus abort-only geometry guard during collection'}


def validate_bundle(value):
    from harness.zone_final_pair_clearance import runtime_interlock
    reg = registry()
    mid = value.get('map_id')
    if not selected(value.get('check'), mid):
        raise ValueError('v95 check/map mismatch')
    for key in ('execution_bundle_id', 'workflow_id', 'workflow_version', 'check', 'seed',
                'robot_model', 'render_profile', 'contact_profile', 'weld', 'sensors', *ROLE):
        if type(value.get(key)) is not type(reg[key]) or value[key] != reg[key]:
            raise ValueError('v95 bundle mismatch: '+key)
    expected = {'start_xy_yaw': STARTS[mid], 'robots': list(ROBOTS),
                'measurement': design(CHECK, mid),
                'measurement_by_robot': {rid: design(CHECK, mid, rid) for rid in ROBOTS},
                'timing': previous.execution_timing(CHECK), 'runtime_interlock': runtime_interlock(),
                'clearance_preflight': path_preflight(CHECK, mid),
                'map_sha256': previous.base.digest(previous.resolve(mid)[0])}
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise ValueError('v95 bundle mismatch: '+key)
    if 'case' in value and value['case'] != cases(CHECK, mid)[0]:
        raise ValueError('v95 case mismatch')


def require_collection_clearance(value):
    validate_bundle(value)
    receipt = path_preflight(value['check'], value['map_id'])
    if not receipt['admitted']:
        raise ValueError(receipt['reason'])
    return receipt


def bundle(map_id, check=CHECK):
    from harness import zone_final_pair_fast as parent
    from harness.python_source_closure import source_closure
    registry()
    value = parent.bundle(map_id, check)
    value.update(schema='ugrp.final_pair_bundle.v95', execution_bundle_id=BUNDLE_ID,
        workflow_id=WORKFLOW_ID, workflow_version=WORKFLOW_VERSION, **ROLE,
        revision='v95 new starts; both robots; reordered signed steps and phase-shifted PRBS',
        controller_variant='v95-unloaded-new-starts', measurement=design(check, map_id),
        measurement_by_robot={rid: design(check, map_id, rid) for rid in ROBOTS},
        robots=list(ROBOTS), start_xy_yaw=copy.deepcopy(STARTS[map_id]),
        clearance_preflight=path_preflight(check, map_id))
    files = set(value['source_sha256']) | set(source_closure(previous.ROOT, [
        'harness/zone_final_pair_new_starts.py', 'scripts/run_final_pair_new_starts.py',
        'sim/final_pair_new_starts.py'])) | {REGISTRY, WORKFLOW}
    value['source_sha256'] = {p: previous.base.sha(previous.ROOT / p) for p in sorted(files)}
    validate_bundle(value)
    return value
