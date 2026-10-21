"""Self-centric navigation adapter scaffold for GPU E2E contract v1 (default OFF).

Contract v1 (2026-10-18, user decisions):
- GPU/MJWarp physics only; this module never imports a simulator (it is CPU-side
  adapter logic, tested without physics).
- NO static map: the adapter must not read map geometry for position/driving/LLM.
  `static` may carry only order-sheet metadata (order ids, destination zone
  letters, robot count); any map access is rejected by `order_sheet()`.
- Own inputs only: own JPEG frames, own issued commands, own self-centric memory
  (relative landmarks), and the condition's delivered messages.
- Position belief is self-centric: robot at (0,0); memory landmarks move opposite
  to commanded displacement and are corrected when re-observed.
- Default OFF fails closed (wheel hold, no arrival claim). When the option is
  active, an owner-injected motion model (odometry with injected calibration)
  and a self-centric destination landmark are both present, `command()` emits a
  proportional differential wheel pulse toward the landmark every control step
  and holds the wheels once arrival evidence is recorded.  Arrival by bottom
  band additionally requires a *current* detection (<= 1 s old) whose largest
  connected component is a plausible zone patch: at least 4% of the frame tall,
  solidity >= 0.45, area <= 65% and height <= 65% of the frame, spanning the
  horizontal centre, and not touching the top edge.  A bare `bottom_norm` (for
  example scattered floor pixels) no longer produces an arrival claim.  Missing
  calibration or a missing detector stays fail-closed (wheels 0) with a
  reported reason.
- Acquisition (bounded SEARCH): when the option is active and ready but *no*
  destination landmark is remembered, the robot first turns in place instead of
  holding blindly.  The turn is a symmetric in-place pair of 35 % wheel pulses
  of 75 ms (inside the existing percent x pulse-width vocabulary); the
  direction reverses every SEARCH_LEG_STEPS steps so the heading never winds
  more than about one turn from the spawn heading, and the whole search is
  bounded by SEARCH_BUDGET_S (20 sim s) and a SEARCH_MAX_STEPS hard cap.  A
  fresh detection is acted on in the same control step, so search stops as soon
  as the destination enters the camera; if the budget expires first, the wheels
  hold with `drive_reason='search_timeout'`.  SEARCH never records arrival
  evidence and cannot bypass the arrival guard.
- `ready` is true only when the option is active AND both the own-RGB detector
  and the odometry/motion model were injected. Detector and motion model are
  deliberately absent in this scaffold; the physical gates still apply.
- **Approved gate mode v230_fwd24 (2026-10-19 user approval; default OFF).**
  The 2026-10-19 window analysis showed that the v1 band (V<=110) has no
  reproducible acquisition window and that the destination paint is brighter
  than the v1 ceiling in the frozen light_scale 0.30 scene. The approved gate
  mode keeps H 110-114 / S>=100 / min_component 600 and raises only the V
  ceiling to 230 (`gpu_calib_v230`), and replaces the blind in-place sweep with
  a bounded forward acquisition of at most 2.4 m before the existing bounded
  in-place SEARCH. The forward cap is integrated from the adapter's *own
  issued* pulses with the owner-injected percent-second calibration (no GT,
  range sensor or map); a detection appearing during the leg switches to
  following in the same control step, and once the cap is reached the wheels
  can only turn in place, never advance farther. The mode is selected only by
  `harness.e2ewarp_nav_gate` (`E2EWARP_NAV_GATE_MODE=v230_fwd24`); the
  constructor default remains `search_in_place` with no forward leg, so every
  existing v1/gate-1/r5 condition is unchanged.
- **Approved gate mode v230_r4 (2026-10-19 r4 step ②; default OFF).** Same
  claim as r3 (the 0.52 m projection along the armed *component-centre* bearing
  and the 1.0 m path fail-safe are unchanged), plus an order-sheet per-robot
  *slot* (`left` / `right`).  The slot is realised in the robot's own camera:
  the visible destination component is split into two equal halves, and the
  follower aims at the centre column of its own half (25 % / 75 % of the
  component bbox, so there is no tuned offset constant; the detector's own
  linear column->bearing mapping supplies the angle).  The aim is applied to
  the *following* bearing only: the arming bearing and therefore the claim
  direction `u` stay the component-centre bearing exactly as in r3, so the
  claim definition is untouched.  The slot is order metadata (which half of the
  destination this robot owns), never map geometry and never GT.
- **Approved gate mode v230_r5 (2026-10-20 decision; default OFF).** r4's r1
  was pushed into the divider's north jamb *before* the wide door because the
  left-half aim already steered north while the robot was still in the doorway.
  r5 therefore makes the slot **two-stage**: through the door the follower aims
  at the component **centre** (offset 0, the aim r2 passed the door with), and
  the order-sheet slot only activates once the *visible destination component's
  bottom row* projects onto the floor at **<= 1.5 m** from the base origin
  (measured camera model `GATE_GROUND_PROJECTION`, identical to
  `experiments/2026-10-19-nav-v230-r2/B_A_DERIVATION.json`).  The 1.5 m is a
  design value derived from the authored geometry (wide door at x = 2.2, zone B
  near edge at x = 4.3, i.e. 2.1 m apart, minus the chassis half-length and the
  body/clearance allowance), so the gate opens about 0.6 m past the door plane;
  it is not fitted to any r2/r3/r4 result.  After activation the applied offset
  is **clamped to +-15 deg** (about 0.29 m of lateral spread over the ~1.1 m to
  the arming row); the arming bearing and the 0.52 m projection claim are still
  the component centre, exactly as in r3/r4.  Activation is one-shot and
  fail-closed: a component without a bbox or with an unprojectable bottom row
  never activates the slot.  Both new inputs are own-camera measurements; the
  static map and GT are never read.
- **Approved gate mode v230_r3 (2026-10-19 decision ①; default OFF).** The
  r2 Step B run failed because its claim counted the *path length* of the own
  issued pulses while arrival is a *position* judgement: both robots drove
  off-axis (x progress 75 % for r1 and 50 % for r2 of the integrated path), so
  a 0.52 m path claim landed outside the zone. r3 keeps the approved 0.52 m
  geometry value and re-defines the claim in the self-odometry frame:
  ``d_proj = (p_odom(t) - p_odom(t_armed)) . u(t_armed) >= 0.52 m`` where
  ``p_odom`` is integrated from the adapter's own issued pulses and ``u`` is the
  unit vector of the own-memory bearing direction at the arming event. The world
  x axis, the static map and GT are never read. After arming the own-odometry
  yaw is held on ``u`` with the existing proportional turn controller (its input
  is the yaw error) and the same forward magnitude the r2 follower used. If the
  path driven since arming reaches 1.0 m with ``d_proj`` still below 0.52 m, the
  adapter does **not** claim: it holds the wheels and records ``NO_CLAIM``.

No ground truth, contact, evaluator, top camera, or peer raw input is accepted.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass, field

OPTION = 'e2ewarp_selfnav_v1'
ALLOWED_STATIC_KEYS = ('orders', 'goal', 'mission', 'robot_count', 'destination_zone', 'condition',
                       'slots')
#: Order-sheet slots (2026-10-19 r4 step ②).  ``left``/``right`` is the half of
#: the *visible* destination marking this robot owns, relative to the robot's
#: own camera (positive bearing = robot-left, the approved v230 convention).
#: The slot is order metadata only; it is realised from the own component bbox
#: (see ``SelfCentricNavigation._slot_detections``) and never from a map or GT.
SLOT_LEFT = 'left'
SLOT_RIGHT = 'right'
SLOTS = (SLOT_LEFT, SLOT_RIGHT)
# ---- r5 two-stage slot (2026-10-20 decision; default OFF) -------------------
# The slot aim is applied only after the destination component's bottom row
# projects onto the floor at <= 1.5 m.  Derivation (design value, not fitted to
# r2/r3/r4): the wide door plane is x = 2.2 and zone B's near paint edge is
# x = 4.3 (`zone_wide_two_doors_final_v3`), 2.1 m apart.  Subtracting the
# chassis half-length plus the body/clearance allowance leaves 1.5 m, so the
# gate opens with the base origin about x = 2.8 m, i.e. ~0.6 m past the door
# plane and clear of the jambs.  The row at 1.5 m under the measured camera
# model is 137/480 (norm 0.286) at the principal column; the row->metre
# sensitivity there is ~12 mm/px, and across the component's columns the
# distance varies ~1.5 % (1.507-1.523 m at cols 200-360), so the choice of
# column inside the bbox is not load-bearing.
SLOT_STAGE2_GROUND_M = 1.5
# The applied slot offset is clamped to +-15 deg (user-approved r5 limit).  The
# 25 %/75 % aim produced -21.0 deg at the r4 r1 arming sample, which pointed at
# the divider jamb rather than into the zone; over the ~1.1 m from activation to
# the arming row (1.5 m -> 0.365 m ground distance) 15 deg is ~0.29 m of lateral
# spread, enough to separate the pair while keeping the follower off the jamb.
SLOT_OFFSET_LIMIT_DEG = 15.0
# Existing calibrated finite-pulse vocabulary (percent x pulse width), taken from
# harness.egocentric_goto.duty (scale .35, 0.10 s).  These are command limits,
# not odometry calibration: metres/degrees per percent-second stay injected.
WHEEL_PCT = .35
PULSE_S = .10
# Controller shaping (dimensionless): bearing expressed in degrees that maps to
# a full-scale turn, the alignment gate that suppresses forward drive while the
# destination is outside the forward camera band, and the range over which
# forward drive ramps down to the arrival threshold.
BEARING_FULL_DEG = 45.0
ALIGN_GATE_DEG = 30.0
APPROACH_RANGE_M = .75
# Bounded acquisition (SEARCH) before destination following.  Gate 1 held with
# `no_destination` because the zone paint through the doorway was only ~91 px,
# below the detector's 600 px largest-component threshold: the robot must turn
# to bring the zone into view.  One leg is 80 steps x (35 % x .10 s x .75) =
# 210 percent-seconds; at the measured gate yaw calibration (1.7275 deg/pct-s,
# experiments/2026-10-18-nav-gate-1/raw/calibration.json) that is ~363 deg, i.e.
# a full turn per leg, and a 20 % calibration error still leaves >= 290 deg
# (full directional coverage with the 120 deg camera HFOV).  Reversing the
# direction every leg keeps the heading within ~one turn of the spawn heading.
# A .75 duty at the 10 Hz gate cadence is a 75 ms pulse with a 25 ms gap, so
# consecutive commands do not overlap.  20 s of search is 200 steps at 10 Hz;
# the step cap protects against a non-monotonic or faster sim clock.
SEARCH_BUDGET_S = 20.0
SEARCH_MAX_STEPS = 220
SEARCH_LEG_STEPS = 80
SEARCH_PULSE_DUTY = .75
# Acquisition modes.  `search_in_place` is the frozen v1/gate-1/r5 behaviour
# (default and constructor default).  `forward_then_search` is the 2026-10-19
# approved mode: a bounded straight +x leg of at most FORWARD_CAP_M (2.4 m)
# before the same bounded in-place SEARCH.  The cap is a user-approved control
# limit, not a calibrated constant: 2.4 m at the gate forward calibration
# (0.1408 m/s at the 35 % x 0.1 s pulse) is ~17.0 s of the 60 s budget.
ACQUISITION_SEARCH_IN_PLACE = 'search_in_place'
ACQUISITION_FORWARD_THEN_SEARCH = 'forward_then_search'
ACQUISITION_MODES = (ACQUISITION_SEARCH_IN_PLACE, ACQUISITION_FORWARD_THEN_SEARCH)
# Floating-point slack for "the 2.4 m leg is finished"; a step is clipped so
# the integrated own-command distance can never exceed the cap.
FORWARD_ACQUISITION_EPS_M = 1e-9
# Arrival evidence recorded in self-centric memory (contract v1 scaffold values).
ARRIVAL_BOTTOM_NORM = .98
ARRIVAL_RANGE_M = .25
ARRIVAL_UNCERTAINTY_M = .5
# A bottom-band arrival is a *visual* claim about the current frame, so the
# landmark must have been observed recently; without this, one false detection
# stays an arrival claim until memory decays (0.5 -> 3.0 m at 0.02 m/s is 125 s).
ARRIVAL_EVIDENCE_MAX_AGE_S = 1.0
# Plausible zone patch, in frame fractions, applied to the largest connected
# component.  These are guards against a floor fill, not a second classifier:
# they cannot separate a floor that is colour-identical to the zone paint.
ARRIVAL_MIN_HEIGHT_NORM = .04
ARRIVAL_MIN_SOLIDITY = .45
ARRIVAL_MAX_AREA_NORM = .65
ARRIVAL_MAX_HEIGHT_NORM = .65
MIN_PULSE_FRACTION = 1e-6
DESTINATION_KIND = 'zone_B'

# ---- C: acquisition quality gate (approved 2026-10-19, v230_r2 mode only) ----
# `height>=0.04` alone would reject *normal* detections: measured on the
# 2026-10-19 Step A renders (x=1.5 = 2.40 m from spawn) the zone_B component is
# height_norm 0.0333 (tick 0) / 0.0375 (tick 5), and on the recorded 45 s dev
# approach it is 0.025-0.033 at the same stop point; the first tick that
# reaches 0.04 is x=1.666 (2.56 m forward), i.e. *past* the approved 2.4 m cap
# (`C_HEIGHT_EVIDENCE.json`).  The rejected low-quality sample (r2 first
# detection, 45 s dev run) is one tick with height 0.025 / width 0.217 /
# solidity 0.344: a height threshold above 0.025 splits normal detections, so
# the pre-filter stays at 0.02 (rejects only the 0.015-0.019 far slivers) and
# the *three consecutive ticks* rule (below) is what rejects the one-tick
# sliver.  A single threshold is deliberately NOT the gate.
ACQUIRE_MIN_HEIGHT_NORM = 0.02
ACQUIRE_CONFIRM_TICKS = 3
# A target that produced no accepted detection for this long is stale and must
# be re-acquired.  This reuses the arrival guard's "current frame" bound
# (`ARRIVAL_EVIDENCE_MAX_AGE_S`) rather than inventing another constant.
ACQUIRE_MAX_AGE_S = ARRIVAL_EVIDENCE_MAX_AGE_S

# ---- B: distance-based arrival redesign (2026-10-19, default OFF) -----------
# Both candidates replace the unreachable bottom-band threshold
# (`ARRIVAL_BOTTOM_NORM=0.98`; observed maximum 0.967 = row 464/480, the
# occlusion boundary of the visible ground).  They are *distance* claims, not a
# recalibration of the bottom band, and either may be selected only through the
# explicit gate flags; the default stays `bottom_band`.
ARRIVAL_BOTTOM_BAND = 'bottom_band'
# (a) `--arrival-odom-residual`: after the near paint edge first reaches the
# bottom of the visible ground region, drive a fixed own-command residual and
# claim.  **The residual is derived from camera geometry, not from the 45 s
# diagnostic fit** (2026-10-19 decision): the ground-distance row curve of
# `GATE_GROUND_PROJECTION` puts the paint's near edge 0.3649 m ahead of the base
# origin at the contact threshold (bottom_norm 0.96, row 460.8, principal
# column), and the 0.15 m inside margin (design parameter) gives
# 0.3649 + 0.15 = 0.5149 m; frozen at 0.52 m (rounded up so rounding cannot
# shrink the margin; realized margin 0.155 m).  The recorded 45 s r1 approach is
# only a cross-check (arming at 0.963, raw base-to-near-edge 0.3842 m, within
# 0.035 m of the projection) - see experiments/2026-10-19-nav-v230-r2/
# B_A_DERIVATION.json.  The contact threshold itself is reachable: the recorded
# approach saturates at 0.967 (the chassis occlusion boundary of the visible
# ground), so 0.96 is arming 3 px earlier.
ARRIVAL_ODOM_RESIDUAL = 'odom_residual'
ARRIVAL_BOTTOM_CONTACT_NORM = 0.96
ARRIVAL_ODOM_RESIDUAL_M = 0.52
# (b) `--arrival-ground-distance-m 0.25`: project the detected patch's centre
# pixel onto the floor with the measured pinhole+fisheye camera model and claim
# when the ground distance is at most the flag value.  The camera model is the
# measured physical fisheye intrinsics (sim/masterpi_camera_profile.py) plus a
# ground-plane mount pose fitted against the frozen geometry (fit provenance in
# `GATE_GROUND_PROJECTION`).
ARRIVAL_GROUND_DISTANCE = 'ground_distance'
ARRIVAL_GROUND_DISTANCE_M = 0.25
# (r3) `--arrival-odom-projection`: the 2026-10-19 decision ① *definition fix* of
# the same approved 0.52 m geometry constant, not a re-tuned value.  The r2 run
# claimed on the integrated *path length* while arrival is a position judgement;
# both robots drove off-axis (measured x progress 75 % (r1) / 50 % (r2) of the
# path), so 0.52 m of path fell short of 0.52 m of x reach.  r3 claims on
#   d_proj = (p_odom(t) - p_odom(t_armed)) . u(t_armed) >= 0.52 m
# where p_odom is the pose integrated from the adapter's own issued wheel pulses
# with the owner-injected percent-second calibration and u is the unit vector of
# the own-memory bearing direction at the arming event, expressed in that same
# self-odometry frame.  No world x axis, static map, GT or simulator state is
# read.  Heading hold: after arming the own-odometry yaw is driven onto u by the
# existing proportional turn controller (its input is the yaw error, full scale
# BEARING_FULL_DEG) and forward stays at the full-scale magnitude the r2
# appearance-only follower used (same 35 % x pulse-width vocabulary).  Fail-safe:
# when the path driven since arming reaches ARRIVAL_PROJECTION_PATH_CAP_M (1.0 m,
# the approved value; 0.52 / 0.5 is 1.04 m and the directive's 1.0 m is the
# tighter cap) with d_proj still below the threshold, the adapter does NOT claim:
# the wheels hold and `NO_CLAIM` is recorded in the report and the nav events.
ARRIVAL_ODOM_PROJECTION = 'odom_projection'
ARRIVAL_ODOM_PROJECTION_M = ARRIVAL_ODOM_RESIDUAL_M  # 0.52 m: B_A_DERIVATION, unchanged
ARRIVAL_PROJECTION_PATH_CAP_M = 1.0
ARRIVAL_MODES = (ARRIVAL_BOTTOM_BAND, ARRIVAL_ODOM_RESIDUAL, ARRIVAL_GROUND_DISTANCE,
                 ARRIVAL_ODOM_PROJECTION)
# Ground-plane camera model used by the ground-distance arrival option.  The
# intrinsics/distortion are the *measured physical* ones already used by the
# renderer (sim/masterpi_camera_profile.py scaled to 640x480).  The mount pose
# (height above floor, pitch down, camera x offset in the base frame) is a
# ground-plane fit: 184 fresh zone_B detections of the recorded 45 s dev
# approach (r1, |heading| <= 6 deg) against the frozen map's zone B near edge,
# RMS 0.049 m, max |residual| 0.161 m.  It is a geometry audit (setup/eval-only
# pixels + authored map rectangle), never a control input, and it is NOT the
# legacy `nav_cam` profile (that camera is not the gate's `robot_cam`).
GATE_GROUND_PROJECTION = dict(
    width=640, height=480,
    fx_px=619.5194540517232, fy_px=622.1654884818748,
    cx_px=287.68910608896766, cy_px=218.69686648455726,
    fisheye_d=(-0.0199819517209417, -0.1707593617153504,
               -0.2568318201202376, 0.9650933421665181),
    camera_height_m=0.29983, pitch_down_deg=18.9934, camera_x_offset_m=0.0255,
    source='sim/masterpi_camera_profile.py intrinsics + ground-plane mount fit '
           '(184 fresh detections, RMS 0.049 m)',
)


def order_sheet(static):
    """Return only authored order-sheet metadata; reject map geometry access."""
    if static is None:
        return {}
    if not isinstance(static, dict):
        raise TypeError('static must be a mapping or None')
    unknown = [k for k in static if k not in ALLOWED_STATIC_KEYS]
    if unknown:
        # Contract v1: the runner must not pass map geometry to this adapter.
        raise ValueError('static map input is forbidden by contract v1: ' + ','.join(sorted(unknown)))
    return {k: copy.deepcopy(static[k]) for k in ALLOWED_STATIC_KEYS if k in static}


def wrap_deg(angle):
    """Wrap an angle in degrees to (-180, 180]."""
    return (float(angle) + 180.0) % 360.0 - 180.0


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def record_robot_id(record):
    """Read an ownership tag from a mapping row or an OwnFrame object."""
    rid = record.get('robot_id') if isinstance(record, Mapping) else getattr(record, 'robot_id', None)
    return None if rid is None else str(rid)


@dataclass
class Landmark:
    kind: str
    range_m: float
    bearing_deg: float
    last_seen_s: float
    uncertainty_m: float = 0.5
    bottom_norm: float = 0.0
    width_norm: float = 0.0
    pixels: int = 0
    # Geometry of the detector's largest connected component, used only by the
    # arrival guard.  Defaults fail closed (height 0, solidity 0): a detection
    # that does not attest its patch geometry can never claim arrival.
    height_norm: float = 0.0
    area_norm: float = 0.0
    solidity: float = 0.0
    spans_center_x: bool = False
    touches_top: bool = False
    # Largest-component pixel box (left, top, right, bottom) as reported by the
    # detector; used only by the ground-distance arrival option, which projects
    # the patch's centre pixel onto the floor.  ``None`` fails closed.
    bbox: tuple | None = None
    # r4 slot aim: rotation-invariant offset (degrees) from the component-centre
    # bearing to the centre of this robot's half of the visible marking.  It is
    # applied to the *following* bearing only; the arming bearing and the claim
    # direction stay the component-centre bearing (r3 definition unchanged).
    slot_bearing_offset_deg: float = 0.0
    # Appearance-only detectors (e.g. GpuCalibZoneDetector) report no metric
    # range.  A default 0.0 must never be read as "arrived at 0 m".
    range_measured: bool = True
    # Uncertainty at ``last_seen_s``.  ``decay()`` re-derives the age term from
    # this anchor on every call; the old code added it to the running value, so
    # a 10 Hz loop added rate*sum(now_k - last_seen) instead of
    # rate*(now - last_seen) and grew quadratically (measured 0.5 -> 2.57 m in
    # 4.5 s where the intended growth is 0.59 m).  A fresh detection sets
    # ``last_seen_s`` and this base together (a re-observation is a new
    # Landmark; ``__post_init__`` keeps the base equal to the initial
    # measurement uncertainty when one is supplied explicitly).
    base_uncertainty_m: float | None = None

    def __post_init__(self):
        if self.base_uncertainty_m is None:
            self.base_uncertainty_m = float(self.uncertainty_m)

    def decay(self, now_s, *, rate_m_per_s=0.02, max_m=3.0):
        """Uncertainty = min(max_m, base + rate * (now - last_seen))."""
        age_s = max(0.0, float(now_s) - self.last_seen_s)
        self.uncertainty_m = min(max_m, self.base_uncertainty_m + rate_m_per_s * age_s)


@dataclass
class SelfCentricMemory:
    """Short self-centric landmark list; robot-relative, never global coordinates."""
    items: list = field(default_factory=list)

    def observe(self, now_s, detections):
        """Update from own-RGB detections: [{kind, range_m, bearing_deg}]."""
        kept = []
        for item in self.items:
            item.decay(now_s)
            if item.uncertainty_m < 3.0:
                kept.append(item)
        for det in detections or ():
            measured = 'range_m' in det and det.get('range_m') is not None
            # Re-observation: this Landmark writes last_seen_s and the decay base
            # together, so the decay clock restarts from this measurement.
            kept.append(Landmark(str(det['kind']), float(det.get('range_m') or 0.0), float(det['bearing_deg']),
                                 float(now_s), bottom_norm=float(det.get('bottom_norm', 0.0)),
                                 width_norm=float(det.get('width_norm', 0.0)), pixels=int(det.get('pixels', 0)),
                                 height_norm=float(det.get('height_norm', 0.0)),
                                 area_norm=float(det.get('area_norm', 0.0)),
                                 solidity=float(det.get('solidity', 0.0)),
                                 spans_center_x=bool(det.get('spans_center_x', False)),
                                 touches_top=bool(det.get('touches_top', False)),
                                 bbox=(tuple(int(v) for v in det['bbox'])
                                       if det.get('bbox') is not None else None),
                                 slot_bearing_offset_deg=float(det.get('slot_bearing_offset_deg') or 0.0),
                                 range_measured=measured))
        self.items = kept[-16:]

    def transform(self, forward_m, yaw_deg):
        """Robot moved forward/yawed; shift remembered relative geometry opposite to motion."""
        for item in self.items:
            b = math.radians(item.bearing_deg - yaw_deg)
            r = max(0.0, item.range_m - forward_m * math.cos(b))
            item.range_m = r
            item.bearing_deg = math.degrees(math.atan2(math.sin(b), math.cos(b)))

    def nearest(self, kind):
        hits = [i for i in self.items if i.kind == kind]
        return min(hits, key=lambda i: (i.range_m, i.uncertainty_m)) if hits else None

    def as_report(self):
        return [dict(kind=i.kind, range_m=round(i.range_m, 3), bearing_deg=round(i.bearing_deg, 2),
                     last_seen_s=round(i.last_seen_s, 3), uncertainty_m=round(i.uncertainty_m, 3),
                     bottom_norm=round(i.bottom_norm, 3), width_norm=round(i.width_norm, 3),
                     height_norm=round(i.height_norm, 3), solidity=round(i.solidity, 3),
                     bbox=(None if i.bbox is None else [int(v) for v in i.bbox]),
                     slot_bearing_offset_deg=round(float(i.slot_bearing_offset_deg), 3),
                     range_measured=bool(i.range_measured))
                for i in self.items]


class SelfCentricNavigation:
    """navigation_factory ABI: observe/task_candidates/start/command/confirm_act/on_messages/accept_release_fix."""

    def __init__(self, robot_id, static=None, *, option='off', detector=None, odometry=None,
                 destination_kind=None, arrival_range_m=ARRIVAL_RANGE_M,
                 acquisition_mode=ACQUISITION_SEARCH_IN_PLACE, forward_cap_m=0.0,
                 acquire_min_height_norm=0.0, acquire_confirm_ticks=1,
                 forward_reacquire=False, arrival_mode=ARRIVAL_BOTTOM_BAND,
                 arrival_odom_residual_m=ARRIVAL_ODOM_RESIDUAL_M,
                 arrival_ground_distance_m=None,
                 arrival_projection_m=ARRIVAL_ODOM_PROJECTION_M,
                 arrival_projection_path_cap_m=ARRIVAL_PROJECTION_PATH_CAP_M,
                 arrival_bottom_contact_norm=ARRIVAL_BOTTOM_CONTACT_NORM,
                 ground_projection=None, slot=None, slot_stage2_ground_m=None):
        if robot_id not in ('r1', 'r2'):
            raise ValueError('contract v1 navigation is two-robot only (r1/r2)')
        if acquisition_mode not in ACQUISITION_MODES:
            raise ValueError('unknown acquisition mode: ' + str(acquisition_mode))
        forward_cap_m = float(forward_cap_m)
        if acquisition_mode == ACQUISITION_FORWARD_THEN_SEARCH:
            if not forward_cap_m > 0.0:
                raise ValueError('forward acquisition requires a positive forward cap')
        elif forward_cap_m != 0.0:
            raise ValueError('forward cap is only valid with forward acquisition')
        # C: acquisition quality gate (v230_r2 only; the constructor defaults
        # disable it, so every existing v1/gate-1/r5 condition is unchanged).
        acquire_min_height_norm = float(acquire_min_height_norm)
        if not 0.0 <= acquire_min_height_norm <= 1.0:
            raise ValueError('acquire_min_height_norm must be in [0, 1]')
        if isinstance(acquire_confirm_ticks, bool) or int(acquire_confirm_ticks) != acquire_confirm_ticks:
            raise ValueError('acquire_confirm_ticks must be an integer')
        acquire_confirm_ticks = int(acquire_confirm_ticks)
        if acquire_confirm_ticks < 1:
            raise ValueError('acquire_confirm_ticks must be >= 1')
        # B: distance-based arrival (default OFF -> the frozen bottom band).
        if arrival_mode not in ARRIVAL_MODES:
            raise ValueError('unknown arrival mode: ' + str(arrival_mode))
        arrival_odom_residual_m = float(arrival_odom_residual_m)
        if arrival_mode == ARRIVAL_ODOM_RESIDUAL:
            if not arrival_odom_residual_m > 0.0:
                raise ValueError('odometry-residual arrival requires a positive residual')
            if acquisition_mode != ACQUISITION_FORWARD_THEN_SEARCH:
                raise ValueError('odometry-residual arrival is an acquisition-mode option')
        if arrival_mode == ARRIVAL_GROUND_DISTANCE:
            if arrival_ground_distance_m is None:
                raise ValueError('ground-distance arrival requires the distance threshold')
            arrival_ground_distance_m = float(arrival_ground_distance_m)
            if not arrival_ground_distance_m > 0.0:
                raise ValueError('ground-distance arrival threshold must be positive')
            if acquisition_mode != ACQUISITION_FORWARD_THEN_SEARCH:
                raise ValueError('ground-distance arrival is an acquisition-mode option')
        else:
            arrival_ground_distance_m = (None if arrival_ground_distance_m is None
                                         else float(arrival_ground_distance_m))
        # B(r3): projection claim (definition fix of the same 0.52 m geometry).
        arrival_projection_m = float(arrival_projection_m)
        arrival_projection_path_cap_m = float(arrival_projection_path_cap_m)
        if arrival_mode == ARRIVAL_ODOM_PROJECTION:
            if not arrival_projection_m > 0.0:
                raise ValueError('odometry-projection arrival requires a positive threshold')
            if not arrival_projection_path_cap_m > 0.0:
                raise ValueError('odometry-projection arrival requires a positive path cap')
            if acquisition_mode != ACQUISITION_FORWARD_THEN_SEARCH:
                raise ValueError('odometry-projection arrival is an acquisition-mode option')
        arrival_bottom_contact_norm = float(arrival_bottom_contact_norm)
        if not 0.0 < arrival_bottom_contact_norm <= 1.0:
            raise ValueError('arrival bottom-contact threshold must be in (0, 1]')
        self.robot_id = robot_id
        self.option = option
        self.acquisition_mode = acquisition_mode
        self.forward_cap_m = forward_cap_m
        sheet = order_sheet(static)
        self.orders = sheet.get('orders') or []
        zone = sheet.get('destination_zone')
        if zone is None and isinstance(sheet.get('mission'), Mapping):
            zone = sheet['mission'].get('destination_zone')
        if destination_kind is None and isinstance(zone, str) and zone:
            destination_kind = zone if zone.startswith('zone_') else f'zone_{zone}'
        self.destination_kind = str(destination_kind) if destination_kind is not None else DESTINATION_KIND
        # r4 step ②: the order sheet may name this robot's slot (left/right).
        # It is read only as order metadata; the aim is computed from the own
        # camera component (no map/GT).  An explicit argument wins, so a caller
        # can bind it without the sheet; both fail closed on an unknown value.
        if slot is None:
            slot = (sheet.get('slots') or {}).get(robot_id)
        if slot is not None:
            slot = str(slot)
            if slot not in SLOTS:
                raise ValueError('unknown destination slot: ' + slot)
        self.slot = slot
        # r5 two-stage slot (2026-10-20, default OFF): the constructor default
        # ``None`` keeps the r4 behaviour byte-identical (the slot offset is
        # applied from the first follow tick).  A positive threshold delays it
        # until the own-camera component bottom row projects at <= that distance.
        if slot_stage2_ground_m is not None:
            slot_stage2_ground_m = float(slot_stage2_ground_m)
            if not slot_stage2_ground_m > 0.0:
                raise ValueError('slot stage-2 ground threshold must be positive')
            if slot is None:
                raise ValueError('slot stage 2 requires a destination slot')
            if arrival_mode != ARRIVAL_ODOM_PROJECTION:
                raise ValueError('slot stage 2 requires the odom_projection arrival claim')
        self.slot_stage2_ground_m = slot_stage2_ground_m
        self.arrival_range_m = float(arrival_range_m)
        if self.arrival_range_m < 0.0:
            raise ValueError('arrival range threshold must be nonnegative')
        self.detector = detector            # own-RGB landmark detector (owner injected)
        self.odometry = odometry            # own-command odometry (owner injected calibration)
        self.memory = SelfCentricMemory()
        self.phase = 'TASK'
        self.instruction = None
        self._last_frame = None
        self._revision = 0
        self._messages = []
        self._issued = []
        self._drive_reason = 'idle'
        # Bounded SEARCH state: the timer starts on the first issued search
        # pulse, not on the first report, so a delayed command cannot exhaust
        # the budget before the robot actually moves.
        self._search_started_s = None
        self._search_steps = 0
        # Bounded forward-acquisition state (own issued commands only).  The
        # distance is accumulated when a forward pulse is issued; the plan is
        # pure and only reads it.  The forward leg is one-shot: once the
        # destination has ever been seen, a later memory loss falls back to the
        # bounded in-place SEARCH, so the 2.4 m can never become a second blind
        # leg after following.
        self._forward_used_m = 0.0
        self._forward_steps = 0
        self._destination_seen = False
        # C: acquisition-quality state.  ``_acquire_streak`` counts consecutive
        # accepted detections; ``_target_confirmed`` latches once the streak
        # reaches ``acquire_confirm_ticks`` and drops only when the target goes
        # stale (no accepted detection for ACQUIRE_MAX_AGE_S), so a single
        # dropped tick cannot restart confirmation or cancel following.
        self.acquire_min_height_norm = acquire_min_height_norm
        self.acquire_confirm_ticks = acquire_confirm_ticks
        self.forward_reacquire = bool(forward_reacquire)
        self._acquire_streak = 0
        self._target_confirmed = False
        self._last_accepted_s = None
        # B: distance-based arrival state.  ``_arrival_armed`` latches when the
        # near paint edge first reaches the bottom of the visible ground region;
        # ``_arrival_travel_m`` is the own-command distance driven since then.
        self.arrival_mode = arrival_mode
        self.arrival_odom_residual_m = arrival_odom_residual_m
        self.arrival_ground_distance_m = arrival_ground_distance_m
        self.arrival_projection_m = arrival_projection_m
        self.arrival_projection_path_cap_m = arrival_projection_path_cap_m
        self.arrival_bottom_contact_norm = arrival_bottom_contact_norm
        self.ground_projection = (dict(ground_projection) if ground_projection is not None
                                  else dict(GATE_GROUND_PROJECTION))
        self._arrival_armed = False
        self._arrival_travel_m = 0.0
        self._ground_distance_m = None
        # B(r3) projection-claim state: the own-odometry pose (self frame, origin
        # at the first issued command), the pose and bearing unit vector latched
        # at the arming event, the integrated path since arming and the signed
        # projection of the displacement onto that unit vector.
        self._odom_x_m = 0.0
        self._odom_y_m = 0.0
        self._odom_yaw_deg = 0.0
        self._arrival_origin_x_m = 0.0
        self._arrival_origin_y_m = 0.0
        self._arrival_u_deg = 0.0
        self._arrival_arming_bearing_deg = 0.0
        self._arrival_path_m = 0.0
        self._arrival_proj_m = 0.0
        self._arrival_no_claim = False
        # r5 two-stage slot state.  ``_slot_stage2_active`` latches once the own
        # camera component bottom row projects at <= slot_stage2_ground_m; the
        # applied offset stays 0 before that (component-centre aim through the
        # door) and is clamped to +-SLOT_OFFSET_LIMIT_DEG after it.  All three
        # diagnostics are recorded, never fed back into the gate.
        self._slot_stage2_active = False
        self._slot_stage2_sim_s = None
        self._slot_ground_m = None
        self._slot_ground_at_activation_m = None
        self._slot_offset_raw_deg = None
        self._slot_offset_applied_deg = None

    @property
    def ready(self):
        """True only with the option active and both own-input components injected."""
        return self.option == OPTION and self.detector is not None and self.odometry is not None

    def _check_owner(self, record, *, required):
        """Own-frame ownership: never accept another robot's record."""
        rid = record_robot_id(record)
        if rid is None:
            if required:
                raise ValueError('own frame must carry robot_id')
            return
        if rid != self.robot_id:
            raise ValueError(f'foreign robot_id={rid} for navigator {self.robot_id}')

    # --- own observation -------------------------------------------------
    def observe(self, frame):
        self._check_owner(frame, required=True)
        self._last_frame = frame
        if self.option != OPTION:
            return self._report(active=False, now_s=frame.sim_s)
        detections = self.detector(frame) if self.detector else ()
        if self.slot is not None:
            detections = self._slot_detections(detections)
        accepted = self._accepted_hit(detections)
        # r5: the stage-2 activation is evaluated on the same accepted component
        # the follower targets, from the current own frame only.  A missing bbox
        # or an unprojectable row leaves the gate closed (fail closed).  The
        # measured (raw) half aim is recorded here every tick so the diagnostic
        # shows what the slot asked for even while the claim heading-hold drives.
        if self.slot is not None and accepted is not None:
            self._slot_offset_raw_deg = float(accepted.get('slot_bearing_offset_deg') or 0.0)
        if self.slot_stage2_ground_m is not None and accepted is not None:
            self._slot_ground_m = self._slot_ground_distance(accepted)
            if (not self._slot_stage2_active and self._slot_ground_m is not None
                    and self._slot_ground_m <= self.slot_stage2_ground_m):
                self._slot_stage2_active = True
                self._slot_stage2_sim_s = float(frame.sim_s)
                self._slot_ground_at_activation_m = self._slot_ground_m
        self.memory.observe(frame.sim_s, detections)
        if self.memory.nearest(self.destination_kind) is not None:
            self._destination_seen = True
        # C: consecutive accepted detections gate the switch to following.  The
        # latch drops only when the target goes stale (ACQUIRE_MAX_AGE_S), so a
        # single dropped tick does not restart the confirmation.
        if accepted is not None:
            self._acquire_streak += 1
            self._last_accepted_s = frame.sim_s
            if self._acquire_streak >= self.acquire_confirm_ticks:
                self._target_confirmed = True
        else:
            self._acquire_streak = 0
        if self._target_confirmed and self._last_accepted_s is not None \
                and frame.sim_s - self._last_accepted_s > ACQUIRE_MAX_AGE_S:
            self._target_confirmed = False
            self._acquire_streak = 0
        # B(a)/B(r3): latch the bottom-contact event once, on an *accepted*
        # detection.  r3 additionally fixes the claim direction to the own-memory
        # bearing seen at that instant (self-odometry frame).
        if (self.arrival_mode in (ARRIVAL_ODOM_RESIDUAL, ARRIVAL_ODOM_PROJECTION)
                and accepted is not None
                and not self._arrival_armed
                and float(accepted.get('bottom_norm') or 0.0) >= self.arrival_bottom_contact_norm):
            self._arrival_armed = True
            if self.arrival_mode == ARRIVAL_ODOM_PROJECTION:
                self._arrival_arming_bearing_deg = wrap_deg(float(accepted.get('bearing_deg') or 0.0))
                # Own-memory bearing (robot-relative, positive left) expressed in
                # the own-odometry frame: the direction the claim projects onto.
                self._arrival_u_deg = wrap_deg(self._odom_yaw_deg + self._arrival_arming_bearing_deg)
                self._arrival_origin_x_m = self._odom_x_m
                self._arrival_origin_y_m = self._odom_y_m
                self._arrival_path_m = 0.0
                self._arrival_proj_m = 0.0
        self._revision += 1
        return self._report(active=True, now_s=frame.sim_s)

    # --- C: acquisition quality ------------------------------------------
    def _slot_detections(self, detections):
        """Add the r4 slot aim offset to the own-camera destination detections.

        The visible destination marking is split into two equal halves; the
        robot aims at the centre column of its own half.  With the detector's
        linear column->bearing mapping, that column's bearing is the midpoint of
        the component-centre bearing and the bbox edge bearing, so the offset is
        ``aim - centre`` and no new angle constant is introduced.  The offset is
        stored on the detection (and therefore on the remembered landmark) for
        the *following* bearing only: ``bearing_deg`` itself is untouched, so the
        arming bearing and the r3 claim direction stay the component centre.

        A destination detection that cannot attest both bbox edge bearings fails
        closed (a slot must never silently fall back to the centre aim).
        """
        adjusted = []
        for det in detections or ():
            if str(det.get('kind')) != self.destination_kind:
                adjusted.append(det)
                continue
            left = det.get('bearing_at_left_edge_deg')
            right = det.get('bearing_at_right_edge_deg')
            if left is None or right is None:
                raise ValueError('slot aim requires measured component edge bearings')
            center = float(det.get('bearing_deg') or 0.0)
            edge = float(left) if self.slot == SLOT_LEFT else float(right)
            value = dict(det)
            value['slot_bearing_offset_deg'] = wrap_deg(0.5 * (float(edge) + center) - center)
            value['slot'] = self.slot
            adjusted.append(value)
        return adjusted

    def _slot_ground_distance(self, detection):
        """Ground distance (m) of the own component's bottom row, or ``None``.

        r5 stage-2 gate: the pixel is the centre column of the component bbox and
        its **bottom row** (``bottom - 1``: the detector reports an exclusive
        bottom edge, so this is the last included row, i.e. the nearest visible
        ground of the marking).  The projection is the same measured
        pinhole+fisheye ground-plane model the ground-distance arrival option
        uses (`GATE_GROUND_PROJECTION`, the B_A_DERIVATION camera).  A missing
        bbox or a row that does not hit the floor returns ``None`` (fail closed:
        the slot stays inactive rather than falling back to a guessed distance).
        """
        bbox = detection.get('bbox')
        if bbox is None:
            return None
        left, _top, right, bottom = (int(v) for v in bbox)
        return ground_distance_m((left + right - 1) / 2.0, bottom - 1, self.ground_projection)

    def _accepted_hit(self, detections):
        """Largest destination component that passes the C height pre-filter.

        Returns ``None`` when nothing passes.  With the constructor default
        (``acquire_min_height_norm=0``) every destination hit is accepted, so
        the frozen v1/gate-1/r5 behaviour is unchanged.
        """
        best = None
        for det in detections or ():
            if str(det.get('kind')) != self.destination_kind:
                continue
            if float(det.get('height_norm') or 0.0) < self.acquire_min_height_norm:
                continue
            if best is None or float(det.get('height_norm') or 0.0) > float(best.get('height_norm') or 0.0):
                best = det
        return best

    def _confirmed(self):
        """True when following is allowed (C disabled -> any target is allowed)."""
        if self.acquire_confirm_ticks <= 1 and self.acquire_min_height_norm <= 0.0:
            return True
        return bool(self._target_confirmed)

    def _target_usable(self, now_s):
        """True when a current, confirmed destination may be followed."""
        landmark = self.memory.nearest(self.destination_kind)
        if landmark is None:
            return False
        if not self._confirmed():
            return False
        if self.acquire_confirm_ticks <= 1 and self.acquire_min_height_norm <= 0.0:
            return True
        if self._last_accepted_s is None:
            return False
        return now_s - self._last_accepted_s <= ACQUIRE_MAX_AGE_S

    def _arrival_evidence(self, landmark, now_s):
        """Current own-memory arrival claim (bottom band by default).

        The bottom-band path is a visual claim, so it must be fresh and its
        component must look like a paint patch rather than a floor fill.  A
        stale claim is not evidence: memory keeps landmarks for driving, but it
        must not keep an arrival claim after the patch left the camera.

        Two *distance* modes replace that unreachable band (2026-10-19 approval,
        default OFF; selected only through the explicit gate flags):
        (a) ``odom_residual`` - the near paint edge reaching the bottom of the
        visible ground latches an arming event, then the robot claims after a
        fixed own-command residual (no band threshold is re-tuned);
        (b) ``ground_distance`` - the current patch centre is projected onto the
        floor with the camera model and compared with a metric threshold;
        (c) ``odom_projection`` - the r3 definition fix: after the same arming
        event, claim only when the own-odometry displacement projected onto the
        armed bearing direction reaches the frozen threshold.  The claim is
        purely odometric, so it does not need a remembered landmark.
        """
        if self.arrival_mode == ARRIVAL_ODOM_PROJECTION:
            return bool(self._arrival_armed
                        and not self._arrival_no_claim
                        and self._arrival_proj_m >= self.arrival_projection_m)
        if landmark is None:
            return False
        if self.arrival_mode == ARRIVAL_ODOM_RESIDUAL:
            # A distance claim latched at the visual contact: the residual is
            # integrated from own issued commands, no current frame is needed.
            return bool(self._arrival_armed
                        and self._arrival_travel_m >= self.arrival_odom_residual_m)
        if self.arrival_mode == ARRIVAL_GROUND_DISTANCE:
            if now_s - landmark.last_seen_s > ARRIVAL_EVIDENCE_MAX_AGE_S:
                return False
            if not self._confirmed():
                return False
            if self.arrival_ground_distance_m is None or landmark.bbox is None:
                self._ground_distance_m = None
                return False
            left, top, right, bottom = landmark.bbox
            distance = ground_distance_m((left + right - 1) / 2.0,
                                         (top + bottom) / 2.0, self.ground_projection)
            self._ground_distance_m = distance
            return bool(distance is not None
                        and distance <= self.arrival_ground_distance_m)
        if now_s - landmark.last_seen_s > ARRIVAL_EVIDENCE_MAX_AGE_S:
            return False
        if not self._confirmed():
            return False
        if (landmark.bottom_norm >= ARRIVAL_BOTTOM_NORM
                and landmark.height_norm >= ARRIVAL_MIN_HEIGHT_NORM
                and landmark.height_norm <= ARRIVAL_MAX_HEIGHT_NORM
                and landmark.area_norm <= ARRIVAL_MAX_AREA_NORM
                and landmark.solidity >= ARRIVAL_MIN_SOLIDITY
                and landmark.spans_center_x
                and not landmark.touches_top):
            return True
        return (landmark.range_measured
                and landmark.range_m <= self.arrival_range_m
                and landmark.uncertainty_m <= ARRIVAL_UNCERTAINTY_M)

    def _search_elapsed_s(self, now_s):
        """Own-clock time spent searching; 0 until the first search pulse."""
        if self._search_started_s is None:
            return 0.0
        return max(0.0, float(now_s) - self._search_started_s)

    def _search_turn(self):
        """Symmetric in-place turn sign for the current leg (±1): alternates."""
        leg = self._search_steps // SEARCH_LEG_STEPS
        return 1.0 if leg % 2 == 0 else -1.0

    def _search_reason(self, now_s):
        """`searching` while the bounded budget lasts, then `search_timeout`."""
        if (self._search_elapsed_s(now_s) >= SEARCH_BUDGET_S
                or self._search_steps >= SEARCH_MAX_STEPS):
            return 'search_timeout'
        return 'searching'

    def _forward_remaining_m(self):
        """Own-command odometry distance left in the approved forward-acquisition cap."""
        return max(0.0, self.forward_cap_m - self._forward_used_m)

    def _forward_acquisition_active(self, now_s=None):
        """True while the bounded forward leg may still advance the robot.

        Frozen ``v230_fwd24`` behaviour is one-shot: once the destination has
        ever been seen, a later loss falls back to the bounded in-place SEARCH.
        The approved ``v230_r2`` mode adds ``forward_reacquire`` (C): when the
        target is lost/stale again the same 2.4 m cap may be used to re-advance,
        because the cap is the approved *geometric* bound of the acquisition
        leg and re-driving into a lost target is what the 45 s dev run showed
        is needed.  The cap itself is never exceeded.
        """
        if self.acquisition_mode != ACQUISITION_FORWARD_THEN_SEARCH:
            return False
        if self._forward_remaining_m() <= FORWARD_ACQUISITION_EPS_M:
            return False
        if now_s is None:
            now_s = self._last_frame.sim_s if self._last_frame is not None else 0.0
        if self._target_usable(now_s):
            return False
        if self._destination_seen and not self.forward_reacquire:
            return False
        return True

    def _drive_plan(self, now_s=None):
        """Own-memory control plan; no plan means the wheel hold is returned."""
        if now_s is None:  # test/introspection default: the last own frame's time
            now_s = self._last_frame.sim_s if self._last_frame is not None else 0.0
        landmark = self.memory.nearest(self.destination_kind)
        if self.option != OPTION:
            return dict(reason='option_off', landmark=landmark, forward=0.0, turn=0.0)
        if self.odometry is None:
            return dict(reason='no_odometry', landmark=landmark, forward=0.0, turn=0.0)
        # A distance-based arrival claim can outlive the visual target (B(a)
        # latches at the contact event), so it is evaluated before the
        # acquisition branch.  With the frozen bottom band this is exactly the
        # old order: the claim still needs a remembered landmark (r3's odometric
        # projection claim is the one mode that does not).
        if self._arrival_evidence(landmark, now_s):
            return dict(reason='arrived', landmark=landmark, forward=0.0, turn=0.0)
        if self.arrival_mode == ARRIVAL_ODOM_PROJECTION and self._arrival_armed:
            # r3 heading hold: drive on the armed bearing direction using the
            # existing proportional turn controller with the own-odometry yaw
            # error as its input.  Forward keeps the r2 follower's full-scale
            # magnitude (same pulse vocabulary).  The fail-safe holds the wheels
            # once the path cap is spent without a claim.
            if self._arrival_no_claim:
                return dict(reason='no_claim', landmark=landmark, forward=0.0, turn=0.0)
            error = wrap_deg(self._arrival_u_deg - self._odom_yaw_deg)
            turn = clamp(error / BEARING_FULL_DEG, -1.0, 1.0)
            forward = 1.0
            left = clamp(forward - turn, -1.0, 1.0)
            right = clamp(forward + turn, -1.0, 1.0)
            return dict(reason='driving_hold_heading', landmark=landmark,
                        forward=(left + right) / 2.0, turn=(right - left) / 2.0)
        if landmark is None or not self._target_usable(now_s):
            # No usable destination: acquire it with a bounded forward leg
            # (approved mode only), then the bounded in-place sweep.  Fail
            # closed when the detector was not injected (nothing could ever be
            # acquired) or when both budgets are exhausted.  With C enabled a
            # remembered but unconfirmed/stale target is *not* usable, so the
            # robot re-advances within the same 2.4 m cap instead of following
            # a memory that no longer matches the camera.
            if not self.ready:
                return dict(reason='no_destination', landmark=None, forward=0.0, turn=0.0)
            if self._forward_acquisition_active(now_s):
                return dict(reason='acquiring_forward', landmark=None, forward=1.0, turn=0.0)
            reason = self._search_reason(now_s)
            if reason == 'search_timeout':
                return dict(reason=reason, landmark=None, forward=0.0, turn=0.0)
            return dict(reason=reason, landmark=None, forward=0.0, turn=self._search_turn())
        # r5 two-stage slot: before the ground-distance activation the follower
        # aims at the component centre exactly as r2 did through the door; after
        # it the order-sheet half aim is applied, clamped to the approved +-15
        # deg.  The r4 path (slot_stage2_ground_m is None) applies the measured
        # offset unchanged, so an r4 run stays byte-identical.
        offset = float(landmark.slot_bearing_offset_deg)
        if self.slot_stage2_ground_m is not None:
            if self._slot_stage2_active:
                offset = clamp(offset, -SLOT_OFFSET_LIMIT_DEG, SLOT_OFFSET_LIMIT_DEG)
            else:
                offset = 0.0
        self._slot_offset_applied_deg = offset
        bearing = wrap_deg(landmark.bearing_deg + offset)
        turn = clamp(bearing / BEARING_FULL_DEG, -1.0, 1.0)
        if abs(bearing) > ALIGN_GATE_DEG:
            forward = 0.0  # rotate toward the destination before translating
        elif landmark.range_measured:
            forward = clamp((landmark.range_m - self.arrival_range_m) / APPROACH_RANGE_M, 0.0, 1.0)
        else:
            forward = 1.0  # appearance-only detector: cruise until the near band
        left = clamp(forward - turn, -1.0, 1.0)
        right = clamp(forward + turn, -1.0, 1.0)
        if abs(left) < MIN_PULSE_FRACTION and abs(right) < MIN_PULSE_FRACTION:
            return dict(reason='no_drive', landmark=landmark, forward=0.0, turn=0.0)
        # Differential (f, l=0, t) decodes to (left, right, left, right); the
        # plan keeps the clamped wheel values by round-tripping through them.
        return dict(reason='driving', landmark=landmark,
                    forward=(left + right) / 2.0, turn=(right - left) / 2.0)

    def _report(self, *, active, now_s):
        holding = 'unknown'
        returned = self.memory.nearest('return')
        plan = self._drive_plan(now_s)
        zone = plan['landmark']
        arrived = bool(active and self._arrival_evidence(zone, now_s))
        handoff = bool(self.phase == 'APPROACH' and self.memory.nearest('cargo') is not None
                       and self.memory.nearest('cargo').range_m <= 0.6)
        return dict(robot_id=self.robot_id, phase=self.phase, position_xy=(0.0, 0.0),
                    map_correction_active=bool(active), self_centric_memory=self.memory.as_report(),
                    holding_status=holding, destination_arrived=arrived, handoff_ready=handoff,
                    evidence_revision=self._revision, return_landmark=bool(returned),
                    ready=self.ready, drive_reason=plan['reason'],
                    destination_landmark=(None if zone is None else zone.kind),
                    search_elapsed_s=round(self._search_elapsed_s(now_s), 3),
                    search_steps=int(self._search_steps),
                    acquisition_mode=self.acquisition_mode,
                    forward_cap_m=round(self.forward_cap_m, 6),
                    forward_used_m=round(self._forward_used_m, 6),
                    forward_steps=int(self._forward_steps),
                    acquire_min_height_norm=round(self.acquire_min_height_norm, 6),
                    acquire_confirm_ticks=int(self.acquire_confirm_ticks),
                    acquire_streak=int(self._acquire_streak),
                    target_confirmed=bool(self._target_confirmed),
                    forward_reacquire=bool(self.forward_reacquire),
                    arrival_mode=self.arrival_mode,
                    slot=self.slot,
                    slot_stage2_ground_m=(None if self.slot_stage2_ground_m is None
                                          else round(self.slot_stage2_ground_m, 6)),
                    slot_stage2_active=bool(self._slot_stage2_active),
                    slot_stage2_sim_s=(None if self._slot_stage2_sim_s is None
                                       else round(self._slot_stage2_sim_s, 3)),
                    slot_ground_distance_m=(None if self._slot_ground_m is None
                                            else round(self._slot_ground_m, 6)),
                    slot_ground_at_activation_m=(None if self._slot_ground_at_activation_m is None
                                                 else round(self._slot_ground_at_activation_m, 6)),
                    slot_bearing_offset_raw_deg=(None if self._slot_offset_raw_deg is None
                                                 else round(self._slot_offset_raw_deg, 3)),
                    slot_bearing_offset_applied_deg=(None if self._slot_offset_applied_deg is None
                                                     else round(self._slot_offset_applied_deg, 3)),
                    slot_offset_limit_deg=round(SLOT_OFFSET_LIMIT_DEG, 3),
                    arrival_armed=bool(self._arrival_armed),
                    arrival_travel_m=round(self._arrival_travel_m, 6),
                    arrival_projection_m=round(self._arrival_proj_m, 6),
                    arrival_projection_threshold_m=round(self.arrival_projection_m, 6),
                    arrival_path_m=round(self._arrival_path_m, 6),
                    arrival_path_cap_m=round(self.arrival_projection_path_cap_m, 6),
                    arrival_u_deg=(round(self._arrival_u_deg, 3) if self._arrival_armed else None),
                    arrival_bearing_armed_deg=(round(self._arrival_arming_bearing_deg, 3)
                                               if self._arrival_armed else None),
                    arrival_heading_error_deg=(round(wrap_deg(self._arrival_u_deg
                                                              - self._odom_yaw_deg), 3)
                                               if self._arrival_armed else None),
                    arrival_no_claim=bool(self._arrival_no_claim),
                    odom_pose=(round(self._odom_x_m, 6), round(self._odom_y_m, 6),
                               round(self._odom_yaw_deg, 3)),
                    arrival_ground_distance_m=(None if self._ground_distance_m is None
                                               else round(self._ground_distance_m, 6)))

    # --- task/order sheet -------------------------------------------------
    def task_candidates(self, completed):
        done = set(completed or ())
        return [dict(id=str(o.get('id', f'order_{i}')), skill='carry_pair', order=o,
                     expected_cost='two-robot carry; own camera only') for i, o in enumerate(self.orders)
                if o.get('id') not in done]

    def start(self, instruction, phase='approach'):
        self.instruction = dict(instruction or {})
        self.phase = str(phase)

    # --- command ----------------------------------------------------------
    def command(self, now_s):
        """One control step: own-memory differential pulse, or the wheel hold.

        Drive is the calibrated finite-pulse vocabulary: every moving wheel is
        sent at WHEEL_PCT and the proportional left/right magnitudes are encoded
        in the per-wheel pulse width (PULSE_S full scale), so the issued row
        stays inside the own-command whitelist.  SEARCH uses the same amplitude
        with a shorter symmetric pulse (SEARCH_PULSE_DUTY * PULSE_S) and turns
        left/right wheels in opposite directions.  No calibration is invented.
        """
        from harness.active_camera import SEARCH  # hold PWM values only (no map)
        pwm = {str(k): int(v) for k, v in SEARCH.items()}
        plan = self._drive_plan(now_s)
        self._drive_reason = plan['reason']
        searching = plan['reason'] == 'searching'
        acquiring = plan['reason'] == 'acquiring_forward'
        if searching:
            # The budget clock starts with the first issued pulse, and each
            # pulse advances the sweep leg (direction reverses every leg).
            if self._search_started_s is None:
                self._search_started_s = float(now_s)
            self._search_steps += 1
        if plan['reason'] in ('driving', 'driving_hold_heading') or searching or acquiring:
            from harness.grasp_act_contract import wheel_mix
            if acquiring:
                forward, turn = 1.0, 0.0  # straight +x bounded leg, no turn
            elif searching:
                forward, turn = 0.0, plan['turn']
            else:
                forward, turn = plan['forward'], plan['turn']
            pulse_s = SEARCH_PULSE_DUTY * PULSE_S if searching else PULSE_S
            wheels, duration = [], []
            for value in wheel_mix((forward, 0.0, turn)):
                value = clamp(float(value), -1.0, 1.0)
                if abs(value) < MIN_PULSE_FRACTION:
                    wheels.append(0.0)
                    duration.append(0.0)
                else:
                    # Existing finite-pulse vocabulary: calibrated percent
                    # amplitude, pulse width proportional to wheel magnitude.
                    wheels.append(math.copysign(WHEEL_PCT, value))
                    duration.append(abs(value) * pulse_s)
        else:
            wheels, duration = [0.0] * 4, [0.0] * 4
        row = dict(t=float(now_s), wheels=wheels, duration_s=duration, pwm=pwm)
        if acquiring:
            self._consume_forward_step(row)
        if (self.arrival_mode == ARRIVAL_ODOM_RESIDUAL and self._arrival_armed
                and self.odometry is not None):
            # B(a): integrate the own-command distance driven since the contact
            # event.  `_consume_forward_step` may have clipped the pulse width,
            # so the same (clipped) row is integrated.
            step_m, _yaw = self.odometry.step(row)
            if step_m > 0.0:
                self._arrival_travel_m += step_m
        if self.arrival_mode == ARRIVAL_ODOM_PROJECTION:
            # B(r3): integrate the self-odometry pose from the same (possibly
            # clipped) issued row and update the path/projection of the claim.
            self._integrate_projection_step(row)
        self._issued.append(row)
        return row

    def _integrate_projection_step(self, row):
        """Advance the own-odometry pose and the r3 projection claim state.

        The pose is integrated from own issued pulses with the owner-injected
        percent-second calibration (the same `OwnCommandOdometry.step` used for
        self-centric memory): midpoint heading for the translation, then the
        path length and the projection onto the armed bearing unit vector.  When
        the path cap is spent without reaching the claim threshold the adapter
        latches ``NO_CLAIM`` and the plan holds the wheels.  No GT, map or
        world-frame input is read.
        """
        if self.odometry is None:
            return
        step_m, step_yaw_deg = self.odometry.step(row)
        heading = math.radians(self._odom_yaw_deg + 0.5 * step_yaw_deg)
        self._odom_x_m += step_m * math.cos(heading)
        self._odom_y_m += step_m * math.sin(heading)
        self._odom_yaw_deg = wrap_deg(self._odom_yaw_deg + step_yaw_deg)
        if not self._arrival_armed or self._arrival_no_claim:
            return
        self._arrival_path_m += abs(step_m)
        u = math.radians(self._arrival_u_deg)
        self._arrival_proj_m = ((self._odom_x_m - self._arrival_origin_x_m) * math.cos(u)
                                + (self._odom_y_m - self._arrival_origin_y_m) * math.sin(u))
        if (self._arrival_proj_m < self.arrival_projection_m
                and self._arrival_path_m >= self.arrival_projection_path_cap_m - 1e-12):
            self._arrival_no_claim = True

    def _consume_forward_step(self, row):
        """Charge one issued forward pulse against the approved 2.4 m cap.

        The distance is the *own-command* integral with the injected
        percent-second calibration (the same `OwnCommandOdometry.step` used for
        self-centric memory).  The pulse width is clipped so the accumulated
        distance cannot pass the cap; after the cap the plan can only turn in
        place.  No GT, range sensor or map is read.
        """
        remaining = self._forward_remaining_m()
        if remaining <= FORWARD_ACQUISITION_EPS_M:
            return
        step_m, _yaw = self.odometry.step(row)
        if step_m <= 0.0:
            return
        if step_m > remaining:
            scale = remaining / step_m
            row['duration_s'] = [dt * scale for dt in row['duration_s']]
            step_m = remaining
        self._forward_used_m += step_m
        self._forward_steps += 1

    def step_odometry(self, row):
        """Apply an issued command to self-centric memory using owner-injected odometry.

        A record carrying another robot's ``robot_id`` is rejected before use.
        """
        self._check_owner(row, required=False)
        if self.option != OPTION or self.odometry is None:
            return None
        forward_m, yaw_deg = self.odometry.step(row)
        self.memory.transform(forward_m, yaw_deg)
        return forward_m, yaw_deg

    # --- nearfield/release handoff ---------------------------------------
    def confirm_act(self, frame, skill):
        return False  # contract v1: nearfield ACT owns its own confirmation

    def on_messages(self, rows):
        self._messages.extend(copy.deepcopy(rows or ()))

    def accept_release_fix(self, report):
        if self.option != OPTION:
            return False
        if not isinstance(report, dict):
            return False
        # No static map: acceptance is own-memory based only.
        return (report.get('relocalized') is True
                and report.get('memory_registered') is True
                and report.get('truth_inputs', 0) == 0
                and report.get('held_world_reads', 0) == 0)


