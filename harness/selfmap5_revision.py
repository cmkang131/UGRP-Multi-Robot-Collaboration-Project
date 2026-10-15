"""Numerical selfmap5 revision policy; own issued motion and visual poses only."""
import math
import numpy as np
from harness.natural_floor_slam import compose, wrap

OPTION = 'selfmap4_revision_gate_v2'
# Independent of insertion uncertainty limits and recovery episode deadline.
REBUILD_COOLDOWN_S = 5.
RECOVERY_ATTEMPTS = 2
# Each attempt allows 9 one-second pans + existing 30s bounded body sweep + 1s dispatch.
RECOVERY_DEADLINE_S = RECOVERY_ATTEMPTS*(9.+30.+1.)


def revision_test(prior, corrected, predicted_covariance, *, measurement_covariance=None, sigma=3.):
    """Wrapped innovation in the predicted map frame; singular axes fail closed."""
    d = np.asarray(corrected, float)-np.asarray(prior, float)
    d[2] = wrap(d[2])
    cov = np.asarray(predicted_covariance, float)
    if cov.shape != (3, 3) or not np.isfinite(cov).all() or not np.isfinite(d).all():
        raise ValueError('FINITE_REVISION_COVARIANCE_REQUIRED')
    predicted = cov.copy()
    if measurement_covariance is not None:
        measurement = np.asarray(measurement_covariance, float)
        if measurement.shape != (3, 3) or not np.isfinite(measurement).all() or np.linalg.eigvalsh((measurement+measurement.T)/2).min() < -1e-10:
            raise ValueError('PSD_MEASUREMENT_COVARIANCE_REQUIRED')
        cov = cov+measurement
    values, vectors = np.linalg.eigh((cov+cov.T)/2)
    if values.min() < -1e-12:
        raise ValueError('PSD_REVISION_COVARIANCE_REQUIRED')
    projected = vectors.T@d
    null = values <= 1e-12
    impossible = np.any(abs(projected[null]) > 1e-8)
    nis = float(np.sum(projected[~null]**2/values[~null]))
    return dict(required=bool(impossible or nis > sigma**2),
                mahalanobis=None if impossible else math.sqrt(nis),
                threshold_sigma=float(sigma), nullspace_innovation=bool(impossible),
                innovation=d.tolist(), predicted_covariance=predicted.tolist(), innovation_covariance=cov.tolist())


def issued_distance(delta):
    """Translation plus 0.15m footprint arc for in-place command rotation."""
    return float(np.linalg.norm(np.asarray(delta)[:2])+.15*abs(delta[2]))


def partial_poses(history, revision):
    """Distribute endpoint drift over only the trailing command-only segment.

    The previous visual anchor and earlier poses are preserved. Zero issued
    distance cannot justify a historical correction. No feature re-fit or truth.
    """
    anchor = revision['anchor_frame_id']
    selected = [r for r in history if r['observation'].frame_id > anchor]
    if any(r['source'] != 'command_only' for r in selected):
        return None, 'non_command_record_after_anchor'
    total = revision['distance']
    if total <= 1e-9:
        return None, 'zero_command_distance'
    # Left SE(2) correction; interpolate translation/yaw and apply to each pose.
    p, q = np.asarray(revision['prior']), np.asarray(revision['corrected'])
    yaw = wrap(q[2]-p[2]); c, s = math.cos(yaw), math.sin(yaw)
    shift = q[:2]-np.array([[c, -s], [s, c]])@p[:2]
    poses = []
    for r in history:
        weight = (min(1., max(0., r['distance_since_visual']/total))
                  if r['observation'].frame_id > anchor else 0.)
        poses.append(compose([*(weight*shift), weight*yaw], r['pose']) if weight else r['pose'].copy())
    return poses, None
