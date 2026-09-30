"""T03 color-box perception v1: explicit kind, common confidence gates, own RGB only.

Numerical geometry is reused from the frozen zone/N7 helpers. Co-motion and
surface projection below are extracted from visual_attachment/visual_box_surface
at c1279667; only segmentation/provenance are parameterized. No recoloring,
module monkeypatch, renderer, current object pose or item-ID lookup is used.
Color is a kind cue, never an individual identity or physical grasp verdict.
"""
from __future__ import annotations
import math
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any
import cv2
import numpy as np
from harness import zone_color_boxes as z
from harness import markerless_box as mb
from harness import visual_attachment as attachment
from harness import visual_box_surface as surface
from harness import wrist_zone_skill_v6 as edge
from harness.zone_own_perception import CARRY_ROI, HOLD_MIN_COVERAGE, HOLD_MARGIN
from harness.monocular_box import _decode_jpeg
from harness.visual_arm import camera_extrinsics
from harness.owncam_view import project_base_points
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix
from harness.m1_color_contract import BOX_KINDS, require_box_kind

PROFILE = 'm1_color_boxes_v1'
MIN_SATURATION = 150
MIN_VALUE = 45
HUE_BANDS = {'cyan': ((85, 98),), 'red': ((0, 6), (172, 179)), 'green': ((56, 70),)}


def color_mask(frame, kind, *, value_range=(MIN_VALUE, 255)):
    require_box_kind(kind)
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.shape != (480, 640, 3):
        raise ValueError('COLOR_BOX_FRAME_MUST_BE_640x480_UINT8')
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(frame.shape[:2], np.uint8)
    # Same saturation/value floor for every kind; hue wrap is explicit for red.
    for lo, hi in HUE_BANDS[kind]:
        mask |= cv2.inRange(hsv, np.array((lo, MIN_SATURATION, value_range[0]), np.uint8),
                           np.array((hi, 255, value_range[1]), np.uint8))
    return mask


def components(frame, kind):
    mask = color_mask(frame, kind)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    accepted, clipped = [], False
    h, w = frame.shape[:2]
    dark = frame.max(axis=2) < 12
    rim_below = np.zeros_like(dark)
    for dy in range(1, 5):
        rim_below[:-dy] |= dark[dy:]
    rim_below[:int(h*.6)] = False
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < z.OWN_MIN_AREA_PX:
            continue
        x, y, cw, ch = cv2.boundingRect(contour)
        if x <= z.OWN_BORDER_PX or y <= z.OWN_BORDER_PX or x+cw >= w-z.OWN_BORDER_PX or y+ch >= h-z.OWN_BORDER_PX:
            clipped = True
            continue
        owned = np.zeros_like(mask)
        cv2.drawContours(owned, [contour], -1, 1, cv2.FILLED)
        if np.count_nonzero((owned > 0) & rim_below) >= 40:
            clipped = True
            continue
        solidity = area / max(float(cv2.contourArea(cv2.convexHull(contour))), 1.)
        if solidity >= z.OWN_MIN_SOLIDITY and cw >= 7 and ch >= 7:
            accepted.append({'contour': contour, 'area': area, 'solidity': solidity, 'bbox': (x,y,cw,ch), 'mask': mask})
    return accepted, clipped


def detect_own(image, servo_pose, kinds=BOX_KINDS):
    for kind in kinds:
        require_box_kind(kind)
    frame = _decode_jpeg(image)
    origin, axes = camera_extrinsics(servo_pose)
    origin, axes = np.asarray(origin), np.asarray(axes)
    k = scaled_camera_matrix(640, 480)
    d = np.asarray(CAMERA_FISHEYE_D).reshape(4, 1)
    detections, clipped_kinds = [], []
    for kind in kinds:
        comps, clipped = components(frame, kind)
        if clipped:
            clipped_kinds.append(kind)
        for comp in comps:
            fit = mb._fit_floor_cuboid(comp, origin, axes, k, d, z.BOX_DIMS_M, frame.shape)
            range_class = 'near'
            if fit is None or fit[0] < z.OWN_MIN_PROJECTION_IOU:
                fit = z._far_coarse_fit(comp, origin, axes, k, d, frame.shape)
                if fit is None or fit[0] < z.FAR_MIN_PROJECTION_IOU:
                    continue
                range_class = 'far_coarse'
            m = cv2.moments(comp['contour'])
            detections.append({'kind': kind, 'range_class': range_class,
                'pixel_centroid': [m['m10']/m['m00'], m['m01']/m['m00']], 'pixel_bbox': list(comp['bbox']),
                'area_px': comp['area'], 'solidity': comp['solidity'], 'floor_hypothesis_projection_iou': float(fit[0]),
                'estimated_box_center_base_m': [float(fit[1][0]), float(fit[1][1]), z.BOX_HALF_M[2]],
                'estimated_yaw_mod_pi_rad': float(fit[2] % math.pi)})
    return {'detections': detections, 'clipped_kinds': clipped_kinds, 'profile': PROFILE}


