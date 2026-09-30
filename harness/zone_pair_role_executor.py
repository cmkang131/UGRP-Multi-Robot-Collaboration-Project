"""Opt-in T07 role dispatcher, isolated from the sealed v6e executor.

Only explicit users of this module select the new implementation. The legacy
module and its source closure remain byte-identical; no module globals or
robot identities are patched. Shared lifecycle methods are inherited.
"""
from __future__ import annotations

import copy
import hashlib
import math
import uuid

from harness import zone_pair_executor as legacy
from harness.zone_own_contract import finite_number
from harness.zone_pair_executor import _digest, _OwnPort, CONTACT_PROFILE
from harness.zone_pair_roles import LEGACY_ROLES, PairRoles, requested_roles, PROFILE as ROLE_PROFILE
from harness.zone_pair_status import ARM_S, EPS
from harness import zone_pair_status as status

PROFILE = 'zone_pair_role_executor_v1'
PAIR = LEGACY_ROLES.participants


class PairStatusChannel(status.PairStatusChannel):
    def __init__(self, task_id, participants=PAIR, **kwargs):
        participants = tuple(participants)
        if len(participants) != 2:
            raise ValueError('invalid pair participants')
        PairRoles(*participants)
        super().__init__(task_id, participants, **kwargs)


class PairStatusEndpoint(status.PairStatusEndpoint):
    def __init__(self, channel, robot_id):
        if robot_id not in channel.participants:
            raise ValueError('status endpoint is not a pair participant')
        super().__init__(channel, robot_id)


def controller_source_record():
    """Audit-only code closure, separate from role/config/model/environment hashes."""
    from pathlib import Path
    from harness.python_source_closure import source_closure
    root = Path(__file__).resolve().parents[1]
    files = source_closure(root, ('harness/zone_pair_role_executor.py', 'harness/zone_pair_role_host.py',
                                  'harness/zone_pair_role_integration.py'))
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    return {'controller_source_sha256': _digest(hashes), 'controller_source_files': hashes}


def make_plan(static_map, sheet, target_zone, end_inset_m=0., *, role_to_robot=None):
    """Relabel the sealed static role geometry; never relabel a live robot."""
    plan = legacy.make_plan(static_map, sheet, target_zone, end_inset_m)
    if role_to_robot is None:
        return plan
    roles = PairRoles.from_mapping(role_to_robot)
    aliases = {rid: LEGACY_ROLES.mapping()[roles.role(rid)] for rid in roles.participants}
    for field in ('prestations', 'keepouts'):
        plan[field] = {rid: copy.deepcopy(plan[field][alias]) for rid, alias in aliases.items()}
    plan['door_plan']['headings_rad'] = {
        rid: plan['door_plan']['headings_rad'][alias] for rid, alias in aliases.items()}
    plan.update(role_to_robot=roles.mapping(), role_assignment_sha256=roles.sha256())
    return plan


def carry_role_sign(rid, roles=LEGACY_ROLES):
    """Direction sign of a robot's carry command (the two ends of the beam drive mirrored commands)."""
    return roles.sign(rid)


def role_door_schedule(controller, t0, roles):
    """Reuse frozen M2 schedule arithmetic with a local role-indexed view.

    The frozen pure method reads only these fields. Its legacy ID indexes the
    role's constants, never a port, camera, status endpoint or robot. Neither
    the live controller identity nor frozen module globals are changed.
    """
    from types import SimpleNamespace
    from scripts import run_m2_pair as m2
    legacy_id = LEGACY_ROLES.mapping()[roles.role(controller.rid)]
    door = copy.deepcopy(controller.door_plan)
    door['headings_rad'] = {legacy_id: door['headings_rad'][controller.rid]}
    view = SimpleNamespace(rid=legacy_id, door_plan=door, grasp_estimate=controller.grasp_estimate,
                           segments=controller.segments, seg=controller.seg, claims=controller.claims)
    return m2.M2DoorStudent.door_schedule(view, t0)


