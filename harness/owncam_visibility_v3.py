"""Conservative absence visibility from static calibration and own commands.

An enclosure covers the CONTINUOUS yaw interval, not just sampled headings.
Unknown self-occlusion rejects a miss; this is not an arm pixel segmentation.
"""
from __future__ import annotations

import math
import numpy as np

from harness.owncam_drive import SEARCH_POSE
from harness.visual_arm import CAMERA_LOCAL_X_CM, CAMERA_LOCAL_Z_CM, tool_pose

VISIBILITY_SIGMAS = 2.
SELF_CLEAR_MAX_TOOL_SLOPE = .5


def yaw_enclosure_radius(distance, yaw_half_width):
    """Maximum chord displacement over [-half_width, +half_width]."""
    return 2*distance*math.sin(min(yaw_half_width, math.pi)/2)


def _raw_projection_contracts(view, camera_points):
    """Certify raw fisheye lies between ideal pixels and the principal point.

    The camera transform is affine and ideal frustum inequalities are linear.
    Checking the support vertices therefore covers its interior too. Bound the
    fisheye radial polynomial on the whole angular interval (all extrema), so
    an interior raw-image extremum cannot escape between checked vertices.
    Unknown/expanding calibration rejects the miss rather than sampling it.
    """
    zmin = float(camera_points[:, 2].min())
    if zmin <= .05:
        return False
    rmax = float(np.linalg.norm(np.abs(camera_points[:, :2]).max(axis=0))/zmin)
    if rmax >= 8.:
        return False
    xmax = math.atan(rmax)**2
    poly = np.polynomial.Polynomial([1., *view.D.ravel()])
    extrema = [0., xmax]
    extrema += [float(r.real) for r in poly.deriv().roots()
                if abs(r.imag) < 1e-10 and 0 < r.real < xmax]
    values = poly(extrema)
    return bool(np.min(values) > 0. and np.max(values) <= 1. + 1e-12)


def self_arm_clear(pose, servo, points_w):
    """Accept only the open SEARCH posture's conservative clear ray cone.

    Static arm geometry (visual_arm / masterpi_scene_v2.xml): in SEARCH the
    shoulder/elbow/wrist stay behind the camera plane. The forward jaws lie
    below tool z=.0056 m; the lens surround starts at z=.016, ending at x=.070.
    Rays from (.067, 0, .0136) with tool slope in [0, .5] clear both. Reject the
    whole lower cone, including space between the fingers, and every other
    posture. This deliberately over-rejects; no encoder or live body pose used.
    """
    if any(servo.get(k, servo.get(str(k))) != SEARCH_POSE[k] for k in (1, 3, 4, 5)):
        return False
    if servo.get(6, servo.get('6')) is None:
        return False
    wrist = tool_pose(servo, tool_length_cm=0.)
    yaw, pitch = math.radians(wrist.yaw_left_deg), math.radians(wrist.pitch_deg)
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    axes = np.array([[cy*cp, sy*cp, sp], [-sy, cy, 0.], [-cy*sp, -sy*sp, cp]])
    c, s = math.cos(pose[2]), math.sin(pose[2])
    pts = np.asarray(points_w, float).copy()
    dx, dy = pts[:, 0]-pose[0], pts[:, 1]-pose[1]
    pts[:, 0], pts[:, 1] = c*dx+s*dy, -s*dx+c*dy
    tool = (pts - [wrist.x_m, wrist.y_m, wrist.z_m]) @ axes.T
    forward = tool[:, 0] - CAMERA_LOCAL_X_CM/100.
    up = tool[:, 2] - CAMERA_LOCAL_Z_CM/100.
    # Linear inequalities cover all rays to the convex support, not just one
    # centre pixel. No reliance on seeing a foreground object with the detector.
    return bool(np.all((forward > 0.) & (up >= -1e-12)
                       & (up <= SELF_CLEAR_MAX_TOOL_SLOPE*forward + 1e-12)))


def absence_visible(view, tr, pose, cov, servo, rows, *, box_half, box_z, max_range):
    cov = np.asarray(cov, float)
    if cov.shape != (3, 3) or not np.isfinite(cov).all() or not np.isfinite(pose).all():
        return False
    if not np.allclose(cov, cov.T) or np.linalg.eigvalsh(cov).min() < -1e-12:
        return False
    xy_sigma = math.sqrt(max(0., float(np.linalg.eigvalsh(cov[:2, :2]).max())))
    yaw_half = VISIBILITY_SIGMAS*math.sqrt(max(0., float(cov[2, 2])))
    # Independent worst-case bounds (sum, not RSS): every translation and yaw
    # in the stated marginal k-sigma support is covered, including correlation.
    target_radius = math.sqrt(2.)*box_half + VISIBILITY_SIGMAS*tr.sigma_m()
    translation_radius = VISIBILITY_SIGMAS*xy_sigma
    yaw_radius = yaw_enclosure_radius(float(np.linalg.norm(tr.x-np.asarray(pose[:2]))), yaw_half)
    radius = target_radius + translation_radius + yaw_radius
    offsets = np.array([(0, 0), (-1, -1), (-1, 1), (1, -1), (1, 1)])*radius
    pts = np.column_stack((tr.x + offsets, np.full(len(offsets), box_z)))
    cam = view.camera_world(pose, servo)
    cam_radius = translation_radius + yaw_enclosure_radius(float(np.linalg.norm(cam[:2]-pose[:2])), yaw_half)
    if np.linalg.norm(tr.x-cam[:2]) + target_radius + cam_radius > max_range:
        return False
    # Express uncertain headings as rotated target points at the mean heading;
    # the radius encloses the complete rotation arc, including interior extrema.
    if not all(view.point_in_view(pose, servo, False, p) for p in pts):
        return False
    camera_points = view.to_camera(pts, np.asarray(pose), servo, False)[0]
    if not _raw_projection_contracts(view, camera_points) or not self_arm_clear(pose, servo, pts):
        return False
    # The world-space AABB contains ALL rays from the uncertain camera origin
    # to the box support. Any intersecting wall/foreground envelope defers the
    # miss (even low walls). This also catches occluders between sample rays.
    lo = np.minimum(cam[:2]-cam_radius, tr.x-target_radius)
    hi = np.maximum(cam[:2]+cam_radius, tr.x+target_radius)
    obstacles = [(c, h) for c, h, _ in view.occluders]
    obstacles += [(np.asarray(r['map_xy']), .03 + VISIBILITY_SIGMAS*r['sigma_m']) for r in rows]
    return not any(np.all(np.asarray(c)+h >= lo) and np.all(np.asarray(c)-h <= hi)
                   for c, h in obstacles)
