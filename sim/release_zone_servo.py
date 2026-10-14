"""Opt-in release centering in a LOCAL zone frame, from own RGB + static size.

No world pose is initialized. Partial edges constrain their normal coordinate,
never their visible midpoint along the edge. Two orthogonal edge families and
multiple views must agree with one rectangle; ambiguous fits fail closed.
This is a position-based visual servo, not global localization (Chaumette &
Hutchinson 2006, doi:10.1109/MRA.2006.250573). Reobserve after each bounded move.
"""
from __future__ import annotations

import itertools
import math
import hashlib
from types import SimpleNamespace

import cv2
import numpy as np

OPTION = 'zone_center_rgb_v1'
MODES = ('margin_v0', OPTION, 'global_localized_release_v1')
FIT_M = .04                 # RGB ground-line compatibility, not truth-fitted
ANGLE_RAD = math.radians(20)
CENTER_TOL_M = .05
MAX_SHIFT_M = .50           # a finite command leg, then set down and reobserve
MAX_CORRECTIONS = 3
PAIR_AGREEMENT_M = .08


def fit_rectangle(views, half_long, half_short, target_hue):
    """Robust partial-line/static-size fit in the stationary sweep body frame.

    The release handoff contract aligns the beam/forward axis with the zone's
    long axis. Both headings are allowed. Reject a rotated/ambiguous handoff.
    Hough slope errors near the horizon are not treated as measured map yaw:
    each hypothesis uses the longer side edge for its orthogonal basis.
    """
    lines = []
    for vi, view in enumerate(views):
        for f in view.get('features', []):
            if f.get('kind') != 'floor_line':
                continue
            dh = abs(f['hue']-target_hue)
            if min(dh, 180-dh) > 12:
                continue
            p = np.asarray(f['endpoints'], float); n = np.asarray(f['normal'], float)
            if p.shape != (2, 2) or n.shape != (2,) or not np.isfinite(p).all() or not np.isfinite(n).all():
                continue
            if np.linalg.norm(n) < .9 or np.linalg.norm(p[1]-p[0]) < .12:
                continue
            n = n/np.linalg.norm(n)
            if max(abs(n)) < math.cos(ANGLE_RAD):
                continue
            lines.append(dict(p=p, n=n, view=vi, axial=abs(n[0]) > abs(n[1])))
    base = {'accepted': False, 'reason': 'insufficient_zone_edges', 'lines': len(lines),
            'coordinate_frame': 'own_body_zone_relative', 'map_pose_known': False}
    short = [i for i, f in enumerate(lines) if f['axial']]
    sides = [i for i, f in enumerate(lines) if not f['axial']]
    hypotheses = []
    for i, j in itertools.product(short, sides):
        side = lines[j]; lateral = side['n'] * (1 if side['n'][1] > 0 else -1)
        axis = np.array([lateral[1], -lateral[0]])
        if abs(lines[i]['n']@axis) < math.cos(ANGLE_RAD):
            continue
        cx = float(lines[i]['p'].mean(0)@axis + np.sign(lines[i]['n']@axis)*half_long)
        cy = float(side['p'].mean(0)@lateral + np.sign(side['n']@lateral)*half_short)
        keep = []; residuals = []
        for k, f in enumerate(lines):
            normal, tangent = (axis, lateral) if f['axial'] else (lateral, axis)
            hn, ht = (half_long, half_short) if f['axial'] else (half_short, half_long)
            cn, ct = (cx, cy) if f['axial'] else (cy, cx)
            if abs(f['n']@normal) < math.cos(ANGLE_RAD):
                continue
            err = np.max(abs(f['p']@normal + np.sign(f['n']@normal)*hn - cn))
            # Exclude an unrelated same-colour edge and an internal slot edge.
            if err <= FIT_M and np.max(abs(f['p']@tangent-ct)) <= ht+FIT_M:
                keep.append(k); residuals.append(float(err))
        if len(keep) < 3 or len({lines[k]['view'] for k in keep}) < 2:
            continue
        if not any(lines[k]['axial'] for k in keep) or not any(not lines[k]['axial'] for k in keep):
            continue
        # Median normal coordinates bound the influence of a noisy Hough line.
        ax = [float(lines[k]['p'].mean(0)@axis + np.sign(lines[k]['n']@axis)*half_long) for k in keep if lines[k]['axial']]
        lat = [float(lines[k]['p'].mean(0)@lateral + np.sign(lines[k]['n']@lateral)*half_short) for k in keep if not lines[k]['axial']]
        center = float(np.median(ax))*axis + float(np.median(lat))*lateral
        hypotheses.append(dict(center=center, axis=axis, keep=keep, residual=max(residuals)))
    if not hypotheses:
        return base
    hypotheses.sort(key=lambda h: (-len(h['keep']), h['residual']))
    best = hypotheses[0]
    if any(len(h['keep']) >= len(best['keep'])-1 and np.linalg.norm(h['center']-best['center']) > 3*FIT_M for h in hypotheses[1:]):
        return {**base, 'reason': 'ambiguous_zone_rectangle'}
    return {**base, 'accepted': True, 'reason': 'rgb_rectangle', 'center_body_m': best['center'].tolist(),
            'long_axis_body': best['axis'].tolist(), 'inliers': len(best['keep']),
            'views_with_evidence': len({lines[k]['view'] for k in best['keep']}), 'max_residual_m': best['residual']}


