"""Conservative can-only own-wrist RGB hypotheses, without a renderer.

Floor: fit a 38 x 50 mm upright cylinder, not a box or a colour centroid.
Held: the full cylinder is not framed by this wrist camera. Compare its visible
bottom rim with a commanded-tool hypothesis; the skill requires two different
lift heights before accepting attachment. These DEV thresholds have synthetic
tests only. Partial/ambiguous floor targets are refused, not repaired from GT.
"""
from __future__ import annotations

import base64
import math
from dataclasses import dataclass

import cv2
import numpy as np

from harness import markerless_box as optics  # projection math only; no box fit
from harness import visual_arm_v3 as arm
from harness.can_skill_registry import CAN
from harness.m1_owncam_contract import M1ContractError, validate_observation

SOURCE = 'own_robot_cam_jpeg+own_issued_pwm+v3_fk+catalogue_cylinder_v1'
MIN_IOU = .80
HUE_LOW, HUE_HIGH = (124, 110, 45), (139, 255, 255)


@dataclass(frozen=True)
class CanView:
    answer: str
    reason: str
    center_base_m: tuple | None = None
    iou: float = 0.
    source: str = SOURCE


def decode_own(obs, *, robot_id, previous_frame_id, now):
    """Decode the *hashed bytes*, never an unrelated caller-provided RGB array."""
    fid, stamp = obs.get('frame_id'), obs.get('sim_time')
    if (type(fid) is not int or fid < 0 or type(stamp) not in (int, float)
            or not math.isfinite(stamp) or not math.isfinite(now)
            or not 0 <= now - stamp <= .25):
        raise M1ContractError('invalid/future/stale own frame')
    validate_observation(obs, robot_id=robot_id, previous_frame_id=previous_frame_id, now=now)
    try:
        raw = base64.b64decode(obs['image'], validate=True)
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except (ValueError, TypeError, cv2.error) as exc:
        raise M1ContractError('invalid JPEG') from exc
    if frame is None or frame.shape[:2] != (480, 640):
        raise M1ContractError('can v1 requires the fixed 640x480 raw wrist image')
    return frame


def _camera(frame, pulses):
    origin, axes = arm.camera_extrinsics(pulses)
    return (np.asarray(origin), np.asarray(axes),
            optics.scaled_camera_matrix(frame.shape[1], frame.shape[0]),
            np.asarray(optics.CAMERA_FISHEYE_D).reshape(4, 1))


def _ring(x, y, z):
    angles = np.arange(64) * (2 * math.pi / 64)
    return np.column_stack((x + CAN.diameter_m / 2 * np.cos(angles),
                            y + CAN.diameter_m / 2 * np.sin(angles),
                            np.full(64, z)))


def cylinder_pixels(center, pulses, frame_shape=(480, 640, 3)):
    """Public analytic helper for inspection; no scene, instance ID or renderer."""
    x, y, bottom = center
    points = np.vstack((_ring(x, y, bottom), _ring(x, y, bottom + CAN.height_m)))
    return optics._project_points(points, *_camera(np.empty(frame_shape, np.uint8), pulses))


def _mask(frame):
    return cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV),
                       np.array(HUE_LOW, np.uint8), np.array(HUE_HIGH, np.uint8))


def _iou(observed, predicted):
    union = np.count_nonzero(observed | predicted)
    return float(np.count_nonzero(observed & predicted) / union) if union else 0.


def _polygon_mask(pixels, shape):
    mask = np.zeros(shape[:2], np.uint8)
    if pixels is not None and len(pixels) >= 3:
        cv2.fillConvexPoly(mask, cv2.convexHull(pixels.astype(np.float32)).astype(np.int32), 1)
    return mask.astype(bool)


