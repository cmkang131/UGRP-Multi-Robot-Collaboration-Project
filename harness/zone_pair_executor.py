"""M2 door-v3 adapter for the per-robot own-camera API (issue #221).

No world/peer handle reaches a robot. PairTeam is host-side dispatch only;
PairExecution has ONE own executor, buffered own commands and enum messages.
The frozen M2 CLI/controller and its imported sources remain byte-identical.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping

from harness.zone_own_contract import finite_number
from harness.zone_pair_status import MAX_SEGMENTS, PairStatusChannel, PairStatusEndpoint

PROFILE = 'zone_pair_executor_v1_dev'
PAIR = ('r1', 'r2')                 # frozen M2 roles: end_neg / end_pos
CONTACT_PROFILE = 'cargo_noslip_v1'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def make_plan(static_map, sheet, target_zone):
    """Static coarse work order -> M2 approach + axis-aligned route to a zone.

    Sheet is authored BEFORE execution, never reconstructed from world state.
    Only the M2 door map and long_beam geometry are supported in this version.
    Catalogue queries below are static geometry, not a teacher or world query.
    """
    from scripts import run_m2_pair as m2
    from sim.zone_cargo import instances, world_grasps
    from harness.map_goto import authored_obstacles, envelope_overlaps, interior_bounds

    if not isinstance(sheet, Mapping) or set(sheet) != {'beam_xyyaw', 'grid', 'source'}:
        raise ValueError('BAD_COARSE_ORDER_SHEET')
    pose = sheet['beam_xyyaw']
    if not isinstance(pose, (list, tuple)) or len(pose) != 3 or not all(finite_number(x) for x in pose):
        raise ValueError('BAD_COARSE_ORDER_SHEET')
    if m2.pa.coarse_order_sheet(pose) != dict(sheet):
        raise ValueError('ORDER_SHEET_NOT_ON_COARSE_GRID')
    door = next((p for p in static_map['passages'] if p['id'] == m2.DOOR_PLAN['door_id']), None)
    if door is None or list(door['center_m']) != [2.2, .05] or door['width_m'] != .5:
        raise ValueError('UNSUPPORTED_PAIR_MAP')
    if not (.7 <= pose[0] <= 1.2 and abs(pose[1] - .05) <= .15 and abs(pose[2]) <= math.radians(10) + 1e-6):
        raise ValueError('PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE')
    region = static_map['regions']['zone_' + target_zone]
    tx, ty = region['center_m']
    route = [[pose[0], .05], [1.55, .05], [2.40, .05], [3.20, .05]]
    # Clear the doorway before the lateral leg. Keep the same opposing headings.
    for point in ([3.20, ty], [tx, ty]):
        if math.dist(route[-1], point) > 1e-6:
            route.append(list(point))
    # Keep the frozen controller's short carry/relocalize cadence on new legs.
    split_route = [route[0]]
    for a, b in zip(route, route[1:]):
        n = max(1, math.ceil(math.dist(a, b) / .85))
        split_route.extend([[a[k] + (b[k] - a[k]) * i / n for k in (0, 1)] for i in range(1, n + 1)])
    route = split_route
    if len(route) - 1 > MAX_SEGMENTS:
        raise ValueError('TOO_MANY_PAIR_SEGMENTS')
    # Static footprint includes the beam and both carriers. This is a planning
    # refusal, not a live collision check or proof of physical clearance.
    envelope = {'x_m': [-.625, .625], 'y_m': [-.20, .20]}
    x0, x1, y0, y1 = interior_bounds(static_map)
    obstacles = authored_obstacles(static_map)
    for a, b in zip(route, route[1:]):
        n = max(1, math.ceil(math.dist(a, b) / .02))
        for i in range(n + 1):
            p = [a[k] + (b[k] - a[k]) * i / n for k in (0, 1)]
            if not (x0 <= p[0] - .625 and p[0] + .625 <= x1 and y0 <= p[1] - .20 and p[1] + .20 <= y1):
                raise ValueError('PAIR_ROUTE_OUTSIDE_MAP')
            if any(envelope_overlaps(p, envelope, o) for o in obstacles):
                raise ValueError('PAIR_ROUTE_BLOCKED_BY_STATIC_MAP')
    item = instances([{'item_id': 'ordered_beam', 'kind': 'long_beam', 'pose': list(pose)}])[0]
    grasps = world_grasps(item, pose=pose)       # explicit STATIC sheet pose, no world
    stations = {r: list(grasps[role]['base_xyyaw']) for r, role in m2.ROLES.items()}
    pre = {r: m2.pa.prestation(stations[r], m2.study.PRESTATION_BACK_M) for r in PAIR}
    bar = next(p for p in item.spec().parts if p.name == 'bar')
    keepouts = {}
    for r in PAIR:
        peer = next(p for p in PAIR if p != r)
        keepouts[r] = [m2.pa.beam_keepout(pose, 2 * bar.size[0], 2 * bar.size[1], m2.KEEPOUT_PAD_M)]
        for label, station in (('station', stations[peer]), ('prestation', pre[peer])):
            keepouts[r].append({'id': 'partner_' + label, 'center_m': station[:2],
                                'half_extents_m': [m2.PARTNER_KEEPOUT_HALF_M] * 2,
                                'source': 'static order sheet'})
    return {'sheet': copy.deepcopy(sheet), 'route': route, 'prestations': pre, 'keepouts': keepouts,
            'target_zone': target_zone, 'door_plan': copy.deepcopy(m2.DOOR_PLAN),
            'map_sha256': _digest(static_map), 'sheet_sha256': _digest(sheet)}


class _OwnPort:
    """Buffer commands for the host; capture only the owning executor's validated frame."""
    def __init__(self, own):
        self.own, self.commands = own, []

    def apply(self, action, now):
        self.commands.append(dict(action))

    def hold(self, now):
        self.commands.append({'kind': 'hold'})

    def capture(self):
        from harness.m1_owncam_contract import validate_observation
        obs = self.own.last_obs
        validate_observation(obs, robot_id=self.own.robot_id, previous_frame_id=None, now=self.own.now)
        return copy.deepcopy(obs)


