"""Own-camera pose source for M1: localizer -> ``PoseReport`` -> skill ``PoseEstimate``.

Inputs are exactly the robot's own issued commands and its own ``robot_cam``
frames (plus the static tagged map and fixed calibrations). Nothing here
imports the simulator; ``tests/test_m1_owncam.py`` checks the boundary.

``PoseReport`` carries what a controller needs to decide whether it may trust
the estimate (Codex review #4): the estimate time, initialisation state,
covariance and standard deviations, time since the last tag, the last valid
observation, and the load state inferred from own commands. ``check_limits``
returns every violated limit so the controller can stop and re-look.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from harness.owncam_localizer import OwnCamLocalizer
from harness.wall_tags import TagDetector
from harness.owncam_time import POSE_TIME_ROUNDING_S, finite_time

SOURCE_PREFIX = 'owncam_pf_v2'


@dataclass(frozen=True)
class PoseReport:
    t_est: float
    initialized: bool
    x_m: float = float('nan')
    y_m: float = float('nan')
    yaw_rad: float = float('nan')
    cov: tuple = ()
    std_xy_m: float = float('inf')
    std_yaw_rad: float = float('inf')
    since_tag_s: float | None = None
    last_valid_obs: Mapping | None = None
    n_eff: float | None = None
    load_state: str = 'unloaded'
    source: str = SOURCE_PREFIX

    # Legacy since_tag_s is retained for frozen consumers only. Never derive a
    # raw fix timestamp from that separately rounded age.
    last_fix_t: float | None = None
    fix_age_s: float | None = None
    fix_source: str | None = None
    observation_quality: Mapping | None = None

    def as_dict(self) -> dict:
        return {'t_est': round(self.t_est, 4), 'initialized': self.initialized,
                'xyyaw': [round(self.x_m, 5), round(self.y_m, 5), round(self.yaw_rad, 6)] if self.initialized else None,
                'std_xy_m': None if not self.initialized else round(self.std_xy_m, 5),
                'std_yaw_rad': None if not self.initialized else round(self.std_yaw_rad, 5),
                'since_tag_s': None if self.since_tag_s is None else round(self.since_tag_s, 3),
                'last_valid_obs': self.last_valid_obs, 'n_eff': self.n_eff, 'load_state': self.load_state,
                'source': self.source, 'last_fix_t': self.last_fix_t, 'fix_age_s': self.fix_age_s,
                'fix_source': self.fix_source, 'observation_quality': self.observation_quality}


@dataclass(frozen=True)
class PoseLimits:
    """Limits under which the controller may act on the estimate."""
    max_std_xy_m: float
    max_std_yaw_rad: float
    max_since_tag_s: float | None = None     # None: no tag-recency requirement
    max_age_s: float = .3
    max_since_look_s: float | None = None    # require a completed look this recently
    name: str = ''


def check_limits(report: PoseReport, now: float, limits: PoseLimits, *, since_look_s: float | None = None) -> list[str]:
    """Every violated limit (empty list = the estimate may be used)."""
    bad = []
    if not report.initialized:
        return ['not_initialized']
    if not finite_time(now) or not finite_time(report.t_est):
        bad.append('invalid_time')
    elif now - report.t_est < -POSE_TIME_ROUNDING_S:
        bad.append('future')
    elif now - report.t_est > limits.max_age_s + POSE_TIME_ROUNDING_S:
        bad.append('stale')
    if not math.isfinite(report.std_xy_m) or report.std_xy_m > limits.max_std_xy_m:
        bad.append('std_xy')
    if not math.isfinite(report.std_yaw_rad) or report.std_yaw_rad > limits.max_std_yaw_rad:
        bad.append('std_yaw')
    if limits.max_since_tag_s is not None and (report.since_tag_s is None or report.since_tag_s > limits.max_since_tag_s):
        bad.append('since_tag')
    if limits.max_since_look_s is not None and (since_look_s is None or since_look_s > limits.max_since_look_s):
        bad.append('since_look')
    return bad


def calibration_label(params: Mapping) -> str:
    blob = json.dumps(params, sort_keys=True, separators=(',', ':')).encode()
    return f'{SOURCE_PREFIX}:{hashlib.sha256(blob).hexdigest()[:8]}'


class FixReportingLocalizer(OwnCamLocalizer):
    """Adapt legacy estimate consumers without changing the frozen PF algorithm."""

    def estimate(self):
        est = super().estimate()
        est.update(last_fix_t=self.last_tag_t, fix_age_s=est.get('since_tag_s'),
                   fix_source='tags_temporary')
        return est


@dataclass
class OwnCamPoseSource:
    """Feeds the localizer with own commands and own frames; reports ``PoseReport``."""
    static_map: Mapping
    params: Mapping
    seed: int = 0
    width: int = 640
    height: int = 480
    loc: OwnCamLocalizer = field(init=False)
    detector: TagDetector = field(init=False)
    source: str = field(init=False)

    def __post_init__(self):
        self.loc = FixReportingLocalizer(self.static_map, self.params, seed=self.seed)
        self.detector = TagDetector.for_map(self.static_map, self.width, self.height)
        self.source = calibration_label(self.params)
        self.servo: dict[int, int] = {}
        self.last_obs = None
        self.frames = 0

    def begin_relocalization(self, now, servo):
        if getattr(self, 'recovery_v6', False):
            return self.begin_observation(now, servo)
        # Preserve the old PF reset and RNG consumption exactly.
        self.loc = FixReportingLocalizer(self.static_map, self.loc.params,
                                  seed=int(self.loc.rng.integers(1 << 30)))
        self.loc.command({'t': float(now), 'kind': 'initial_servo_command', 'pulses': dict(servo)})
        self.servo = dict(servo)

    def expected_observability(self, pose, pan, static_map):
        if getattr(self, 'recovery_v6', False):
            from harness.owncam_observability_v6 import expected_observability
            return expected_observability(self.loc, pose, pan, static_map)
        return expected_tag_observability(pose, pan, static_map)

    def begin_observation(self, now, servo, *, lost=False):
        if not getattr(self, 'recovery_v6', False):
            raise ValueError('posterior recovery v6 is not enabled')
        self.loc.predict_to(now)
        # Issued PWM bookkeeping already arrived through on_command. A look
        # request is neither a motor command nor a new absolute observation.
        return self.loc.request_recovery() if lost else True

    def get_motion_params(self) -> dict:
        import copy
        return copy.deepcopy(self.loc._motion_params())

    def on_command(self, row: Mapping) -> None:
        """One own issued command (time ordered, as logged at the robot's port)."""
        self.loc.command(row)
        kind = row['kind']
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def set_motion_profile(self, now: float, name: str | None) -> None:
        """The controller names its own manipulation phase (own state, not a measurement)."""
        if name != self.loc.motion_profile:
            self.loc.set_motion_profile(now, name)

    def on_frame(self, now: float, rgb: np.ndarray) -> PoseReport:
        """One own ``robot_cam`` frame (RGB array decoded from the JPEG the robot saw)."""
        if getattr(self, 'recovery_v6', False):
            key = hashlib.sha256(rgb.tobytes()).hexdigest()
            if key == getattr(self, '_last_image_digest', None):
                return self.report(now)  # same pixels cannot create a new fix
            self._last_image_digest = key
        dets = self.detector.detect(rgb)
        self.frames += 1
        edge = getattr(self, 'beam_edge', None)
        if edge is not None:
            # v6e carry_beam_edge: own-RGB robot-minus-beam relative-yaw increment (harness/own_beam_edge.py)
            dyaw = edge.observe(now, rgb, self.servo, self.loc.load.loaded)
            if dyaw:
                self.loc.apply_relative_yaw(now, dyaw)
        if getattr(self, 'carry_yaw_fallback', None) is not None:
            from harness import owncam_carry_v6e
            owncam_carry_v6e.update_availability(self, now)
        self.loc.update(now, dets, dict(self.servo))
        if dets:
            self.last_obs = {'t': round(now, 4), 'tag_ids': sorted(int(d['id']) for d in dets), 'n_tags': len(dets)}
        return self.report(now)

    def report(self, now: float) -> PoseReport:
        self.loc.predict_to(now)
        est = self.loc.estimate()
        load = 'loaded' if self.loc.load.loaded else 'unloaded'
        if not est.get('initialized'):
            return PoseReport(t_est=float(now), initialized=False, load_state=load, source=self.source,
                              last_valid_obs=self.last_obs, fix_source='tags_temporary')
        w = np.exp(self.loc.logw - self.loc.logw.max())
        n_eff = float(w.sum()**2/np.sum(w*w))
        quality = (dict(self.loc.quality) if getattr(self, 'recovery_v6', False) else
                   {'accepted': self.loc.last_tag_t == now,
                    'observed_features': 0 if self.last_obs is None else self.last_obs['n_tags']})
        if getattr(self, 'recovery_v6', False):
            quality.update(last_fix_quality=self.loc.last_fix_quality, lost=self.loc.inconsistent_frames >= 3)
            offsets = self.loc.px - [est['x'],est['y'],est['yaw']]
            angles = (offsets[:,2]+math.pi)%(2*math.pi)-math.pi
            quality['posterior_envelope'] = {
                'xy_radius_m':float(np.linalg.norm(offsets[:,:2],axis=1).max()),
                'yaw_radius_rad':float(np.abs(angles).max()),
                'scope':'all current PF hypotheses; not calibrated physical coverage'}
        fix_t = (self.loc.last_informative_t if getattr(self, 'recovery_v6', False) else self.loc.last_tag_t)
        return PoseReport(t_est=float(est['t']), initialized=True, x_m=est['x'], y_m=est['y'], yaw_rad=est['yaw'],
                          cov=tuple(tuple(r) for r in est['cov']), std_xy_m=est['std_xy_m'],
                          std_yaw_rad=est['std_yaw_rad'], since_tag_s=est.get('since_tag_s'),
                          last_valid_obs=self.last_obs, n_eff=round(n_eff, 1), load_state=load, source=self.source,
                          last_fix_t=fix_t, fix_age_s=est.get('since_tag_s'),
                          fix_source='tags_temporary',
                          observation_quality=quality)


def to_skill_estimate(report: PoseReport, pose_estimate_cls):
    """Skill ``PoseEstimate`` from a checked report (raises when not initialised)."""
    if not report.initialized:
        raise ValueError('pose report not initialised')
    return pose_estimate_cls(report.x_m, report.y_m, report.yaw_rad, report.source)


def mean_xy(points: Sequence[Sequence[float]]) -> tuple[float, float]:
    a = np.asarray(points, float)
    return float(a[:, 0].mean()), float(a[:, 1].mean())


def expected_tag_observability(pose, pan, static_map):
    """Temporary provider's historical projected-area score, byte-equivalent arithmetic.

    Visibility is predicted only. Occlusion/pose error can invalidate it; a
    subsequent accepted own observation and the unchanged gates are required.
    """
    from harness.owncam_drive import LOOK_P20
    from harness.owncam_view import project_base_points, valid_pixel_mask
    from harness.wall_tags import tag_world_frame

    c, s = math.cos(pose.yaw), math.sin(pose.yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    valid = valid_pixel_mask()
    target = {**LOOK_P20, 6: pan}
    score = 0.
    for tag in static_map.get('landmarks', {}).get('tags', []):
        center, axes = tag_world_frame(tag)
        if np.dot(np.array([pose.x, pose.y]) - center[:2], tag['normal_xy']) <= 0:
            continue
        h = tag['size_m'] / 2
        corners = np.array([[-h, h, 0.], [h, h, 0.], [h, -h, 0.], [-h, -h, 0.]]) @ axes.T + center
        points = (corners - np.array([pose.x, pose.y, 0.])) @ rot
        px = project_base_points(target, points)
        if not np.isfinite(px).all() or not ((px >= 1).all() and (px < [639, 479]).all()):
            continue
        uv = px.astype(int)
        side = float(np.mean(np.linalg.norm(px - np.roll(px, 1, axis=0), axis=1)))
        if side >= 8. and valid[uv[:, 1], uv[:, 0]].all():
            score += side * side

    return score
