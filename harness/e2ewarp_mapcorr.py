"""Default-off e2ewarp owner adapters: loaded-camera FK + own/static map correction.

Contract consumed by ``harness.e2e_warp_mission.IntegratedController`` via
``harness.e2e_warp_components``:

    navigation_factory(robot_id=..., static=...) -> navigation adapter
    navigation.observe(OwnFrame) -> report with map_correction_active,
        handoff_ready, destination_arrived, holding_status, evidence_revision
    navigation.task_candidates(completed) / start(instruction, phase) /
        command(sim_s) / confirm_act(frame, skill) / on_messages(rows) /
        accept_release_fix(report)

The two missing e2ewarp parts this module supplies are:

* ``loaded_camera_fk_v1`` — qualify the own commanded camera FK in the carry
  posture (closed gripper command).  The mapbuild owner chain has no finger
  slider in the camera ancestry, so grip PWM changes occlusion, not the nominal
  transform; the owner API exposes this as ``servo_fk_carry_v1`` and states
  explicitly that it is a command-only kinematic model, never measured load,
  sag or settling.  Without the toggle the previous fail-closed behavior
  (``loaded_or_unknown_load_not_qualified``) is preserved.
* ``selfmap_map_correction_v1`` — causal own-map accumulation plus scan-to-
  submap correction against the own map and the authored static wall map inside
  a +/-1 prior-sigma window.  The motion prior is own issued commands (owner
  command odometry), the measurement is own RGB (owner ground-pair VO and wall
  scan).  No GT/spawn anchor is accepted, and a frame without own-RGB
  perception never updates the pose (odometry-only is blocked).

Contract v1 adds one more, explicit default-off binding:

* ``memory_registered_v1`` — the loaded-FK navigation composition takes its
  registration and pose estimate from the navigator's self-centric memory
  (``harness.e2ewarp_selfnav``: owner ``selfnav_memory_v1``, robot at (0,0),
  relative landmarks) instead of a static map.  In this mode ``static`` may
  carry only order-sheet metadata; map geometry is refused, the correction
  object is never constructed, and no static-map hash or global pose is
  reported.  The binding fails closed while the injected selfnav navigator is
  missing or not ``ready``.  It is mutually exclusive with
  ``selfmap_map_correction_v1``; both default off.

Allowed inputs are exactly the e2ewarp control boundary: one own JPEG, own
issued commands, the authored static map/orders and the per-condition channel
messages the composition layer receives.  No world/model/data/evaluator object,
top camera, contact, measured joint or ground-truth value is read.  This module
imports no simulator or physics code (tests assert the import boundary).

Default is off.  The mapbuild owner modules used here are byte copies pinned to
``origin/codex/mapbuild1`` (SHA recorded in
``experiments/2026-10-18-e2ewarp-r4-mapcorr/owner-assets.json``); no bytes were
edited.  Enabling a toggle is a capability claim for a *new* physical gate, not
a result inherited from any earlier run.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

SCHEMA = 'ugrp.e2ewarp.mapcorr.v1'
OPTION_NAV = 'e2e_warp_navigation_v1'
OPTION_LOADED_FK = 'loaded_camera_fk_v1'
OPTION_CORRECTION = 'selfmap_map_correction_v1'
OPTION_MEMORY = 'memory_registered_v1'
TOGGLE_KEYS = (OPTION_NAV, OPTION_LOADED_FK, OPTION_CORRECTION, OPTION_MEMORY)
OPTION_ZONE = 'own_rgb_zone_visdet_v1'
ACCEPTED_TOGGLES = TOGGLE_KEYS + (OPTION_ZONE,)
ENTRY_NAV = 'harness.e2ewarp_mapcorr:navigation_factory'
ENTRY_LOADED = 'harness.e2ewarp_mapcorr:loaded_camera_fk'
ENTRY_CORRECTION = 'harness.e2ewarp_mapcorr:selfmap_map_correction'
ENTRY_MEMORY = 'harness.e2ewarp_mapcorr:memory_registered'
ROBOTS = ('r1', 'r2', 'r3')
PHASES = ('approach', 'carry')
SKILLS = ('grasp', 'regrasp', 'release')
SELFCENTRIC_OWNER = 'selfnav_memory_v1'
MEMORY_SCHEMA = 'ugrp.e2ewarp.selfnav.v1'
#: Keys the composition adapter owns; an injected owner report may not override them.
_ADAPTER_KEYS = ('schema', 'robot_id', 'option', 'registration_mode',
                 'map_correction_active', 'odometry_only', 'own_rgb_measurement',
                 'static_map_registered', 'reason', 'category', 'blocked_object',
                 'minimum_gap_m', 'gap_status', 'static_map_sha256', 'loaded_fk',
                 'flow', 'scan_status', 'self_map', 'correction', 'own_rgb_zone',
                 'truth_inputs', 'spawn_anchor_used', 'held_world_reads',
                 'input_audit', 'dependency_wait')

# Byte-pinned owner asset origin (mapbuild owner branch tip).  The full
# per-file sha256 table lives in the experiment owner-assets.json.
OWNER_ORIGIN = '95769da0e12326e41b71d29843c4da75c5b10a00'

# Compute-budget caps, not acceptance thresholds: bounded number of exhaustive
# global registration attempts per episode.  Local tracking is unaffected and
# the owner matcher keeps its own score/overlap/window rules.
REGISTRATION_MAX_ATTEMPTS = 3
MIN_GLOBAL_SEGMENTS = 8   # one qualified keyframe (owner sample count floor)


class _Ledger:
    """Bounded own-input ledger with the mandatory rejection fields."""

    def __init__(self, limit=512):
        self.limit, self.rows = int(limit), []

    def add(self, row):
        self.rows.append(row)
        del self.rows[:-self.limit]
        return row


def _static_sha(static):
    try:
        payload = json.dumps(static, sort_keys=True, default=str).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError('authored static map/orders must be serializable') from exc
    return hashlib.sha256(payload).hexdigest()


def _static_map(static):
    if not isinstance(static, dict):
        raise ValueError('authored static mapping required')
    authored = static.get('static_map')
    if not isinstance(authored, dict):
        raise ValueError('authored static_map required')
    bounds = authored.get('bounds_m')
    obstacles = authored.get('obstacles')
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        raise ValueError('static map requires bounds_m[4]')
    if not isinstance(obstacles, list) or not obstacles:
        raise ValueError('static map requires authored obstacles')
    return authored


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _memory_registration(report):
    """Validate the navigator's self-centric registration block; never a pose claim."""
    registration = report.get('memory_registration') if isinstance(report, dict) else None
    from harness.e2ewarp_selfnav import validate_memory_registration
    return validate_memory_registration(registration)


