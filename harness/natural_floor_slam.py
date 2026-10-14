"""Sparse SLAM from natural floor texture and issued wheel commands.

The map starts empty in ``<robot_id>/natural_floor_origin``.  Runtime inputs
are restricted to the robot's own RGB, fixed camera calibration and issued
commands; a supplied/static map, fiducial and evaluation pose are deliberately
absent from this API.

ORB describes floor pixels, while the calibrated floor-plane intersection
provides metric 2-D observations.  Descriptor correspondences are accepted
only after a rigid SE(2) RANSAC check.  Issued motion is a prediction, never a
measurement: if visual geometry is unavailable the pose remains explicitly
``command_only`` and its covariance grows.  Unknown vision is not zero motion.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math

import cv2
import numpy as np


def wrap(angle):
    return (float(angle) + math.pi) % (2 * math.pi) - math.pi


def compose(a, b):
    """Compose world-from-body pose ``a`` with a body-frame SE(2) delta."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array([a[0] + c*b[0] - s*b[1],
                     a[1] + s*b[0] + c*b[1], wrap(a[2] + b[2])])


def transform(points, pose):
    points, pose = np.asarray(points, float), np.asarray(pose, float)
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return points @ np.array([[c, s], [-s, c]]) + pose[:2]


@dataclass(frozen=True)
class Options:
    features: int = 800
    ratio: float = .75
    min_matches: int = 8
    min_inliers: int = 6
    global_min_inliers: int = 12
    min_inlier_fraction: float = .60
    ransac_threshold_m: float = .025
    ransac_iterations: int = 300
    min_spread_m: float = .025
    local_gate_m: float = .40
    landmark_spacing_m: float = .025
    keyframe_translation_m: float = .15
    keyframe_yaw_deg: float = 10.
    observation_sigma_m: float = .005
    max_landmarks: int = 5000

    def __post_init__(self):
        if (type(self.features) is not int or type(self.min_matches) is not int or
                type(self.min_inliers) is not int or type(self.global_min_inliers) is not int or
                type(self.ransac_iterations) is not int or type(self.max_landmarks) is not int):
            raise ValueError('NATURAL_FLOOR_INTEGER_OPTIONS_REQUIRED')
        if min(self.features, self.min_matches, self.min_inliers,
               self.global_min_inliers, self.ransac_iterations, self.max_landmarks) <= 0:
            raise ValueError('NATURAL_FLOOR_POSITIVE_OPTIONS_REQUIRED')
        if not 0 < self.ratio < 1 or not 0 < self.min_inlier_fraction <= 1:
            raise ValueError('NATURAL_FLOOR_INVALID_RATIO')
        positive = (self.ransac_threshold_m, self.min_spread_m, self.local_gate_m,
                    self.landmark_spacing_m, self.keyframe_translation_m,
                    self.keyframe_yaw_deg, self.observation_sigma_m)
        if any(not math.isfinite(x) or x <= 0 for x in positive):
            raise ValueError('NATURAL_FLOOR_INVALID_SCALE')


@dataclass(frozen=True)
class Observation:
    frame_id: int
    t: float
    points_body: np.ndarray
    descriptors: np.ndarray
    sha256: str = ''

    def checked(self):
        points = np.asarray(self.points_body, float)
        desc = np.asarray(self.descriptors, np.uint8)
        if (type(self.frame_id) is not int or not math.isfinite(self.t) or
                points.ndim != 2 or points.shape[1:] != (2,) or
                desc.ndim != 2 or desc.shape != (len(points), 32) or
                not np.isfinite(points).all()):
            raise ValueError('INVALID_NATURAL_FLOOR_OBSERVATION')
        return points, desc


@dataclass
class Landmark:
    landmark_id: int
    position: np.ndarray
    descriptor: np.ndarray
    observations: int
    first_frame: int
    last_frame: int


