"""Default-off, single-object beam perception; release15 motion is unchanged.

Known shape: a straight beam, with its assigned colour band on that beam.
Connected-component association and deterministic two-point RANSAC operate
only on current own RGB. No world, target coordinates or temporal GT enters.
See release16.md for the checked references and offline evaluation limits.
"""
from __future__ import annotations

import hashlib
import math

import cv2
import numpy as np

from harness.zone_own_perception import _usable_region
from sim import release14, release15
from sim.release_regrasp import assigned_beam_mask, beam_mask

PROFILE = 'release16_known_shape_v1'
PROFILES = (*release15.PROFILES, PROFILE)
SAFE = release15.SAFE
# Reuse the exact release15 time limits, pulse selection and map/FOV guards.
line_step = release15.line_step
map_motion_clear = release15.map_motion_clear
backoff_plan = release15.backoff_plan
approach_plan = release15.approach_plan


def validate(profile, record_training, options, plan):
    release15.validate(release15.PROFILE if profile == PROFILE else profile,
                       record_training, options, plan)


def row_centres(mask, start=0, stop=480):
    """Both lateral boundaries must be visible; gaps are never painted in."""
    usable = _usable_region(640, 480)
    rows = []
    for y in range(start, stop, 4):
        xs = np.flatnonzero(mask[y]); bounds = np.flatnonzero(usable[y])
        if len(xs) < 8 or not len(bounds):
            continue
        if xs[0] <= bounds[0]+3 or xs[-1] >= bounds[-1]-3:
            continue
        # Two parallel objects in the same row are not a single beam width.
        if np.max(np.diff(xs), initial=1) > 5:
            continue
        rows.append((y, (xs[0]+xs[-1])/2., xs[-1]-xs[0]+1.))
    return np.asarray(rows, float).reshape(-1, 3)


def fit_rows(rows, *, min_rows=12, min_span=120.):
    """RANSAC minimal pair -> consensus -> least-squares consensus refit.

    Thresholds are pixels in the fixed 640x480 calibration. A fixed local RNG
    makes replay exact without changing any caller's random stream.
    """
    if len(rows) < min_rows or np.ptp(rows[:, 0]) < min_span:
        return None
    y, x = rows[:, 0], rows[:, 1]
    pairs = np.random.default_rng(0).integers(0, len(rows), (128, 2))
    pairs = np.vstack(([0, len(rows)-1], pairs))
    best = None
    for i, j in pairs:
        if abs(y[j]-y[i]) < min_span/2:
            continue
        a = (x[j]-x[i])/(y[j]-y[i]); b = x[i]-a*y[i]
        residual = abs(x-(a*y+b)); inside = residual <= 4.
        score = (int(inside.sum()), -float(np.minimum(residual, 4.).sum()))
        if best is None or score > best[0]:
            best = score, inside
    if best is None or best[0][0] < max(min_rows, math.ceil(.85*len(rows))):
        return None
    keep = best[1]
    if np.ptp(y[keep]) < min_span:
        return None
    a, b = np.polyfit(y[keep], x[keep], 1)
    residual = abs(x-(a*y+b))
    if float(np.quantile(residual, .9)) > .02*640:
        return None
    return dict(slope=float(a), intercept=float(b), inliers=int(keep.sum()),
                rows=len(rows), span_px=float(np.ptp(y[keep])),
                residual_p90_px=float(np.quantile(residual, .9)))


def compatible(first, second):
    """Associate separated collinear strips, not side-by-side/lookalike cargo.

    Seam closing handles JPEG colour boundaries. Larger gaps need two
    independently observed straight strips, compatible width and direction,
    and a bounded longitudinal gap; unknown geometry is not merged.
    """
    a, b = row_centres(first), row_centres(second)
    fa = fit_rows(a, min_rows=6, min_span=32.)
    fb = fit_rows(b, min_rows=6, min_span=32.)
    if fa is None or fb is None:
        return False
    gap = max(a[:, 0].min(), b[:, 0].min())-min(a[:, 0].max(), b[:, 0].max())
    if gap < 0 or gap > 96:
        return False
    width_a, width_b = np.median(a[:, 2]), np.median(b[:, 2])
    if not .5 <= width_a/width_b <= 2.:
        return False
    if abs(math.atan(fa['slope'])-math.atan(fb['slope'])) > math.radians(5):
        return False
    ys = np.array([a[:, 0].mean(), b[:, 0].mean()])
    separation = abs((fa['slope']-fb['slope'])*ys+fa['intercept']-fb['intercept'])
    return bool(np.max(separation) <= max(5., .15*min(width_a, width_b)))