def navigation_factory(robot_id, static=None, **kwargs):
    return SelfCentricNavigation(robot_id, static, **kwargs)

# ---- own-RGB zone detector (GPU appearance profile, no sim imports) ----
# gpu_calib_v1 was fitted on **OpenCV HSV** pixels: H in 0-180, S and V in
# 0-255.  These are NOT degrees.  hue 110-114 OpenCV == 220-228 degrees.
# `rgb_to_hsv` below returns degrees for readability, so the detector converts
# with /2.0 before comparing.  Mixing the two units was the gate-1 failure.
GPU_CALIB_V1 = dict(hue_cv=(110.0, 114.0), sat_min=100.0, val=(30.0, 110.0),
                    min_pixels=600, units='opencv_h_0_180_sv_0_255')
# Approved 2026-10-19 gate mode: same hue/saturation/min-component as v1, only
# the V ceiling is raised (110 -> 230).  This is the `candidate` band frozen in
# outputs/reports/2026-10-19-nav-rerun-runbook.md §2.1 and approved by the user
# on 2026-10-19 together with the 2.4 m forward acquisition.  The v1 profile is
# unchanged and remains the default; results from the two bands are not pooled.
GPU_CALIB_V230 = dict(hue_cv=(110.0, 114.0), sat_min=100.0, val=(30.0, 230.0),
                      min_pixels=600, units='opencv_h_0_180_sv_0_255')
