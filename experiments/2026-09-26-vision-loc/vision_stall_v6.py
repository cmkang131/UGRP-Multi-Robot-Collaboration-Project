"""VIS6 recipe 1c: image-based stall detection (a ZUPT analogue) from two own frames at the same arm pose.

Inputs are robot-owned only: two consecutive own wrist frames (raw fisheye JPEG,
undistorted with the fixed camera model of PR #210), the commanded arm pose (the
camera pose in the base frame from the commanded-PWM FK plus the TRAIN sag table),
the PF's command-integrated predicted base displacement between the two frames,
and optionally the own segmentation column observation of the later frame (only
to keep the test on floor pixels below the observed wall-bottom edge). No
simulator state, ``eval_only/`` or teacher file is read here.

Test. The floor is a plane (z = 0). For a sample of textured floor pixels of the
later frame, the base displacement ``s * delta`` (``delta`` = predicted, s a
fraction on a fixed grid) moves their floor points to a pixel of the earlier
frame; the photometric residual ``r(s)`` = mean |I1 - I0(warp_s)| is computed on
the same point set for every ``s``. ``s* = argmin r``.

* ``stall``: s* <= ``stall_max_scale`` and r(1) - r(s*) clears both the absolute
  (gray levels) and relative contrast thresholds -- the image says the base moved
  much less than the commands predict (1.2 of the literature review: VISW s942
  102-111 s, VIS3 s945 170-205 s).
* ``moving``: s* >= ``moving_min_scale`` and r(0) - r(s*) clears the same contrast.
* ``unknown``: anything else, including too few textured floor points or a
  predicted image motion below ``min_pred_px`` (no power; the uniform zone paint
  and the 0.57 m checker squares leave many frames without floor texture).

The checker floor is periodic, so the test only covers small displacements. The
checker size recorded here is read from the scene source (see ``CHECKER``); one
frame interval at 5 Hz and 0.12 m/s is 2.4 cm, far below the half period.

References: ZUPT (Foxlin 2005, IEEE CG&A 25(6)); visual/kinematic velocity mismatch
for immobilisation detection (Ward & Iagnemma 2008, Autonomous Robots); plane-induced
homography warping (Hartley & Zisserman, Multiple View Geometry, 2nd ed., 13.1).
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import cv2
import numpy as np

import vision_loc as vl

mp = vl.mp

# Checker floor of the environment-v3 scenes, from the scene SOURCE (not a render):
#   sim/masterpi_scene_v2.xml: <texture name="ground" type="2d" builtin="checker" width="256" height="256">,
#     <material name="groundmat" texture="ground" texrepeat="14 14"> (texuniform default false)
#   sim/zone_arena.py (build of the zone scenes): floor.set('size', '8 8 .1')  -> a 16 m x 16 m plane
#   MuJoCo XML reference (doc/XMLreference.rst, material/texuniform): with texuniform false the 2d texture
#   is repeated N = texrepeat times over the object; builtin "checker" is a 2-by-2 checker pattern.
#   Render check: outputs/vision-loc-20260926/render/vl3-dev-s945/scene.xml has the same values.
CHECKER = {
    'plane_side_m': 16.,
    'texrepeat': 14,
    'repeat_m': 16./14,             # one texture image = 2 x 2 squares: 1.142857 m
    'square_m': 8./14,              # 0.571429 m
    'rgb': [[.20, .22, .24], [.27, .29, .31]],
    'source': ['sim/masterpi_scene_v2.xml (ground texture, groundmat)', "sim/zone_arena.py floor size '8 8 .1'",
               'MuJoCo doc/XMLreference.rst asset/material texrepeat, texuniform; asset/texture builtin checker'],
}

DEFAULT_STALL = {
    'scales': [0., .25, .5, .75, 1., 1.25],   # fractions of the predicted displacement tested
    'stall_max_scale': .25,
    'moving_min_scale': .75,
    'min_pred_px': 2.,          # median predicted image shift of the sample points at s = 1
    'min_points': 150,          # textured floor points common to every s
    'max_points': 4000,
    'stride_px': 4,
    'grad_min': 4.,             # Sobel magnitude (gray levels / px, after blur) of a textured point
    'blur_ksize': 5,
    'min_contrast_gray': 1.,    # r(1) - r(s*) (stall) or r(0) - r(s*) (moving), gray levels
    'min_contrast_rel': .15,    # the same difference over the larger residual
    'floor_range_m': [.2, 1.5],  # horizontal distance of the floor point from the camera nadir
    'obs_floor_mask': True,     # keep only rows below the observed wall-bottom edge of the later frame
    'obs_margin_px': 4.,
    'max_dt_s': .45,            # frame pair gap (5 Hz frames: 0.2 s)
    'gain': 1.,                 # share of the predicted displacement removed on 'stall' (1: back to the old pose)
    'velocity_gain': 1.,        # share of the PF velocity state removed on 'stall'
}


def _num(v, name, lo, hi, lo_open=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        raise ValueError(f'{name} must be a finite number, got {v!r}')
    v = float(v)
    if v < lo or v > hi or (lo_open and v <= lo):
        raise ValueError(f'{name}={v!r} outside [{lo}, {hi}]')
    return v


def validate_stall(cfg: Mapping | None) -> dict | None:
    """None (off) or DEFAULT_STALL merged with ``cfg``; unknown keys, bad types and ranges refused."""
    if cfg is None:
        return None
    if not isinstance(cfg, Mapping):
        raise ValueError('stall must be a mapping or null')
    unknown = set(cfg) - set(DEFAULT_STALL)
    if unknown:
        raise ValueError(f'unknown stall options {sorted(unknown)}')
    c = {**DEFAULT_STALL, **cfg}
    sc = c['scales']
    if not isinstance(sc, (list, tuple)) or len(sc) < 3:
        raise ValueError('stall.scales needs at least three values')
    sc = [_num(v, 'stall.scales[]', 0., 3.) for v in sc]
    if sorted(sc) != sc or len(set(sc)) != len(sc) or sc[0] != 0. or 1. not in sc:
        raise ValueError('stall.scales must be increasing, start at 0 and contain 1')
    c['scales'] = sc
    _num(c['stall_max_scale'], 'stall.stall_max_scale', 0., 1.)
    _num(c['moving_min_scale'], 'stall.moving_min_scale', 0., 3.)
    if c['moving_min_scale'] <= c['stall_max_scale']:
        raise ValueError('stall.moving_min_scale must exceed stall_max_scale')
    _num(c['min_pred_px'], 'stall.min_pred_px', 0., 100., lo_open=True)
    for k in ('min_points', 'max_points', 'stride_px', 'blur_ksize'):
        if isinstance(c[k], bool) or not isinstance(c[k], int) or c[k] < 1:
            raise ValueError(f'stall.{k} must be a positive integer')
    if c['blur_ksize'] % 2 == 0:
        raise ValueError('stall.blur_ksize must be odd')
    if c['max_points'] < c['min_points']:
        raise ValueError('stall.max_points must be >= min_points')
    _num(c['grad_min'], 'stall.grad_min', 0., 255.)
    _num(c['min_contrast_gray'], 'stall.min_contrast_gray', 0., 255.)
    _num(c['min_contrast_rel'], 'stall.min_contrast_rel', 0., 1.)
    fr = c['floor_range_m']
    if not isinstance(fr, (list, tuple)) or len(fr) != 2:
        raise ValueError('stall.floor_range_m needs [near, far]')
    fr = [_num(v, 'stall.floor_range_m[]', 0., 10.) for v in fr]
    if fr[1] <= fr[0]:
        raise ValueError('stall.floor_range_m must be increasing')
    c['floor_range_m'] = fr
    if not isinstance(c['obs_floor_mask'], bool):
        raise ValueError('stall.obs_floor_mask must be boolean')
    _num(c['obs_margin_px'], 'stall.obs_margin_px', 0., 100.)
    _num(c['max_dt_s'], 'stall.max_dt_s', 0., 5., lo_open=True)
    _num(c['gain'], 'stall.gain', 0., 1., lo_open=True)
    _num(c['velocity_gain'], 'stall.velocity_gain', 0., 1.)
    return c


def prepare(bgr: np.ndarray, blur_ksize: int = 5) -> np.ndarray:
    """Raw fisheye BGR frame -> undistorted, blurred float32 gray image (invalid pinhole pixels NaN)."""
    gray = cv2.cvtColor(mp.undistort(bgr), cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    gray[~vl.VALID] = np.nan
    return gray


def floor_min_rows(obs, width: int = vl.WIDTH, height: int = vl.HEIGHT, margin_px: float = 4.) -> np.ndarray:
    """First floor row of every image column from an own column observation (``height``: no floor known).

    EDGE / INTERVAL with a finite upper end: floor starts below ``b_hi``; wall down
    to the image bottom (``b_hi`` = POS_INF) or no observation (NONE): no floor.
    Image columns take the value of the nearest observed column.
    """
    cols = np.asarray(obs.columns, float)
    hi = np.asarray(obs.b_hi, float)
    ok = (np.asarray(obs.b_kind) != vl.NONE) & np.isfinite(hi) & (hi < vl.POS_INF/2)
    start = np.where(ok, np.maximum(hi, 0.) + margin_px, float(height))
    u = np.arange(width)
    nearest = np.abs(u[:, None] - cols[None, :]).argmin(1)
    return start[nearest]


def camera_pose(cm) -> tuple[np.ndarray, np.ndarray]:
    """(origin (3,), optical->base rotation (3, 3)) of a PR #210 / VIS3 ``ColumnModel`` (sag, dz, pan yaw applied)."""
    return np.asarray(cm.origin, float), np.asarray(cm._rot, float)