def observe_ground_box(image, servo_pose, kind):
    result = detect_own(image, servo_pose, (kind,))
    rows = [d for d in result['detections'] if d['range_class'] == 'near']
    base = {'kind': kind, 'target_id': 'small_box_01', 'visible': False,
            'identity_source': 'task_catalog_reference_only_not_visually_decoded',
            'provenance': 'own_rgb_kind_silhouette+known_floor_cuboid_projection',
            'assumptions': ['upright known-size cuboid', 'floor hypothesis; not contact proof']}
    if len(rows) != 1 or kind in result['clipped_kinds']:
        return {**base, 'reason': 'TARGET_KIND_NOT_UNIQUELY_VISIBLE', 'candidate_count': len(rows)}
    row = rows[0]
    return {**base, **row, 'visible': True, 'reason': 'FLOOR_CUBOID_HYPOTHESIS_VALIDATED',
            'ambiguity_reason': None, 'confidence': row['solidity']*row['floor_hypothesis_projection_iou']}


def _object_mask(frame, kind):
    mask = color_mask(frame, kind)
    kernel = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    x0, y0, x1, y1 = (int(round(v * size)) for v, size in zip(CARRY_ROI, (640, 480, 640, 480)))
    coverage = float(np.mean(mask[y0:y1, x0:x1] > 0))
    runner_up = max(float(np.mean(color_mask(frame, other)[y0:y1, x0:x1] > 0))
                    for other in BOX_KINDS if other != kind)
    if (coverage < HOLD_MIN_COVERAGE['cuboid'] or coverage < HOLD_MARGIN*runner_up
            or np.mean(mask > 0) > .85):
        # A distant floor cuboid or a featureless colored frame is not a held object.
        return np.zeros_like(mask), 0., None
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= attachment.MIN_CLOSE_AREA_PX]
    if len(contours) != 1:
        return np.zeros_like(mask), 0., None
    contour = contours[0]
    area = float(cv2.contourArea(contour)); m = cv2.moments(contour)
    owned = np.zeros_like(mask)
    cv2.drawContours(owned, [contour], -1, 255, cv2.FILLED)
    return owned, area, np.array((m['m10']/m['m00'], m['m01']/m['m00']))

