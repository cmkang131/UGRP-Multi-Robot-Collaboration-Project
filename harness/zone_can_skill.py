"""T04 local can manipulation: own RGB approach -> lift proofs -> release.

Opt-in via can_skill_registry.create_skill; not a replacement for a sealed M1
executor. A navigation owner must bring the robot to the near pickup view and,
after holding, to the public destination. Navigation waypoints are never proof
of delivery. This module issues normal arm/mecanum/hold commands but never
owns a simulator/peer or consumes setup identities. No external model calls.
"""
from __future__ import annotations

import copy
import math

from harness import visual_arm_v3 as arm
from harness import wrist_can as vision
from harness.can_skill_registry import CAN
from harness.m1_owncam_contract import M1ContractError, require_m1_source
from harness.owncam_pose_source import PoseLimits, check_limits
from harness.pose_provider import is_own_pose_provider
from harness.zone_own_guards import OwnPose, _rect_distance
from harness.zone_own_guards_v3 import SweepGuardV3

STATES = ('approach', 'lower', 'close', 'lift_first', 'lift_second',
          'holding', 'release_lower', 'release_open', 'release_look', 'released_visual', 'failed')
VIEWS = ({1: 2000, 3: 800, 4: 2300, 5: 1600, 6: 1500},
         {1: 2000, 3: 700, 4: 2300, 5: 1600, 6: 1500},
         {1: 2000, 3: 600, 4: 2300, 5: 1600, 6: 1500})
LIMITS = PoseLimits(.025, .035, max_age_s=.25, name='can_local_v1')
SETTLE_S = .6
PHASE_LIMIT_S = 45.


class _CanGuard(SweepGuardV3):
    """Keep the v3 robot envelope, add the taller can at the actual v3 pad."""
    def arm_clearance(self, servo, pose, *, loaded):
        best, hit = super().arm_clearance(servo, pose, loaded=False)
        if loaded:
            x, y, z = arm.forward_grip(servo)
            z += CAN.height_m / 2 - CAN.grasp_height_m
            radius = math.hypot(CAN.diameter_m / 2, CAN.height_m / 2)
            c, s = math.cos(pose.yaw), math.sin(pose.yaw)
            wx, wy = pose.x + c*x - s*y, pose.y + s*x + c*y
            margin = self.margin(pose, math.hypot(x, y))
            for box in self.boxes:
                if z - radius >= box['height'] + margin:
                    continue
                clearance = _rect_distance(box, wx, wy) - radius - margin
                if clearance < best:
                    best, hit = clearance, box['id']
        return best, hit