def m2_controller(execution, plan, params):
    """Instantiate the REAL frozen controller, with only route and I/O adapters."""
    from harness import owncam_carry_v6e as v6e_carry
    from scripts import run_m2_pair as m2
    from scripts.zone_teacher import ArmSequence
    from harness.zone_pair_guards import GuardedPairApproach
    from harness.zone_pair_grasp import PairGraspRelook
    from harness.m2_provider_adapter import ProviderM2DoorStudent

    class RoutedM2(PairGraspRelook, ProviderM2DoorStudent):
        requires_fresh_frame = True

        @property
        def policy(self):
            return execution.policy

        def relative_report(self, now, obs):
            return execution.command_guard.relative_report(now, obs)

        def global_certificate(self, now, beam=None):
            return execution.command_guard.global_certificate(now, beam)

        def begin_scheduled_reobserve(self, now):
            return execution.command_guard.begin_scheduled_reobserve(now)

        def reset_object_anchor(self):
            execution.command_guard.object_anchor = None

        def reset_phase_budget(self, now, phase):
            execution.command_guard.reset_phase_budget(now, phase)

        def align_stop_ready(self, now):
            return execution.command_guard.align_stop_ready(now, self.align_look_started_at)

        def align_look_choices(self):
            from harness.zone_pair_align import ranked_look_pans
            own = execution.own
            guard = execution.command_guard.sweep_guard()
            safety_pose = None
            if self.policy.beam_relative:
                safety_pose = execution.command_guard._pose(own.now)
                if safety_pose is None:
                    return []
            return ranked_look_pans(own.map, own.last_report, own.servo, guard, own.pose,
                                    recovery_v6=self.policy.posterior_relook,
                                    excluded=getattr(self,'relook_excluded',()), safety_pose=safety_pose)

        def preclose_check(self, now, obs):
            return execution.command_guard.preclose_check(now, obs)

        def record_standoff(self, now, obs):
            return execution.command_guard.observe_standoff(now, obs)

        def fail(self, reason, now):
            if reason in ('APPROACH_BLOCKED', 'APPROACH_POSE_UNCERTAIN', 'APPROACH_LOST', 'APPROACH_ARRIVAL_UNCONFIRMED'):
                reason = 'PAIR_APPROACH_' + reason.removeprefix('APPROACH_').lower()
            return super().fail(reason, now)

        def _wait_carry(self, now, arm_idle):
            # Both schedules must contain the same alignment interval. Refuse
            # the frozen runner's optional 'no estimate -> skip alignment' path.
            if self.grasp_estimate is None or not all(finite_number(v) for v in self.grasp_estimate):
                return self.fail('DOOR_POSE_NOT_LOCALIZED', now)
            return super()._wait_carry(now, arm_idle)

        def door_schedule(self, t0):
            a, b = plan['route'][self.seg:self.seg + 2]
            self.door_plan['axis_y_m'] = a[1]
            schedule = role_door_schedule(self, t0, execution.roles)
            start, _, _ = schedule[-1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            lateral = abs(dy) > 1e-6
            axis = 'lateral' if lateral else 'axial'
            duration = math.hypot(dx, dy) / (m2.study.SPEED_M_S * m2.study.CARRY_ODOM_SCALE[axis])

            def leg_command(sign):
                return {'forward': sign * math.copysign(m2.study.SPEED_M_S, dx) / m2.study.FORWARD_GAIN
                        if not lateral else 0.,
                        'left': sign * math.copysign(m2.study.SPEED_M_S, dy) / m2.study.LEFT_GAIN
                        if lateral else 0., 'turn': 0.}
            sign = carry_role_sign(self.rid, execution.roles)
            command = leg_command(sign)
            if self.policy.carry_lateral_lag and axis in v6e_carry.LAG_AXES:
                # v6e: invert the calibrated loaded first-order-lag plant (harness/owncam_carry_v6e.py)
                duration = v6e_carry.leg_duration(math.hypot(dx, dy), axis,
                                                  [command['forward'], command['left'], command['turn']], params)
            schedule[-1] = (start, start + duration, command)
            if self.policy.carry_pair_yaw:
                # v6e carry_pair_yaw: the partner's command of this leg is the SAME plan function with the partner's
                # role sign (route leg from the static plan, roles fixed by the order sheet); nothing is received.
                partner = leg_command(carry_role_sign(execution.partner_id, execution.roles))
                v6e_carry.set_partner_plan(execution.own.pose, start, start + duration, own=command, partner=partner)
            claim = self.claims['segments'][-1]
            claim.pop('axial_m', None)
            claim.update(axis=axis, distance_m=math.hypot(dx, dy), static_from_xy=list(a), static_to_xy=list(b))
            if self.policy.carry_pair_yaw:
                claim['pair_partner_command'] = {'source': 'route plan + role sign (no message)', **partner}
            return schedule

    own, rid = execution.own, execution.own.robot_id
    driver = GuardedPairApproach(own, copy.deepcopy(params),
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


class PairExecution(legacy.PairExecution):
    def __init__(self, own, status, arguments, plan, params, factory=m2_controller, *, policy='v5h'):
        from harness.zone_pair_v6_policy import pair_policy
        self.policy = pair_policy(policy)
        self.own, self.status = own, status
        self.roles = (PairRoles.from_mapping(plan['role_to_robot'])
                      if 'role_to_robot' in plan else LEGACY_ROLES)
        self.partner_id = self.roles.partner(own.robot_id)
        if (arguments['role'] != self.roles.role(own.robot_id)
                or status.robot_id != own.robot_id
                or tuple(status.channel.participants) != self.roles.participants):
            raise ValueError('PAIR_SUBMISSION_MISMATCH')
        self.poll_s = ARM_S
        self.plan, self.calibration_sha256 = copy.deepcopy(plan), _digest(params)
        self.arguments, self.port = dict(arguments), _OwnPort(own)
        self.events, self.inputs = [], []
        self.terminal, self.started, self.cleared = False, False, False
        self.job_id = None
        self.last_phase = None
        self.rendezvous_deadline = own.now + 5.
        self.next_control = own.now
        self.control_started = False
        self.arm_wait_at = None
        self.controller = factory(self, copy.deepcopy(plan), copy.deepcopy(params))
        from harness.zone_pair_guards import PairCommandGuard
        self.command_guard = PairCommandGuard(self)


class PairTeam(legacy.PairTeam):
    def __init__(self, *args, controller_factory=m2_controller, **kwargs):
        super().__init__(*args, controller_factory=controller_factory, **kwargs)
        self._role_source_record = None

    def start(self, rid, item_ref=None, target_zone=None, partner_id=None, role=None, *, now):
        ex = self.executors[rid]
        ex.now = now
        args = {'order_id': ex._token(item_ref), 'target_ref': ex._token(target_zone),
                'role': role if role is not None else dict(zip(PAIR, ('end_neg', 'end_pos'))).get(rid)}
        def refuse(reason):
            # Only this API caller can receive a refusal event. There is no
            # host notification API addressed to an arbitrary partner.
            if reason in ('PAIR_SUBMISSION_MISMATCH', 'PAIR_STATIC_INPUT_MISMATCH'):
                ex._emit(now, 'pair_refused', reason=reason)
            return ex._ack('pair_carry', args, False, reason)
        if not all(isinstance(v, str) and v for v in (item_ref, target_zone, partner_id)):
            return refuse('BAD_PAIR_ARGUMENTS')
        # A busy actor cannot use spec equality (or alter a waiting peer) as an oracle.
        if ex.job is not None:
            return refuse('SELF_BUSY')
        if ex.stopped is not None:
            return refuse('SELF_STOPPED')
        # Preserve the legacy API's mismatch outcome for the already addressed
        # r1/r2 request. Explicit role requests select only their own pair.
        if role is None:
            legacy_pending = next((s for s in reversed(self.sessions)
                                   if not s['closed'] and len(s['endpoints']) == 1
                                   and 'role_to_robot' not in s['plan']
                                   and rid in s['channel'].participants and rid not in s['endpoints']), None)
            if legacy_pending:
                first = next(iter(legacy_pending['endpoints'].values()))
                if now < first.rendezvous_deadline - EPS and partner_id != first.own.robot_id:
                    legacy_pending['submissions'][rid] = (item_ref, target_zone, partner_id)
                    first.abort(now, 'PAIR_SUBMISSION_MISMATCH')
                    legacy_pending['closed'] = True
                    self.poll(now)
                    return refuse('PAIR_SUBMISSION_MISMATCH')
        try:
            roles = requested_roles(rid, partner_id, role)
        except ValueError as exc:
            return refuse(str(exc))
        if partner_id not in self.executors:
            return refuse('UNSUPPORTED_PAIR')
        # Inspect submitted requests, never the other robot's private state.
        pending = next((s for s in reversed(self.sessions) if len(s['endpoints']) == 1
                        and set(s['channel'].participants) == set(roles.participants)
                        and rid not in s['endpoints'] and not s['closed']), None)
        if pending:
            first = next(iter(pending['endpoints'].values()))
            if now >= first.rendezvous_deadline - EPS:
                first.abort(now, 'PAIR_RENDEZVOUS_TIMEOUT')
                pending['closed'] = True
                self.poll(now)
                pending = None  # own fresh request is independent of a peer's expired attempt
        if pending:
            expected = pending['submissions'][first.own.robot_id]
            if ((item_ref, target_zone, partner_id) != (expected[0], expected[1], first.own.robot_id)
                    or roles != first.roles):
                pending['submissions'][rid] = (item_ref, target_zone, partner_id)
                first.abort(now, 'PAIR_SUBMISSION_MISMATCH')
                pending['closed'] = True
                self.poll(now)
                return refuse('PAIR_SUBMISSION_MISMATCH')
        if self.contact_profile != CONTACT_PROFILE or self.weld is not False:
            return refuse('PAIR_REQUIRES_NOSLIP_WELD_OFF')
        if _digest(ex.params) != _digest(self.params):
            return refuse('PAIR_CALIBRATION_MISMATCH')
        order = ex.orders.get(item_ref)
        if order is None:
            return refuse('UNKNOWN_ORDER')
        if order.get('kind') != 'long_beam' or order.get('count') != 1 or order.get('required_robots') != 2:
            return refuse('UNSUPPORTED_PAIR_ORDER')
        if target_zone != order.get('destination_zone') or target_zone not in ex.map['zone_slots']:
            return refuse('WRONG_PAIR_DESTINATION')
        state = ex.pair_readiness(now, item_ref, target_zone)
        if state != 'available':
            return refuse('SELF_' + state.upper())
        try:
            # Both actors compute from their own configured static inputs.
            plan_kw = {'role_to_robot': roles.mapping()} if role is not None else {}
            plan = (make_plan(ex.map, self.sheets.get(item_ref), target_zone, self.policy.carry_end_inset_m, **plan_kw)
                    if self.policy.carry_end_inset_m else make_plan(ex.map, self.sheets.get(item_ref), target_zone, **plan_kw))
            if pending and _digest(plan) != _digest(first.plan):
                pending['submissions'][rid] = (item_ref, target_zone, partner_id)
                first.abort(now, 'PAIR_STATIC_INPUT_MISMATCH')
                pending['closed'] = True
                self.poll(now)
                return refuse('PAIR_STATIC_INPUT_MISMATCH')
            if pending is None:
                # No host-wide sequence number exposing another actor's past attempts.
                channel = PairStatusChannel('pair-' + uuid.uuid4().hex, participants=roles.participants,
                                            heartbeat_timeout_s=self.heartbeat_timeout_s)
                if role is not None and self._role_source_record is None:
                    self._role_source_record = controller_source_record()
                session = {'channel': channel, 'endpoints': {}, 'submissions': {}, 'acks': {},
                           'plan': copy.deepcopy(plan), 'calibration_sha256': _digest(self.params),
                           'closed': False}
            else:
                session, channel = pending, pending['channel']
            ep = PairExecution(ex, PairStatusEndpoint(channel, rid), args, plan, self.params, self.factory,
                               policy=self.policy.name)
        except (ValueError, KeyError, TypeError):
            return refuse('INVALID_PAIR_PLAN')
        ep.rendezvous_deadline = now + self.rendezvous_timeout_s
        ex._pair = ep
        ack = _pair_carry(ex, item_ref, target_zone, partner_id, role)  # ONLY the caller's job
        if not ack['accepted']:
            ex._pair = None
            return ack
        session['endpoints'][rid] = ep
        session['submissions'][rid] = (item_ref, target_zone, partner_id)
        session['acks'][rid] = ack
        if pending is None:
            self.sessions.append(session)
        self.cancel_scheduled(rid, now, 'pair_submission')
        return ack

    def records(self):
        rows = super().records()
        for row in rows:
            row['profile'] = PROFILE
            if 'role_to_robot' in row['plan']:
                row.update(role_profile=ROLE_PROFILE,
                           role_to_robot=row['plan']['role_to_robot'],
                           role_assignment_sha256=row['plan']['role_assignment_sha256'],
                           **copy.deepcopy(self._role_source_record))
        return rows


def _pair_carry(self, item_ref=None, target_zone=None, partner_id=None, role=None):
    """Submit this robot only; the partner must independently submit the identical task."""
    from harness.zone_own_executor import TERMINAL_STOP
    args = {'order_id': self._token(item_ref), 'target_ref': self._token(target_zone),
            'role': role if role is not None else {'r1': 'end_neg', 'r2': 'end_pos'}.get(self.robot_id)}
    if not all(isinstance(v, str) and v for v in (item_ref, target_zone, partner_id)):
        return self._ack('pair_carry', args, False, 'BAD_PAIR_ARGUMENTS')
    if self.stopped is not None:
        return self._ack('pair_carry', args, False, TERMINAL_STOP)
    if self._pair is None or self._pair.arguments != args or self._pair.partner_id != partner_id:
        return self._ack('pair_carry', args, False, 'PAIR_REQUIRES_TEAM_DISPATCH')
    state = self.pair_readiness(self.now, item_ref, target_zone)
    if state != 'available':
        return self._ack('pair_carry', args, False, 'SELF_' + state.upper())
    ack = self._start('pair_carry', 'pair_carry', args)
    if ack['accepted']:
        self._pending_hold = False
        self._pair.job_id = ack['job_id']
        self._pair.status.tick('start_ready', self.now)
        self.job.phase = 'waiting_partner'
    return ack
