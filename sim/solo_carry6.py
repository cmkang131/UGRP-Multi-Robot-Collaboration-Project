"""Opt-in carry6 geometry/partial-fix helpers. No simulator or truth input."""
from itertools import combinations, product
import hashlib
import math
from pathlib import Path
import numpy as np
from sim.active_lookaround import PANS_DEG, information, gain, wrap

RANK_OPTION = 'carry5_rank_aware_views_v1'
TRIM_OPTION = 'carry5_trim_yaw_calibration_v1'
MIN_EIGENVALUE = 100.  # DEV information threshold, metres/radians coordinates
MARGIN_PX = 100


def sigma_poses(pose, covariance):
    """27 Cartesian {0,+/-2 sigma} samples; includes mixed-axis corners."""
    root = np.linalg.cholesky(covariance)
    return [np.asarray(pose)+root@np.asarray(d) for d in product((-2., 0., 2.), repeat=3)]


def rank_aware_plan(pose, covariance, landmarks, visible, *, start_pan=0., retry=0):
    """Test every <=3-pan combination at each heading against ALL sigma samples.

    visible must enforce the 100px margin. If no robust combination exists,
    report infeasibility and choose a body-turn exploratory plan; never claim a
    predicted view is a fix. Retries rotate through +90/-90/180 relative headings.
    """
    samples = sigma_poses(pose, covariance)
    headings = (0., 90., -90., 180.) if not retry else ((90., -90., 180.)[(retry-1)%3],)
    options = []
    for yaw in headings:
        candidates = []
        matrices = []
        for pan in PANS_DEG:
            seen = [l for l in landmarks if visible(pose, yaw, pan, l)]
            candidates.append(dict(body_yaw_deg=yaw, pan_deg=float(pan),
                landmarks=sorted({l.get('group', l['id']) for l in seen})))
            matrices.append(np.asarray([information(p, [l for l in landmarks if visible(p, yaw, pan, l)])
                                        for p in samples]))
        matrices = np.asarray(matrices)
        for count in (1, 2, 3):
            for ids in combinations(range(len(PANS_DEG)), count):
                J = matrices[list(ids)].sum(0)
                eigen = np.maximum(0., np.linalg.eigvalsh(J)[:, 0])
                # Centre sample is index13 in the 3x3x3 Cartesian product.
                # Reuse exactly the same per-view matrices, no extra projection.
                nominal = matrices[list(ids), 13].sum(0)
                nominal_min = max(0., float(np.linalg.eigvalsh(nominal)[0]))
                robust = bool(eigen.min() >= MIN_EIGENVALUE)
                motion = abs(yaw)+abs(PANS_DEG[ids[0]]-start_pan)+PANS_DEG[ids[-1]]-PANS_DEG[ids[0]]
                score = (robust, int((eigen >= MIN_EIGENVALUE).sum()), float(eigen.min()),
                         float(np.median(eigen)), nominal_min, gain(covariance, nominal)-.0001*motion)
                options.append((score, yaw, ids, eigen, nominal, candidates))
    feasible = [o for o in options if o[0][0]]
    pool = feasible or [o for o in options if o[1] != 0.]
    best = max(pool, key=lambda o: o[0])
    score, yaw, ids, eigen, nominal, candidates = best
    return dict(views=[candidates[i] for i in ids], rotated=yaw != 0.,
        expected_gain_nats=gain(covariance, nominal),
        expected_landmarks=sorted({l for i in ids for l in candidates[i]['landmarks']}),
        rank_aware=dict(profile=RANK_OPTION, robust_feasible=bool(score[0]),
            minimum_eigenvalue=float(eigen.min()), nominal_minimum_eigenvalue=max(0., float(np.linalg.eigvalsh(nominal)[0])),
            minimum_eigenvalue_required=MIN_EIGENVALUE, margin_px=MARGIN_PX,
            sigma_samples=len(samples), passing_samples=int((eigen >= MIN_EIGENVALUE).sum()),
            retry=retry, exploratory_body_turn=not bool(score[0])))


def partial_posterior(prior, covariance, posterior, post_covariance, rows, receipt):
    """Project a rank-2 proposal onto its observable subspace; preserve null variance.

    Full-fix acceptance is unchanged. A partial requires the SAME inlier,
    innovation and gain tests; only residual/group count and rank are partial.
    Rank-3 ambiguous scenes and poor-inlier scenes always roll back.
    """
    if (not all(math.isfinite(receipt[k]) for k in ('inlier_fraction', 'innovation_chi2', 'information_gain'))
            or receipt['accepted'] or receipt['pose_rank'] != 2 or receipt['residual_count'] < 2
            or receipt['inlier_fraction'] < .8 or receipt['innovation_chi2'] > 11.345
            or receipt['information_gain'] < receipt['minimum_information_gain']
            or not all(np.isfinite(a).all() for a in (prior, covariance, posterior, post_covariance, rows))):
        return None
    _, s, vh = np.linalg.svd(np.asarray(rows), full_matrices=True)
    if np.count_nonzero(s > 1e-8) != 2:
        return None
    Q = vh[:2].T@vh[:2]; N = np.eye(3)-Q
    delta = np.asarray(posterior)-prior; delta[2] = wrap(delta[2])
    x = np.asarray(prior)+Q@delta; x[2] = wrap(x[2])
    P = Q@post_covariance@Q + N@covariance@N
    return x, (P+P.T)/2, dict(applied=True, pose_rank=2,
        observable_projector=Q.tolist(), null_variance_before=float(vh[2]@covariance@vh[2]),
        null_variance_after=float(vh[2]@P@vh[2]), counts_as_fix=False)


def calibrated_trim_delta(issued, delta, calibration):
    """Scale mixed translation+turn yaw only; pure body turns retain drive model.

    Constant fitted offline. No live truth or measured wheel state enters here.
    """
    wheels, durations = issued['wheels'], issued['duration_s']
    a, b, c, d = wheels
    translation = math.hypot((a+b+c+d)/4, (-a+b+c-d)/4)
    mixed = translation > 1e-6 and max(durations)-min(durations) > 1e-6
    return (*delta[:2], delta[2]*calibration['trim_yaw_scale']) if mixed else delta


def validate_calibration(value):
    if (not isinstance(value, dict) or value.get('schema') != 'ugrp.carry6_trim_calibration.v1'
            or value.get('drive_model_source') != '01703ed2790dadad666e53d1b276b97f2b510bda'
            or not math.isfinite(value.get('trim_yaw_scale', math.nan))
            or abs(value['trim_yaw_scale']) > 1
            or value.get('drive_model_sha256') != hashlib.sha256((Path(__file__).resolve().parents[1]/'harness/drive_model.py').read_bytes()).hexdigest()
            or not value.get('calibration_ids') or not value.get('validation_ids')
            or set(value['calibration_ids']) & set(value['validation_ids'])):
        raise ValueError('separate offline calibration/validation provenance and matching drive source required')
