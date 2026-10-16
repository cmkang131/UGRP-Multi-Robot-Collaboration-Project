"""Active look-around after a set-down (setdown_lookaround_v1).

User 2026-10-14: "둘러보기 위해서 아래에 뒀으면, 진짜 좀 둘러봐야 할듯".
After a set-down the robot points its own camera where the static map says
informative landmarks should be, from its own pose estimate, and corrects the
estimate from what it actually sees. No simulator import: callers pass the
static-map landmarks, a visibility predictor built from own commands and the
camera model, and detections made from the own image.

Method (references in the PR 참고 자료 section):
- view choice: expected information gain of bearing measurements
  (Fox/Burgard/Thrun 1998 active Markov localization; Davison & Murray 2002
  active fixation; Zhang & Scaramuzza 2019 Fisher information field),
  scored as log det P - log det P_post with the linearized bearing Jacobian;
- greedy fixed budget of K views, then executed in a canonical left-to-right
  pan order at a fixed slew and dwell so a student can imitate it;
- fusion: EKF bearing updates with a chi-square gate (Arras et al. 2001),
  Joseph form.
"""
from __future__ import annotations
import math
import numpy as np

PANS_DEG = tuple(range(-90, 91, 15))
BODY_YAWS_DEG = (0., 90., -90., 180.)   # body rotation candidates, used only when pans alone see too little
BUDGET = 3
BEARING_SIGMA_RAD = math.radians(1.5)
GATE_CHI2_1 = 6.63                      # 99 % one degree of freedom
MOTION_COST_PER_RAD = .02               # small: prefer short pan moves among near-equal views
MIN_GAIN = .05                          # stop adding views below this information gain


def wrap(a):
    return (a+math.pi) % (2*math.pi)-math.pi


def bearing_jacobian(pose, point):
    """d(bearing in body frame)/d(x, y, yaw) for a landmark at point."""
    dx, dy = point[0]-pose[0], point[1]-pose[1]; d2 = dx*dx+dy*dy
    return np.array([dy/d2, -dx/d2, -1.])


def predicted_bearing(pose, point):
    return wrap(math.atan2(point[1]-pose[1], point[0]-pose[0])-pose[2])


class OwnPose:
    """Map-frame own pose from the map code's estimate, moved only by own issued commands."""
    def __init__(self, pose, sigma_xy=.05, sigma_yaw=math.radians(2.)):
        self.x = np.array(pose, dtype=float)
        self.P = np.diag([sigma_xy**2, sigma_xy**2, sigma_yaw**2])
        self.updates = []

    def propagate(self, dx, dy, dyaw, *, k_trans=.10, k_rot=.10):
        c, s = math.cos(self.x[2]), math.sin(self.x[2])
        F = np.array([[1, 0, -s*dx-c*dy], [0, 1, c*dx-s*dy], [0, 0, 1]])
        self.x = self.x+np.array([c*dx-s*dy, s*dx+c*dy, dyaw]); self.x[2] = wrap(self.x[2])
        q = np.diag([(k_trans*math.hypot(dx, dy))**2]*2+[(k_rot*abs(dyaw)+.2*k_trans*math.hypot(dx, dy))**2])
        self.P = F@self.P@F.T+q

    def update_bearing(self, point, z, sigma=BEARING_SIGMA_RAD, label=None):
        """EKF bearing update with a chi-square gate; returns True if accepted."""
        H = bearing_jacobian(self.x, point).reshape(1, 3); R = np.array([[sigma**2]])
        nu = wrap(z-predicted_bearing(self.x, point)); S = H@self.P@H.T+R
        d2 = float(nu*nu/S[0, 0])
        ok = d2 <= GATE_CHI2_1
        self.updates.append({'label': label, 'innovation_rad': nu, 'chi2': d2, 'accepted': ok})
        if not ok:
            return False
        K = self.P@H.T/S[0, 0]
        self.x = self.x+(K*nu).ravel(); self.x[2] = wrap(self.x[2])
        I = np.eye(3)-K@H
        self.P = I@self.P@I.T+K@R@K.T
        return True


