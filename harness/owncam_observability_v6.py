"""Static shape observability across own posterior hypotheses, without IDs.

Scores are proposals, never fix receipts. No detector, worker, or model call.
Wall corners/edges are used for either temporary-tag or markerless providers.
"""
import math
import numpy as np

from harness.owncam_drive import LOOK_P20
from harness.owncam_view import project_base_points, valid_pixel_mask
from harness.zone_own_guards import static_boxes


def posterior_hypotheses(loc, pose):
    if getattr(loc, 'initialized', False) and hasattr(loc, 'px'):
        w = np.exp(loc.logw - np.max(loc.logw)); w /= w.sum()
        # Deterministic quantiles preserve separated modes without RNG draws.
        idx = np.minimum(np.searchsorted(np.cumsum(w), np.linspace(.01, .99, 11)), len(w)-1)
        return np.unique(loc.px[idx], axis=0)
    return np.array([[pose.x, pose.y, pose.yaw]])


def geometry_score(hypotheses, pan, static_map):
    points = []
    for box in static_boxes(static_map):
        c, s = math.cos(box['yaw']), math.sin(box['yaw'])
        for x in (-box['half'][0], box['half'][0]):
            for y in (-box['half'][1], box['half'][1]):
                for z in (0., box['height']):
                    points.append([box['center'][0]+c*x-s*y, box['center'][1]+s*x+c*y, z])
    if not points:
        return 0.
    points = np.asarray(points)
    valid = valid_pixel_mask()
    servo = {**LOOK_P20, 6: pan}

    def project(p):
        c, s = math.cos(p[2]), math.sin(p[2])
        rot = np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
        return project_base_points(servo, (points-np.array([*p[:2],0.])) @ rot)

    scores, signatures = [], []
    for p in hypotheses:
        px = project(p)
        mask = np.isfinite(px).all(axis=1) & (px >= 1).all(axis=1) & (px < [639,479]).all(axis=1)
        idx = np.flatnonzero(mask)
        mask[idx] &= valid[px[idx,1].astype(int),px[idx,0].astype(int)]
        if not mask.any():
            scores.append(0.); continue
        # Image geometry derivatives discriminate translation and yaw; area or
        # number of visible markers is not used as a readiness condition.
        derivatives = []
        for axis, step in enumerate((.01,.01,.02)):
            a, b = p.copy(), p.copy(); a[axis] += step; b[axis] -= step
            derivatives.append(((project(a)-project(b))[mask]/(2*step)).reshape(-1))
        jac = np.column_stack(derivatives)
        if not np.isfinite(jac).all():
            scores.append(0.); continue
        information = jac.T @ jac / max(1, len(jac))
        eig = np.linalg.eigvalsh(information)
        spread = np.var(px[mask]/[640,480], axis=0).sum()
        scores.append(float(math.log1p(max(0., eig[0])) * spread))
        signatures.append(np.mean(px[mask]/[640,480], axis=0))
    # Bad hypotheses matter; a single attractive mean cannot hide unseen modes.
    discrimination = float(np.var(signatures, axis=0).sum()) if len(signatures)>1 else 0.
    return float(min(scores, default=0.) + .25*np.mean(scores)) * (1+discrimination)


def expected_observability(loc, pose, pan, static_map):
    return geometry_score(posterior_hypotheses(loc, pose), pan, static_map)