def object_mask(frame, end):
    """Return actual selected pixels, with a single association definition."""
    raw = assigned_beam_mask(frame, end, colour_profile=release15.PROFILE)
    shaft = beam_mask(frame)
    # A 1-pixel JPEG seam is association-only, not invented image evidence.
    closed = cv2.morphologyEx(raw.astype('uint8'), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed)
    support = np.bincount(labels[shaft], minlength=n)
    ranked = sorted(range(1, n), key=lambda i: (-int(support[i]), -stats[i, cv2.CC_STAT_AREA]))
    if not ranked or support[ranked[0]] < 32:
        return raw, dict(reason='beam_missing', components=0, merged_components=0)
    mask = (labels == ranked[0]) & raw
    merged = 0; competitors = []; detached_bands = 0
    for i in ranked[1:]:
        candidate = (labels == i) & raw
        if candidate.sum() < max(32, .002*mask.sum()):
            continue
        if compatible(mask, candidate):
            mask |= candidate; merged += 1
        elif support[i] < 32:
            # Assigned colour is not an object identity. In particular, a
            # separate blue destination patch is not part of this beam.
            detached_bands += 1
        else:
            competitors.append(int(candidate.sum()))
    reason = 'beam_object'
    if max(competitors, default=0) > .3*mask.sum():
        reason = 'beam_ambiguous'
    if mask.sum() < .015*640*480:
        reason = 'beam_missing'
    return mask, dict(reason=reason, components=len(ranked), merged_components=merged,
                     detached_band_components=detached_bands)


def line_features(frame, end=None):
    f = dict(valid=False, reason='beam_invalid_frame', line=None, points=[],
             fov_safe=False, unclipped=False, slope_error=None,
             object_model='shaft_plus_assigned_band_straight_v1')
    if frame is None or frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
        return f
    mask, info = object_mask(frame, end)
    f.update(info, mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest(), pixels=int(mask.sum()))
    if info['reason'] != 'beam_object':
        return f
    ys, xs = np.nonzero(mask)
    f.update(valid=True, center_x_px=float(xs.mean()), offset_px=float(xs.mean()-319.5),
             image_width=640, center_error=float((xs.mean()-319.5)/640), reason='beam_clipped')
    rows = row_centres(mask, 96, 384)
    model = fit_rows(rows)
    if len(rows) >= 12 and np.ptp(rows[:, 0]) >= 120 and model is None:
        # A prism's end face can bend its silhouette centreline. The object
        # is still observed, but that is NOT a usable straight direction.
        # Retain its complete FOV envelope and request translation/relook.
        f.update(reason='beam_direction_unresolved')
    if model is not None:
        f.update(center_error=(model['slope']*239.5+model['intercept']-319.5)/640,
                 slope_error=model['slope']*192/640, unclipped=True,
                 reason='beam_rows', fitted_model=model)
        f['line'] = release14.polar_line(f).tolist()
    # The FOV region comes from precisely the SAME selected object and model.
    # Keep release15's central line-window + whole assigned-band convention.
    target = mask.copy()
    if f['line'] is not None:
        target[:96] = False; target[384:] = False
        target |= mask & ~beam_mask(frame)
    ty, tx = np.nonzero(target)
    box = [float(tx.min()), float(ty.min()), float(tx.max()), float(ty.max())]
    points = [[box[x], box[y]] for x, y in ((0, 1), (2, 1), (0, 3), (2, 3))]
    f.update(points=points, visible_box_px=box, fov_safe=release15.inside(points),
             fov_margin_px=float(min(box[0]-64, box[1]-64, 575-box[2], 415-box[3])))
    return f


class LineAlign(release15.LineAlign):
    def features(self, frame):
        return line_features(frame, self.teacher.end)

    def fail(self, reason):
        self.failure = 'release16_'+reason; self.state = 'failed'
        return 'failed'
