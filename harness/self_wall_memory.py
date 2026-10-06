"""Stage D: the robot's own wall map in its LLM memory. OPTIONS, both default OFF. Refs #216.

Design ``docs/design/2026-10-05-ego-wall-map-for-llm-memory.md`` stage D, §3.5: ``Memory.observe()`` takes ``self_walls``
in the observation dict, ``snapshot()`` carries it next to ``observations`` / ``peer_reports``, and a peer's claim about a
wall never overwrites it ("Peer assertions never overwrite directly measured object facts").

``harness/coela_modules.py`` and ``harness/coela_runtime.py`` are hash-pinned
(``tests/fixtures/rgb_communication_audit/source_manifest.json``), so this is an additive subclass, not an edit of ``Memory``.
Nothing constructs it yet: ``coela_runtime.py`` builds ``Memory(r)`` itself. Wiring it in means changing that pinned file
(or the manifest with it); that is a separate, explicit step.

Options, constructor keywords, defaults OFF:

  ``self_walls_enabled``  keep ``observation['self_walls']`` records and put ``self_walls`` in ``snapshot()``.
  ``self_walls_text``     additionally put ``self_walls_text`` (the LLM wording) in ``snapshot()``; needs the option above.
  ``self_walls_text_height``  print each face's measured height ``h`` in that wording (needs ``self_walls_text``). Off: the
                          records keep ``h`` but the wording leaves it out, because the measured height is not yet reliable
                          (README: a 0.40 m wall reads 0.08-0.13 m in the search pose where its top is out of frame or at a
                          door edge).

With both off the object behaves exactly as ``Memory``: ``observe`` ignores ``self_walls`` and ``snapshot()`` is
byte-identical to ``Memory.snapshot()`` (tested).

A record is what ``experiments/2026-10-05-ego-wall-map-probe/code/ego_wall_map.py`` writes:
``{'t_sim', 'seg': [(r1, th1, r2, th2, h), ...], 'posture', 'load', 'view_index'}``, coordinates in the robot's frame at
``t_sim`` (r metres from the chassis origin, th radians counter-clockwise from forward). Geometry only: no wall names, no
map pose, no fusion; repeated sightings are kept (the same ``(t_sim, view_index)`` seen twice is one record: ``observe`` may
be called again with the same observation).
"""
from __future__ import annotations

import copy
import math

from harness.coela_modules import Memory

MAX_SEGMENTS_PER_RECORD = 16


def _num(x, name):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(f"INVALID_SELF_WALL_RECORD: {name}")
    return float(x)


def validate_record(record):
    """The record as a plain dict, or ``ValueError('INVALID_SELF_WALL_RECORD: ...')``."""
    if not isinstance(record, dict):
        raise ValueError("INVALID_SELF_WALL_RECORD: not a dict")
    t = _num(record.get("t_sim"), "t_sim")
    seg = record.get("seg")
    if not isinstance(seg, (list, tuple)) or not seg or len(seg) > MAX_SEGMENTS_PER_RECORD:
        raise ValueError("INVALID_SELF_WALL_RECORD: seg")
    out = []
    for s in seg:
        if not isinstance(s, (list, tuple)) or len(s) != 5:
            raise ValueError("INVALID_SELF_WALL_RECORD: segment")
        r1, th1, r2, th2 = (_num(s[i], "segment") for i in range(4))
        if r1 < 0 or r2 < 0 or abs(th1) > math.pi + 1e-6 or abs(th2) > math.pi + 1e-6:
            raise ValueError("INVALID_SELF_WALL_RECORD: segment range")
        out.append((r1, th1, r2, th2, None if s[4] is None else _num(s[4], "height")))
    if not isinstance(record.get("posture"), str) or not isinstance(record.get("load"), bool) \
            or isinstance(record.get("view_index"), bool) or not isinstance(record.get("view_index"), int):
        raise ValueError("INVALID_SELF_WALL_RECORD: posture/load/view_index")
    return {"t_sim": t, "seg": out, "posture": record["posture"], "load": record["load"],
            "view_index": record["view_index"]}