def compare_box_comotion(before_image, after_image, *, kind, camera_pan_delta_pwm=0):
    """Compare two controlled-arm RGB frames for relative attachment evidence.

    The kind color does not identify a box. The caller must have established
    a unique visual target before the intervention. A positive
    result is evidence of visual attachment/co-motion only, not force sensing,
    absolute height, or guaranteed grasp success.
    """
    if isinstance(camera_pan_delta_pwm, bool) or not isinstance(camera_pan_delta_pwm, (int, float)):
        raise ValueError("camera_pan_delta_pwm must be numeric")
    pan_delta = abs(float(camera_pan_delta_pwm))
    if not np.isfinite(pan_delta) or pan_delta > 120:
        raise ValueError("camera_pan_delta_pwm outside calibrated range")
    require_box_kind(kind)
    before = _decode_jpeg(before_image)
    after = _decode_jpeg(after_image)
    if before.shape != after.shape:
        raise ValueError("CAMERA_FRAME_SIZE_CHANGED")
    before_mask, before_area, before_centroid = _object_mask(before, kind)
    after_mask, after_area, after_centroid = _object_mask(after, kind)
    base = {
        "evidence": "visual_attachment", "kind": kind,
        "attached": False,
        "identity_source": "caller_prior_visual_target_binding_required",
        "color_is_identity_evidence": False,
        "provenance": "two_own_rgb_jpegs+controlled_arm_intervention+kind_mask_comotion",
        "thresholds": {"min_saturation": MIN_SATURATION, "min_value": MIN_VALUE,
            "min_held_coverage": HOLD_MIN_COVERAGE['cuboid'], "kind_margin": HOLD_MARGIN,
            "roi_fraction": list(CARRY_ROI), "max_mask_fraction": .85,
            "min_close_area_px": attachment.MIN_CLOSE_AREA_PX, "min_iou": attachment.MIN_IOU,
            "max_centroid_delta_px": attachment.MAX_CENTROID_DELTA_PX,
            "pan_centroid_px_per_pwm": attachment.MAX_PAN_CENTROID_PX_PER_PWM,
            "area_ratio_range": list(attachment.AREA_RATIO_RANGE)},
        "camera_pan_delta_pwm": float(camera_pan_delta_pwm),
        "before_area_px": before_area,
        "after_area_px": after_area,
    }
    if before_centroid is None or after_centroid is None or min(before_area, after_area) < attachment.MIN_CLOSE_AREA_PX:
        return {**base, "reason": "CLOSE_TARGET_KIND_OBJECT_NOT_VISIBLE_IN_BOTH_FRAMES"}
    intersection = int(np.count_nonzero((before_mask > 0) & (after_mask > 0)))
    union = int(np.count_nonzero((before_mask > 0) | (after_mask > 0)))
    iou = float(intersection/union) if union else 0.0
    centroid_delta = float(np.linalg.norm(after_centroid-before_centroid))
    area_ratio = float(after_area/before_area)
    metrics = {"mask_iou": iou, "centroid_delta_px": centroid_delta,
               "area_ratio": area_ratio,
               "before_centroid_px": [float(v) for v in before_centroid],
               "after_centroid_px": [float(v) for v in after_centroid]}
    centroid_limit = (attachment.MAX_CENTROID_DELTA_PX + pan_delta * attachment.MAX_PAN_CENTROID_PX_PER_PWM
                      + (attachment.PAN_CENTROID_QUANTIZATION_PX if pan_delta else 0.0))
    metrics["effective_centroid_limit_px"] = centroid_limit
    passed = (iou >= attachment.MIN_IOU and centroid_delta <= centroid_limit
              and attachment.AREA_RATIO_RANGE[0] <= area_ratio <= attachment.AREA_RATIO_RANGE[1])
    return {**base, **metrics, "attached": bool(passed),
            "reason": "VISUAL_ATTACHMENT_SUPPORTED" if passed else "TARGET_KIND_OBJECT_DID_NOT_COMOVE_WITH_CAMERA"}

def _top_quad(frame, kind):
    mask = color_mask(frame, kind, value_range=(152, 220))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    height, width = frame.shape[:2]
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 180:
            continue
        hull = cv2.convexHull(contour)
        perimeter = float(cv2.arcLength(hull, True))
        quad = cv2.approxPolyDP(hull, .02 * perimeter, True).reshape(-1, 2)
        if len(quad) != 4 or not cv2.isContourConvex(quad.astype(np.float32)):
            continue
        if np.any(quad[:, 0] <= 2) or np.any(quad[:, 0] >= width-3) or np.any(quad[:, 1] <= 2) or np.any(quad[:, 1] >= height-3):
            continue
        solidity = area / max(float(cv2.contourArea(hull)), 1.)
        if solidity < .90:
            continue
        candidates.append((area, solidity, quad.astype(np.float64)))
    return candidates[0] if len(candidates) == 1 else None

def _surface_invisible(kind, target_id, reason, size):
    return {'kind': kind, 'target_id': target_id, 'visible': False, 'reason': reason,
            'image_size_px': list(size), 'provenance': 'own_rgb_kind_top_surface+known_upright_box_geometry'}


