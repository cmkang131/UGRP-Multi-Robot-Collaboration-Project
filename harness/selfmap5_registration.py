"""Opt-in multi-view line evidence and augmented PF recovery; no plant imports."""
import copy
import math
import numpy as np
from harness.natural_floor_slam import compose, transform
from harness.own_map_amcl_vendor.augmented import Policy, pose_key

OPTION = 'selfmap4_multiframe_registration_v1'
ALPHA_SLOW, ALPHA_FAST, SIGMA_SCALE = .001, .1, 6.


class RecoveryPolicy(Policy):
    """Same augmented averages, allowing recovery draws even at high ESS.

    Legacy selective resampling can suppress every random draw in a collapsed
    equal-weight cloud. This opt-in policy responds to falling sensor likelihood;
    it cannot diagnose or guarantee removal of a systematic sensor bias.
    """
    def __init__(self, alpha_slow=ALPHA_SLOW, alpha_fast=ALPHA_FAST):
        super().__init__()
        if not 0 < alpha_slow < alpha_fast <= 1:
            raise ValueError('INVALID_RECOVERY_ALPHAS')
        self.alpha_slow, self.alpha_fast = alpha_slow, alpha_fast

    def measure(self, pf, prior, ll, pose, moved):
        avg = float(prior@np.exp(ll)/pf.n)
        self.slow = avg if self.slow == 0 else self.slow+self.alpha_slow*(avg-self.slow)
        self.fast = avg if self.fast == 0 else self.fast+self.alpha_fast*(avg-self.fast)
        diff = max(0., 1-self.fast/self.slow) if self.slow > 0 else 0.
        weights = pf._weights(); ess = float(1/np.sum(weights**2))
        row = dict(w_avg=avg, w_slow=self.slow, w_fast=self.fast,
            injection_probability=diff, ess=ess, resampled=False, injected=0,
            pose=list(pose_key(pose)), alpha_slow=self.alpha_slow, alpha_fast=self.alpha_fast)
        if moved:
            self.seen.clear()
        self.seen.add(pose_key(pose))
        if ess <= .5*pf.n or diff > 0:
            injected = pf.rng.random(pf.n) < diff
            cdf = np.cumsum(weights)
            indices = np.minimum(np.searchsorted(cdf, pf.rng.random(pf.n), side='right'), pf.n-1)
            indices[injected] = pf.rng.integers(pf.n, size=int(injected.sum()))
            for name in ('px', 'scale', 'stuck', 'yaw_bias', 'yaw_extra', 'drift'):
                value = getattr(pf, name, None)
                if value is not None:
                    setattr(pf, name, value[indices].copy())
            if injected.any():
                pf.px[injected] = pf._uniform_free(int(injected.sum()))
            pf.logw = np.zeros(pf.n); pf._inject = 0.; pf.stats['resamples'] += 1
            row.update(resampled=True, injected=int(injected.sum()))
            if diff > 0:
                self.slow = self.fast = 0.
        self.rows.append(row)
        return copy.deepcopy(row)


def calibrated_covariance(covariance, scale=SIGMA_SCALE):
    # Conservative diagnostic envelope, not a fitted posterior calibration.
    return np.asarray(covariance)*scale**2 + np.diag([.02**2, .02**2, math.radians(.5)**2])


class MultiFrameEvidence:
    def __init__(self):
        self.active = False
        self.frames = []
        self.started = None
        self.trace_edge_ids = False
        self.rolling = False

    def begin(self, t):
        self.active = True
        if not self.rolling:
            self.frames.clear()
        self.started = float(t)

    def end(self):
        self.active = False
        if not self.rolling:
            self.frames.clear()

    def add(self, observation, own_pose, t):
        if not self.active and not self.rolling:
            return
        if self.rolling:
            self.frames = [f for f in self.frames if t-f['t'] <= 30.+1e-8]
        elif t-self.started > 30.+1e-8:
            self.end(); return
        lines = [copy.deepcopy(f) for f in observation['features'] if f['kind'] == 'floor_line']
        if lines:
            self.frames.append(dict(t=float(t), pose=np.asarray(own_pose).copy(), lines=lines))
        self.frames = self.frames[-400:]

    def supported(self, edges, world_pose, own_pose, covariance):
        from harness.selfmap4_geometry import inverse
        anchor = compose(world_pose, inverse(own_pose))
        normals, errors, used_frames, edge_ids, fresh_ids = [], [], set(), set(), set()
        for i, frame in enumerate(self.frames):
            pose = compose(anchor, frame['pose'])
            for line in frame['lines']:
                ends = transform(line['endpoints'], pose)
                angle = math.atan2(line['normal'][1], line['normal'][0])+pose[2]
                candidates = []
                for edge_id, edge in enumerate(edges):
                    hd = abs(edge['hue']-line['hue']); hd = min(hd, 180-hd)
                    da = abs(math.atan2(math.sin(angle-math.atan2(*edge['normal'][::-1])),
                                        math.cos(angle-math.atan2(*edge['normal'][::-1]))))
                    if hd > 12 or da > 3*math.sqrt(covariance[2, 2]+(math.radians(5)/3)**2):
                        continue
                    a, b = np.asarray(edge['a']), np.asarray(edge['b']); vec = b-a
                    along = np.clip((ends-a)@vec/(vec@vec), 0, 1)
                    residual = ends-a-along[:, None]*vec
                    nis = []
                    for point, error in zip(ends, residual):
                        # Uncertainty rotates about the current PF pose, including
                        # the SLAM-relative displacement to this older observation.
                        dx, dy = point-np.asarray(world_pose)[:2]
                        J = np.array([[1., 0., -dy], [0., 1., dx]])
                        S = J@covariance@J.T+np.eye(2)*(.05/3)**2
                        nis.append(float(error@np.linalg.solve(S, error)))
                    if max(nis) <= 9.:
                        candidates.append((max(nis), edge['normal'], float(np.linalg.norm(residual, axis=1).max()), edge_id))
                if candidates:
                    _, normal, error, edge_id = min(candidates, key=lambda r:r[0])
                    normals.append(normal); errors.append(error); used_frames.add(i)
                    edge_ids.add(f'static:{edge_id}')
                    if i == len(self.frames)-1:
                        fresh_ids.add(f'static:{edge_id}')
        values = np.linalg.eigvalsh(np.asarray(normals).T@np.asarray(normals)) if normals else np.zeros(2)
        axes = int(np.count_nonzero(values >= .5))
        detail = dict(supported_floor_lines=len(normals), independent_line_axes=axes == 2,
            independent_axis_count=axes, information_eigenvalues=values.tolist(),
            max_line_error_m=max(errors, default=None), evidence_frames=len(used_frames),
            buffered_frames=len(self.frames), sweep_active=self.active,
            residual_gate='PF_covariance_3sigma', sigma_scale=SIGMA_SCALE)
        if self.trace_edge_ids:
            detail.update(evidence_edge_ids=sorted(edge_ids), fresh_evidence_edge_ids=sorted(fresh_ids))
        return axes == 2, detail
