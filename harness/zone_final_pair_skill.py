"""Instance adapter for the frozen registered pair skill on final v3 maps.

The v2 0.948 fit is deliberately replaced by measured v3 gain/lag, never
presented as a byte-identical replay of the b-v6h1 v2 acceptance cohort.
"""
from __future__ import annotations

import copy
import math
from types import MethodType, SimpleNamespace

import numpy as np

from harness import zone_pair_executor as pair
from harness import pair_passage_plan as passage
from harness import visual_arm_v3 as arm
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_guards import CommandGuard
from harness.zone_final_pair_vision import PairVision, GRASP_RADIUS_M, ALIGN_TOL_X_M, ALIGN_TOL_Y_M, grasp_postures
from scripts import run_m2_pair as m2

TASK_POSE = [1., .05, 0.]
ORDER = {'orders': [{'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
                    'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}
SHEET = m2.pa.coarse_order_sheet(TASK_POSE)
ENVELOPE = {'x_m': [-.625-arm.MOUNT_X_M, .625+arm.MOUNT_X_M], 'y_m': [-.20, .20]}


def task(static):
    corridor = static['map_id'] == 'zone_wide_corridor_final_v3'
    pose, target = ([1., 1.2, 0.], 'A') if corridor else (TASK_POSE, 'B')
    order = copy.deepcopy(ORDER)
    order['orders'][0]['destination_zone'] = target
    return {'beam_pose': list(pose), 'target': target, 'order': order,
            'sheet': m2.pa.coarse_order_sheet(pose)}


def route_for(static, sheet, target, opening):
    """V3 clear-side checkpoints, with the registered <=0.85 m leg clock."""
    from harness.map_goto import authored_obstacles, interior_bounds
    check = passage.check_passage(static, opening, envelope=ENVELOPE)
    (x0, x1), yc, _ = passage._extent(opening)
    before = [x0-ENVELOPE['x_m'][1]-.05, yc]
    after = [x1-ENVELOPE['x_m'][0]+.05, yc]
    x, y, _ = sheet['beam_xyyaw']
    if x >= before[0]:
        raise passage.PassageRefusal('PAIR_PICKUP_PAST_BEFORE_CHECKPOINT')
    tx, ty = static['regions']['zone_'+target]['center_m']
    key = [[x, yc]] if abs(y-yc) <= passage.DOOR_ALIGN_MAX_M else [[x, y], [x, yc]]
    key.extend([before, after, [after[0], ty], [tx, ty]])
    key = [p for i, p in enumerate(key) if i == 0 or math.dist(p, key[i-1]) > 1e-9]
    route = passage.split_legs(key)
    if len(route)-1 > passage.MAX_LEGS:
        raise passage.PassageRefusal('PAIR_PASSAGE_TOO_MANY_SEGMENTS')
    reason, blocker = passage._sweep_blocker(route, ENVELOPE, authored_obstacles(static),
                                            interior_bounds(static), passage.ROUTE_MARGIN_M)
    if reason:
        raise passage.PassageRefusal(reason, blocker=blocker)
    index = lambda xy: next(i for i, p in enumerate(route) if math.dist(p, xy) < 1e-8)
    checkpoints = {'before_door': index(before), 'after_door': index(after),
                   'before_destination': len(route)-2}
    info = {'id': opening['id'], 'axis_y_m': yc, 'exit_x_m': after[0], 'x_range_m': [x0, x1],
            'envelope': copy.deepcopy(ENVELOPE), **check,
            'route_length_m': sum(math.dist(a, b) for a, b in zip(route, route[1:]))}
    return route, checkpoints, info


def make_plan(static, sheet, target):
    from sim.zone_model_conventions import station_offset
    static = passage.without_aliases(static)
    if sheet != task(static)['sheet'] or target != task(static)['target']:
        raise ValueError('final v3 adapter requires its authored static task')
    # Template supplies catalogue geometry only; its M2 pickup envelope is
    # not applied to the separately authored corridor task.
    plan = pair.make_plan(passage.load_map(passage.TEMPLATE_MAP_ID), SHEET, target)
    plan.update(sheet=copy.deepcopy(sheet), sheet_sha256=passage.digest(sheet))
    routes = []
    for p in passage.traversable_passages(static):
        try:
            routes.append(route_for(static, sheet, target, p))
        except passage.PassageRefusal:
            continue
    if not routes:
        raise ValueError('NO_STATIC_V3_PAIR_ROUTE')
    route, checkpoints, info = min(routes, key=lambda r: r[2]['route_length_m'])
    plan.update(route=route, passage=info, checkpoint_segments=checkpoints, map_sha256=passage.digest(static))
    plan['door_plan'].update(door_id=info['id'], axis_y_m=info['axis_y_m'],
                             target_beam_x_m=info['exit_x_m'])
    x, y, yaw = sheet['beam_xyyaw']
    c, s = math.cos(yaw), math.sin(yaw)
    stations = {}
    for rid, role in m2.ROLES.items():
        dx, dy, heading = station_offset(static, 'long_beam', role)
        stations[rid] = [x+c*dx-s*dy, y+s*dx+c*dy, yaw+heading]
    plan['prestations'] = {r: m2.pa.prestation(p, m2.study.PRESTATION_BACK_M) for r, p in stations.items()}
    for rid in pair.PAIR:
        peer = next(r for r in pair.PAIR if r != rid)
        for row in plan['keepouts'][rid]:
            if row['id'] == 'partner_station':
                row['center_m'] = stations[peer][:2]
            elif row['id'] == 'partner_prestation':
                row['center_m'] = plan['prestations'][peer][:2]
            else:
                row['center_m'] = list(sheet['beam_xyyaw'][:2])
    return plan


def motor_command(profile, velocity):
    """Invert the same measured gain and piecewise deadband as the pair PF."""
    effective = np.linalg.solve(np.asarray(profile['gain'], float), velocity)
    c0 = np.asarray(profile['deadband']['c0'], float)
    u1 = np.asarray(profile['deadband']['u1'], float)
    raw = effective.copy()
    for i, value in enumerate(effective):
        if 0 < abs(value) < u1[i] and u1[i] > c0[i]:
            raw[i] = math.copysign((c0[i]+math.sqrt(c0[i]**2+4*abs(value)*(u1[i]-c0[i])))/2, value)
    return raw


class V3Controller:
    def set(self, state, now, **detail):
        return super().set(state, now, seg=self.seg, **detail)

    def _switch_look(self, distance, now):
        return super()._switch_look(distance-(GRASP_RADIUS_M-m2.study.ob.GRASP_RADIUS_M), now)

    # Same open descent/close rendezvous, using the finite calibrated poses.
    def _queue_open_descent(self, now):
        bx, by = self.grip_base
        if abs(bx-GRASP_RADIUS_M) > ALIGN_TOL_X_M+1e-9 or abs(by) > ALIGN_TOL_Y_M+1e-9:
            return self.fail('V3_GRIP_OUTSIDE_FIXED_POSTURE', now)
        try:
            self.hover, path = grasp_postures()
        except Exception as exc:
            return self.fail(f'IK_UNAVAILABLE:{exc}', now)
        self.grasp_pose = path[-1]
        self.log(self.rid, 'v3_grasp_target', now, observed_grip=list(self.grip_base),
                 commanded_target=[GRASP_RADIUS_M, 0.], source='fixed calibrated posture; own RGB alignment')
        self.arm.queue({**self.hover, 1: m2.study.OPEN}, now, duration=1.)
        for pose in path:
            self.arm.queue(pose, now, duration=.12, settle=0.)
        from harness.zone_pair_grasp_entry_v6c import FINAL_DESCENT_SETTLE_S
        self.arm.until += FINAL_DESCENT_SETTLE_S
        self.set('pregrasp_descend', now)

    _on_beam_obs = bind(m2.M2DoorStudent._on_beam_obs, EXPECT_GRIP_X_M=m2.study.PRESTATION_BACK_M+GRASP_RADIUS_M)
    _start_reapproach = bind(m2.M2DoorStudent._start_reapproach, EXPECT_GRIP_X_M=m2.study.PRESTATION_BACK_M+GRASP_RADIUS_M)

    def _begin_provider_look(self, now):
        # Markerless P03 invalidates the receipt, not the PF or its belief.
        self.port.own.pose.begin_relocalization(now, self.port.own.servo)

    def _cp_open(self, now, arm_idle):
        if not arm_idle:
            return
        self.log(self.rid, 'checkpoint_open', now, seg=self.seg)
        self.seg += 1
        self.pregrasp_done, self.pregrasp_sweeps = False, 0
        self.grasp_estimate = None
        self.claims.pop('door_align', None)
        self.aligned_streak = 0
        # set(align) invokes the registered bounded stop/look/return sequence,
        # then actual RGB alignment -> grasp -> lift, using the same provider.
        self.look_name = 'p45'
        self.set('align', now, restart='v3_checkpoint')

    def door_schedule(self, t0):
        from harness.owncam_carry_v6e import lag_duration
        a, b = self.v3_plan['route'][self.seg:self.seg+2]
        mp = self.v3_params['motion_loaded']
        _, y, yaw = self.grasp_estimate
        dy = float(np.clip(a[1]-y, -m2.DOOR_ALIGN_MAX_M, m2.DOOR_ALIGN_MAX_M))
        ey = float(np.clip(m2.study.wrap(self.door_plan['headings_rad'][self.rid]-yaw),
                           -m2.DOOR_ALIGN_MAX_RAD, m2.DOOR_ALIGN_MAX_RAD))
        # Measured full matrix also handles cross-axis coupling. Fixed common
        # interval preserves both endpoints' barrier schedule.
        from harness.owncam_carry_v6e import lag_travel
        tau_axis = np.asarray(mp.get('tau_axis_s', [mp['tau_s']]*3), float)
        effective_s = np.array([lag_travel(m2.DOOR_ALIGN_S, 1., tau, mp['tau_stop_s'])
                                for tau in tau_axis])
        v = np.array([math.sin(yaw)*dy, math.cos(yaw)*dy, ey]) / effective_s
        u = motor_command(mp, v)
        align = dict(zip(('forward', 'left', 'turn'), map(float, u)))
        self.claims['door_align'] = {'dy_m': dy, 'e_yaw_rad': ey, 'cmd': align}
        t = t0 + m2.DOOR_ALIGN_S + .5
        delta = np.asarray(b)-a
        distance = float(np.linalg.norm(delta))
        axis = 'lateral' if abs(delta[1]) > 1e-6 else 'axial'
        sign = pair.carry_role_sign(self.rid)
        velocity = np.r_[sign*delta/distance*m2.study.SPEED_M_S, 0.]
        u = motor_command(mp, velocity)
        command = dict(zip(('forward', 'left', 'turn'), map(float, u)))
        duration = lag_duration(distance, abs(float(velocity[1 if axis == 'lateral' else 0])),
                                tau_axis[1 if axis == 'lateral' else 0], mp['tau_stop_s'])
        # Reject inadmissible commands before scheduling; never silently clip
        # a command while retaining the unclipped timing prediction.
        from sim.camera_robot_port import validate_raw_action
        for cmd in (align, command):
            validate_raw_action({'kind': 'mecanum', **cmd, 'duration_s': .15},
                                allow_reverse=True, allow_mecanum=True)
        provider = self.port.own.pose.provider
        provider.loc._pf.pair_plan = {'t0': t, 't1': t+duration, 'own': u.copy(), 'partner': -u.copy()}
        self.claims.setdefault('segments', []).append({'seg': self.seg, 'axis': axis,
            'distance_m': distance, 'static_from_xy': a, 'static_to_xy': b, 'cmd': command})
        return [(t0, t0+m2.DOOR_ALIGN_S, align), (t, t+duration, command)]


def controller(execution, plan, params):
    ctl = pair.m2_controller(execution, plan, params)
    ctl.__class__ = type('FinalV3PairController', (V3Controller, type(ctl)), {})
    ctl.v3_plan, ctl.v3_params = plan, params
    vision = execution.vision
    # Preserve the beam alignment algorithm/code object. Force its no-local-
    # import path and substitute per-instance projection/hue dependencies.
    ob = SimpleNamespace(**{**vars(m2.study.ob), 'align_errors': vision.align_errors,
                           'align_command': vision.align_command})
    def observe(image, servo):
        hue = m2.study.PairStudent._beam_hue_lo(ctl)
        return vision.observe_beam(image, servo, hue_lo=hue)
    ob2 = SimpleNamespace(**{**vars(m2.study.ob2), 'observe_beam': observe})
    ctl._align = MethodType(bind(m2.study.PairStudent._align, ob=ob, ob2=ob2), ctl)
    ctl._beam_hue_lo = lambda: None
    ctl._released = MethodType(bind(m2.study.PairStudent._released, ob2=ob2), ctl)
    return ctl


class Execution(pair.PairExecution):
    def __init__(self, *args, calibration, **kwargs):
        self.vision = PairVision(calibration)
        kwargs.update(factory=controller, policy='b-v6g')
        super().__init__(*args, **kwargs)
        self.command_guard = CommandGuard(self, self.vision)


class Team(pair.PairTeam):
    """Same dispatch/admission contract, with no v2 calibration injection."""
    def __init__(self, executors, calibration, static_task):
        from harness.zone_pair_v6_policy import pair_policy
        self.executors = dict(executors)
        self.policy = pair_policy('b-v6g')
        self.sheets = {'cargoX': copy.deepcopy(static_task['sheet'])}
        self.params = copy.deepcopy(calibration['params'])
        self.cancel_scheduled = lambda *a: None
        self.contact_profile, self.weld = pair.CONTACT_PROFILE, False
        self.factory = controller
        self.rendezvous_timeout_s, self.heartbeat_timeout_s = 5., .15
        self.align_motion, self.carry_dr, self.sessions = {}, {}, []
        def make_execution(own, status, arguments, plan, params, factory, *, policy):
            return Execution(own, status, arguments, plan, params, calibration=calibration)
        self.start = MethodType(bind(pair.PairTeam.start, make_plan=make_plan, PairExecution=make_execution), self)

    def records(self):
        rows = super().records()
        for row in rows:
            row['pair_policy'] = 'b-v6h1-v3-measured'
            row['v2_calibration_inherited'] = False
        return rows