class ZoneCenterServo:
    """Own-camera adapter. Runtime API has no plan/spawn/world/evaluation input."""
    def __init__(self, static, destination, camera, mp):
        from harness.zone_solo_cyan_landmarks import MapFeatures
        mapped = MapFeatures(static)
        target = [e for e in mapped.edges if e['region'] == destination]
        self.hue = target[0]['hue']
        self.unique_colour = not any(e['region'] != destination and min(abs(e['hue']-self.hue), 180-abs(e['hue']-self.hue)) <= 24 for e in mapped.edges)
        self.half_short, self.half_long = sorted(static['regions'][destination]['half_extents_m'])
        self.camera, self.mp = camera, mp
        self.mapped = SimpleNamespace(hues=[self.hue])
        self.views = []
        self.result = None

    def begin(self):
        self.views = []; self.result = None

    def observe(self, rgb, servo, now):
        from harness.zone_solo_cyan_landmarks import floor_features, ground
        rec = {'t': float(now), 'servo': dict(servo), 'features': [],
               'rgb_array_sha256': hashlib.sha256(rgb.tobytes()).hexdigest()}
        cam, reason = self.camera.pose(servo)
        if cam is None:
            rec['reason'] = reason
        else:
            if rgb.shape != (480, 640, 3):
                raise ValueError('zone servo requires native 640x480 own RGB')
            cm = SimpleNamespace(origin=cam[0], _rot=cam[1])
            und = self.mp.undistort(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            yy, xx = np.indices((480, 640))
            points, valid, _ = ground(cm, np.c_[xx.ravel(), yy.ravel()], self.mp.K_INV)
            valid &= np.linalg.norm(points-cam[0][:2], axis=1) < 2.5
            rec['features'] = floor_features(und, cm, self.mp.K_INV, self.mapped, valid.reshape(480, 640))
        self.views.append(rec)
        return rec

    def finalize(self, beam_center_body):
        fit = fit_rectangle(self.views, self.half_long, self.half_short, self.hue)
        if not self.unique_colour:
            fit.update(accepted=False, reason='ambiguous_destination_colour')
        if fit['accepted']:
            c = np.asarray(fit['center_body_m']); a = np.asarray(fit['long_axis_body'])
            b = np.asarray(beam_center_body); lateral = np.array([-a[1], a[0]])
            # Only axial transport is implemented. Keep lateral/yaw outside the
            # handoff contract explicit; do not silently treat centering as fit.
            shift = float((c-b)@a/a[0])
            landing = b + np.array([shift, 0.])
            lateral_extent = .30*abs(a[1]) + .02*abs(a[0])
            clearance = self.half_short-abs((landing-c)@lateral)-lateral_extent
            fit.update(shift_body_m=shift, lateral_clearance_m=float(clearance),
                       beam_center_body_m=b.tolist())
            if clearance < .04:
                fit.update(accepted=False, reason='lateral_clearance_unresolved')
        self.result = fit
        return fit


def pair_choice(reports, robots, now):
    """Both robots must independently see a compatible center. No lower bounds."""
    evidence = [reports[r].get('zone_center', {}) for r in robots]
    if not all(e.get('accepted') for e in evidence):
        return dict(action='stop', reason='zone_center_unobserved', t=now, evidence=evidence)
    shifts = [evidence[0]['shift_body_m'], -evidence[1]['shift_body_m']]
    if abs(shifts[0]-shifts[1]) > PAIR_AGREEMENT_M:
        return dict(action='stop', reason='zone_center_disagreement', t=now, shifts_m=shifts)
    shift = sum(shifts)/2
    if max(abs(x) for x in shifts) <= CENTER_TOL_M:
        return dict(action='lower', reason='rgb_centered', t=now, shifts_m=shifts)
    return dict(action='shift', shift_m=max(-MAX_SHIFT_M, min(MAX_SHIFT_M, shift)),
                reason='rgb_center_correction', t=now, shifts_m=shifts)
