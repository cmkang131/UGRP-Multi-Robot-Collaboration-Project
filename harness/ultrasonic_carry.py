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

Also: solo carry of the small final-study items (``SOLO_ITEMS``, ``solo_posture_margins``,
``recommended_solo_tool_z``, the forward rule ``solo_forward_state``) and the v2 / v3
(draft PR #249) geometry parameters (``RobotGeometry``, ``arm_links`` for link sensitivity).
"""
from __future__ import annotations

import math
from collections import deque
from contextlib import contextmanager
from functools import lru_cache
from dataclasses import dataclass, field, replace

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
class RobotGeometry:
    """Sensor mount and arm-axis placement in the robot floor frame (x forward from the chassis centre)."""
    name: str
    mount_x_m: float
    mount_z_m: float
    arm_axis_x_m: float = 0.            # arm yaw axis ahead of the chassis centre
    link2_cm: float = va.LINK_2_CM       # upper arm (SDK 6.5 cm)
    gripper_cm: float = va.GRIPPER_LINK_CM
    source: str = ''

    def spec(self, base: UltrasonicSpec = DEFAULT_SPEC) -> UltrasonicSpec:
        return replace(base, mount_x_m=self.mount_x_m, mount_z_floor_m=self.mount_z_m)


GEOMETRY_V2 = RobotGeometry('v2', DEFAULT_SPEC.mount_x_m, DEFAULT_SPEC.mount_z_floor_m, 0.,
                            source='current SIM model (photo nominal mount, arm axis at the chassis centre)')
# Draft PR #249 remodel: drawing-scaled, not measured. Sonar on the arm-base box front face, level.
GEOMETRY_V3 = RobotGeometry('v3', .0880, .0617, .0482,
                            source='PR #249 drawing layout (not measured): sonar 88.0/61.7 mm, arm axis +48.2 mm')
GEOMETRIES = {'v2': GEOMETRY_V2, 'v3': GEOMETRY_V3}
# Proposed (not applied) drawing link lengths, for reach sensitivity only.
DRAWING_LINK2_CM, DRAWING_GRIPPER_CM = 5.77, 9.40


@contextmanager
def arm_links(link2_cm: float | None = None, gripper_cm: float | None = None):
    """Temporarily evaluate the controller IK/FK with other link lengths (sensitivity only)."""
    saved = (va.LINK_2_CM, va.GRIPPER_LINK_CM, dict(va.tool_pose.__kwdefaults__))
    try:
        if link2_cm is not None:
            va.LINK_2_CM = float(link2_cm)
        if gripper_cm is not None:
            va.GRIPPER_LINK_CM = float(gripper_cm)
            va.tool_pose.__kwdefaults__['tool_length_cm'] = float(gripper_cm)
        yield
    finally:
        va.LINK_2_CM, va.GRIPPER_LINK_CM = saved[0], saved[1]
        va.tool_pose.__kwdefaults__.clear()
        va.tool_pose.__kwdefaults__.update(saved[2])


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
                     beam_length_m: float = BEAM_LENGTH_M, arm_axis_x_m: float = 0.) -> dict:
    """Minimum bar underside and commanded tool z for the chosen criterion."""
    t = math.tan(math.radians(cone_edge_deg(spec, margins, half_angle_deg=half_angle_deg)))
    near = arm_axis_x_m + grip_radius_m - GRIP_FROM_END_M - spec.mount_x_m   # sensor -> near end face
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
                             step_m: float = .005, arm_axis_x_m: float = 0.) -> float:
    """Commanded lift (grip z) for the ``near_face`` criterion at the published 15 deg, rounded up.

    Raises when the calibrated IK cannot reach it at the grasp radius. Re-evaluate
    whenever the mount height/offset changes (robot remodel, bench measurement).
    """
    need = required_heights('near_face', spec, margins, half_angle_deg=max(15., spec.half_angle_deg),
                            arm_axis_x_m=arm_axis_x_m)['tool_z_min_m']
    z = round(math.ceil(need / step_m - 1e-9) * step_m, 4)
    reach = max_tool_z()['tool_z_m']
    if reach is None or z > reach:
        raise ValueError(f'carry height {z:.3f} m exceeds the calibrated arm reach {reach}')
    return z


def expected_bar_bottom(tool_z_m: float, margins: CarryMargins = CarryMargins()) -> float:
    return tool_z_m - GRIP_ABOVE_BOTTOM_M - margins.load_sag_m


def max_tool_z(radius_m: float = GRASP_RADIUS_M, pitch_range_deg=IK_PITCH_RANGE_DEG, step_m: float = .001) -> dict:
    return dict(_max_tool_z(float(radius_m), tuple(pitch_range_deg), float(step_m), va.LINK_2_CM, va.GRIPPER_LINK_CM))


@lru_cache(maxsize=64)
def _max_tool_z(radius_m: float, pitch_range_deg: tuple, step_m: float, _link2: float, _gripper: float) -> tuple:
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


# --- solo carry (one robot, one small item) --------------------------------------------------------

@dataclass(frozen=True)
class SoloItem:
    """A solo item as held: grip frame x forward, y left, z up, origin at the grip point."""
    kind: str
    shape: str                      # 'box' | 'cylinder'
    half_x_m: float                 # box: along the reach; cylinder: radius
    half_y_m: float
    height_m: float
    grip_above_bottom_m: float
    mass_kg: float
    source: str


# Final-study solo kinds (configs/zone_study_scenarios: cyan/green/red boxes, can, tile).
SOLO_ITEMS = {
    'box': SoloItem('box', 'box', .017, .020, .032, .024, .030,
                    'sim/research_dispatch_arena.py dispatch_box 34x40x32 mm, 0.03 kg; zone colour replicas'),
    'can': SoloItem('can', 'cylinder', .019, .019, .050, .024, .080, 'sim/zone_cargo.py can 38x50 mm, 0.08 kg'),
    'tile': SoloItem('tile', 'box', .030, .020, .012, .007, .025, 'sim/zone_cargo.py tile 60x40x12 mm, 0.025 kg'),
}
# The own executor's solo carry posture (harness/owncam_drive.CARRY_POSTURE, "carry_p30"):
# grip 0.14 m ahead, 0.18 m high, tool pitch -30 deg (experiments/2026-09-25-zone-owncam-skill).
CARRY_P30 = {1: 1500, 3: 777, 4: 2053, 5: 1646, 6: 1500}
# Recorded carry_p30 held-box tilt from the grasp (same record): ~32 deg (tool pitch -90 -> -30 then).
CARRY_P30_RECORDED_TILT_DEG = 32.


@dataclass(frozen=True)
class SoloMargins:
    load_sag_m: float = .010        # held item below the commanded grip (conservative; carry_p30 record ~4-12 mm)
    swing_deg: float = 5.           # extra item pitch in the jaws around each tilt case
    height_m: float = .005


def solo_vertices(item: SoloItem, n_rim: int = 24):
    """Convex-hull vertices of the held item in the level grip frame."""
    import numpy as np
    zb, zt = -item.grip_above_bottom_m, item.height_m - item.grip_above_bottom_m
    if item.shape == 'box':
        xy = [(sx * item.half_x_m, sy * item.half_y_m) for sx in (-1, 1) for sy in (-1, 1)]
    else:
        xy = [(item.half_x_m * math.cos(a), item.half_x_m * math.sin(a))
              for a in np.linspace(0., 2 * math.pi, n_rim, endpoint=False)]
    return np.array([(x, y, z) for x, y in xy for z in (zb, zt)], float)


def item_points(item: SoloItem, grip_x_m: float, grip_z_m: float, tilt_deg: float, sag_m: float = 0.):
    """Item vertices in the robot floor frame; ``tilt_deg`` > 0 raises the forward edge (tool pitched up)."""
    import numpy as np
    t = math.radians(tilt_deg)
    rot = np.array([[math.cos(t), 0., -math.sin(t)], [0., 1., 0.], [math.sin(t), 0., math.cos(t)]])
    return solo_vertices(item) @ rot.T + np.array([grip_x_m, 0., grip_z_m - sag_m])


def cone_margin(points, spec: UltrasonicSpec = DEFAULT_SPEC, *, half_angle_deg: float | None = None,
                mount_pitch_up_deg: float = 0.) -> float:
    """Min over points of height above the cone's upper tangent plane (> 0: whole item outside the cone).

    The cone lies below the plane z - z_s = dx * tan(edge), so a convex item whose
    vertices are all above it is outside the cone (sufficient, conservative).
    """
    edge = (spec.half_angle_deg if half_angle_deg is None else half_angle_deg) + spec.mount_pitch_deg + mount_pitch_up_deg
    t = math.tan(math.radians(edge))
    return float(min(p[2] - spec.mount_z_floor_m - max(0., p[0] - spec.mount_x_m) * t for p in points))


def solo_lift(item: SoloItem, tool_z_m: float, radius_m: float = GRASP_RADIUS_M) -> dict:
    grasp = va.solve_grip_ik(radius_m, 0., item.grip_above_bottom_m, -90)
    g_pitch = va.tool_pose(grasp).pitch_deg
    pose = va.solve_grip_ik(radius_m, 0., tool_z_m, g_pitch)
    tp = va.tool_pose(pose)
    return {'grasp_pulses': grasp, 'grasp_pitch_deg': g_pitch, 'pulses': pose, 'tool_x_m': tp.x_m,
            'tool_z_m': tp.z_m, 'pitch_deg': tp.pitch_deg, 'pitch_change_from_grasp_deg': tp.pitch_deg - g_pitch}


def solo_posture_margins(item: SoloItem, pulses: dict, grasp_pitch_deg: float, spec: UltrasonicSpec = DEFAULT_SPEC,
                         margins: SoloMargins = SoloMargins(), *, half_angle_deg: float = 15.,
                         extra_tilts_deg=(), arm_axis_x_m: float = 0.) -> dict:
    """Cone margin for level and rigid (tilt = pitch change) holds, each +- swing, sag applied."""
    tp = va.tool_pose(pulses)
    gx = tp.x_m + arm_axis_x_m
    rigid = tp.pitch_deg - grasp_pitch_deg
    cases = {}
    for name, tilt in (('level', 0.), ('rigid', rigid), *((f'tilt_{t:g}', t) for t in extra_tilts_deg)):
        worst = min(cone_margin(item_points(item, gx, tp.z_m, tilt + s, margins.load_sag_m), spec,
                                half_angle_deg=half_angle_deg) for s in (-margins.swing_deg, 0., margins.swing_deg))
        cases[name] = {'tilt_deg': round(tilt, 2), 'margin_m': round(worst - margins.height_m, 4)}
    front = max(float(item_points(item, gx, tp.z_m, t)[:, 0].max()) for t in (0., rigid))
    return {'tool_x_m': round(tp.x_m, 4), 'tool_z_m': round(tp.z_m, 4), 'pitch_deg': round(tp.pitch_deg, 2),
            'item_front_beyond_sensor_m': round(max(0., front - spec.mount_x_m), 4),
            'cases': cases, 'clear': all(c['margin_m'] >= 0. for c in cases.values())}


def recommended_solo_tool_z(kind: str, spec: UltrasonicSpec = DEFAULT_SPEC, margins: SoloMargins = SoloMargins(), *,
                            radius_m: float = GRASP_RADIUS_M, step_m: float = .005, half_angle_deg: float = 15.,
                            arm_axis_x_m: float = 0.) -> float:
    """Lowest straight-lift grip z (grasp radius, grasp-pitch rule) that clears the cone in every tilt case."""
    item = SOLO_ITEMS[kind]
    z = .03
    while z <= .20 + 1e-9:
        try:
            lift = solo_lift(item, z, radius_m)
        except ValueError:
            z = round(z + step_m, 4)
            continue
        if solo_posture_margins(item, lift['pulses'], lift['grasp_pitch_deg'], spec, margins,
                                half_angle_deg=half_angle_deg, arm_axis_x_m=arm_axis_x_m)['clear']:
            return round(z, 4)
        z = round(z + step_m, 4)
    raise ValueError(f'no reachable straight-lift height clears the cone for {kind}')


def turn_in_place_grip_shift_m(turn_deg: float, geometry: RobotGeometry = GEOMETRY_V2) -> float:
    """Grip displacement when the base spins about its own centre and the arm counter-yaws.

    Zero when the arm yaw axis is at the chassis centre (v2). With an offset axis (v3) the
    base must instead rotate about the arm axis (mecanum: spin plus a matching translation,
    possible in principle, not implemented or verified).
    """
    return 2. * abs(geometry.arm_axis_x_m) * abs(math.sin(math.radians(turn_deg) / 2.))


# --- solo forward rule -----------------------------------------------------------------------------

CLEAR, SLOW, STOP, STOP_NEAR_FIELD, NO_READING = 'clear', 'slow', 'stop', 'stop_near_field', 'no_reading'


def solo_stop_distance(front_extent_from_sensor_m: float, *, speed_mps: float = .19, reaction_s: float = .30,
                       margin_m: float = .02) -> float:
    """Sensor range at which to stop: load/body front + reaction travel + margin.

    Defaults: forward command <= 0.12 x motion gain <= 1.6 (owncam_drive, zone_own_guards);
    reaction = one 60 ms reading + 2-reading debounce + 0.1 s control step; margin = BASE_MARGIN_M.
    """
    return front_extent_from_sensor_m + speed_mps * reaction_s + margin_m


def solo_forward_state(report: RangeReport, now: float, expected, *, front_extent_from_sensor_m: float,
                       stop_m: float, slow_m: float, max_age_s: float = .2,
                       spec: UltrasonicSpec = DEFAULT_SPEC, pose_sigma_m: float = 0.) -> dict:
    """One own reading vs the static-map prediction during a solo carry (forward drive).

    ``state`` is an extra stop/slow input next to the existing sweep/collision guard,
    never a replacement. ``consistency`` feeds the PF / overconfidence check.
    """
    from harness.ultrasonic_map import range_consistency
    if report.t_meas is None or now - report.t_meas > max_age_s + 1e-9:
        return {'state': NO_READING, 'consistency': None}
    consistency = range_consistency(report.range_m if report.valid else None, report.valid, expected, spec,
                                    pose_sigma_m=pose_sigma_m)
    if not report.valid:
        return {'state': CLEAR, 'consistency': consistency}
    r = report.range_m
    if r <= front_extent_from_sensor_m + .02:
        state = STOP_NEAR_FIELD        # own load sagged into the cone, or contact-range obstacle
    elif r <= stop_m:
        state = STOP
    elif r <= slow_m:
        state = SLOW
    else:
        state = CLEAR
    return {'state': state, 'consistency': consistency}