def sample_points(img1: np.ndarray, origin: np.ndarray, rot: np.ndarray, cfg: Mapping,
                  min_rows: np.ndarray | None = None):
    """(u, v, floor xy in the later base frame) of textured floor pixels of ``img1`` (a strided grid)."""
    h, w = img1.shape
    s = int(cfg['stride_px'])
    vv, uu = np.mgrid[s//2:h:s, s//2:w:s]
    u, v = uu.ravel(), vv.ravel()
    g = np.nan_to_num(img1, nan=0.)
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))/8.
    keep = vl.VALID[v, u] & np.isfinite(img1[v, u]) & (mag[v, u] >= float(cfg['grad_min']))
    if min_rows is not None:
        keep &= v >= min_rows[u]
    u, v = u[keep], v[keep]
    ray = rot @ (mp.K_INV @ np.stack([u.astype(float), v.astype(float), np.ones(u.size)]))
    down = ray[2] < -1e-6
    lam = np.where(down, -origin[2]/np.where(down, ray[2], -1.), np.nan)
    q = origin[:2, None] + ray[:2]*lam
    dist = np.hypot(q[0] - origin[0], q[1] - origin[1])
    near, far = cfg['floor_range_m']
    ok = down & (dist >= near) & (dist <= far)
    u, v, q = u[ok], v[ok], q[:, ok].T
    if u.size > int(cfg['max_points']):
        idx = np.linspace(0, u.size - 1, int(cfg['max_points'])).round().astype(int)
        u, v, q = u[idx], v[idx], q[idx]
    return u, v, q


