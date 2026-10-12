"""Own-camera geometry and temporal verification before an arrival declaration.

ORB/ratio matching + RANSAC homography is the classical planar verification
stage. Three fresh observations are required; descriptor similarity alone never
declares a place. No scene, authored B coordinate, or evaluation input is read.
"""
import copy
import functools
import math
import cv2
import numpy as np
from harness.active_camera import goal_camera
from harness.floor_goal import optical_rays, floor_intersections
from harness.floor_goal_self_mask import body_envelopes, project_envelopes
from harness.self_odom_grid import transform
from harness.zone_study_contract import ContractViolation

OPTION = 'rgb_geometry_v1'
# B marker pixel rule (default off = the original fixed HSV thresholds).
# contrast_v1: the sim slot marks are 35 %-alpha white over 30 %-alpha blue over
# a checker floor, so they keep the floor hue and only raise min(R,G,B) and
# lower saturation relative to their OWN local background (two blue tones).
# Local background = grayscale opening (min-RGB) / closing (S) with a square
# element larger than a mark, i.e. ratio forms of the white/black top-hat
# (OpenCV morphologyEx). The two ratio tests are gain-invariant; the absolute
# floors (delta 12, V 50) are not. Replay verified gains 0.7-1.3 only. Saturation of dark pixels (V < 50) is ill-conditioned
# and is excluded from the background. A 3x3 binary opening removes 1-2 px
# edge ringing, and marks touching the region border are cleared (imclearborder):
# floor-tone patches always reach the B edge, the marks lie inside it.
# Island count/area and quad shape checks are unchanged.
MARKER_OPTION = 'contrast_v1'
# contrast_v2: same mark pixels as v1; the B quad is fitted by harness/e2e_b_quad.py
# (floor-blue hue mask, undistort + convex hull + adaptive approxPolyDP, lens/border/solidity guards).
MARKER_OPTION_V2 = 'contrast_v2'
MARKER_OPTIONS = (MARKER_OPTION, MARKER_OPTION_V2)
MARKER_CONTRAST = dict(min_rgb_ratio=1.3, min_rgb_delta=12, saturation_ratio=.78, background_value_min=50,
                       kernel_fraction=.25, kernel_px_min=15, kernel_px_max=151)


@functools.lru_cache(maxsize=4)
def lens_valid(width, height, erode_px=5):
    """Fixed camera calibration: pixels inside the raw fisheye image circle."""
    from sim.masterpi_camera_profile import raw_fisheye_remap
    x, y = raw_fisheye_remap(width, height)
    valid = ((x >= 0) & (x <= width-1) & (y >= 0) & (y <= height-1)).astype(np.uint8)
    valid = cv2.erode(valid, np.ones((erode_px, erode_px), np.uint8)) != 0
    valid.setflags(write=False)
    return valid


def white_markers(rgb, hsv, inner, *, region_area_px2, option='off'):
    """Boolean mark mask inside ``inner``; own RGB only."""
    if option == 'off':
        return (hsv[:, :, 1] < 55) & (hsv[:, :, 2] > 180) & inner
    if option not in MARKER_OPTIONS: raise ContractViolation('UNKNOWN_B_MARKER_DETECT')
    c = MARKER_CONTRAST
    k = int(np.clip(c['kernel_fraction']*math.sqrt(max(region_area_px2, 0.)),
                    c['kernel_px_min'], c['kernel_px_max'])) | 1
    element = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    w, s = np.asarray(rgb).min(axis=2), hsv[:, :, 1]
    valid = lens_valid(w.shape[1], w.shape[0])
    # Outside the lens circle is neutral: it can neither lower the min-RGB
    # background (255) nor raise the saturation background (0).
    reliable_s = np.where(valid & (hsv[:, :, 2] >= c['background_value_min']), s, 0).astype(np.uint8)
    wb = cv2.morphologyEx(np.where(valid, w, 255).astype(np.uint8), cv2.MORPH_OPEN, element).astype(np.float32)
    sb = cv2.morphologyEx(reliable_s, cv2.MORPH_CLOSE, element).astype(np.float32)
    w, s = w.astype(np.float32), s.astype(np.float32)
    mask = inner & valid & (w >= c['min_rgb_ratio']*wb) & (w-wb >= c['min_rgb_delta']) & (s <= c['saturation_ratio']*sb)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels = cv2.connectedComponents(mask)
    edge = inner & ~(cv2.erode(inner.astype(np.uint8), np.ones((3, 3), np.uint8)) != 0)
    touching = np.unique(labels[edge & (labels > 0)])
    return (labels > 0) & ~np.isin(labels, touching)


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