def extract(rgb, servo, *, frame_id, t, sha256='', options=None):
    """Extract metric natural-floor features using the existing calibration.

    This adapter intentionally uses the map-free floor mask.  It never invokes
    the optional static-wall masking modes in :mod:`harness.e2e_vo_floor_mask`.
    """
    from harness.e2e_rgb_vo import HEIGHT, WIDTH, ground, image_mask

    o = options if isinstance(options, Options) else Options(**(options or {}))
    image = np.asarray(rgb)
    if image.shape != (HEIGHT, WIDTH, 3) or image.dtype != np.uint8:
        raise ValueError('NATURAL_FLOOR_REQUIRES_640X480_UINT8_RGB')
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    keypoints, desc = cv2.ORB_create(nfeatures=o.features).detectAndCompute(
        gray, image_mask(image, servo))
    if desc is None or not keypoints:
        return Observation(int(frame_id), float(t), np.empty((0, 2)),
                           np.empty((0, 32), np.uint8), sha256)
    uv = np.asarray([p.pt for p in keypoints], np.float64)
    points, depth = ground(servo, uv)
    valid = np.isfinite(points).all(1) & np.isfinite(depth) & (depth > 0)
    return Observation(int(frame_id), float(t), points[valid], desc[valid], sha256)


def _matches(a, b, ratio):
    """Mutual ratio-checked Hamming matches as ``(a_index, b_index)``."""
    if len(a) < 2 or len(b) < 2:
        return []
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    forward = {m.queryIdx: m.trainIdx for pair in matcher.knnMatch(a, b, k=2)
               if len(pair) == 2 for m, n in [pair] if m.distance < ratio*n.distance}
    reverse = {m.queryIdx: m.trainIdx for pair in matcher.knnMatch(b, a, k=2)
               if len(pair) == 2 for m, n in [pair] if m.distance < ratio*n.distance}
    return [(i, j) for i, j in forward.items() if reverse.get(j) == i]


def _rigid(before, after):
    """Fit ``before = R @ after + t`` for row-vector point arrays."""
    a, b = before.mean(0), after.mean(0)
    u, _, vt = np.linalg.svd((before-a).T @ (after-b))
    rot = u @ np.diag([1., np.linalg.det(u @ vt)]) @ vt
    return rot, a-rot @ b


def _ransac(world, body, options, seed):
    if len(world) < options.min_inliers:
        return None
    rng = np.random.default_rng(seed)
    best = np.zeros(len(world), bool)
    best_error = math.inf
    for _ in range(options.ransac_iterations):
        index = rng.choice(len(world), 2, replace=False)
        if np.linalg.norm(body[index[0]]-body[index[1]]) < options.min_spread_m:
            continue
        rot, delta = _rigid(world[index], body[index])
        error = np.linalg.norm(world-(body @ rot.T+delta), axis=1)
        inside = error < options.ransac_threshold_m
        cost = float(error[inside].sum())
        if inside.sum() > best.sum() or (inside.sum() == best.sum() and cost < best_error):
            best, best_error = inside, cost
    if best.sum() < options.min_inliers or best.mean() < options.min_inlier_fraction:
        return None
    rot, delta = _rigid(world[best], body[best])
    error = np.linalg.norm(world-(body @ rot.T+delta), axis=1)
    inside = error < options.ransac_threshold_m
    if inside.sum() < options.min_inliers or inside.mean() < options.min_inlier_fraction:
        return None
    rot, delta = _rigid(world[inside], body[inside])
    spread = float(np.linalg.svd(body[inside]-body[inside].mean(0),
                                 compute_uv=False)[-1]/math.sqrt(inside.sum()))
    if spread < options.min_spread_m:
        return None
    residual = world[inside]-(body[inside] @ rot.T+delta)
    return rot, delta, inside, residual, spread


def _motion_covariance(pose, body_delta, covariance, command_covariance):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    dx = c*body_delta[0]-s*body_delta[1]
    dy = s*body_delta[0]+c*body_delta[1]
    F = np.array([[1., 0., -dy], [0., 1., dx], [0., 0., 1.]])
    R = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    return F @ covariance @ F.T + R @ command_covariance @ R.T


