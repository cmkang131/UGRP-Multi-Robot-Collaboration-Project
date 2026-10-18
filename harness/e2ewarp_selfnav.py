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
- Default OFF fails closed (wheel hold, no arrival claim). This is a scaffold:
  the motion model and own-RGB landmark detector are injected by the owner and
  are deliberately absent here; ready=false until physical gates pass.

No ground truth, contact, evaluator, top camera, or peer raw input is accepted.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

OPTION = 'e2ewarp_selfnav_v1'
ALLOWED_STATIC_KEYS = ('orders', 'goal', 'mission', 'robot_count', 'destination_zone', 'condition')


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
            kept.append(Landmark(str(det['kind']), float(det.get('range_m', 0.0)), float(det['bearing_deg']),
                                 float(now_s), bottom_norm=float(det.get('bottom_norm', 0.0)),
                                 width_norm=float(det.get('width_norm', 0.0)), pixels=int(det.get('pixels', 0))))
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
                     last_seen_s=round(i.last_seen_s, 3), uncertainty_m=round(i.uncertainty_m, 3))
                for i in self.items]


class SelfCentricNavigation:
    """navigation_factory ABI: observe/task_candidates/start/command/confirm_act/on_messages/accept_release_fix."""

    def __init__(self, robot_id, static=None, *, option='off', detector=None, odometry=None):
        if robot_id not in ('r1', 'r2'):
            raise ValueError('contract v1 navigation is two-robot only (r1/r2)')
        self.robot_id = robot_id
        self.option = option
        self.orders = order_sheet(static).get('orders') or []
        self.detector = detector            # own-RGB landmark detector (owner injected)
        self.odometry = odometry            # own-command odometry (owner injected calibration)
        self.memory = SelfCentricMemory()
        self.phase = 'TASK'
        self.instruction = None
        self._last_frame = None
        self._revision = 0
        self._messages = []
        self._issued = []

    # --- own observation -------------------------------------------------
    def observe(self, frame):
        self._last_frame = frame
        if self.option != OPTION:
            return self._report(active=False)
        self.memory.observe(frame.sim_s, self.detector(frame) if self.detector else ())
        self._revision += 1
        return self._report(active=True)

    def _report(self, *, active):
        holding = 'unknown'
        returned = self.memory.nearest('return')
        zone = self.memory.nearest('zone_B')
        arrived = bool(zone is not None and (zone.bottom_norm >= 0.98 or (zone.range_m <= 0.25 and zone.uncertainty_m <= 0.5)))
        handoff = bool(self.phase == 'APPROACH' and self.memory.nearest('cargo') is not None
                       and self.memory.nearest('cargo').range_m <= 0.6)
        return dict(robot_id=self.robot_id, phase=self.phase, position_xy=(0.0, 0.0),
                    map_correction_active=bool(active), self_centric_memory=self.memory.as_report(),
                    holding_status=holding, destination_arrived=arrived, handoff_ready=handoff,
                    evidence_revision=self._revision, return_landmark=bool(returned))

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
        from harness.active_camera import SEARCH  # hold PWM values only (no map)
        pwm = {str(k): int(v) for k, v in SEARCH.items()}
        row = dict(t=float(now_s), wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm=pwm)
        self._issued.append(row)
        return row

    def step_odometry(self, row):
        """Apply an issued command to self-centric memory using owner-injected odometry."""
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

