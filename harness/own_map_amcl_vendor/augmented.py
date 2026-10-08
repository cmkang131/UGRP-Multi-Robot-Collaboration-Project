"""Unmodified PR406 definitions; only imports and Runtime omission differ."""
import copy
import math
import numpy as np
from .motion import converged

ALPHA_SLOW, ALPHA_FAST = .001, .1


def pose_key(pose):
    return tuple(int(pose[k]) for k in (3, 4, 5, 6))


def belief_report(px, weights):
    """Full posterior moments and disjoint bins, never a connected-cluster claim."""
    w = np.asarray(weights); p = np.asarray(px)
    xy = w @ p[:, :2]
    cs, sn = w @ np.cos(p[:, 2]), w @ np.sin(p[:, 2])
    yaw = math.atan2(sn, cs)
    d = p[:, :2] - xy
    cov = np.zeros((3, 3)); cov[:2, :2] = (w[:, None]*d).T @ d
    cov[2, 2] = max(0., -2*math.log(max(math.hypot(cs, sn), 1e-300)))
    bins, ids = np.unique(np.floor(p/[.5, .5, math.pi/18]).astype(int), axis=0, return_inverse=True)
    masses = np.bincount(ids, weights=w)
    best = np.argsort(-masses, kind='stable')[:10]
    modes = [dict(bin=bins[i].tolist(), weight=float(masses[i])) for i in best]
    ready = converged(p) and cov[2, 2] <= math.radians(5)**2
    return np.r_[xy, yaw], cov, dict(resolved=bool(ready), bin_count=len(bins),
        leading_bins=modes, global_std_xy_m=float(np.sqrt(np.trace(cov[:2, :2]))),
        circular_yaw_std_rad=float(np.sqrt(cov[2, 2])), known_own_dock=False)


class Policy:
    def __init__(self):
        self.slow = self.fast = 0.
        self.seen = set()
        self.rows = []
        self.active = True

    def new_view(self, pose):
        return self.active and pose_key(pose) not in self.seen

    def measure(self, pf, prior, ll, pose, moved):
        # Nav2 uses the unnormalised sensor total/N, NOT normalised weights
        # or the max-shifted likelihood (both destroy the recovery signal).
        avg = float(prior @ np.exp(ll)/pf.n)
        self.slow = avg if self.slow == 0 else self.slow+ALPHA_SLOW*(avg-self.slow)
        self.fast = avg if self.fast == 0 else self.fast+ALPHA_FAST*(avg-self.fast)
        diff = max(0., 1-self.fast/self.slow) if self.slow > 0 else 0.
        ess = float(1/np.sum(pf._weights()**2))
        row = dict(w_avg=avg, w_slow=self.slow, w_fast=self.fast, injection_probability=diff,
            ess=ess, resampled=False, injected=0, pose=list(pose_key(pose)))
        if moved:
            self.seen.clear()
        self.seen.add(pose_key(pose))
        # ROS AMCL selective resampling returns BEFORE the recovery draw when
        # ESS>N/2. All hypotheses and weights survive, no arbitrary row quota.
        if ess <= .5*pf.n:
            cdf = np.cumsum(pf._weights()); indices=[]; injected=[]
            for i in range(pf.n):
                random = pf.rng.random() < diff
                injected.append(random)
                indices.append(0 if random else min(int(np.searchsorted(cdf, pf.rng.random(), side='right')), pf.n-1))
            indices=np.array(indices); injected=np.array(injected)
            # Latent motion variables keep ordinary weighted ancestry; an
            # injected pose gets an independent prior latent sample ancestry.
            indices[injected]=pf.rng.integers(pf.n, size=int(injected.sum()))
            for name in ('px','scale','stuck','yaw_bias','yaw_extra','drift'):
                value=getattr(pf,name,None)
                if value is not None:setattr(pf,name,value[indices].copy())
            if injected.any():pf.px[injected]=pf._uniform_free(int(injected.sum()))
            pf.logw=np.zeros(pf.n);pf._inject=0.;pf.stats['resamples']+=1
            row.update(resampled=True,injected=int(injected.sum()))
            if diff>0:self.slow=self.fast=0.
        self.rows.append(row)
        return copy.deepcopy(row)
