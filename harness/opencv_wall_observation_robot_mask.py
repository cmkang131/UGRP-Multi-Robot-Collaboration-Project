"""Opt-in own-RGB robot mask, separate from the frozen wall observer.

The legacy module is an S2 source-hash dependency. Resolve its observations at
call time so the existing exact memo installation remains effective.
"""
import copy

import cv2
import numpy as np

from harness import opencv_wall_observation as legacy
from harness import vision_loc_protocol as vp
from harness.vision_loc_client import FrameRejected, WorkerFailure

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
    obs = legacy.observations(vl, bgr, camera, gates)
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


class OpenCVObserver(legacy.OpenCVObserver):
    def __init__(self, vl, camera, gates=None, *, robot_mask=None):
        if robot_mask not in (None, ROBOT_MASK):
            raise ValueError(f'unknown robot_mask: {robot_mask!r}')
        super().__init__(vl, camera, gates)
        self.robot_mask = robot_mask

    def observe(self, bgr):
        if self.robot_mask is None:
            return super().observe(bgr)
        if self.closed:
            raise WorkerFailure('OpenCV observer closed')
        try:
            vp.check_frame(bgr)
        except vp.ProtocolError as exc:
            raise FrameRejected(str(exc)) from exc
        self.calls += 1
        try:
            return masked_observations(self.vl, bgr, self.camera(), self.gates, robot_mask=self.robot_mask)
        except (ValueError, cv2.error) as exc:
            raise WorkerFailure(str(exc)) from exc

    def record(self):
        result = super().record()
        if self.robot_mask is not None:
            result['robot_mask'] = {'profile': self.robot_mask, 'config': copy.deepcopy(ROBOT_MASK_CONFIG),
                                    'input': 'own_rgb_only', 'scope': 'offline_candidate_not_admitted'}
        return result
