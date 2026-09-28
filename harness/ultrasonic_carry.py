"""Pair-carry height vs the own front ultrasonic cone, and a carry-time sonar rule (#221, #246).

Simulator-free. Geometry is the M2 / v6 facing-pair ``long_beam`` carry: each
carrier grips 0.03 m in from its end at the calibrated 0.155 m grasp radius,
the robots face each other, and the lift is the M2 ``hover`` pose (tool z
0.095 m, recorded beam body z 0.0602-0.061 m over 31 door crossings, i.e.
about 10 mm of load sag below the commanded grip height).

Two clearance criteria for a level, lifted bar above the sensor axis:

* ``near_face``: the vertical end face nearest the sensor is above the cone.
  The remaining surfaces inside the cone are the bar's underside, met at
  grazing incidence (>= 73 deg), which the v1 echo model rejects. The rays
  under the bar reach the partner robot. Relies on the grazing assumption and
  on the bottom edge not diffracting a detectable echo (bench check needed).
* ``whole_beam``: no part of the bar is inside the cone. Binding point is the
  far end (0.647 m from the sensor), so the cone's rise over the whole bar
  applies.

``required_heights`` is parameterised by mount height/forward offset, the
cone half-angle and margins, because the mount is a photo estimate and the
robot geometry is being remodelled. ``lift_ik`` / ``max_tool_z`` use the
calibrated controller IK (``harness.visual_arm``), not the simulator.
"""
from __future__ import annotations

import math
from collections import deque
from functools import lru_cache
from dataclasses import dataclass, field

from harness import visual_arm as va
from harness.range_provider import RangeReport
from harness.ultrasonic_model import DEFAULT_SPEC, UltrasonicSpec

GRASP_RADIUS_M = .155            # sim.zone_cargo.GRASP_RADIUS_M (calibrated box/beam grasp)
GRIP_FROM_END_M = .03            # long_beam grip point is 0.03 m in from each end
BEAM_LENGTH_M = .60
GRIP_ABOVE_BOTTOM_M = .024       # sim.zone_cargo.GRASP_Z_M: grip point above the bar's underside
M2_LIFT_TOOL_Z_M = .095          # scripts/study_owncam_pair_beam.HOVER_Z_M (M2 / v6 lift pose)
M2_BEAM_BODY_Z_M = (.0602, .0610)  # recorded door-crossing range, experiments/2026-09-26-zone-m2-pair
M2_TILT_P95_DEG, M2_TILT_MAX_DEG = 1.76, 6.16   # 60 lifted M2 runs (same record)
IK_PITCH_RANGE_DEG = (-90, -40)  # harness.visual_arm.solve_grip_site_ik search range


@dataclass(frozen=True)
class CarryMargins:
    load_sag_m: float = .010          # commanded grip z - recorded bar underside - 0.024 (M2: 0.095-0.024-0.061)
    beam_pitch_deg: float = 2.0       # >= M2 p95 tilt 1.76 deg; the 6.16 deg max is reported as sensitivity
    height_m: float = .005            # servo / IK / sway allowance on the bar underside
    mount_pitch_up_deg: float = 0.    # unknown sensor tilt; widens the cone's upper edge


def cone_edge_deg(spec: UltrasonicSpec = DEFAULT_SPEC, margins: CarryMargins = CarryMargins(),
                  *, half_angle_deg: float | None = None) -> float:
    base = spec.half_angle_deg if half_angle_deg is None else half_angle_deg
    return base + spec.mount_pitch_deg + margins.mount_pitch_up_deg


def required_heights(criterion: str, spec: UltrasonicSpec = DEFAULT_SPEC, margins: CarryMargins = CarryMargins(),
                     *, half_angle_deg: float | None = None, grip_radius_m: float = GRASP_RADIUS_M,
                     beam_length_m: float = BEAM_LENGTH_M) -> dict:
    """Minimum bar underside and commanded tool z for the chosen criterion."""
    t = math.tan(math.radians(cone_edge_deg(spec, margins, half_angle_deg=half_angle_deg)))
    near = grip_radius_m - GRIP_FROM_END_M - spec.mount_x_m          # sensor -> near end face
    far = near + beam_length_m
    tilt = math.sin(math.radians(margins.beam_pitch_deg))
    if criterion == 'near_face':
        bottom = spec.mount_z_floor_m + near * t + GRIP_FROM_END_M * tilt + margins.height_m
    elif criterion == 'whole_beam':
        bottom = spec.mount_z_floor_m + far * t + beam_length_m * tilt + margins.height_m
    else:
        raise ValueError(f'unknown criterion {criterion!r}')
    return {'criterion': criterion, 'cone_edge_deg': cone_edge_deg(spec, margins, half_angle_deg=half_angle_deg),
            'near_face_from_sensor_m': near, 'far_end_from_sensor_m': far,
            'bar_bottom_min_m': bottom, 'tool_z_min_m': bottom + GRIP_ABOVE_BOTTOM_M + margins.load_sag_m}


def recommended_carry_tool_z(spec: UltrasonicSpec = DEFAULT_SPEC, margins: CarryMargins = CarryMargins(), *,
                             step_m: float = .005) -> float:
    """Commanded lift (grip z) for the ``near_face`` criterion at the published 15 deg, rounded up.

    Raises when the calibrated IK cannot reach it at the grasp radius. Re-evaluate
    whenever the mount height/offset changes (robot remodel, bench measurement).
    """
    need = required_heights('near_face', spec, margins, half_angle_deg=max(15., spec.half_angle_deg))['tool_z_min_m']
    z = round(math.ceil(need / step_m - 1e-9) * step_m, 4)
    reach = max_tool_z()['tool_z_m']
    if reach is None or z > reach:
        raise ValueError(f'carry height {z:.3f} m exceeds the calibrated arm reach {reach}')
    return z