# BRANCH_NAV_V5 band candidates (2026-10-21, pre-registered in
# experiments/2026-10-21-nav-v5-recal/NAV_V5_RECAL_PREREG_DRAFT.json, default
# OFF).  On the v5 scene the pickup floor overlay renders opaque at OpenCV
# H 107-108 / S~212 / V~90 (experiments/2026-10-18-nav-gate-1), 2-3 hue units
# below zone B; only the hue floor is raised, everything else equals v230.  They
# are selected only by the v5 gate modes in harness.e2ewarp_nav_gate.
GPU_CALIB_V5_H111 = dict(GPU_CALIB_V230, hue_cv=(111.0, 114.0))
GPU_CALIB_V5_H112 = dict(GPU_CALIB_V230, hue_cv=(112.0, 114.0))
GPU_CALIB_PROFILES = {'gpu_calib_v1': GPU_CALIB_V1, 'gpu_calib_v230': GPU_CALIB_V230,
                      'gpu_calib_v5_h111': GPU_CALIB_V5_H111,
                      'gpu_calib_v5_h112': GPU_CALIB_V5_H112}
DEFAULT_GPU_CALIB_PROFILE = 'gpu_calib_v1'
# Bearing convention of the detector.  ``positive_right`` is the legacy
# image-column convention (cx right of centre -> positive); the frozen v1 gate
# never detected a destination, so it was never exercised.  The controller
# treats a *positive* turn as a left (CCW) turn: calibration with the +turn
# pulse pattern measured turn_deg_signed=+120.9 deg (measured yaw, not
# magnitude), and a +5 deg yaw render shifts the zone strip right
# (bbox centre 230 -> 287.5 px), i.e. the unmirrored image has robot-left on
# image-left.  The approved v230_fwd24 mode therefore uses ``positive_left``
# so that a destination seen on the left produces a left turn.  The legacy
# default is unchanged for the frozen v1 gate.
BEARING_POSITIVE_RIGHT = 'positive_right'
BEARING_POSITIVE_LEFT = 'positive_left'
BEARING_CONVENTIONS = (BEARING_POSITIVE_RIGHT, BEARING_POSITIVE_LEFT)
DEFAULT_BEARING_CONVENTION = BEARING_POSITIVE_RIGHT


