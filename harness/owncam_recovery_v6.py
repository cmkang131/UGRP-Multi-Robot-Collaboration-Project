"""Opt-in informative fixes and bounded sensor recovery for the own RGB PF.

No reset on routine looks. Detector acceptance is only a parsing result.
Residual compatibility, posterior support and local geometric curvature are
required before an observation can refresh the absolute-fix clock. Thresholds
are development hypotheses, not calibrated error coverage.
"""
from __future__ import annotations

import math
import numpy as np

from harness.owncam_localizer import OwnCamLocalizer
from harness.wall_tags import observed_tag_in_camera

MAX_RECOVERY_REQUESTS = 2
RECOVERY_FRAMES = 3
MIN_INLIER_FRACTION = .66


def likelihood_quality(per_feature, logweights, *, floor, curvature=0., settled=True):
    """Likelihood mixture diagnostics; no feature IDs or count-based gate.

    Outlier floor is computed from the configured mixture, NOT the historical
    min_best_loglik=-12 which is unreachable with a tempered floor near -9.
    """
    ll = np.asarray(per_feature, float)
    if ll.ndim != 2 or not ll.size or not np.isfinite(ll).all():
        return {'accepted': False, 'informative': False, 'settled': bool(settled),
                'ambiguous': True, 'reason': 'no_usable_geometry'}
    w = np.exp(logweights - np.max(logweights)); w /= w.sum()
    fit = np.mean(ll, axis=1)
    best = int(np.argmax(fit + np.log(np.maximum(w, 1e-300))))
    # More likely inlier than flat outlier in the robust mixture.
    inlier = ll > floor + math.log(2.)
    fraction = float(inlier[best].mean())
    support = float(w[inlier.mean(axis=1) >= MIN_INLIER_FRACTION].sum())
    saturated = bool(np.max(ll) <= floor + 1e-4)
    spread = float(np.ptp(fit))
    informative = (settled and not saturated and fraction >= MIN_INLIER_FRACTION
                   and support >= .10 and np.isfinite(curvature) and curvature > 1.)
    return {'accepted': True, 'informative': bool(informative), 'settled': bool(settled),
            'ambiguous': not bool(informative), 'inlier_fraction': fraction,
            'posterior_support': support, 'likelihood_span': spread,
            'saturated': saturated, 'geometric_curvature': float(curvature),
            'reason': 'informative' if informative else 'residual_or_geometry_inconsistent'}


