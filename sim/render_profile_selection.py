"""Lazy profile selection for new consumers; frozen runners keep their imports."""
from __future__ import annotations


def for_name(name):
    """Load the texture extension only for its explicit, versioned profile name."""
    if name in ('walls_floor_contrast_v4_dark', 'walls_floor_contrast_v4_light', 'walls_floor_contrast_v4_skirt',
                'walls_floor_contrast_v4_luma', 'walls_floor_contrast_v4_flat'):
        from sim import scene_contrast_v4 as profile
        profile.resolve(name)
        return profile
    if name in ('floor_light_textured_v1', 'walls_floor_textured_v2', 'walls_floor_textured_v3'):
        from sim import render_profile_textured as profile
    else:
        from sim import render_profile as profile
    profile.resolve(name)
    return profile