def floor_can(frame, pulses):
    """One unoccluded near cylinder; center is conditional on the floor hypothesis."""
    mask = _mask(frame)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 60]
    if len(contours) != 1:
        return CanView('unknown', 'absent_or_multiple_can_regions')
    contour = contours[0]
    x, y, w, h = cv2.boundingRect(contour)
    if x < 5 or y < 5 or x + w > 635 or y + h > 475:
        return CanView('unknown', 'clipped_can')
    observed = mask.astype(bool)
    # A silhouette beside the optical-black rim is also clipped.
    edge = cv2.dilate(mask, np.ones((7, 7), np.uint8)) > 0
    if np.any(edge & (frame.max(axis=2) < 12)):
        return CanView('unknown', 'occluded_or_black_rim')
    convex = _polygon_mask(contour.reshape(-1, 2), frame.shape)
    if np.count_nonzero(observed & convex) / max(1, np.count_nonzero(convex)) < .94:
        return CanView('unknown', 'occluded_can')
    camera = _camera(frame, pulses)
    points = contour.reshape(-1, 2)
    band = points[points[:, 1] >= y + h - 1 - max(2, h * .04)]
    hits = [optics._pixel_ground_point(p, *camera) for p in band]
    hits = [p for p in hits if p is not None]
    if not hits:
        return CanView('unknown', 'unsupported_floor_ray')
    near = np.median(hits, axis=0)[:2]
    radial = near - camera[0][:2]
    seed = near + radial / max(np.linalg.norm(radial), 1e-9) * CAN.diameter_m / 2
    best = (0., None)
    # Fixed local search, not a learned correction or hidden position lookup.
    for half, count in ((.025, 9), (.004, 5)):
        center = seed if best[1] is None else best[1]
        for dx in np.linspace(-half, half, count):
            for dy in np.linspace(-half, half, count):
                xy = center + (dx, dy)
                if not .185 <= xy[0] <= .80 or abs(xy[1]) > .25:
                    continue
                pixels = optics._project_points(
                    np.vstack((_ring(*xy, 0.), _ring(*xy, CAN.height_m))), *camera)
                if pixels is None or np.any(pixels < 4) or np.any(pixels > (635, 475)):
                    continue
                score = _iou(observed, _polygon_mask(pixels, frame.shape))
                if score > best[0]:
                    best = (score, xy)
    if best[0] < MIN_IOU:
        return CanView('unknown', 'cylinder_projection_mismatch', iou=best[0])
    # Colour + a tolerable silhouette score is insufficient: a violet cuboid
    # also passed that gate. Require the cylinder to beat competing cuboids.
    # These are rejection hypotheses, never the can's geometry or thresholds.
    competing = 0.
    angles = np.arange(64) * (2 * math.pi / 64)
    radius = CAN.diameter_m / 2
    lying = np.asarray([(along, radius * math.sin(t), radius * (1 + math.cos(t)))
                        for along in (-CAN.height_m/2, CAN.height_m/2) for t in angles])
    for dx in (-.004, 0., .004):
        for dy in (-.004, 0., .004):
            for yaw in np.arange(6) * math.pi / 12:
                for dims in ((.038, .038, .050), (.034, .040, .032)):
                    pixels = optics._project_points(
                        optics._cuboid_corners(best[1] + (dx, dy), yaw, dims), *camera)
                    competing = max(competing, _iou(observed, _polygon_mask(pixels, frame.shape)))
            # An upright-only skill must also reject a can lying on its side.
            for yaw in np.arange(12) * math.pi / 12:
                c, s = math.cos(yaw), math.sin(yaw)
                rotation = np.asarray(((c, -s, 0.), (s, c, 0.), (0., 0., 1.)))
                points = lying @ rotation.T + (*list(best[1] + (dx, dy)), 0.)
                pixels = optics._project_points(points, *camera)
                competing = max(competing, _iou(observed, _polygon_mask(pixels, frame.shape)))
    if best[0] < competing + .025:
        return CanView('unknown', 'can_shape_or_upright_pose_ambiguous', iou=best[0])
    return CanView('yes', 'floor_cylinder_hypothesis', (*map(float, best[1]), CAN.height_m / 2), best[0])


def held_rim_mask(pulses, frame_shape=(480, 640, 3)):
    """Visible lower rim at the commanded pad site; full can is out of frame.

    Upright can / maintained wrist pitch is a hypothesis. Real gripper occlusion
    and contact slip are deliberately not inferred from commanded PWM.
    """
    x, y, z = arm.forward_grip(pulses)
    pixels = optics._project_points(_ring(x, y, z - CAN.grasp_height_m),
                                    *_camera(np.empty(frame_shape, np.uint8), pulses))
    return _polygon_mask(pixels, frame_shape)


def attached_can(frame, pulses):
    x, y, z = arm.forward_grip(pulses)
    if (pulses.get(1) != CAN.close_pwm or not .075 <= z <= .105
            or not .19 <= x <= .21 or abs(y) > .005
            or not -68 <= arm.tool_pose(pulses).pitch_deg <= -64):
        return CanView('unknown', 'unsupported_holding_pose')
    predicted = held_rim_mask(pulses, frame.shape)
    area = np.count_nonzero(predicted)
    if not 500 <= area <= frame.shape[0] * frame.shape[1] * .4:
        return CanView('unknown', 'held_rim_not_framed')
    score = _iou(_mask(frame).astype(bool), predicted)
    if score < MIN_IOU:
        return CanView('unknown', 'empty_wrong_or_unattached', iou=score)
    # A plausible complete floor can is never attachment evidence.
    if floor_can(frame, pulses).answer == 'yes':
        return CanView('unknown', 'floor_attachment_ambiguity', iou=score)
    return CanView('yes', 'held_rim_hypothesis_requires_two_lifts', iou=score)
