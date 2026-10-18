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
            kept.append(Landmark(str(det['kind']), float(det['range_m']), float(det['bearing_deg']), float(now_s)))
        self.items = kept[-16:]

    def nearest(self, kind):
        hits = [i for i in self.items if i.kind == kind]
        return min(hits, key=lambda i: (i.range_m, i.uncertainty_m)) if hits else None

    def as_report(self):
        return [dict(kind=i.kind, range_m=round(i.range_m, 3), bearing_deg=round(i.bearing_deg, 2),
                     last_seen_s=round(i.last_seen_s, 3), uncertainty_m=round(i.uncertainty_m, 3))
                for i in self.items]


class SelfCentricNavigation:
    """navigation_factory ABI: observe/task_candidates/start/command/confirm_act/on_messages/accept_release_fix."""

    def __init__(self, robot_id, static=None, *, option='off', detector=None, motion_model=None):
        if robot_id not in ('r1', 'r2'):
            raise ValueError('contract v1 navigation is two-robot only (r1/r2)')
        self.robot_id = robot_id
        self.option = option
        self.orders = order_sheet(static).get('orders') or []
        self.detector = detector            # own-RGB landmark detector (owner injected)
        self.motion_model = motion_model    # commanded-displacement model (owner injected)
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
        arrived = bool(zone is not None and zone.range_m <= 0.25 and zone.uncertainty_m <= 0.5)
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
