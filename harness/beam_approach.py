"""T08b own-only approach/relative-alignment candidate; no runtime registration.

The caller supplies a continuous own-camera provider, a v3 calibrated RGB beam
observer and an own-only command sweep guard. There is deliberately no world,
spawn pose, partner executor, prior/reset hook, probe setup or carry controller.
Factories are not installed into the frozen executor. See PHYSICS_HANDOFF.md.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from harness import beam_initial_pose_plan as bp
from harness.map_goto import plan_path
from harness.static_keepouts import polygon_at
from harness.zone_pair_status import PairStatusChannel, PROFILE as STATUS_PROFILE

PROFILE = 'beam_approach_t08b_v1'
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
CONFIG = {'sim_cap_s': 900., 'uncertain_timeout_s': 30., 'frame_max_age_s': .25,
          'max_std_xy_m': .025, 'max_std_yaw_rad': .04, 'max_fix_age_s': 2.,
          'prestation_xy_tol_m': .035, 'prestation_yaw_tol_rad': .06,
          'relative_x_tol_m': .012, 'relative_y_tol_m': .008, 'relative_yaw_tol_rad': .035,
          'alignment_frames': 2, 'beam_missing_timeout_s': 5.,
          'command_ack_timeout_s': .5, 'status_start_timeout_s': 5.}


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def wrap(x):
    return (x + math.pi) % (2 * math.pi) - math.pi


def clip(x, limit):
    return max(-limit, min(limit, x))


@dataclass
class OwnApproachMemory:
    """Existing own state, not a probe checkpoint; provider already consumed history.

    ``history`` contains issued port records, including the initial PWM command.
    Servo is reconstructed from those records, never from actuator measurements.
    on_command is the sole new-command delivery path to the provider.
    """
    provider: object
    history: list[dict]
    servo: dict = field(init=False)
    frames: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.servo = {}
        last_t = -math.inf
        for row in self.history:
            if not finite(row.get('t')) or row['t'] < last_t:
                raise ValueError('BAD_OWN_HISTORY')
            last_t = row['t']
            self._servo_command(row)
        if set(self.servo) != set(range(1, 7)):
            raise ValueError('INITIAL_ISSUED_SERVO_REQUIRED')

    def _servo_command(self, row):
        if row['kind'] == 'initial_servo_command':
            self.servo.update({int(k): int(v) for k, v in row['pulses'].items()})
        elif row['kind'] == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif row['kind'] == 'look':
            self.servo[6] = int(row['pan_pulse'])
        if any(not 0 <= v <= 1000 for v in self.servo.values()):
            raise ValueError('BAD_ISSUED_SERVO')


@dataclass(frozen=True)
class Decision:
    action: dict
    phase: str
    status: str
    reason: str | None


class BeamApproach:
    """One robot from its live own RGB belief to two-frame relative alignment.

    RGB observer signature: (BGR frame, issued_servo, role) -> visible,
    end_visible, grip_base_m=[x,y], axis_heading_rad, std_xy_m, std_yaw_rad.
    Coordinates MUST use the v3 chassis frame (mount offset is not zero).
    Sweep guard signature: (action, report, issued_servo, phase) -> bool; it
    must include static walls/terrain, own-RGB hazards and full v3 swept body.
    No permissive default is supplied. These dependencies require separate
    calibrated physical admission; fake tests establish the decision logic only.
    """
    def __init__(self, static_map, sheet, order, *, robot_id, role_assignment,
                 task_id, condition, memory: OwnApproachMemory,
                 observe_beam: Callable, command_clear: Callable,
                 search_servo: dict, started_at: float):
        if (condition not in CONDITIONS or set(role_assignment) != set(bp.ROLES)
                or len(set(role_assignment.values())) != 2
                or not set(role_assignment.values()) <= {'r1', 'r2', 'r3'}
                or robot_id not in role_assignment.values()):
            raise ValueError('UNSUPPORTED_ROLE_ASSIGNMENT_OR_CONDITION')
        if not finite(started_at) or started_at < 0 or not memory.history or started_at > memory.history[0]['t']:
            raise ValueError('BAD_START_TIME')
        if (set(search_servo) != set(range(1, 7))
                or any(type(v) is not int or not 0 <= v <= 1000 for v in search_servo.values())
                or search_servo[1] < 400 or memory.servo[1] < 400):
            raise ValueError('OPEN_SEARCH_POSTURE_REQUIRED')
        self.plan = bp.make_initial_pose_plan(static_map, sheet, order)
        self.map = copy.deepcopy(static_map)
        self.robot_id, self.assignment = robot_id, dict(role_assignment)
        self.role = next(r for r, rid in role_assignment.items() if rid == robot_id)
        self.peer = next(rid for rid in role_assignment.values() if rid != robot_id)
        self.goal = tuple(self.plan['roles'][self.role]['prestation_xyyaw'])
        self.memory, self.observe_beam, self.command_clear = memory, observe_beam, command_clear
        self.search_servo = dict(search_servo)
        self.started_at, self.last_now = started_at, max(started_at, memory.history[-1]['t'])
        self.phase, self.failure = 'localizing', None
        self.status_channel = PairStatusChannel(task_id, (robot_id, self.peer))
        self.last_frame_id, self.last_obs, self.rgb = -1, None, None
        self.pending, self.pending_at, self.settle_until = None, None, started_at
        self.uncertain_since, self.missing_since = None, None
        self.pre_streak = self.aligned_streak = 0
        self.alignment_entry = None
        self.events = []
        self.audit = {'controller': PROFILE, 'config_sha256': bp.digest(CONFIG),
                      'controller_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'search_servo_sha256': bp.digest(search_servo),
                      'memory_version': PROFILE, 'status_profile': STATUS_PROFILE,
                      'sensors': 'own_rgb_only', 'role_assignment_sha256': bp.digest(role_assignment),
                      'map_sha256': self.plan['map_sha256'], 'sheet_sha256': self.plan['sheet_sha256'],
                      'condition': condition, 'physical_ready': False, 'delivery_success': None}

    def receive_status(self, raw, received_at):
        # A local mailbox receives only delivered fixed-enum records; no bus/host handle.
        if raw.get('robot_id') != self.peer or not self.status_channel.publish(raw, received_at):
            self._fail('INVALID_DELIVERED_STATUS', received_at)
            return False
        return True

    def _fail(self, reason, now):
        if self.failure is None:
            self.failure, self.phase = reason, 'failed'
            self.pending = None  # discard all non-issued proposals; stop is always next
            self.events.append({'event': 'failed', 't': now, 'reason': reason})

    def on_command(self, row):
        """ACK exactly the proposed own command after the port actually issued it."""
        action = {k: v for k, v in row.items() if k != 't'}
        if (self.pending is None or action != self.pending or not finite(row.get('t'))
                or row['t'] != self.pending_at or row['t'] < self.memory.history[-1]['t']):
            self._fail('OWN_COMMAND_HISTORY_MISMATCH', self.last_now)
            return False
        self.memory.history.append(copy.deepcopy(row))
        self.memory._servo_command(row)
        duration = action.get('duration_s', 0.)
        self.settle_until = max(self.settle_until, row['t'] + duration)
        self.pending = None
        try:
            self.memory.provider.on_command(copy.deepcopy(row))
        except Exception:
            self._fail('POSE_PROVIDER_COMMAND_ERROR', row['t'])
            return False
        return True

    def _frame(self, obs, now):
        # No actuator_state/evaluation keys are read or forwarded to the provider.
        try:
            frame_id, at = obs['frame_id'], obs['sim_time']
            if (obs['robot_id'] != self.robot_id or obs['camera'] != 'robot_cam'
                    or type(frame_id) is not int or frame_id < 0 or frame_id < self.last_frame_id
                    or not finite(at) or not 0 <= now - at <= CONFIG['frame_max_age_s']):
                raise ValueError('wrong, stale or future own image')
            data = base64.b64decode(obs['image'], validate=True)
            if hashlib.sha256(data).hexdigest() != obs['sha256']:
                raise ValueError('image hash mismatch')
            if frame_id == self.last_frame_id:
                if (obs['sha256'], at) != (self.last_obs['sha256'], self.last_obs['sim_time']):
                    raise ValueError('frame identity changed')
                return False
            if self.last_obs is not None and at <= self.last_obs['sim_time']:
                raise ValueError('frame clock did not advance')
            frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None or frame.ndim != 3 or float(frame.std()) < 1.:
                raise ValueError('undecodable or featureless image')
        except (KeyError, TypeError, ValueError):
            self._fail('OWN_IMAGE_INVALID', now)
            return False
        self.last_obs = {k: obs[k] for k in ('robot_id', 'camera', 'frame_id', 'sim_time', 'sha256')}
        self.memory.frames.append(dict(self.last_obs))
        self.last_frame_id, self.rgb = frame_id, frame
        self.memory.provider.on_frame(at, frame)
        return True

    def _trusted(self, report, now):
        vals = (report.t_est, report.x_m, report.y_m, report.yaw_rad,
                report.std_xy_m, report.std_yaw_rad, report.last_fix_t)
        return (report.initialized is True and all(finite(v) for v in vals)
                and isinstance(report.source, str) and report.source.startswith('owncam_pf')
                and 0 <= now - report.t_est <= CONFIG['frame_max_age_s']
                and 0 <= now - report.last_fix_t <= CONFIG['max_fix_age_s']
                and 0 <= report.std_xy_m <= CONFIG['max_std_xy_m']
                and 0 <= report.std_yaw_rad <= CONFIG['max_std_yaw_rad'])

    def _offer(self, action, now, report=None):
        clear = True
        if action['kind'] != 'hold':
            try:
                clear = self.command_clear(copy.deepcopy(action), report, dict(self.memory.servo), self.phase)
            except Exception:
                self._fail('COMMAND_GUARD_ERROR', now)
                clear = False
        if clear is not True:
            self._fail('APPROACH_OR_ALIGNMENT_BLOCKED', now)
            action = {'kind': 'hold'}
        self.pending, self.pending_at = copy.deepcopy(action), now
        status = ('abort' if self.failure else 'uncertain' if self.uncertain_since is not None
                  else 'aligning' if self.phase in ('aligning', 'aligned') else 'busy')
        # aligned is a local visual claim, never STATUS ready/done or delivery.
        return Decision(action, self.phase, status, self.failure)

    def _hold(self, now):
        return self._offer({'kind': 'hold'}, now)

    def _move(self, now, report, forward=0., left=0., turn=0.):
        return self._offer({'kind': 'mecanum', 'forward': forward, 'left': left,
                            'turn': turn, 'duration_s': .1}, now, report)

    def _posture(self, now, report):
        for servo_id, target in self.search_servo.items():
            current = self.memory.servo[servo_id]
            if current != target:
                return self._offer({'kind': 'arm', 'servo_id': servo_id,
                                    'pulse': current + int(clip(target - current, 20)),
                                    'duration_s': .1}, now, report)
        return None

    def _navigate(self, now, report):
        heading_error = wrap(self.goal[2] - report.yaw_rad)
        if abs(heading_error) > CONFIG['prestation_yaw_tol_rad']:
            self.pre_streak = 0
            return self._move(now, report, turn=clip(.6 * heading_error, .10))
        x, y = report.x_m, report.y_m
        if math.dist((x, y), self.goal[:2]) <= CONFIG['prestation_xy_tol_m']:
            self.pre_streak += 1
            if self.pre_streak >= 2:
                self.phase = 'aligning'
                # Save an audit receipt, pass the SAME live memory, never reseed a PF.
                self.alignment_entry = {'t': now, 'frame_id': self.last_frame_id,
                                        'history_count': len(self.memory.history),
                                        'history_sha256': bp.digest(self.memory.history),
                                        'servo': dict(self.memory.servo), 'report': report.as_dict()}
                self.events.append({'event': 'alignment_entry', **self.alignment_entry})
            return self._hold(now)
        self.pre_streak = 0
        # Fixed-heading SEARCH footprint, padded for accepted posterior/yaw error.
        # Public T08a beam/opposite-role envelopes prohibit crossing the beam or
        # taking the opposite end's local corridor. They are not live peer poses.
        parts = polygon_at((0., 0., report.yaw_rad),
                           [(-.2, -.2), (.2482, -.2), (.2482, .2), (-.2, .2)])
        pad = 2 * report.std_xy_m + .32 * 2 * report.std_yaw_rad
        envelope = {axis + '_m': [min(p[i] for p in parts) - pad,
                                  max(p[i] for p in parts) + pad] for i, axis in enumerate(('x', 'y'))}
        opposite = next(r for r in bp.ROLES if r != self.role)
        keepouts = []
        for label in ('beam', opposite):
            x0, x1, y0, y1 = self.plan['swept_bounds_m'][label]
            keepouts.append({'id': 'public_' + label, 'center_m': [(x0+x1)/2, (y0+y1)/2],
                             'half_extents_m': [(x1-x0)/2, (y1-y0)/2], 'source': 'public T08a sheet'})
        path = plan_path(self.map, (x, y), self.goal[:2], envelope, obstacles=keepouts)
        if path is None:
            self._fail('APPROACH_NO_PATH', now)
            return self._hold(now)
        # Validate continuous start/goal joins too (the old grid planner samples
        # grid-cell endpoints). Swept AABBs conservatively include each segment.
        from harness.static_keepouts import polygons_overlap, rect_corners
        obstacles = self.map['obstacles'] + self.map['terrain'] + keepouts
        for a, b in zip(path['waypoints_m'], path['waypoints_m'][1:]):
            ex, ey = envelope['x_m'], envelope['y_m']
            box = (min(a[0], b[0]) + ex[0] - .02, max(a[0], b[0]) + ex[1] + .02,
                   min(a[1], b[1]) + ey[0] - .02, max(a[1], b[1]) + ey[1] + .02)
            bx0, bx1, by0, by1 = self.map['bounds_m']
            poly = [(box[0], box[2]), (box[1], box[2]), (box[1], box[3]), (box[0], box[3])]
            if (not (bx0 < box[0] < box[1] < bx1 and by0 < box[2] < box[3] < by1)
                    or any(polygons_overlap(poly, rect_corners((*o['center_m'], *o['half_extents_m'],
                                                                o.get('yaw_rad', 0.)))) for o in obstacles)):
                self._fail('APPROACH_SWEEP_BLOCKED', now)
                return self._hold(now)
        target = next((p for p in path['waypoints_m'][1:] if math.dist((x, y), p) > .02), self.goal[:2])
        dx, dy = target[0] - x, target[1] - y
        c, s = math.cos(report.yaw_rad), math.sin(report.yaw_rad)
        return self._move(now, report, clip(.6 * (c*dx + s*dy), .08),
                          clip(.6 * (-s*dx + c*dy), .06))

    def _align(self, now, report):
        # A calibrated, own-image-only dependency; never an externally supplied
        # grip/GT argument to tick. Both roles use the identical decision rule.
        centre = self.plan['sheet']['coarse']['beam_xyyaw']
        dx, dy = report.x_m - centre[0], report.y_m - centre[1]
        c, s = math.cos(centre[2]), math.sin(centre[2])
        side = (c*dx + s*dy) * (-1 if self.role == 'end_neg' else 1)
        if not .30 <= side <= 1. or abs(-s*dx + c*dy) > .20:
            self._fail('CROSS_APPROACH_OR_WRONG_END', now)
            return self._hold(now)
        try:
            obs = self.observe_beam(self.rgb.copy(), dict(self.memory.servo), self.role)
        except Exception:
            self._fail('RELATIVE_OBSERVER_ERROR', now)
            return self._hold(now)
        try:
            valid = (obs['visible'] is True and obs['end_visible'] is True
                     and len(obs['grip_base_m']) == 2
                     and all(finite(v) for v in (*obs['grip_base_m'], obs['axis_heading_rad'],
                                                obs['std_xy_m'], obs['std_yaw_rad'])))
            valid = valid and 0 <= obs['std_xy_m'] <= .012 and 0 <= obs['std_yaw_rad'] <= .035
        except (KeyError, TypeError):
            valid = False
        if not valid:
            self.aligned_streak = 0
            if self.missing_since is None:
                self.missing_since = now
            if now - self.missing_since >= CONFIG['beam_missing_timeout_s']:
                self._fail('RELATIVE_BEAM_UNCERTAIN', now)
            return self._hold(now)
        self.missing_since = None
        # v3: .0482 m mount + .155 m calibrated reach, from T08a convention.
        ex = obs['grip_base_m'][0] - self.plan['model_convention']['station_radius_m']
        ey, ea = obs['grip_base_m'][1], wrap(obs['axis_heading_rad'])
        # Reject the wrong end/side rather than correcting through the beam.
        if (not .10 <= obs['grip_base_m'][0] <= .65 or abs(ey) > .15 or abs(ea) > .45):
            self._fail('CROSS_APPROACH_OR_WRONG_END', now)
            return self._hold(now)
        limits = [CONFIG['relative_x_tol_m'], CONFIG['relative_y_tol_m'], CONFIG['relative_yaw_tol_rad']]
        errors = (ex, ey, ea)
        if all(abs(e) <= tol for e, tol in zip(errors, limits)):
            self.aligned_streak += 1
            if self.aligned_streak >= CONFIG['alignment_frames']:
                self.phase = 'aligned'
                self.events.append({'event': 'relative_aligned', 't': now, 'frame_id': self.last_frame_id,
                                    'errors': list(errors), 'delivery_success': None})
            return self._hold(now)
        self.aligned_streak = 0
        commands = [0. if abs(e) <= tol else clip(.6 * e, bound)
                    for e, tol, bound in zip(errors, limits, (.04, .04, .06))]
        return self._move(now, report, *commands)

    def tick(self, now, observation):
        if not finite(now) or now < self.last_now:
            self._fail('NON_MONOTONIC_OWN_CLOCK', self.last_now)
            return self._hold(self.last_now)
        self.last_now = now
        if self.failure:
            return self._hold(now)
        if now - self.started_at >= CONFIG['sim_cap_s']:
            self._fail('APPROACH_ALIGNMENT_TIMEOUT', now)
            return self._hold(now)
        peer = self.status_channel.partner_view(self.robot_id, now)[self.peer]
        if peer['state'] == 'abort':
            self._fail('PARTNER_ABORT', now)
        elif now - self.started_at >= CONFIG['status_start_timeout_s'] and not peer['alive']:
            self._fail('PARTNER_STATUS_TIMEOUT', now)
        if self.failure:
            return self._hold(now)
        if self.pending is not None:
            if now - self.pending_at >= CONFIG['command_ack_timeout_s']:
                self._fail('OWN_COMMAND_NOT_ACKNOWLEDGED', now)
                return self._hold(now)
            # Do not issue a second command or count proposed motion as history.
            return Decision({}, self.phase, 'busy', 'awaiting_own_command_ack')
        try:
            fresh = self._frame(observation, now)
            if self.failure:
                return self._hold(now)
            report = self.memory.provider.report(now)
            trusted = self._trusted(report, now)
        except Exception:
            self._fail('POSE_PROVIDER_ERROR', now)
            return self._hold(now)
        if not trusted:
            self.pre_streak = self.aligned_streak = 0
            if self.uncertain_since is None:
                self.uncertain_since = now
            if now - self.uncertain_since >= CONFIG['uncertain_timeout_s']:
                self._fail('SELF_POSE_UNCERTAIN', now)
            return self._hold(now)
        self.uncertain_since = None
        if not fresh or observation['sim_time'] < self.settle_until or now < self.settle_until:
            return self._hold(now)
        if self.phase == 'aligned':
            return self._hold(now)
        if self.phase == 'localizing':
            self.phase = 'search_posture'
        posture = self._posture(now, report)
        if posture is not None:
            return posture
        if self.phase == 'search_posture':
            self.phase = 'approaching'
        if self.phase == 'approaching':
            return self._navigate(now, report)
        return self._align(now, report)

    def handoff(self):
        """An explicit live handoff for a separately admitted downstream controller."""
        if (self.failure or self.phase not in ('aligning', 'aligned') or self.pending is not None
                or self.uncertain_since is not None):
            raise ValueError('ALIGNMENT_HANDOFF_NOT_READY')
        return self.memory
