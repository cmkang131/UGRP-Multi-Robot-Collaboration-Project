"""Own traversed footprint layer, default off via reference-route installer.

Reuse the Nav2 convexFillCells port in public_navigation_unknown. Each recorded
own pose clears its body polygon; history is retained for return planning only.
No future waypoint, interpolation across a pose jump, GT, or static map is used.
This is body-support provenance, never RGB wall coverage or localization input.
"""
import math
from types import SimpleNamespace
import numpy as np
from harness.active_wall_mapping import compose
from harness.public_navigation_unknown import footprint_cells
from harness.public_navigation.costmap import Costmap

OPTION = 'footprint_history_v1'


class TraversedFree:
    def __init__(self):
        self.poses = {}
        self._key = None
        self._seen = set()
        self._cells = set()
        self._report = dict(option=OPTION, source='own_pose_history', poses=0, cells=0)

    @classmethod
    def from_graph(cls, graph):
        result = cls()
        for node in graph.nodes:
            result.add(node['pose'], node['frame_id'])
        for edge in graph.edges:
            for row in edge['samples']:
                result.add(row['pose'], row['frame_id'])
        for row in graph.pending:
            result.add(row['pose'], row['frame_id'])
        return result

    def add(self, pose, frame_id):
        pose = np.asarray(pose, float)
        if pose.shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('FINITE_OWN_POSE_REQUIRED')
        key = int(frame_id)
        if key in self.poses and self.poses[key] != tuple(pose):
            self._key = None
        self.poses[key] = tuple(pose)

    def overlay(self, observed, map_to_odom):
        resolution = observed.resolution
        key = (*map(float, map_to_odom), resolution)
        if key != self._key:
            self._key, self._seen, self._cells = key, set(), set()
        grid = SimpleNamespace(cell=lambda p: tuple(np.floor(np.asarray(p)/resolution).astype(int)))
        for frame in self.poses.keys()-self._seen:
            self._cells.update(footprint_cells(grid, compose(map_to_odom, self.poses[frame])))
            self._seen.add(frame)
        if not self._cells:
            return Costmap(observed.raw.copy(), observed.origin, resolution)
        cells = np.asarray(sorted(self._cells), int)
        base = np.rint(observed.origin/resolution).astype(int)
        lo = np.minimum(base, cells.min(0))
        hi = np.maximum(base+observed.raw.shape[::-1]-1, cells.max(0))
        raw = np.full(tuple((hi-lo+1)[::-1]), 255, np.uint8)
        x, y = base-lo
        raw[y:y+observed.raw.shape[0], x:x+observed.raw.shape[1]] = observed.raw
        xy = cells-lo
        old = raw[xy[:,1], xy[:,0]].copy()
        raw[xy[:,1], xy[:,0]] = 0
        self._report = dict(option=OPTION, source='own_pose_history', poses=len(self.poses), cells=len(cells),
                            cleared_unknown=int((old==255).sum()), cleared_occupied=int((old==254).sum()))
        return Costmap(raw, lo*resolution, resolution)

    def diagnostics(self):
        return dict(self._report, poses=len(self.poses))