def m2_controller(execution, plan, params):
    """Instantiate the REAL frozen controller, with only route and I/O adapters."""
    from scripts import run_m2_pair as m2
    from scripts.zone_teacher import ArmSequence

    class RoutedM2(m2.M2DoorStudent):
        requires_fresh_frame = True

        def _wait_carry(self, now, arm_idle):
            # Both schedules must contain the same alignment interval. Refuse
            # the frozen runner's optional 'no estimate -> skip alignment' path.
            if self.grasp_estimate is None or not all(finite_number(v) for v in self.grasp_estimate):
                return self.fail('DOOR_POSE_NOT_LOCALIZED', now)
            return super()._wait_carry(now, arm_idle)

        def door_schedule(self, t0):
            a, b = plan['route'][self.seg:self.seg + 2]
            self.door_plan['axis_y_m'] = a[1]
            schedule = super().door_schedule(t0)  # reuse M2 own-estimate alignment and timing
            start, _, _ = schedule[-1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            lateral = abs(dy) > 1e-6
            axis = 'lateral' if lateral else 'axial'
            duration = math.hypot(dx, dy) / (m2.study.SPEED_M_S * m2.study.CARRY_ODOM_SCALE[axis])
            sign = 1. if self.rid == 'r1' else -1.
            schedule[-1] = (start, start + duration,
                            {'forward': sign * math.copysign(m2.study.SPEED_M_S, dx) / m2.study.FORWARD_GAIN
                             if not lateral else 0.,
                             'left': sign * math.copysign(m2.study.SPEED_M_S, dy) / m2.study.LEFT_GAIN
                             if lateral else 0., 'turn': 0.})
            claim = self.claims['segments'][-1]
            claim.pop('axial_m', None)
            claim.update(axis=axis, distance_m=math.hypot(dx, dy), static_from_xy=list(a), static_to_xy=list(b))
            return schedule

    own, rid = execution.own, execution.own.robot_id
    driver = m2.pa.PairApproachDriverV2(copy.deepcopy(own.map), copy.deepcopy(params),
                                       goal_xyyaw=plan['prestations'][rid], door_xy=None,
                                       keepouts=plan['keepouts'][rid], initial_servo=dict(own.servo), seed=own.seed)
    driver.on_command({'t': own.now, 'kind': 'initial_servo_command', 'pulses': dict(own.servo)})
    arm = ArmSequence(execution.port, dict(own.servo))
    ctl = RoutedM2(rid, execution.port, arm, execution.status.sync_for, execution.log,
                   execution.save, (execution.status.channel, execution.status), 'fullframe_v3', driver,
                   lambda *a: None, door_plan=copy.deepcopy(plan['door_plan']),
                   axial_m=plan['route'][-1][0] - plan['sheet']['beam_xyyaw'][0],
                   sheet_beam_x=plan['sheet']['beam_xyyaw'][0], version='v3')
    ctl.segments = [math.dist(a, b) for a, b in zip(plan['route'], plan['route'][1:])]
    ctl.state_t = own.now
    return ctl


class PairExecution:
    """One robot's local job. Peers are observable only through status records."""
    def __init__(self, own, status, arguments, plan, params, factory=m2_controller):
        self.own, self.status = own, status
        self.partner_id = next(r for r in PAIR if r != own.robot_id)
        self.plan, self.calibration_sha256 = copy.deepcopy(plan), _digest(params)
        self.arguments, self.port = dict(arguments), _OwnPort(own)
        self.events, self.inputs = [], []
        self.terminal, self.started, self.cleared = False, False, False
        self.job_id = None
        self.last_phase = None
        self.controller = factory(self, copy.deepcopy(plan), copy.deepcopy(params))

    def log(self, rid, kind, now, **detail):
        self.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **detail})

    def save(self, rid, obs, phase):
        # JPEGs are saved by OwnCamTeamHost._capture_raw. Keep an exact link to
        # every consumed frame (including repeated reads), separately per robot.
        self.inputs.append({'robot_id': rid, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
                            'sim_s': obs['sim_time'], 'phase': phase})

    def on_command(self, row):
        if not self.terminal:
            self.controller.driver.on_command(row)

    def abort(self, now, reason):
        if self.terminal:
            return
        self.status.tick('abort', now)
        self._clear(now)
        self.terminal = True
        if self.own.job is not None and self.own.job.job_id == self.job_id:
            self.own._holding_after = {'answer': 'unknown', 'source': 'pair stopped; no release confirmation'}
            self.own._fail(now, reason)

    def _clear(self, now):
        self.controller.arm.events.clear()
        self.controller.arm.until = now
        self.controller.schedule = []
        self.port.commands.clear()

    def check(self, now):
        if self.terminal:
            return
        self.own.now = now
        if self.controller.state == 'failed':
            return self.abort(now, self.controller.failure or 'M2_FAILED')
        if self.own.stopped is not None:
            return self.abort(now, 'ROBOT_STOPPED')
        if self.own.job is None or self.own.job.job_id != self.job_id:
            return self.abort(now, 'PAIR_JOB_LOST')
        if now > self.own.job.deadline:
            return self.abort(now, 'LOCAL_TIMEOUT')
        for v in self.status.channel.partner_view(self.own.robot_id, now).values():
            if v['state'] == 'abort':
                return self.abort(now, 'PARTNER_ABORT')
            if not v['alive']:
                return self.abort(now, 'PARTNER_SILENT')

    def step(self, now):
        self.check(now)
        if self.terminal:
            return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
        if not self.started:
            self.status.tick('start_ready', now)
            ready = {m['robot_id'] for m in self.status.channel.log if m['state'] == 'start_ready'}
            if ready != set(self.status.channel.participants):
                return {'mode': 'tick', 'commands': []}
            self.started = True
        if (getattr(self.controller, 'requires_fresh_frame', False) and self.controller.state != 'done'
                and (self.own.last_obs is None or self.own.last_obs['sim_time'] < now - 1e-6)):
            # Capture before calling the monolithic tick: unwinding halfway
            # through its look() would advance timers without an observation.
            return {'mode': 'capture'}
        # A done controller must not republish the frozen coarse put_down state.
        if self.controller.state != 'done':
            self.controller.tick(now)
        if self.controller.state == 'failed':
            self.abort(now, self.controller.failure or 'M2_FAILED')
            return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
        phase = self.controller.state
        if phase != self.last_phase:
            self.own.job.phase = phase
            self.own._emit(now, 'pair_progress', phase=phase)
            self.last_phase = phase
        if phase == 'done':
            self.status.tick('done', now)
            # Sequence completion is not an RGB confirmation of the named zone.
            # Wait for the other robot's done ENUM, never inspect its controller.
            if all(m['state'] == 'done' for m in self.status.channel.latest.values()):
                self._clear(now)
                self.terminal = True
                self.own._holding_after = {'answer': 'unknown', 'source': 'M2 release sequence; zone unconfirmed'}
                self.own._finish(now, 'unconfirmed', 'PAIR_SEQUENCE_DONE', profile=PROFILE)
                return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
        self.controller.arm.tick(now)
        commands, self.port.commands = self.port.commands, []
        return {'mode': 'tick', 'commands': commands}


