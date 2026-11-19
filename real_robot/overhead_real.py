"""Real ceiling camera -> robot poses, with the same top cards as the simulator (harness/overhead_v1.py).

The simulator reader assumes an ideal pinhole camera at a known place. A real camera has lens
distortion and is never mounted exactly, so here both are measured once after installing:

1. intrinsics from about 15 checkerboard photos (`calibrate_intrinsics`);
2. camera pose from one photo of at least 4 floor cards whose centres were taped at measured
   arena coordinates (`calibrate_pose`).

Floor cards and the start (sync) card use another ArUco dictionary (5x5) than the robot cards
(4x4, ids 40..48) and the destination signs, so they can never be read as a robot.

Reading: each corner of a robot card becomes a ray that is cut at the card height
(base height + card height above the base, overhead_v1.BASE_Z + CARD_AT[2]). The top edge
(corner 0 -> 1) is the heading, and the base origin is CARD_AT[0] behind the card centre,
exactly as overhead_v1.OverheadReader does. Used for evaluation only, never as a robot input
unless the execution layer reads it the same way it does in the simulator.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from harness import overhead_v1 as ov

FLOOR_DICT = 'DICT_5X5_50'   # floor calibration cards and the start card
SYNC_CARD_ID = 49            # start card in FLOOR_DICT: shown to the ceiling camera and the phone at the start
ROBOT_DICT = 'DICT_4X4_50'   # same as overhead_v1.OverheadReader
CARD_PLANE_Z = ov.BASE_Z + ov.CARD_AT[2]


def _aruco(dict_name):
    import cv2
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name)),
                                   cv2.aruco.DetectorParameters())


def _gray(img):
    import cv2
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def calibrate_intrinsics(images, board=(9, 6), square_m=0.025):
    """Checkerboard photos -> (camera matrix, distortion, rms px). `board` = inner corners."""
    import cv2
    obj = np.zeros((board[0] * board[1], 3), np.float32)
    obj[:, :2] = np.mgrid[0:board[0], 0:board[1]].T.reshape(-1, 2) * square_m
    objs, pts, size = [], [], None
    for img in images:
        g = _gray(img)
        size = g.shape[::-1]
        ok, c = cv2.findChessboardCorners(g, board)
        if ok:
            c = cv2.cornerSubPix(g, c, (11, 11), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3))
            objs.append(obj)
            pts.append(c)
    if len(objs) < 5:
        raise ValueError(f'checkerboard found in {len(objs)} photos; need at least 5')
    rms, K, dist, _, _ = cv2.calibrateCamera(objs, pts, size, None, None)
    return K, dist.ravel(), float(rms), len(objs)


def calibrate_pose(image, K, dist, floor_cards):
    """One photo + {card id: (x, y)} measured floor positions (arena frame, z = 0) -> rvec, tvec, rms px."""
    import cv2
    K, dist = np.asarray(K, np.float64), np.asarray(dist, np.float64)
    corners, ids, _ = _aruco(FLOOR_DICT).detectMarkers(_gray(image))
    seen = {} if ids is None else {int(i): c.reshape(4, 2).mean(axis=0) for c, i in zip(corners, ids.ravel())}
    use = [i for i in floor_cards if i in seen]
    if len(use) < 4:
        raise ValueError(f'floor cards seen: {sorted(seen)}; need at least 4 of {sorted(floor_cards)}')
    obj = np.array([[*floor_cards[i], 0.] for i in use], np.float64)
    img = np.array([seen[i] for i in use], np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError('solvePnP failed')
    proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    rms = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, axis=1))))
    return rvec.ravel(), tvec.ravel(), rms, use


class Camera:
    def __init__(self, K, dist, rvec, tvec):
        import cv2
        self.K, self.dist = np.asarray(K, float), np.asarray(dist, float)
        R, _ = cv2.Rodrigues(np.asarray(rvec, float))
        self.Rt = R.T
        self.center = -R.T @ np.asarray(tvec, float)

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text())
        if not d.get('measured'):
            raise ValueError(f'{path}: not a measured ceiling calibration')
        return cls(d['camera_matrix'], d['dist'], d['rvec'], d['tvec'])

    def to_plane(self, px, z):
        """Image pixels (N, 2) -> arena points (N, 2) on the plane at height z."""
        import cv2
        n = cv2.undistortPoints(np.asarray(px, np.float64).reshape(-1, 1, 2), self.K, self.dist).reshape(-1, 2)
        rays = (self.Rt @ np.c_[n, np.ones(len(n))].T).T
        s = (z - self.center[2]) / rays[:, 2]
        return (self.center + s[:, None] * rays)[:, :2]


class RealOverheadReader:
    """Ceiling picture -> {robot: (x, y, yaw)}, plus whether the start card is in view."""

    def __init__(self, camera: Camera):
        self.camera = camera
        self.robots = _aruco(ROBOT_DICT)
        self.floor = _aruco(FLOOR_DICT)

    def read(self, img):
        g = _gray(img)
        out = {}
        corners, ids, _ = self.robots.detectMarkers(g)
        for q, n in zip(corners, [] if ids is None else ids.ravel().tolist()):
            if not ov.TOP_ID0 <= n < ov.TOP_ID0 + 9:
                continue
            w = self.camera.to_plane(q.reshape(4, 2), CARD_PLANE_Z)
            # heading = top edge direction (corner 0 -> 1, as overhead_v1). All four edges are averaged: on a
            # ~20 px marker one edge alone moves by about 3 deg with one pixel of corner error.
            c = w.mean(axis=0)
            f = (w[1] - w[0]) + (w[2] - w[3])
            up = (w[0] - w[3]) + (w[1] - w[2])
            v = f + np.array([up[1], -up[0]])
            yaw = math.atan2(v[1], v[0]) + ov.YAW_OFFSET
            yaw = math.atan2(math.sin(yaw), math.cos(yaw))
            x, y = c[0] - ov.CARD_AT[0] * math.cos(yaw), c[1] - ov.CARD_AT[0] * math.sin(yaw)
            side_m = float(np.mean([np.linalg.norm(w[i] - w[(i + 1) % 4]) for i in range(4)]))
            out['r%d' % (n - ov.TOP_ID0 + 1)] = (float(x), float(y), float(yaw), side_m)
        _, fids, _ = self.floor.detectMarkers(g)
        sync = fids is not None and SYNC_CARD_ID in fids.ravel().tolist()
        return out, sync
