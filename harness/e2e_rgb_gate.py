"""Own-camera geometry and temporal verification before an arrival declaration.

ORB/ratio matching + RANSAC homography is the classical planar verification
stage. Three fresh observations are required; descriptor similarity alone never
declares a place. No scene, authored B coordinate, or evaluation input is read.
"""
import copy
import math
import cv2
import numpy as np
from harness.active_camera import goal_camera
from harness.floor_goal import optical_rays, floor_intersections
from harness.floor_goal_self_mask import body_envelopes, project_envelopes
from harness.self_odom_grid import transform
from harness.zone_study_contract import ContractViolation

OPTION = 'rgb_geometry_v1'


def features(rgb, mask=None):
    image = np.asarray(rgb)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ContractViolation('OWN_UINT8_RGB_REQUIRED')
    keypoints, descriptors = cv2.ORB_create(nfeatures=800).detectAndCompute(
        cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), mask)
    return dict(points=np.asarray([p.pt for p in keypoints], np.float32).reshape(-1, 2),
                descriptors=descriptors, shape=image.shape[:2])


def geometric_match(reference, current):
    a, b = reference['descriptors'], current['descriptors']
    if a is None or b is None or min(len(a), len(b)) < 12:
        return dict(accepted=False, reason='insufficient_features')
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    reverse = {m.queryIdx: m.trainIdx for pair in matcher.knnMatch(b, a, k=2)
               if len(pair) == 2 for m, n in [pair] if m.distance < .75*n.distance}
    matches = [m for pair in matcher.knnMatch(a, b, k=2) if len(pair) == 2
               for m, n in [pair] if m.distance < .75*n.distance and reverse.get(m.trainIdx) == m.queryIdx]
    if len(matches) < 12:
        return dict(accepted=False, reason='insufficient_mutual_matches')
    src = np.asarray([reference['points'][m.queryIdx] for m in matches])
    dst = np.asarray([current['points'][m.trainIdx] for m in matches])
    h, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.)
    if h is None or mask is None or not np.isfinite(h).all():
        return dict(accepted=False, reason='geometry_failed')
    good = mask.ravel().astype(bool)
    spread = cv2.contourArea(cv2.convexHull(dst[good])) / np.prod(current['shape']) if good.sum() >= 3 else 0.
    accepted = int(good.sum()) >= 12 and float(good.mean()) >= .6 and spread >= .04
    return dict(accepted=bool(accepted), reason='verified' if accepted else 'weak_geometry',
                matches=len(matches), inliers=int(good.sum()), coverage=float(spread))


def boundary(rgb, servo, pose):
    """All four visible blue edges + three white islands, projected by command FK.

    Image/camera-mask clipped regions remain unknown. A partial patch's hull or
    a remembered authored size is never promoted to the full B boundary.
    """
    height, width = rgb.shape[:2]
    origin, axes = goal_camera(servo, 'camera_v3')
    self_mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, width, height)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    blue = cv2.inRange(hsv, (90, 70, 35), (135, 255, 255))
    blue[self_mask] = 0
    contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        if cv2.contourArea(contour) < 100: continue
        quad = cv2.approxPolyDP(contour, .02*cv2.arcLength(contour, True), True).reshape(-1, 2)
        if len(quad) != 4 or not cv2.isContourConvex(quad): continue
        if (quad[:, 0].min() <= 2 or quad[:, 1].min() <= 2 or
                quad[:, 0].max() >= width-3 or quad[:, 1].max() >= height-3): continue
        region = np.zeros((height, width), np.uint8); cv2.fillConvexPoly(region, quad, 255)
        if np.any(self_mask & (cv2.dilate(region, np.ones((5, 5), np.uint8)) != 0)): continue
        inner = cv2.erode(region, np.ones((5, 5), np.uint8)) != 0
        white = ((hsv[:, :, 1] < 55) & (hsv[:, :, 2] > 180) & inner).astype(np.uint8)
        _, _, stats, _ = cv2.connectedComponentsWithStats(white)
        islands = [v for v in stats[1:] if v[cv2.CC_STAT_AREA] >= 9]
        if len(islands) != 3: continue
        rays = optical_rays(width, height)[quad[:, 1], quad[:, 0]]
        xyz, valid = floor_intersections(rays, origin, axes)
        if not valid.all(): continue
        polygon = transform(xyz[:, :2], pose)
        candidates.append(dict(polygon=polygon.tolist(), center=np.mean(polygon, axis=0).tolist(),
                               pixel_polygon=quad.tolist(), complete=True, white_markers=3))
    return candidates[0] if len(candidates) == 1 else None