class NaturalFloorSLAM:
    """Online sparse landmark map in an arbitrary, robot-owned start frame."""

    def __init__(self, robot_id, *, options=None):
        if not robot_id or not isinstance(robot_id, str):
            raise ValueError('NATURAL_FLOOR_ROBOT_ID_REQUIRED')
        self.robot_id = robot_id
        self.options = options if isinstance(options, Options) else Options(**(options or {}))
        self.pose = np.zeros(3)
        self.covariance = np.zeros((3, 3))
        self.landmarks = {}
        self.trajectory = []
        self.keyframes = []
        self.events = []
        self._next_landmark = 0
        self._last_frame = -1
        self._last_t = -math.inf

    def _landmark_arrays(self):
        ids = sorted(self.landmarks)
        if not ids:
            return ids, np.empty((0, 2)), np.empty((0, 32), np.uint8)
        return (ids, np.asarray([self.landmarks[i].position for i in ids]),
                np.asarray([self.landmarks[i].descriptor for i in ids], np.uint8))

    def _fit(self, points, descriptors, prior, frame_id):
        ids, world, bank = self._landmark_arrays()
        pairs = _matches(descriptors, bank, self.options.ratio)
        base = dict(matches=len(pairs), inliers=0, fit_rms_m=None, spread_m=None)
        if len(pairs) < self.options.min_matches:
            return None, pairs, dict(base, reason='insufficient_matches')
        oi, li = np.asarray(pairs).T
        predicted = transform(points[oi], prior)
        local = np.linalg.norm(predicted-world[li], axis=1) <= self.options.local_gate_m

        def attempt(use, minimum):
            if int(use.sum()) < max(self.options.min_matches, minimum):
                return None
            fit = _ransac(world[li[use]], points[oi[use]], self.options, frame_id)
            if fit is None:
                return None
            rot, delta, inside, residual, spread = fit
            chosen = np.flatnonzero(use)[inside]
            yaw = wrap(math.atan2(rot[1, 0], rot[0, 0]))
            pose = np.array([delta[0], delta[1], yaw])
            rotated = points[oi[chosen]] @ rot.T
            J = np.zeros((2*len(chosen), 3))
            J[::2, 0] = 1.; J[1::2, 1] = 1.
            J[::2, 2] = -rotated[:, 1]; J[1::2, 2] = rotated[:, 0]
            sigma2 = max(float(np.sum(residual**2)/max(1, 2*len(chosen)-3)),
                         self.options.observation_sigma_m**2)
            covariance = sigma2*np.linalg.inv(J.T @ J)
            return pose, covariance, chosen, residual, spread

        fit = attempt(local, self.options.min_inliers)
        source = 'visual_update'
        if fit is None:
            fit = attempt(np.ones(len(pairs), bool), self.options.global_min_inliers)
            source = 'visual_relocalized'
        if fit is None:
            return None, pairs, dict(base, reason='no_rigid_consensus')
        pose, covariance, chosen, residual, spread = fit
        matched = [(int(oi[k]), ids[int(li[k])]) for k in chosen]
        details = dict(base, reason=source, matches=len(pairs), inliers=len(chosen),
                       fit_rms_m=float(np.sqrt(np.mean(residual**2))), spread_m=spread,
                       matched=matched, covariance=covariance)
        return pose, pairs, details

    def _add_landmarks(self, points, descriptors, pose, frame_id, matched_observations):
        world = transform(points, pose)
        occupied = [lm.position for lm in self.landmarks.values()]
        added = 0
        for index, (point, descriptor) in enumerate(zip(world, descriptors)):
            if index in matched_observations or len(self.landmarks) >= self.options.max_landmarks:
                continue
            if occupied and np.linalg.norm(np.asarray(occupied)-point, axis=1).min() < self.options.landmark_spacing_m:
                continue
            landmark_id = self._next_landmark
            self._next_landmark += 1
            self.landmarks[landmark_id] = Landmark(landmark_id, point.copy(), descriptor.copy(),
                                                   1, frame_id, frame_id)
            occupied.append(point.copy())
            added += 1
        return added

    def _update_landmarks(self, points, pose, frame_id, matched):
        world = transform(points, pose)
        for observation_index, landmark_id in matched:
            landmark = self.landmarks[landmark_id]
            # A bounded running mean smooths pixel noise without letting a long
            # trajectory rewrite the start-frame anchor indefinitely.
            weight = min(landmark.observations, 9)
            landmark.position = (weight*landmark.position+world[observation_index])/(weight+1)
            landmark.observations += 1
            landmark.last_frame = frame_id

    def _keyframe_due(self, pose, source):
        if not self.keyframes or source == 'visual_relocalized':
            return True
        previous = np.asarray(self.keyframes[-1]['pose'])
        return (np.linalg.norm(pose[:2]-previous[:2]) >= self.options.keyframe_translation_m or
                abs(wrap(pose[2]-previous[2])) >= math.radians(self.options.keyframe_yaw_deg))

    def step(self, observation, *, command_delta, command_covariance):
        """Advance one RGB frame; ``command_delta`` covers the previous frame interval."""
        points, descriptors = observation.checked()
        if observation.frame_id <= self._last_frame or observation.t <= self._last_t:
            raise ValueError('CAUSAL_NATURAL_FLOOR_FRAMES_REQUIRED')
        delta = np.asarray(command_delta, float)
        Q = np.asarray(command_covariance, float)
        if (delta.shape != (3,) or Q.shape != (3, 3) or not np.isfinite(delta).all() or
                not np.isfinite(Q).all() or not np.allclose(Q, Q.T) or
                np.linalg.eigvalsh(Q).min() < -1e-12):
            raise ValueError('FINITE_COMMAND_MOTION_AND_COVARIANCE_REQUIRED')
        prior_pose = compose(self.pose, delta)
        prior_covariance = _motion_covariance(self.pose, delta, self.covariance, Q)
        matched = []
        if not self.landmarks:
            self.pose, self.covariance = prior_pose, prior_covariance
            source, reason = 'bootstrap', 'empty_map_origin'
            added = self._add_landmarks(points, descriptors, self.pose, observation.frame_id, set())
            visual = dict(matches=0, inliers=0, fit_rms_m=None, spread_m=None)
        else:
            estimate, _, visual = self._fit(points, descriptors, prior_pose, observation.frame_id)
            if estimate is None:
                self.pose, self.covariance = prior_pose, prior_covariance
                source, reason, added = 'command_only', visual['reason'], 0
            else:
                self.pose, measurement_covariance, matched, = estimate, visual['covariance'], visual['matched']
                self.covariance = measurement_covariance
                source, reason = visual['reason'], visual['reason']
                self._update_landmarks(points, self.pose, observation.frame_id, matched)
                added = self._add_landmarks(points, descriptors, self.pose, observation.frame_id,
                                            {i for i, _ in matched})
        keyframe = bool(len(points) and source != 'command_only' and self._keyframe_due(self.pose, source))
        if keyframe:
            self.keyframes.append(dict(frame_id=observation.frame_id, t=float(observation.t),
                                       pose=self.pose.tolist(), sha256=observation.sha256,
                                       features=len(points), source=source))
        event = dict(frame_id=observation.frame_id, t=float(observation.t), status=source,
                     reason=reason, pose=self.pose.tolist(), covariance=self.covariance.tolist(),
                     command_delta=delta.tolist(), features=len(points), matches=visual['matches'],
                     inliers=visual['inliers'], fit_rms_m=visual['fit_rms_m'],
                     spread_m=visual['spread_m'], landmarks_added=added,
                     landmark_count=len(self.landmarks), keyframe=keyframe)
        self.events.append(event)
        self.trajectory.append(dict(frame_id=observation.frame_id, t=float(observation.t),
                                    pose=self.pose.tolist(), covariance=self.covariance.tolist(),
                                    source=source))
        self._last_frame, self._last_t = observation.frame_id, observation.t
        return event

    def snapshot(self, *, include_descriptors=False):
        landmarks = []
        for landmark_id in sorted(self.landmarks):
            lm = self.landmarks[landmark_id]
            row = dict(id=lm.landmark_id, position_m=lm.position.tolist(),
                       observations=lm.observations, first_frame=lm.first_frame,
                       last_frame=lm.last_frame)
            if include_descriptors:
                row['descriptor_hex'] = lm.descriptor.tobytes().hex()
            landmarks.append(row)
        return dict(schema='ugrp.natural_floor_slam.v1', robot_id=self.robot_id,
                    coordinate_frame=self.robot_id+'/natural_floor_origin', started_empty=True,
                    runtime_inputs=['own_rgb', 'issued_wheel_commands', 'fixed_camera_calibration'],
                    options=asdict(self.options), pose=self.pose.tolist(),
                    covariance=self.covariance.tolist(), landmarks=landmarks,
                    keyframes=list(self.keyframes), trajectory=list(self.trajectory),
                    status_counts=dict(Counter(e['status'] for e in self.events)))
