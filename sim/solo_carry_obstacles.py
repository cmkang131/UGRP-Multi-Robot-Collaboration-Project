"""Opt-in own-RGB obstacle memory. No scene/visibility/truth API is accepted.

Reuse catalogue colour contours, fisheye calibration and commanded camera FK.
Range is a floor/chassis-plane hypothesis, NOT measured depth. Inflated discs
and retained unseen tracks are conservative; recognition needs remote validation.
Held masking uses only the issued grasp and current arm commands, never cargo
world coordinates. Another object of the same colour remains observable.
"""
from __future__ import annotations

import math
import cv2
import numpy as np

from harness.zone_own_perception import APPEARANCE, hue_mask, _components, _frame_reference
from sim.grasp_act_solo_lookback import transforms, object_transform, _pixel_rays, _ray_box, project

PROFILE = 'solo_own_rgb_obstacles_v1'


def held_mask(kind, grasp_pwm, pwm, size=(640, 480)):
    from sim.grasp_act_solo_teacher import cargo
    obj = object_transform(kind, grasp_pwm, pwm)
    _, camera = transforms(pwm)
    rays = _pixel_rays(*size) @ camera[:3, :3].T
    entry, exit_ = _ray_box(camera[:3, 3], rays, obj[:3, 3],
                            np.asarray(cargo(kind).dims_m)/2+.008, obj[:3, :3])
    mask = (np.isfinite(entry) & (exit_ >= np.maximum(entry, 0.)) & (exit_ > 0.)).reshape(size[1], size[0])
    return cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)


def detections(bgr, pwm, *, held_kind=None, grasp_pwm=None):
    if bgr.shape != (480, 640, 3) or bgr.dtype != np.uint8:
        raise ValueError('native own RGB required for obstacle detection')
    _, cam = transforms(pwm)
    rays = (_pixel_rays(640, 480) @ cam[:3, :3].T).reshape(480, 640, 3)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    reference = _frame_reference(hsv)
    excluded = held_mask(held_kind, grasp_pwm, pwm) if held_kind is not None else np.zeros((480, 640), bool)
    masks = [(k, hue_mask(hsv, k, reference=reference), v) for k, v in APPEARANCE.items()]
    # Existing orange robot appearance extended through the yellow chassis band.
    masks.append(('robot', cv2.inRange(hsv, (5, 70, 40), (42, 255, 255)),
                  {'footprint_m': (.30, .30), 'height_m': .12}))
    out = []
    for kind, raw, spec in masks:
        raw = raw.copy(); raw[excluded] = 0
        comps, _ = _components(raw, 6. if kind != 'robot' else 20.)
        for comp in comps:
            x, y, w, h = comp['bbox']
            if x < 3 or y < 3 or x+w >= 637 or y+h >= 477:
                continue
            # A mask-cut contour is not a new object at the held mask boundary.
            if excluded[y:y+h, x:x+w].any():
                continue
            points = comp['contour'].reshape(-1, 2)
            band = points[points[:, 1] >= points[:, 1].max()-max(1., .12*h)]
            rr = rays[band[:, 1], band[:, 0]]
            plane = .06 if kind == 'robot' else 0.
            scale = (plane-cam[2, 3])/np.minimum(rr[:, 2], -1e-9)
            valid = (rr[:, 2] < -1e-4) & (scale > 0)
            if not valid.any():
                continue
            xy = np.median((cam[:3, 3]+scale[valid, None]*rr[valid])[:, :2], axis=0)
            distance = float(np.linalg.norm(xy))
            if not .28 <= distance <= 4.:
                continue  # self hardware / unsupported horizon
            hx, hy = np.asarray(spec['footprint_m'])/2
            corners = [[xy[0]+a, xy[1]+b, z] for a in (-hx, hx)
                       for b in (-hy, hy) for z in (0., spec['height_m'])]
            uv, front = project(corners, pwm)
            expected = float(np.ptp(uv, axis=0).max())
            ratio = max(w, h)/max(expected, 1.)
            if not front.all() or not .35 <= ratio <= 2.5:
                continue  # floor paint is much larger than catalogue geometry
            out.append({'kind': kind, 'xy': xy.tolist(), 'radius': math.hypot(hx, hy),
                        'range_error_m': .06+.08*distance, 'pixel_bbox': [x, y, w, h]})
    return out, int(excluded.sum())


class RGBObstacleMemory:
    def __init__(self):
        self.tracks = []
        self.holding = False
        self.frames = 0
        self.masked_pixels = 0
        self.last_t = None

    def update(self, observations, pose, now, *, holding=False, kind=None, grip_xy=None):
        x, y, a = pose; c, s = math.cos(a), math.sin(a)
        def world(q):
            return [x+c*q[0]-s*q[1], y+s*q[0]+c*q[1]]
        if holding and not self.holding and grip_xy is not None:
            target = world(grip_xy)
            # At most one observed pickup track; never all same-colour cargo.
            matches = [(math.dist(t['xy'], target), i) for i, t in enumerate(self.tracks) if t['kind'] == kind]
            if matches:
                d, i = min(matches)
                if d <= .20:
                    self.tracks.pop(i)
        self.holding = holding
        used = set()
        for ob in observations:
            q = {**ob, 'xy': world(ob['xy']), 'seen_t': float(now)}
            matches = [(math.dist(q['xy'], t['xy']), i) for i, t in enumerate(self.tracks)
                       if t['kind'] == q['kind'] and i not in used]
            if matches and min(matches)[0] <= .20:
                i = min(matches)[1]; self.tracks[i] = q; used.add(i)
            else:
                used.add(len(self.tracks)); self.tracks.append(q)
        self.last_t = float(now)

    def observe(self, bgr, pwm, pose, now, *, holding, kind, grasp_pwm):
        obs, masked = detections(bgr, pwm, held_kind=kind if holding else None, grasp_pwm=grasp_pwm)
        from harness.visual_arm_v3 import forward_grip
        grip = forward_grip(grasp_pwm)[:2] if grasp_pwm is not None else None
        self.update(obs, pose, now, holding=holding, kind=kind, grip_xy=grip)
        self.frames += 1; self.masked_pixels = masked

    def discs(self, now):
        # Unseen does not mean free. Keep pre-lift observations for the entire
        # finite diagnostic, inflating stale peer tracks instead of erasing them.
        from scripts.zone_teacher import PeerDisc
        # Never let A* release an observed non-held obstacle on failed replans.
        return [PeerDisc((*t['xy'], t['radius']+t['range_error_m']+
                 (min(.20, .01*max(0., now-t['seen_t'])) if t['kind'] == 'robot' else 0.)))
                for t in self.tracks]

    def record(self):
        return {'profile': PROFILE, 'frames': self.frames, 'last_t': self.last_t,
                'held_mask_pixels': self.masked_pixels, 'tracks': self.tracks,
                'source': 'own_rgb_issued_camera_fk_command_pose', 'truth_reads': 0,
                'range_calibrated': False, 'unseen_is_free': False}
