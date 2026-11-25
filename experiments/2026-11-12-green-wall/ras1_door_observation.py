"""Door jamb observations from the stopped ras1 wrist camera."""
import math

import cv2
import numpy as np

from green_wall_mapper import axes_for_floor_normal, camera_geometry


class CameraProjection:
    def __init__(self, lens, pose):
        model = lens.get('model', 'opencv_fisheye')
        self.use_raw = model == 'opencv_fisheye' and pose[3] == 500
        self.K = np.asarray(lens['K'], dtype=float)
        self.D = np.asarray(lens['D'], dtype=float)
        if self.K.shape != (3, 3) or not np.isfinite(self.K).all() or not np.isfinite(self.D).all():
            raise ValueError('invalid lens calibration')
        self.origin, self.axes = camera_geometry(pose)
        if self.origin[2] <= 0:
            raise ValueError('camera height is invalid for this posture')
        if model == 'opencv_fisheye':
            self.maps = cv2.fisheye.initUndistortRectifyMap(
                self.K, self.D, np.eye(3), self.K, (640, 480), cv2.CV_32FC1,
            )
        elif model == 'opencv_pinhole':
            self.maps = cv2.initUndistortRectifyMap(self.K, self.D, None, self.K, (640, 480), cv2.CV_32FC1)
        else:
            raise ValueError('unknown lens model')
        if 'floor_normal_camera' in lens:
            fitted = lens['pose']
            for joint in (4, 5):
                if pose[joint] != fitted[str(joint)]:
                    raise ValueError('floor profile posture differs from the camera posture')
            if pose[3] != fitted['3'] and (pose[3] not in (500, 650) or pose[6] != 1500):
                raise ValueError('floor profile has no model for this wrist posture')
            reference = dict(pose)
            reference[3] = fitted['3']
            _, mounting = camera_geometry(reference)
            yaw = math.atan2(mounting[1, 2], mounting[0, 2])
            c, s = math.cos(yaw), math.sin(yaw)
            fitted_axes = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]) @ axes_for_floor_normal(
                lens['floor_normal_camera'],
            )
            self.axes = fitted_axes @ mounting.T @ self.axes

    def rectify(self, image):
        return cv2.remap(image, *self.maps, cv2.INTER_LINEAR)

    def camera_extrinsics(self, _posture):
        return self.origin, self.axes.T

    def ground_pixels(self, points):
        ground = np.column_stack((points, np.zeros(len(points))))
        camera = (ground - self.origin) @ self.axes
        if np.any(camera[:, 2] <= 0):
            return None
        homogeneous = camera @ self.K.T
        return homogeneous[:, :2] / homogeneous[:, 2, None]


def panel_edges(blob, projection):
    rgb = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    if rgb is None or rgb.shape != (480, 640, 3):
        raise ValueError('expected a 640x480 camera image')
    near = getattr(projection, 'use_raw', False)
    if not near:
        rgb = projection.rectify(rgb)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
    seed = cv2.inRange(hsv, (55, 103, 4), (102 if near else 90, 255, 170))
    shadow = cv2.inRange(hsv, (86, 85, 3), (122 if near else 115, 255, 55))
    mask = cv2.bitwise_or(seed, shadow)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    panels = []
    for contour in contours:
        if cv2.contourArea(contour) < (650 if near else 4500):
            continue
        region = np.zeros_like(mask)
        cv2.drawContours(region, [contour], -1, 255, cv2.FILLED)
        if np.count_nonzero(seed & region) >= .045 * np.count_nonzero(region):
            panels.append(contour)
    panels.sort(key=lambda c: cv2.boundingRect(c)[0])
    picks = []
    for left, right in zip(panels, panels[1:]):
        left_box, right_box = cv2.boundingRect(left), cv2.boundingRect(right)
        inner_edges = []
        for panel, box, inside_edge in (
            (left, left_box, left_box[0] + left_box[2] - 1), (right, right_box, right_box[0]),
        ):
            dense = panel[:, 0]
            jamb_strip = dense[abs(dense[:, 0] - inside_edge) <= 9]
            foot_y = int(jamb_strip[:, 1].max())
            foot = jamb_strip[jamb_strip[:, 1] >= foot_y - 2]
            # The wall must continue above its near edge. A fixed straight
            # segment test fails on the bent/wide-angle outline of the panel.
            foot_x = int(np.median(foot[:, 0]))
            x0, x1 = max(0, foot_x-70), min(mask.shape[1], foot_x+70)
            y0, y1 = max(0, foot_y-110), max(0, foot_y-25)
            band = mask[y0:y1,x0:x1]
            supported_rows = np.count_nonzero(np.count_nonzero(band,axis=1) >= 12)
            inner_edges.append(np.median(foot, axis=0) if supported_rows >= (27 if near else 60) else None)
        if any(edge is None for edge in inner_edges):
            continue
        l, r = np.array(inner_edges, dtype=int)
        gap = r[0] - l[0]
        if gap < 40 or l[0] < 12 or r[0] > 627:
            continue
        columns = np.linspace(l[0] + gap*.25, r[0] - gap*.25, 13).astype(int)
        base = np.interp(columns, [l[0], r[0]], [l[1], r[1]]).astype(int)
        sample = [hsv[y - 12:y - 2, x] for x, y in zip(columns, base) if 12 <= y < rgb.shape[0]]
        if len(sample) != len(columns):
            continue
        sample = np.array(sample)
        if np.mean((sample[..., 1] < 100) & (sample[..., 2] > 45)) >= .60:
            picks.append([l.tolist(), r.tolist()])
    return rgb, picks


def geometry(blobs, projection):
    picks = [panel_edges(blob, projection)[1] for blob in blobs]
    samples = np.array([found[0] for found in picks if len(found) == 1])
    minimum = max(3, (3 * len(blobs) + 4) // 5)
    if len(samples) < minimum:
        raise ValueError('three or more agreeing door views needed')
    distance = np.linalg.norm(samples[:, None] - samples[None, :], axis=3).max(axis=2)
    groups = distance <= 8
    group = groups[int(np.argmax(groups.sum(axis=1)))]
    if np.count_nonzero(group) < minimum:
        raise ValueError('door edges moved between settled frames')
    pixels = np.median(samples[group], axis=0)
    rectified = pixels
    if getattr(projection,'use_raw',False):
        rectified = cv2.fisheye.undistortPoints(pixels[:,None,:],projection.K,projection.D,P=projection.K)[:,0]
    rays = np.column_stack((rectified, np.ones(len(pixels)))) @ np.linalg.inv(projection.K).T @ projection.axes.T
    if np.any(rays[:, 2] >= -.20):
        raise ValueError('door jamb feet are too near the horizon')
    points = projection.origin[:2] - projection.origin[2] * rays[:, :2] / rays[:, 2, None]
    center = points.mean(0)
    norm = float(np.linalg.norm(points[1] - points[0]))
    if not .06 <= norm <= .75:
        raise ValueError('door span inconsistent with the observed panels')
    tangent = (points[1] - points[0]) / norm
    toward = np.array([-tangent[1], tangent[0]])
    if toward @ center < 0:
        toward = -toward
    return dict(pixels=pixels.tolist(), jambs=points.tolist(), center=center.tolist(), toward=toward.tolist(),
                wall_plane_m=float(toward @ center), width_m=norm)

