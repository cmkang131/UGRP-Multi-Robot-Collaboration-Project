"""Stage D: the robot's own wall map in its LLM memory. OPTIONS, both default OFF. Refs #216.

Design ``docs/design/2026-10-05-ego-wall-map-for-llm-memory.md`` stage D, §3.5: ``Memory.observe()`` takes ``self_walls``
in the observation dict, ``snapshot()`` carries it next to ``observations`` / ``peer_reports``, and a peer's claim about a
wall never overwrites it ("Peer assertions never overwrite directly measured object facts").

``harness/coela_modules.py`` and ``harness/coela_runtime.py`` are hash-pinned
(``tests/fixtures/rgb_communication_audit/source_manifest.json``), so this is an additive subclass, not an edit of ``Memory``.
``coela_runtime.py`` builds ``Memory(r)`` itself and is not edited: ``harness/coela_runtime_self_walls.py`` runs it with this
class in place of ``Memory`` when the option ``self_wall_memory=on_v1`` is given (default ``off``: the pinned runtime, untouched).

Options, constructor keywords, defaults OFF:

  ``self_walls_enabled``  keep ``observation['self_walls']`` records and put ``self_walls`` in ``snapshot()``.
  ``self_walls_text``     additionally put ``self_walls_text`` (the LLM wording) in ``snapshot()``; needs the option above.
  ``self_walls_source``   optional ``callable(robot_id) -> iterable of records``, polled on every ``observe()`` (the runtime's
                          observation carries no wall data; this is where the stage C map reaches the memory). Needs
                          ``self_walls_enabled``; with the option off it is never called.
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
                 snapshot_records=12, text_max_obs=6, text_min_gap_s=2.0, self_walls_source=None,
                 self_map="off", self_map_options=None, pose_correction="off", pose_correction_options=None,
                 wall_projection_guard="off", pose_graph="off", pose_graph_options=None,
                 goal_detection="off", goal_detection_options=None, **kwargs):
        super().__init__(robot_id, **kwargs)
        if self_map not in ("off", "odom_grid_v1"):
            raise ValueError("UNKNOWN_SELF_MAP")
        if pose_correction not in ("off", "own_map_csm_v1", "own_map_csm_v2", "own_map_csm_prob_v1", "own_map_rbpf_v1"):
            raise ValueError("UNKNOWN_POSE_CORRECTION")
        if pose_correction != "off" and self_map != "odom_grid_v1":
            raise ValueError("POSE_CORRECTION_NEEDS_SELF_MAP")
        from harness.wall_projection_guard import validate_option
        validate_option(wall_projection_guard)
        if wall_projection_guard != "off" and self_map != "odom_grid_v1":
            raise ValueError("WALL_PROJECTION_GUARD_NEEDS_SELF_MAP")
        self.wall_projection_guard = wall_projection_guard
        self.projection_guard_events = []
        if pose_graph not in ("off", "own_submap_v1"):
            raise ValueError("UNKNOWN_POSE_GRAPH")
        if pose_graph != "off" and (self_map != "odom_grid_v1" or wall_projection_guard != "positive_depth_v1" or
                pose_correction not in ("own_map_rbpf_v1", "own_map_csm_prob_v1")):
            raise ValueError("POSE_GRAPH_NEEDS_GUARDED_RBPF_OR_PROB")
        self.pose_graph = pose_graph
        self.pose_graph_options = pose_graph_options
        self.pose_graph_result = None
        self._graph_view = None
        if pose_graph != "off":
            from harness.self_pose_graph import GraphOptions
            GraphOptions(**(pose_graph_options or {}))
        self.self_map = None
        if self_map == "odom_grid_v1":
            if pose_correction == "off":
                from harness.self_odom_grid import OdomGrid
                self.self_map = OdomGrid(robot_id, **(self_map_options or {}))
            elif pose_correction == "own_map_csm_v1":
                from harness.self_map_csm import CorrectedOdomGrid
                self.self_map = CorrectedOdomGrid(robot_id, correction_options=pose_correction_options,
                                                 **(self_map_options or {}))
            elif pose_correction == "own_map_csm_v2":
                from harness.self_map_csm_v2 import CorrectedOdomGridV2
                self.self_map = CorrectedOdomGridV2(robot_id, correction_options=pose_correction_options,
                                                   **(self_map_options or {}))
            elif pose_correction == "own_map_csm_prob_v1":
                from harness.self_map_prob import ProbabilisticOdomGrid
                self.self_map = ProbabilisticOdomGrid(robot_id, correction_options=pose_correction_options,
                                                     **(self_map_options or {}))
            else:
                from harness.self_map_rbpf import RaoBlackwellizedGrid
                self.self_map = RaoBlackwellizedGrid(robot_id, correction_options=pose_correction_options,
                                                     **(self_map_options or {}))
        if self_walls_source is not None and not self_walls_enabled:
            raise ValueError("SELF_WALLS_SOURCE_NEEDS_SELF_WALLS_ENABLED")
        if self_walls_text and not self_walls_enabled:
            raise ValueError("SELF_WALLS_TEXT_NEEDS_SELF_WALLS_ENABLED")
        if self_walls_text_height and not self_walls_text:
            raise ValueError("SELF_WALLS_TEXT_HEIGHT_NEEDS_SELF_WALLS_TEXT")
        self.self_walls_enabled = bool(self_walls_enabled)
        self.self_walls_text = bool(self_walls_text)
        self.self_walls_text_height = bool(self_walls_text_height)
        self._source = self_walls_source
        self.snapshot_records = int(snapshot_records)
        self.text_max_obs, self.text_min_gap_s = int(text_max_obs), float(text_min_gap_s)
        self.self_walls = []
        self._self_wall_keys = set()
        self._sim_time = None
        if goal_detection not in ("off", "floor_color_v1", "floor_color_v2", "floor_color_v3"):
            raise ValueError("UNKNOWN_GOAL_DETECTION")
        self.self_goal = None
        if goal_detection != "off":
            if self.self_map is None:
                raise ValueError("GOAL_DETECTION_NEEDS_SELF_MAP")
            if goal_detection == "floor_color_v3":
                from harness.floor_goal_v3 import FloorGoalMemoryV3
                self.self_goal = FloorGoalMemoryV3(robot_id, options=goal_detection_options)
            elif goal_detection == "floor_color_v2":
                from harness.floor_goal_v2 import FloorGoalMemoryV2
                self.self_goal = FloorGoalMemoryV2(robot_id, options=goal_detection_options)
            else:
                from harness.floor_goal import FloorGoalMemory
                self.self_goal = FloorGoalMemory(robot_id, options=goal_detection_options)

    def observe(self, observation, sim_time):
        super().observe(observation, sim_time)
        if not self.self_walls_enabled:
            return
        self._sim_time = observation.get("sim_time", sim_time)
        records = list(observation.get("self_walls", []))
        if self._source is not None:
            records += list(self._source(self.robot_id))
        for raw in records:
            rec = validate_record(raw)
            key = (rec["t_sim"], rec["view_index"])
            if key not in self._self_wall_keys:
                self._self_wall_keys.add(key)
                self.self_walls.append(rec)

    def command(self, row):
        """Issued own command; inert with self_map off. Feed in timestamp order."""
        if self.self_map is not None:
            self._graph_view = self.pose_graph_result = None
            self.self_map.odom.command(row)

    def observe_goal_rgb(self, rgb, *, robot_id, frame_id, t, commanded_servo, camera_profile):
        """Offline D input boundary: own RGB/issued arm commands and own map pose.

        Default off is inert, including invalid inputs. No static/GT/peer inputs.
        Replayed graph revisions of older goal patches are outside floor_color_v1.
        """
        if self.self_goal is None:
            return None
        if robot_id != self.robot_id:
            raise ValueError("GOAL_PEER_INPUT_FORBIDDEN")
        if frame_id in self.self_goal.seen or t <= self.self_goal.last_t:
            raise ValueError("GOAL_DUPLICATE_OR_NON_MONOTONIC_FRAME")
        odom = self.self_map.odom
        pose = odom.advance(t)
        settled = odom.has_servo and t-odom.servo_since+1e-8 >= (.25, 2.25)[int(odom.loaded)]
        return self.self_goal.observe(rgb, robot_id=robot_id, frame_id=frame_id, t=t, pose=pose,
                                      servo=commanded_servo, profile=camera_profile, settled=settled)

    def goal_target(self, static_goal):
        """Off returns the unchanged static goal; on never falls back on unknown."""
        return static_goal if self.self_goal is None else self.self_goal.snapshot()

    def observe_wall(self, record, *, camera_xy, robot_id, camera_origin=None, camera_rotation=None):
        """Own C record and camera geometry, no peer/GT.

        positive_depth_v1 requires command-calibrated 3D origin and optical-to-
        chassis rotation. It filters BEFORE matching/insertion, including free
        rays. Default off delegates byte-for-byte to the legacy map path.
        """
        if self.self_map is not None:
            self._graph_view = self.pose_graph_result = None
            if self.wall_projection_guard != "off":
                import numpy as np
                from harness.wall_projection_guard import filter_segments
                if robot_id != self.self_map.robot_id:
                    raise ValueError("SELF_MAP_PEER_INPUT_FORBIDDEN")
                rec = validate_record(record)
                key = (rec["t_sim"], rec["view_index"])
                if key in self.self_map.seen:
                    return []
                local = [[[r1*math.cos(a1), r1*math.sin(a1)], [r2*math.cos(a2), r2*math.sin(a2)]]
                         for r1, a1, r2, a2, _ in rec["seg"]]
                kept, event = filter_segments(local, wall_projection_guard=self.wall_projection_guard,
                                              camera_origin=camera_origin, camera_rotation=camera_rotation)
                if not np.allclose(np.asarray(camera_origin, float)[:2], camera_xy, atol=1e-8, rtol=0):
                    raise ValueError("WALL_PROJECTION_CAMERA_FRAME_MISMATCH")
                event.update(t=rec["t_sim"], frame_id=rec["view_index"])
                self.projection_guard_events.append(event)
                if not kept:
                    self.self_map.odom.advance(rec["t_sim"])
                    self.self_map.seen.add(key)
                    return []
                record = {**rec, "seg": [rec["seg"][e["segment"]] for e in event["segments"] if e["accepted"]]}
            return self.self_map.observe(record, camera_xy=camera_xy, robot_id=robot_id)
        return []

    def finalize_pose_graph(self, poses=None):
        """Explicit offline finalization; never feed global correction into RBPF.

        Optional full-frame poses must carry this robot's id. With no path, use
        the frontend's final ledger poses. New commands/observations invalidate
        this frozen view; frontend state and RNG are left untouched.
        """
        if self.pose_graph == "off":
            return None
        from harness.self_pose_graph import apply_pose_graph, rebuild
        rows = [{**copy.deepcopy(r), "robot_id": self.robot_id} for r in self.self_map.ledger]
        if poses is None:
            poses = [{"robot_id":self.robot_id,"t":r["t"],"pose":r["pose"]} for r in rows]
        rows, path, diagnostics = apply_pose_graph(rows, poses, robot_id=self.robot_id,
            pose_graph=self.pose_graph, options=self.pose_graph_options)
        self._graph_view = rebuild(self.robot_id, rows)
        if path:
            self._graph_view.odom._predictor.px[0] = path[-1]["pose"]
        self.pose_graph_result = {"ledger": rows, "poses": path, "diagnostics": diagnostics}
        return self.pose_graph_result

    def snapshot(self):
        snap = super().snapshot()
        if self.self_goal is not None:
            snap["self_goal"] = self.self_goal.snapshot()
        if self.self_map is not None:
            snap["self_map_text"] = (self.self_map.text() if self._graph_view is None else
                self._graph_view.text().replace("drift uncorrected", "own submap graph; drift uncertain"))
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
