"""reloc8: command-conditioned hypotheses and next view, no plant/GT input.

Finite geometric NBV approximation (not a replacement AMCL implementation).
Predicted signatures choose actions only; they never constitute observations.
The caller retains its residual, innovation, rank and independent-view gates.
"""
from __future__ import annotations

import math
import numpy as np

OPTION = 'reloc8_active_vision_v1'
LOOK = {1: 2000, 3: 858, 4: 2320, 5: 1320, 6: 1500}


def wrap(a):
    return (np.asarray(a)+math.pi) % (2*math.pi)-math.pi


def validate(option):
    if option not in ('off', OPTION):
        raise ValueError('UNKNOWN_ACTIVE_RELOCALIZATION')


def prior_support(poses, prior, covariance):
    """Full command-prediction ellipsoid, circular yaw; never shrink P here."""
    poses = np.asarray(poses, float).reshape(-1, 3)
    d = poses-np.asarray(prior)
    d[:, 2] = wrap(d[:, 2])
    P = np.asarray(covariance, float)
    try:
        np.linalg.cholesky(P)
        nis = np.einsum('ni,ij,nj->n', d, np.linalg.inv(P), d)
        valid = (np.isfinite(d).all(1) & np.isfinite(nis) & (nis <= 9.) &
                 (np.abs(d) <= 3*np.sqrt(np.diag(P))).all(1))
    except np.linalg.LinAlgError:
        valid, nis = np.zeros(len(d), bool), np.full(len(d), math.inf)
    return valid, nis


def conditioned_modes(poses, scores, prior, covariance, *, complete=True):
    """Do not filter an already truncated global peak list to certify uniqueness.

    Score all caller candidates within command support. This may propose a
    view but cannot authorize a correction until independent RGB agrees.
    """
    poses, scores = np.asarray(poses, float), np.asarray(scores, float)
    valid, nis = prior_support(poses, prior, covariance)
    valid &= np.isfinite(scores)
    ids = np.flatnonzero(valid)
    modes = []
    if len(ids):
        peak = scores[ids].max()
        ids = ids[scores[ids] >= peak-math.log(20.)]
        ids = ids[np.argsort(-(scores[ids]-.5*nis[ids]), kind='stable')]
        while len(ids) and len(modes) < 8:
            i = ids[0]
            modes.append(dict(pose=poses[i].tolist(), relative_likelihood=float(math.exp(scores[i]-peak))))
            ids = ids[(np.linalg.norm(poses[ids, :2]-poses[i, :2], axis=1) > .30) |
                      (np.abs(wrap(poses[ids, 2]-poses[i, 2])) > math.radians(30))]
    return dict(available=True, ambiguous=not (complete and len(modes) == 1), hypotheses=modes,
                search_complete=bool(complete), command_supported_N=int(valid.sum()),
                reason='command_conditioned_rgb', prior_is_observation=False)


def relative_candidates(poses, current, previous):
    """Transport each global hypothesis to a previous own-command frame."""
    poses = np.asarray(poses, float).copy()
    current, previous = np.asarray(current), np.asarray(previous)
    d = previous[:2]-current[:2]
    c, s = math.cos(current[2]), math.sin(current[2])
    dx, dy = np.array([[c, s], [-s, c]])@d
    c, s = np.cos(poses[:, 2]), np.sin(poses[:, 2])
    poses[:, 0] += c*dx-s*dy
    poses[:, 1] += s*dx+c*dy
    poses[:, 2] = wrap(poses[:, 2]+wrap(previous[2]-current[2]))
    return poses


class ViewEvidence:
    """At most three past RGB likelihoods, propagated by issued pose history.

    Never reuse a repeated view as independent evidence. A failed overlap
    remains ambiguous. Clear after an accepted correction or task reset.
    """
    def __init__(self):
        self.frames = []

    def score(self, poses, current, now, heading, sensor_score):
        score = sensor_score(poses)
        independent = []
        for f in self.frames:
            if now-f['t'] > 60. or abs(wrap(heading-f['heading'])) < math.radians(15):
                continue
            past = f['score'](relative_candidates(poses, current, f['pose']))
            score += past-past.max()
            independent.append(f['t'])
        return score, independent

    def add(self, pose, now, heading, sensor_score):
        # Replace an older repeat even in an A/B/A sequence. It must never
        # count twice when the next C view is scored.
        self.frames = [f for f in self.frames
                       if abs(wrap(heading-f['heading'])) >= math.radians(15)]
        self.frames.append(dict(pose=np.asarray(pose).copy(), t=float(now), heading=float(heading), score=sensor_score))
        self.frames = self.frames[-3:]


