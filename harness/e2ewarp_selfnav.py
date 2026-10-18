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
  and holds the wheels once arrival evidence is recorded (bottom band >= 0.98
  or measured range <= the configured threshold). Missing calibration or a
  missing destination stays fail-closed (wheels 0) with a reported reason.
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
# Arrival evidence recorded in self-centric memory (contract v1 scaffold values).
ARRIVAL_BOTTOM_NORM = .98
ARRIVAL_RANGE_M = .25
ARRIVAL_UNCERTAINTY_M = .5
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
                     bottom_norm=round(i.bottom_norm, 3), range_measured=bool(i.range_measured))
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
            return self._report(active=False)
        self.memory.observe(frame.sim_s, self.detector(frame) if self.detector else ())
        self._revision += 1
        return self._report(active=True)

    def _arrival_evidence(self, landmark):
        """Recorded own-memory arrival: near bottom band or measured close range."""
        if landmark.bottom_norm >= ARRIVAL_BOTTOM_NORM:
            return True
        return (landmark.range_measured
                and landmark.range_m <= self.arrival_range_m
                and landmark.uncertainty_m <= ARRIVAL_UNCERTAINTY_M)

    def _drive_plan(self):
        """Own-memory control plan; no plan means the wheel hold is returned."""
        landmark = self.memory.nearest(self.destination_kind)
        if self.option != OPTION:
            return dict(reason='option_off', landmark=landmark, forward=0.0, turn=0.0)
        if self.odometry is None:
            return dict(reason='no_odometry', landmark=landmark, forward=0.0, turn=0.0)
        if landmark is None:
            return dict(reason='no_destination', landmark=None, forward=0.0, turn=0.0)
        if self._arrival_evidence(landmark):
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

    def _report(self, *, active):
        holding = 'unknown'
        returned = self.memory.nearest('return')
        plan = self._drive_plan()
        zone = plan['landmark']
        arrived = bool(active and zone is not None and self._arrival_evidence(zone))
        handoff = bool(self.phase == 'APPROACH' and self.memory.nearest('cargo') is not None
                       and self.memory.nearest('cargo').range_m <= 0.6)
        return dict(robot_id=self.robot_id, phase=self.phase, position_xy=(0.0, 0.0),
                    map_correction_active=bool(active), self_centric_memory=self.memory.as_report(),
                    holding_status=holding, destination_arrived=arrived, handoff_ready=handoff,
                    evidence_revision=self._revision, return_landmark=bool(returned),
                    ready=self.ready, drive_reason=plan['reason'],
                    destination_landmark=(None if zone is None else zone.kind))

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
        stays inside the own-command whitelist.  No calibration is invented.
        """
        from harness.active_camera import SEARCH  # hold PWM values only (no map)
        pwm = {str(k): int(v) for k, v in SEARCH.items()}
        plan = self._drive_plan()
        self._drive_reason = plan['reason']
        if plan['reason'] == 'driving':
            from harness.grasp_act_contract import wheel_mix
            wheels, duration = [], []
            for value in wheel_mix((plan['forward'], 0.0, plan['turn'])):
                value = clamp(float(value), -1.0, 1.0)
                if abs(value) < MIN_PULSE_FRACTION:
                    wheels.append(0.0)
                    duration.append(0.0)
                else:
                    # Existing finite-pulse vocabulary: calibrated percent
                    # amplitude, pulse width proportional to wheel magnitude.
                    wheels.append(math.copysign(WHEEL_PCT, value))
                    duration.append(abs(value) * PULSE_S)
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
GPU_CALIB_V1 = dict(hue=(110.0, 114.0), sat_min=100.0, val=(30.0, 110.0), min_pixels=600)


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


class GpuCalibZoneDetector:
    """Detect destination zone paint from one own RGB frame (gpu_calib_v1 profile).

    Threshold provenance: experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu
    (MJWarp native render, 36 frames): hue 110-114, S>=100, 30<=V<=110, component
    >=600 px; on that capture zone-B 33/33 accepted, pickup FP 0/3, R4 floor FP 0/180.
    This detector supplies *evidence only* (bearing/bottom band), never a success claim
    and never reads a map, GT, top camera, or simulator state.
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
        h, s, v = rgb_to_hsv(rgb)
        lo, hi = GPU_CALIB_V1['hue']; vlo, vhi = GPU_CALIB_V1['val']
        mask = (h >= lo) & (h <= hi) & (s >= GPU_CALIB_V1['sat_min']) & (v >= vlo) & (v <= vhi)
        n = int(mask.sum())
        if n < self.min_pixels:
            return []
        ys, xs = np.nonzero(mask)
        H, W = mask.shape
        cx = float(xs.mean()); top, bottom = int(ys.min()), int(ys.max())
        bearing = (cx / max(W - 1, 1) - 0.5) * self.hfov_deg
        return [dict(kind='zone_B', bearing_deg=bearing, bottom_norm=(bottom + 1) / H,
                     width_norm=(xs.max() - xs.min() + 1) / W, height_norm=(bottom - top + 1) / H,
                     pixels=n, profile='gpu_calib_v1')]


class OwnCommandOdometry:
    """Integrate own issued wheel pulses into self-centric displacement (injected calibration).

    Wheel mix matches harness.grasp_act_contract.wheel_mix: (f-l-t, f+l+t, f+l-t, f-l+t).
    Calibration is owner-supplied measured metres / degrees per percent-second; this
    class invents no defaults (contract v1: no unjustified constants).
    """
    def __init__(self, *, forward_m_per_pct_s, yaw_deg_per_pct_s):
        self.forward = float(forward_m_per_pct_s); self.yaw = float(yaw_deg_per_pct_s)
        if not (self.forward > 0.0 and self.yaw > 0.0):
            raise ValueError('odometry calibration must be positive')

    def step(self, row):
        wheels = list(row['wheels']); dts = list(row['duration_s'])
        if len(wheels) != 4 or len(dts) != 4:
            raise ValueError('four own wheel pulses required')
        f = sum(w * dt for w, dt in zip(wheels, dts)) / 4.0
        t = ((wheels[1] * dts[1] + wheels[3] * dts[3]) - (wheels[0] * dts[0] + wheels[2] * dts[2])) / 4.0
        return f * self.forward, t * self.yaw

