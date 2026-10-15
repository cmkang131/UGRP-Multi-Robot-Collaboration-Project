"""Lazy profile selection for new consumers; frozen runners keep their imports."""
from __future__ import annotations


def for_name(name):
    """Load the texture extension only for its explicit, versioned profile name."""
    if name in ('floor_light_textured_v1', 'walls_floor_textured_v2'):
        from sim import render_profile_textured as profile
    else:
        from sim import render_profile as profile
    profile.resolve(name)
    return profile