class PairTeam:
    """Host-side two-phase acceptance; dispatch task content outside the status channel.

    Every endpoint decides its own admission and publishes only a fixed enum.
    Host cancellation callbacks never enter an endpoint's object graph.
    """
    def __init__(self, executors, sheets, params, *, cancel_scheduled, contact_profile, weld=False,
                 controller_factory=m2_controller):
        self.executors = dict(executors)
        self.sheets, self.params = copy.deepcopy(sheets), copy.deepcopy(params)
        self.cancel_scheduled = cancel_scheduled
        self.contact_profile, self.weld = contact_profile, weld
        self.factory = controller_factory
        self.sessions = []
        self.counter = 0

    def start(self, rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        ex = self.executors[rid]
        ex.now = now
        args = {'order_id': ex._token(item_ref), 'target_ref': ex._token(target_zone),
                'role': 'end_neg' if rid == 'r1' else 'end_pos'}
        def refuse(reason):
            return ex._ack('pair_carry', args, False, reason)
        if not all(isinstance(v, str) and v for v in (item_ref, target_zone, partner_id)):
            return refuse('BAD_PAIR_ARGUMENTS')
        if rid not in PAIR or partner_id not in PAIR or rid == partner_id or partner_id not in self.executors:
            return refuse('UNSUPPORTED_PAIR')
        if self.contact_profile != CONTACT_PROFILE or self.weld is not False:
            return refuse('PAIR_REQUIRES_NOSLIP_WELD_OFF')
        order = ex.orders.get(item_ref)
        if order is None:
            return refuse('UNKNOWN_ORDER')
        if order.get('kind') != 'long_beam' or order.get('count') != 1 or order.get('required_robots') != 2:
            return refuse('UNSUPPORTED_PAIR_ORDER')
        if target_zone != order.get('destination_zone') or target_zone not in ex.map['zone_slots']:
            return refuse('WRONG_PAIR_DESTINATION')
        self.counter += 1
        channel = PairStatusChannel(f'pair-{self.counter:06d}')  # opaque id, no task meaning
        senders = {r: PairStatusEndpoint(channel, r) for r in PAIR}
        for r in PAIR:
            self.executors[r].now = now
            senders[r].tick(self.executors[r].pair_readiness(now, item_ref, target_zone), now)
        for r in (rid, partner_id):
            state = channel.latest[r]['state']
            if state != 'available':
                return refuse(('SELF_' if r == rid else 'PARTNER_') + state.upper())
        try:
            plan = make_plan(ex.map, self.sheets.get(item_ref), target_zone)
            endpoints = {}
            for r in PAIR:
                local = self.executors[r]
                own_args = {**args, 'role': 'end_neg' if r == 'r1' else 'end_pos'}
                endpoints[r] = PairExecution(local, senders[r], own_args, plan, self.params, self.factory)
        except (ValueError, KeyError, TypeError) as exc:
            return refuse(str(exc) or 'INVALID_PAIR_PLAN')
        acks = {}
        for r in PAIR:
            local = self.executors[r]
            local._pair = endpoints[r]
            acks[r] = local.pair_carry(item_ref, target_zone, endpoints[r].partner_id)
            if not acks[r]['accepted']:
                local._pair = None
        self.sessions.append({'channel': channel, 'endpoints': endpoints, 'acks': acks,
                              'plan': copy.deepcopy(plan), 'calibration_sha256': _digest(self.params)})
        if not all(a['accepted'] for a in acks.values()):
            for ep in endpoints.values():
                ep.abort(now, 'PAIR_ACCEPTANCE_ROLLBACK')
            self.poll(now)
            return refuse('PAIR_ACCEPTANCE_ROLLBACK')
        for r in PAIR:
            # Remove any previous host macro and poll both local status consumers
            # at the acceptance time. Only the status rendezvous authorizes motion.
            self.cancel_scheduled(r, now, 'pair_start')
        # Initial joint readiness is sent by the two local acceptance paths.
        return acks[rid]

    def poll(self, now):
        """Before/after host commands: propagate abort via enums, cancel BOTH macros."""
        for session in self.sessions:
            endpoints = session['endpoints']
            # Two passes propagate a second endpoint's abort to the first too.
            for _ in range(2):
                for ep in endpoints.values():
                    ep.check(now)
            for ep in endpoints.values():
                if ep.terminal and not ep.cleared:
                    ep.cleared = True
                    if ep.job_id is not None:
                        self.cancel_scheduled(ep.own.robot_id, now, 'pair_terminal')

    def records(self):
        return [{'profile': PROFILE, 'status_profile': 'zone_pair_status_v2',
                 'status_messages': s['channel'].log, 'rejected_status': s['channel'].rejected,
                 'plan': s['plan'], 'calibration_sha256': s['calibration_sha256'],
                 'acks': s['acks'], 'robots': {r: {'events': ep.events, 'inputs': ep.inputs}
                                             for r, ep in s['endpoints'].items()}} for s in self.sessions]
