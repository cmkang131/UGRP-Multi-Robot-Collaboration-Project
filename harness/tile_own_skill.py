"""T05 opt-in west tile manipulation candidate. No navigation/host dispatch.

Own JPEG -> bounded low arm target -> issued-command history -> post-lift
holding -> requested lowering/opening -> RGB release belief. A coordinator may
use this skill after own-camera navigation and while transporting; it must stop
navigation whenever ``carry_permitted`` is false. ``request_release`` is the
robot policy's intent, NOT a host arrival receipt. No method accepts a referee
result, partner state, measured servo state or an externally estimated target.

The existing sealed executor remains unchanged. Completion here is only local
manipulation; this module never returns a delivery-success field.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import math

import cv2
import numpy as np

from harness import tile_own_vision as vision
from harness import visual_arm_v3 as arm
from harness.zone_study_inputs import FORMATIONS

PROFILE = 'tile-west-manipulation-dev1'
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
STATES = ('search', 'open', 'lower', 'close', 'lift', 'verify_hold', 'holding',
          'lower_release', 'open_release', 'inspect_release', 'verify_release', 'done', 'failed')
GRASP_Z_RANGE_M = (.006, .008)  # command target bounds, not a physical clearance measurement
TARGET_X_RANGE_M = (.176, .180)  # v3 candidate; SDK box calibration does not cover low tile
OPEN_PWM, CLOSED_PWM = 2000, 1500
SETTLE_S, FRAME_MAX_AGE_S, STAGE_LIMIT_S, SIM_LIMIT_S = .5, .25, 12., 900.
CONFIRM_FRAMES = 2


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def low_pose(xy, *, height_m=vision.GRASP_HEIGHT_M):
    """v3 command IK; do not silently clamp a box height into the tile range."""
    if not _finite(height_m) or not GRASP_Z_RANGE_M[0] <= height_m <= GRASP_Z_RANGE_M[1]:
        raise ValueError('TILE_GRASP_HEIGHT_OUT_OF_RANGE')
    if len(xy) != 2 or not all(_finite(v) for v in xy):
        raise ValueError('TILE_TARGET_INVALID')
    if not TARGET_X_RANGE_M[0] <= xy[0] <= TARGET_X_RANGE_M[1] or abs(xy[1]) > .005:
        raise ValueError('TILE_TARGET_OUTSIDE_DEV_ENVELOPE')
    pose = arm.solve_grip_site_ik((*xy, height_m), preferred_pitch_deg=-40., calibrated_grasp_only=False)
    actual = arm.forward_grip(pose)  # commanded FK only, never physical joint readings
    if abs(actual[2] - height_m) > .001 or math.dist(actual[:2], xy) > .002:
        raise ValueError('TILE_COMMAND_IK_RESIDUAL')
    if vision.grip_mask(pose, (640, 480)).mean() > .95:
        raise ValueError('TILE_HOLD_UNOBSERVABLE')
    return pose


class TileWestSkill:
    def __init__(self, *, robot_id, order, role, condition_name):
        if robot_id not in ('r1', 'r2', 'r3') or condition_name not in CONDITIONS:
            raise ValueError('TILE_ACTOR_OR_CONDITION_UNSUPPORTED')
        if role != 'west' or FORMATIONS['tile'] != ('west',):
            raise ValueError('TILE_ROLE_UNSUPPORTED: public contract and this candidate are west only')
        if (order.get('kind') != 'tile' or type(order.get('count')) is not int or order['count'] != 1
                or type(order.get('required_robots')) is not int or order['required_robots'] != 1
                or order.get('identity') != 'kind_fungible'
                or order.get('item_ids') not in ([], ()) or order.get('destination_zone') not in ('B', 'C')
                or not isinstance(order.get('order_id'), str) or not order['order_id']):
            raise ValueError('TILE_ORDER_UNSUPPORTED: one fungible tile to B/C')
        self.robot_id, self.role = robot_id, role
        self.order_id, self.destination = order['order_id'], order['destination_zone']
        # No condition-specific controller/config/sensor/memory branch.
        self.state, self.reason = 'search', None
        self.pose, self.initial_pose = {}, None
        self.command_time = -math.inf
        self.command_serial, self.pose_serial, self.pose_time = 0, {}, {}
        self.pending_after = 0
        self.arm_time = -math.inf
        self.motion_until = -math.inf
        self.last_frame_id, self.frame_time = -1, -math.inf
        self.frame_command_time = -math.inf
        self.view = vision.TileView()
        self.grasp_pose, self.lift_pose, self.target_xy = None, None, None
        self.started, self.entered, self.now = None, None, -math.inf
        self.pending = None
        self.command_sent = False
        self.last_counted = -1
        self.streak, self.previous_target = 0, None
        self.hold_streak, self.absent_streak = 0, 0
        self.release_requested = False
        self.last_hold_yes = -math.inf
        self.events = []

    def manifest(self):
        return {'controller': PROFILE, 'vision': vision.PROFILE, 'robot_model': 'masterpi_v3',
                'kind': 'tile', 'dimensions_m': vision.DIMENSIONS_M, 'mass_kg': vision.MASS_KG,
                'grasp_height_m': vision.GRASP_HEIGHT_M, 'roles': ('west',),
                'target_x_m': TARGET_X_RANGE_M, 'target_abs_y_max_m': .005,
                'grasp_height_range_m': GRASP_Z_RANGE_M, 'confirm_frames': CONFIRM_FRAMES,
                'settle_s': SETTLE_S, 'max_frame_age_s': FRAME_MAX_AGE_S, 'stage_limit_s': STAGE_LIMIT_S,
                'state_enum': STATES, 'sensor': 'own_robot_cam', 'memory': 'own-issued-pwm-and-two-frames-v1',
                'sim_cap_s': SIM_LIMIT_S, 'physical_validation': 'unmeasured'}

    def role_assignment(self):
        """Hash separately from controller/config, even when the actor changes."""
        return {'robot_id': self.robot_id, 'role': self.role, 'order_id': self.order_id,
                'destination_zone': self.destination}

    def on_command(self, row):
        """Only a command actually issued at this actor's port, never a servo measurement."""
        t = row.get('t')
        if row.get('robot_id') != self.robot_id or not _finite(t) or t < self.command_time:
            raise ValueError('TILE_OWN_COMMAND_REQUIRED')
        kind = row.get('kind')
        if kind == 'initial_servo_command':
            if self.initial_pose is not None:
                raise ValueError('TILE_HISTORY_RESET_FORBIDDEN')
            updates = {int(k): v for k, v in row['pulses'].items()}
            if set(updates) != {1, 3, 4, 5, 6}:
                raise ValueError('TILE_INITIAL_COMMAND_INCOMPLETE')
        elif kind == 'arm':
            updates = {row['servo_id']: row['pulse']}
        elif kind == 'look':
            updates = {6: row['pan_pulse']}
        elif kind in ('hold', 'mecanum'):
            updates = {}
        else:
            raise ValueError('TILE_COMMAND_UNSUPPORTED')
        if any(k not in (1, 3, 4, 5, 6) or isinstance(v, bool) or not isinstance(v, int)
               or not 500 <= v <= 2500 for k, v in updates.items()):
            raise ValueError('TILE_PWM_OUT_OF_RANGE')
        if kind == 'mecanum':
            if not all(_finite(row.get(k)) for k in ('forward', 'left', 'turn', 'duration')) or row['duration'] < 0:
                raise ValueError('TILE_MOTION_COMMAND_INVALID')
            self.motion_until = max(self.motion_until, t + row['duration'])
            self.previous_target, self.streak = None, 0
            if self.state not in ('search', 'holding', 'failed', 'done'):
                self._fail('BASE_MOVED_DURING_MANIPULATION')
        if any(self.pose.get(k) != v for k, v in updates.items()):
            self.arm_time = t
            if self.state == 'search':
                self.previous_target, self.streak = None, 0
        self.command_serial += 1
        self.pose_serial.update({k: self.command_serial for k in updates})
        self.pose_time.update({k: t for k in updates})
        self.pose.update(updates)
        if kind == 'initial_servo_command':
            self.initial_pose = dict(self.pose)
        self.command_time = t

    def on_frame(self, now, obs):
        """Hash and decode the same own JPEG; ignore all non-camera envelope fields."""
        fid, t = obs.get('frame_id'), obs.get('sim_time')
        if (not _finite(now) or now < self.now or not _finite(t) or not 0 <= now - t <= FRAME_MAX_AGE_S
                or t < self.frame_time or t < self.command_time or isinstance(fid, bool)
                or not isinstance(fid, int) or fid <= self.last_frame_id
                or obs.get('robot_id') != self.robot_id or obs.get('camera') != 'robot_cam'
                or self.initial_pose is None):
            self._fail('OWN_IMAGE_INVALID')
            return
        try:
            jpeg = base64.b64decode(obs['image'], validate=True)
            if hashlib.sha256(jpeg).hexdigest() != obs.get('sha256'):
                raise ValueError('hash mismatch')
            bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if bgr is None or bgr.shape != (480, 640, 3):
                raise ValueError('unexpected camera size')
            view = vision.inspect(bgr, self.pose, grasp_pose=self.grasp_pose)
        except (ValueError, KeyError, TypeError, binascii.Error, cv2.error):
            self._fail('OWN_IMAGE_INVALID')
            return
        self.last_frame_id, self.frame_time, self.frame_command_time = fid, t, self.arm_time
        self.view = view

    def _fail(self, reason):
        if self.state not in ('failed', 'done'):
            self.state, self.reason, self.pending = 'failed', reason, None
            self.events.append({'event': 'skill_failed', 'reason': reason})

    def abort(self):
        self._fail('CANCELLED')

    def _enter(self, state, now, pose=None):
        self.state, self.entered = state, now
        self.pending, self.command_sent = copy.deepcopy(pose), False
        self.streak, self.hold_streak, self.absent_streak = 0, 0, 0
        self.last_counted = self.last_frame_id

    def _fresh(self, now):
        return (0 <= now - self.frame_time <= FRAME_MAX_AGE_S and self.frame_command_time == self.arm_time
                and self.frame_time >= self.arm_time + SETTLE_S and self.frame_time >= self.motion_until)

    def carry_permitted(self, now):
        return self.state == 'holding' and self._fresh(now) and self.view.holding == 'yes'

    def request_release(self, *, now, destination_zone):
        if destination_zone != self.destination or not self.carry_permitted(now):
            raise ValueError('TILE_RELEASE_REQUIRES_FRESH_OWN_HOLD_AND_ORDER_ZONE')
        self.release_requested = True

    def status(self, now):
        return {'phase': self.state, 'reason': self.reason, 'holding': self.view.holding if self._fresh(now) else 'unknown',
                'carry_permitted': self.carry_permitted(now), 'skill_complete': self.state == 'done',
                'release_belief': 'own_rgb_released' if self.state == 'done' else 'unconfirmed',
                'order_id': self.order_id, 'role': self.role}

    def step(self, now):
        if not _finite(now) or now < self.now or now < self.command_time:
            self._fail('OWN_CLOCK_INVALID')
            return self._output()
        self.now = now
        if self.started is None:
            self.started = self.entered = now
        if self.state in ('failed', 'done'):
            return self._output()
        if now - self.started >= SIM_LIMIT_S:
            self._fail('SIM_LIMIT')
        elif self.state != 'holding' and now - self.entered >= STAGE_LIMIT_S:
            self._fail('TILE_NOT_DETECTED' if self.state == 'search' else 'STAGE_TIMEOUT_' + self.state.upper())
        elif self.state == 'holding' and now - self.frame_time > STAGE_LIMIT_S:
            self._fail('HOLD_OBSERVATION_TIMEOUT')
        elif self.state == 'holding' and now - self.last_hold_yes > STAGE_LIMIT_S:
            self._fail('HOLD_UNCONFIRMED')
        if self.state == 'failed' or self.initial_pose is None:
            return self._output()
        if self.pending is not None:
            if not self.command_sent:
                self.command_sent = True
                self.pending_after = self.command_serial
                return self._output(self.pending)
            # Submission is not execution. Wait for own issued history AND a
            # fresh post-settle RGB frame before advancing the next stage.
            if not all(self.pose.get(k) == v and self.pose_serial.get(k, 0) > self.pending_after
                       for k, v in self.pending.items()) or not self._fresh(now):
                return self._output()
            if self.frame_time < max(self.pose_time[k] for k in self.pending) + SETTLE_S:
                return self._output()
            self.pending = None
            self._advance_arm(now)
            return self._output()
        if not self._fresh(now) or self.last_counted == self.last_frame_id:
            return self._output()
        self.last_counted = self.last_frame_id
        if self.state == 'search':
            xy = self.view.target_xy_m
            if xy is None:
                self.previous_target, self.streak = None, 0
            else:
                self.streak = self.streak + 1 if self.previous_target is not None and math.dist(xy, self.previous_target) <= .008 else 1
                self.previous_target = xy
                if self.streak >= CONFIRM_FRAMES:
                    try:
                        self.grasp_pose = low_pose(xy)
                        self.lift_pose = arm.solve_grip_site_ik((*xy, .070), calibrated_grasp_only=False,
                                             preferred_pitch_deg=arm.tool_pose(self.grasp_pose).pitch_deg)
                    except ValueError:
                        self._fail('TILE_TARGET_OUTSIDE_ARM_ENVELOPE')
                    else:
                        self.target_xy = xy
                        self._enter('open', now, {1: OPEN_PWM})
        elif self.state in ('verify_hold', 'holding'):
            if self.view.holding == 'yes':
                self.last_hold_yes = now
            self.hold_streak = self.hold_streak + 1 if self.view.holding == 'yes' else 0
            self.absent_streak = self.absent_streak + 1 if self.view.holding == 'no' else 0
            if self.absent_streak >= CONFIRM_FRAMES:
                self._fail('TILE_NOT_HELD')
            elif self.state == 'verify_hold' and self.hold_streak >= CONFIRM_FRAMES:
                self._enter('holding', now)
            elif self.state == 'holding' and self.release_requested and self.view.holding == 'yes':
                self._enter('lower_release', now, {**self.grasp_pose, 1: CLOSED_PWM})
        elif self.state == 'verify_release':
            xy = self.view.target_xy_m
            released = (self.view.holding == 'no' and xy is not None and math.dist(xy, self.target_xy) <= .025)
            self.streak = self.streak + 1 if released else 0
            if self.streak >= CONFIRM_FRAMES:
                self._enter('done', now)
                self.events.append({'event': 'skill_complete', 'confirmation': 'own_rgb_released',
                                    'scope': 'local_manipulation_only'})
        return self._output()

    def _advance_arm(self, now):
        transitions = {
            'open': ('lower', {**self.grasp_pose, 1: OPEN_PWM}),
            'lower': ('close', {1: CLOSED_PWM}),
            'close': ('lift', {**self.lift_pose, 1: CLOSED_PWM}),
            'lift': ('verify_hold', None),
            'lower_release': ('open_release', {1: OPEN_PWM}),
            'open_release': ('inspect_release', {**self.initial_pose, 1: OPEN_PWM}),
            'inspect_release': ('verify_release', None),
        }
        state, pose = transitions[self.state]
        self._enter(state, now, pose)

    def _output(self, pose=None):
        commands = [{'kind': 'hold'}]
        if pose is not None:
            commands += [({'kind': 'look', 'pan_pulse': v} if k == 6 else
                          {'kind': 'arm', 'servo_id': k, 'pulse': v}) for k, v in sorted(pose.items())]
        return {'mode': 'tick', 'commands': commands, 'phase': self.state}