def rgb_to_hsv(rgb):
    """uint8 HxWx3 RGB -> (hue deg 0-360, sat 0-255, val 0-255) via numpy."""
    import numpy as np
    a = np.asarray(rgb, dtype=np.float64) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-12
    rm = m & (mx == r); gm = m & (mx == g) & ~rm; bm = m & (mx == b) & ~rm & ~gm
    h[rm] = ((g[rm] - b[rm]) / d[rm]) % 6.0
    h[gm] = (b[gm] - r[gm]) / d[gm] + 2.0
    h[bm] = (r[bm] - g[bm]) / d[bm] + 4.0
    h *= 60.0
    sat = np.where(mx > 1e-12, d / np.maximum(mx, 1e-12) * 255.0, 0.0)
    return h, sat, mx * 255.0


def hue_degrees_to_opencv(hue_deg):
    """Map hue degrees (0-360) to OpenCV hue units (0-180), scalar or array.

    `gpu_calib_v1` thresholds live in OpenCV units; this is the only conversion
    the detector is allowed to use.
    """
    return hue_deg / 2.0


def _fisheye_theta(radius_px, d):
    """Invert the OpenCV fisheye radial model for one normalised radius (rad)."""
    lo, hi = 0.0, math.radians(80.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        t2 = mid * mid
        r = mid * (1.0 + t2 * (d[0] + t2 * (d[1] + t2 * (d[2] + t2 * d[3]))))
        if r < radius_px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ground_point_robot(u, v, projection=None):
    """Project one own-RGB pixel onto the floor; robot base frame (x fwd, y left).

    Uses the measured pinhole+fisheye intrinsics and the ground-plane mount pose
    in ``GATE_GROUND_PROJECTION`` (or an explicit ``projection`` mapping).  This
    is a *geometry* projection of the current frame only: no map, no ground
    truth, no simulator state.  Returns ``(x_forward_m, y_left_m)`` or ``None``
    when the ray does not hit the floor (at/above the horizon) or the pixel is
    outside the image.  Fail closed: a bad/absent profile returns ``None``.
    """
    proj = projection if projection is not None else GATE_GROUND_PROJECTION
    try:
        width = int(proj['width']); height = int(proj['height'])
        fx = float(proj['fx_px']); fy = float(proj['fy_px'])
        cx = float(proj['cx_px']); cy = float(proj['cy_px'])
        height_m = float(proj['camera_height_m'])
        pitch = math.radians(float(proj['pitch_down_deg']))
        offset = float(proj.get('camera_x_offset_m') or 0.0)
        d = tuple(float(x) for x in proj['fisheye_d'])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 <= float(u) <= width - 1.0 and 0.0 <= float(v) <= height - 1.0):
        return None
    if not (height_m > 0.0 and fy > 0.0 and fx > 0.0):
        return None
    dx = (float(u) - cx) / fx
    dy = (float(v) - cy) / fy
    radius = math.hypot(dx, dy)
    theta = _fisheye_theta(radius, d) if radius > 1e-12 else 0.0
    phi = math.atan2(dy, dx) if radius > 1e-12 else 0.0
    right = math.sin(theta) * math.cos(phi)
    down = math.sin(theta) * math.sin(phi)
    forward = math.cos(theta)
    # Optical axis pitched down by `pitch`; image right = robot right.
    fwd = math.cos(pitch) * forward - math.sin(pitch) * down
    up = -math.sin(pitch) * forward - math.cos(pitch) * down
    left = -right
    if up >= -1e-9:
        return None
    scale = height_m / (-up)
    return scale * fwd + offset, scale * left


