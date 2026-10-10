"""Default-off, own-image Manhattan pitch. No map, telemetry or truth input.

The Lu/Phan implementation is vendored byte-for-byte. The adapter handles its
single focal length convention, degenerate images, axis signs and abstention.
Input image must already be undistorted with the supplied K. See egomap13.
"""
from __future__ import annotations

import numpy as np

OPTION = 'online_vp_v1'
PARAMETERS = dict(length_px=30, seed=1337, axis_limit_deg=30,
                  cluster_deg=6, min_vertical_lines=2, min_other_lines=2)
AXES = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]])


def rotation_with_pitch(rotation, gravity):
    """Signed upward camera ray -> elevation; retain calibrated yaw and roll."""
    from scipy.spatial.transform import Rotation
    a = Rotation.from_matrix(np.asarray(rotation) @ AXES.T).as_euler('ZYX')
    g = np.asarray(gravity, float)
    g = g / np.linalg.norm(g)
    a[1] = -np.arcsin(np.clip(g[2], -1., 1.))
    return Rotation.from_euler('ZYX', a).as_matrix() @ AXES


def _support(lines, vps, principal, focal):
    # Same midpoint-to-VP acute angle as upstream __cluster_lines, without GUI.
    midpoint = (lines[:, :2] + lines[:, 2:]) / 2
    direction = lines[:, :2] - lines[:, 2:]
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    # Homogeneous form also works for vanishing points at infinity.
    rays = focal * vps[:, None, :2] + (principal - midpoint)[None] * vps[:, None, 2:]
    norms = np.linalg.norm(rays, axis=2)
    cosine = np.divide(np.einsum('vnc,nc->vn', rays, direction), norms,
                       out=np.zeros_like(norms), where=norms > 1e-12)
    angles = np.arccos(np.clip(np.abs(cosine), 0., 1.))
    labels = np.argmin(angles, axis=0)
    valid = np.min(angles, axis=0) <= np.radians(PARAMETERS['cluster_deg'])
    return [int(np.sum(valid & (labels == i))) for i in range(3)]


def correct_rotation(undistorted_bgr, intrinsics, nominal_rotation, *, camera_pitch='off'):
    """Return (rotation, diagnostics); abstention returns the exact old object."""
    if camera_pitch == 'off':
        return nominal_rotation, dict(option='off', accepted=False, reason='off')
    if camera_pitch != OPTION:
        raise ValueError('UNKNOWN_CAMERA_PITCH')
    import cv2
    from harness.vendor.lu_vp.vp_detection import VPDetection
    meta = dict(option=OPTION, accepted=False, reason='uninitialized')

    def abstain(reason):
        return nominal_rotation, {**meta, 'reason': reason}

    if undistorted_bgr is None:
        return abstain('missing_own_image')
    k = np.asarray(intrinsics, float)
    r = np.asarray(nominal_rotation, float)
    if (k.shape != (3, 3) or r.shape != (3, 3) or not np.isfinite(k).all()
            or not np.isfinite(r).all() or min(k[0, 0], k[1, 1]) <= 0):
        raise ValueError('INVALID_CAMERA_GEOMETRY')
    scale = k[1, 1] / k[0, 0]
    image = undistorted_bgr
    if scale != 1.:
        # x'=scale*x, no half-pixel resize offset in the calibrated coordinates.
        image = cv2.warpAffine(image, np.array([[scale, 0., 0.], [0., 1., 0.]]),
                               (int(np.ceil(image.shape[1] * scale)), image.shape[0]))
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    lines = cv2.createLineSegmentDetector(0).detect(grey)[0]
    if lines is None:
        return abstain('no_lines')
    # OpenCV 4 returns N x 1 x 4, OpenCV 5 returns N x 4. Same endpoints.
    lines = np.asarray(lines).reshape(-1, 4)
    lines = lines[np.linalg.norm(lines[:, :2] - lines[:, 2:], axis=1) >= PARAMETERS['length_px']]
    meta['lines'] = len(lines)
    if len(lines) < 2:
        return abstain('too_few_lines')
    direction = lines[:, 2:] - lines[:, :2]
    cross = direction[:, 0, None] * direction[None, :, 1] - direction[:, 1, None] * direction[None, :, 0]
    if not np.any(np.abs(cross) >= 1e-8):
        # Upstream retries parallel pairs indefinitely; never invoke on this input.
        return abstain('all_parallel')
    principal = np.array([k[0, 2] * scale, k[1, 2]])
    class VPFromLines(VPDetection):
        def _VPDetection__detect_lines(self, img):
            # Feed exactly the original LSD/filter result after API normalization.
            # Keep all upstream hypothesis, voting and ranking code unchanged.
            self._VPDetection__lines = lines
            return lines

    detector = VPFromLines(PARAMETERS['length_px'], principal, k[1, 1], PARAMETERS['seed'])
    with np.errstate(divide='ignore', invalid='ignore'):
        vps = np.asarray(detector.find_vps(image), float)
    if vps.shape != (3, 3) or not np.isfinite(vps).all():
        return abstain('nonfinite_vps')
    norms = np.linalg.norm(vps, axis=1)
    if np.any(norms < 1e-8):
        return abstain('degenerate_vps')
    vps /= norms[:, None]
    prior = r.T @ np.array([0., 0., 1.])
    dots = vps @ prior
    index = int(np.argmax(np.abs(dots)))
    angle = float(np.degrees(np.arccos(np.clip(abs(dots[index]), 0., 1.))))
    counts = _support(lines, vps, principal, k[1, 1])
    meta.update(vps=vps.tolist(), vertical_axis=index, axis_delta_deg=angle, support_lines=counts)
    if angle > PARAMETERS['axis_limit_deg']:
        return abstain('ambiguous_vertical_axis')
    if counts[index] < PARAMETERS['min_vertical_lines']:
        return abstain('insufficient_vertical_support')
    if max(counts[i] for i in range(3) if i != index) < PARAMETERS['min_other_lines']:
        return abstain('insufficient_other_axis_support')
    gravity = vps[index] * (1 if dots[index] >= 0 else -1)
    result = rotation_with_pitch(r, gravity)
    meta.update(accepted=True, reason='accepted', pitch_deg=float(np.degrees(np.arcsin(gravity[2]))))
    return result, meta
