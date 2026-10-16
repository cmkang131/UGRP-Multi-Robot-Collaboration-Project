"""Two-view own RGB verification, no metric pose correction or truth input.

Reuse the existing ORB descriptor, ratio and pixel chi-square gates. Homography
verification is suitable for planar floor/wall patches and rotating views; it
does not establish metric location and is not a replacement SLAM back end.
"""
import math
import cv2
import numpy as np
from harness.own_rgb_homing import PARAMS, matches
from harness.own_teach_capture import MIN_ROTATION
from harness.own_traversal_reconnection import PARTIAL_TIMEOUT

OPTION = 'two_view_rgb_v1'
MIN_ANGLE = math.radians(MIN_ROTATION)
MAX_AGE = 2 * PARTIAL_TIMEOUT


def angle_difference(a, b):
    return abs(math.atan2(math.sin(a-b), math.cos(a-b)))


def geometry(a, b, K):
    """Mutual ORB + RANSAC + both directions' octave-scaled pixel residuals."""
    pairs = matches(a.descriptors, b.descriptors)
    result = dict(accepted=False, reason='insufficient_matches', matches=len(pairs), inliers=0)
    if len(pairs) < PARAMS['min_matches']:
        return result
    ia, ib = np.asarray(pairs).T
    uv, xy = a.uv[ia].astype(np.float64), b.uv[ib].astype(np.float64)
    H, mask = cv2.findHomography(uv, xy, cv2.RANSAC, PARAMS['homography_px'],
        maxIters=PARAMS['iterations'], confidence=PARAMS['confidence'])
    if H is None or mask is None or not np.isfinite(H).all():
        return dict(result, reason='homography_failed')
    try:
        inverse = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return dict(result, reason='singular_homography')
    def residual(transform, source, target):
        p = np.column_stack([source, np.ones(len(source))]) @ transform.T
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.sum((p[:, :2]/p[:, 2:] - target)**2, axis=1)
    forward, backward = residual(H, uv, xy), residual(inverse, xy, uv)
    good = ((mask.ravel() != 0) & np.isfinite(forward) & np.isfinite(backward)
            & (forward <= PARAMS['chi2'] * b.variance[ib])
            & (backward <= PARAMS['chi2'] * a.variance[ia]))
    result.update(inliers=int(good.sum()))
    if result['inliers'] < PARAMS['min_matches']:
        return dict(result, reason='symmetric_reprojection_gate')
    # Use the least rotation among all plane-decomposition solutions. A
    # changed command/odometry yaw alone is not a changed optical viewpoint.
    try:
        _, rotations, _, _ = cv2.decomposeHomographyMat(H, K)
        angles = [math.acos(float(np.clip((np.trace(R)-1)/2, -1, 1)))
                  for R in rotations if np.isfinite(R).all()]
    except cv2.error:
        angles = []
    return dict(result, accepted=True, reason='homography_verified',
        minimum_optical_angle_rad=min(angles) if angles else None,
        rms_px=float(np.sqrt(np.mean(forward[good]))))


class TwoViewGate:
    """A first view never confirms; each confirmation still needs current RGB."""
    def __init__(self, K):
        self.K = np.asarray(K).copy()
        self.states = {}
        self.rows = []

    def observe(self, key, current, *, references=None, semantic=True, evidence=None):
        row = dict(key=str(key), t=current.t, frame_id=current.frame_id,
            sha256=current.sha256, accepted=False, semantic=bool(semantic), evidence=evidence)
        state = self.states.get(key)
        if state is not None and (current.t-state['first'].t > MAX_AGE
                or math.dist(current.pose[:2], state['first'].pose[:2]) > .30):
            self.states.pop(key)
            state = None
        if not semantic:
            row['reason'] = 'semantic_or_association_rejected'
        elif state is not None and current.frame_id <= state['first'].frame_id:
            row['reason'] = 'noncausal_or_repeated_frame'
        elif state is not None and current.sha256 == state['first'].sha256:
            row['reason'] = 'repeated_rgb'
        else:
            # Pin one past reference on first admission; changing to another
            # look-alike historical image cannot satisfy the second view.
            reference = state.get('reference') if state else None
            if reference is None and references is not None:
                causal = [f for f in references if f.t < current.t and f.frame_id < current.frame_id]
                trials = [(geometry(f, current, self.K), f) for f in causal]
                accepted = [(r, f) for r, f in trials if r['accepted']]
                if accepted:
                    match, reference = max(accepted, key=lambda p: p[0]['inliers'])
                    row['reference_match'] = match
                else:
                    row['reason'] = 'no_reference' if not causal else 'reference_geometry_rejected'
                    row['reference_trials'] = [dict(r, frame_id=f.frame_id) for r, f in trials]
            elif reference is not None:
                match = geometry(reference, current, self.K)
                row['reference_match'] = match
                if not match['accepted']:
                    row['reason'] = 'reference_geometry_rejected'
            if reference is not None:
                row['reference_frame'] = reference.frame_id
            if 'reason' not in row:
                if state is None:
                    self.states[key] = dict(first=current, reference=reference, confirmed=False)
                    row['reason'] = 'second_view_required'
                else:
                    match = geometry(state['first'], current, self.K)
                    row['pair_match'] = match
                    yaw = angle_difference(current.pose[2], state['first'].pose[2])
                    optical = match.get('minimum_optical_angle_rad')
                    row['own_yaw_separation_rad'] = yaw
                    if not match['accepted']:
                        row['reason'] = 'current_geometry_rejected'
                    elif not state['confirmed'] and (yaw < MIN_ANGLE or optical is None or optical < MIN_ANGLE):
                        row['reason'] = 'different_angle_required'
                    else:
                        state['confirmed'] = True
                        row.update(accepted=True, reason='two_view_confirmed', first_frame=state['first'].frame_id)
        self.rows.append(row)
        return row
