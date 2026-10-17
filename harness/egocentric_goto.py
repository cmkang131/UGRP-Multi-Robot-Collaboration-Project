"""Default-off egocentric memory goto: remember an observed floor target and drive back.

Controller inputs are the robot's own raw fisheye RGB, own commanded servo
pose and own issued wheel-command history.  It never receives qpos, world
coordinates, a static map, top-camera frames, held-object pose or evaluation
labels.  Memory transport/correction reuses the byte-vendored egomem2
``LandmarkMemory`` (Castellanos old-frame EKF update, ROVIO/Stone Soup hooks
kept available); the finite drive vocabulary is the existing sim heading pulse
(.35 raw limit, .10 s turn/forward, .06 rad heading gate, .10 m final
alignment) from ``harness.zone_solo_cyan_path_heading.PARAMS``.

Public method references (pinned in the experiment README):
* Nav2 RPP rotate-to-heading / collision checks, Nav2 RotationShim, Nav2 DWB
  trajectory critics, Nav2 NavigateToPose initializeGoalPose goal fixation.
* VFH (Borenstein & Koren 1991) polar obstacle clearance idea and DWA
  (Fox, Burgard & Thrun 1997) finite candidate evaluation; this module uses a
  small calibrated pulse set, not a reimplementation of either planner.
* ROVIO/ETH ASL robocentric EKF and MRPT range-bearing SLAM landmark
  persistence (through the vendored egomem2 module).
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

import numpy as np

OPTION = 'egocentric_goto_v1'
TARGET_KIND = 'zone_marking'
TARGET_SIGNATURE = 'floor_orange_zone_marking'
SCHEMA = 'ugrp.memory_item.v1'
VENDOR = Path(__file__).with_name('egonav_vendor')

# Existing calibrated finite-pulse values.  Imported rather than duplicated so
# a change in the registered heading policy is visible here.
from harness.zone_solo_cyan_path_heading import PARAMS as HEADING_PARAMS
from harness.rbpf_rejection import motion_variance

ARRIVAL_RADIUS_M = HEADING_PARAMS['final_alignment_m']
HEADING_TOLERANCE_RAD = HEADING_PARAMS['heading_tolerance_rad']
SIGMA_RANGE_M = .2       # PR406 own-map range sigma, inherited not refitted.
SIGMA_BEARING_RAD = math.radians(3.)  # PR406 own-map bearing sigma.
# Floor zone markings are broad painted regions.  The gate-08 preflight
# (10/16 worlds, authored range 0.99-3.71 m) measured own-RGB
# ``observed_area_m2`` 0.4427-0.8619 m^2 for the true marking; the world02
# replay's false orange detections (peer robot wheels, cargo boxes; 180 ticks)
# measured 0.0053-0.0240 m^2.  The geometric log-midpoint
# sqrt(0.4427*0.0240)=0.103 sits 4.4x below the smallest true marking and
# 4.2x above the largest false positive, so the birth gate adopts 0.10 m^2.
# Observations without a measured area are ignored (fail-closed).
ZONE_MARKING_MIN_OBSERVED_AREA_M2 = .10
# Finite-pulse turn calibration.  ``command_delta()`` below is a frozen
# wheel-contact model.  A pure-turn pulse probe (240 pulses, no wall contact,
# ``scripts/egonav_gate.py --probe-rotation``) measured 0.1060358 rad/pulse
# median and 0.1027191 rad/pulse p10 on gcp4 under warp_native_contact_v1;
# the frozen model predicts 0.1423730, so it overestimates 1.34x.  A repeat
# probe on worlds 0-6 reproduced 0.10599-0.10615 rad/pulse at every spawn
# (including gate-07 world06's).  The gate-07 "4.29x" figure compared an
# authored spawn yaw to a final qpos yaw, not per-pulse deltas, so it is not
# used.  Raw: experiments/2026-10-17-egonav/probe-rotation.json and
# probe-rotation-w0-6.json (VM runs probe-rotation-01/-w0-6).
TURN_RAD_PER_PULSE_MEDIAN = 0.10603575778058376
TURN_RAD_PER_PULSE_P10 = 0.10271914804372737

# Default-off far sub-gate candidate (``egonav_far_candidate_v1``).  The static
# far-measure probe on gcp4 (4 authored starts, 100 ticks each, own RGB only)
# measured the true zone marking at 0.842-0.903 m^2 (2.0 m), 0.822-0.893 m^2
# (3.0 m) and 0.378-0.442 m^2 (3.94 m), all far above the 0.10 m^2 birth gate;
# at 4.90 m the marking was outside the floor-projection max_range_m=4.0 and
# the only sub-gate patch was red cargo at 1.32 m (0.00917-0.00957 m^2, hue 1).
# The per-world static area max/min ratio over 100 ticks was <=1.169, so the
# 1.25 growth threshold sits above the measured static noise.  True patches
# were present on 100/100 ticks; 5 frames (0.5 s) is a minimal persistence
# window well below that.
#
# Hue reference: the task map's declared zone-A marking colour, not a live
# observation.  maps/zones/zone_wide_door_geometry_v3.json regions.zone_A.rgba
# is ".95 .45 .10 .30"; RGB (0.95, 0.45, 0.10) converts to OpenCV hue 12.3529
# (uint8 12).  This is a fixed task label, so a candidate can be judged before
# the first 0.10 m^2 confirmation (the earlier observed-confirmation reference
# made the toggle inert on fresh far starts: world3 logged only
# hue_reference_unavailable).  Tolerance 1.35 = |12.3529 - 11|: the true
# marking's per-tick uint8 hue medians were exactly 12 with p10 12 / p90 13 on
# 100/100 ticks at 2.0/3.0/3.94 m, so integer hues 11-13 are inside the class;
# hue 14 and the red cargo class (kind red ".80 .12 .10" -> hue 1) are outside.
# Raw: outputs/egonav-far/far-measure-02 (VM far-measure-02).
#
# A candidate never creates memory, never sets seen_target/done and never
# drives forward: it can only select the sign of the in-place search turn, so
# confirmation/arrival stay owned by the 0.10 m^2 gate.
FAR_CANDIDATE_OPTION = 'egonav_far_candidate_v1'
FAR_CANDIDATE_MIN_FRAMES = 5
DECLARED_TARGET_HUE = 12.352941176470589
DECLARED_TARGET_HUE_TOLERANCE = 1.35
FAR_CANDIDATE_AREA_GROWTH_RATIO = 1.25
FAR_CANDIDATE_MAX_AGE_S = 1.


def hue_distance(a, b):
    """Circular distance on OpenCV's 0..179 hue wheel."""
    difference = abs(float(a)-float(b))
    return min(difference, 180.-difference)