def select_for_text(records, max_obs=6, min_gap_s=2.0):
    """Newest first, at most ``max_obs`` records, each at least ``min_gap_s`` of sim time older than the previous pick."""
    picked = []
    for r in sorted(records, key=lambda r: (r["t_sim"], r["view_index"]), reverse=True):
        if not picked or picked[-1]["t_sim"] - r["t_sim"] >= min_gap_s:
            picked.append(r)
        if len(picked) >= max_obs:
            break
    return picked


def render_self_walls(records, now=None, max_obs=6, min_gap_s=2.0, max_segments=4, show_height=False):
    """LLM wording of the own wall observations. ``now`` (sim time) adds each observation's age.

    ``self_walls (own camera; ego frame at each t: distance in metres, angle in degrees, 0 = straight ahead, positive =
    left; wall base lines): 2 observations | t=14.8 (age 1.0s) [high, carrying] 1.2m @ 88° → 1.2m @ 70° | ...``
    ``show_height`` appends `` h=0.40`` to a face whose height was measured.
    """
    picked = select_for_text(records, max_obs, min_gap_s)
    if not picked:
        return "self_walls: no wall observed yet"
    head = ("self_walls (own camera; ego frame at each t: distance in metres, angle in degrees, 0 = straight ahead, positive = "
            f"left; wall base lines{'; h = measured height' if show_height else ''}): {len(picked)} observations")
    parts = []
    for r in picked:
        age = "" if now is None else f" (age {max(0.0, now - r['t_sim']):.1f}s)"
        segs = " ; ".join(
            f"{s[0]:.1f}m @ {math.degrees(s[1]):.0f}° → {s[2]:.1f}m @ {math.degrees(s[3]):.0f}°"
            + (f" h={s[4]:.2f}" if show_height and s[4] is not None else "") for s in r["seg"][:max_segments])
        more = len(r["seg"]) - max_segments
        parts.append(f"t={r['t_sim']:.1f}{age} [{r['posture']}, {'carrying' if r['load'] else 'not carrying'}] {segs}"
                     + (f" ; +{more} more" if more > 0 else ""))
    return head + " | " + " | ".join(parts)


class SelfWallMemory(Memory):
    def __init__(self, robot_id, *, self_walls_enabled=False, self_walls_text=False, self_walls_text_height=False,
                 snapshot_records=12, text_max_obs=6, text_min_gap_s=2.0, **kwargs):
        super().__init__(robot_id, **kwargs)
        if self_walls_text and not self_walls_enabled:
            raise ValueError("SELF_WALLS_TEXT_NEEDS_SELF_WALLS_ENABLED")
        if self_walls_text_height and not self_walls_text:
            raise ValueError("SELF_WALLS_TEXT_HEIGHT_NEEDS_SELF_WALLS_TEXT")
        self.self_walls_enabled = bool(self_walls_enabled)
        self.self_walls_text = bool(self_walls_text)
        self.self_walls_text_height = bool(self_walls_text_height)
        self.snapshot_records = int(snapshot_records)
        self.text_max_obs, self.text_min_gap_s = int(text_max_obs), float(text_min_gap_s)
        self.self_walls = []
        self._self_wall_keys = set()
        self._sim_time = None

    def observe(self, observation, sim_time):
        super().observe(observation, sim_time)
        if not self.self_walls_enabled:
            return
        self._sim_time = observation.get("sim_time", sim_time)
        for raw in observation.get("self_walls", []):
            rec = validate_record(raw)
            key = (rec["t_sim"], rec["view_index"])
            if key not in self._self_wall_keys:
                self._self_wall_keys.add(key)
                self.self_walls.append(rec)

    def snapshot(self):
        snap = super().snapshot()
        if not self.self_walls_enabled:
            return snap
        snap["self_walls"] = copy.deepcopy([self._json(r) for r in self.self_walls[-self.snapshot_records:]])
        if self.self_walls_text:
            snap["self_walls_text"] = render_self_walls(self.self_walls, now=self._sim_time, max_obs=self.text_max_obs,
                                                        min_gap_s=self.text_min_gap_s, show_height=self.self_walls_text_height)
        return snap

    @staticmethod
    def _json(rec):
        return {**rec, "seg": [list(s) for s in rec["seg"]]}
