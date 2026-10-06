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


ROBOT_MASK = 'orange_columns_v1'
ROBOT_MASK_CONFIG = {'hsv_lower': [5, 100, 60], 'hsv_upper': [25, 255, 255],
                     'open_px': 3, 'dilate_px': 5, 'close_columns_px': 31}


def robot_occluded_columns(und):
    """Conservative VGA RGB-only orange-appearance exclusion, not robot recognition.

    OpenCV HSV inRange -> opening -> dilation -> column projection -> closing.
    The projection withholds the entire column; closing bridges small dark gaps
    between orange parts. No inpainting, pose, map, depth or peer state is used.
    Orange scenery can also be withheld; uncoloured/large dark gaps can survive.
    Profile and sources: experiments/2026-10-06-owncam-robot-mask/README.md.
    """
    vp.check_frame(und)
    cfg = ROBOT_MASK_CONFIG
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, tuple(cfg['hsv_lower']), tuple(cfg['hsv_upper']))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                          np.ones((cfg['open_px'], cfg['open_px']), np.uint8))
    mask = cv2.dilate(mask, np.ones((cfg['dilate_px'], cfg['dilate_px']), np.uint8))
    columns = mask.max(axis=0, keepdims=True)
    # Explicit padding keeps closing from inventing an orange region at an edge.
    pad = cfg['close_columns_px']
    padded = np.pad(columns, ((0, 0), (pad, pad)))
    closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, np.ones((1, pad), np.uint8))
    return closed[0, pad:-pad] > 0


def masked_observations(vl, bgr, camera, gates=None, *, robot_mask=None):
    """Explicit opt-in wrapper; the legacy observer stays byte-identical.

    None uses precisely the original path, including its optional exact memo.
    The enabled path only turns observations into NONE, never a fabricated wall.
    """
    if robot_mask not in (None, ROBOT_MASK):
        raise ValueError(f'unknown robot_mask: {robot_mask!r}')
    obs = observations(vl, bgr, camera, gates)
    if robot_mask is None:
        return obs
    excluded = robot_occluded_columns(vl.mp.undistort(bgr))
    drop = np.array([excluded[max(0, int(u)-2):int(u)+3].any() for u in obs.columns])
    result = copy.deepcopy(obs)
    for kind in ('b_kind', 't_kind'):
        getattr(result, kind)[drop] = 0       # VIS3 NONE: no measurement, not free space
    for bound in ('b_lo', 'b_hi', 't_lo', 't_hi'):
        getattr(result, bound)[drop] = np.nan
    return result


class OpenCVObserver:
    def __init__(self, vl, camera, gates=None, *, robot_mask=None):
        if robot_mask not in (None, ROBOT_MASK):
            raise ValueError(f'unknown robot_mask: {robot_mask!r}')
        self.robot_mask = robot_mask
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
            if self.robot_mask is None:
                return observations(self.vl, bgr, self.camera(), self.gates)
            return masked_observations(self.vl, bgr, self.camera(), self.gates, robot_mask=self.robot_mask)
        except (ValueError, cv2.error) as exc:
            raise WorkerFailure(str(exc)) from exc

    def record(self):
        result = {'backend': 'opencv_classical_wall_band_v1', 'learned_segmentation': False,
                'model_calls': 0, 'frames': self.calls, 'closed': self.closed,
                'opencv_version': cv2.__version__, 'detector': copy.deepcopy(DETECTOR),
                'own_image_gates': copy.deepcopy(self.gates if self.gates is not None else LEGACY)}
        if self.robot_mask is not None:
            result['robot_mask'] = {'profile': self.robot_mask, 'config': copy.deepcopy(ROBOT_MASK_CONFIG),
                                    'input': 'own_rgb_only', 'scope': 'offline_candidate_not_admitted'}
        return result

    def close(self):
        self.closed = True