def issued_forward(command):
    """True iff the previously issued wheel pulse has net forward duty.

    Turn pulses cancel across wheels (left/right opposite signs), so their
    duration-weighted sum is zero; forward pulses sum positive.  Uses only the
    controller's own issued command, never pose or contact.
    """
    if not isinstance(command, dict):
        return False
    try:
        wheels = [float(w) for w in command['wheels']]
        durations = [float(d) for d in command['duration_s']]
    except (KeyError, TypeError, ValueError):
        return False
    if not wheels or len(wheels) != len(durations):
        return False
    return math.fsum(w*d for w, d in zip(wheels, durations)) > 0.


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def duty(drive):
    """Existing finite pulse decoder; copied from egomem1_record/egomem2."""
    f, l, t = drive
    desired = [f-l-t, f+l+t, f+l-t, f-l+t]
    scale = max(.35, max(map(abs, desired)))
    duration = [.1*abs(v)/scale for v in desired]
    return ([0. if dt < .001 else math.copysign(.35, v) for v, dt in zip(desired, duration)],
            [0. if dt < .001 else dt for dt in duration])


def command_delta(command, dt=.1):
    """Own issued-wheel command -> planar increment (frozen wheel model)."""
    a, b, c, d = [w*min(dt, t) for w, t in zip(command['wheels'], command['duration_s'])]
    gain = .0325*150*2*math.pi/60
    return [gain*(a+b+c+d)/4, gain*(-a+b+c-d)/4,
            gain*(-a+b-c+d)/(4*.1255)]