def expected_bar_bottom(tool_z_m: float, margins: CarryMargins = CarryMargins()) -> float:
    return tool_z_m - GRIP_ABOVE_BOTTOM_M - margins.load_sag_m


def max_tool_z(radius_m: float = GRASP_RADIUS_M, pitch_range_deg=IK_PITCH_RANGE_DEG, step_m: float = .001) -> dict:
    return dict(_max_tool_z(float(radius_m), tuple(pitch_range_deg), float(step_m)))


@lru_cache(maxsize=32)
def _max_tool_z(radius_m: float, pitch_range_deg: tuple, step_m: float) -> tuple:
    """Highest grip z the calibrated IK solves at this radius (pulses within the safe PWM range)."""
    best = {'tool_z_m': None, 'pitch_deg': None}
    for pitch in range(int(pitch_range_deg[0]), int(pitch_range_deg[1]) + 1):
        z = .0
        while z < .40:
            if va._ik_at_pitch(radius_m * 100., z * 100. - va.ROBOT_BASE_FLOOR_HEIGHT_CM, float(pitch)) is not None:
                if best['tool_z_m'] is None or z > best['tool_z_m'] + 1e-9:
                    best = {'tool_z_m': round(z, 4), 'pitch_deg': pitch}
            z += step_m
    return tuple(best.items())


def grasp_pose(radius_m: float = GRASP_RADIUS_M) -> dict:
    return va.solve_grip_ik(radius_m, 0., GRIP_ABOVE_BOTTOM_M, -90)


def lift_ik(tool_z_m: float, radius_m: float = GRASP_RADIUS_M) -> dict:
    """The M2 lift rule: same radius, pitch as close as possible to the grasp pitch."""
    pitch = va.tool_pose(grasp_pose(radius_m)).pitch_deg
    pose = va.solve_grip_ik(radius_m, 0., tool_z_m, pitch)
    tp = va.tool_pose(pose)
    return {'pulses': pose, 'tool_z_m': tp.z_m, 'pitch_deg': tp.pitch_deg,
            'pitch_change_from_grasp_deg': tp.pitch_deg - pitch}


# --- carry-time sonar rule -----------------------------------------------------------------------

FORMATION_OK = 'formation_ok'           # reading at the baseline (partner under/around the bar)
LOAD_PRESENT = 'load_present'           # low mode: reading at the load's own end face
LOAD_IN_CONE = 'load_in_cone'           # high mode: something within the near field -> bar sagged/slipped
INTRUSION = 'intrusion'                 # shorter than the baseline but beyond the near field
BEYOND_BASELINE = 'beyond_baseline'     # longer than the baseline, or no echo
LOAD_LOST = 'load_lost'                 # low mode: load reading jumped longer
CALIBRATING = 'calibrating'
UNKNOWN = 'unknown'
STOP_STATES = (LOAD_IN_CONE, INTRUSION, BEYOND_BASELINE, LOAD_LOST)


@dataclass
class CarrySonarMonitor:
    """Own-reading rule for the lifted carry. Baseline = median of the first own readings after the lift.

    ``mode='above_cone'`` (lift >= ``required_heights('near_face')``): the baseline is
    whatever the rays reach under the bar (normally the partner's chassis).
    ``mode='load_in_cone'`` (the current M2 lift): the baseline is the own load's
    end face (~0.05 m); a jump longer means the load left the cone (slip/drop).
    A state is reported only after ``k`` consecutive agreeing readings (60 ms each).
    """
    mode: str = 'above_cone'
    spec: UltrasonicSpec = DEFAULT_SPEC
    near_field_m: float = .12
    band_k_sigma: float = 4.
    band_min_m: float = .02
    k: int = 3
    n_baseline: int = 5
    baseline_m: float | None = field(default=None, init=False)
    _cal: list = field(default_factory=list, init=False)
    _recent: deque = field(default_factory=lambda: deque(maxlen=16), init=False)
    _last_t: float | None = field(default=None, init=False)

    def __post_init__(self):
        if self.mode not in ('above_cone', 'load_in_cone'):
            raise ValueError('mode must be above_cone or load_in_cone')

    def band(self) -> float:
        return max(self.band_min_m, self.band_k_sigma * self.spec.sigma_m(self.baseline_m or 0.))

    def _classify(self, report: RangeReport) -> str:
        b = self.baseline_m
        if not report.valid:
            return BEYOND_BASELINE if self.mode == 'above_cone' else LOAD_LOST
        r = report.range_m
        if self.mode == 'load_in_cone':
            return LOAD_PRESENT if abs(r - b) <= self.band() else (LOAD_LOST if r > b else UNKNOWN)
        if abs(r - b) <= self.band():
            return FORMATION_OK
        if r > b:
            return BEYOND_BASELINE
        return LOAD_IN_CONE if r <= self.near_field_m else INTRUSION

    def update(self, report: RangeReport) -> str:
        """Feed each NEW own report (time ordered); returns the debounced state."""
        if report.t_meas is None or (self._last_t is not None and report.t_meas <= self._last_t):
            return self.state()
        self._last_t = report.t_meas
        if self.baseline_m is None:
            if report.valid:
                self._cal.append(report.range_m)
            if len(self._cal) >= self.n_baseline:
                ordered = sorted(self._cal)
                self.baseline_m = ordered[len(ordered) // 2]
            return CALIBRATING if self.baseline_m is None else self.state()
        self._recent.append(self._classify(report))
        return self.state()

    def state(self) -> str:
        if self.baseline_m is None:
            return CALIBRATING
        tail = list(self._recent)[-self.k:]
        if len(tail) == self.k and len(set(tail)) == 1:
            return tail[0]
        return UNKNOWN