def observe_known_box_top(image, servo_pose, kind, target_id="small_box_01"):
    """Estimate an already-identified upright box centre from its kind top.

    This color surface is not an identity signal. Callers may use it only after
    a unique visual target was bound during the same approach.
    Base axes are +x forward, +y left, +z up.
    """
    if target_id not in surface.BOX_TOP_DIMS_M:
        raise ValueError("UNKNOWN_BOX_ID")
    frame = _decode_jpeg(image)
    height, width = frame.shape[:2]
    candidate = _top_quad(frame, kind)
    if candidate is None:
        return _surface_invisible(kind, target_id, "TARGET_KIND_TOP_QUAD_NOT_VISIBLE", (width, height))
    area, solidity, quad = candidate
    k = scaled_camera_matrix(width, height)
    d = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)
    rays = cv2.fisheye.undistortPoints(quad.reshape(1, 4, 2), k, d).reshape(4, 2)
    optical = np.column_stack((rays, np.ones(4)))
    origin, axes = camera_extrinsics(servo_pose)
    origin = np.asarray(origin, np.float64)
    directions = optical @ np.asarray(axes, np.float64)
    if not np.all(np.isfinite(directions)) or np.any(directions[:, 2] >= -.02):
        return _surface_invisible(kind, target_id, "TOP_RAYS_NOT_DOWNWARD", (width, height))
    slopes = directions[:, :2] / directions[:, 2, None]
    edge_coeff = np.linalg.norm(np.roll(slopes, -1, axis=0)-slopes, axis=1)
    if np.any(edge_coeff <= 1e-6):
        return _surface_invisible(kind, target_id, "DEGENERATE_TOP_QUAD", (width, height))
    a, b = surface.BOX_TOP_DIMS_M[target_id]
    # Illumination separates the high-value top as a bright strip: its two
    # short photometric edges need not be the physical top boundary. The two
    # long opposite edges remain the full manufactured long dimension.
    pixel_edges = np.linalg.norm(np.roll(quad, -1, axis=0)-quad, axis=1)
    pair = (0, 2) if np.mean(pixel_edges[[0, 2]]) >= np.mean(pixel_edges[[1, 3]]) else (1, 3)
    long_dimension = max(a, b)
    independent_heights = long_dimension / edge_coeff[list(pair)]
    camera_above = float(np.mean(independent_heights))
    edge_rmse = float(np.std(independent_heights) * long_dimension / max(camera_above, 1e-9))
    pair_disagreement = float(abs(independent_heights[0]-independent_heights[1]) / camera_above)
    top_z = float(origin[2]-camera_above)
    if pair_disagreement > .18 or not .0 < camera_above < 1.0 or not -.01 <= top_z <= .35:
        return _surface_invisible(kind, target_id, "TOP_GEOMETRY_AMBIGUOUS", (width, height))
    scales = (top_z-origin[2]) / directions[:, 2]
    points = origin + directions * scales[:, None]
    surface_patch = np.mean(points, axis=0)
    surface_patch[2] = top_z
    box_center_height = top_z - surface.BOX_HEIGHT_M[target_id] / 2.0
    edge_lengths = np.linalg.norm(np.roll(points[:, :2], -1, axis=0)-points[:, :2], axis=1)
    confidence = float(np.clip(solidity * (1-pair_disagreement/.18), 0., 1.))
    return {
        "target_id": target_id, "kind": kind,
        "visible": True,
        "pixel_corners": [[float(x), float(y)] for x, y in quad],
        "pixel_centroid": [float(v) for v in np.mean(quad, axis=0)],
        "area_px": area,
        "estimated_top_height_base_m": top_z,
        "estimated_surface_patch_base_m": [float(v) for v in surface_patch],
        "estimated_box_center_height_m": float(box_center_height),
        "measured_top_edge_lengths_m": [float(v) for v in edge_lengths],
        "known_top_dimensions_m": [a, b],
        "edge_fit_rmse_m": edge_rmse,
        "opposite_long_edge_height_disagreement_ratio": pair_disagreement,
        "measurement_scope": "height from two full long top edges; XY is bright surface-patch center, not full box center",
        "confidence": confidence,
        "identity_source": "caller_prior_visual_target_binding_required",
        "provenance": "own_rgb_kind_top_quad+raw_fisheye_rays+own_camera_fk+known_upright_box_dimensions",
    }