def resolve_toggles(static, toggles=None):
    """Toggles are explicit off/on strings; absent keys default off."""
    raw = dict((static or {}).get('toggles') or {})
    raw.update(toggles or {})
    unknown = set(raw) - set(ACCEPTED_TOGGLES)
    if unknown:
        raise ValueError('UNKNOWN_MAPCORR_TOGGLE:' + ','.join(sorted(unknown)))
    out = {}
    for key in ACCEPTED_TOGGLES:
        value = raw.get(key, 'off')
        if value not in ('off', 'on'):
            raise ValueError('TOGGLE_VALUES_OFF_ON:' + key)
        out[key] = value == 'on'
    return out


def _servo(pwm):
    try:
        servo = {int(k): int(v) for k, v in dict(pwm).items()}
    except (TypeError, ValueError) as exc:
        raise ValueError('own issued PWM mapping required') from exc
    return servo


class LoadedCameraFK:
    """Command-only camera FK adapter; carry posture is default off.

    This is the owner-API gate, not a new FK model: the bytes of
    ``harness.servo_camera_fk`` are the mapbuild owner's, and this class only
    chooses ``servo_fk_v1`` (legacy fail-closed) or ``servo_fk_carry_v1``
    (explicit command-only carry commands) and reports the owner reason.
    """

    def __init__(self, *, option='off', camera_model=None):
        if option not in ('off', OPTION_LOADED_FK):
            raise ValueError('UNKNOWN_LOADED_CAMERA_FK_OPTION')
        self.option = option
        self.enabled = option == OPTION_LOADED_FK
        self.camera_model = self._model(camera_model)

    @staticmethod
    def _model(model):
        if model is None:
            return None
        if not isinstance(model, dict):
            raise ValueError('camera_model mapping required')
        required = ('width', 'height', 'fx', 'fy', 'cx', 'cy')
        if not all(k in model for k in required):
            raise ValueError('camera_model intrinsics required')
        clean = {}
        for key in required:
            value = model[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError('camera_model numeric field required:' + key)
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError('camera_model positive finite field required:' + key)
            clean[key] = float(value)
        return clean

    def resolve(self, pwm):
        """Own commanded PWM -> camera transform evidence (never a pose claim)."""
        from harness.servo_camera_fk import (CARRY_OPTION, OPTION as UNLOADED_OPTION,
                                             transform_from_commands)
        try:
            servo = _servo(pwm)
        except ValueError as exc:
            return dict(qualified=False, reason='invalid_owned_command:' + str(exc),
                        carry_command=False, camera_pose='off', origin=None,
                        rotation=None, source='servo_camera_fk', truth_inputs=0,
                        held_world_reads=0)
        carry = int(servo.get(1, 2000)) <= 1600
        camera_pose = CARRY_OPTION if self.enabled else UNLOADED_OPTION
        try:
            value, reason = transform_from_commands(servo, camera_pose=camera_pose)
        except ValueError as exc:
            return dict(qualified=False, reason='invalid_owned_command:' + str(exc),
                        carry_command=carry, camera_pose=camera_pose, origin=None,
                        rotation=None, source='servo_camera_fk', truth_inputs=0,
                        held_world_reads=0)
        if value is None:
            return dict(qualified=False, reason=reason, carry_command=carry,
                        camera_pose=camera_pose, origin=None, rotation=None,
                        source='servo_camera_fk', truth_inputs=0,
                        held_world_reads=0)
        origin, rotation = value
        return dict(qualified=True, reason=reason, carry_command=carry,
                    camera_pose=camera_pose,
                    origin=[float(v) for v in origin],
                    rotation=[[float(v) for v in row] for row in rotation],
                    source='servo_camera_fk', command_only=True,
                    load_measured=False, truth_inputs=0, held_world_reads=0)

    def zone_camera_model(self, fk):
        """visdet pinhole model from the own servo FK (optional)."""
        if self.camera_model is None or not fk.get('qualified'):
            return None
        from harness.own_rgb_zone_visdet import CameraModel
        model = self.camera_model
        return CameraModel(kind='pinhole', width=int(model['width']),
                           height=int(model['height']), fx=model['fx'],
                           fy=model['fy'], cx=model['cx'], cy=model['cy'],
                           rotation=np.asarray(fk['rotation'], float),
                           translation_m=tuple(fk['origin']))

    def report(self):
        return dict(option=self.option, enabled=self.enabled,
                    command_only=True, load_measured=False,
                    camera_model='pinhole' if self.camera_model else None,
                    truth_inputs=0, held_world_reads=0)


def _mix_inverse(wheels):
    """Inverse of grasp_act_contract.wheel_mix: four wheels -> (f, left, turn)."""
    w = [float(v) for v in wheels]
    if len(w) != 4 or not np.isfinite(w).all():
        raise ValueError('four finite wheel commands required')
    forward = sum(w) / 4.
    left = (w[1]+w[2]-w[0]-w[3]) / 4.
    turn = (w[1]+w[3]-w[0]-w[2]) / 4.
    return forward, left, turn


class OwnStaticMapCorrection:
    """Default-off causal own-map + static-wall-map correction adapter.

    The heavy lifting is the byte-pinned mapbuild owner module; this adapter
    supplies the causal own-input plumbing, forbids odometry-only updates and
    records the mandatory ledger fields.  ``map_correction_active`` means the
    capability is enabled *and* own-RGB perception is available this episode;
    it never means the current frame was accepted as a position fix.
    """

    def __init__(self, static, *, option='off', loaded_fk=None):
        if option not in ('off', OPTION_CORRECTION):
            raise ValueError('UNKNOWN_SELFMAP_MAP_CORRECTION_OPTION')
        self.option = option
        self.enabled = option == OPTION_CORRECTION
        self.static = static
        self.static_map = _static_map(static)
        self.static_sha256 = _static_sha(static)
        self.loaded_fk = loaded_fk or LoadedCameraFK()
        self.ledger = _Ledger()
        self.last_t = None
        self.prior = None
        self.prior_covariance = None
        self.fed_command_t = None
        self.perception_seen = False
        self.registration_attempts = 0
        self.last_report = None
        if self.enabled:
            from harness.selfmap_map_correction import SelfMapCorrection
            from harness.self_map_csm import UncertainCommandOdometry
            self.owner = SelfMapCorrection(self.static_map, option=OPTION_CORRECTION)
            self.odometry = UncertainCommandOdometry()

    # -- own-input motion prior ---------------------------------------------
    def _feed_issued(self, issued):
        """Feed exactly one new own issued command into the owner command model."""
        if not issued:
            return None
        row = issued[-1]
        try:
            stamp = float(row['t'])
            wheels = list(row['wheels'])
            duration = list(row['duration_s'])
        except (KeyError, TypeError, ValueError):
            return 'issued_command_malformed'
        if self.fed_command_t is not None and stamp <= self.fed_command_t + 1e-9:
            return None
        try:
            forward, left, turn = _mix_inverse(wheels)
        except ValueError:
            return 'unsupported_issued_command_shape'
        spans = {round(float(v), 9) for v in duration}
        if len(spans) != 1:
            # Per-wheel durations have no owner command-odometry mapping; fail
            # closed instead of inventing a mixed pulse.
            return 'unsupported_issued_command_shape'
        span = float(duration[0])
        if not math.isfinite(span) or span < 0:
            return 'issued_command_malformed'
        try:
            if span == 0. and forward == 0. and left == 0. and turn == 0.:
                self.odometry.command(dict(kind='hold', t=stamp))
            else:
                self.odometry.command(dict(kind='mecanum', t=stamp, forward=forward,
                                           left=left, turn=turn, duration_s=span))
        except ValueError as exc:
            return 'owner_command_model_rejected:' + str(exc)
        self.fed_command_t = stamp
        return None

    def _motion_prior(self, t):
        """Own issued-command increment since the previous corrected frame."""
        pose = self.odometry.advance(t)
        covariance = np.asarray(self.odometry.covariance, float)
        pose = np.asarray(pose, float)
        if self.prior is None:
            delta = np.zeros(3)
            increment = covariance.copy()
        else:
            from harness.e2e_rgb_vo import between
            delta = np.asarray(between(self.prior, pose), float)
            increment = covariance - self.prior_covariance
        # Analytic owner covariance can lose a few ulps of PSD on subtraction;
        # clip the eigenspectrum to the feasible half-space.  No threshold.
        increment = (increment + increment.T) / 2.
        values, vectors = np.linalg.eigh(increment)
        values = np.clip(values, 0., None)
        increment = vectors @ np.diag(values) @ vectors.T
        self.prior, self.prior_covariance = pose, covariance
        return delta, increment

    # -- per-frame correction ----------------------------------------------
    def step(self, t, frame_id, *, flow, scan, issued, perception_available):
        t = float(t)
        if not math.isfinite(t):
            raise ValueError('finite own frame time required')
        if self.last_t is not None and t <= self.last_t:
            raise ValueError('causal own frames required')
        self.last_t = t
        self.perception_seen |= bool(perception_available)
        base = dict(t=t, frame_id=int(frame_id), category='map_correction',
                    blocked_object='own_observed_wall', minimum_gap_m=None,
                    gap_status='not_measured', truth_inputs=0,
                    spawn_anchor_used=False, odometry_only=False,
                    static_map_sha256=self.static_sha256,
                    map_correction_active=bool(self.enabled and perception_available))
        if not self.enabled:
            row = dict(base, status='off', reason='selfmap_map_correction_off',
                       accepted=False, inserted=False, attempted=False,
                       static_map_registered=False)
            self.last_report = self.ledger.add(row)
            return row
        command_issue = self._feed_issued(issued)
        if command_issue is not None:
            row = dict(base, status='rejected', reason=command_issue,
                       accepted=False, inserted=False, attempted=False,
                       static_map_registered=self._registered())
            self.last_report = self.ledger.add(row)
            return row
        if not perception_available:
            # Odometry-only correction is forbidden: no own-RGB measurement this
            # episode/frame means no pose update may be accepted.
            row = dict(base, status='rejected', reason='own_rgb_perception_unavailable',
                       accepted=False, inserted=False, attempted=False,
                       static_map_registered=self._registered(),
                       map_correction_active=False)
            self.last_report = self.ledger.add(row)
            return row
        delta, covariance = self._motion_prior(t)
        owner_flow = flow if isinstance(flow, dict) else dict(status='unknown_flow')
        owner_scan = scan if isinstance(scan, dict) else dict(segments=[], camera=None)
        pose, event = self.owner.step(t, frame_id, delta, covariance, owner_flow, owner_scan)
        registration = self._register_if_due(event)
        row = dict(base, status=event.get('status', 'unknown'),
                   reason=event.get('reason', 'unknown'),
                   prior_pose=[float(v) for v in pose],
                   covariance=[[float(v) for v in r] for r in np.asarray(self.owner.covariance)],
                   accepted=bool(event.get('accepted')),
                   inserted=bool(event.get('inserted')),
                   attempted=bool(event.get('attempted')),
                   motion_delta=[float(v) for v in delta],
                   motion_source='own_issued_commands',
                   measurement='own_rgb_ground_pair' if owner_flow.get('status') == 'measured' else owner_flow.get('status'),
                   owner_event=event,
                   static_map_registered=self._registered(),
                   registration=registration)
        self.last_report = self.ledger.add(row)
        return row

    def _registered(self):
        return bool(self.enabled and self.owner.static_from_own is not None)

    def _register_if_due(self, event):
        if not self.enabled or self._registered():
            return None
        if self.registration_attempts >= REGISTRATION_MAX_ATTEMPTS:
            return dict(status='skipped', reason='compute_cap_registration_attempts',
                        attempts=self.registration_attempts,
                        work=dict(candidates=0, point_checks=0))
        segments = len(getattr(self.owner, 'global_segments', []))
        if segments < MIN_GLOBAL_SEGMENTS:
            return dict(status='deferred', reason='insufficient_own_map_segments',
                        segments=segments, attempts=self.registration_attempts)
        result = self.owner.initialize_static()
        result = dict(result or {})
        result['work'] = dict(result.get('work') or {})
        result['attempts'] = self.registration_attempts + 1
        self.registration_attempts += 1
        return result

    def report(self):
        registered = self._registered()
        return dict(option=self.option, enabled=self.enabled,
                    map_correction_active=bool(self.enabled and self.perception_seen),
                    odometry_only=False, own_rgb_measurement=True,
                    static_map_sha256=self.static_sha256,
                    static_map_registered=registered,
                    spawn_anchor_used=False, truth_inputs=0,
                    own_gauge_pose=(None if not self.enabled else
                                    [float(v) for v in self.owner.pose]),
                    registration_attempts=self.registration_attempts,
                    ledger_rows=len(self.ledger.rows),
                    last=self.last_report)


class E2EWarpNavigation:
    """Fail-closed navigation_factory adapter composing FK + map correction.

    ``observe`` always produces the map-correction evidence from allowed own
    inputs.  Route/task behaviour is delegated to an injected owner navigation
    object when provided; without it the adapter only holds the wheels and
    reports dependency wait (no motion or arrival claim is invented).  The
    e2ewarp navigation component itself is still mapbuild8-owned.

    With ``memory_registered_v1`` on, no static map/correction object exists:
    registration and pose come from the injected selfnav navigator's
    ``memory_registration`` block, ``static`` is order-sheet metadata only, and
    every report is gated on the navigator being ready and having a registered
    own-memory destination.  The mode is default off and fails closed.
    """

    def __init__(self, robot_id, static=None, *, toggles=None, owner_navigation=None,
                 camera_model=None):
        if robot_id not in ROBOTS:
            raise ValueError('unknown robot_id')
        self.robot_id, self.static = robot_id, static
        self.toggles = resolve_toggles(static, toggles)
        self.memory_mode = self.toggles[OPTION_MEMORY]
        if self.memory_mode:
            if self.toggles[OPTION_CORRECTION]:
                raise ValueError('MEMORY_REGISTERED_AND_MAP_CORRECTION_ARE_EXCLUSIVE')
            # Contract v1: only order-sheet metadata may reach this mode; the
            # selfnav validator rejects any map-geometry key.
            from harness.e2ewarp_selfnav import order_sheet
            self.order_sheet = order_sheet(static)
            self.static_sha256 = None
        else:
            self.order_sheet = None
            self.static_sha256 = _static_sha(static)
        self.owner = owner_navigation
        if owner_navigation is not None:
            for name in ('observe', 'task_candidates', 'start', 'command',
                         'confirm_act', 'on_messages'):
                if not callable(getattr(owner_navigation, name, None)):
                    raise ValueError('owner navigation missing method:' + name)
        self.loaded_fk = LoadedCameraFK(
            option=OPTION_LOADED_FK if self.toggles[OPTION_LOADED_FK] else 'off',
            camera_model=camera_model)
        if self.memory_mode:
            self.correction = None
        else:
            self.correction = OwnStaticMapCorrection(
                static, option=OPTION_CORRECTION if self.toggles[OPTION_CORRECTION] else 'off',
                loaded_fk=self.loaded_fk)
        self.enabled = self.toggles[OPTION_NAV]
        self.instruction = None
        self.phase = None
        self.messages = []
        self.events = _Ledger()
        self.last_t = None
        self.last_report = None
        self.evidence_revision = 0
        self.previous_rgb = None
        self.previous_pwm = None
        self.servo_since = 0.
        self.colour = None
        self.carry_camera = None
        self.zone_reporter = None
        self.zone = None
        self.last_zone = None
        self.memory_registration = None
        self.memory_owner_report = None
        self.memory_active = False

    # -- own-RGB perception --------------------------------------------------
    def _decode(self, frame):
        import cv2
        data = np.frombuffer(frame.jpeg, np.uint8)
        rgb = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if rgb is None:
            raise ValueError('own JPEG decode failed')
        return cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)

    def _colour_state(self):
        if self.colour is None:
            from harness.scene_colour_boundary import (ColourBoundaryState,
                                                       RELOC16_OPTION)
            root = __import__('pathlib').Path(__file__).resolve().parents[1]
            path = root / 'experiments/2026-10-17-e2ewarp/vendor-data/colour-calibration.json'
            expected = 'a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f'
            import hashlib as _hash
            raw = path.read_bytes()
            if _hash.sha256(raw).hexdigest() != expected:
                raise ValueError('FROZEN_COLOUR_CALIBRATION_REQUIRED')
            self.colour = ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',
                                              json.loads(raw), option=RELOC16_OPTION)
        return self.colour

    def _carry_camera(self):
        if self.carry_camera is None:
            from harness.mapbuild_camera import CommandCamera
            from harness.servo_camera_fk import CARRY_OPTION
            self.carry_camera = CommandCamera(camera_pose=CARRY_OPTION)
        return self.carry_camera

    def _perception(self, frame, rgb, servo, fk):
        """Own-RGB flow + wall scan; unknown stays unknown (no invented zero)."""
        from harness.e2e_rgb_vo import PARAMS
        if not fk.get('qualified'):
            return dict(status='unknown_' + str(fk.get('reason')), delta=None), \
                dict(segments=[], camera=None, columns=[], work=None), 'camera_unqualified'
        key = tuple(sorted(servo.items()))
        loaded = int(servo.get(1, 2000)) <= 1600
        if self.previous_pwm is not None and key != self.previous_pwm:
            self.servo_since = frame.sim_s
        changed = self.previous_pwm is not None and key != self.previous_pwm
        settled_s = max(PARAMS['settle_s']) if not loaded else PARAMS['settle_s'][1]
        settled = frame.sim_s - self.servo_since + 1e-9 >= settled_s
        if self.loaded_fk.enabled:
            # Owner carry-camera binding: pair/scan use the admitted carry FK.
            flow, scan = self._carry_camera().observe(
                frame.sim_s, self.previous_rgb, rgb, servo, self._colour_state())
            scan_status = 'observed_wall_contacts' if scan.get('segments') else 'unknown_wall_contact'
        else:
            from harness.e2e_rgb_vo import ground_pair
            from harness.mapbuild_rbpf import virtual_scan
            if self.previous_rgb is None:
                flow = dict(status='bootstrap', delta=None)
            elif changed:
                flow = dict(status='unknown_servo_change', delta=None)
            elif not settled:
                flow = dict(status='unknown_commanded_camera_settling', delta=None)
            else:
                flow = ground_pair(self.previous_rgb, rgb, servo)
            scan = virtual_scan(rgb, servo, self._colour_state())
            scan_status = 'observed_wall_contacts' if scan.get('segments') else 'unknown_wall_contact'
            if not settled:
                scan = {**scan, 'segments': []}
                scan_status = 'unknown_commanded_camera_settling'
        self.previous_rgb, self.previous_pwm = rgb, key
        return flow, {**scan, 'scan_status': scan_status}, scan_status

    def _zone(self, rgb, fk):
        if not self.toggles.get(OPTION_ZONE):
            return dict(status='off', enabled=False, destination_arrived=False,
                        zone_visible=False, evidence_revision=0,
                        reason='own_rgb_zone_visdet_off')
        model = self.loaded_fk.zone_camera_model(fk)
        if model is None:
            return dict(status='off', enabled=False, destination_arrived=False,
                        zone_visible=False, evidence_revision=0,
                        reason='own_rgb_zone_camera_model_unavailable')
        if self.zone_reporter is None:
            from harness.own_rgb_zone_visdet import ZoneArrivalReporter
            spec = None
            destination = (self.instruction or {}).get('destination_zone')
            regions = (self.static.get('static_map') or {}).get('regions') or {}
            region = regions.get(destination) or {}
            if destination == 'B' and region.get('center_m') and region.get('half_extents_m'):
                from harness.own_rgb_zone_visdet import ZoneSpec
                (cx, cy), (hx, hy) = region['center_m'], region['half_extents_m']
                spec = ZoneSpec(rect=(cx-hx, cx+hx, cy-hy, cy+hy))
            self.zone_reporter = ZoneArrivalReporter(model, enabled=True, spec=spec)
        self.zone = self.zone_reporter.observe(rgb)
        return self.zone

    # -- ABI -----------------------------------------------------------------
    def observe(self, frame):
        if frame.robot_id != self.robot_id:
            raise ValueError('cross-robot navigation input rejected')
        if self.last_t is not None and frame.sim_s <= self.last_t:
            raise ValueError('causal own frames required')
        self.last_t = float(frame.sim_s)
        if not frame.issued:
            raise ValueError('own issued command history required')
        self.evidence_revision += 1
        if not self.enabled:
            report = self._report(off_reason='e2e_warp_navigation_off')
            self.last_report = report
            return report
        rgb = self._decode(frame)
        pwm = {str(k): int(v) for k, v in frame.issued[-1]['pwm'].items()}
        servo = _servo(pwm)
        fk = self.loaded_fk.resolve(pwm)
        if self.memory_mode:
            return self._observe_memory(frame, fk)
        flow, scan, scan_status = self._perception(frame, rgb, servo, fk)
        zone = self._zone(rgb, fk)
        self.last_zone = zone
        correction_row = self.correction.step(
            frame.sim_s, frame.tick, flow=flow, scan=scan,
            issued=frame.issued, perception_available=bool(fk.get('qualified')))
        report = self._report(flow=flow, scan=scan, scan_status=scan_status,
                              fk=fk, zone=zone, correction_row=correction_row)
        if self.owner is not None:
            owner_report = self.owner.observe(frame)
            if not isinstance(owner_report, dict):
                raise ValueError('owner navigation report must be a mapping')
            if owner_report.get('map_correction_active') is False:
                raise ValueError('owner cannot disable the enabled map correction')
            merged = dict(owner_report)
            for key in _ADAPTER_KEYS:
                merged[key] = report[key]
            report = merged
        self.last_report = report
        return report

    def _observe_memory(self, frame, fk):
        """Self-centric binding: navigator memory replaces static map registration."""
        owner_report, registration, reason = None, None, None
        self.memory_owner_report = None
        if self.owner is None:
            reason = 'selfnav_navigator_missing'
        else:
            owner_report = self.owner.observe(frame)
            if not isinstance(owner_report, dict):
                raise ValueError('owner navigation report must be a mapping')
            self.memory_owner_report = owner_report
            try:
                registration = _memory_registration(owner_report)
            except ValueError as exc:
                reason = 'selfnav_memory_contract_invalid:' + str(exc)
            else:
                if registration['ready'] is not True:
                    reason = 'selfnav_not_ready'
                elif registration['registered'] is not True:
                    reason = 'selfnav_memory_unregistered'
        if reason is None and not fk.get('qualified'):
            reason = 'own_rgb_perception_unavailable:' + str(fk.get('reason'))
        self.memory_registration = registration
        self.memory_active = bool(reason is None and registration is not None)
        report = self._report(off_reason=reason, fk=fk, owner_report=owner_report,
                              memory_registration=registration)
        self.last_report = report
        return report

    def _report(self, *, off_reason=None, flow=None, scan=None, scan_status=None,
                fk=None, zone=None, correction_row=None, owner_report=None,
                memory_registration=None):
        if self.memory_mode:
            return self._memory_report(off_reason=off_reason, fk=fk,
                                       owner_report=owner_report,
                                       registration=memory_registration)
        correction = self.correction.report()
        if correction_row is not None:
            correction['last'] = correction_row
        fk = fk or dict(qualified=False, reason='navigation_off', carry_command=False,
                        camera_pose='off', truth_inputs=0, held_world_reads=0)
        zone = zone or dict(status='off', enabled=False, destination_arrived=False,
                            zone_visible=False, evidence_revision=0,
                            reason='navigation_off')
        active = bool(self.enabled and self.toggles[OPTION_CORRECTION]
                      and fk.get('qualified'))
        if not self.enabled:
            reason = off_reason or 'e2e_warp_navigation_off'
        elif not self.toggles[OPTION_CORRECTION]:
            reason = 'selfmap_map_correction_off'
        elif not fk.get('qualified'):
            reason = 'own_rgb_perception_unavailable:' + str(fk.get('reason'))
        elif off_reason:
            reason = off_reason
        else:
            reason = correction.get('last', {}).get('reason', 'observed') if correction.get('last') else 'bootstrap'
        return dict(
            schema=SCHEMA, robot_id=self.robot_id, option=self.toggles,
            registration_mode='static_map',
            map_correction_active=active,
            odometry_only=False, own_rgb_measurement=True,
            static_map_registered=correction.get('static_map_registered', False),
            handoff_ready=False,       # e2ewarp navigation owner decides
            destination_arrived=bool(zone.get('destination_arrived')),
            holding_status='unknown',  # no measured holding is available here
            evidence_revision=self.evidence_revision,
            reason=reason, category='own_navigation',
            blocked_object='not_observed', minimum_gap_m=None,
            gap_status='not_measured',
            static_map_sha256=self.static_sha256,
            loaded_fk=fk, flow=flow, scan_status=scan_status,
            self_map=dict(frame='own_start', scan_status=scan_status,
                          segments=(len((scan or {}).get('segments') or [])
                                    if isinstance(scan, dict) else 0)),
            correction=correction, own_rgb_zone=zone,
            truth_inputs=0, spawn_anchor_used=False, held_world_reads=0,
            input_audit=dict(top_camera_control=False, held_world_reads=0,
                             truth_inputs=0, spawn_anchor_used=False,
                             odometry_only=False,
                             static_map_correction=bool(self.toggles[OPTION_CORRECTION]),
                             self_centric_memory=False,
                             static_map_route=False),
            dependency_wait=[name for name, ready in dict(
                navigation_owner=self.owner is not None,
                selected_ACT=False, release_relocalization=False).items() if not ready])

    def _memory_report(self, *, off_reason=None, fk=None, owner_report=None,
                       registration=None):
        """Report self-centric memory registration; static-map fields stay empty."""
        fk = fk or dict(qualified=False, reason='navigation_off', carry_command=False,
                        camera_pose='off', truth_inputs=0, held_world_reads=0)
        registration = registration if isinstance(registration, dict) else None
        owner_report = owner_report if isinstance(owner_report, dict) else {}
        ready = bool(registration is not None and registration.get('ready') is True)
        registered = bool(ready and registration.get('registered') is True)
        perception = bool(fk.get('qualified'))
        active = bool(self.enabled and registered and perception)
        self.memory_active = active
        self.memory_registration = registration
        if not self.enabled:
            reason = off_reason or 'e2e_warp_navigation_off'
        elif off_reason:
            reason = off_reason
        elif not perception:
            reason = 'own_rgb_perception_unavailable:' + str(fk.get('reason'))
        elif registration is None:
            reason = 'selfnav_navigator_missing'
        elif not ready:
            reason = 'selfnav_not_ready'
        elif not registered:
            reason = 'selfnav_memory_unregistered'
        else:
            reason = str(owner_report.get('drive_reason') or 'self_centric_memory_ready')
        landmark = None if registration is None else registration.get('destination_landmark')
        return dict(
            schema=SCHEMA, robot_id=self.robot_id, option=self.toggles,
            registration_mode='memory_registered',
            navigator_owner=None if registration is None else registration.get('owner'),
            memory_registered=active,
            memory_active=active,
            memory_registration=registration,
            memory_sha256=None if registration is None else registration.get('memory_sha256'),
            memory_evidence_revision=None if registration is None else registration.get('evidence_revision'),
            destination_registered=bool(registration is not None
                                        and registration.get('destination_registered') is True),
            destination_landmark=landmark,
            pose_estimate=dict(frame='self_centric', position_xy=[0.0, 0.0]),
            map_correction_active=active,
            odometry_only=False, own_rgb_measurement=True,
            static_map_registered=False,
            static_map_sha256=None,
            own_gauge_pose=None,
            handoff_ready=bool(active and owner_report.get('handoff_ready')),
            destination_arrived=bool(active and owner_report.get('destination_arrived')),
            holding_status=str(owner_report.get('holding_status') or 'unknown') if active else 'unknown',
            evidence_revision=self.evidence_revision,
            reason=reason, category='own_navigation',
            blocked_object='not_observed', minimum_gap_m=None,
            gap_status='not_measured',
            loaded_fk=fk, flow=None, scan_status='self_centric_memory',
            self_map=dict(frame='own_start', scan_status='self_centric_memory', segments=0),
            correction=dict(option='off', enabled=False,
                            reason='not_used_memory_registered',
                            static_map_registered=False, truth_inputs=0,
                            held_world_reads=0),
            own_rgb_zone=dict(status='off', enabled=False, destination_arrived=False,
                              zone_visible=False, evidence_revision=0,
                              reason='self_centric_memory_mode'),
            truth_inputs=0, spawn_anchor_used=False, held_world_reads=0,
            input_audit=dict(top_camera_control=False, held_world_reads=0,
                             truth_inputs=0, spawn_anchor_used=False,
                             odometry_only=False, static_map_correction=False,
                             self_centric_memory=True, static_map_route=False),
            dependency_wait=[name for name, ready in dict(
                navigation_owner=self.owner is not None,
                selfnav_ready=ready, selfnav_memory_registered=registered,
                selected_ACT=False, release_relocalization=False).items() if not ready])

    def task_candidates(self, completed):
        if not isinstance(completed, (list, tuple)):
            raise ValueError('completed instruction list required')
        if self.owner is not None:
            return self.owner.task_candidates(completed=list(completed))
        return []

    def start(self, instruction, phase):
        if phase not in PHASES:
            raise ValueError('unknown navigation phase')
        if not isinstance(instruction, dict):
            raise ValueError('navigation start requires the LLM task instruction')
        for key in ('object_kind', 'role', 'destination_zone', 'order_id'):
            if key not in instruction:
                raise ValueError('missing task token:' + key)
        self.instruction = dict(instruction)
        self.phase = phase
        self.zone_reporter = None
        if self.owner is not None:
            self.owner.start(dict(instruction), phase)

    def command(self, now):
        from harness.grasp_act_contract import command
        if not math.isfinite(float(now)):
            raise ValueError('finite command time required')
        if self.memory_mode and not self.memory_active:
            # Fail closed: an unready/missing selfnav navigator gets no motion.
            return self._hold(now)
        if self.owner is not None:
            return self.owner.command(now)
        return self._hold(now)

    def _hold(self, now):
        from harness.grasp_act_contract import command
        from harness.active_camera import SEARCH
        pwm = {str(k): int(v) for k, v in SEARCH.items()}
        pwm['1'] = 2000   # hold the gripper open: no invented grasp/release
        value = dict(t=float(now), wheels=[0.] * 4, duration_s=[0.] * 4, pwm=pwm)
        return command(value)

    def confirm_act(self, frame, skill):
        if skill not in SKILLS:
            raise ValueError('unknown ACT skill')
        if frame.robot_id != self.robot_id:
            raise ValueError('cross-robot ACT confirmation rejected')
        if self.owner is not None:
            confirmed = self.owner.confirm_act(frame, skill)
            self._event('act_confirmed_by_owner' if confirmed else 'act_not_confirmed_by_owner',
                        skill=skill)
            return bool(confirmed)
        zone = self.last_zone or {}
        self._event('act_confirm_evidence', skill=skill,
                    zone_visible=bool(zone.get('zone_visible')),
                    destination_arrived=bool(zone.get('destination_arrived')))
        return bool(skill == 'release' and zone.get('destination_arrived') is True
                    and (self.instruction or {}).get('destination_zone') == 'B')

    def on_messages(self, rows):
        if not isinstance(rows, (list, tuple)):
            raise ValueError('channel message rows required')
        self.messages.extend(dict(row) for row in rows)
        if self.owner is not None:
            self.owner.on_messages(rows)

    def accept_release_fix(self, report):
        if not isinstance(report, dict):
            return False
        if self.memory_mode:
            return self._accept_memory_release_fix(report)
        if not (self.toggles[OPTION_CORRECTION] and self.correction._registered()):
            self._event('release_fix_rejected', detail='map_correction_not_registered')
            return False
        if report.get('relocalized') is not True or report.get('static_map_registered') is not True:
            self._event('release_fix_rejected', detail='release_evidence_incomplete')
            return False
        if report.get('truth_inputs', 0) != 0 or report.get('held_world_reads', 0) != 0:
            self._event('release_fix_rejected', detail='release_reports_forbidden_inputs')
            return False
        if self.owner is not None and callable(getattr(self.owner, 'accept_release_fix', None)):
            accepted = self.owner.accept_release_fix(report)
            self._event('release_fix_owner_decision', accepted=bool(accepted))
            return bool(accepted)
        self._event('release_fix_accepted', detail='registered_correction_and_own_release_evidence')
        return True

    def _accept_memory_release_fix(self, report):
        """Accept a release fix bound to the navigator's live self-centric memory."""
        def reject(detail):
            self._event('release_fix_rejected', detail=detail)
            return False

        if not self.enabled:
            return reject('memory_registration_disabled')
        if report.get('static_map_registered') is True:
            return reject('mixed_static_map_evidence')
        if report.get('navigator_owner') != SELFCENTRIC_OWNER:
            return reject('navigator_owner_mismatch')
        if report.get('relocalized') is not True or report.get('memory_registered') is not True:
            return reject('release_evidence_incomplete')
        if not _hex64(report.get('memory_sha256')):
            return reject('memory_snapshot_hash_invalid')
        revision = report.get('navigator_evidence_revision')
        if type(revision) is not int or revision < 0:
            return reject('navigator_evidence_revision_invalid')
        if report.get('truth_inputs', 0) != 0 or report.get('held_world_reads', 0) != 0:
            return reject('release_reports_forbidden_inputs')
        registration = self.memory_registration
        if not isinstance(registration, dict) or registration.get('ready') is not True:
            return reject('selfnav_not_ready')
        if registration.get('destination_registered') is not True:
            return reject('selfnav_destination_unregistered')
        landmark = report.get('memory_landmark')
        if (not isinstance(landmark, dict) or landmark.get('kind') != registration.get('destination_kind')):
            return reject('destination_landmark_mismatch')
        if revision > registration.get('evidence_revision', -1):
            return reject('future_release_evidence')
        if self.owner is not None and callable(getattr(self.owner, 'accept_release_fix', None)):
            accepted = self.owner.accept_release_fix(report)
            self._event('release_fix_owner_decision', accepted=bool(accepted))
            return bool(accepted)
        self._event('release_fix_accepted', detail='self_centric_memory_registration')
        return True

    def _event(self, name, **extra):
        return self.events.add(dict(category='own_navigation', reason=name, robot_id=self.robot_id,
                                    blocked_object='not_observed', minimum_gap_m=None,
                                    gap_status='not_measured', truth_inputs=0, **extra))