class ArrivalGate:
    def __init__(self, robot_id, *, option='off'):
        if option not in ('off', OPTION): raise ContractViolation('UNKNOWN_RGB_ARRIVAL_GATE')
        self.option, self.robot_id = option, robot_id
        self.references, self.current, self.history = {}, None, {}

    def observe(self, *, ref, rgb, servo, pose, covariance):
        if self.option == 'off': return
        from harness.e2e_own_inputs import rgb_ref
        rgb_ref(ref, self.robot_id, ref['t_sim'], [ref])
        if self.current and (ref['frame_id'] <= self.current['ref']['frame_id'] or
                             ref['t_sim'] <= self.current['ref']['t_sim']):
            raise ContractViolation('NEW_OWN_RGB_REQUIRED')
        origin, axes = goal_camera(servo, 'camera_v3')
        mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, rgb.shape[1], rgb.shape[0])
        self.current = dict(ref=copy.deepcopy(ref), features=features(rgb, (~mask).astype(np.uint8)*255),
                            boundary=boundary(rgb, servo, pose), pose=list(pose), covariance=copy.deepcopy(covariance))
        self.references.setdefault('start', copy.deepcopy(self.current))

    def remember_B(self):
        if self.current and self.current['boundary'] is not None:
            self.references.setdefault('B', copy.deepcopy(self.current))

    def verify_boundary(self, now):
        """Replanning evidence only; this does not declare B arrival or release."""
        row, anchor = self.current, self.references.get('B')
        good = row is not None and anchor is not None and row['boundary'] is not None
        if good:
            good = (0 <= now-row['ref']['t_sim'] <= .25 and
                    row['ref']['frame_id'] > anchor['ref']['frame_id'] and
                    geometric_match(anchor['features'], row['features'])['accepted'])
        history = self.history.setdefault('boundary', [])
        if not good: history.clear()
        elif not history or history[-1] != row['ref']:
            if history and row['ref']['t_sim']-history[-1]['t_sim'] > .5: history.clear()
            history.append(copy.deepcopy(row['ref'])); del history[:-3]
        accepted = good and len(history) == 3 and history[-1]['t_sim']-history[0]['t_sim'] >= .2-1e-8
        return dict(accepted=bool(accepted), permission='replan_only', frames=copy.deepcopy(history),
                    boundary=copy.deepcopy(row['boundary']) if row else None)

    def verify(self, label, *, now, target, near=True, geometry_confirmed=True):
        if self.option == 'off': return dict(accepted=bool(near), reason='off')
        row, anchor = self.current, self.references.get(label)
        reason = 'missing_reference'
        good = row is not None and anchor is not None
        if good:
            age = now-row['ref']['t_sim']
            good = 0 <= age <= .25 and row['ref']['frame_id'] > anchor['ref']['frame_id']
            reason = 'fresh_reobservation_required'
        if good:
            p = np.asarray(row['covariance'], float)
            good = p.shape == (3, 3) and np.isfinite(p).all() and np.allclose(p, p.T) and np.linalg.eigvalsh(p).min() >= 0
            reason = 'invalid_covariance'
        if good:
            sigma = math.sqrt(float(np.linalg.eigvalsh(p[:2, :2]).max()))
            good = near and geometry_confirmed and math.dist(row['pose'][:2], target) + 3*sigma <= .20
            reason = 'arrival_uncertainty_or_geometry'
        if good:
            match = geometric_match(anchor['features'], row['features'])
            good, reason = match['accepted'], match['reason']
        if good and label == 'B':
            good = row['boundary'] is not None
            reason = 'full_B_boundary_required' if not good else reason
        history = self.history.setdefault(label, [])
        if not good:
            history.clear()
        elif not history or history[-1] != row['ref']:
            if history and row['ref']['t_sim']-history[-1]['t_sim'] > .5: history.clear()
            history.append(copy.deepcopy(row['ref'])); del history[:-3]
        accepted = good and len(history) == 3 and history[-1]['t_sim']-history[0]['t_sim'] >= .2-1e-8
        return dict(accepted=bool(accepted), reason='verified' if accepted else reason,
                    frames=copy.deepcopy(history), boundary=copy.deepcopy(row['boundary']) if row else None)
