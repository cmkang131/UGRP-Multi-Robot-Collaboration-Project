"""Own-image OpenCV wall-band observations; no network/learned segmentation.

Reuse the classical markerless probe's undistortion, contrast/uniform-band
detector and measured column geometry. Ambiguous bands and coloured occluders
are discarded, not converted to an absolute pose or labelled from the map.
"""
import copy
import cv2
import numpy as np

from harness import vision_loc_protocol as vp
from harness.vision_loc_client import FrameRejected, WorkerFailure

DETECTOR = {'wall_height_m': .40, 'columns': 96, 'strip_half_px': 2}


def observations(vl, bgr, camera):
    und = vl.mp.undistort(bgr)
    scan = vl.mp.detect_boundaries(und, camera, DETECTOR)
    # Saturated cargo/robot faces are not uniform grey walls. A potential
    # wall band touching them is withheld. No scene masks or GT labels.
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    saturated = cv2.dilate(cv2.inRange(hsv, (0, 80, 30), (179, 255, 255)),
                          np.ones((5, 5), np.uint8)) > 0
    n = len(scan.columns)
    bk, tk = np.zeros(n, int), np.zeros(n, int)
    bottom, top = np.full(n, np.nan), np.full(n, np.nan)
    for j, u in enumerate(scan.columns):
        candidates = np.flatnonzero(np.isfinite(scan.vb[j]))
        if len(candidates) != 1:
            continue
        k = candidates[0]
        b, t = scan.vb[j, k], scan.vt[j, k]
        lo, hi = max(0, int(t)-3) if np.isfinite(t) else 0, min(480, int(b)+4)
        if saturated[lo:hi, max(0, int(u)-2):int(u)+3].any():
            continue
        bk[j], bottom[j] = vl.EDGE, b
        if np.isfinite(t):
            tk[j], top[j] = vl.EDGE, t
    return vl.ColumnObs(scan.columns.copy(), bk, bottom, bottom.copy(), tk, top, top.copy())


class OpenCVObserver:
    def __init__(self, vl, camera):
        self.vl, self.camera, self.calls, self.closed = vl, camera, 0, False

    def observe(self, bgr):
        if self.closed:
            raise WorkerFailure('OpenCV observer closed')
        try:
            vp.check_frame(bgr)
        except vp.ProtocolError as exc:
            raise FrameRejected(str(exc)) from exc
        self.calls += 1
        try:
            return observations(self.vl, bgr, self.camera())
        except (ValueError, cv2.error) as exc:
            raise WorkerFailure(str(exc)) from exc

    def record(self):
        return {'backend': 'opencv_classical_wall_band_v1', 'learned_segmentation': False,
                'model_calls': 0, 'frames': self.calls, 'closed': self.closed,
                'opencv_version': cv2.__version__, 'detector': copy.deepcopy(DETECTOR)}

    def close(self):
        self.closed = True
