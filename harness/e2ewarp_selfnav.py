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

No ground truth, contact, evaluator, top camera, or peer raw input is accepted.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass, field

OPTION = 'e2ewarp_selfnav_v1'
ALLOWED_STATIC_KEYS = ('orders', 'goal', 'mission', 'robot_count', 'destination_zone', 'condition')
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
    # Appearance-only detectors (e.g. GpuCalibZoneDetector) report no metric
    # range.  A default 0.0 must never be read as "arrived at 0 m".
    range_measured: bool = True

    def decay(self, now_s, *, rate_m_per_s=0.02, max_m=3.0):
        self.uncertainty_m = min(max_m, self.uncertainty_m + rate_m_per_s * max(0.0, now_s - self.last_seen_s))


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
            kept.append(Landmark(str(det['kind']), float(det.get('range_m') or 0.0), float(det['bearing_deg']),
                                 float(now_s), bottom_norm=float(det.get('bottom_norm', 0.0)),
                                 width_norm=float(det.get('width_norm', 0.0)), pixels=int(det.get('pixels', 0)),
                                 height_norm=float(det.get('height_norm', 0.0)),
                                 area_norm=float(det.get('area_norm', 0.0)),
                                 solidity=float(det.get('solidity', 0.0)),
                                 spans_center_x=bool(det.get('spans_center_x', False)),
                                 touches_top=bool(det.get('touches_top', False)),
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
                     range_measured=bool(i.range_measured))
                for i in self.items]