class CanSkill:
    """One local attempt. Rejected/unknown evidence never becomes completion.

    ``step(now, obs)`` feeds the validated JPEG to a registered own-camera pose
    provider. ``on_command`` receives its own issued port log, not measured
    joints. The caller retains raw frames/commands and the localizer provenance.
    ``request_release`` is an intent; fresh own holding and zone containment
    still have to pass. ``released_visual`` remains distinct from referee success.
    """
    def __init__(self, robot_id, static_map, *, destination_zone, pose_source):
        if robot_id not in ('r1', 'r2', 'r3') or destination_zone not in ('A', 'B', 'C'):
            raise ValueError('unsupported robot/zone')
        if not is_own_pose_provider(pose_source):
            raise ValueError('can requires a registered own-camera pose provider')
        require_m1_source(pose_source.source)
        self.pose = pose_source
        self.robot_id = robot_id
        self.map = copy.deepcopy(static_map)
        self.zone = copy.deepcopy(self.map['regions']['zone_' + destination_zone])
        self.bounds = tuple(self.map['bounds_m'])
        self.guard = _CanGuard(self.map)
        self.phase, self.reason = 'approach', 'awaiting_own_rgb'
        self.servo = {}
        self.last_command_t = -math.inf
        self.last_arm_t = -math.inf
        self.last_motion_end = -math.inf
        self.last_frame_id = None
        self.now = None
        self.started = None
        self.phase_started = None
        self.view_index = 0
        self.target_xy = None
        self.proofs = 0
        self.release_requested = False
        self.log = []
        self.last_evidence = None
        self.evidence_time = -math.inf
        self.anchor_pose = None

    def _bad_command(self, reason):
        self.phase, self.reason = 'failed', reason
        raise ValueError(reason)

    def on_command(self, row):
        """Only the own command channel can acknowledge emitted PWM changes."""
        t = row.get('t')
        if (row.get('robot_id') != self.robot_id or type(t) not in (int, float)
                or not math.isfinite(t) or t < self.last_command_t):
            self._bad_command('invalid_own_command')
        kind = row.get('kind')
        if kind == 'initial_servo_command' and not self.servo:
            pulses = row['pulses']
            values = {int(k): v for k, v in pulses.items()}
            if set(values) != {1, 3, 4, 5, 6} or any(type(v) is not int or not 500 <= v <= 2500
                                                     for v in values.values()):
                self._bad_command('invalid initial own PWM')
            self.servo = values
            self.last_arm_t = t
        elif kind == 'arm':
            sid, pulse = row.get('servo_id'), row.get('pulse')
            if type(sid) is not int or sid not in self.servo or type(pulse) is not int or not 500 <= pulse <= 2500:
                self._bad_command('invalid own PWM')
            self.servo[sid] = pulse
            self.last_arm_t = t
            self.evidence_time = -math.inf
        elif kind == 'mecanum':
            duration = row.get('duration_s')
            if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 1:
                self._bad_command('invalid own movement duration')
            speeds = [row.get(k) for k in ('forward', 'left', 'turn')]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in speeds):
                self._bad_command('invalid own movement')
            if any(speeds) and self.phase not in ('approach', 'holding'):
                self._bad_command('base_moved_during_manipulation')
            self.last_motion_end = t + duration
        elif kind != 'hold':
            self._bad_command('unsupported own command')
        self.last_command_t = t
        self.pose.on_command(row)

    def request_release(self):
        if self.phase != 'holding':
            raise ValueError('release requires own-RGB holding')
        self.release_requested = True

    def _set(self, phase, now, reason):
        self.phase, self.phase_started, self.reason = phase, now, reason
        self.proofs = 0
        self.log.append({'t': now, 'phase': phase, 'reason': reason})

    def _result(self, commands=None):
        return {'mode': 'tick', 'commands': commands or [{'kind': 'hold'}],
                'phase': self.phase, 'reason': self.reason,
                'holding': 'yes' if (self.phase == 'holding' and self.now is not None
                                     and self.now - self.evidence_time <= .25) else 'unknown',
                'release_visual': self.phase == 'released_visual',
                'delivery_success': None, 'skill_id': CAN.skill_id}

    def _fail(self, now, reason):
        self._set('failed', now, reason)
        return self._result()

    def _within_map(self, pose):
        x0, x1, y0, y1 = self.bounds
        margin = .25 + 3 * pose.std_xy
        return x0 + margin <= pose.x <= x1 - margin and y0 + margin <= pose.y <= y1 - margin

    def _arm_to(self, target, pose, now, *, loaded=False):
        target = {**self.servo, **target}
        # Check exactly the simultaneous increment that will be issued below.
        # The sealed guard clips long paths at 60 PWM per tick, whereas this
        # skill issues 40. Unequal joint remainders make those paths different.
        # Every delta here is <=40, so the guard samples this single increment
        # (including its start and interior), with no 60-PWM waypoint to diverge.
        next_servo = {k: self.servo[k] + max(-40, min(40, v-self.servo[k]))
                      for k, v in target.items()}
        if not self.guard.transition_clear(self.servo, next_servo, pose, loaded=loaded):
            return self._fail(now, 'static_arm_sweep_blocked')
        commands = [{'kind': 'arm', 'servo_id': k, 'pulse': v,
                     'duration_ms': 100} for k, v in sorted(next_servo.items()) if self.servo[k] != v]
        if commands:
            return self._result([{'kind': 'hold'}, *commands])
        if now - self.last_arm_t < SETTLE_S:
            return self._result()
        return None

    def _grip_pose(self, height):
        return arm.solve_grip_site_ik((CAN.grasp_forward_m, 0., height), preferred_pitch_deg=-66.)

    def _zone_contains(self, pose, xy):
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        wx, wy = pose.x + c*xy[0] - s*xy[1], pose.y + s*xy[0] + c*xy[1]
        cx, cy = self.zone['center_m']
        hx, hy = self.zone['half_extents_m']
        margin = CAN.diameter_m/2 + 3*pose.std_xy + 3*pose.std_yaw*math.hypot(*xy) + .01
        return abs(wx-cx) + margin < hx and abs(wy-cy) + margin < hy

    def step(self, now, obs):
        if self.phase in ('failed', 'released_visual'):
            return self._result()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or self.now is not None and now < self.now):
            return self._fail(self.now, 'invalid_clock')
        self.now = now
        if self.started is None:
            self.started = self.phase_started = now
        if now - self.started >= CAN.max_sim_s:
            return self._fail(now, 'local_sim_cap')
        if self.phase != 'holding' and now - self.phase_started >= PHASE_LIMIT_S:
            return self._fail(now, 'phase_timeout')
        try:
            frame = vision.decode_own(obs, robot_id=self.robot_id, previous_frame_id=self.last_frame_id, now=now)
            own_pose = self.pose.on_frame(now, frame[..., ::-1].copy())
            require_m1_source(own_pose.source)
            if check_limits(own_pose, now, LIMITS):
                raise ValueError('uncertain/stale pose')
            pose = OwnPose.from_report(own_pose)
            if pose is None or min(pose.std_xy, pose.std_yaw) < 0:
                raise ValueError('invalid pose')
            if not self.servo or self.last_command_t > obs['sim_time'] or not self._within_map(pose):
                raise ValueError('unsupported pose/command history')
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
            return self._fail(now, 'input_refused:' + str(exc))
        self.last_frame_id = obs['frame_id']
        if (self.phase not in ('approach', 'holding') and self.anchor_pose is not None
                and (math.hypot(pose.x-self.anchor_pose.x, pose.y-self.anchor_pose.y) > .015
                     or abs(math.atan2(math.sin(pose.yaw-self.anchor_pose.yaw),
                                       math.cos(pose.yaw-self.anchor_pose.yaw))) > .04)):
            return self._fail(now, 'own_pose_shifted_during_manipulation')
        if now < self.last_motion_end + .15:
            return self._result()

        if self.phase == 'approach':
            waiting = self._arm_to(VIEWS[self.view_index], pose, now)
            if waiting:
                return waiting
            seen = vision.floor_can(frame, self.servo)
            self.last_evidence = seen
            if seen.answer != 'yes':
                self.proofs = 0
                self.reason = seen.reason
                return self._result()
            x, y, _ = seen.center_base_m
            if self.view_index == 0 and x <= .32 or self.view_index == 1 and x <= .26:
                self.view_index += 1
                self.proofs = 0
                return self._result()
            if not .194 <= x <= .65 or abs(y) > .12:
                return self._fail(now, 'unsupported_relative_pose')
            ex = x - CAN.grasp_forward_m
            if abs(ex) <= .006 and abs(y) <= .004:
                self.proofs += 1
                if self.proofs >= 2:
                    self.target_xy = (x, y)
                    self.anchor_pose = pose
                    self._set('lower', now, 'two_own_rgb_floor_centers')
                return self._result()
            self.proofs = 0
            forward, left = max(-.015, min(.025, ex*.5)), max(-.015, min(.015, y*.5))
            if not self.guard.translation_clear(self.servo, pose, forward*.1, left*.1, loaded=False):
                return self._fail(now, 'static_approach_sweep_blocked')
            return self._result([{'kind': 'mecanum', 'forward': forward, 'left': left,
                                  'turn': 0., 'duration_s': .1}])

        if self.phase in ('lower', 'close', 'lift_first', 'lift_second', 'release_lower', 'release_open'):
            phase = self.phase
            height = {'lift_first': CAN.lift_heights_m[0], 'lift_second': CAN.lift_heights_m[1]}.get(
                phase, CAN.grasp_height_m)
            opened = phase in ('lower', 'release_open')
            target = {**self._grip_pose(height), 1: CAN.open_pwm if opened else CAN.close_pwm}
            if phase.startswith('release') and not self._zone_contains(pose, (CAN.grasp_forward_m, 0.)):
                return self._fail(now, 'release_outside_public_zone')
            waiting = self._arm_to(target, pose, now, loaded=phase != 'lower')
            if waiting:
                return waiting
            transitions = {'lower': 'close', 'close': 'lift_first',
                           'release_lower': 'release_open', 'release_open': 'release_look'}
            if phase in transitions:
                self._set(transitions[phase], now, 'issued_posture_settled_not_grasp_proof')
                return self._result()
            seen = vision.attached_can(frame, self.servo)
            self.last_evidence = seen
            self.evidence_time = now if seen.answer == 'yes' else -math.inf
            self.proofs = self.proofs + 1 if seen.answer == 'yes' else 0
            if self.proofs >= 2:
                self._set('lift_second' if phase == 'lift_first' else 'holding', now,
                          'two_height_rim_attachment' if phase == 'lift_second' else 'first_lift_rim')
            else:
                self.reason = seen.reason
            return self._result()

        if self.phase == 'holding':
            seen = vision.attached_can(frame, self.servo)
            self.last_evidence = seen
            self.evidence_time = now if seen.answer == 'yes' else -math.inf
            if seen.answer != 'yes':
                return self._fail(now, 'holding_lost_or_unobservable')
            if self.release_requested:
                if not self._zone_contains(pose, (CAN.grasp_forward_m, 0.)):
                    return self._fail(now, 'release_outside_public_zone')
                self.anchor_pose = pose
                self._set('release_lower', now, 'own_pose_inside_public_zone')
            return self._result()

        if self.phase == 'release_look':
            waiting = self._arm_to(VIEWS[2], pose, now)
            if waiting:
                return waiting
            seen = vision.floor_can(frame, self.servo)
            self.last_evidence = seen
            valid = (seen.answer == 'yes' and abs(seen.center_base_m[0] - CAN.grasp_forward_m) < .025
                     and abs(seen.center_base_m[1]) < .025
                     and self._zone_contains(pose, seen.center_base_m[:2]))
            self.proofs = self.proofs + 1 if valid else 0
            if self.proofs >= 2:
                self._set('released_visual', now, 'two_own_rgb_floor_release_views')
            else:
                self.reason = 'release_unconfirmed'
            return self._result()
        return self._fail(now, 'unknown_state')