def ground_distance_m(u, v, projection=None):
    """Ground distance (m) from the robot base origin to one pixel's floor point."""
    point = ground_point_robot(u, v, projection)
    return None if point is None else math.hypot(point[0], point[1])


def largest_component(mask):
    """Largest 4-connected component of a boolean mask.

    Returns ``dict(area, left, top, right, bottom)`` with exclusive right/bottom,
    or ``None``.  Run-length union-find: each row is compressed to its True runs
    and runs from adjacent rows are unioned when their columns overlap.  This is
    dependency-free (no scipy/cv2) and linear in the number of runs, which keeps
    the CPU adapter cheap at 10 Hz.  The detector classifies by this component,
    never by ``mask.sum()``: scattered floor pixels add up without forming a
    patch.
    """
    import numpy as np
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2 or not m.any():
        return None
    parent = []
    spans = []  # run id -> (row, left, right_exclusive)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    prev = []
    for y in range(m.shape[0]):
        d = np.diff(np.concatenate(([False], m[y], [False])).astype(np.int8))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1)  # exclusive
        cur = []
        j = 0
        for x0, x1 in zip(starts.tolist(), ends.tolist()):
            rid = len(parent)
            parent.append(rid)
            spans.append((y, x0, x1))
            cur.append(rid)
            while j < len(prev) and spans[prev[j]][2] <= x0:
                j += 1
            k = j
            while k < len(prev) and spans[prev[k]][1] < x1:
                union(rid, prev[k])
                k += 1
        prev = cur

    agg = {}
    for rid, (y, x0, x1) in enumerate(spans):
        root = find(rid)
        box = agg.get(root)
        if box is None:
            agg[root] = [x1 - x0, x0, x1, y, y + 1]
        else:
            box[0] += x1 - x0
            box[1] = min(box[1], x0)
            box[2] = max(box[2], x1)
            box[3] = min(box[3], y)
            box[4] = max(box[4], y + 1)
    area, left, right, top, bottom = max(agg.values(), key=lambda b: b[0])
    return dict(area=int(area), left=int(left), top=int(top),
                right=int(right), bottom=int(bottom))