class SelfCentricNavigation:
    """navigation_factory ABI: observe/task_candidates/start/command/confirm_act/on_messages/accept_release_fix."""

    def __init__(self, robot_id, static=None, *, option='off', detector=None, odometry=None,
                 destination_kind=None, arrival_range_m=ARRIVAL_RANGE_M):
        if robot_id not in ('r1', 'r2'):
            raise ValueError('contract v1 navigation is two-robot only (r1/r2)')
        self.robot_id = robot_id
        self.option = option
        sheet = order_sheet(static)
        self.orders = sheet.get('orders') or []
        zone = sheet.get('destination_zone')
        if zone is None and isinstance(sheet.get('mission'), Mapping):
            zone = sheet['mission'].get('destination_zone')
        if destination_kind is None and isinstance(zone, str) and zone:
            destination_kind = zone if zone.startswith('zone_') else f'zone_{zone}'
        self.destination_kind = str(destination_kind) if destination_kind is not None else DESTINATION_KIND
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
        self.memory.observe(frame.sim_s, self.detector(frame) if self.detector else ())
        self._revision += 1
        return self._report(active=True, now_s=frame.sim_s)

    def _arrival_evidence(self, landmark, now_s):
        """Current own-memory arrival: bottom band or measured close range.

        The bottom-band path is a visual claim, so it must be fresh and its
        component must look like a paint patch rather than a floor fill.  A
        stale claim is not evidence: memory keeps landmarks for driving, but it
        must not keep an arrival claim after the patch left the camera.
        """
        if now_s - landmark.last_seen_s > ARRIVAL_EVIDENCE_MAX_AGE_S:
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

    def _drive_plan(self, now_s=None):
        """Own-memory control plan; no plan means the wheel hold is returned."""
        if now_s is None:  # test/introspection default: the last own frame's time
            now_s = self._last_frame.sim_s if self._last_frame is not None else 0.0
        landmark = self.memory.nearest(self.destination_kind)
        if self.option != OPTION:
            return dict(reason='option_off', landmark=landmark, forward=0.0, turn=0.0)
        if self.odometry is None:
            return dict(reason='no_odometry', landmark=landmark, forward=0.0, turn=0.0)
        if landmark is None:
            # No remembered destination: acquire it with a bounded in-place
            # sweep.  Fail closed when the detector was not injected (nothing
            # could ever be acquired) or when the budget is exhausted.
            if not self.ready:
                return dict(reason='no_destination', landmark=None, forward=0.0, turn=0.0)
            reason = self._search_reason(now_s)
            if reason == 'search_timeout':
                return dict(reason=reason, landmark=None, forward=0.0, turn=0.0)
            return dict(reason=reason, landmark=None, forward=0.0, turn=self._search_turn())
        if self._arrival_evidence(landmark, now_s):
            return dict(reason='arrived', landmark=landmark, forward=0.0, turn=0.0)
        bearing = wrap_deg(landmark.bearing_deg)
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
        arrived = bool(active and zone is not None and self._arrival_evidence(zone, now_s))
        handoff = bool(self.phase == 'APPROACH' and self.memory.nearest('cargo') is not None
                       and self.memory.nearest('cargo').range_m <= 0.6)
        return dict(robot_id=self.robot_id, phase=self.phase, position_xy=(0.0, 0.0),
                    map_correction_active=bool(active), self_centric_memory=self.memory.as_report(),
                    holding_status=holding, destination_arrived=arrived, handoff_ready=handoff,
                    evidence_revision=self._revision, return_landmark=bool(returned),
                    ready=self.ready, drive_reason=plan['reason'],
                    destination_landmark=(None if zone is None else zone.kind),
                    search_elapsed_s=round(self._search_elapsed_s(now_s), 3),
                    search_steps=int(self._search_steps))

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
        if searching:
            # The budget clock starts with the first issued pulse, and each
            # pulse advances the sweep leg (direction reverses every leg).
            if self._search_started_s is None:
                self._search_started_s = float(now_s)
            self._search_steps += 1
        if plan['reason'] == 'driving' or searching:
            from harness.grasp_act_contract import wheel_mix
            forward, turn = (0.0, plan['turn']) if searching else (plan['forward'], plan['turn'])
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
        self._issued.append(row)
        return row

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
    """Detect destination zone paint from one own RGB frame (gpu_calib_v1 profile).

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
    """
    def __init__(self, *, profile='gpu_calib_v1', hfov_deg=120.0, min_pixels=None):
        if profile != 'gpu_calib_v1':
            raise ValueError('unknown own-RGB appearance profile')
        self.hfov_deg, self.min_pixels = float(hfov_deg), int(min_pixels or GPU_CALIB_V1['min_pixels'])

    def __call__(self, frame_or_rgb):
        import io
        import numpy as np
        from PIL import Image
        raw = frame_or_rgb.jpeg if hasattr(frame_or_rgb, 'jpeg') else frame_or_rgb
        img = Image.open(io.BytesIO(raw)).convert('RGB') if isinstance(raw, (bytes, bytearray)) else Image.fromarray(np.asarray(raw, dtype=np.uint8))
        rgb = np.asarray(img)
        h_deg, s, v = rgb_to_hsv(rgb)
        h = hue_degrees_to_opencv(h_deg)  # OpenCV H 0-180, the profile's unit
        lo, hi = GPU_CALIB_V1['hue_cv']; vlo, vhi = GPU_CALIB_V1['val']
        mask = (h >= lo) & (h <= hi) & (s >= GPU_CALIB_V1['sat_min']) & (v >= vlo) & (v <= vhi)
        total = int(mask.sum())
        comp = largest_component(mask)
        if comp is None or comp['area'] < self.min_pixels:
            return []
        H, W = mask.shape
        left, right, top, bottom = comp['left'], comp['right'], comp['top'], comp['bottom']
        width, height = right - left, bottom - top
        cx = (left + right - 1) / 2.0
        bearing = (cx / max(W - 1, 1) - 0.5) * self.hfov_deg
        return [dict(kind='zone_B', bearing_deg=bearing, bottom_norm=bottom / H,
                     width_norm=width / W, height_norm=height / H,
                     area_norm=comp['area'] / (H * W), solidity=comp['area'] / (width * height),
                     spans_center_x=bool(left <= W // 2 < right),
                     touches_left=bool(left <= 0), touches_right=bool(right >= W),
                     touches_top=bool(top <= 0),
                     bbox=(left, top, right, bottom), pixels=comp['area'], total_pixels=total,
                     hue_units=GPU_CALIB_V1['units'], profile='gpu_calib_v1')]


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