def jacobian_rows(pose, lm):
    """(rows, sigmas) of one landmark's measurement Jacobian w.r.t. (x, y, yaw).

    model 'bearing' (default): body-frame bearing to a point.
    model 'line_point': a point seen on a mapped line (wall base, zone edge); the
      measurement is its normal distance to the line, h = n.(p + R q) - c, so
      dh/dp = n and dh/dyaw = n.perp(l - p) (Arras et al. 2001 line features).
    model 'point': a mapped point seen in the body frame (door jamb), both axes.
    """
    if not isinstance(lm, dict):
        lm = {'xy': lm}
    x, y = lm['xy']; model = lm.get('model', 'bearing')
    if model == 'bearing':
        return [bearing_jacobian(pose, (x, y))], [lm.get('sigma', BEARING_SIGMA_RAD)]
    px, py = x-pose[0], y-pose[1]; perp = (-py, px)
    if model == 'line_point':
        nx, ny = lm['normal']
        return [np.array([nx, ny, nx*perp[0]+ny*perp[1]])], [lm['sigma']]
    if model == 'point':
        return [np.array([1., 0., perp[0]]), np.array([0., 1., perp[1]])], [lm['sigma']]*2
    raise ValueError(model)


def information(pose, landmarks, sigma=None):
    J = np.zeros((3, 3))
    for lm in landmarks:
        rows, sigmas = jacobian_rows(pose, lm)
        for h, s in zip(rows, sigmas):
            s = sigma if (sigma is not None and not isinstance(lm, dict)) else s
            J += np.outer(h, h)/s**2
    return J


def gain(P, J):
    """log det P - log det (P^-1 + J)^-1 (nats)."""
    Pi = np.linalg.inv(P)
    return float(np.linalg.slogdet(Pi+J)[1]-np.linalg.slogdet(Pi)[1])


def plan_views(pose, P, landmarks, visible_fn, *, pans=PANS_DEG, body_yaws=BODY_YAWS_DEG, budget=BUDGET, start_pan=0.):
    """Choose up to ``budget`` views (body yaw, pan) and return them in canonical order.

    landmarks: [{'id', 'type', 'xy', optional 'model'/'normal'/'sigma'/'group'}] (see jacobian_rows); visible_fn(pose, body_yaw_deg, pan_deg, landmark) -> bool
    predicts visibility from the own pose estimate, own commands and the static map only.
    Body yaw is considered only if pans at the current heading leave the information gain
    below MIN_GAIN; the plan then rotates once and sweeps there.
    """
    def cands(yaws):
        out = []
        for yaw in yaws:
            for pan in pans:
                seen = [l for l in landmarks if visible_fn(pose, yaw, pan, l)]
                out.append({'body_yaw_deg': float(yaw), 'pan_deg': float(pan),
                            'landmarks': sorted({l.get('group', l['id']) for l in seen}), 'points': seen})
        return out

    def greedy(candidates):
        chosen = []; J = np.zeros((3, 3)); last = start_pan
        for _ in range(budget):
            best = None
            for c in candidates:
                if c in chosen or not c['points']:
                    continue
                g = gain(P, J+information(pose, c['points']))-gain(P, J)
                score = g-MOTION_COST_PER_RAD*math.radians(abs(c['pan_deg']-last))
                if best is None or score > best[0]+1e-12:
                    best = (score, g, c)
            if best is None or best[1] < MIN_GAIN:
                break
            chosen.append(best[2]); J = J+information(pose, best[2]['points']); last = best[2]['pan_deg']
        return chosen, gain(P, J)

    chosen, total = greedy(cands((0.,)))
    rotated = False
    if total < MIN_GAIN and len(body_yaws) > 1:
        options = [(greedy(cands((y,))), y) for y in body_yaws[1:]]
        (alt, alt_total), yaw = max(options, key=lambda o: (o[0][1], -abs(o[1])))
        if alt_total > total:
            chosen, total, rotated = alt, alt_total, True
    # Canonical execution order: one body heading, pans swept left to right (fixed slew/dwell).
    chosen = sorted(chosen, key=lambda c: (c['body_yaw_deg'], c['pan_deg']))
    return {'views': chosen, 'expected_gain_nats': total, 'rotated': rotated,
            'expected_landmarks': sorted({i for c in chosen for i in c['landmarks']})}
