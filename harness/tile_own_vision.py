"""T05 candidate: tile cues from own wrist BGR and issued PWM, using v3 FK.

Thresholds are development hypotheses, not calibrated detector accuracy. A
magenta floor patch with exactly the same projection is not distinguishable in
one frame: acquisition is a hypothesis; only post-lift frames may imply holding.
No runtime scene, segmentation, contact, item ID or partner state is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from harness import visual_arm_v3 as arm
from harness.zone_own_perception_v3 import _pixel_rays, _ray_box, _rot_z
from harness.zone_own_perception_v3_1 import image_information
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

PROFILE = 'tile-own-v3-fk-dev1'
DIMENSIONS_M = (.060, .040, .012)
MASS_KG = .025
GRASP_HEIGHT_M = .007


@dataclass(frozen=True)
class TileView:
    target_xy_m: tuple[float, float] | None = None
    target_reason: str = 'TILE_NOT_OBSERVED'
    holding: str = 'unknown'
    holding_reason: str = 'GRASP_NOT_ATTEMPTED'


def tile_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (150, 110, 55), (168, 255, 255)) > 0


def floor_target(bgr, pose):
    """Small slab at its known top-plane height; west-aligned close view only.

    The long edge must lie along own forward axis (modulo pi); the commanded
    heading's alignment with the map west role is the navigation caller's job.
    No candidate selection from setup identity or nearest private item lookup.
    """
    h, w = bgr.shape[:2]
    mask = tile_mask(bgr)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    origin, axes = (np.asarray(v, float) for v in arm.camera_extrinsics(pose))
    k, d = scaled_camera_matrix(w, h), np.asarray(CAMERA_FISHEYE_D).reshape(4, 1)
    candidates = []
    for contour in contours:
        if cv2.contourArea(contour) < 70:
            continue
        x, y, width, height = cv2.boundingRect(contour)
        if min(x, y) < 3 or x + width >= w - 3 or y + height >= h - 3:
            continue
        norm = cv2.fisheye.undistortPoints(contour.astype(float), k, d).reshape(-1, 2)
        rays = np.column_stack((norm, np.ones(len(norm)))) @ axes
        if np.any(rays[:, 2] >= -1e-5):
            continue
        distances = (DIMENSIONS_M[2] - origin[2]) / rays[:, 2]
        if np.any(distances <= 0):
            continue
        points = (origin + distances[:, None] * rays)[:, :2].astype(np.float32)
        rect = cv2.minAreaRect(points)
        corners = cv2.boxPoints(rect)
        edges = np.roll(corners, -1, axis=0) - corners
        lengths = np.linalg.norm(edges, axis=1)
        long = edges[int(np.argmax(lengths))]
        yaw = math.atan2(float(long[1]), float(long[0]))
        along, across = float(max(rect[1])), float(min(rect[1]))
        fill = cv2.contourArea(points) / max(along * across, 1e-9)
        if not (.045 <= along <= .075 and .030 <= across <= .050
                and along / max(across, 1e-9) >= 1.25 and fill >= .75
                and abs(math.sin(yaw)) <= math.sin(math.radians(15))):
            continue
        cx, cy = (float(v) for v in rect[0])
        if .12 <= cx <= .40 and abs(cy) <= .08:
            candidates.append((cx, cy))
    if len(candidates) == 1:
        return candidates[0], 'TILE_FLOOR_HYPOTHESIS'
    return None, 'TILE_AMBIGUOUS' if candidates else 'TILE_NOT_OBSERVED'


def grip_mask(grasp_pose, size):
    """Static rigid-hold prediction, not a rendering or measured joint pose.

    Camera and hypothetical held tile are rigid relative to the tool; use the
    issued grasp posture even after lifting. Physical pad geometry is v3, not
    the SDK virtual tip. The catalogue's west contact is 7 mm above the floor.
    """
    w, h = size
    origin, axes = (np.asarray(v, float) for v in arm.camera_extrinsics(grasp_pose))
    grip = np.asarray(arm.forward_grip(grasp_pose))
    yaw = math.radians(arm.tool_pose(grasp_pose).yaw_left_deg)
    centre = grip + np.array((0., 0., DIMENSIONS_M[2] / 2 - GRASP_HEIGHT_M))
    rays = _pixel_rays(w, h) @ axes
    enter, leave = _ray_box(origin, rays, centre, np.array(DIMENSIONS_M) / 2, _rot_z(yaw))
    return (np.isfinite(enter) & np.isfinite(leave) & (leave >= enter) & (enter >= .01)).reshape(h, w)


def holding_judgment(bgr, grasp_pose):
    nominal = grip_mask(grasp_pose, (bgr.shape[1], bgr.shape[0]))
    if nominal.sum() < 120 or nominal.mean() > .95:
        return 'unknown', 'TILE_NOT_FRAMED_AT_GRIP'
    band = cv2.dilate(nominal.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    ring = (cv2.dilate(band.astype(np.uint8), np.ones((21, 21), np.uint8)) > 0) & ~band
    colour = tile_mask(bgr)
    fill = float((colour & nominal).sum()) / nominal.sum()
    containment = float((colour & band).sum()) / max(int(colour.sum()), 1)
    # A painted background extending beyond the hypothetical tile is not a hold.
    boundary = ring.sum() >= 200 and float((colour & ring).sum()) / ring.sum() <= .10
    if fill >= .60 and containment >= .75 and boundary:
        return 'yes', 'TILE_AT_GRIP_RGB'
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    if float((colour & band).sum()) / band.sum() <= .01 and (hsv[..., 2][band] > 55).mean() >= .8:
        return 'no', 'TILE_ABSENT_AT_GRIP_RGB'
    return 'unknown', 'TILE_GRIP_AMBIGUOUS'


def inspect(bgr, issued_pose, *, grasp_pose=None):
    if not image_information(bgr)['sufficient']:
        return TileView(target_reason='OWN_IMAGE_UNINFORMATIVE', holding_reason='OWN_IMAGE_UNINFORMATIVE')
    target, reason = floor_target(bgr, issued_pose)
    held, held_reason = ('unknown', 'GRASP_NOT_ATTEMPTED') if grasp_pose is None else holding_judgment(bgr, grasp_pose)
    return TileView(target, reason, held, held_reason)