def landmarks(static):
    """Wall bases/upper faces, doorway jambs and colored boundary samples."""
    out = []
    for o in static['obstacles']:
        if o.get('kind') != 'wall':
            continue
        x, y = o['center_m']; a, b = o['half_extents_m']
        for p, q in [((x-a, y-b), (x+a, y-b)), ((x+a, y-b), (x+a, y+b)),
                     ((x+a, y+b), (x-a, y+b)), ((x-a, y+b), (x-a, y-b))]:
            for f in np.linspace(0, 1, max(2, int(math.dist(p, q)/.4))):
                xy = (1-f)*np.asarray(p)+f*np.asarray(q)
                for z in (0., .20):
                    out.append(dict(xyz=[*xy, z], kind='wall'))
    for d in static.get('passages', []):
        if d.get('kind') != 'door':
            continue
        axis = np.array([0, 1] if d.get('axis') == 'x' else [1, 0])
        for sign in (-1, 1):
            out.append(dict(xyz=[*(np.asarray(d['center_m'])+sign*axis*d['width_m']/2), .1], kind='door'))
    for r in static['regions'].values():
        x, y = r['center_m']; a, b = r['half_extents_m']
        color = r['rgba']
        if isinstance(color, str): color = [float(v) for v in color.split()]
        kind = 'zone:'+','.join(str(round(v, 1)) for v in color[:3])
        for p in ((x-a, y-b), (x+a, y-b), (x+a, y+b), (x-a, y+b)):
            out.append(dict(xyz=[*p, 0.], kind=kind))
    return out


def _occluded(start, ends, static):
    blocked = np.zeros(len(ends), bool)
    # Stop short of the target's own wall face.
    ends = start+.98*(ends-start)
    d = ends-start
    for o in static['obstacles']:
        if o.get('kind') != 'wall': continue
        center, half = np.asarray(o['center_m']), np.asarray(o['half_extents_m'])
        with np.errstate(divide='ignore', invalid='ignore'):
            a, b = (center-half-start)/d, (center+half-start)/d
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        parallel = np.abs(d) < 1e-10
        outside = parallel & ((start < center-half) | (start > center+half))
        lo[parallel], hi[parallel] = -math.inf, math.inf
        blocked |= (~outside.any(1) & (np.maximum(lo.max(1), 0) < np.minimum(hi.min(1), 1)))
    return blocked


def next_view(static, pose, covariance, *, hypotheses=(), previous_headings=()):
    """Entropy of predicted *measurable* signatures + uncertain visibility.

    Signatures contain kind, camera bearing/range bins, never global feature
    IDs: repeated rooms must not acquire fake discriminative identifiers.
    All headings use the actual fixed camera FK; body turns are in place.
    """
    from harness.active_camera import transform
    from sim.masterpi_camera_profile import scaled_camera_matrix
    pose, P = np.asarray(pose, float), np.asarray(covariance, float)
    np.linalg.cholesky(P)
    modes = [pose, *[np.asarray(h['pose'], float) for h in hypotheses]][:9]
    root = np.linalg.cholesky(P)
    samples = [pose, *[pose+sign*2*root[:, k] for k in range(3) for sign in (-1, 1)]]
    lms = landmarks(static); xyz = np.asarray([l['xyz'] for l in lms])
    K = scaled_camera_matrix(640, 480)

    def signature(p, yaw, servo):
        origin, rotation = transform(servo)
        angle = p[2]+math.radians(yaw); c, s = math.cos(angle), math.sin(angle)
        R = np.array([[c, -s], [s, c]])
        body = xyz.copy(); body[:, :2] = (xyz[:, :2]-p[:2])@R
        q = (body-origin)@rotation
        with np.errstate(divide='ignore', invalid='ignore'):
            uv = (q@K.T)[:, :2]/q[:, 2, None]
        visible = ((q[:, 2] > .05) & (np.linalg.norm(body-origin, axis=1) < 4.) &
                   (uv[:, 0] >= 70) & (uv[:, 0] <= 570) & (uv[:, 1] >= 55) & (uv[:, 1] <= 425))
        ids = np.flatnonzero(visible)
        if len(ids):
            cw = p[:2]+R@origin[:2]
            ids = ids[~_occluded(cw, xyz[ids, :2], static)]
        sig = sorted({(lms[i]['kind'], int(uv[i, 0]//100), int(np.linalg.norm(body[i, :2])/.5)) for i in ids})
        return tuple(sig), len(ids), len({lms[i]['kind'] for i in ids})

    candidates = []
    for yaw in (-180., -90., -45., 0., 45., 90., 180.):
        for pan in (-45., 0., 45.):
            servo = {**LOOK, 6: int(round(1500+pan/0.09))}
            sigs = [signature(p, yaw, servo)[0] for p in modes]
            counts = [sigs.count(s)/len(sigs) for s in set(sigs)]
            entropy = -sum(p*math.log(p) for p in counts)
            uncertain = [signature(p, yaw, servo) for p in samples]
            support = sum(n >= 2 for _, n, _ in uncertain)/len(samples)
            nominal, n, kinds = uncertain[0]
            heading = float(wrap(pose[2]+math.radians(yaw+pan)))
            repeated = any(abs(wrap(heading-h)) < math.radians(20) for h in previous_headings)
            score = (bool(n), not repeated, entropy, support, kinds, min(n, 12), -.001*(abs(yaw)+abs(pan)))
            candidates.append((score, dict(body_yaw_deg=yaw, pan_deg=pan, pan_pulse=servo[6], servo=servo,
                expected_signature=[list(s) for s in nominal], predicted_points=n,
                uncertainty_support=support, hypothesis_entropy_nats=entropy, heading_rad=heading)))
    score, view = max(candidates, key=lambda c:c[0])
    view.update(profile=OPTION, feasible=bool(score[0]), predicted_only=True,
                hypothesis_count=len(modes), sigma_samples=len(samples), motion='in_place_only')
    return view