def navigation_factory(robot_id, static=None, *, toggles=None, owner_navigation=None,
                       camera_model=None):
    """Manifest entry point: module:navigation_factory, called with robot_id/static."""
    return E2EWarpNavigation(robot_id, static, toggles=toggles,
                             owner_navigation=owner_navigation,
                             camera_model=camera_model)


def loaded_camera_fk(*, option='off', camera_model=None):
    """Manifest entry point for the loaded camera FK part."""
    return LoadedCameraFK(option=option, camera_model=camera_model)


def selfmap_map_correction(static, *, option='off', loaded_fk=None):
    """Manifest entry point for the own/static map correction part."""
    return OwnStaticMapCorrection(static, option=option, loaded_fk=loaded_fk)


def memory_registered(robot_id, static=None, *, owner_navigation=None, camera_model=None):
    """Manifest entry point for the explicit self-centric loaded-FK composition.

    Explicitly turns on both ``e2e_warp_navigation_v1`` and the default-off
    ``memory_registered_v1``; the caller must still inject a ready selfnav
    navigator or every report/command stays fail-closed.  ``loaded_camera_fk_v1``
    is deliberately *not* enabled here: the carry-pose FK is its own capability
    claim and must be opted in separately (static ``toggles`` or factory).
    """
    return E2EWarpNavigation(
        robot_id, static,
        toggles={OPTION_NAV: 'on', OPTION_MEMORY: 'on'},
        owner_navigation=owner_navigation, camera_model=camera_model)
