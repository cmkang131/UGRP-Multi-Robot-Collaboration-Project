"""Explicit v2-only nominal material classification; own RGB, no scene truth.

This is a PNG-calibrated candidate, not a transferred camera calibration. Do not
use its masks as a success/pose verdict. GCP PNG/JPEG scoring is required first.
"""
from __future__ import annotations

import cv2
import numpy as np
from functools import lru_cache

PROFILE = 'walls_floor_textured_v2'


def surface_masks(bgr, profile):
    if profile != PROFILE:
        raise ValueError('scene tex2 perception requires its explicit render profile')
    image = np.asarray(bgr)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('expected uint8 BGR')
    from sim.natural_scene_texture_v2 import manifest
    palettes = manifest()['palettes_hsv']
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    # Bounds are the authored disjoint V intervals. S<20 is the complement of
    # the broadest all-hue paint detector, not an unexplained tuning constant.
    # Hue is not gated: at S<=18 integer RGB quantization makes it unstable.
    return {kind: (hsv[..., 1] < 20) & (hsv[..., 2] >= p['v'][0]) &
                  (hsv[..., 2] <= p['v'][1]) for kind, p in palettes.items()}


def wall_band_parameters(profile):
    """Candidate ONLY: bound variance analytically, retain all geometry tests.

    Popoviciu: std <= range/2. Apply independently to luminance and B-R;
    the frozen detector sums their variances. This is a nominal PNG bound;
    rendered-light calibration remains explicitly unverified.
    """
    if profile != PROFILE:
        raise ValueError('scene tex2 perception requires its explicit render profile')
    from sim.natural_scene_texture_v2 import manifest, ASSETS, checked_file
    from PIL import Image
    record = manifest()
    minimum, maximum = np.full(2, np.inf), np.full(2, -np.inf)
    for key in record['images']:
        if key == 'floor':
            continue
        rgb = np.asarray(Image.open(checked_file(key, record, ASSETS))).astype(float)
        values = np.stack((.299*rgb[..., 0]+.587*rgb[..., 1]+.114*rgb[..., 2],
                           rgb[..., 2]-rgb[..., 0]), axis=-1).reshape(-1, 2)
        minimum = np.minimum(minimum, values.min(0))
        maximum = np.maximum(maximum, values.max(0))
    return {'max_band_std': float(np.linalg.norm(maximum-minimum)/2)}


def detect_boundaries(mp, bgr, camera, *, profile, params=None):
    """Opt-in adapter: keep the frozen candidate geometry, then demand a true
    nominal wall-to-floor transition instead of accepting internal wear edges.
    No monkeypatch and no changes to frozen consumers/calibration.
    """
    p = {**(params or {}), **_parameters(profile)}
    scan = mp.detect_boundaries(bgr, camera, p)
    masks = surface_masks(bgr, profile)
    window = int({**mp.DEFAULT_DETECTOR, **p}['window_px'])
    # A strict whole-window test introduces no fitted fraction. Occlusion,
    # antialiasing or light outside the nominal class causes abstention.
    for j, u in enumerate(scan.columns):
        for k in np.flatnonzero(np.isfinite(scan.vb[j])):
            v = int(round(scan.vb[j, k]))
            if (v-window < 0 or v+window >= bgr.shape[0] or
                    not masks['walls'][v-window:v, u].all() or
                    not masks['floor'][v+1:v+1+window, u].all()):
                scan.vb[j, k] = scan.vt[j, k] = np.nan
    return scan


_parameters = lru_cache(maxsize=1)(wall_band_parameters)
