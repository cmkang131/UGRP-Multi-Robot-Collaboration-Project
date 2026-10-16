"""Default-off KLD/Augmented MCL and mode-discriminating wrist sensing.

Fox IJRR 2003; Nav2 pf.c (Probabilistic Robotics table 8.3); Burgard et al.
IJCAI 1997. Static-map/own-belief inputs only. Planning predictions never
enter the sensor update. Frozen v141/v146 sources are not patched globally.
"""
import copy
import math

import numpy as np

from harness import zone_solo_cyan_kld_start as kld
from harness import zone_solo_cyan_augmented_start as augmented
from harness.zone_solo_cyan_best_cluster import connected_labels

OPTION = 'kld_augmented_v2'
HEAD_OPTION = 'mode_information_v1'
PARAMS = {**kld.PARAMS, 'min_samples': 8000, 'max_samples': 400000}
HEAD = dict(planning_particles=512, columns=[64., 192., 320., 448., 576.],
            extra_pans=[700, 2300], max_extra_views=2, budget_s=120.)


class Policy(augmented.Policy):
    def measure(self, pf, prior, ll, pose, moved):
        # Nav2: unnormalized sensor weight total / sample count, then the
        # slow/fast running averages. No likelihood floor or fixed injection.
        avg = float(prior @ np.exp(ll) / pf.n)
        self.slow = avg if self.slow == 0 else self.slow + augmented.ALPHA_SLOW*(avg-self.slow)
        self.fast = avg if self.fast == 0 else self.fast + augmented.ALPHA_FAST*(avg-self.fast)
        probability = max(0., 1.-self.fast/self.slow) if self.slow > 0 else 0.
        row = dict(w_avg=avg, w_slow=self.slow, w_fast=self.fast,
                   injection_probability=probability, ess=float(1/(pf._weights()**2).sum()),
                   samples_before=pf.n, pose=list(augmented.pose_key(pose)))
        if moved:
            self.seen.clear()
        self.seen.add(augmented.pose_key(pose))
        # resample_interval=1 as in Nav2, without the optional ROS1 ESS exit.
        row.update(kld.resample(pf, probability, PARAMS), resampled=True, samples_after=pf.n)
        if probability > 0:
            self.slow = self.fast = 0.
        self.rows.append(row)
        return copy.deepcopy(row)


def mode_information(weights, labels, probabilities):
    """I(mode; measurement), pooling indistinguishable particles within a mode."""
    mass = np.bincount(labels, weights=weights)
    joint = np.zeros((len(mass), probabilities.shape[1]))
    np.add.at(joint, labels, weights[:, None]*probabilities)
    conditional = joint / np.maximum(mass[:, None], 1e-300)
    return augmented.information_gain(mass, conditional)


def rank_views(pf, pans):
    from harness import vision_loc_protocol as vp
    count = HEAD['planning_particles']
    cdf = np.cumsum(pf._weights()); cdf[-1] = 1.
    indices = np.searchsorted(cdf, (np.arange(count)+.5)/count, side='right')
    sample = pf.px[indices].copy()
    # Labels of the actual posterior, not spurious gaps in the subsample.
    labels = connected_labels(pf.px)[indices]
    _, labels = np.unique(labels, return_inverse=True)
    modes = len(np.unique(labels))
    weights = np.full(count, 1./count)
    vl = vp.load_vis3()[0]
    rows = []
    for pan in pans:
        cm = pf.column_model_for({**augmented.LOOK_P20, 6: pan}, columns=np.array(HEAD['columns']))
        bottom, _ = vl.expected_rows(pf.geometry, sample, cm)
        score = 0.
        for col in bottom.T:
            sensor = augmented.sensor_probabilities(col, float(pf.measurement['sigma_px']))
            score += (mode_information(weights, labels, sensor) if modes > 1
                      else augmented.information_gain(weights, sensor))
        rows.append(dict(pan=int(pan), expected_information_nats=float(score),
                         represented_modes=modes, hypothetical=True,
                         actual_observation=False, proxy='sum of five marginal ray information gains'))
    return sorted(rows, key=lambda r: (-r['expected_information_nats'], pans.index(r['pan'])))


def attach(runtime, *, global_diversity='off', mode_head_look='off'):
    if global_diversity not in ('off', OPTION) or mode_head_look not in ('off', HEAD_OPTION):
        raise ValueError('unknown global diversity / head look option')
    if global_diversity == mode_head_look == 'off':
        return runtime
    pf = runtime.pose.provider.loc._pf
    if pf.t != 0 or not getattr(runtime, 'global_policy', None) or not runtime.global_policy.active:
        raise ValueError('untouched global-start own provider required')
    audit = dict(global_diversity=global_diversity, mode_head_look=mode_head_look,
                 parameters=copy.deepcopy(PARAMS), head=copy.deepcopy(HEAD),
                 seed_changed=False, thresholds_changed=False, gt_inputs=False,
                 actions=[], extra_views=0, sampling_updates=[])
    if global_diversity != 'off':
        n = pf.n
        extra = PARAMS['max_samples'] - n
        if extra < 0:
            raise ValueError('initial particle count exceeds candidate cap')
        # Keep the historical samples as a prefix; add free-space samples
        # using this filter's existing RNG, never an evaluation-derived seed.
        poses = np.concatenate([pf.px, pf._uniform_free(extra)])
        indices = np.r_[np.arange(n), pf.rng.integers(n, size=extra)]
        kld.assign(pf, indices, poses)
        runtime.global_policy = pf.s2_global_policy = Policy()
        runtime.kld_audit.update(parameters=copy.deepcopy(PARAMS), initial_samples=pf.n)
        audit['sampling_updates'] = runtime.global_policy.rows
    old_control, old_record = runtime._control, runtime.record
    if mode_head_look != 'off':
        def control(now, idle):
            if (runtime.global_policy.active and idle and runtime.state == 'scan'
                    and not runtime.terminal and not runtime.pose.provider.failure
                    and now-runtime.global_scan_started < HEAD['budget_s']):
                if not runtime.scan_queue and audit['extra_views'] == 0:
                    modes = len(np.unique(connected_labels(pf.px)))
                    if modes > 1:
                        runtime.scan_queue = [{**augmented.LOOK_P20, 6: p} for p in HEAD['extra_pans']]
                        audit['extra_views'] = len(runtime.scan_queue)
                if runtime.scan_queue:
                    ranking = rank_views(pf, [p[6] for p in runtime.scan_queue])
                    selected = ranking[0]['pan']
                    pose = next(p for p in runtime.scan_queue if p[6] == selected)
                    runtime.scan_queue.remove(pose)
                    audit['actions'].append(dict(t=float(now), selected_pan=selected, ranking=ranking))
                    runtime.queue(pose, now, duration=.65, settle=.8)
                    return [{'kind': 'hold'}]
            return old_control(now, idle)
        runtime._control = control
    inner = runtime.pose.provider
    inner.runtime_contract['s3_global_diversity'] = {k: copy.deepcopy(v) for k, v in audit.items()
        if k not in ('sampling_updates', 'actions')}
    inner.identity_sha256 = augmented.hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s3_diversity:' + inner.identity_sha256[:8]
    runtime.pose.source = inner.source
    def record():
        return {**old_record(), 'global_diversity': copy.deepcopy(audit)}
    runtime.record = record
    runtime.s3_diversity_audit = audit
    return runtime
