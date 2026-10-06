"""Stage C: the robot's own wall map in its own frame, accumulated per observation. OPTION, default OFF. Refs #216.

Design ``docs/design/2026-10-05-ego-wall-map-for-llm-memory.md`` stage C: no pose, no fusion, no loop closure, no
de-duplication. Every settled observation that shows at least one wall face is appended as

    {'t_sim': 12.3, 'seg': [(r1, th1, r2, th2, h), ...], 'posture': 'high', 'load': True, 'view_index': 4812}

``seg`` entries are the two end points of a wall face and its measured height, in the ROBOT (chassis) frame at
``t_sim``: ``r`` metres from the chassis origin, ``th`` radians counter-clockwise from the chassis +x (forward).
``t_sim`` is kept: an old observation is less accurate than a new one, and the LLM has to be able to know that.

Frame. The detector works in forward-kinematics coordinates whose origin is the arm-base axis, ``ARM_AXIS_OFFSET_M``
(0.0482 m, ``sim/masterpi_geometry_v3.YAW_AXIS_X_M``) ahead of the chassis origin. The map origin is the chassis origin,
and the arm-axis offset is RECORDED ONLY: ``EgoWallMap(arm_axis_offset_m=...)`` is the shift applied to the end points and
defaults to 0 (``DEFAULT_APPLIED_OFFSET_M``), so the records are in the detector's arm-axis coordinates. The header always
carries the physical offset (``arm_axis_offset_recorded_m``) and the one applied (``arm_axis_offset_m``); pass
``arm_axis_offset_m=ARM_AXIS_OFFSET_M`` to get exact chassis-origin coordinates. README §13.1 scores both.

Gate (``settle_s``). The camera model is forward kinematics of the COMMANDED pulses, valid once the arm has followed
them. An observation is recorded only when the commanded pulses have been unchanged for ``settle_s[load class]``
seconds: 0.25 s unloaded, 2.25 s loaded, derived from the recordings by ``settle_curve.py`` (the arm settles slower
when it carries the beam). Own command history only.

Everything is inert unless ``enabled=True``: a disabled map keeps nothing and returns nothing.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Mapping, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from harness.zone_pair_highpose import at_high  # noqa: E402
from sim.masterpi_geometry_v3 import YAW_AXIS_X_M  # noqa: E402

ARM_AXIS_OFFSET_M = YAW_AXIS_X_M                       # chassis origin -> arm-base axis (the FK frame origin), 0.0482 m
DEFAULT_APPLIED_OFFSET_M = 0.0                         # recorded only (coordinator decision): nothing is shifted by default
SETTLE_S = {'unloaded': 0.25, 'loaded': 2.25}           # settle_curve.py: fit on s911, confirmed on s912/s913 (loaded: 1 run)
SCHEMA = 'ego-wall-map/1'


def fk_to_chassis(point_fk, arm_axis_offset_m: float = ARM_AXIS_OFFSET_M):
    """FK-frame (x, y) -> chassis-frame (x, y): the FK origin is the arm axis, ahead of the chassis origin.

    ``arm_axis_offset_m`` is the shift to apply; the default is the physical offset, ``EgoWallMap`` passes its own
    (default 0, recorded only)."""
    return point_fk[0] + arm_axis_offset_m, point_fk[1]


def segment_to_chassis(seg: Mapping, nadir_fk, arm_axis_offset_m: float = ARM_AXIS_OFFSET_M):
    """``height_free_wall.link_segments`` entry -> (r1, th1, r2, th2, h) about the chassis origin
    (``arm_axis_offset_m`` = 0: about the arm axis).

    ``range_*`` / ``bearing_*`` are measured from the camera nadir in the FK frame; ``nadir_fk`` is that nadir
    (``ColumnModel.origin[:2]``).
    """
    pts = []
    for end in ('first', 'last'):
        r, b = seg[f'range_{end}_m'], seg[f'bearing_{end}_rad']
        x, y = fk_to_chassis((nadir_fk[0] + r*math.cos(b), nadir_fk[1] + r*math.sin(b)), arm_axis_offset_m)
        pts.append((math.hypot(x, y), math.atan2(y, x)))
    h = seg.get('height_m')
    return (round(pts[0][0], 4), round(pts[0][1], 4), round(pts[1][0], 4), round(pts[1][1], 4),
            None if h is None else round(float(h), 4))


def posture_label(servo: Mapping) -> str:
    """'high' = the raised carry/localisation pose of ``harness.zone_pair_highpose``, else 'other'."""
    return 'high' if at_high(servo) else 'other'


class EgoWallMap:
    """Append-only list of ego-frame wall observations. ``enabled=False`` (default) is a no-op."""

    def __init__(self, enabled: bool = False, settle_s: Mapping[str, float] | None = SETTLE_S,
                 arm_axis_offset_m: float = DEFAULT_APPLIED_OFFSET_M):
        self.enabled = bool(enabled)
        self.settle_s = None if settle_s is None else dict(settle_s)
        self.arm_axis_offset_m = float(arm_axis_offset_m)
        self.records: list[dict] = []
        self.frames_seen = 0              # settled observations examined (with or without a wall)
        self._cmd = None
        self._since = 0.0

    # -- own command history -------------------------------------------------------------------------------
    def update_command(self, t_sim: float, servo: Mapping) -> None:
        """Call on every control tick with the commanded pulses; tracks when they last changed."""
        if not self.enabled:
            return
        key = tuple(sorted((int(k), int(v)) for k, v in servo.items()))
        if key != self._cmd:
            self._cmd, self._since = key, float(t_sim)

    def settled(self, t_sim: float, loaded: bool) -> bool:
        """True when the commanded pulses have been constant for the load class's settle time (always, with no gate)."""
        if not self.enabled:
            return False
        if self.settle_s is None:
            return True
        return float(t_sim) - self._since >= self.settle_s['loaded' if loaded else 'unloaded']

    # -- observation ---------------------------------------------------------------------------------------
    def observe(self, t_sim: float, servo: Mapping, loaded: bool, nadir_fk, segments: Sequence[Mapping],
                view_index: int) -> dict | None:
        """Record one detector output. Returns the record, or None (disabled, not settled, or no wall face)."""
        if not self.enabled or not self.settled(t_sim, loaded):
            return None
        self.frames_seen += 1
        if not segments:
            return None
        rec = {'t_sim': round(float(t_sim), 3),
               'seg': [segment_to_chassis(s, nadir_fk, self.arm_axis_offset_m) for s in segments],
               'posture': posture_label(servo), 'load': bool(loaded), 'view_index': int(view_index)}
        self.records.append(rec)
        return rec

    # -- file ----------------------------------------------------------------------------------------------
    def header(self) -> dict:
        return {'schema': SCHEMA, 'frame': 'origin labelled chassis; +x forward, +y left; seg = (r1, th1, r2, th2, h) in m, rad, m',
                'arm_axis_offset_m': self.arm_axis_offset_m,
                'arm_axis_offset_recorded_m': ARM_AXIS_OFFSET_M,
                'arm_axis_offset_note': 'arm_axis_offset_recorded_m is how far the arm axis (the detector / forward-'
                                        'kinematics frame origin) lies ahead of the chassis origin. arm_axis_offset_m is the '
                                        'shift already applied to the x of the end points: 0 = not applied, seg is about '
                                        'the arm axis, add the recorded offset to x for exact chassis-origin coordinates; '
                                        'equal to the recorded offset = seg is about the chassis origin',
                'settle_s': self.settle_s, 'settled_frames_seen': self.frames_seen, 'records': len(self.records)}

    def save(self, path) -> None:
        lines = [json.dumps(self.header())] + [json.dumps(r) for r in self.records]
        Path(path).write_text('\n'.join(lines) + '\n')

    @staticmethod
    def load(path) -> tuple[dict, list[dict]]:
        lines = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        return lines[0], lines[1:]