def point_covariance(xy):
    """PR406 range/bearing sigmas propagated through the Cartesian Jacobian."""
    xy = np.asarray(xy, float)
    r = float(np.linalg.norm(xy))
    a = math.atan2(xy[1], xy[0])
    c, s = math.cos(a), math.sin(a)
    j = np.array([[c, -r*s], [s, r*c]])
    return j @ np.diag([SIGMA_RANGE_M**2, SIGMA_BEARING_RAD**2]) @ j.T


def load_memory_module():
    """Load the byte-vendored egomem2 module without adding top-level shims.

    The vendored file is unchanged.  Its two absolute harness imports are
    satisfied with the also-byte-vendored dependency files, only for the names
    that are not already present from a future merged implementation.
    """
    def module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        value.__package__ = 'harness'
        spec.loader.exec_module(value)
        return value
    for name, file in (
            ('harness.rovio_feature_statistics', VENDOR/'rovio_feature_statistics.py'),
            ('harness.egomem_object_association', VENDOR/'egomem_object_association.py')):
        if name not in sys.modules:
            sys.modules[name] = module(name, file)
    return module('harness.egonav_vendor.egocentric_landmark_memory',
                  VENDOR/'egocentric_landmark_memory.py')


def _segment_distance(point, start, end):
    point, start, end = (np.asarray(v, float) for v in (point, start, end))
    direction = end-start
    length2 = float(direction @ direction)
    if length2 <= 1e-12:
        return float(np.linalg.norm(point-start))
    u = float(np.clip((point-start) @ direction/length2, 0., 1.))
    return float(np.linalg.norm(point-(start+u*direction)))


