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
# Shared with carry5 scene parking: largest supported detected peer disc.
PEER_DISC_MAX_M = math.hypot(.15, .15)+.06+.08*4.+.20
MAHALANOBIS_GATE_2D = 9.21  # chi-square 99%, 2 DoF; assumed errors, not calibrated


def held_mask(kind, grasp_pwm, pwm, size=(640, 480)):
    from sim.grasp_act_solo_teacher import cargo
    obj = object_transform(kind, grasp_pwm, pwm)
    _, camera = transforms(pwm)
    rays = _pixel_rays(*size) @ camera[:3, :3].T
    entry, exit_ = _ray_box(camera[:3, 3], rays, obj[:3, 3],
                            np.asarray(cargo(kind).dims_m)/2+.008, obj[:3, :3])
    mask = (np.isfinite(entry) & (exit_ >= np.maximum(entry, 0.)) & (exit_ > 0.)).reshape(size[1], size[0])
    return cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)


def detections(bgr, pwm, *, held_kind=None, grasp_pwm=None, managed=False):
    if bgr.shape != (480, 640, 3) or bgr.dtype != np.uint8:
        raise ValueError('native own RGB required for obstacle detection')
    _, cam = transforms(pwm)
    rays = (_pixel_rays(640, 480) @ cam[:3, :3].T).reshape(480, 640, 3)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    reference = _frame_reference(hsv)
    excluded = held_mask(held_kind, grasp_pwm, pwm) if held_kind is not None else np.zeros((480, 640), bool)
    masks = [(k, hue_mask(hsv, k, reference=reference), v) for k, v in APPEARANCE.items()]
    # Existing orange robot appearance extended through the yellow chassis band.
    masks.append(('robot', cv2.inRange(hsv, (5, 70, 40), (20 if managed else 42, 255, 255)),
                  {'footprint_m': (.30, .30), 'height_m': .12}))
    out = []
    for kind, raw, spec in masks:
        raw = raw.copy(); raw[excluded] = 0
        comps, _ = _components(raw, 6. if kind != 'robot' else 20.)
        for comp in comps:
            x, y, w, h = comp['bbox']
            if x < 3 or y < 3 or x+w >= 637 or y+h >= 477:
                continue
            if managed and kind == 'robot':
                # Orange alone also describes zone A. Require adjoining dark
                # chassis/wheel evidence below it, with substantial vertical extent.
                below = hsv[y+h:min(480, y+h+max(4, h)), max(0, x-w//2):min(640, x+3*w//2)]
                if h < 4 or not below.size or np.mean((below[..., 1] < 90) & (below[..., 2] < 105)) < .30:
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
    def __init__(self, *, managed=False):
        self.managed = bool(managed)
        self.deleted = []
        self.next_id = 0
        self.tracks = []
        self.holding = False
        self.frames = 0
        self.masked_pixels = 0
        self.last_t = None

    def update(self, observations, pose, now, *, holding=False, kind=None, grip_xy=None, pose_sigma=(0., 0., 0.), clear_ids=()):
        if self.managed:
            return self._managed_update(observations, pose, now, holding=holding, kind=kind,
                                        grip_xy=grip_xy, pose_sigma=pose_sigma, clear_ids=clear_ids)
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

    def observe(self, bgr, pwm, pose, now, *, holding, kind, grasp_pwm, pose_sigma=(0., 0., 0.)):
        obs, masked = detections(bgr, pwm, held_kind=kind if holding else None, grasp_pwm=grasp_pwm, managed=self.managed)
        from harness.visual_arm_v3 import forward_grip
        grip = forward_grip(grasp_pwm)[:2] if grasp_pwm is not None else None
        self.update(obs, pose, now, holding=holding, kind=kind, grip_xy=grip, pose_sigma=pose_sigma,
                    clear_ids=self.clear_view_ids(bgr, pwm, pose, pose_sigma) if self.managed else ())
        self.frames += 1; self.masked_pixels = masked

    def _managed_update(self, observations, pose, now, *, holding, kind, grip_xy, pose_sigma, clear_ids):
        x, y, a = pose; c, s = math.cos(a), math.sin(a)
        R = np.array([[c, -s], [s, c]])
        def world(q):
            return (np.array([x, y])+R@q).tolist()
        if holding and not self.holding and grip_xy is not None:
            candidates = [(math.dist(t['xy'], world(grip_xy)), i) for i, t in enumerate(self.tracks) if t['kind'] == kind]
            if candidates:
                d, i = min(candidates)
                if d <= self.tracks[i]['radius']+self.tracks[i]['range_error_m']+.08:
                    self.deleted.append({'id': self.tracks[i]['id'], 't': now, 'reason': 'own_pickup'})
                    self.tracks.pop(i)
        self.holding = holding
        new = []
        for ob in observations:
            q = {**ob, 'xy': world(ob['xy']), 'seen_t': float(now)}
            v = R@np.asarray(ob['xy']); J = np.array([-v[1], v[0]])
            cov = (np.eye(2)*ob['range_error_m']**2 + np.diag(np.square(pose_sigma[:2]))
                   + np.outer(J, J)*pose_sigma[2]**2)
            q['covariance'] = cov.tolist()
            new.append(q)
        # Global greedy one-to-one distance assignment. Never collapse two same-frame detections.
        pairs = []
        for j, q in enumerate(new):
            for i, t in enumerate(self.tracks):
                if q['kind'] != t['kind']:
                    continue
                d = np.asarray(q['xy'])-t['xy']
                C = np.asarray(q['covariance'])+t['covariance']+np.eye(2)*1e-6
                d2 = float(d@np.linalg.solve(C, d))
                if d2 <= MAHALANOBIS_GATE_2D:
                    pairs.append((d2, i, j))
        used_i, used_j = set(), set()
        for d2, i, j in sorted(pairs):
            if i in used_i or j in used_j:
                continue
            old = self.tracks[i]
            # Observations share self-pose error: replace, do NOT shrink it by repeated fusion.
            self.tracks[i] = {**new[j], 'id': old['id'], 'hits': old['hits']+1,
                              'misses': 0, 'association_d2': d2}
            used_i.add(i); used_j.add(j)
        for i, t in enumerate(self.tracks):
            if i not in used_i and t['id'] in clear_ids:
                t['misses'] += 1
        keep = []
        for t in self.tracks:
            # Blind time alone never erases an obstacle. Three clear, fully projected
            # own-RGB opportunities after >=1 s are required to delete a ghost.
            if t['misses'] >= 3 and now-t['seen_t'] >= 1.:
                self.deleted.append({'id': t['id'], 't': now, 'reason': 'three_clear_own_rgb_views'})
            else:
                keep.append(t)
        self.tracks = keep
        for j, q in enumerate(new):
            if j not in used_j:
                self.tracks.append({**q, 'id': self.next_id, 'hits': 1, 'misses': 0})
                self.next_id += 1
        self.last_t = float(now)

    def clear_view_ids(self, bgr, pwm, pose, pose_sigma):
        # No clearing on an uncertain map projection or held occlusion. Only
        # neutral floor texture in the entire projected object/uncertainty box.
        if self.holding or max(pose_sigma[:2]) > .15 or pose_sigma[2] > math.radians(8.):
            return ()
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        x, y, a = pose; c, s = math.cos(a), math.sin(a); out = []
        for t in self.tracks:
            dx, dy = t['xy'][0]-x, t['xy'][1]-y
            bx, by = c*dx+s*dy, -s*dx+c*dy
            r = t['radius']+t['range_error_m']+max(pose_sigma[:2])
            uv, front = project([[bx+u, by+v, z] for u in (-r, r) for v in (-r, r)
                                 for z in (0., .16 if t['kind'] == 'robot' else .04)], pwm)
            if not front.all() or not np.isfinite(uv).all():
                continue
            lo = np.floor(uv.min(axis=0)).astype(int); hi = np.ceil(uv.max(axis=0)).astype(int)
            if not (8 <= lo[0] < hi[0] < 632 and 8 <= lo[1] < hi[1] < 472):
                continue
            patch = hsv[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
            # Coloured objects, dark occluders and flat paint cannot clear tracks.
            if np.mean((patch[..., 1] < 85) & (patch[..., 2] > 65)) >= .98 and patch[..., 2].std() > 8.:
                out.append(t['id'])
        return out

    def reanchor(self, before, after):
        """Keep observed relative geometry when a shared map-pose fix is accepted."""
        a = after[2]-before[2]; c, s = math.cos(a), math.sin(a)
        R = np.array([[c, -s], [s, c]])
        for t in self.tracks:
            t['xy'] = (np.array(after[:2])+R@(np.array(t['xy'])-before[:2])).tolist()
            if 'covariance' in t:
                t['covariance'] = (R@t['covariance']@R.T).tolist()

    def pickup_discs(self, now, pose, kind, target):
        from scripts.zone_teacher import PeerDisc
        x, y, a = pose; c, s = math.cos(a), math.sin(a)
        discs = [PeerDisc((c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y), r))
                 for ox, oy, r in self.discs(now)]
        if target is not None:
            candidates = [(math.dist(d[:2], target), i) for i, (d, t) in enumerate(zip(discs, self.tracks))
                          if t['kind'] == kind and math.dist(d[:2], target) <= t['radius']+t['range_error_m']+.08]
            # A single unambiguous same-kind target only. Nearby unrelated cargo stay.
            if candidates:
                candidates.sort()
                if len(candidates) == 1 or candidates[1][0]-candidates[0][0] > .08:
                    discs.pop(candidates[0][1])
        return discs

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
                'range_calibrated': False, 'unseen_is_free': False,
                **({'management_profile': 'carry5_mahalanobis_clear_views_v1',
                    'gate_d2': MAHALANOBIS_GATE_2D, 'deleted': self.deleted} if self.managed else {})}