def boundary(rgb, servo, pose, *, diagnostics=None, marker_detect='off'):
    """All four visible blue edges + three white islands, projected by command FK.

    Image/camera-mask clipped regions remain unknown. A partial patch's hull or
    a remembered authored size is never promoted to the full B boundary.
    """
    height, width = rgb.shape[:2]
    origin, axes = goal_camera(servo, 'camera_v3')
    self_mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, width, height)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    v2 = marker_detect == MARKER_OPTION_V2
    if v2:
        from harness import e2e_b_quad
        blue = e2e_b_quad.floor_blue_mask(hsv, self_mask)
    else:
        blue = cv2.inRange(hsv, (90, 70, 35), (135, 255, 255))
        blue[self_mask] = 0
    if diagnostics is not None:
        diagnostics.update(blue_pixels=int(np.count_nonzero(blue)), contours=[], accepted_candidates=0)
    contours, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        row = dict(area_px2=float(cv2.contourArea(contour)), reason='area_below_100')
        if diagnostics is not None: diagnostics['contours'].append(row)
        if row['area_px2'] < 100: continue
        if v2:
            quad, why, fit = e2e_b_quad.fit_quad(contour, lens_valid(width, height))
            row.update(fit, reason=why)
            if quad is None: continue
            row.update(vertices=4, convex=True)
            region = np.zeros((height, width), np.uint8)
            cv2.fillConvexPoly(region, cv2.convexHull(contour), 255)
        else:
            quad = cv2.approxPolyDP(contour, .02*cv2.arcLength(contour, True), True).reshape(-1, 2)
            row.update(vertices=len(quad), convex=bool(cv2.isContourConvex(quad)), reason='not_convex_quad')
            if len(quad) != 4 or not cv2.isContourConvex(quad): continue
        row.update(border_margin_px=int(min(quad[:, 0].min(), quad[:, 1].min(),
            width-1-quad[:, 0].max(), height-1-quad[:, 1].max())), reason='image_clipped')
        if (quad[:, 0].min() <= 2 or quad[:, 1].min() <= 2 or
                quad[:, 0].max() >= width-3 or quad[:, 1].max() >= height-3): continue
        if not v2: region = np.zeros((height, width), np.uint8); cv2.fillConvexPoly(region, quad, 255)
        row.update(self_mask_overlap_px=int(np.count_nonzero(self_mask &
            (cv2.dilate(region, np.ones((5, 5), np.uint8)) != 0))), reason='self_mask_clipped')
        if row['self_mask_overlap_px']: continue
        inner = cv2.erode(region, np.ones((5, 5), np.uint8)) != 0
        if diagnostics is not None:
            low_s = inner & (hsv[:, :, 1] < 55)
            row['low_saturation_pixels'] = int(low_s.sum())
            row['low_saturation_value_max'] = int(hsv[:,:,2][low_s].max()) if low_s.any() else None
        white = white_markers(rgb, hsv, inner, region_area_px2=float(cv2.contourArea(quad.astype(np.float32))),
                              option=MARKER_OPTION if v2 else marker_detect).astype(np.uint8)
        _, _, stats, _ = cv2.connectedComponentsWithStats(white)
        islands = [v for v in stats[1:] if v[cv2.CC_STAT_AREA] >= 9]
        row.update(white_islands=len(islands), white_island_areas_px=[int(v[cv2.CC_STAT_AREA]) for v in islands],
                   reason='white_islands_not_three')
        if len(islands) != 3: continue
        rays = optical_rays(width, height)[quad[:, 1], quad[:, 0]]
        xyz, valid = floor_intersections(rays, origin, axes)
        row.update(valid_floor_corners=int(valid.sum()), reason='invalid_floor_projection')
        if not valid.all(): continue
        polygon = transform(xyz[:, :2], pose)
        if v2:
            shape_ok, shape = e2e_b_quad.floor_shape_ok(polygon)
            row.update(shape, reason='floor_shape_implausible')
            if not shape_ok: continue
        row.update(reason='accepted', projected_area_m2=float(cv2.contourArea(polygon.astype(np.float32))))
        candidates.append(dict(polygon=polygon.tolist(), center=np.mean(polygon, axis=0).tolist(),
                               pixel_polygon=quad.tolist(), complete=True, white_markers=3))
    if diagnostics is not None:
        diagnostics['accepted_candidates'] = len(candidates)
    return candidates[0] if len(candidates) == 1 else None


class ArrivalGate:
    def __init__(self, robot_id, *, option='off', marker_detect='off'):
        if option not in ('off', OPTION): raise ContractViolation('UNKNOWN_RGB_ARRIVAL_GATE')
        if marker_detect not in ('off', *MARKER_OPTIONS): raise ContractViolation('UNKNOWN_B_MARKER_DETECT')
        self.option, self.robot_id, self.marker_detect = option, robot_id, marker_detect
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
        diagnostics = {} if getattr(self, 'diagnostics_enabled', False) else None
        self.current = dict(ref=copy.deepcopy(ref), features=features(rgb, (~mask).astype(np.uint8)*255),
                            boundary=boundary(rgb, servo, pose, diagnostics=diagnostics,
                                                   marker_detect=self.marker_detect),
                            pose=list(pose), covariance=copy.deepcopy(covariance))
        if diagnostics is not None: self.current['boundary_diagnostics'] = diagnostics
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
