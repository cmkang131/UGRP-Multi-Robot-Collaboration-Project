"""Default-off S2 tracking recovery, Nav2 pf.c 235fc5ce (LGPL-2.1+).

Unnormalised sensor average -> slow/fast EMA -> random map-free samples,
multinomial resampling and EMA reset: pf.c 249-280, 325-415 (PR Table 8.3).
The RGB sensor and motion update triggers are unchanged. Tracking uses the
existing 2000-particle budget (KLD min=max); no contact or truth input.
"""
import copy

import numpy as np

from harness.zone_solo_cyan_augmented_start import ALPHA_SLOW, ALPHA_FAST
from harness.zone_solo_cyan_kld_start import PARAMS, resample

OPTION = 'augmented_mcl_v1'


class Policy:
    def __init__(self):
        self.slow = self.fast = 0.
        self.rows = []

    def new_view(self, pose):
        # Recovery must not bypass Nav2's odometry motion threshold.
        return False

    def measure(self, pf, prior, ll, pose, moved):
        avg = float(prior @ np.exp(ll) / pf.n)
        self.slow = avg if self.slow == 0 else self.slow + ALPHA_SLOW*(avg-self.slow)
        self.fast = avg if self.fast == 0 else self.fast + ALPHA_FAST*(avg-self.fast)
        probability = max(0., 1-self.fast/self.slow) if self.slow > 0 else 0.
        row = dict(t=float(pf.t), w_avg=avg, w_slow=self.slow, w_fast=self.fast,
                   injection_probability=probability, ess=float(1/sum(pf._weights()**2)),
                   resampled=True, samples_before=pf.n)
        # Nav2 resample_interval=1. No ROS1 selective-ESS early return:
        # a flat, very unlikely observation still permits kidnapped recovery.
        row.update(resample(pf, probability, {**PARAMS, 'min_samples': pf.n, 'max_samples': pf.n}))
        if probability > 0:
            self.slow = self.fast = 0.
        row['samples_after'] = pf.n
        self.rows.append(row)
        return copy.deepcopy(row)


def attach(runtime, *, localization_recovery='off'):
    if localization_recovery == 'off':
        return runtime
    if localization_recovery != OPTION:
        raise ValueError('UNKNOWN_LOCALIZATION_RECOVERY')
    if (getattr(runtime, 'start_prior', None) != 'none_v1'
            or getattr(runtime, 'global_localization', None) != 'augmented_active_v1'
            or getattr(runtime, 'particle_sampling', None) != 'kld_global_v1'):
        raise ValueError('RECOVERY_REQUIRES_V139_UNKNOWN_START')
    if hasattr(runtime, 'tracking_recovery_audit'):
        raise ValueError('RECOVERY_ALREADY_ATTACHED')
    policy = Policy()
    audit = dict(option=OPTION, gt_inputs=False, contact_inputs=False,
        scope='S2 tracking after unchanged global KLD handoff',
        alpha_slow=ALPHA_SLOW, alpha_fast=ALPHA_FAST, resample_interval=1,
        selective_resampling=False, particle_budget='existing tracking N; min=max',
        random_pose='uniform static map free space, full yaw',
        ema_initialization='zero at tracking handoff; independent of changed global sample count',
        attached_t=None, rows=policy.rows)
    runtime.tracking_recovery_audit = audit
    command, record = runtime.on_command, runtime.record

    def on_command(rid, now, action):
        result = command(rid, now, action)
        pf = runtime.pose.provider.loc._pf
        if not runtime.global_policy.active and audit['attached_t'] is None:
            if hasattr(pf, 's2_global_policy'):
                raise ValueError('RECOVERY_POLICY_CONFLICT')
            pf.s2_global_policy = policy
            audit['attached_t'] = float(now)
            runtime.amcl_audit['tracking_after_global'] = dict(
                recovery_alpha_slow=ALPHA_SLOW, recovery_alpha_fast=ALPHA_FAST,
                selective_resampling=False, option=OPTION)
        return result

    def with_record():
        return {**record(), 'localization_recovery': copy.deepcopy(audit)}

    runtime.on_command, runtime.record = on_command, with_record
    from harness.zone_solo_cyan_v106 import hp
    inner = runtime.pose.provider
    inner.runtime_contract['s2_tracking_recovery'] = {k:v for k,v in audit.items() if k not in ('rows','attached_t')}
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_recovery:' + inner.identity_sha256[:8]
    runtime.pose.source = inner.source
    return runtime