class EgocentricGoto:
    """Bounded-state target memory + finite heading-pulse policy.

    ``option='off'`` is the default and returns an explicit stop without
    constructing or consulting any memory.  New candidates pass OPTION.
    """

    def __init__(self, *, option='off', target_kind=TARGET_KIND,
                 target_signature=TARGET_SIGNATURE, footprint_radius_m,
                 arrival_radius_m=ARRIVAL_RADIUS_M,
                 heading_tolerance_rad=HEADING_TOLERANCE_RAD,
                 far_candidate=False,
                 declared_target_hue=DECLARED_TARGET_HUE,
                 declared_target_hue_tolerance=DECLARED_TARGET_HUE_TOLERANCE):
        if option not in ('off', OPTION):
            raise ValueError('UNKNOWN_EGOCENTRIC_GOTO_OPTION')
        if not isinstance(far_candidate, (bool, np.bool_)):
            raise ValueError('INVALID_FAR_CANDIDATE_FLAG')
        if declared_target_hue is not None:
            try:
                declared_target_hue = float(declared_target_hue)
            except (TypeError, ValueError):
                raise ValueError('INVALID_DECLARED_TARGET_HUE')
            if not math.isfinite(declared_target_hue) or not 0 <= declared_target_hue < 180:
                raise ValueError('INVALID_DECLARED_TARGET_HUE')
        try:
            declared_target_hue_tolerance = float(declared_target_hue_tolerance)
        except (TypeError, ValueError):
            raise ValueError('INVALID_DECLARED_TARGET_HUE_TOLERANCE')
        if (not math.isfinite(declared_target_hue_tolerance)
                or declared_target_hue_tolerance < 0):
            raise ValueError('INVALID_DECLARED_TARGET_HUE_TOLERANCE')
        if not math.isfinite(footprint_radius_m) or footprint_radius_m <= 0:
            raise ValueError('OWN_FOOTPRINT_REQUIRED')
        if not math.isfinite(arrival_radius_m) or arrival_radius_m < 0:
            raise ValueError('INVALID_ARRIVAL_RADIUS')
        if not math.isfinite(heading_tolerance_rad) or heading_tolerance_rad < 0:
            raise ValueError('INVALID_HEADING_TOLERANCE')
        self.enabled = option == OPTION
        self.target_kind = target_kind
        self.target_signature = target_signature
        self.far_candidate = bool(far_candidate)
        self.far_candidate_state = None
        self.declared_target_hue = declared_target_hue
        self.declared_target_hue_tolerance = declared_target_hue_tolerance
        self.confirmed_hue = None
        self.footprint_radius_m = float(footprint_radius_m)
        self.arrival_radius_m = float(arrival_radius_m)
        # Derived from the actual calibrated pulse, never a fitted threshold:
        # a 180-degree flip after a small pulse would otherwise chatter.
        model_turn = abs(command_delta({'wheels': duty([0., 0., 1.])[0],
                                        'duration_s': duty([0., 0., 1.])[1]})[2])
        full_turn = (model_turn if TURN_RAD_PER_PULSE_P10 is None
                     else float(TURN_RAD_PER_PULSE_P10))
        # Own-command yaw transport uses the same frozen model, so rescale it
        # by the measured median/model ratio once the probe is applied.
        self.yaw_transport_scale = (
            1. if TURN_RAD_PER_PULSE_MEDIAN is None
            else float(TURN_RAD_PER_PULSE_MEDIAN)/max(1e-9, model_turn))
        self.turn_threshold_rad = max(float(heading_tolerance_rad), .5*full_turn)
        # One measured (lower-decile) full circle, not a multiplier on the
        # uncalibrated model; the probe's p10 already covers the slow tail.
        self.verify_limit = int(math.ceil(2*math.pi/max(1e-9, full_turn)))
        self.search_limit = int(math.ceil(2*math.pi/max(1e-9, full_turn)))
        self.stage = 'off' if not self.enabled else 'search'
        self.done = False
        self.events = []
        self.search_steps = 0
        self.search_sign = 1
        self.seen_target = False
        self.visible_previous = False
        self.last_visible_t = None
        self.last_visible_range_m = None
        self.verify_steps = 0
        self.rejected_previous = False
        self.small_marking_previous = False
        self.blocked_previous = False
        self.aim = None
        self.target_source = None
        self.last_observation_relative_xy_m = None
        self.memory_module = load_memory_module() if self.enabled else None
        self.language_context = (self.memory_module.language_context
                                 if self.enabled else None)
        self.memory = None
        self.memories = []
        self.last_command = None
        if self.enabled:
            self.memory = self.memory_module.LandmarkMemory(
                option=self.memory_module.OPTION,
                options=self.memory_module.MemoryOptions(implementation='legacy_v1'))
            self._event('controller_enabled', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=0.)

    def _event(self, reason, *, blocked_object, minimum_gap_m, gap_status, t, **extra):
        self.events.append(dict(category='egocentric_goto', reason=reason,
                                blocked_object=blocked_object,
                                minimum_gap_m=None if minimum_gap_m is None else float(minimum_gap_m),
                                gap_status=gap_status, t=float(t), stage=self.stage, **extra))

    def _far_event(self, reason, t, state, reason_category, **extra):
        """Candidate ledger: every row carries reason/blocked_object/min_gap."""
        self._event(reason, blocked_object='orange_object_below_zone_marking_area',
                    minimum_gap_m=None, gap_status='not_measured', t=t,
                    toggle=FAR_CANDIDATE_OPTION, reason_category=reason_category,
                    observed_area_m2=state.get('last_area'),
                    first_area_m2=state.get('first_area'),
                    frames=state.get('frames'), hue=state.get('hue'),
                    declared_hue=self.declared_target_hue,
                    declared_tolerance=self.declared_target_hue_tolerance,
                    confirmed_hue=self.confirmed_hue,
                    forward_approach=bool(state.get('forward_approach')), **extra)

    def _far_candidate(self, t, command, rejected_markings):
        """Track one below-gate orange patch; return it only after (a)(b)(c).

        Inputs are the same own-RGB observations already rejected by the birth
        gate and the own previously issued command.  Candidates never enter
        memory and never decide arrival; a returned candidate may only select
        the sign of the in-place search turn.
        """
        if not self.far_candidate:
            return None
        forward = issued_forward(command)
        candidates = []
        for obs in rejected_markings:
            xy = np.asarray(obs.get('relative_xy_m', []), float)
            if xy.shape != (2,) or not np.isfinite(xy).all():
                continue
            try:
                area = float(obs.get('observed_area_m2'))
            except (TypeError, ValueError):
                continue
            if math.isfinite(area) and area > 0:
                candidates.append((area, obs, xy))
        state = self.far_candidate_state
        if not candidates:
            if state is not None and t-state['last_t'] > FAR_CANDIDATE_MAX_AGE_S:
                self._far_event('far_candidate_expired', t, state, 'stale')
                self.far_candidate_state = None
            return None
        area, obs, xy = max(candidates, key=lambda value: value[0])
        try:
            hue = None if obs.get('hue') is None else float(obs.get('hue'))
        except (TypeError, ValueError):
            hue = None
        if state is None or t-state['last_t'] > FAR_CANDIDATE_MAX_AGE_S:
            state = dict(first_t=float(t), last_t=float(t), first_area=area,
                         last_area=area, frames=1, hue=hue,
                         relative_xy_m=xy.tolist(), forward_approach=False,
                         accepted=False, last_reason=None, logged_sign=None)
            self.far_candidate_state = state
            self._far_event('far_candidate_tracking', t, state, 'tracking')
            return None
        state['last_t'] = float(t)
        state['last_area'] = area
        state['relative_xy_m'] = xy.tolist()
        state['frames'] += 1
        state['forward_approach'] = bool(state['forward_approach'] or forward)
        if hue is None:
            reason = 'hue_not_measured'
        elif self.declared_target_hue is None:
            # Fail-closed only when the task/detector profile declares no
            # target hue class; an accepted-observation reference is not used.
            reason = 'hue_reference_unavailable'
        elif hue_distance(hue, self.declared_target_hue) > self.declared_target_hue_tolerance:
            reason = 'hue_mismatch'
        elif state['frames'] < FAR_CANDIDATE_MIN_FRAMES:
            reason = 'persistence'
        elif not state['forward_approach']:
            reason = 'no_forward_approach'
        elif area < state['first_area']*FAR_CANDIDATE_AREA_GROWTH_RATIO:
            reason = 'no_area_growth'
        else:
            reason = None
        if reason is not None:
            state['accepted'] = False
            if state['last_reason'] != reason:
                self._far_event('far_candidate_rejected', t, state, reason)
                state['last_reason'] = reason
            return None
        if not state['accepted']:
            state['accepted'] = True
            self._far_event('far_candidate_accepted', t, state, 'accepted')
        return state

    @staticmethod
    def _validate_memories(memories):
        forbidden = ('world_pose', 'qpos', 'qvel', 'static_map', 'ground_truth',
                     'held_object', 'held_world', 'truth_', 'map_pose')
        for item in memories:
            if not isinstance(item, dict):
                raise ValueError('MEMORY_ITEM_SCHEMA')
            bad = [k for k in item if any(k == prefix or k.startswith(prefix) for prefix in forbidden)]
            if bad:
                raise ValueError('WORLD_OR_HELD_INPUT_FORBIDDEN:'+','.join(sorted(bad)))

    def _target(self, memories):
        candidates = [m for m in memories
                      if m.get('kind') == self.target_kind
                      and m.get('signature') == self.target_signature
                      and np.asarray(m.get('relative_xy_m', []), float).shape == (2,)]
        if not candidates:
            return None
        # One-off orange false positives (e.g. a peer robot arm) can create a
        # nearer landmark.  The repeatedly associated target is the one with
        # the most observations; range is not a truth cue.
        return min(candidates, key=lambda m: (-int(m.get('observations', 0)),
                                              float(m.get('first_seen_s', 1e9)),
                                              m.get('id', '')))

    def goal_memory(self):
        """Primary target memory used by the policy (evaluation may read this)."""
        return self._target(self.memories)

    def _observed_target(self, observations, target):
        candidates = []
        for obs in observations:
            if obs.get('kind') != self.target_kind or obs.get('signature') != self.target_signature:
                continue
            xy = np.asarray(obs.get('relative_xy_m', []), float)
            if xy.shape == (2,) and np.isfinite(xy).all():
                distance = np.linalg.norm(xy) if target is None else np.linalg.norm(
                    xy-np.asarray(target['relative_xy_m'], float))
                candidates.append((float(distance), obs, xy))
        return min(candidates, key=lambda v: v[0]) if candidates else None

    def _obstacle_points(self, scan, obstacles):
        points = []
        for segment in (scan or {}).get('segments', []) or []:
            try:
                a, b = np.asarray(segment, float)
            except (TypeError, ValueError):
                continue
            if a.shape != (2,) or b.shape != (2,) or not np.isfinite(np.r_[a, b]).all():
                continue
            for u in np.linspace(0., 1., 5):
                points.append(a+u*(b-a))
        for point in obstacles or []:
            p = np.asarray(point, float)
            if p.shape == (2,) and np.isfinite(p).all():
                points.append(p)
        return np.asarray(points, float).reshape(-1, 2) if points else np.empty((0, 2))

    def _clearance(self, points, displacement=None):
        if len(points) == 0:
            return math.inf
        start = np.zeros(2)
        end = np.asarray(displacement if displacement is not None else np.zeros(2), float)
        return min(_segment_distance(p, start, end) for p in points)

    def _target_action(self, target, observation, points, t):
        xy = (np.asarray(observation[2], float) if observation is not None
              else np.asarray(target['relative_xy_m'], float))
        self.aim = xy.tolist()
        self.target_source = 'observed' if observation is not None else 'memory'
        distance = float(np.linalg.norm(xy))
        bearing = math.atan2(float(xy[1]), float(xy[0]))
        if distance <= self.arrival_radius_m:
            # A just-lost floor marking below the fisheye near field is still a
            # visual arrival: the final few centimetres are own-command
            # transport from a close observation, never a static-map/GT point.
            recent = (self.last_visible_t is not None and t-self.last_visible_t <= 1.5
                      and self.last_visible_range_m is not None
                      and self.last_visible_range_m <= .6)
            if observation is not None or recent:
                self.stage = 'arrive'
                self.done = True
                self._event('arrival' if observation is not None
                            else 'arrival_from_recent_close_observation',
                            blocked_object='not_observed', minimum_gap_m=None,
                            gap_status='not_measured', t=t, range_m=distance,
                            source=self.target_source,
                            last_visible_age_s=(None if self.last_visible_t is None
                                                else t-self.last_visible_t),
                            last_visible_range_m=self.last_visible_range_m)
                return self._stop(t, 'arrival')
            self.verify_steps += 1
            if self.verify_steps == 1:
                self._event('arrival_verify_look', blocked_object='not_observed',
                            minimum_gap_m=None, gap_status='not_measured', t=t,
                            range_m=distance, source=self.target_source)
            self.stage = 'verify'
            if self.verify_steps > self.verify_limit:
                self.done = True
                self._event('arrival_unverified', blocked_object='not_observed',
                            minimum_gap_m=None, gap_status='not_measured', t=t,
                            range_m=distance, source=self.target_source)
                return self._stop(t, 'arrival_unverified')
            return self._action([0., 0., float(self.search_sign)], t, 'verify',
                                0., distance)
        self.verify_steps = 0
        error = wrap(bearing)
        if abs(error) > self.turn_threshold_rad:
            gap = self._clearance(points)
            if gap < self.footprint_radius_m:
                self._event('turn_blocked', blocked_object='observed_obstacle',
                            minimum_gap_m=gap, gap_status='measured', t=t)
                self.stage = 'blocked'
                return self._stop(t, 'turn_blocked')
            self.stage = 'approach'
            return self._action([0., 0., 1. if error > 0 else -1.], t, 'turn', error, distance)
        gap = self._clearance(points)
        if gap < self.footprint_radius_m:
            self._event('forward_blocked', blocked_object='observed_obstacle',
                        minimum_gap_m=gap, gap_status='measured', t=t)
            self.stage = 'blocked'
            # VFH-style fallback: turn toward the side with more clearance.
            left = self._clearance(points[points[:, 1] >= 0] if len(points) else points)
            right = self._clearance(points[points[:, 1] < 0] if len(points) else points)
            sign = 1. if left >= right else -1.
            return self._action([0., 0., sign], t, 'avoid_turn', error, distance)
        forward = [1., 0., 0.]
        displacement = np.asarray(command_delta({'wheels': duty(forward)[0],
                                                'duration_s': duty(forward)[1]}))[:2]
        path_gap = self._clearance(points, displacement)
        if path_gap < self.footprint_radius_m:
            self._event('forward_path_blocked', blocked_object='observed_obstacle',
                        minimum_gap_m=path_gap, gap_status='measured', t=t)
            self.stage = 'blocked'
            left = self._clearance(points[points[:, 1] >= 0] if len(points) else points)
            right = self._clearance(points[points[:, 1] < 0] if len(points) else points)
            sign = 1. if left >= right else -1.
            return self._action([0., 0., sign], t, 'avoid_turn', error, distance)
        self.stage = 'approach'
        return self._action(forward, t, 'forward', error, distance)

    def _action(self, drive, t, kind, heading_error, distance):
        wheels, duration = duty(drive)
        return dict(kind=kind, drive=list(drive), wheels=list(wheels),
                    duration_s=list(duration), heading_error_rad=float(heading_error),
                    target_range_m=(float(distance) if math.isfinite(distance) else None),
                    target_source=self.target_source,
                    stage=self.stage, t=float(t))

    def _stop(self, t, reason):
        return dict(kind='stop', drive=[0., 0., 0.], wheels=[0., 0., 0., 0.],
                    duration_s=[0., 0., 0., 0.], heading_error_rad=None,
                    target_range_m=None, target_source=self.target_source,
                    stage=self.stage, t=float(t), reason=reason)

    def update_memory(self, t, command, observations=()):
        """Transport by own issued command, then correct with own RGB detections."""
        if not self.enabled:
            return []
        delta = (np.zeros(3) if command is None
                 else np.asarray(command_delta(command), float))
        delta[2] *= self.yaw_transport_scale
        covariance = np.diag(np.asarray(motion_variance(delta), float))
        # The area field is a controller-side birth gate; the vendored EKF
        # schema is fixed and rejects unknown observation fields.
        memory_observations = []
        for obs in observations:
            item = dict(obs)
            item.pop('observed_area_m2', None)
            memory_observations.append(item)
        result = self.memory.step(t, delta, covariance, memory_observations,
                                  observation_tick=bool(memory_observations))
        self.memories = result['memories']
        self.last_command = command
        return result

    def _zone_marking_observations(self, observations):
        """Only measured, target-sized floor markings may steer the policy."""
        accepted = []
        for obs in observations:
            if (obs.get('kind') != self.target_kind
                    or obs.get('signature') != self.target_signature):
                continue
            area = obs.get('observed_area_m2')
            if area is None:
                continue
            try:
                area = float(area)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(area) or area < ZONE_MARKING_MIN_OBSERVED_AREA_M2:
                continue
            accepted.append(obs)
        return accepted

    def step(self, t, command=None, observations=(), *, scan=None, obstacles=()):
        """One 10 Hz decision.  ``command`` is the previously issued command."""
        if not self.enabled:
            self.stage = 'off'
            self.done = True
            return self._stop(t, 'option_off')
        target_markings = [o for o in observations
                           if o.get('kind') == self.target_kind
                           and o.get('signature') == self.target_signature]
        observations = self._zone_marking_observations(observations)
        accepted_hues = []
        for o in observations:
            try:
                value = float(o.get('hue'))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                accepted_hues.append(value)
        if accepted_hues:
            # Diagnostic only: recorded in the ledger.  The far candidate judges
            # against DECLARED_TARGET_HUE, never against live observations.
            self.confirmed_hue = float(np.median(accepted_hues))
        accepted_ids = {id(o) for o in observations}
        rejected_markings = [o for o in target_markings if id(o) not in accepted_ids]
        small_rejected = bool(rejected_markings)
        if small_rejected and not self.small_marking_previous:
            self._event('small_marking_rejected',
                        blocked_object='orange_object_below_zone_marking_area',
                        minimum_gap_m=None, gap_status='not_measured', t=t,
                        observed_area_m2_min=min(
                            float(o.get('observed_area_m2') or 0.)
                            for o in rejected_markings))
        self.small_marking_previous = small_rejected
        prior_target = self.goal_memory()
        result = self.update_memory(t, command, observations)
        target = self.goal_memory()
        control_observations = observations
        rejected = False
        if (prior_target is not None and target is not None
                and target.get('id') == prior_target.get('id')):
            # Once a target memory exists, a colour patch that the vendored
            # EKF association gate rejects (e.g. an orange peer arm projected
            # onto the floor) must not become the drive target.  The accepted
            # re-observation set is generated from this frame's own RGB only.
            accepted = {e.get('observation') for e in result.get('events', ())
                        if e.get('reason') == 'reobserved'
                        and e.get('memory_id') == target.get('id')}
            control_observations = [o for o in observations if o.get('id') in accepted]
            rejected = len(control_observations) != len(observations)
        if rejected and not self.rejected_previous:
            self._event('target_observation_rejected',
                        blocked_object='non_floor_or_inconsistent_orange',
                        minimum_gap_m=None, gap_status='not_measured', t=t)
        self.rejected_previous = rejected
        observation = self._observed_target(control_observations, target)
        self.last_observation_relative_xy_m = (None if observation is None
                                               else list(observation[2]))
        visible = observation is not None
        if visible:
            self.last_visible_t = float(t)
            self.last_visible_range_m = float(np.linalg.norm(observation[2]))
        if visible and not self.seen_target:
            self.seen_target = True
            self._event('target_acquired', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=t,
                        source='observed')
        if self.seen_target and self.visible_previous and not visible:
            self._event('target_lost', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=t)
        if self.seen_target and visible and not self.visible_previous:
            self._event('target_reacquired', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=t)
        self.visible_previous = visible
        if target is not None or observation is not None:
            if target is None:
                # Defensive one-frame handoff only; memory birth happens in
                # LandmarkMemory.step from this same self-centered observation.
                target = dict(relative_xy_m=list(observation[2]),
                              range_m=float(np.linalg.norm(observation[2])),
                              age_s=0., id='observed-only', kind=self.target_kind,
                              signature=self.target_signature,
                              covariance_m2=point_covariance(observation[2]).tolist())
            self.search_steps = 0
            points = self._obstacle_points(scan, obstacles)
            return self._target_action(target, observation, points, t)
        candidate = self._far_candidate(t, command, rejected_markings)
        self.stage = 'search'
        self.search_steps += 1
        if self.search_steps > self.search_limit:
            self.done = True
            self._event('search_exhausted', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=t)
            return self._stop(t, 'search_exhausted')
        if self.search_steps == 1:
            self._event('search_started', blocked_object='not_observed',
                        minimum_gap_m=None, gap_status='not_measured', t=t)
        sign = float(self.search_sign)
        if candidate is not None:
            bearing = math.atan2(float(candidate['relative_xy_m'][1]),
                                 float(candidate['relative_xy_m'][0]))
            sign = 1. if bearing > 0. else -1.
            if candidate.get('logged_sign') != sign:
                self._far_event('far_candidate_turn', t, candidate, 'accepted',
                                bearing_rad=bearing, turn_sign=sign)
                candidate['logged_sign'] = sign
        return self._action([0., 0., sign], t, 'search', 0., math.inf)

    def context(self):
        memories = self.memories
        self._validate_memories(memories)
        items = []
        for m in memories:
            items.append(dict(
                id=m.get('id'), kind=m.get('kind'), signature=m.get('signature'),
                frame='self/current', relative_xy_m=m.get('relative_xy_m'),
                range_m=m.get('range_m'), bearing_rad=m.get('bearing_rad'),
                covariance_m2=m.get('covariance_m2'), last_seen_s=m.get('last_seen_s'),
                age_s=m.get('age_s'), radius95_m=m.get('radius95_m'),
                extent_unknown=bool(m.get('extent_unknown') or m.get('kind') == self.target_kind),
                source='own_rgb+own_commands', arrival_verified=False))
        result = dict(schema=SCHEMA, frame='self/current', items=items,
                      navigation_hint_relative_xy_m=(None if self.aim is None else list(self.aim)),
                      goal_signature=self.target_signature,
                      arrival_verified=False, held_world_reads=0,
                      static_map_control=0, top_camera_frames=0)
        if self.language_context is not None:
            result['language_context'] = self.language_context(
                memories, goal_signature=self.target_signature,
                footprint_radius_m=self.footprint_radius_m)
        return result