def project(q1: np.ndarray, delta, origin: np.ndarray, rot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pixels in the EARLIER frame of floor points ``q1`` (later base frame), later base pose ``delta`` in the earlier.

    ``delta`` = (dx, dy, dyaw): the later base frame expressed in the earlier one.
    The camera sits at the same pose in both base frames (same commanded arm pose).
    """
    dx, dy, dyaw = (float(x) for x in delta)
    c, s = math.cos(dyaw), math.sin(dyaw)
    q0 = np.column_stack([c*q1[:, 0] - s*q1[:, 1] + dx, s*q1[:, 0] + c*q1[:, 1] + dy, np.zeros(len(q1))])
    cam = (rot.T @ (q0 - origin[None, :]).T)
    z = cam[2]
    with np.errstate(divide='ignore', invalid='ignore'):
        u = np.where(z > 1e-6, mp.FX*cam[0]/z + mp.CX, np.nan)
        v = np.where(z > 1e-6, mp.FY*cam[1]/z + mp.CY, np.nan)
    return u, v


def _bilinear(img: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear samples (NaN outside the image or next to an invalid pixel)."""
    h, w = img.shape
    out = np.full(u.shape, np.nan, np.float64)
    ok = np.isfinite(u) & np.isfinite(v) & (u >= 0) & (v >= 0) & (u <= w - 1.001) & (v <= h - 1.001)
    if not ok.any():
        return out
    x, y = u[ok], v[ok]
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    out[ok] = (a*(1 - fx) + b*fx)*(1 - fy) + (c*(1 - fx) + d*fx)*fy
    return out


def stall_test(img0: np.ndarray, img1: np.ndarray, origin: np.ndarray, rot: np.ndarray, delta, cfg: Mapping,
               min_rows: np.ndarray | None = None) -> dict:
    """Decide stall / moving / unknown for one frame pair (see the module docstring)."""
    u, v, q1 = sample_points(img1, origin, rot, cfg, min_rows)
    out = {'decision': 'unknown', 'reason': None, 'n': int(u.size), 's_star': None, 'pred_px': None,
           'residuals': None}
    if u.size < int(cfg['min_points']):
        out['reason'] = 'few_textured_floor_points'
        return out
    i1 = img1[v, u].astype(np.float64)
    samples = []
    for s in cfg['scales']:
        du, dv = project(q1, [s*float(x) for x in delta], origin, rot)
        samples.append(_bilinear(img0, du, dv))
        if s == 1.:
            pred_px = float(np.nanmedian(np.hypot(du - u, dv - v))) if np.isfinite(du).any() else 0.
    common = np.all(np.isfinite(np.stack(samples)), axis=0)
    out['n'] = int(common.sum())
    out['pred_px'] = round(pred_px, 3)
    if out['n'] < int(cfg['min_points']):
        out['reason'] = 'few_common_points'
        return out
    if pred_px < float(cfg['min_pred_px']):
        out['reason'] = 'small_predicted_motion'
        return out
    r = np.array([float(np.mean(np.abs(i1[common] - smp[common]))) for smp in samples])
    scales = np.asarray(cfg['scales'], float)
    k = int(np.argmin(r))
    s_star = float(scales[k])
    out['residuals'] = [round(float(x), 4) for x in r]
    out['s_star'] = s_star
    r1, r0 = float(r[list(scales).index(1.)]), float(r[0])

    def clear(ref):
        diff = ref - r[k]
        return diff >= float(cfg['min_contrast_gray']) and diff >= float(cfg['min_contrast_rel'])*max(ref, 1e-9)
    if s_star <= float(cfg['stall_max_scale']) and clear(r1):
        out['decision'] = 'stall'
    elif s_star >= float(cfg['moving_min_scale']) and clear(r0):
        out['decision'] = 'moving'
    else:
        out['reason'] = 'low_contrast_or_intermediate_scale'
    return out