def top_edge_yaw(frame: np.ndarray, pose: Mapping[int | str, int | float],
                 target_xy: Sequence[float] | None = None, *, kind) -> dict[str, Any]:
    """Yaw (mod 90, robot base frame) of the far top edge of the target kind box in one own frame."""
    if frame is None or frame.ndim != 3 or frame.shape[:2] != (480, 640):
        return {'ok': False, 'reason': 'NO_FRAME'}
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = color_mask(frame, kind)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    comps = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= edge.EDGE_MIN_COMPONENT_PX]
    if not comps:
        return {'ok': False, 'reason': 'NO_TARGET_KIND_COMPONENT'}
    comp = max(comps, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    selection = 'largest'
    if target_xy is not None:
        px = project_base_points(pose, np.array([[float(target_xy[0]), float(target_xy[1]), edge.BOX_HEIGHT_M / 2]]))[0]
        if np.all(np.isfinite(px)):
            comp = min(comps, key=lambda i: float(np.hypot(*(centroids[i] - px))))
            selection = 'nearest_projected_own_target'
    x0, _y0, w, _h = (int(v) for v in stats[comp, :4])
    inset = max(2, int(.1 * w))
    sel = labels == comp
    valid = edge._valid_mask()
    pixels = []
    columns = clipped = 0
    for col in range(x0 + inset, x0 + w - inset):
        rows = np.flatnonzero(sel[:, col])
        if not len(rows):
            continue
        columns += 1
        row = int(rows.min())
        lo, hi = row - edge.EDGE_ABOVE_ROWS[1], row - edge.EDGE_ABOVE_ROWS[0]
        if lo < 0 or not valid[row, col] or (hsv[lo:hi + 1, col, 2] <= edge.EDGE_VIGNETTE_MAX_V).any():
            clipped += 1                                   # cut by the image / lens vignette: not the far edge
            continue
        if mask[lo:hi + 1, col].any():
            continue
        pixels.append((col, row))
    if columns and clipped > edge.EDGE_MAX_CLIPPED_FRACTION * columns:
        return {'ok': False, 'reason': 'TOP_EDGE_CLIPPED', 'columns': columns, 'clipped': clipped}
    if len(pixels) < edge.EDGE_MIN_INLIERS:
        return {'ok': False, 'reason': 'FEW_EDGE_PIXELS', 'pixels': len(pixels)}
    k = scaled_camera_matrix(640, 480)
    d = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)
    und = cv2.fisheye.undistortPoints(np.asarray(pixels, np.float64).reshape(1, -1, 2), k, d).reshape(-1, 2)
    origin, axes = camera_extrinsics(pose)
    origin = np.asarray(origin, np.float64)
    dirs = np.column_stack((und, np.ones(len(und)))) @ np.asarray(axes, np.float64)
    down = dirs[:, 2] < -1e-6
    if int(down.sum()) < edge.EDGE_MIN_INLIERS:
        return {'ok': False, 'reason': 'FEW_EDGE_RAYS'}
    s = (edge.BOX_HEIGHT_M - origin[2]) / dirs[down, 2]
    pts = origin[:2] + s[:, None] * dirs[down, :2]
    rng = np.random.default_rng(0)                         # deterministic
    best = None
    for _ in range(edge.EDGE_RANSAC_ITERS):
        i, j = rng.choice(len(pts), 2, replace=False)
        vec = pts[j] - pts[i]
        length = float(np.linalg.norm(vec))
        if length < .005:
            continue
        normal = np.array([-vec[1], vec[0]]) / length
        inl = np.abs((pts - pts[i]) @ normal) <= edge.EDGE_RANSAC_TOL_M
        if best is None or inl.sum() > best.sum():
            best = inl
    if best is None or int(best.sum()) < edge.EDGE_MIN_INLIERS:
        return {'ok': False, 'reason': 'NO_EDGE_LINE'}
    q = pts[best]
    mean = q.mean(0)
    _vals, vecs = np.linalg.eigh(np.cov((q - mean).T))
    u = vecs[:, -1]
    along = (q - mean) @ u
    span = float(along.max() - along.min())
    residual = float(np.std((q - mean) @ np.array([-u[1], u[0]])))
    info = {'inliers': int(best.sum()), 'points': int(len(pts)), 'span_m': round(span, 4),
            'residual_m': round(residual, 5), 'component': selection}
    if span < edge.EDGE_MIN_SPAN_M:
        return {'ok': False, 'reason': 'EDGE_TOO_SHORT', **info}
    if residual > edge.EDGE_MAX_RESIDUAL_M:
        return {'ok': False, 'reason': 'EDGE_NOT_STRAIGHT', **info}
    return {'ok': True, 'yaw_mod90_rad': float(math.atan2(u[1], u[0]) % edge._PERIOD), **info}