class RecoveryLocalizer(OwnCamLocalizer):
    def enable_recovery(self):
        self.quality = {'accepted': False, 'informative': False, 'ambiguous': True,
                        'settled': False, 'reason': 'no_v6_observation'}
        self.last_informative_t = None
        self.last_fix_quality = None
        self.recovery_requests = self.recovery_frames = self.inconsistent_frames = 0
        self.last_update_t = None

    def request_recovery(self):
        # A caller cannot turn an ordinary look into an unlimited kidnapped PF.
        est = self.estimate()
        lost = (not self.initialized or self.inconsistent_frames >= 3
                or est.get('std_xy_m', math.inf) > .15 or est.get('std_yaw_rad', math.inf) > .20)
        if not lost or self.recovery_requests >= MAX_RECOVERY_REQUESTS:
            return False
        self.recovery_requests += 1
        self.recovery_frames = RECOVERY_FRAMES
        return True

    def _curvature(self, point, dets, pose):
        # Worst axis of a numerical information matrix in metres/radians.
        # A broad flat residual surface is not a position observation.
        step = np.array([.01, .01, .02])
        probes = [point]
        for i in range(3):
            for sign in (-1, 1):
                q = point.copy(); q[i] += sign * step[i]; probes.append(q)
        values = self._loglik(np.asarray(probes), dets, pose)
        diagonal = [(2 * values[0] - values[1+2*i] - values[2+2*i]) / step[i]**2 for i in range(3)]
        information = np.diag(diagonal)
        for i in range(3):
            for j in range(i+1,3):
                mixed=[]
                for si,sj in ((1,1),(1,-1),(-1,1),(-1,-1)):
                    q=point.copy();q[i]+=si*step[i];q[j]+=sj*step[j];mixed.append(q)
                v=self._loglik(np.asarray(mixed),dets,pose)
                information[i,j]=information[j,i]=-(v[0]-v[1]-v[2]+v[3])/(4*step[i]*step[j])
        return max(0.,float(np.linalg.eigvalsh(information)[0]))

    def update(self, t, detections, commanded_pose=None):
        if self.last_update_t is not None and t <= self.last_update_t:
            return self.estimate()
        self.predict_to(t)
        self.last_update_t = t
        pose = {int(k): int(v) for k, v in (commanded_pose or self.servo).items()}
        mp = self.params['measurement']
        if self.load.loaded:
            mp = {**mp, **self.params.get('measurement_loaded', {})}
        maximum = mp.get('max_range_m')
        dets = [d for d in detections if int(d['id']) in self.tags and d.get('solutions')
                and (not maximum or np.linalg.norm(observed_tag_in_camera(d)[0]) <= maximum)]
        settled = t - self.last_servo_cmd_t >= .3
        if not dets:
            self.quality = likelihood_quality([], self.logw, floor=0., settled=settled)
            return self.estimate()
        self.stats['updates'] += 1
        if not self.initialized:
            self.px = self._reset_from(dets, pose, self.n)
            self.scale = 1. + self.rng.normal(size=(self.n, 3)) * self.params['motion']['scale_std']
            self.logw = self._map_logprior(self.px)
            self.initialized = True
        elif self.recovery_frames and settled:
            # Preserve 80% of the existing hypotheses; proposals span yaw and
            # observations, rather than replacing the cloud by one PnP mode.
            count = max(1, int(self.n * .2))
            idx = self.rng.choice(self.n, count, replace=False)
            self.px[idx] = self._reset_from(dets, pose, count)
            self.scale[idx] = 1.
            self.logw[idx] = np.max(self.logw)
            self.recovery_frames -= 1
            self.stats['resets'] += 1
        per = np.column_stack([self._loglik(self.px, [d], pose) for d in dets])
        ll = self._loglik(self.px, dets, pose)
        best = int(np.argmax(ll + self.logw))
        floor = math.log(mp['outlier_prob']) - mp['outlier_margin']
        self.quality = likelihood_quality(per, self.logw, floor=floor, settled=settled,
                                         curvature=self._curvature(self.px[best], dets, pose))
        self.last_best_loglik = float(ll.max())
        # Bootstrap/recovery may accumulate compatible evidence until the cloud
        # resolves. Incompatible frames NEVER contract an established posterior.
        compatible = self.quality.get('inlier_fraction', 0.) >= MIN_INLIER_FRACTION
        if settled and compatible and not self.quality.get('saturated', True):
            self.logw += ll
            self._normalize_and_resample()
        if self.quality['informative']:
            self.last_informative_t = self.last_tag_t = t
            self.last_fix_quality = {**self.quality, 't': t}
            self.inconsistent_frames = 0
        elif settled:
            self.inconsistent_frames += 1
        self.quality['last_fix_quality'] = self.last_fix_quality
        self.quality['lost'] = self.inconsistent_frames >= 3
        return self.estimate()

    def estimate(self):
        est = super().estimate()
        t = getattr(self, 'last_informative_t', None)
        est.update(last_fix_t=t, fix_age_s=None if t is None else self.t-t,
                   fix_source='tags_temporary', since_tag_s=None if t is None else self.t-t)
        return est


def enable_provider(provider):
    """Configure before a pair job, including wrappers, without losing posterior."""
    if hasattr(provider, 'provider'):
        return enable_provider(provider.provider)
    from harness.owncam_pose_source import OwnCamPoseSource
    if isinstance(provider, OwnCamPoseSource):
        if not isinstance(provider.loc, RecoveryLocalizer):
            # Same object identity: frozen drivers continue to share this PF.
            provider.loc.__class__ = RecoveryLocalizer
            provider.loc.enable_recovery()
        provider.recovery_v6 = True
        if not provider.source.endswith(':recovery_v6'):
            provider.source += ':recovery_v6'
        return
    # Markerless providers must implement the same semantics; no tag fallback.
    if not callable(getattr(provider, 'begin_observation', None)):
        raise ValueError('v6 provider lacks posterior-preserving observation contract')


def begin_observation(provider, now, servo, *, lost=False):
    method = getattr(provider, 'begin_observation', None)
    if method is None:
        raise ValueError('v6 provider lacks posterior-preserving observation contract')
    return method(now, servo, lost=lost)