class GpuCalibZoneDetector:
    """Detect destination zone paint from one own RGB frame (frozen appearance profile).

    Threshold provenance: experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu
    (MJWarp native render, 36 frames): OpenCV hue 110-114, S>=100, 30<=V<=110,
    largest connected component >=600 px.  Re-measured offline in OpenCV units:
    30/30 zone-B poses detected and 0/2 nav-gate floor frames detected
    (experiments/2026-10-18-nav-gate-1/CALIBRATION_PREREG.md).  The earlier
    extent-gated CPU detector reported zone-B 33/33, pickup FP 0/3, R4 floor
    FP 0/180 on the same capture.  Units are explicit: ``hue_cv`` is OpenCV
    H 0-180 (220-228 degrees), not degrees.  Classification uses the largest
    connected component only; the total mask is reported for audit but never
    decides.  This detector supplies *evidence only* (bearing/bottom band/component
    geometry), never a success claim and never reads a map, GT, top camera, or
    simulator state.

    ``profile='gpu_calib_v230'`` is the 2026-10-19 approved band: identical
    hue/saturation/min-component, V ceiling 230.  Only
    ``harness.e2ewarp_nav_gate`` selects it; the default stays ``gpu_calib_v1``.
    """
    def __init__(self, *, profile=DEFAULT_GPU_CALIB_PROFILE, hfov_deg=120.0,
                 min_pixels=None, bearing_convention=DEFAULT_BEARING_CONVENTION):
        if profile not in GPU_CALIB_PROFILES:
            raise ValueError('unknown own-RGB appearance profile')
        if bearing_convention not in BEARING_CONVENTIONS:
            raise ValueError('unknown bearing convention: ' + str(bearing_convention))
        self.profile = profile
        self.bearing_convention = bearing_convention
        self.band = GPU_CALIB_PROFILES[profile]
        self.hfov_deg = float(hfov_deg)
        self.min_pixels = int(min_pixels or self.band['min_pixels'])

    def __call__(self, frame_or_rgb):
        import io
        import numpy as np
        from PIL import Image
        raw = frame_or_rgb.jpeg if hasattr(frame_or_rgb, 'jpeg') else frame_or_rgb
        img = Image.open(io.BytesIO(raw)).convert('RGB') if isinstance(raw, (bytes, bytearray)) else Image.fromarray(np.asarray(raw, dtype=np.uint8))
        rgb = np.asarray(img)
        h_deg, s, v = rgb_to_hsv(rgb)
        h = hue_degrees_to_opencv(h_deg)  # OpenCV H 0-180, the profile's unit
        lo, hi = self.band['hue_cv']; vlo, vhi = self.band['val']
        mask = (h >= lo) & (h <= hi) & (s >= self.band['sat_min']) & (v >= vlo) & (v <= vhi)
        total = int(mask.sum())
        comp = largest_component(mask)
        if comp is None or comp['area'] < self.min_pixels:
            return []
        H, W = mask.shape
        left, right, top, bottom = comp['left'], comp['right'], comp['top'], comp['bottom']
        width, height = right - left, bottom - top

        def column_bearing(column):
            """Bearing (deg) of one image column under this detector's convention."""
            offset = column / max(W - 1, 1) - 0.5
            if self.bearing_convention == BEARING_POSITIVE_LEFT:
                offset = -offset
            return offset * self.hfov_deg

        cx = (left + right - 1) / 2.0
        bearing = column_bearing(cx)
        # r4 slot aim (2026-10-19, default OFF): the bbox edge columns are
        # measured here from the same own frame so an order-sheet slot can aim
        # at the centre of one half of the visible marking.  They are additive
        # measurement fields; no existing consumer reads them.
        bearing_left = column_bearing(left)
        bearing_right = column_bearing(right)
        return [dict(kind='zone_B', bearing_deg=bearing, bottom_norm=bottom / H,
                     width_norm=width / W, height_norm=height / H,
                     area_norm=comp['area'] / (H * W), solidity=comp['area'] / (width * height),
                     spans_center_x=bool(left <= W // 2 < right),
                     touches_left=bool(left <= 0), touches_right=bool(right >= W),
                     touches_top=bool(top <= 0),
                     bbox=(left, top, right, bottom), pixels=comp['area'], total_pixels=total,
                     bearing_at_left_edge_deg=bearing_left,
                     bearing_at_right_edge_deg=bearing_right,
                     hue_units=self.band['units'], profile=self.profile,
                     bearing_convention=self.bearing_convention)]


# Issued rows carry the adapter's *normalized* wheel duty in [-1, 1] (`WHEEL_PCT =
# .35` is 35 %), while the injected calibration is measured per *percent*-second
# (calibration JSON: pulse.percent = 35.0, width_s = 0.1).  This constant is the
# single conversion boundary between those two vocabularies; the calibration JSON
# contract (forward_m_per_pct_s, yaw_deg_per_pct_s) stays unchanged.
PCT_PER_NORMALIZED_WHEEL = 100.0


class OwnCommandOdometry:
    """Integrate own issued wheel pulses into self-centric displacement (injected calibration).

    Wheel mix matches harness.grasp_act_contract.wheel_mix: (f-l-t, f+l+t, f-l-t, f-l+t).
    Calibration is owner-supplied measured metres / degrees per *percent*-second; this
    class invents no defaults (contract v1: no unjustified constants).

    Input rows are the adapter's own commands, whose wheel values are normalized duty
    in [-1, 1] (a 0.35 wheel is 35 %).  `step` converts that duty to percent (x100)
    before applying the percent-second constants, so 0.35 for 0.1 s integrates as
    3.5 pct-s (0.0141 m at the gate forward calibration), not as 0.035 pct-s
    (1.4e-4 m, a 100x under-integration).
    """
    def __init__(self, *, forward_m_per_pct_s, yaw_deg_per_pct_s):
        self.forward = float(forward_m_per_pct_s); self.yaw = float(yaw_deg_per_pct_s)
        if not (self.forward > 0.0 and self.yaw > 0.0):
            raise ValueError('odometry calibration must be positive')

    @staticmethod
    def wheels_percent(row):
        """Own normalized wheel duty in [-1, 1] expressed as percent (-100 .. 100)."""
        return [float(w) * PCT_PER_NORMALIZED_WHEEL for w in row['wheels']]

    def step(self, row):
        # Convert at the boundary: normalized duty -> percent, the calibration unit.
        wheels = self.wheels_percent(row); dts = list(row['duration_s'])
        if len(wheels) != 4 or len(dts) != 4:
            raise ValueError('four own wheel pulses required')
        f = sum(w * dt for w, dt in zip(wheels, dts)) / 4.0
        t = ((wheels[1] * dts[1] + wheels[3] * dts[3]) - (wheels[0] * dts[0] + wheels[2] * dts[2])) / 4.0
        return f * self.forward, t * self.yaw

