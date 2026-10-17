"""Reject near-field colour bands as destination paint using the metric extent.

The vendored ``floor_patch`` fit returns a record with ``extent_m`` (the
diagonal extent of the fitted ground points in metres) and ``pixels``.  A
zone-sized destination paint patch has a metre-scale extent; the long_beam's
blue end band is only 36 x 41 mm (``zone_cargo.py`` band half extents
0.018 x 0.0205 m), so its visible extent stays below ~0.06 m even when it is
close to the camera and large in pixels.  This filter therefore uses the
metric extent, not the pixel count, and never uses a world coordinate.

Default off; the fix candidate turns it on and records every rejection.
"""
from __future__ import annotations

# Beam band footprint (0.036 x 0.041 m) diagonal is 0.054 m.  Zone B is
# 0.6 x 1.4 m, so any visible zone patch has an extent of at least 0.30 m.
# The threshold sits between the two known geometries (not a tuned value).
PAINT_MIN_EXTENT_M = 0.15


def filter_paint(paint, patch_record, min_extent_m=PAINT_MIN_EXTENT_M):
    """Return (paint_out, info). paint_out has pixels=0 when rejected."""
    info = dict(min_extent_m=min_extent_m, action='not_applicable',
                extent_m=None, reason=None)
    if not paint:
        return paint, info
    if paint.get('pixels', 0) < 600:
        return paint, info
    rec = patch_record or {}
    if rec.get('reason') != 'painted_ground_hypothesis':
        info.update(action='not_metric_patch', reason=rec.get('reason'))
        return paint, info
    extent = rec.get('extent_m')
    info['extent_m'] = extent
    if extent is None:
        info.update(action='not_measured')
        return paint, info
    if float(extent) < float(min_extent_m):
        info.update(action='rejected', reason='paint_rejected_small_extent')
        out = dict(paint)
        out['pixels'] = 0
        out['reason'] = 'paint_rejected_small_extent'
        out['rejected_extent_m'] = extent
        out['raw_pixels_before_filter'] = int(paint.get('pixels', 0))
        return out, info
    info['action'] = 'accepted'
    return paint, info