class KindEdgeYawAligner:
    """Inlier vote over own-RGB top-edge yaw fits (v5's vote and face selection; no map fallback)."""

    used_fallback = False                 # read by v1's grasp event; always False here

    def __init__(self, kind):
        self.kind = require_box_kind(kind)
        self._fits: deque[float] = deque(maxlen=edge.FACE_WINDOW)
        self._previous_normal: tuple[float, float] | None = None
        self.last_ready: dict[str, Any] | None = None
        self.observations = 0
        self.edge_accepted = 0
        self.frame: Mapping[str, Any] | None = None        # set by the box skill before each decide

    def reset_window(self) -> None:
        self._fits.clear()

    def observe(self, box: Mapping[str, Any], target_xy: Sequence[float]) -> dict[str, Any]:
        self.observations += 1
        base = {'ready': False, 'normal_xy': None, 'reason': '', 'evidence': {}}
        try:
            tx, ty = (float(v) for v in target_xy)
        except (TypeError, ValueError):
            return {**base, 'reason': 'INVALID_TARGET_XY'}
        if not (math.isfinite(tx) and math.isfinite(ty)) or math.hypot(tx, ty) <= 1e-9:
            return {**base, 'reason': 'INVALID_TARGET_XY'}
        frame = self.frame
        fit = {'ok': False, 'reason': 'NO_CURRENT_OWN_FRAME'}
        if isinstance(frame, Mapping):
            pose = (frame.get('actuator_state') or {}).get('servo_pulses')
            image = edge.decode_jpeg_b64(frame.get('image')) if isinstance(frame.get('image'), str) else None
            if isinstance(pose, Mapping) and image is not None:
                fit = top_edge_yaw(image, pose, (tx, ty), kind=self.kind)
        ok = (bool(fit.get('ok')) and box.get('visible') is True
              and box.get('kind') == self.kind)
        if ok:
            self.edge_accepted += 1
            self._fits.append(float(fit['yaw_mod90_rad']) % edge._PERIOD)
        if not ok:
            self._fits.clear()
        cuboid = (box or {}).get('estimated_yaw_mod_pi_rad') if isinstance(box, Mapping) else None
        fits = list(self._fits)
        tol = math.radians(edge.FACE_INLIER_DEG)
        best = max(fits, key=lambda f: sum(edge._mod90_dist(f, g) <= tol for g in fits), default=None)
        inliers = [g for g in fits if best is not None and edge._mod90_dist(best, g) <= tol]
        evidence = {'estimator': 'own_rgb_top_edge_yaw', 'window': [round(math.degrees(f), 2) for f in fits],
                    'inliers': len(inliers), 'min_inliers': edge.FACE_MIN_INLIERS, 'min_fraction': edge.FACE_MIN_INLIER_FRACTION,
                    'inlier_tol_deg': edge.FACE_INLIER_DEG, 'frame_accepted': ok,
                    'edge': {k: (round(math.degrees(v), 2) if k == 'yaw_mod90_rad' else v) for k, v in fit.items()},
                    'n7_cuboid_yaw_mod90_deg_not_voted': (None if not isinstance(cuboid, (int, float)) or isinstance(cuboid, bool)
                                                          or not math.isfinite(float(cuboid))
                                                          else round(math.degrees(float(cuboid) % edge._PERIOD), 2))}
        if len(inliers) < edge.FACE_MIN_INLIERS or len(inliers) < edge.FACE_MIN_INLIER_FRACTION * len(fits):
            return {**base, 'reason': 'WAITING_FOR_CONSISTENT_OWN_RGB_EDGE_FITS' if ok else
                    'EDGE_YAW_EVIDENCE_NOT_ACCEPTED', 'evidence': evidence}
        s = sum(math.sin(4 * g) for g in inliers)
        c = sum(math.cos(4 * g) for g in inliers)
        yaw_est = (math.atan2(s, c) / 4) % edge._PERIOD
        candidates = [(math.cos(yaw_est + k * edge._PERIOD), math.sin(yaw_est + k * edge._PERIOD)) for k in range(4)]
        if self._previous_normal is None:
            norm = math.hypot(tx, ty)
            toward = (-tx / norm, -ty / norm)
            selected = max(candidates, key=lambda n: n[0] * toward[0] + n[1] * toward[1])
            selection = 'outward_face_toward_chassis'
        else:
            prev = self._previous_normal
            selected = max(candidates, key=lambda n: n[0] * prev[0] + n[1] * prev[1])
            selection = 'current_own_frame_candidate_nearest_previous_normal'
        self._previous_normal = selected
        evidence.update({'yaw_mod90_deg': round(math.degrees(yaw_est), 2), 'selection': selection})
        result = {'ready': True, 'normal_xy': [selected[0], selected[1]], 'reason': 'OWN_RGB_EDGE_YAW_INLIER_VOTE',
                  'normal_source': 'own_rgb_markerless_top_edge_vote', 'evidence': evidence}
        self.last_ready = result
        return result
