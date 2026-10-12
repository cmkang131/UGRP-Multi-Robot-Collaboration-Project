"""Own-body masking, metric floor footprint gates and consecutive SE(2) evidence.

No live ground truth, peer state, static goal position or simulator dependency.
Known B dimensions are .6 by 1.4 m; observed partial regions remain partial.
"""
from dataclasses import dataclass, fields
import math

import cv2
import numpy as np

from harness.floor_goal import FloorGoalMemory, FloorGoalOptions, commanded_camera, floor_intersections, optical_rays
from harness.floor_goal_v2 import FloorGoalV2Options, detect_floor_v2
from harness.floor_goal_self_mask import self_body_mask
from harness.self_odom_grid import transform


@dataclass(frozen=True)
class FloorGoalV3Options(FloorGoalV2Options):
    minimum_observed_area_m2: float = .005
    temporal_overlap_min: float = .35
    temporal_center_max_m: float = .10

    def __post_init__(self):
        super().__post_init__()
        if not (0 < self.minimum_observed_area_m2 < .84 and 0 < self.temporal_overlap_min <= 1 and
                0 < self.temporal_center_max_m <= 1):
            raise ValueError('INVALID_GOAL_V3_OPTIONS')


def footprint(region, points):
    contours, hierarchy = cv2.findContours(region.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    area = 0.
    for contour, parent in zip(contours, hierarchy[0] if hierarchy is not None else []):
        uv = contour.reshape(-1, 2)
        polygon = points[uv[:, 1], uv[:, 0], :2].astype(np.float32)
        area += cv2.contourArea(polygon)*(1 if parent[3] == -1 else -1)
    xy = points[region, :2].astype(np.float32)
    hull = cv2.convexHull(xy).reshape(-1, 2)
    hull_area = cv2.contourArea(hull)
    return {'observed_area_m2': max(0., float(area)), 'hull_area_m2': hull_area,
            'rect_sides_m': sorted(float(s) for s in cv2.minAreaRect(hull)[1]),
            'footprint_solidity': min(1., max(0., area)/max(1e-12, hull_area))}


def metric_rejection(shape, options):
    if shape['observed_area_m2'] < options.minimum_observed_area_m2:
        return 'metric_area'
    short, long = shape['rect_sides_m']
    if short < .03 or short > .6*1.2 or long > 1.4*1.2:
        return 'metric_size'
    if shape['footprint_solidity'] < .25:
        return 'metric_shape'
    return None


def detect_floor_v3(rgb, *, servo, profile, options):
    if not isinstance(options, FloorGoalV3Options):
        raise ValueError('GOAL_V3_NEEDS_EXPLICIT_OPTIONS')
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('GOAL_REQUIRES_UINT8_RGB')
    mask = self_body_mask(servo, profile, rgb.shape[1], rgb.shape[0])
    filtered = rgb.copy()
    filtered[mask] = 0
    patches, labels, diagnostics = detect_floor_v2(filtered, servo=servo, profile=profile, options=options)
    diagnostics['self_mask_pixels'] = int(mask.sum())
    diagnostics['before_metric'] = len(patches)
    origin, axes = commanded_camera(servo, profile)
    points, _ = floor_intersections(optical_rays(rgb.shape[1], rgb.shape[0]), origin, axes,
                                    downward_min=options.downward_min, max_range_m=options.max_range_m)
    accepted, new_labels = [], np.zeros_like(labels)
    for patch in patches:
        region = labels == patch['component']
        shape = footprint(region, points)
        reason = metric_rejection(shape, options)
        if reason:
            diagnostics[reason] = diagnostics.get(reason, 0)+1
            continue
        patch.update(shape)
        patch['component'] = len(accepted)+1
        new_labels[region] = patch['component']
        accepted.append(patch)
    diagnostics['accepted'] = len(accepted)
    return accepted, new_labels, diagnostics


def compatible(last_hull, last_center, hull, center, options):
    residual = float(np.linalg.norm(last_center-center))
    if residual > options.temporal_center_max_m:
        return False, 'temporal_center', residual, 0.
    a, b = np.asarray(last_hull, np.float32), np.asarray(hull, np.float32)
    intersection, _ = cv2.intersectConvexConvex(a, b)
    overlap = float(intersection/max(1e-12, min(cv2.contourArea(a), cv2.contourArea(b))))
    return overlap >= options.temporal_overlap_min, 'temporal_overlap', residual, overlap


class FloorGoalMemoryV3(FloorGoalMemory):
    detector = staticmethod(detect_floor_v3)

    def __init__(self, robot_id, *, options=None):
        required = {'hue_low', 'hue_high', 'saturation_min', 'min_pixels', 'minimum_solidity',
                    'minimum_observed_area_m2', 'temporal_overlap_min', 'temporal_center_max_m'}
        if options is None or not required.issubset(options):
            raise ValueError('GOAL_V3_NEEDS_FROZEN_DEV_OPTIONS')
        selected = FloorGoalV3Options(**options)
        super().__init__(robot_id, options={f.name: getattr(selected, f.name) for f in fields(FloorGoalOptions)})
        self.options = selected

    def observe(self, rgb, *, robot_id, frame_id, t, pose, servo, profile, settled):
        if robot_id != self.robot_id:
            raise ValueError('GOAL_PEER_INPUT_FORBIDDEN')
        if not math.isfinite(t) or np.asarray(pose).shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('GOAL_NONFINITE_POSE_TIME')
        if frame_id in self.seen:
            raise ValueError('GOAL_DUPLICATE_FRAME')
        if t <= self.last_t:
            raise ValueError('GOAL_NON_MONOTONIC_TIME')
        if not settled:
            self.seen.add(frame_id)
            self.last_t = t
            return [], None, {'unsettled': 1}
        patches, labels, diagnostics = self.detector(rgb, servo=servo, profile=profile, options=self.options)
        self.seen.add(frame_id)
        self.last_t = t
        used = set()
        for patch in patches:
            center = transform([patch['center_body_m']], pose)[0]
            hull = transform(patch['hull_body_m'], pose)
            choices = []
            for track in self.tracks:
                if track['id'] in used:
                    continue
                if t-track['last_t'] > 3.:
                    diagnostics['temporal_gap'] = diagnostics.get('temporal_gap', 0)+1
                    continue
                ok, reason, residual, overlap = compatible(track['last_hull'], track['anchor_center'], hull, center, self.options)
                if ok:
                    choices.append((residual, track['id'], overlap))
                else:
                    diagnostics[reason] = diagnostics.get(reason, 0)+1
            if choices:
                residual, index, overlap = min(choices)
                track = self.tracks[index-1]
                patch.update(temporal_overlap=overlap, temporal_center_residual_m=residual)
            else:
                track = {'id': len(self.tracks)+1, 'cells': set(), 'box': np.array([hull.min(axis=0), hull.max(axis=0)]),
                         'views': {}, 'first_t': t, 'confirmed_t': None, 'quality_sum': 0., 'patches': 0,
                         'anchor_center': center.copy()}
                self.tracks.append(track)
                diagnostics['new_track'] = diagnostics.get('new_track', 0)+1
            used.add(track['id'])
            track['last_center'], track['last_hull'] = center, hull
            cells = np.floor(transform(patch.pop('_points_body_m'), pose)/self.options.cell_m).astype(int)
            track['cells'].update(tuple(x) for x in cells)
            track['box'] = np.array([np.minimum(track['box'][0], hull.min(axis=0)), np.maximum(track['box'][1], hull.max(axis=0))])
            track['views'][frame_id] = (t, tuple(pose))
            track['last_t'] = t
            track['quality_sum'] += patch['confidence']
            track['patches'] += 1
            views = list(track['views'].values())
            baseline = max(np.linalg.norm(np.array(p)[:2]-np.array(views[0][1])[:2]) for _, p in views)
            if len(views) >= 3 and t-track['first_t'] >= 2 and track['confirmed_t'] is None:
                if baseline >= .05:
                    track['confirmed_t'] = t
                else:
                    diagnostics['insufficient_translation'] = diagnostics.get('insufficient_translation', 0)+1
            patch.update(track_id=track['id'], center_odom_m=center.tolist(), hull_odom_m=hull.tolist(), confirmed_t=track['confirmed_t'])
        return patches, labels, diagnostics

    def snapshot(self):
        result = super().snapshot()
        result['confirmation_rule'] = 'v3: consecutive recent footprints, metric size, own translation >= .05 m'
        return result
