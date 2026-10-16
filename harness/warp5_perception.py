"""Default-off MJWarp colour class reuse. No simulator input or fitted bound."""
import hashlib,json,os
from functools import lru_cache
from pathlib import Path

ENV='UGRP_WARP5_PERCEPTION'


@lru_cache(maxsize=4)
def calibration(path,sha):
    p=Path(path)
    if not sha or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('WARP5_CALIBRATION_HASH_MISMATCH')
    c=json.loads(p.read_text())
    if c.get('renderer_profile')!='warp5_native_visual_v1':raise ValueError('WARP5_RENDERER_PROFILE_REQUIRED')
    return c


def exclude_wall(mask,bgr):
    if os.environ.get(ENV,'off')=='off':return mask
    if os.environ[ENV]!='rendered_v1':raise ValueError('UNKNOWN_WARP5_PERCEPTION')
    from harness.scene_colour_boundary import surface_masks
    c=calibration(os.environ['UGRP_SCENE_COLOUR_CALIBRATION'],os.environ['UGRP_SCENE_COLOUR_CALIBRATION_SHA256'])
    surfaces,_=surface_masks(bgr,c,expanded_wall_value=True)
    # Reuse the measured wall RGB class. No GT mask, new HSV threshold,
    # minimum area, floor-plane distance or success tolerance is introduced.
    return mask & ~surfaces['wall']
