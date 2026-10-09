"""Own-image OpenCV wall-band observations; no network/learned segmentation.

Reuse the classical markerless probe's undistortion, contrast/uniform-band
detector and measured column geometry. Ambiguous bands and coloured occluders
are discarded, not converted to an absolute pose or labelled from the map.
"""
import copy
import math
import cv2
import numpy as np

from harness import vision_loc_protocol as vp
from harness.own_image_gates import LEGACY
from harness.vision_loc_client import FrameRejected, WorkerFailure

DETECTOR = {'wall_height_m': .40, 'columns': 96, 'strip_half_px': 2}


def edge_step(lum, chroma, v, u):
    """Luminance/chroma step across a candidate boundary at row v, column u (3-row windows, 5-column strip)."""
    a, b = max(0, int(u)-2), int(u)+3
    return math.hypot(lum[v+1:v+4, a:b].mean() - lum[v-3:v, a:b].mean(),
                      chroma[v+1:v+4, a:b].mean() - chroma[v-3:v, a:b].mean())


def observations(vl, bgr, camera, gates=None):
    """``gates``: own_image_gates ``values`` (None keeps the pre-2026-10-03 values: S >= 80, no step test)."""
    gates = LEGACY if gates is None else gates
    und = vl.mp.undistort(bgr)
    scan = vl.mp.detect_boundaries(und, camera, DETECTOR)
    # Saturated cargo/robot faces are not uniform grey walls. A potential
    # wall band touching them is withheld. No scene masks or GT labels.
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    saturated = cv2.dilate(cv2.inRange(hsv, (0, int(gates['wall_band_saturation_max']), 30), (179, 255, 255)),
                          np.ones((5, 5), np.uint8)) > 0
    step_min = float(gates['wall_edge_step_min'])
    if step_min > 0:       # a wall/floor boundary has a real step; a shading gradient does not
        img = und.astype(np.float32)
        lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
        chroma = img[..., 0] - img[..., 2]
    n = len(scan.columns)
    bk, tk = np.zeros(n, int), np.zeros(n, int)
    bottom, top = np.full(n, np.nan), np.full(n, np.nan)
    for j, u in enumerate(scan.columns):
        candidates = np.flatnonzero(np.isfinite(scan.vb[j]))
        if len(candidates) != 1:
            continue
        k = candidates[0]
        b, t = scan.vb[j, k], scan.vt[j, k]
        if step_min > 0:
            row = int(round(b))
            if row < 4 or row > 470 or edge_step(lum, chroma, row, u) < step_min:
                continue
        lo, hi = max(0, int(t)-3) if np.isfinite(t) else 0, min(480, int(b)+4)
        if saturated[lo:hi, max(0, int(u)-2):int(u)+3].any():
            continue
        bk[j], bottom[j] = vl.EDGE, b
        if np.isfinite(t):
            tk[j], top[j] = vl.EDGE, t
    return vl.ColumnObs(scan.columns.copy(), bk, bottom, bottom.copy(), tk, top, top.copy())


class OpenCVObserver:
    def __init__(self, vl, camera, gates=None):
        self.vl, self.camera, self.gates, self.calls, self.closed = vl, camera, gates, 0, False

    def observe(self, bgr):
        if self.closed:
            raise WorkerFailure('OpenCV observer closed')
        try:
            vp.check_frame(bgr)
        except vp.ProtocolError as exc:
            raise FrameRejected(str(exc)) from exc
        self.calls += 1
        try:
            return observations(self.vl, bgr, self.camera(), self.gates)
        except (ValueError, cv2.error) as exc:
            raise WorkerFailure(str(exc)) from exc

    def record(self):
        return {'backend': 'opencv_classical_wall_band_v1', 'learned_segmentation': False,
                'model_calls': 0, 'frames': self.calls, 'closed': self.closed,
                'opencv_version': cv2.__version__, 'detector': copy.deepcopy(DETECTOR),
                'own_image_gates': copy.deepcopy(self.gates if self.gates is not None else LEGACY)}

    def close(self):
        self.closed = True
